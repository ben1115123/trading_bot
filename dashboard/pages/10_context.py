import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from database.db import get_connection

st.set_page_config(page_title="Context Analysis · Trading Bot", layout="wide")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from styles import inject_css
inject_css()

DEPLOY_DATE    = "2026-05-30"
DAY_NAMES      = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"}
SESSION_ORDER  = ["LONDON_OPEN", "LONDON_MID", "NY_OPEN", "NY_MID", "NY_CLOSE", "OFF_HOURS"]
NORMAL_SPREADS = {"US500": 0.6, "EURUSD": 0.0008, "DAX": 1.0, "US100": 0.6}

st.markdown("""
<h1 style="margin-bottom:4px">Trade Context Analysis</h1>
<p style="color:#8B949E;font-size:13px;margin-top:0">Session, day, volatility and trend regime breakdown</p>
""", unsafe_allow_html=True)

st.info(
    f"Context data captured from {DEPLOY_DATE} onwards. "
    "Historical trades show NULL for context fields.",
    icon="ℹ️",
)


# ── Filters ───────────────────────────────────────────────────────────────────

fc1, fc2, fc3 = st.columns(3)
with fc1:
    sym_sel = st.selectbox("Symbol", ["All", "US500", "US100", "EURUSD", "DAX"])
with fc2:
    src_sel = st.selectbox("Source", ["All", "live_signal_loop", "tradingview_webhook"])
with fc3:
    days_sel = st.selectbox("Period", [30, 60, 90], format_func=lambda x: f"Last {x} days")

sym    = None if sym_sel == "All" else sym_sel
src    = None if src_sel == "All" else src_sel
days   = days_sel
cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

conds: list  = ["pnl IS NOT NULL", "status = 'CLOSED'", "timestamp >= ?"]
params: list = [cutoff]
if sym:
    conds.append("symbol = ?")
    params.append(sym)
if src:
    if src == "live_signal_loop":
        conds.append("source IN ('signal_loop', 'live_signal_loop')")
    else:
        conds.append("source = ?")
        params.append(src)
where = " AND ".join(conds)


# ── Data fetch ────────────────────────────────────────────────────────────────

try:
    conn = get_connection()
    cur  = conn.cursor()

    cur.execute(f"""
        SELECT session,
               COUNT(*) as trades,
               SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
               SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
               ROUND(100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
               ROUND(SUM(pnl), 2) as total_pnl,
               ROUND(AVG(pnl), 2) as avg_pnl
        FROM trades WHERE {where} AND session IS NOT NULL
        GROUP BY session
    """, params)
    session_rows = [dict(r) for r in cur.fetchall()]

    cur.execute(f"""
        SELECT day_of_week,
               COUNT(*) as trades,
               SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
               SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
               ROUND(100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
               ROUND(SUM(pnl), 2) as total_pnl,
               ROUND(AVG(pnl), 2) as avg_pnl
        FROM trades WHERE {where} AND day_of_week IS NOT NULL
        GROUP BY day_of_week ORDER BY day_of_week
    """, params)
    dow_rows = [dict(r) for r in cur.fetchall()]

    cur.execute(f"""
        SELECT price_vs_ema200, direction,
               COUNT(*) as trades,
               SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
               ROUND(100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
               ROUND(SUM(pnl), 2) as total_pnl
        FROM trades WHERE {where} AND price_vs_ema200 IS NOT NULL
        GROUP BY price_vs_ema200, direction ORDER BY price_vs_ema200, direction
    """, params)
    ema200_rows = [dict(r) for r in cur.fetchall()]

    cur.execute(f"""
        SELECT
            CASE
                WHEN vix_level < 15 THEN 'Low (<15)'
                WHEN vix_level < 20 THEN 'Normal (15-20)'
                WHEN vix_level < 25 THEN 'Elevated (20-25)'
                ELSE 'High (>25)'
            END as vix_bucket,
            COUNT(*) as trades,
            SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
            ROUND(100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
            ROUND(SUM(pnl), 2) as total_pnl,
            ROUND(MIN(vix_level), 1) as vix_min
        FROM trades WHERE {where} AND vix_level IS NOT NULL
        GROUP BY vix_bucket ORDER BY vix_min
    """, params)
    vix_rows = [dict(r) for r in cur.fetchall()]

    cur.execute(f"""
        SELECT symbol, ROUND(AVG(spread), 5) as avg_spread, COUNT(*) as n
        FROM trades WHERE {where} AND spread IS NOT NULL
        GROUP BY symbol ORDER BY symbol
    """, params)
    spread_avg_rows = [dict(r) for r in cur.fetchall()]

    cur.execute(f"""
        SELECT symbol, spread, pnl
        FROM trades WHERE {where} AND spread IS NOT NULL
    """, params)
    spread_trade_rows = [dict(r) for r in cur.fetchall()]

    cur.execute(f"""
        SELECT atr_at_entry, pnl
        FROM trades WHERE {where} AND atr_at_entry IS NOT NULL
        ORDER BY atr_at_entry
    """, params)
    atr_raw = [dict(r) for r in cur.fetchall()]

    cur.execute(f"""
        SELECT timestamp, symbol, direction, source, strategy_name, pnl,
               spread, vix_level, ema200_daily, price_vs_ema200,
               atr_at_entry, day_of_week, session
        FROM trades WHERE {where}
        ORDER BY id DESC LIMIT 500
    """, params)
    raw_rows = [dict(r) for r in cur.fetchall()]

    conn.close()
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

_live_vix = None
try:
    from filters.vix_filter import get_current_vix
    _live_vix = get_current_vix()
except Exception:
    pass


def _wr_color(wr) -> str:
    if wr is None: return "#8B949E"
    if wr >= 55:   return "#238636"
    if wr >= 45:   return "#9e6a03"
    return "#da3633"


def _no_data_msg(msg="No context data yet."):
    st.markdown(
        f'<div style="color:#8B949E;font-size:13px;padding:12px 0">{msg}</div>',
        unsafe_allow_html=True,
    )


# ── Section 2 — Session Performance ──────────────────────────────────────────

st.markdown('<div class="section-hd">Session Performance</div>', unsafe_allow_html=True)

if not session_rows:
    _no_data_msg(f"No session data yet — context captured from {DEPLOY_DATE} onwards.")
else:
    sess_order = {s: i for i, s in enumerate(SESSION_ORDER)}
    session_rows = sorted(session_rows, key=lambda r: sess_order.get(r["session"], 99))

    sc1, sc2 = st.columns([1, 1])
    with sc1:
        df_sess = pd.DataFrame(session_rows).rename(columns={
            "session": "Session", "trades": "Trades", "wins": "Wins",
            "losses": "Losses", "win_rate": "WR%", "total_pnl": "P&L", "avg_pnl": "Avg P&L",
        })
        best_wr  = df_sess["WR%"].max()
        worst_wr = df_sess["WR%"].min()
        st.dataframe(
            df_sess.style
                .background_gradient(subset=["WR%"], cmap="RdYlGn", vmin=30, vmax=70)
                .format({"WR%": "{:.1f}%", "P&L": "${:+.2f}", "Avg P&L": "${:+.2f}"}),
            use_container_width=True, hide_index=True,
        )
        best_row  = df_sess[df_sess["WR%"] == best_wr].iloc[0]
        worst_row = df_sess[df_sess["WR%"] == worst_wr].iloc[0]
        st.caption(
            f"Best: **{best_row['Session']}** {best_wr:.1f}%  ·  "
            f"Worst: **{worst_row['Session']}** {worst_wr:.1f}%"
        )
    with sc2:
        fig = go.Figure(go.Bar(
            y=[r["session"] for r in session_rows],
            x=[r["win_rate"] for r in session_rows],
            orientation="h",
            marker_color=[_wr_color(r["win_rate"]) for r in session_rows],
            text=[f"{r['win_rate']}%" for r in session_rows],
            textposition="outside",
        ))
        fig.update_layout(
            template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)", height=300,
            margin=dict(l=0, r=50, t=10, b=10), xaxis_title="Win Rate %",
        )
        st.plotly_chart(fig, use_container_width=True)


# ── Section 3 — Day of Week Performance ──────────────────────────────────────

st.markdown('<div class="section-hd">Day of Week Performance</div>', unsafe_allow_html=True)
st.caption("Monday block active from 2026-05-30 — Monday trades will be sparse going forward.")

if not dow_rows:
    _no_data_msg("No day-of-week data yet.")
else:
    dc1, dc2 = st.columns([1, 1])
    with dc1:
        df_dow = pd.DataFrame(dow_rows)
        df_dow["Day"] = df_dow["day_of_week"].map(DAY_NAMES).fillna(df_dow["day_of_week"].astype(str))
        df_dow = df_dow.rename(columns={
            "trades": "Trades", "wins": "Wins", "losses": "Losses",
            "win_rate": "WR%", "total_pnl": "P&L", "avg_pnl": "Avg P&L",
        })[["Day", "Trades", "Wins", "Losses", "WR%", "P&L", "Avg P&L"]]
        st.dataframe(
            df_dow.style
                .background_gradient(subset=["WR%"], cmap="RdYlGn", vmin=30, vmax=70)
                .format({"WR%": "{:.1f}%", "P&L": "${:+.2f}", "Avg P&L": "${:+.2f}"}),
            use_container_width=True, hide_index=True,
        )
    with dc2:
        fig = go.Figure(go.Bar(
            x=[DAY_NAMES.get(r["day_of_week"], str(r["day_of_week"])) for r in dow_rows],
            y=[r["win_rate"] for r in dow_rows],
            marker_color=[_wr_color(r["win_rate"]) for r in dow_rows],
            text=[f"{r['win_rate']}%" for r in dow_rows],
            textposition="outside",
        ))
        fig.update_layout(
            template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)", height=300,
            margin=dict(l=0, r=10, t=10, b=10), yaxis_title="Win Rate %",
        )
        st.plotly_chart(fig, use_container_width=True)


# ── Section 4 — Market Regime ─────────────────────────────────────────────────

st.markdown('<div class="section-hd">Market Regime</div>', unsafe_allow_html=True)

mc1, mc2 = st.columns(2)

with mc1:
    st.markdown("**Trend Context (Price vs EMA200 Daily)**")
    if not ema200_rows:
        _no_data_msg("No EMA200 data yet.")
    else:
        df_ema = pd.DataFrame(ema200_rows)
        df_ema["Context"] = df_ema["price_vs_ema200"] + " / " + df_ema["direction"]
        df_ema = df_ema.rename(columns={
            "trades": "Trades", "wins": "Wins", "win_rate": "WR%", "total_pnl": "P&L",
        })[["Context", "Trades", "Wins", "WR%", "P&L"]]
        st.dataframe(
            df_ema.style
                .background_gradient(subset=["WR%"], cmap="RdYlGn", vmin=30, vmax=70)
                .format({"WR%": "{:.1f}%", "P&L": "${:+.2f}"}),
            use_container_width=True, hide_index=True,
        )
        st.caption("ABOVE/BUY = trend-following long · BELOW/SELL = trend-following short")

with mc2:
    st.markdown("**Volatility Context (VIX Buckets)**")
    if _live_vix:
        st.caption(f"Current VIX: **{_live_vix:.2f}**")
    if not vix_rows:
        _no_data_msg("No VIX data yet.")
    else:
        df_vix = pd.DataFrame(vix_rows).drop(columns=["vix_min"], errors="ignore")
        df_vix = df_vix.rename(columns={
            "vix_bucket": "VIX Regime", "trades": "Trades", "wins": "Wins",
            "win_rate": "WR%", "total_pnl": "P&L",
        })
        st.dataframe(
            df_vix.style
                .background_gradient(subset=["WR%"], cmap="RdYlGn", vmin=30, vmax=70)
                .format({"WR%": "{:.1f}%", "P&L": "${:+.2f}"}),
            use_container_width=True, hide_index=True,
        )


# ── Section 5 — Spread Analysis ───────────────────────────────────────────────

st.markdown('<div class="section-hd">Spread Analysis</div>', unsafe_allow_html=True)
st.caption(f"Spread data available from {DEPLOY_DATE} onwards (webhook trades only).")

if not spread_avg_rows:
    _no_data_msg("No spread data yet.")
else:
    sp1, sp2 = st.columns(2)
    with sp1:
        st.markdown("**Average spread by symbol**")
        df_sp = pd.DataFrame(spread_avg_rows).rename(columns={
            "symbol": "Symbol", "avg_spread": "Avg Spread", "n": "Trades",
        })
        st.dataframe(df_sp, use_container_width=True, hide_index=True)

    with sp2:
        st.markdown("**Win rate by spread width**")
        bins: dict = {"Normal (≤1×)": [], "Slightly Wide (1–1.5×)": [], "Wide (1.5–2×)": []}
        for r in spread_trade_rows:
            normal = NORMAL_SPREADS.get(r.get("symbol", ""), 0)
            if not normal or r.get("spread") is None or r.get("pnl") is None:
                continue
            ratio = r["spread"] / normal
            pnl   = r["pnl"]
            if ratio <= 1.0:
                bins["Normal (≤1×)"].append(pnl)
            elif ratio <= 1.5:
                bins["Slightly Wide (1–1.5×)"].append(pnl)
            else:
                bins["Wide (1.5–2×)"].append(pnl)

        bin_rows = []
        for label, pnls in bins.items():
            if pnls:
                w = sum(1 for p in pnls if p > 0)
                bin_rows.append({
                    "Spread": label, "Trades": len(pnls),
                    "WR%": round(w / len(pnls) * 100, 1),
                    "P&L": round(sum(pnls), 2),
                })
        if bin_rows:
            df_bins = pd.DataFrame(bin_rows)
            st.dataframe(
                df_bins.style
                    .background_gradient(subset=["WR%"], cmap="RdYlGn", vmin=30, vmax=70)
                    .format({"WR%": "{:.1f}%", "P&L": "${:+.2f}"}),
                use_container_width=True, hide_index=True,
            )
        else:
            _no_data_msg("Insufficient spread data for binning.")


# ── Section 6 — ATR Regime ────────────────────────────────────────────────────

st.markdown('<div class="section-hd">ATR Regime</div>', unsafe_allow_html=True)
st.caption("Splits trades into low/medium/high ATR terciles. High ATR = more volatile candle at entry.")

if len(atr_raw) < 6:
    _no_data_msg("Insufficient ATR data (need ≥ 6 trades with context).")
else:
    n  = len(atr_raw)
    t1 = atr_raw[n // 3]["atr_at_entry"]
    t2 = atr_raw[2 * n // 3]["atr_at_entry"]

    atr_buckets: dict = {"Low ATR": [], "Medium ATR": [], "High ATR": []}
    for r in atr_raw:
        pnl = r.get("pnl")
        if pnl is None:
            continue
        atr = r["atr_at_entry"]
        if atr <= t1:
            atr_buckets["Low ATR"].append(pnl)
        elif atr <= t2:
            atr_buckets["Medium ATR"].append(pnl)
        else:
            atr_buckets["High ATR"].append(pnl)

    atr_df_rows = []
    for label, pnls in atr_buckets.items():
        if pnls:
            w = sum(1 for p in pnls if p > 0)
            atr_df_rows.append({
                "ATR Regime": label, "Trades": len(pnls),
                "WR%":       round(w / len(pnls) * 100, 1),
                "Total P&L": round(sum(pnls), 2),
                "Avg P&L":   round(sum(pnls) / len(pnls), 2),
            })

    if atr_df_rows:
        at1, at2 = st.columns([1, 1])
        with at1:
            df_atr = pd.DataFrame(atr_df_rows)
            st.dataframe(
                df_atr.style
                    .background_gradient(subset=["WR%"], cmap="RdYlGn", vmin=30, vmax=70)
                    .format({"WR%": "{:.1f}%", "Total P&L": "${:+.2f}", "Avg P&L": "${:+.2f}"}),
                use_container_width=True, hide_index=True,
            )
            st.caption(
                f"Tercile boundaries: Low ≤ {t1:.2f} · Medium ≤ {t2:.2f} · High > {t2:.2f}"
            )
        with at2:
            fig = go.Figure(go.Bar(
                x=[r["ATR Regime"] for r in atr_df_rows],
                y=[r["WR%"] for r in atr_df_rows],
                marker_color=[_wr_color(r["WR%"]) for r in atr_df_rows],
                text=[f"{r['WR%']}%" for r in atr_df_rows],
                textposition="outside",
            ))
            fig.update_layout(
                template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)", height=280,
                margin=dict(l=0, r=10, t=10, b=10), yaxis_title="Win Rate %",
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        _no_data_msg("No resolved ATR data yet.")


# ── Section 7 — Raw Context Data ─────────────────────────────────────────────

with st.expander("View raw context data"):
    if not raw_rows:
        st.caption("No data.")
    else:
        df_raw = pd.DataFrame(raw_rows)
        if "timestamp" in df_raw.columns:
            df_raw["timestamp"] = df_raw["timestamp"].apply(
                lambda t: (
                    datetime.fromisoformat(str(t).replace("Z", "+00:00"))
                    .strftime("%Y-%m-%d %H:%M")
                ) if t else "—"
            )
        if "day_of_week" in df_raw.columns:
            df_raw["day_of_week"] = df_raw["day_of_week"].map(DAY_NAMES).fillna(df_raw["day_of_week"])
        st.dataframe(df_raw, use_container_width=True, hide_index=True)
