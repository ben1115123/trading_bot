import sys
import re
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from database.db import get_connection

st.set_page_config(page_title="Overview · Trading Bot", layout="wide")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from styles import inject_css
inject_css()


# ── Data ─────────────────────────────────────────────────────────────────────

def fetch_data():
    conn = get_connection()
    try:
        cur = conn.cursor()

        try:
            cur.execute("SELECT * FROM signal_log ORDER BY id DESC LIMIT 20")
            signal_rows = [dict(r) for r in cur.fetchall()]
        except Exception:
            signal_rows = []

        today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cur.execute("""
            SELECT SUM(pnl) as s, COUNT(*) as n FROM trades
            WHERE pnl IS NOT NULL AND UPPER(status) = 'CLOSED'
              AND DATE(timestamp) = ?
        """, (today_utc,))
        row = cur.fetchone()
        today_pnl = row["s"] if row and row["s"] is not None else None
        today_count = row["n"] if row else 0

        cur.execute("""
            SELECT timestamp, pnl FROM trades
            WHERE pnl IS NOT NULL ORDER BY id ASC
        """)
        pnl_rows = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT COUNT(*) as n,
                   COALESCE(ABS(SUM(CASE WHEN pnl < 0 THEN pnl ELSE 0 END)), 0) as losses
            FROM trades
            WHERE source IN ('signal_loop', 'live_signal_loop')
            AND DATE(timestamp) = ?
        """, (today_utc,))
        risk_row         = dict(cur.fetchone())
        today_bot_trades = risk_row["n"]
        today_bot_losses = risk_row["losses"]

        cur.execute("""
            SELECT symbol, strategy_name, source,
                   COUNT(*) as total,
                   SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
                   COALESCE(SUM(pnl), 0) as total_pnl
            FROM trades
            WHERE pnl IS NOT NULL
            AND UPPER(status) = 'CLOSED'
            GROUP BY symbol, strategy_name, source
        """)
        strategy_stats = {
            f"{r['symbol']}_{r['strategy_name']}_{r['source']}": dict(r)
            for r in cur.fetchall()
        }

        try:
            cur.execute("""
                SELECT symbol, strategy_name, timeframe,
                       COUNT(*) as total,
                       SUM(CASE WHEN simulated_pnl > 0 THEN 1 ELSE 0 END) as wins,
                       SUM(CASE WHEN simulated_pnl < 0 THEN 1 ELSE 0 END) as losses,
                       COALESCE(SUM(simulated_pnl), 0) as total_pnl
                FROM paper_trades
                GROUP BY symbol, strategy_name, timeframe
            """)
            paper_stats = {
                f"{r['symbol']}_{r['timeframe']}_{r['strategy_name']}": dict(r)
                for r in cur.fetchall()
            }
        except Exception:
            paper_stats = {}

        try:
            cur.execute("""
                SELECT a.strategy_name, a.symbol, a.timeframe, a.status, a.backtest_id,
                       b.win_rate as bt_win_rate, b.total_profit as bt_profit
                FROM active_strategy a
                LEFT JOIN backtest_results b ON a.backtest_id = b.id
                WHERE a.status IN ('active', 'live', 'paper')
            """)
            pipeline_rows = [dict(r) for r in cur.fetchall()]
        except Exception:
            pipeline_rows = []

        try:
            cur.execute("""
                SELECT symbol, timeframe, strategy_name, signal, checked_at, candle_time, error
                FROM signal_log
                WHERE id IN (SELECT MAX(id) FROM signal_log GROUP BY symbol, timeframe, strategy_name)
            """)
            signal_by_key = {
                (r["symbol"], r["timeframe"], r["strategy_name"]): dict(r)
                for r in cur.fetchall()
            }
        except Exception:
            signal_by_key = {}

        try:
            cur.execute("""
                SELECT symbol, timeframe, strategy_name, COUNT(*) as n
                FROM paper_trades
                WHERE DATE(checked_at) = ?
                GROUP BY symbol, timeframe, strategy_name
            """, (today_utc,))
            today_paper_by_key = {
                (r["symbol"], r["timeframe"], r["strategy_name"]): r["n"]
                for r in cur.fetchall()
            }
        except Exception:
            today_paper_by_key = {}

    finally:
        conn.close()

    return signal_rows, today_pnl, today_count, pnl_rows, today_bot_trades, today_bot_losses, strategy_stats, paper_stats, pipeline_rows, signal_by_key, today_paper_by_key


signal_rows, today_pnl, today_count, pnl_rows, today_bot_trades, today_bot_losses, strategy_stats, paper_stats, pipeline_rows, signal_by_key, today_paper_by_key = fetch_data()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_ts(ts):
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return ts[:16]


def _next_check(ts):
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return (dt + timedelta(hours=1)).strftime("%H:%M UTC")
    except Exception:
        return "—"


def _age_hours(ts_str):
    """Return float hours since ts_str, or None on parse failure."""
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except Exception:
        return None


def _paper_stats_html(stats_key: str, paper_stats: dict) -> str:
    data = paper_stats.get(stats_key)
    if not data or data.get("total", 0) == 0:
        return '<div style="font-size:11px;color:#8B949E;margin-top:2px;margin-bottom:8px">No paper signals yet</div>'
    total     = data["total"]
    wins      = data.get("wins") or 0
    losses    = data.get("losses") or 0
    total_pnl = data.get("total_pnl") or 0.0
    if wins > 0 or losses > 0:
        win_rate = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0.0
        pnl_sign = "+" if total_pnl >= 0 else ""
        return (
            f'<div style="font-size:11px;margin-bottom:8px">'
            f'<span style="color:#3B82F6;background:#3B82F622;'
            f'padding:2px 8px;border-radius:4px;font-weight:700">{win_rate:.0f}% sim</span>'
            f'<span style="color:#8B949E;font-size:10px;margin-left:6px">'
            f'{wins}W/{losses}L · {pnl_sign}${total_pnl:.2f} sim</span></div>'
        )
    return (
        f'<div style="font-size:11px;color:#8B949E;margin-bottom:8px">'
        f'{total} signal{"s" if total != 1 else ""} fired · P&amp;L pending</div>'
    )


def _parse_daily_log(log_path):
    """Return dict with ts/backtests/strategies/errors from last run block."""
    try:
        text = Path(log_path).read_text()
        lines = text.splitlines()
        last_idx = None
        for i, line in enumerate(lines):
            if "Daily run complete" in line:
                last_idx = i
        if last_idx is None:
            return None
        block = "\n".join(lines[max(0, last_idx - 30):last_idx + 1])
        ts_m  = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", block)
        bt_m  = re.search(r"(\d+)\s+backtests?", block)
        st_m  = re.search(r"(\d+)\s+strategies?\s+updated", block)
        err_m = re.search(r"(\d+)\s+errors?", block)
        return {
            "ts":         ts_m.group(1)       if ts_m  else None,
            "backtests":  int(bt_m.group(1))  if bt_m  else "—",
            "strategies": int(st_m.group(1))  if st_m  else "—",
            "errors":     int(err_m.group(1)) if err_m else "—",
        }
    except Exception:
        return None


_SIG_COLOR = {
    "BUY":        "#22C55E",
    "SELL":       "#EF4444",
    "NONE":       "#8B949E",
    "ERROR":      "#F97316",
    "BLOCKED":    "#F59E0B",
    "PAPER_BUY":  "#3B82F6",
    "PAPER_SELL": "#8B5CF6",
}
LOG_PATH   = "/app/logs/daily_run.log"

cron_info = _parse_daily_log(LOG_PATH)

SOURCE_MAP = {
    ("EURUSD", "swiftalgo", "HOUR"): "webhook",
    ("US500",  "swiftalgo", "HOUR"): "webhook",
}
SUBTITLE_MAP = {
    ("EURUSD", "swiftalgo", "HOUR"):       "Webhook only",
    ("US500",  "swiftalgo", "HOUR"):       "Webhook only",
    ("EURUSD", "london_breakout", "15MIN"): "06:00–09:00 UTC",
}
GROUP_BORDER = {
    "LIVE":        "#3B82F6",
    "PAPER_HOUR":  "#F59E0B",
    "PAPER_15MIN": "#22C55E",
}
GROUP_TITLES = {
    "LIVE":        ("LIVE",                     "#3B82F6"),
    "PAPER_HOUR":  ("PAPER · HOUR (Swing)",     "#F59E0B"),
    "PAPER_15MIN": ("PAPER · 15MIN (Intraday)", "#22C55E"),
}


def _strategy_group(row):
    if row["status"] in ("active", "live"):
        return "LIVE"
    if row["status"] == "paper" and row["timeframe"] == "HOUR":
        return "PAPER_HOUR"
    if row["status"] == "paper" and row["timeframe"] == "15MIN":
        return "PAPER_15MIN"
    return None


def _render_strategy_card(row):
    symbol, tf, strat = row["symbol"], row["timeframe"], row["strategy_name"]
    group  = _strategy_group(row)
    src    = SOURCE_MAP.get((symbol, strat, tf), "loop")
    subt   = SUBTITLE_MAP.get((symbol, strat, tf))
    border = GROUP_BORDER.get(group, "#30363D")

    src_badge = (
        '<span style="font-size:10px;color:#22C55E;background:#22C55E22;'
        'padding:2px 6px;border-radius:4px;margin-left:6px">🔄 loop</span>'
        if src == "loop" else
        '<span style="font-size:10px;color:#F59E0B;background:#F59E0B22;'
        'padding:2px 6px;border-radius:4px;margin-left:6px">📡 webhook</span>'
    )
    subtitle_html = (
        f'<div style="font-size:11px;color:#8B949E;margin-top:2px">{subt}</div>'
        if subt else ""
    )

    sig_row = signal_by_key.get((symbol, tf, strat))
    sig     = (sig_row.get("signal") or "NONE").upper() if sig_row else None

    if src == "webhook":
        status_label, status_color = "Live", "#22C55E"
    elif sig and sig not in ("NONE", "BLOCKED", "ERROR"):
        status_label, status_color = "Firing", "#22C55E"
    else:
        status_label, status_color = "Awaiting", "#8B949E"

    if group == "LIVE":
        stats_source = "live_signal_loop" if src == "loop" else "tradingview_webhook"
        live_data    = strategy_stats.get(f"{symbol}_{strat}_{stats_source}")
        signals_n    = live_data["total"] if live_data else 0
        sim_html     = ""
    else:
        paper_data = paper_stats.get(f"{symbol}_{tf}_{strat}")
        signals_n  = paper_data["total"] if paper_data else 0
        sim_html   = _paper_stats_html(f"{symbol}_{tf}_{strat}", paper_stats)

    bt_html = ""
    if row.get("bt_win_rate") is not None or row.get("bt_profit") is not None:
        bt_wr   = row.get("bt_win_rate")
        bt_pnl  = row.get("bt_profit")
        wr_str  = f"{bt_wr * 100:.1f}%" if bt_wr is not None else "—"
        pnl_str = f"${bt_pnl:,.2f}" if bt_pnl is not None else "—"
        bt_html = (
            f'<div class="info-tile"><div class="lbl">Backtest</div>'
            f'<div class="val">{wr_str} WR · {pnl_str}</div></div>'
        )

    detail_html = ""
    if sig_row:
        chk  = _fmt_ts(sig_row["checked_at"])
        cndl = sig_row["candle_time"][:16] if sig_row.get("candle_time") else "—"
        nxt  = _next_check(sig_row["checked_at"])
        err_html = (
            f'<div class="info-tile"><div class="lbl">Error</div>'
            f'<div class="val" style="color:#F97316">{sig_row["error"]}</div></div>'
            if sig_row.get("error") else ""
        )
        detail_html = (
            f'<div class="info-tile"><div class="lbl">Candle</div><div class="val">{cndl}</div></div>'
            f'<div class="info-tile"><div class="lbl">Checked</div><div class="val">{chk}</div></div>'
            f'<div class="info-tile"><div class="lbl">Next check</div><div class="val">{nxt}</div></div>'
            f'{err_html}'
        )

    return f"""
    <div style="background:#161B22;border:1px solid #30363D;border-left:3px solid {border};
                border-radius:10px;padding:16px 20px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
        <div>
          <div style="font-size:13px;font-weight:600;color:#E6EDF3">{symbol} · {tf} · {strat}{src_badge}</div>{subtitle_html}
        </div>
        <div style="font-size:12px;font-weight:700;color:{status_color};background:{status_color}22;
                    padding:2px 10px;border-radius:4px">{status_label}</div>
      </div>
      <div style="height:8px"></div>
      <div class="info-tile"><div class="lbl">Signals</div><div class="val">{signals_n}</div></div>
      {sim_html}
      {bt_html}
      {detail_html}
    </div>
    """


# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""
<h1 style="margin-bottom:4px">Overview</h1>
<p style="color:#8B949E;font-size:13px;margin-top:0">Live account performance summary</p>
""", unsafe_allow_html=True)


# ── Section 1 — Alert Banners ─────────────────────────────────────────────────

if signal_rows:
    sig_age_h = _age_hours(signal_rows[0]["checked_at"])
    if sig_age_h is not None and sig_age_h > 2:
        total_m = int(sig_age_h * 60)
        hh, mm  = total_m // 60, total_m % 60
        st.markdown(f"""
        <div style="background:#7F1D1D;border:1px solid #EF4444;border-radius:8px;
                    padding:12px 20px;margin-bottom:10px;font-size:13px;color:#FCA5A5">
          ⚠️ Signal loop may be down — last check was {hh}h {mm}m ago
        </div>
        """, unsafe_allow_html=True)

if cron_info and cron_info["ts"]:
    cron_age_h = _age_hours(cron_info["ts"] + ":00")
    if cron_age_h is not None and cron_age_h > 26:
        st.markdown(f"""
        <div style="background:#78350F;border:1px solid #F59E0B;border-radius:8px;
                    padding:12px 20px;margin-bottom:10px;font-size:13px;color:#FDE68A">
          ⚠️ Morning cron may have missed — last run was {int(cron_age_h)} hours ago
        </div>
        """, unsafe_allow_html=True)


# ── Section 2 — Strategy Pipeline ─────────────────────────────────────────────

_GROUP_ORDER = ["LIVE", "PAPER_HOUR", "PAPER_15MIN"]

_pipeline_by_group = {"LIVE": [], "PAPER_HOUR": [], "PAPER_15MIN": []}
for _row in pipeline_rows:
    _grp = _strategy_group(_row)
    if _grp:
        _pipeline_by_group[_grp].append(_row)

for _grp in _pipeline_by_group:
    _pipeline_by_group[_grp].sort(key=lambda r: (r["symbol"], r["strategy_name"]))

for _group_key in _GROUP_ORDER:
    _rows = _pipeline_by_group[_group_key]
    if not _rows:
        continue

    _title, _color = GROUP_TITLES[_group_key]
    st.markdown(
        f'<div class="section-hd"><span style="color:{_color}">── {_title} ──</span></div>',
        unsafe_allow_html=True,
    )

    if _group_key != "LIVE":
        _n_strats = len(_rows)
        _signals_today = sum(
            today_paper_by_key.get((r["symbol"], r["timeframe"], r["strategy_name"]), 0)
            for r in _rows
        )
        _best_label = "—"
        _best_wr    = None
        for r in _rows:
            _pdata = paper_stats.get(f"{r['symbol']}_{r['timeframe']}_{r['strategy_name']}")
            if _pdata and _pdata["total"] > 0:
                _wr = _pdata["wins"] / _pdata["total"] * 100
                if _best_wr is None or _wr > _best_wr:
                    _best_wr    = _wr
                    _best_label = r["strategy_name"]
        _best_str = f"{_best_label} {_best_wr:.0f}% WR" if _best_wr is not None else "—"
        st.markdown(
            f'<div style="font-size:11px;color:#8B949E;margin-bottom:8px">'
            f'{_n_strats} strateg{"y" if _n_strats == 1 else "ies"} · '
            f'{_signals_today} signal{"s" if _signals_today != 1 else ""} today · '
            f'best: {_best_str}</div>',
            unsafe_allow_html=True,
        )

    for _i in range(0, len(_rows), 2):
        _pair = _rows[_i:_i + 2]
        _cols = st.columns(2)
        for _col, _row in zip(_cols, _pair):
            with _col:
                st.markdown(_render_strategy_card(_row), unsafe_allow_html=True)

    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)


_live_trade_total  = sum(v["total"] for v in strategy_stats.values()
                         if v.get("source") in ("live_signal_loop", "signal_loop"))
_paper_trade_total = sum(v.get("total", 0) for v in paper_stats.values())
st.markdown(
    f'<div style="font-size:11px;color:#8B949E;text-align:right;margin-top:4px">'
    f'Tracking {_live_trade_total} live trade{"s" if _live_trade_total != 1 else ""}'
    f' &nbsp;·&nbsp; {_paper_trade_total} paper signal{"s" if _paper_trade_total != 1 else ""}'
    f'</div>',
    unsafe_allow_html=True,
)


# ── Section 3 — Cron Status Bar ───────────────────────────────────────────────

st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)

if cron_info and cron_info["ts"]:
    err_val   = cron_info["errors"]
    err_color = "#EF4444" if isinstance(err_val, int) and err_val > 0 else "#8B949E"
    st.markdown(f"""
    <div style="background:#161B22;border:1px solid #30363D;border-radius:8px;
                padding:10px 20px;font-size:12px;color:#8B949E">
      Last daily run: <span style="color:#E6EDF3">{cron_info['ts']} UTC</span> —
      {cron_info['backtests']} backtests ·
      {cron_info['strategies']} strategies updated ·
      <span style="color:{err_color}">{err_val} errors</span>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div style="background:#161B22;border:1px solid #30363D;border-radius:8px;
                padding:10px 20px;font-size:12px;color:#8B949E">
      No daily run recorded yet
    </div>
    """, unsafe_allow_html=True)

loss_color = "#EF4444" if today_bot_losses >= 60 else "#8B949E"
st.markdown(f"""
<div style="background:#161B22;border:1px solid #30363D;border-radius:8px;
            padding:10px 20px;font-size:12px;color:#8B949E;margin-top:6px">
  Today (bot): <span style="color:#E6EDF3">{today_bot_trades} trades</span> ·
  <span style="color:{loss_color}">${today_bot_losses:.2f} losses</span> ·
  limit $75
</div>
""", unsafe_allow_html=True)


# ── Section 4 — Today's P&L ───────────────────────────────────────────────────

st.markdown("<div class=\"section-hd\">Today's P&L</div>", unsafe_allow_html=True)

if today_pnl is not None and today_count > 0:
    sign      = "+" if today_pnl >= 0 else ""
    pnl_class = "pos" if today_pnl >= 0 else "neg"
    card_cls  = "green" if today_pnl >= 0 else "red"
    st.markdown(f"""
    <div class="kpi-card {card_cls}" style="width:100%">
      <div class="kpi-label">Today's P&amp;L (UTC)</div>
      <div class="kpi-value {pnl_class}">{sign}${today_pnl:,.2f}</div>
      <div class="kpi-sub">{today_count} closed trade{'s' if today_count != 1 else ''} today</div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div style="background:#161B22;border:1px solid #30363D;border-radius:10px;
                padding:24px;text-align:center;color:#8B949E;font-size:13px">
      No closed trades today (UTC)
    </div>
    """, unsafe_allow_html=True)


# ── Section 5 — Equity Curve ──────────────────────────────────────────────────

st.markdown('<div class="section-hd">Equity Curve</div>', unsafe_allow_html=True)

if pnl_rows:
    df_pnl = pd.DataFrame(pnl_rows)
    df_pnl["cumulative_pnl"] = df_pnl["pnl"].cumsum()

    line_color = "#22C55E" if df_pnl["cumulative_pnl"].iloc[-1] >= 0 else "#EF4444"
    fill_color = "rgba(34,197,94,0.08)" if line_color == "#22C55E" else "rgba(239,68,68,0.08)"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_pnl["timestamp"],
        y=df_pnl["cumulative_pnl"],
        mode="lines",
        name="Equity",
        line=dict(color=line_color, width=2),
        fill="tozeroy",
        fillcolor=fill_color,
        hovertemplate="<b>%{x}</b><br>P&L: $%{y:,.2f}<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor="#161B22",
        plot_bgcolor="#161B22",
        font=dict(family="Inter, sans-serif", color="#8B949E", size=11),
        xaxis=dict(
            showgrid=True, gridcolor="#21262D", gridwidth=1,
            zeroline=False, tickfont=dict(color="#8B949E"),
            title=None,
        ),
        yaxis=dict(
            showgrid=True, gridcolor="#21262D", gridwidth=1,
            zeroline=True, zerolinecolor="#30363D",
            tickprefix="$", tickfont=dict(color="#8B949E"),
            title=None,
        ),
        margin=dict(l=0, r=0, t=8, b=0),
        height=280,
        hovermode="x unified",
        legend=dict(
            font=dict(color="#8B949E"), bgcolor="rgba(0,0,0,0)",
            bordercolor="#30363D",
        ),
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.markdown("""
    <div style="background:#161B22;border:1px solid #30363D;border-radius:10px;
                padding:32px;text-align:center;color:#8B949E;font-size:13px">
      No closed trades with P&amp;L data yet — the curve will appear once trades are closed.
    </div>
    """, unsafe_allow_html=True)
