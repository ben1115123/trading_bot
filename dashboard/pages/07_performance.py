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
        "trade_count":  trade_count,
        "total_pnl":    total_pnl,
        "avg_pnl":      avg_pnl,
        "win_rate":     win_rate,
        "wins":         wins,
        "daily":        daily,
        "symbol_stats": symbol_stats,
        "source_stats": source_stats,
        "top_winners":  top_winners,
        "top_losers":   top_losers,
    }


# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""
<h1 style="margin-bottom:4px">Performance Analytics</h1>
<p style="color:#8B949E;font-size:13px;margin-top:0">Win rates, P&amp;L trends and strategy breakdown</p>
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
    <div class="kpi-sub">{period}</div>
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

        st.markdown(f"""
        <div style="background:#161B22;border:1px solid #30363D;border-radius:10px;padding:16px 20px">
          <div style="font-size:13px;font-weight:600;color:#58A6FF;margin-bottom:12px">{sym}</div>
          <div class="info-tile">
            <div class="lbl">Win Rate</div><div class="val">{wr_s:.1f}%</div>
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
            <div class="lbl">Win Rate</div><div class="val">{wr_src:.1f}%</div>
          </div>
          <div class="info-tile">
            <div class="lbl">Total P&amp;L</div>
            <div class="val"><span class="cal-pnl {tot_cls}">{tot_str}</span></div>
          </div>
        </div>
        """, unsafe_allow_html=True)


# ── Row 5 — Best and worst trades ─────────────────────────────────────────────

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
