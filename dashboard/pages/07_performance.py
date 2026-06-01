import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from database.db import get_connection

st.set_page_config(page_title="Performance · Trading Bot", layout="wide")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from styles import inject_css
inject_css()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cutoff(period: str) -> str | None:
    now = datetime.now(timezone.utc)
    if period == "Today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    if period == "This Week":
        monday = now - timedelta(days=now.weekday())
        return monday.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    if period == "This Month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    return None


def _fmt_pnl(v) -> tuple:
    if v is None:
        return "—", ""
    return (f"+${v:,.2f}", "pos") if v >= 0 else (f"-${abs(v):,.2f}", "neg")


# ── Data ──────────────────────────────────────────────────────────────────────

def fetch_performance(period: str) -> dict:
    cutoff      = _cutoff(period)
    base_cond   = "pnl IS NOT NULL"
    base_params: list = []
    if cutoff:
        base_cond  += " AND timestamp >= ?"
        base_params = [cutoff]

    today       = datetime.now(timezone.utc).date()
    chart_start = str(today - timedelta(days=13))

    conn = get_connection()
    try:
        cur = conn.cursor()

        # KPIs
        cur.execute(
            f"SELECT COUNT(*) as n, SUM(pnl) as s, AVG(pnl) as a "
            f"FROM trades WHERE {base_cond}",
            base_params,
        )
        row         = cur.fetchone()
        trade_count = row["n"] or 0
        total_pnl   = row["s"] or 0.0
        avg_pnl     = row["a"] or 0.0

        cur.execute(
            f"SELECT COUNT(*) as n FROM trades WHERE {base_cond} AND pnl > 0",
            base_params,
        )
        wins     = cur.fetchone()["n"]
        win_rate = (wins / trade_count * 100) if trade_count > 0 else 0.0

        cur.execute("SELECT COUNT(*) as n FROM trades")
        total_in_db = cur.fetchone()["n"] or 0

        # 14-day daily chart (fixed window — always last 14 calendar days)
        daily: dict = {
            str(today - timedelta(days=i)): {"wins": 0, "total": 0, "pnl": 0.0}
            for i in range(13, -1, -1)
        }
        cur.execute(
            """
            SELECT DATE(timestamp) as day,
                   COUNT(*) as n,
                   SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as w,
                   SUM(pnl) as s
            FROM trades
            WHERE pnl IS NOT NULL AND timestamp >= ?
            GROUP BY DATE(timestamp)
            """,
            [chart_start],
        )
        for r in cur.fetchall():
            if r["day"] in daily:
                daily[r["day"]] = {
                    "wins":  r["w"] or 0,
                    "total": r["n"] or 0,
                    "pnl":   r["s"] or 0.0,
                }

        # By symbol
        symbol_stats: dict = {}
        for sym in ["US500", "US100", "BTC"]:
            cur.execute(
                f"""
                SELECT COUNT(*) as n,
                       SUM(pnl) as s,
                       SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as w,
                       MAX(pnl) as best,
                       MIN(pnl) as worst
                FROM trades WHERE {base_cond} AND symbol = ?
                """,
                base_params + [sym],
            )
            symbol_stats[sym] = dict(cur.fetchone())

        # By source
        source_stats: dict = {}
        for src in ["tradingview_webhook", "signal_loop"]:
            if src == "signal_loop":
                cur.execute(
                    f"""
                    SELECT COUNT(*) as n,
                           SUM(pnl) as s,
                           SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as w
                    FROM trades WHERE {base_cond}
                      AND source IN ('signal_loop', 'live_signal_loop')
                    """,
                    base_params,
                )
            else:
                cur.execute(
                    f"""
                    SELECT COUNT(*) as n,
                           SUM(pnl) as s,
                           SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as w
                    FROM trades WHERE {base_cond} AND source = ?
                    """,
                    base_params + [src],
                )
            source_stats[src] = dict(cur.fetchone())

        # By strategy
        cur.execute(
            f"""
            SELECT strategy_name, symbol, source,
                   COUNT(*) as total,
                   SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                   COALESCE(SUM(pnl), 0) as total_pnl,
                   COALESCE(AVG(pnl), 0) as avg_pnl
            FROM trades
            WHERE {base_cond}
            AND status = 'CLOSED'
            AND source != 'ig_import'
            AND (strategy_name IS NULL OR strategy_name != 'manual')
            AND strategy_name != 'youtube'
            AND symbol != 'BTC'
            GROUP BY strategy_name, symbol, source
            ORDER BY total_pnl DESC
            """,
            base_params,
        )
        strategy_stats = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT strategy_name, symbol
            FROM active_strategy
            WHERE status = 'active'
        """)
        active_set = {(r['strategy_name'], r['symbol']) for r in cur.fetchall()}

        # Best / worst 5
        cur.execute(
            f"""
            SELECT timestamp, symbol, strategy_name, source, pnl
            FROM trades WHERE {base_cond} AND pnl > 0
            ORDER BY pnl DESC LIMIT 5
            """,
            base_params,
        )
        top_winners = [dict(r) for r in cur.fetchall()]

        cur.execute(
            f"""
            SELECT timestamp, symbol, strategy_name, source, pnl
            FROM trades WHERE {base_cond} AND pnl < 0
            ORDER BY pnl ASC LIMIT 5
            """,
            base_params,
        )
        top_losers = [dict(r) for r in cur.fetchall()]

    finally:
        conn.close()

    return {
        "trade_count":    trade_count,
        "total_in_db":    total_in_db,
        "total_pnl":      total_pnl,
        "avg_pnl":        avg_pnl,
        "win_rate":       win_rate,
        "wins":           wins,
        "daily":          daily,
        "symbol_stats":   symbol_stats,
        "source_stats":   source_stats,
        "strategy_stats": strategy_stats,
        "active_set":     active_set,
        "top_winners":    top_winners,
        "top_losers":     top_losers,
    }


# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""
<h1 style="margin-bottom:4px">Performance Analytics</h1>
<p style="color:#8B949E;font-size:13px;margin-top:0">Win rates, P&amp;L trends and strategy breakdown</p>
""", unsafe_allow_html=True)


# ── Strategy History ──────────────────────────────────────────────────────────

st.markdown('<div class="section-hd">Strategy History</div>', unsafe_allow_html=True)

try:
    _hist_conn = get_connection()
    try:
        _hist_cur = _hist_conn.cursor()
        _hist_cur.execute("""
            SELECT changed_at, symbol, strategy_name, timeframe, score, reason
            FROM active_strategy_history
            ORDER BY changed_at DESC LIMIT 10
        """)
        _hist_rows = [dict(r) for r in _hist_cur.fetchall()]
    finally:
        _hist_conn.close()

    if _hist_rows:
        _hist_df = pd.DataFrame(_hist_rows)
        _hist_df["changed_at"] = _hist_df["changed_at"].apply(
            lambda t: (
                datetime.fromisoformat(t.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M UTC")
                if t else "—"
            )
        )
        _hist_df = _hist_df.rename(columns={
            "changed_at":    "Changed",
            "symbol":        "Symbol",
            "strategy_name": "Strategy",
            "timeframe":     "TF",
            "score":         "Score",
            "reason":        "Reason",
        })
        st.dataframe(
            _hist_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Changed":  st.column_config.TextColumn("Changed"),
                "Symbol":   st.column_config.TextColumn("Symbol"),
                "Strategy": st.column_config.TextColumn("Strategy"),
                "TF":       st.column_config.TextColumn("TF"),
                "Score":    st.column_config.NumberColumn("Score", format="%.3f"),
                "Reason":   st.column_config.TextColumn("Reason"),
            },
        )
    else:
        st.markdown("""
        <div style="background:#161B22;border:1px solid #30363D;border-radius:10px;
                    padding:24px;text-align:center;color:#8B949E;font-size:13px">
          No strategy changes recorded yet.
        </div>
        """, unsafe_allow_html=True)
except Exception:
    st.markdown("""
    <div style="background:#161B22;border:1px solid #30363D;border-radius:10px;
                padding:24px;text-align:center;color:#8B949E;font-size:13px">
      Strategy history unavailable.
    </div>
    """, unsafe_allow_html=True)


# ── Period filter ─────────────────────────────────────────────────────────────

period = st.selectbox(
    "Period",
    ["Today", "This Week", "This Month", "All Time"],
    index=3,
    label_visibility="collapsed",
)

d = fetch_performance(period)


# ── Row 1 — KPI cards ─────────────────────────────────────────────────────────

st.markdown('<div class="section-hd">Summary</div>', unsafe_allow_html=True)

wr_card     = "green" if d["win_rate"] >= 50 else "amber"
pnl_card    = "green" if d["total_pnl"] >= 0 else "red"
avg_card    = "green" if d["avg_pnl"]   >= 0 else "red"
pnl_val_cls = "pos"   if d["total_pnl"] >= 0 else "neg"
avg_val_cls = "pos"   if d["avg_pnl"]   >= 0 else "neg"
pnl_sign    = "+"     if d["total_pnl"] >= 0 else ""
avg_sign    = "+"     if d["avg_pnl"]   >= 0 else ""

st.markdown(f"""
<div class="kpi-grid">
  <div class="kpi-card {wr_card}">
    <div class="kpi-label">Win Rate</div>
    <div class="kpi-value">{d['win_rate']:.1f}<span style="font-size:16px">%</span></div>
    <div class="kpi-sub">{d['wins']} of {d['trade_count']} trades</div>
  </div>
  <div class="kpi-card {pnl_card}">
    <div class="kpi-label">Total P&amp;L</div>
    <div class="kpi-value {pnl_val_cls}">{pnl_sign}${d['total_pnl']:,.2f}</div>
    <div class="kpi-sub">Closed trades · {period}</div>
  </div>
  <div class="kpi-card blue">
    <div class="kpi-label">Trade Count</div>
    <div class="kpi-value">{d['trade_count']}</div>
    <div class="kpi-sub">{d['trade_count']} with P&amp;L · {d['total_in_db']} total in DB</div>
  </div>
  <div class="kpi-card {avg_card}">
    <div class="kpi-label">Avg P&amp;L / Trade</div>
    <div class="kpi-value {avg_val_cls}">{avg_sign}${d['avg_pnl']:,.2f}</div>
    <div class="kpi-sub">Per closed trade</div>
  </div>
</div>
""", unsafe_allow_html=True)


# ── Row 2 — Daily win rate bar chart ─────────────────────────────────────────

st.markdown('<div class="section-hd">Daily Win Rate — Last 14 Days</div>', unsafe_allow_html=True)

daily    = d["daily"]
dates    = list(daily.keys())
wr_vals  : list = []
bar_cols : list = []
hover    : list = []

for dt in dates:
    day_d = daily[dt]
    if day_d["total"] == 0:
        wr_vals.append(0)
        bar_cols.append("#30363D")
        hover.append(f"{dt}<br>No trades")
    else:
        wr = day_d["wins"] / day_d["total"] * 100
        wr_vals.append(wr)
        bar_cols.append("#22C55E" if day_d["pnl"] >= 0 else "#EF4444")
        pnl_str = f"+${day_d['pnl']:,.2f}" if day_d["pnl"] >= 0 else f"-${abs(day_d['pnl']):,.2f}"
        hover.append(
            f"{dt}<br>Win rate: {wr:.0f}%<br>Trades: {day_d['total']}<br>P&L: {pnl_str}"
        )

fig = go.Figure()
fig.add_trace(go.Bar(
    x=dates,
    y=wr_vals,
    marker_color=bar_cols,
    hovertemplate="%{customdata}<extra></extra>",
    customdata=hover,
))
fig.add_hline(
    y=50,
    line_dash="dot",
    line_color="#8B949E",
    line_width=1,
    annotation_text="50%",
    annotation_font_color="#8B949E",
    annotation_font_size=10,
)
fig.update_layout(
    paper_bgcolor="#161B22",
    plot_bgcolor="#161B22",
    font=dict(family="Inter, sans-serif", color="#8B949E", size=11),
    xaxis=dict(
        showgrid=False,
        zeroline=False,
        tickfont=dict(color="#8B949E", size=10),
        title=None,
    ),
    yaxis=dict(
        showgrid=True,
        gridcolor="#21262D",
        gridwidth=1,
        zeroline=False,
        ticksuffix="%",
        tickfont=dict(color="#8B949E"),
        range=[0, 105],
        title=None,
    ),
    margin=dict(l=0, r=0, t=8, b=0),
    height=240,
    bargap=0.25,
    showlegend=False,
)
st.plotly_chart(fig, use_container_width=True)


# ── Row 3 — By symbol ─────────────────────────────────────────────────────────

st.markdown('<div class="section-hd">By Symbol</div>', unsafe_allow_html=True)

for col, sym in zip(st.columns(3), ["US500", "US100", "BTC"]):
    with col:
        s    = d["symbol_stats"][sym]
        n    = s["n"] or 0
        wr_s = (s["w"] / n * 100) if n > 0 else 0.0
        tot  = s["s"] or 0.0

        tot_str,  tot_cls  = _fmt_pnl(tot)
        best_str, best_cls = _fmt_pnl(s["best"])
        wrst_str, wrst_cls = _fmt_pnl(s["worst"])
        wr_color = "#22C55E" if wr_s >= 50 else "#EF4444"

        st.markdown(f"""
        <div style="background:#161B22;border:1px solid #30363D;border-radius:10px;padding:16px 20px">
          <div style="font-size:13px;font-weight:600;color:#58A6FF;margin-bottom:12px">{sym}</div>
          <div class="info-tile">
            <div class="lbl">Win Rate</div><div class="val"><span style="background:{wr_color}22;color:{wr_color};padding:2px 10px;border-radius:4px;font-weight:700">{wr_s:.1f}%</span></div>
          </div>
          <div class="info-tile">
            <div class="lbl">Total P&amp;L</div>
            <div class="val"><span class="cal-pnl {tot_cls}">{tot_str}</span></div>
          </div>
          <div class="info-tile">
            <div class="lbl">Trades</div><div class="val">{n}</div>
          </div>
          <div class="info-tile">
            <div class="lbl">Best trade</div>
            <div class="val"><span class="cal-pnl {best_cls}">{best_str}</span></div>
          </div>
          <div class="info-tile">
            <div class="lbl">Worst trade</div>
            <div class="val"><span class="cal-pnl {wrst_cls}">{wrst_str}</span></div>
          </div>
        </div>
        """, unsafe_allow_html=True)


# ── Row 4 — By source ─────────────────────────────────────────────────────────

st.markdown('<div class="section-hd">By Source</div>', unsafe_allow_html=True)

_SRC_META = {
    "tradingview_webhook": ("SwiftAlgo", "Pine Script / TradingView webhook"),
    "signal_loop":         ("Bot",       "Autonomous signal loop"),
}

for col, src in zip(st.columns(2), ["tradingview_webhook", "signal_loop"]):
    with col:
        s     = d["source_stats"][src]
        label, sublabel = _SRC_META[src]
        n     = s["n"] or 0
        tot   = s["s"] or 0.0
        wr_src = (s["w"] / n * 100) if n > 0 else 0.0

        tot_str, tot_cls = _fmt_pnl(tot)
        wr_src_color = "#22C55E" if wr_src >= 50 else "#EF4444"

        st.markdown(f"""
        <div style="background:#161B22;border:1px solid #30363D;border-radius:10px;padding:16px 20px">
          <div style="margin-bottom:12px">
            <div style="font-size:13px;font-weight:600;color:#58A6FF">{label}</div>
            <div style="font-size:11px;color:#8B949E;margin-top:2px">{sublabel}</div>
          </div>
          <div class="info-tile">
            <div class="lbl">Trades</div><div class="val">{n}</div>
          </div>
          <div class="info-tile">
            <div class="lbl">Win Rate</div><div class="val"><span style="background:{wr_src_color}22;color:{wr_src_color};padding:2px 10px;border-radius:4px;font-weight:700">{wr_src:.1f}%</span></div>
          </div>
          <div class="info-tile">
            <div class="lbl">Total P&amp;L</div>
            <div class="val"><span class="cal-pnl {tot_cls}">{tot_str}</span></div>
          </div>
        </div>
        """, unsafe_allow_html=True)


# ── Row 5 — By strategy ───────────────────────────────────────────────────────

st.markdown('<div class="section-hd">By Strategy</div>', unsafe_allow_html=True)
st.markdown(
    '<p style="color:#8B949E;font-size:12px;margin-top:-8px;margin-bottom:12px">'
    'US500 &amp; US100 only. '
    '<span style="color:#22C55E">● Active</span> = currently selected by daily cron. '
    'Dimmed rows = never traded live.</p>',
    unsafe_allow_html=True,
)

_SRC_LABEL = {
    "live_signal_loop":    "Bot",
    "signal_loop":         "Bot",
    "tradingview_webhook": "SwiftAlgo",
    "manual":              "Manual",
}

_ALL_STRATEGIES = [
    'rsi', 'stoch_rsi', 'supertrend', 'vwap_ema',
    'ema_ribbon', 'bb_squeeze', 'rsi_divergence',
    'orb', 'ichimoku', 'keltner', 'ema_cross_volume',
    'vwap_mean_reversion', 'connors_rsi2',
]
_LIVE_SYMBOLS = ['US500', 'US100']

_active_set = d.get("active_set", set())

# Merge real rows with placeholder rows for untested strategy+symbol combos
_seen   = {(r["strategy_name"], r["symbol"]) for r in d["strategy_stats"]}
_all_rows = list(d["strategy_stats"])
for _sn in _ALL_STRATEGIES:
    for _sym_name in _LIVE_SYMBOLS:
        if (_sn, _sym_name) not in _seen:
            _all_rows.append({
                "strategy_name": _sn,
                "symbol":        _sym_name,
                "source":        None,
                "total":         0,
                "wins":          0,
                "total_pnl":     0.0,
                "avg_pnl":       0.0,
                "_placeholder":  True,
            })

def _strat_sort_key(r):
    _act      = (r["strategy_name"], r["symbol"]) in _active_set
    _has      = (r.get("total") or 0) > 0
    # groups: 0=active+trades, 1=active+no trades, 2=inactive+trades, 3=no trades
    group = 0 if (_act and _has) else 1 if _act else 2 if _has else 3
    return (group, -(r.get("total") or 0))

_all_rows.sort(key=_strat_sort_key)

_rows_html = ""
for _sr in _all_rows:
    _is_active      = (_sr["strategy_name"], _sr["symbol"]) in _active_set
    _is_placeholder = _sr.get("_placeholder", False)
    _n              = _sr["total"] or 0

    if _is_active:
        _status_html = '<span style="color:#22C55E;font-weight:600">&#9679; Active</span>'
    elif _is_placeholder:
        _status_html = '<span style="color:#484F58">&#9675; No live trades</span>'
    else:
        _status_html = '<span style="color:#8B949E">&#9675; Inactive</span>'

    if _n > 0:
        _w         = _sr["wins"] or 0
        _wr        = _w / _n * 100
        _pnl       = _sr["total_pnl"] or 0.0
        _avg       = _sr["avg_pnl"] or 0.0
        _wr_color  = "#22C55E" if _wr >= 50 else "#EF4444"
        _pnl_color = "#22C55E" if _pnl >= 0 else "#EF4444"
        _avg_color = "#22C55E" if _avg >= 0 else "#EF4444"
        _pnl_str   = f"+${_pnl:,.2f}" if _pnl >= 0 else f"-${abs(_pnl):,.2f}"
        _avg_str   = f"+${_avg:,.2f}" if _avg >= 0 else f"-${abs(_avg):,.2f}"
        _n_td   = f'<td style="padding:10px 16px;color:#E6EDF3">{_n}</td>'
        _wr_td  = f'<td style="padding:10px 16px"><span style="background:{_wr_color}22;color:{_wr_color};padding:2px 10px;border-radius:4px;font-weight:700">{_wr:.1f}%</span></td>'
        _pnl_td = f'<td style="padding:10px 16px;color:{_pnl_color}">{_pnl_str}</td>'
        _avg_td = f'<td style="padding:10px 16px;color:{_avg_color}">{_avg_str}</td>'
    else:
        _n_td   = '<td style="padding:10px 16px;color:#484F58">0</td>'
        _wr_td  = '<td style="padding:10px 16px;color:#484F58">—</td>'
        _pnl_td = '<td style="padding:10px 16px;color:#484F58">—</td>'
        _avg_td = '<td style="padding:10px 16px;color:#484F58">—</td>'

    _src_lbl    = _SRC_LABEL.get(_sr["source"] or "", "—") if _sr["source"] else "—"
    _strat      = _sr["strategy_name"] or "—"
    _sym        = _sr["symbol"] or "—"
    _dim        = _is_placeholder and not _is_active
    _name_color = "#6E7681" if _dim else "#E6EDF3"
    _sym_color  = "#3D6B8E" if _dim else "#58A6FF"
    _rows_html += f"""<tr style="border-bottom:1px solid #21262D{';opacity:0.6' if _dim else ''}">
      <td style="padding:10px 16px;color:{_name_color}">{_strat}</td>
      <td style="padding:10px 16px;color:{_sym_color};font-weight:600">{_sym}</td>
      <td style="padding:10px 16px;color:#8B949E">{_src_lbl}</td>
      <td style="padding:10px 16px">{_status_html}</td>
      {_n_td}{_wr_td}{_pnl_td}{_avg_td}
    </tr>"""

st.markdown(f"""
<div style="background:#161B22;border:1px solid #30363D;border-radius:10px;overflow:hidden">
  <table style="width:100%;border-collapse:collapse;font-size:13px">
    <thead>
      <tr style="border-bottom:1px solid #30363D">
        <th style="text-align:left;padding:10px 16px;color:#8B949E;font-weight:500">Strategy</th>
        <th style="text-align:left;padding:10px 16px;color:#8B949E;font-weight:500">Symbol</th>
        <th style="text-align:left;padding:10px 16px;color:#8B949E;font-weight:500">Source</th>
        <th style="text-align:left;padding:10px 16px;color:#8B949E;font-weight:500">Status</th>
        <th style="text-align:left;padding:10px 16px;color:#8B949E;font-weight:500">Trades</th>
        <th style="text-align:left;padding:10px 16px;color:#8B949E;font-weight:500">Win Rate</th>
        <th style="text-align:left;padding:10px 16px;color:#8B949E;font-weight:500">Total P&amp;L</th>
        <th style="text-align:left;padding:10px 16px;color:#8B949E;font-weight:500">Avg P&amp;L</th>
      </tr>
    </thead>
    <tbody>{_rows_html}</tbody>
  </table>
</div>
""", unsafe_allow_html=True)


# ── Row 6 — Best and worst trades ─────────────────────────────────────────────

st.markdown('<div class="section-hd">Best &amp; Worst Trades</div>', unsafe_allow_html=True)


def _trade_table(trades: list, empty_label: str) -> None:
    if not trades:
        st.markdown(f"""
        <div style="background:#161B22;border:1px solid #30363D;border-radius:10px;
                    padding:24px;text-align:center;color:#8B949E;font-size:13px">
          No {empty_label} for selected period.
        </div>
        """, unsafe_allow_html=True)
        return
    df = pd.DataFrame(trades)
    df["pnl"] = df["pnl"].apply(
        lambda v: f"+${v:,.2f}" if v > 0 else f"-${abs(v):,.2f}"
    )
    if "timestamp" in df.columns:
        df["timestamp"] = df["timestamp"].apply(lambda t: t[:16] if t else "—")
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "timestamp":     st.column_config.TextColumn("Time"),
            "symbol":        st.column_config.TextColumn("Symbol"),
            "strategy_name": st.column_config.TextColumn("Strategy"),
            "source":        st.column_config.TextColumn("Source"),
            "pnl":           st.column_config.TextColumn("P&L"),
        },
    )


bw_left, bw_right = st.columns(2)

with bw_left:
    st.markdown(
        '<div class="section-hd" style="margin-top:4px">Top 5 Winners</div>',
        unsafe_allow_html=True,
    )
    _trade_table(d["top_winners"], "winning trades")

with bw_right:
    st.markdown(
        '<div class="section-hd" style="margin-top:4px">Top 5 Losers</div>',
        unsafe_allow_html=True,
    )
    _trade_table(d["top_losers"], "losing trades")


# ── Row 7 — Paper vs Live ─────────────────────────────────────────────────────

st.markdown('<div class="section-hd">📄 Paper vs Live</div>', unsafe_allow_html=True)

try:
    _pconn = get_connection()
    try:
        _pcur = _pconn.cursor()
        _pcur.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN outcome='WIN'  THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) as losses,
                   COALESCE(SUM(simulated_pnl), 0) as total_pnl
            FROM paper_trades
        """)
        _pr       = dict(_pcur.fetchone())

        _pcur.execute("""
            SELECT strategy_name,
                   COUNT(*) as total,
                   SUM(CASE WHEN outcome='WIN'  THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) as losses,
                   COALESCE(SUM(simulated_pnl), 0) as total_pnl
            FROM paper_trades
            WHERE outcome IN ('WIN', 'LOSS')
            GROUP BY strategy_name
            ORDER BY total DESC
        """)
        _p_by_strat = [dict(r) for r in _pcur.fetchall()]
        _p_total  = _pr["total"]     or 0
        _p_wins   = _pr["wins"]      or 0
        _p_losses = _pr["losses"]    or 0
        _p_pnl    = _pr["total_pnl"] or 0.0
        _p_wr     = (_p_wins / (_p_wins + _p_losses) * 100) if (_p_wins + _p_losses) > 0 else 0.0
    finally:
        _pconn.close()

    pv_left, pv_right = st.columns(2)

    with pv_left:
        st.markdown(
            '<div class="section-hd" style="margin-top:4px">Live (Bot)</div>',
            unsafe_allow_html=True,
        )
        s_bot    = d["source_stats"]["signal_loop"]
        n_bot    = s_bot["n"] or 0
        tot_bot  = s_bot["s"] or 0.0
        wr_bot   = (s_bot["w"] / n_bot * 100) if n_bot > 0 else 0.0
        tot_str, tot_cls = _fmt_pnl(tot_bot)
        wr_color = "#22C55E" if wr_bot >= 50 else "#EF4444"
        st.markdown(f"""
        <div style="background:#161B22;border:1px solid #30363D;border-radius:10px;padding:16px 20px">
          <div class="info-tile"><div class="lbl">Trades</div><div class="val">{n_bot}</div></div>
          <div class="info-tile">
            <div class="lbl">Win Rate</div>
            <div class="val"><span style="background:{wr_color}22;color:{wr_color};padding:2px 10px;border-radius:4px;font-weight:700">{wr_bot:.1f}%</span></div>
          </div>
          <div class="info-tile">
            <div class="lbl">Total P&amp;L</div>
            <div class="val"><span class="cal-pnl {tot_cls}">{tot_str}</span></div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    with pv_right:
        st.markdown(
            '<div class="section-hd" style="margin-top:4px">Paper (Simulated)</div>',
            unsafe_allow_html=True,
        )
        _resolved = _p_wins + _p_losses
        wr_color_p  = "#3B82F6" if _p_wr >= 50 else "#8B5CF6"
        pnl_str_p, pnl_cls_p = _fmt_pnl(_p_pnl) if _resolved > 0 else ("pending", "")

        _strat_breakdown_html = ""
        for _bs in _p_by_strat:
            _bs_res = (_bs["wins"] or 0) + (_bs["losses"] or 0)
            _bs_wr  = (_bs["wins"] / _bs_res * 100) if _bs_res > 0 else 0.0
            _bs_pnl = _bs["total_pnl"] or 0.0
            _bs_src = "📡 webhook" if _bs["strategy_name"] == "smc" else "🔄 loop"
            _bs_wr_c = "#3B82F6" if _bs_wr >= 50 else "#8B5CF6"
            _bs_pnl_s, _bs_pnl_c = _fmt_pnl(_bs_pnl)
            _strat_breakdown_html += (
                f'<div class="info-tile">'
                f'<div class="lbl">{_bs["strategy_name"]} <span style="font-size:10px;color:#8B949E">{_bs_src}</span></div>'
                f'<div class="val"><span style="background:{_bs_wr_c}22;color:{_bs_wr_c};'
                f'padding:1px 6px;border-radius:3px;font-size:11px;font-weight:700">'
                f'{_bs_wr:.0f}%</span>'
                f'<span style="color:#8B949E;font-size:10px;margin-left:6px">'
                f'{_bs["wins"]}W/{_bs["losses"]}L · <span class="cal-pnl {_bs_pnl_c}">{_bs_pnl_s}</span></span>'
                f'</div></div>'
            )

        st.markdown(f"""
        <div style="background:#161B22;border:1px solid #1D4ED8;border-radius:10px;padding:16px 20px">
          <div class="info-tile"><div class="lbl">Signals</div><div class="val">{_p_total}</div></div>
          <div class="info-tile">
            <div class="lbl">Sim Win Rate</div>
            <div class="val"><span style="background:{wr_color_p}22;color:{wr_color_p};padding:2px 10px;border-radius:4px;font-weight:700">{"—" if _resolved == 0 else f"{_p_wr:.1f}%"}</span></div>
          </div>
          <div class="info-tile">
            <div class="lbl">Sim P&amp;L</div>
            <div class="val"><span class="cal-pnl {pnl_cls_p}">{pnl_str_p}</span></div>
          </div>
          {('<div style="border-top:1px solid #21262D;margin-top:8px;padding-top:8px">' + _strat_breakdown_html + '</div>') if _strat_breakdown_html else ''}
        </div>
        """, unsafe_allow_html=True)

except Exception as _pe:
    st.markdown(f"""
    <div style="background:#161B22;border:1px solid #30363D;border-radius:10px;
                padding:24px;text-align:center;color:#8B949E;font-size:13px">
      Paper stats unavailable: {_pe}
    </div>
    """, unsafe_allow_html=True)
