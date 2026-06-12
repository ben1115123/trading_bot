import sys
import math
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from database.db import get_connection
from database.models import get_outcome_summary, get_webhook_outcomes

st.set_page_config(page_title="Context Analysis · Trading Bot", layout="wide")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from styles import inject_css
inject_css()

DEPLOY_DATE    = "2026-05-30"
DAY_NAMES      = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"}
SESSION_ORDER  = ["LONDON_OPEN", "LONDON_MID", "NY_OPEN", "NY_MID", "NY_CLOSE", "OFF_HOURS"]
NORMAL_SPREADS = {"US500": 0.6, "EURUSD": 0.0008, "DAX": 1.0, "US100": 0.6}

# Backtest WR baselines for live strategies (win_rate as %, hardcoded — proven live)
BACKTEST_WR_BASELINE = {
    ("US500", "stoch_rsi"): 54.0,
}

st.markdown("""
<h1 style="margin-bottom:4px">Trade Context & Filter Analysis</h1>
<p style="color:#8B949E;font-size:13px;margin-top:0">Are my filters helping? Which sessions work? Is live performance on track?</p>
""", unsafe_allow_html=True)

st.info(
    f"Context data captured from {DEPLOY_DATE} onwards. "
    "Historical trades show NULL for context fields.",
    icon="ℹ️",
)


def _wr_color(wr) -> str:
    if wr is None: return "#8B949E"
    if wr >= 55:   return "#238636"
    if wr >= 45:   return "#9e6a03"
    return "#da3633"


def _wr_bg(val) -> str:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return ""
    if val >= 55:
        return "background-color: #1a4a1a; color: #7ee787"
    if val >= 45:
        return "background-color: #3a2a00; color: #e3b341"
    return "background-color: #4a1a1a; color: #f85149"


def _no_data_msg(msg="No context data yet."):
    st.markdown(
        f'<div style="color:#8B949E;font-size:13px;padding:12px 0">{msg}</div>',
        unsafe_allow_html=True,
    )


def _trade_verdict(trades: int, win_rate) -> str:
    """Traffic-light verdict for a bucket of trades."""
    if trades < 5:
        return f"⚪ Need more data ({trades}/5)"
    if win_rate >= 55:
        return "🟢 TRADE IT"
    if win_rate >= 45:
        return "🟡 NEUTRAL"
    return "🔴 AVOID"


# ── Section 1 — Live vs Backtest Tracking ────────────────────────────────────

st.markdown('<div class="section-hd">Live vs Backtest Tracking</div>', unsafe_allow_html=True)
st.caption("Is live performance holding up against the backtest that justified going live? (last 90 days)")

try:
    conn = get_connection()
    cur  = conn.cursor()
    cutoff_90 = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    cur.execute("""
        SELECT t.symbol, t.strategy_name, t.source,
               COUNT(*) as trades,
               SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) as wins,
               ROUND(100.0 * SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate
        FROM trades t
        INNER JOIN active_strategy a
            ON t.symbol = a.symbol AND t.strategy_name = a.strategy_name
        WHERE a.status IN ('active', 'live')
          AND t.pnl IS NOT NULL AND t.status = 'CLOSED'
          AND t.source IN ('signal_loop', 'live_signal_loop', 'tradingview_webhook')
          AND t.timestamp >= ?
        GROUP BY t.symbol, t.strategy_name, t.source
        ORDER BY t.symbol, t.strategy_name
    """, (cutoff_90,))
    live_rows = [dict(r) for r in cur.fetchall()]

    cur.execute("""
        SELECT strategy_name, symbol, COUNT(*) as total_trades
        FROM trades
        WHERE status = 'CLOSED' AND pnl IS NOT NULL
          AND source IN ('signal_loop', 'live_signal_loop', 'tradingview_webhook')
        GROUP BY strategy_name, symbol
    """)
    total_trades_map = {(r["strategy_name"], r["symbol"]): r["total_trades"] for r in cur.fetchall()}
    conn.close()
except Exception as e:
    live_rows = []
    total_trades_map = {}
    st.error(f"Database error: {e}")

if not live_rows:
    _no_data_msg("No closed live trades in the last 90 days yet.")
else:
    tracking_rows = []
    for r in live_rows:
        strat, sym, trades, live_wr = r["strategy_name"], r["symbol"], r["trades"], r["win_rate"]
        tf_label = "HOUR" if r["source"] in ("signal_loop", "live_signal_loop") else ""
        bt_wr = BACKTEST_WR_BASELINE.get((sym, strat))
        total_trades = total_trades_map.get((strat, sym), trades)

        if trades < 10:
            status = "⚪ Insufficient data"
            gap_str = "—"
        elif bt_wr is not None:
            gap = bt_wr - live_wr
            gap_str = f"{gap:+.0f}%"
            if abs(gap) <= 10:
                status = "🟢 On track"
            elif abs(gap) <= 20:
                status = "🟡 Watch closely"
            else:
                status = "🔴 Degrading — review strategy"
        else:
            gap_str = "—"
            if live_wr >= 50:
                status = "🟢 On track"
            elif live_wr >= 40:
                status = "🟡 Watch closely"
            else:
                status = "🔴 Degrading — review strategy"

        tracking_rows.append({
            "Strategy":               f"{strat} {sym}" + (f" {tf_label}" if tf_label else ""),
            "Backtest WR":            f"{bt_wr:.0f}%" if bt_wr is not None else "—",
            "Live WR":                f"{live_wr:.1f}%",
            "Trades (context/total)": f"{trades} / {total_trades}",
            "Gap":                    gap_str,
            "Status":                 status,
        })

    st.dataframe(pd.DataFrame(tracking_rows), use_container_width=True, hide_index=True)
    st.caption(
        "🔴 status triggers review — consider demoting to paper if gap persists over 20+ trades"
    )
    st.caption(
        "⚠️ Live WR shown only reflects trades with context data (from 2026-05-30). "
        "Full trade history may show different WR. Click through to Trade Log for complete picture."
    )


# ── Section 1B — Filter Effectiveness ────────────────────────────────────────

st.markdown('<div class="section-hd">FILTER EFFECTIVENESS — Would blocked alerts have won?</div>', unsafe_allow_html=True)
st.caption("Resolves blocked webhook alerts against actual price action — did SL or TP hit first?")

try:
    conn = get_connection()
    outcome_summary = get_outcome_summary(conn, days=30)
    outcome_rows    = get_webhook_outcomes(conn, days=30)
    conn.close()
except Exception as e:
    outcome_summary = []
    outcome_rows    = []
    st.error(f"Database error: {e}")

total_resolved = sum(
    (r["would_win"] or 0) + (r["would_lose"] or 0) + (r["unknown"] or 0)
    for r in outcome_summary
)

if not outcome_summary or total_resolved == 0:
    _no_data_msg("Resolver running — outcomes populate daily at 06:00 UTC.")
else:
    st.markdown("**Summary by filter**")

    summary_rows = []
    total_blocked = total_win = total_lose = 0
    total_pnl_missed = total_losses_saved = 0.0

    for r in outcome_summary:
        would_win  = r["would_win"] or 0
        would_lose = r["would_lose"] or 0
        unknown    = r["unknown"] or 0
        pnl_missed    = r["pnl_missed"] or 0.0
        losses_saved  = abs(r["losses_saved"] or 0.0)

        total_blocked      += r["total_blocked"] or 0
        total_win          += would_win
        total_lose         += would_lose
        total_pnl_missed   += pnl_missed
        total_losses_saved += losses_saved

        resolved = would_win + would_lose
        if resolved < 10:
            verdict = "⚪ Need more data"
        elif losses_saved > pnl_missed:
            verdict = "✅ Filter is helping"
        else:
            verdict = "🔴 Filter may be costing you"

        summary_rows.append({
            "Filter":          r["block_reason"],
            "Total Blocked":   r["total_blocked"],
            "Would WIN":       would_win,
            "Would LOSE":      would_lose,
            "P&L Missed (if executed)": f"${pnl_missed:,.2f}",
            "Losses Saved (by blocking)": f"${losses_saved:,.2f}",
            "Verdict":         verdict,
        })

    resolved_total = total_win + total_lose
    if resolved_total < 10:
        net_verdict = "⚪ Need more data"
    elif total_losses_saved > total_pnl_missed:
        net_verdict = "✅ Filter is helping"
    else:
        net_verdict = "🔴 Filter may be costing you"

    summary_rows.append({
        "Filter":          "NET FILTER VALUE",
        "Total Blocked":   total_blocked,
        "Would WIN":       total_win,
        "Would LOSE":      total_lose,
        "P&L Missed (if executed)": f"${total_pnl_missed:,.2f}",
        "Losses Saved (by blocking)": f"${total_losses_saved:,.2f}",
        "Verdict":         net_verdict,
    })

    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

    st.markdown("**Recent blocked alerts**")

    if not outcome_rows:
        _no_data_msg("No resolved blocked alerts yet.")
    else:
        detail_rows = []
        for r in outcome_rows[:20]:
            pnl = r["estimated_pnl"]
            detail_rows.append({
                "Date":         r["timestamp"][:16].replace("T", " "),
                "Symbol":       r["symbol"],
                "Direction":    r["direction"],
                "Block Reason": r["block_reason"],
                "Outcome":      r["outcome"],
                "Est P&L":      f"${pnl:,.2f}" if pnl is not None else "—",
            })

        def _outcome_bg(val):
            if val == "WIN":
                return "background-color: #1a4a1a; color: #7ee787"
            if val == "LOSS":
                return "background-color: #4a1a1a; color: #f85149"
            return "background-color: #21262d; color: #8B949E"

        df_detail = pd.DataFrame(detail_rows)
        st.dataframe(
            df_detail.style.applymap(_outcome_bg, subset=["Outcome"]),
            use_container_width=True, hide_index=True,
        )

    st.caption(
        "Verdict: Losses saved > P&L missed → filter helping. "
        "Losses saved < P&L missed → filter may be costing you. "
        "Fewer than 10 resolved outcomes → not enough data yet."
    )


# ── Section 2 — Confluence A/B Test ──────────────────────────────────────────

st.markdown('<div class="section-hd">Confluence A/B Test — stoch_rsi_confluence (US500 HOUR)</div>', unsafe_allow_html=True)
st.caption("Comparing trades that passed the session filter vs. shadow trades that were filtered out.")

try:
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT
            CASE WHEN notes LIKE 'SHADOW%' THEN 'shadow' ELSE 'regular' END as bucket,
            COUNT(*) as trades,
            SUM(CASE WHEN outcome='WIN'  THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) as losses,
            COALESCE(SUM(simulated_pnl), 0) as total_pnl
        FROM paper_trades
        WHERE symbol = 'US500' AND timeframe = 'HOUR' AND strategy_name = 'stoch_rsi_confluence'
        GROUP BY bucket
    """)
    confluence_rows = {r["bucket"]: dict(r) for r in cur.fetchall()}
    conn.close()
except Exception as e:
    confluence_rows = {}
    st.error(f"Database error: {e}")

regular = confluence_rows.get("regular", {"trades": 0, "wins": 0, "losses": 0, "total_pnl": 0.0})
shadow  = confluence_rows.get("shadow",  {"trades": 0, "wins": 0, "losses": 0, "total_pnl": 0.0})

def _resolved_wr(bucket):
    res = (bucket.get("wins") or 0) + (bucket.get("losses") or 0)
    if res == 0:
        return None
    return (bucket["wins"] or 0) / res * 100

reg_wr    = _resolved_wr(regular)
shadow_wr = _resolved_wr(shadow)

if regular["trades"] == 0 and shadow["trades"] == 0:
    _no_data_msg("No stoch_rsi_confluence paper trades yet — this section will populate over time.")
else:
    ab_rows = [
        {
            "": "✅ PASSED filter",
            "Trades": regular["trades"],
            "WR": f"{reg_wr:.1f}%" if reg_wr is not None else "—",
            "P&L": f"${regular['total_pnl']:+.2f}",
        },
        {
            "": "🚫 BLOCKED (shadow)",
            "Trades": shadow["trades"],
            "WR": f"{shadow_wr:.1f}%" if shadow_wr is not None else "—",
            "P&L": f"${shadow['total_pnl']:+.2f}",
        },
    ]
    if reg_wr is not None and shadow_wr is not None:
        edge = reg_wr - shadow_wr
        ab_rows.append({
            "": "Edge from filter",
            "Trades": "",
            "WR": f"{edge:+.1f}%",
            "P&L": f"${regular['total_pnl'] - shadow['total_pnl']:+.2f}",
        })

    st.dataframe(pd.DataFrame(ab_rows), use_container_width=True, hide_index=True)

    if regular["trades"] < 5 or shadow["trades"] < 5:
        st.caption("⚪ Insufficient data — need at least 5 resolved trades in each bucket.")
    elif reg_wr is None or shadow_wr is None:
        st.caption("⚪ Insufficient data — trades not yet resolved.")
    elif reg_wr > shadow_wr + 5:
        st.caption("✅ Session filter IS adding edge — keep it")
    elif reg_wr < shadow_wr:
        st.caption("🔴 Session filter may be HURTING — review")
    else:
        st.caption("⚠️ Session filter not yet proven — need more data")


# ── Filters ───────────────────────────────────────────────────────────────────

st.markdown('<div class="section-hd">Filters</div>', unsafe_allow_html=True)

try:
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) as n FROM trades WHERE session IS NOT NULL AND timestamp >= ?",
        (DEPLOY_DATE,),
    )
    _context_trade_count = cur.fetchone()["n"]
    conn.close()
except Exception:
    _context_trade_count = 0

st.caption(
    f"📊 Current data: {_context_trade_count} total trades with context. "
    "Confident verdicts need 15+ trades per bucket."
)

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


# ── Section 3 — Session Performance ──────────────────────────────────────────

st.markdown('<div class="section-hd">Session Performance</div>', unsafe_allow_html=True)

if not session_rows:
    _no_data_msg(f"No session data yet — context captured from {DEPLOY_DATE} onwards.")
else:
    sess_order = {s: i for i, s in enumerate(SESSION_ORDER)}
    session_rows = sorted(session_rows, key=lambda r: sess_order.get(r["session"], 99))

    df_sess = pd.DataFrame(session_rows).rename(columns={
        "session": "Session", "trades": "Trades", "wins": "Wins",
        "losses": "Losses", "win_rate": "WR%", "total_pnl": "P&L", "avg_pnl": "Avg P&L",
    })
    df_sess["Verdict"] = [
        _trade_verdict(r["trades"], r["win_rate"]) for r in session_rows
    ]
    df_sess = df_sess[["Session", "Trades", "Wins", "Losses", "WR%", "P&L", "Avg P&L", "Verdict"]]
    st.dataframe(
        df_sess.style
            .apply(lambda col: [_wr_bg(v) for v in col], subset=["WR%"])
            .format({"WR%": "{:.1f}%", "P&L": "${:+.2f}", "Avg P&L": "${:+.2f}"}),
        use_container_width=True, hide_index=True,
    )

    best_row  = max(session_rows, key=lambda r: r["win_rate"])
    worst_row = min(session_rows, key=lambda r: r["win_rate"])
    st.caption(
        f"Best session: **{best_row['session']}** ({best_row['win_rate']:.1f}%)  ·  "
        f"Worst: **{worst_row['session']}** ({worst_row['win_rate']:.1f}%)"
    )
    st.caption(
        "Currently filtered: stoch_rsi_confluence US500 HOUR allows only "
        "LONDON_OPEN (07:00-08:59 UTC) + NY_OPEN (13:00-15:59 UTC), all others shadow-logged"
    )
    st.caption(
        "Verdicts shown for sessions with 5+ trades only. "
        "Minimum 15 trades recommended before acting on any verdict."
    )

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
        plot_bgcolor="rgba(0,0,0,0)", height=280,
        margin=dict(l=0, r=50, t=10, b=10), xaxis_title="Win Rate %",
    )
    st.plotly_chart(fig, use_container_width=True)


# ── Section 4 — Day of Week Performance ──────────────────────────────────────

st.markdown('<div class="section-hd">Day of Week Performance</div>', unsafe_allow_html=True)
st.caption(f"Monday block active since {DEPLOY_DATE} — Monday trades will be sparse going forward.")

if not dow_rows:
    _no_data_msg("No day-of-week data yet.")
else:
    df_dow = pd.DataFrame(dow_rows)
    df_dow["Day"] = df_dow["day_of_week"].map(DAY_NAMES).fillna(df_dow["day_of_week"].astype(str))

    verdicts = []
    for r in dow_rows:
        day_name = DAY_NAMES.get(r["day_of_week"], str(r["day_of_week"]))
        if day_name == "Monday":
            verdicts.append("🔴 BLOCKED ✋")
        else:
            verdicts.append(_trade_verdict(r["trades"], r["win_rate"]))
    df_dow["Verdict"] = verdicts

    df_dow = df_dow.rename(columns={
        "trades": "Trades", "wins": "Wins", "losses": "Losses",
        "win_rate": "WR%", "total_pnl": "P&L", "avg_pnl": "Avg P&L",
    })[["Day", "Trades", "Wins", "Losses", "WR%", "P&L", "Avg P&L", "Verdict"]]
    st.dataframe(
        df_dow.style
            .apply(lambda col: [_wr_bg(v) for v in col], subset=["WR%"])
            .format({"WR%": "{:.1f}%", "P&L": "${:+.2f}", "Avg P&L": "${:+.2f}"}),
        use_container_width=True, hide_index=True,
    )

    non_monday = [r for r in dow_rows if DAY_NAMES.get(r["day_of_week"]) != "Monday"]
    if non_monday:
        best_day = max(non_monday, key=lambda r: r["win_rate"])
        st.caption(
            f"Best day: **{DAY_NAMES.get(best_day['day_of_week'])}** "
            f"({best_day['win_rate']:.1f}%)  ·  Currently blocking: Monday"
        )
        tuesday = next((r for r in non_monday if DAY_NAMES.get(r["day_of_week"]) == "Tuesday"), None)
        wednesday = next((r for r in non_monday if DAY_NAMES.get(r["day_of_week"]) == "Wednesday"), None)
        if tuesday and tuesday["win_rate"] >= 55 and (not wednesday or wednesday["win_rate"] < 45):
            need = max(0, 5 - tuesday["trades"])
            if need > 0:
                st.caption(
                    f"Tuesday showing edge — consider blocking Wednesday "
                    f"if pattern holds after {need}+ more trades"
                )
    else:
        st.caption("Currently blocking: Monday")

    st.caption(
        "Verdicts shown for days with 5+ trades only. "
        "Minimum 15 trades recommended before acting on any verdict."
    )

    fig = go.Figure(go.Bar(
        x=[DAY_NAMES.get(r["day_of_week"], str(r["day_of_week"])) for r in dow_rows],
        y=[r["win_rate"] for r in dow_rows],
        marker_color=[_wr_color(r["win_rate"]) for r in dow_rows],
        text=[f"{r['win_rate']}%" for r in dow_rows],
        textposition="outside",
    ))
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", height=280,
        margin=dict(l=0, r=10, t=10, b=10), yaxis_title="Win Rate %",
    )
    st.plotly_chart(fig, use_container_width=True)


# ── Section 5 — Trend Regime ──────────────────────────────────────────────────

st.markdown('<div class="section-hd">Trend Regime</div>', unsafe_allow_html=True)

st.markdown("**Does trading WITH the trend help?**")

if not ema200_rows:
    _no_data_msg("No EMA200 data yet.")
else:
    with_trend    = {"trades": 0, "wins": 0, "total_pnl": 0.0}
    against_trend = {"trades": 0, "wins": 0, "total_pnl": 0.0}
    for r in ema200_rows:
        bucket = with_trend if (
            (r["price_vs_ema200"] == "ABOVE" and r["direction"] == "BUY") or
            (r["price_vs_ema200"] == "BELOW" and r["direction"] == "SELL")
        ) else against_trend
        bucket["trades"]    += r["trades"]
        bucket["wins"]      += r["wins"]
        bucket["total_pnl"] += r["total_pnl"]

    def _wr(b):
        return (b["wins"] / b["trades"] * 100) if b["trades"] else None

    with_wr    = _wr(with_trend)
    against_wr = _wr(against_trend)

    trend_rows = [
        {
            "Trade type": "With trend (aligned)",
            "Trades": with_trend["trades"],
            "WR%": with_wr,
            "P&L": with_trend["total_pnl"],
        },
        {
            "Trade type": "Against trend",
            "Trades": against_trend["trades"],
            "WR%": against_wr,
            "P&L": against_trend["total_pnl"],
        },
    ]
    df_trend = pd.DataFrame(trend_rows)
    st.dataframe(
        df_trend.style
            .apply(lambda col: [_wr_bg(v) for v in col], subset=["WR%"])
            .format({"WR%": lambda v: f"{v:.1f}%" if v is not None else "—", "P&L": "${:+.2f}"}),
        use_container_width=True, hide_index=True,
    )

    if with_wr is not None and against_wr is not None:
        if with_wr > against_wr + 10:
            st.caption("✅ Trend alignment helps — consider EMA200 filter")
        else:
            st.caption("⚠️ Trend direction not decisive yet")
    else:
        st.caption("⚪ Need more data in one or both buckets")

    st.caption("ABOVE/BUY = trend-following long · BELOW/SELL = trend-following short")

st.markdown("**Current market regime**")
_regime_symbol = sym or "US500"
try:
    from scripts.run_backtest import _fetch_yfinance_candles
    _candles = _fetch_yfinance_candles(_regime_symbol, "DAY", 250)
    if len(_candles) >= 200:
        _closes = [c["close"] for c in _candles]
        _k = 2 / 201
        _ema = _closes[0]
        for _c in _closes[1:]:
            _ema = _c * _k + _ema * (1 - _k)
        _pve = "ABOVE" if _closes[-1] > _ema else "BELOW"
        st.caption(f"{_regime_symbol}: Price is currently **{_pve}** daily EMA200 (EMA200 ≈ {_ema:,.2f})")
    else:
        _no_data_msg("Not enough daily candles to compute EMA200.")
except Exception:
    _no_data_msg("Could not fetch live price for current regime.")


# ── Section 6 — VIX & ATR ──────────────────────────────────────────────────────

st.markdown('<div class="section-hd">VIX & ATR Regime</div>', unsafe_allow_html=True)

vc1, vc2 = st.columns(2)

with vc1:
    st.markdown("**Volatility Context (VIX Buckets)**")
    if _live_vix is not None:
        if _live_vix < 15:
            vix_label = "🟢 Low (<15)"
        elif _live_vix < 20:
            vix_label = "🟡 Normal (15-20)"
        elif _live_vix < 25:
            vix_label = "🟠 Elevated (20-25)"
        else:
            vix_label = "🔴 High (>25)"
        st.caption(f"Current VIX: **{_live_vix:.2f}** — {vix_label}")

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
                .apply(lambda col: [_wr_bg(v) for v in col], subset=["WR%"])
                .format({"WR%": "{:.1f}%", "P&L": "${:+.2f}"}),
            use_container_width=True, hide_index=True,
        )

with vc2:
    st.markdown("**ATR Regime (terciles)**")
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
                })

        if atr_df_rows:
            df_atr = pd.DataFrame(atr_df_rows)
            st.dataframe(
                df_atr.style
                    .apply(lambda col: [_wr_bg(v) for v in col], subset=["WR%"])
                    .format({"WR%": "{:.1f}%", "Total P&L": "${:+.2f}"}),
                use_container_width=True, hide_index=True,
            )
            st.caption(
                f"Tercile boundaries: Low ≤ {t1:.2f} · Medium ≤ {t2:.2f} · High > {t2:.2f}"
            )
            best_atr = max(atr_df_rows, key=lambda r: r["WR%"])
            st.caption(f"Best entries in {best_atr['ATR Regime']} regime ({best_atr['WR%']:.0f}% WR)")
        else:
            _no_data_msg("No resolved ATR data yet.")


# ── Section 7 — Spread Analysis ───────────────────────────────────────────────

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
                    .apply(lambda col: [_wr_bg(v) for v in col], subset=["WR%"])
                    .format({"WR%": "{:.1f}%", "P&L": "${:+.2f}"}),
                use_container_width=True, hide_index=True,
            )
        else:
            _no_data_msg("Insufficient spread data for binning.")


# ── Section 8 — Raw Context Data ─────────────────────────────────────────────

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
