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

        cur.execute("""
            SELECT strategy_name, symbol, timeframe, strategy_type, score, activated_at
            FROM active_strategy WHERE status = 'active' ORDER BY symbol ASC
        """)
        strategy_rows = [dict(r) for r in cur.fetchall()]

        try:
            cur.execute("SELECT * FROM signal_log ORDER BY id DESC LIMIT 20")
            signal_rows = [dict(r) for r in cur.fetchall()]
        except Exception:
            signal_rows = []

        try:
            cur.execute("""
                SELECT * FROM signal_log
                WHERE symbol='US100' AND timeframe='5MIN'
                ORDER BY id DESC LIMIT 1
            """)
            _r = cur.fetchone()
            us100_5min = dict(_r) if _r else None
        except Exception:
            us100_5min = None

        last_trade_by_symbol = {}
        for sym in ["US500", "US100", "BTC"]:
            cur.execute("""
                SELECT direction, entry_price, pnl, status
                FROM trades WHERE symbol = ? ORDER BY id DESC LIMIT 1
            """, (sym,))
            row = cur.fetchone()
            last_trade_by_symbol[sym] = dict(row) if row else None

        today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cur.execute("""
            SELECT SUM(pnl) as s, COUNT(*) as n FROM trades
            WHERE pnl IS NOT NULL AND status = 'closed'
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

    finally:
        conn.close()

    return strategy_rows, signal_rows, last_trade_by_symbol, today_pnl, today_count, pnl_rows, us100_5min


strategy_rows, signal_rows, last_trade_by_symbol, today_pnl, today_count, pnl_rows, us100_5min = fetch_data()


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


_SIG_COLOR = {"BUY": "#22C55E", "SELL": "#EF4444", "NONE": "#8B949E", "ERROR": "#F97316"}
LOG_PATH   = "/app/logs/daily_run.log"

strategy_by_symbol = {r["symbol"]: r for r in strategy_rows}
signal_by_symbol   = {}
for _row in signal_rows:
    _sym = _row["symbol"]
    if _sym not in signal_by_symbol:
        signal_by_symbol[_sym] = _row

cron_info = _parse_daily_log(LOG_PATH)


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


# ── Section 2 — Signal Monitor ────────────────────────────────────────────────

st.markdown('<div class="section-hd">Signal Monitor</div>', unsafe_allow_html=True)

_CARDS = [
    ("US500", "US500",        signal_by_symbol.get("US500"), None),
    ("US100", "US100",        signal_by_symbol.get("US100"), None),
    ("US100", "US100 · 5MIN", us100_5min,                   "US session only 14:30–21:00 UTC"),
    ("BTC",   "BTC",          signal_by_symbol.get("BTC"),  None),
]
sig_cols = st.columns(4)
for col, (symbol, label, r, subtitle) in zip(sig_cols, _CARDS):
    with col:
        strat_row  = strategy_by_symbol.get(symbol)
        last_trade = last_trade_by_symbol.get(symbol)

        if last_trade:
            ep        = last_trade.get("entry_price")
            pnl_val   = last_trade.get("pnl")
            direction = (last_trade.get("direction") or "?").upper()
            status    = last_trade.get("status", "")
            ep_str    = f"${ep:,.2f}" if ep else "?"
            if status == "closed" and pnl_val is not None:
                sign      = "+" if pnl_val >= 0 else ""
                clr       = "#22C55E" if pnl_val >= 0 else "#EF4444"
                mark      = "✓" if pnl_val >= 0 else "✗"
                trade_html = (
                    f'<div class="info-tile"><div class="lbl">Last trade</div>'
                    f'<div class="val">{direction} @ {ep_str} → '
                    f'<span style="color:{clr}">{sign}${pnl_val:,.2f} {mark}</span></div></div>'
                )
            else:
                trade_html = (
                    f'<div class="info-tile"><div class="lbl">Last trade</div>'
                    f'<div class="val">{direction} @ {ep_str} → '
                    f'<span style="color:#F59E0B">OPEN</span></div></div>'
                )
        else:
            trade_html = (
                '<div class="info-tile"><div class="lbl">Last trade</div>'
                '<div class="val" style="color:#8B949E">No trades yet</div></div>'
            )

        subtitle_html = (
            f'<div style="font-size:11px;color:#8B949E;margin-top:2px">{subtitle}</div>'
            if subtitle else ""
        )

        if r:
            sig        = (r.get("signal") or "NONE").upper()
            color      = _SIG_COLOR.get(sig, "#8B949E")
            strat_name = r.get("strategy_name") or (strat_row["strategy_name"] if strat_row else "—")
            tf         = r.get("timeframe") or (strat_row["timeframe"] if strat_row else "—")
            chk        = _fmt_ts(r["checked_at"])
            cndl       = r["candle_time"][:16] if r.get("candle_time") else "—"
            nxt        = _next_check(r["checked_at"])
            err_html   = (
                f'<div class="info-tile"><div class="lbl">Error</div>'
                f'<div class="val" style="color:#F97316">{r["error"]}</div></div>'
                if r.get("error") else ""
            )
            st.markdown(f"""
            <div style="background:#161B22;border:1px solid #30363D;border-radius:10px;padding:16px 20px">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
                <div>
                  <div style="font-size:13px;font-weight:600;color:#58A6FF">{label}</div>{subtitle_html}
                </div>
                <div style="font-size:12px;font-weight:700;color:{color};background:{color}22;
                            padding:2px 10px;border-radius:4px">{sig}</div>
              </div>
              <div style="height:8px"></div>
              <div class="info-tile"><div class="lbl">Strategy</div><div class="val">{strat_name} · {tf}</div></div>
              <div class="info-tile"><div class="lbl">Candle</div><div class="val">{cndl}</div></div>
              <div class="info-tile"><div class="lbl">Checked</div><div class="val">{chk}</div></div>
              <div class="info-tile"><div class="lbl">Next check</div><div class="val">{nxt}</div></div>
              {trade_html}
              {err_html}
            </div>
            """, unsafe_allow_html=True)
        else:
            strat_name = strat_row["strategy_name"] if strat_row else "—"
            tf         = strat_row["timeframe"] if strat_row else "—"
            st.markdown(f"""
            <div style="background:#161B22;border:1px solid #30363D;border-radius:10px;padding:16px 20px;font-size:13px">
              <div style="margin-bottom:4px">
                <div style="font-weight:600;color:#58A6FF">{label}</div>{subtitle_html}
              </div>
              <div style="height:8px"></div>
              <div class="info-tile"><div class="lbl">Strategy</div><div class="val">{strat_name} · {tf}</div></div>
              <div class="info-tile"><div class="lbl">Signal</div>
                <div class="val" style="color:#8B949E">No data yet</div></div>
              {trade_html}
            </div>
            """, unsafe_allow_html=True)


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
