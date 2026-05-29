import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from database.db import get_connection

st.set_page_config(page_title="Webhook Log · Trading Bot", layout="wide")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from styles import inject_css
inject_css()

WEBHOOK_SYMBOLS   = ["EURUSD", "US500"]
DAILY_LOSS_LIMIT  = 75.0
FRIDAY_BLOCK_MINS = 19 * 60 + 45  # 19:45 UTC


# ── Data helpers ──────────────────────────────────────────────────────────────

def _fetch_filter_status() -> list:
    from filters.webhook_filters import SESSION_WINDOWS

    now      = datetime.now(timezone.utc)
    today    = now.strftime("%Y-%m-%d")
    now_mins = now.hour * 60 + now.minute
    friday_blocked = (now.weekday() == 4 and now_mins >= FRIDAY_BLOCK_MINS)

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT COALESCE(SUM(CASE WHEN pnl < 0 THEN pnl ELSE 0 END), 0) AS losses
            FROM trades
            WHERE UPPER(status) = 'CLOSED' AND DATE(timestamp) = ?
        """, (today,))
        row = cur.fetchone()
        loss_today = abs(row["losses"] if row else 0)
        remaining  = max(0.0, DAILY_LOSS_LIMIT - loss_today)
        loss_ok    = loss_today < DAILY_LOSS_LIMIT

        rows = []
        for sym in WEBHOOK_SYMBOLS:
            window = SESSION_WINDOWS.get(sym)
            if window:
                in_session    = window[0] <= now.hour < window[1]
                session_label = f"{window[0]:02d}:00–{window[1]:02d}:00 UTC"
            else:
                in_session    = True
                session_label = "always"

            cur.execute("""
                SELECT status FROM active_strategy
                WHERE symbol = ? AND strategy_name = 'swiftalgo'
                LIMIT 1
            """, (sym,))
            sr           = cur.fetchone()
            strat_status = sr["status"] if sr else "no_row"

            rows.append({
                "symbol":        sym,
                "in_session":    in_session,
                "session_label": session_label,
                "friday_blocked": friday_blocked,
                "loss_ok":       loss_ok,
                "loss_today":    loss_today,
                "remaining":     remaining,
                "strat_status":  strat_status,
            })
        return rows
    finally:
        conn.close()


def _fetch_log(limit: int = 500) -> list:
    conn = get_connection()
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT * FROM webhook_log ORDER BY timestamp DESC LIMIT ?", (limit,)
            )
            return [dict(r) for r in cur.fetchall()]
        except Exception:
            return []
    finally:
        conn.close()


def _fetch_stats(days: int = 7) -> list:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        try:
            cur.execute("""
                SELECT
                    COALESCE(
                        CASE WHEN result IN ('EXECUTED','PAPER') THEN result
                             ELSE block_reason END,
                        result
                    ) AS reason,
                    COUNT(*) AS count
                FROM webhook_log
                WHERE timestamp >= ?
                GROUP BY reason
                ORDER BY count DESC
            """, (cutoff,))
            return [dict(r) for r in cur.fetchall()]
        except Exception:
            return []
    finally:
        conn.close()


# ── Page ──────────────────────────────────────────────────────────────────────

st.title("Webhook Alert Log")
st.caption(
    f"Live filter status + full decision history · "
    f"refreshed at {datetime.now(timezone.utc).strftime('%H:%M UTC')}"
)

# ── Section 1 — Current Filter Status ────────────────────────────────────────

st.subheader("Current Filter Status")

def _ok(flag: bool) -> str:
    return "✅" if flag else "❌"

def _strat_badge(s: str) -> str:
    return {"active": "✅ active", "paper": "⚠️ paper", "inactive": "❌ inactive"}.get(s, f"⚠️ {s}")

try:
    filter_rows = _fetch_filter_status()
    cols = st.columns(len(filter_rows))
    for i, row in enumerate(filter_rows):
        with cols[i]:
            st.markdown(f"**{row['symbol']}**")
            st.markdown(
                f"| Filter | Status | Detail |\n"
                f"|--------|--------|--------|\n"
                f"| Session | {_ok(row['in_session'])} | {row['session_label']} |\n"
                f"| Friday block | {_ok(not row['friday_blocked'])} | "
                f"{'🔒 active' if row['friday_blocked'] else 'not active'} |\n"
                f"| Daily loss | {_ok(row['loss_ok'])} | "
                f"${row['loss_today']:.2f} lost · ${row['remaining']:.2f} left |\n"
                f"| Strategy | {_strat_badge(row['strat_status'])} | swiftalgo |"
            )
except Exception as e:
    st.warning(f"Could not load filter status: {e}")

st.divider()

# ── Section 2 — Alert Decision Log ───────────────────────────────────────────

st.subheader("Alert Decision Log")

fc1, fc2, fc3 = st.columns([2, 2, 2])
with fc1:
    sym_filter = st.selectbox("Symbol", ["All"] + WEBHOOK_SYMBOLS + ["US100", "DAX"])
with fc2:
    result_filter = st.selectbox("Result", ["All", "EXECUTED", "BLOCKED", "PAPER"])
with fc3:
    days_back = st.selectbox(
        "Time window", [1, 3, 7, 14, 30], index=2,
        format_func=lambda x: f"Last {x} day{'s' if x > 1 else ''}"
    )

raw_log  = _fetch_log(limit=500)
cutoff   = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()
filtered = [r for r in raw_log if (r.get("timestamp") or "") >= cutoff]

if sym_filter != "All":
    filtered = [r for r in filtered if r.get("symbol") == sym_filter]
if result_filter != "All":
    filtered = [r for r in filtered if r.get("result") == result_filter]

if not filtered:
    st.info("No webhook alerts in this window.")
else:
    ICONS = {"EXECUTED": "🟢", "BLOCKED": "🔴", "PAPER": "🟡"}

    display = []
    for r in filtered[:200]:
        ts_raw = r.get("timestamp", "")
        try:
            dt    = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            t_str = dt.strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            t_str = ts_raw

        res  = r.get("result", "")
        icon = ICONS.get(res, "⚪")
        display.append({
            "Time (UTC)":   t_str,
            "Symbol":       r.get("symbol", ""),
            "Dir":          r.get("direction", ""),
            "Result":       f"{icon} {res}",
            "Block Reason": r.get("block_reason") or "—",
            "Deal Ref":     r.get("deal_reference") or "—",
            "Notes":        (r.get("notes") or "")[:60] or "—",
        })

    st.dataframe(pd.DataFrame(display), use_container_width=True, hide_index=True)
    st.caption(f"Showing {min(len(filtered), 200)} of {len(filtered)} matching rows")

st.divider()

# ── Section 3 — Filter Hit Rate ───────────────────────────────────────────────

st.subheader("Why alerts were blocked — last 7 days")
stats = _fetch_stats(days=7)

if not stats:
    st.info("No webhook_log data yet. Alerts will appear here once they hit the webhook endpoint.")
else:
    reasons = [r["reason"] or "unknown" for r in stats]
    counts  = [r["count"] for r in stats]

    bar_colors = []
    for reason in reasons:
        if reason == "EXECUTED":  bar_colors.append("#2ecc71")
        elif reason == "PAPER":   bar_colors.append("#f39c12")
        else:                     bar_colors.append("#e74c3c")

    fig = go.Figure(go.Bar(
        x=counts,
        y=reasons,
        orientation="h",
        marker_color=bar_colors,
        text=counts,
        textposition="outside",
        textfont=dict(color="#e0e0e0"),
    ))
    fig.update_layout(
        height=max(220, len(reasons) * 48),
        margin=dict(l=0, r=60, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e0e0e0"),
        xaxis=dict(gridcolor="#333", title="alerts"),
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── Section 4 — Summary Stats ─────────────────────────────────────────────────

st.subheader("Summary — last 7 days")
total = sum(r["count"] for r in stats)

if total == 0:
    st.info("No data.")
else:
    exec_count  = next((r["count"] for r in stats if r["reason"] == "EXECUTED"), 0)
    paper_count = next((r["count"] for r in stats if r["reason"] == "PAPER"),    0)
    block_count = total - exec_count - paper_count

    block_only  = [r for r in stats if r["reason"] not in ("EXECUTED", "PAPER")]
    top_block   = block_only[0]["reason"] if block_only else "—"

    pct = lambda n: f"{n / total * 100:.0f}%" if total else "—"

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total alerts", total)
    c2.metric("Executed", exec_count,  delta=pct(exec_count))
    c3.metric("Blocked",  block_count, delta=f"-{pct(block_count)}", delta_color="inverse")
    c4.metric("Paper",    paper_count, delta=pct(paper_count))
    c5.metric("Top block reason", top_block)
