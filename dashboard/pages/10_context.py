import sys
import math
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import pandas as pd
from database.db import get_connection
from database.models import get_webhook_outcomes

st.set_page_config(page_title="Context Analysis · Trading Bot", layout="wide")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from styles import inject_css
inject_css()

DAY_NAMES     = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}
SESSION_ORDER = ["LONDON", "LONDON_OPEN", "LONDON_MID", "NY_OPEN", "NY_MID", "NY_CLOSE", "OFF_HOURS"]
PAGE_SIZE     = 25

_SESS_DERIVE_TRADES = """COALESCE(session, CASE
    WHEN CAST(strftime('%H', timestamp) AS INT) BETWEEN 7  AND 9  THEN 'LONDON'
    WHEN CAST(strftime('%H', timestamp) AS INT) BETWEEN 13 AND 14 THEN 'NY_OPEN'
    WHEN CAST(strftime('%H', timestamp) AS INT) BETWEEN 15 AND 17 THEN 'NY_MID'
    WHEN CAST(strftime('%H', timestamp) AS INT) BETWEEN 18 AND 20 THEN 'NY_CLOSE'
    ELSE 'OFF_HOURS' END)"""

_SESS_DERIVE_PAPER = """COALESCE(session, CASE
    WHEN CAST(strftime('%H', checked_at) AS INT) BETWEEN 7  AND 9  THEN 'LONDON'
    WHEN CAST(strftime('%H', checked_at) AS INT) BETWEEN 13 AND 14 THEN 'NY_OPEN'
    WHEN CAST(strftime('%H', checked_at) AS INT) BETWEEN 15 AND 17 THEN 'NY_MID'
    WHEN CAST(strftime('%H', checked_at) AS INT) BETWEEN 18 AND 20 THEN 'NY_CLOSE'
    ELSE 'OFF_HOURS' END)"""


def _wr_bg(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return ""
    if val >= 55:
        return "background-color: #1a4a1a; color: #7ee787"
    if val >= 40:
        return "background-color: #3a2a00; color: #e3b341"
    return "background-color: #4a1a1a; color: #f85149"


def _traffic(wr, pnl=None):
    if wr is None:
        return "⚫"
    if pnl is not None and pnl < 0:
        return "🔴"
    if wr >= 55:
        return "🟢"
    if wr >= 40:
        return "🟡"
    return "🔴"


def _no_data(msg="No data."):
    st.markdown(
        f'<div style="color:#8B949E;font-size:13px;padding:8px 0">{msg}</div>',
        unsafe_allow_html=True,
    )


def _fmt_wr(v):
    return f"{v:.1f}%" if v is not None else "—"


def _fmt_pnl(v):
    return f"${v:+.2f}" if v is not None else "—"


st.markdown("""
<h1 style="margin-bottom:4px">Trade Context & Filter Analysis</h1>
<p style="color:#8B949E;font-size:13px;margin-top:0">
Per-strategy session, day-of-week, and filter breakdown across live and paper trades.
</p>
""", unsafe_allow_html=True)


# ── SECTION 1: FILTERS ───────────────────────────────────────────────────────

st.markdown('<div class="section-hd">Filters</div>', unsafe_allow_html=True)

f1, f2, f3 = st.columns(3)

with f1:
    source_sel = st.selectbox("Source", ["LIVE", "PAPER", "ALL"], index=0, key="ctx_source")

try:
    conn = get_connection()
    cur  = conn.cursor()
    if source_sel == "LIVE":
        _strats = [r[0] for r in cur.execute(
            "SELECT DISTINCT strategy_name FROM trades WHERE pnl IS NOT NULL AND status='CLOSED' ORDER BY strategy_name"
        ).fetchall()]
    elif source_sel == "PAPER":
        _strats = [r[0] for r in cur.execute(
            "SELECT DISTINCT strategy_name FROM paper_trades ORDER BY strategy_name"
        ).fetchall()]
    else:
        _ls = {r[0] for r in cur.execute("SELECT DISTINCT strategy_name FROM trades WHERE pnl IS NOT NULL AND status='CLOSED'").fetchall()}
        _ps = {r[0] for r in cur.execute("SELECT DISTINCT strategy_name FROM paper_trades").fetchall()}
        _strats = sorted(_ls | _ps)
    conn.close()
except Exception as e:
    _strats = []
    st.error(f"DB error: {e}")

_def_strat = "swiftalgo"
_strat_idx = _strats.index(_def_strat) if _def_strat in _strats else 0

with f2:
    strategy_sel = st.selectbox("Strategy", _strats or ["—"], index=_strat_idx, key="ctx_strategy")

try:
    conn = get_connection()
    cur  = conn.cursor()
    if source_sel == "LIVE":
        _syms = [r[0] for r in cur.execute(
            "SELECT DISTINCT symbol FROM trades WHERE strategy_name=? AND pnl IS NOT NULL AND status='CLOSED' ORDER BY symbol",
            (strategy_sel,)
        ).fetchall()]
    elif source_sel == "PAPER":
        _syms = [r[0] for r in cur.execute(
            "SELECT DISTINCT symbol FROM paper_trades WHERE strategy_name=? ORDER BY symbol",
            (strategy_sel,)
        ).fetchall()]
    else:
        _ls2 = {r[0] for r in cur.execute("SELECT DISTINCT symbol FROM trades WHERE strategy_name=? AND pnl IS NOT NULL AND status='CLOSED'", (strategy_sel,)).fetchall()}
        _ps2 = {r[0] for r in cur.execute("SELECT DISTINCT symbol FROM paper_trades WHERE strategy_name=?", (strategy_sel,)).fetchall()}
        _syms = sorted(_ls2 | _ps2)
    conn.close()
except Exception as e:
    _syms = []

_def_sym = "EURUSD"
_sym_idx = _syms.index(_def_sym) if _def_sym in _syms else 0

with f3:
    symbol_sel = st.selectbox("Symbol", _syms or ["—"], index=_sym_idx, key="ctx_symbol")

st.divider()

if not _syms or symbol_sel == "—":
    _no_data(f"No resolved trades for {strategy_sel} ({source_sel}).")
    st.stop()


# ── DATA FETCH ────────────────────────────────────────────────────────────────

def _fetch_live(strategy, symbol):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute(f"""
        SELECT
            timestamp,
            direction,
            {_SESS_DERIVE_TRADES} AS session,
            CAST(strftime('%w', timestamp) AS INT) AS dow,
            pnl,
            status,
            vix_level,
            atr_at_entry
        FROM trades
        WHERE strategy_name = ? AND symbol = ?
          AND status = 'CLOSED' AND pnl IS NOT NULL
        ORDER BY timestamp DESC
    """, (strategy, symbol))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def _fetch_paper(strategy, symbol):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute(f"""
        SELECT
            checked_at AS timestamp,
            CASE
                WHEN signal = 'PAPER_BUY'  THEN 'BUY'
                WHEN signal = 'PAPER_SELL' THEN 'SELL'
                WHEN signal = 'BUY'        THEN 'BUY'
                WHEN signal = 'SELL'       THEN 'SELL'
                ELSE signal
            END AS direction,
            {_SESS_DERIVE_PAPER} AS session,
            CAST(strftime('%w', checked_at) AS INT) AS dow,
            simulated_pnl AS pnl,
            outcome AS status,
            NULL AS vix_level,
            NULL AS atr_at_entry
        FROM paper_trades
        WHERE strategy_name = ? AND symbol = ?
          AND outcome != 'PENDING'
          AND signal NOT LIKE 'SHADOW%'
        ORDER BY checked_at DESC
    """, (strategy, symbol))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


live_rows  = _fetch_live(strategy_sel, symbol_sel)  if source_sel in ("LIVE", "ALL")  else []
paper_rows = _fetch_paper(strategy_sel, symbol_sel) if source_sel in ("PAPER", "ALL") else []
all_rows   = live_rows + paper_rows


# ── SECTION 2: SUMMARY STATS ─────────────────────────────────────────────────

st.markdown('<div class="section-hd">Summary</div>', unsafe_allow_html=True)


def _summary(rows, label):
    resolved = [r for r in rows if r.get("pnl") is not None]
    if not resolved:
        return None
    total      = len(resolved)
    wins       = sum(1 for r in resolved if r["pnl"] > 0)
    total_pnl  = round(sum(r["pnl"] for r in resolved), 2)
    avg_pnl    = round(total_pnl / total, 2)
    gross_win  = sum(r["pnl"] for r in resolved if r["pnl"] > 0)
    gross_loss = abs(sum(r["pnl"] for r in resolved if r["pnl"] < 0))
    pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else None
    return {
        "Source":    label,
        "Trades":    total,
        "Wins":      wins,
        "Losses":    total - wins,
        "WR%":       round(wins / total * 100, 1),
        "Total P&L": total_pnl,
        "Avg P&L":   avg_pnl,
        "PF":        pf,
    }


parts = []
if live_rows:
    s = _summary(live_rows, "LIVE")
    if s:
        parts.append(s)
if paper_rows:
    s = _summary(paper_rows, "PAPER")
    if s:
        parts.append(s)
if source_sel == "ALL" and all_rows:
    s = _summary(all_rows, "COMBINED")
    if s:
        parts.append(s)

if not parts:
    _no_data("No resolved trades.")
else:
    df_sum = pd.DataFrame(parts)
    st.dataframe(
        df_sum.style
            .apply(lambda col: [_wr_bg(v) for v in col], subset=["WR%"])
            .format({
                "WR%":       _fmt_wr,
                "Total P&L": _fmt_pnl,
                "Avg P&L":   _fmt_pnl,
                "PF":        lambda v: f"{v:.2f}" if v is not None else "—",
            }),
        use_container_width=True, hide_index=True,
    )


# ── SECTION 3: SESSION TRAFFIC LIGHTS ────────────────────────────────────────

st.markdown('<div class="section-hd">Session Performance</div>', unsafe_allow_html=True)


def _session_table(rows, label):
    buckets: dict = {}
    for r in rows:
        sess = r.get("session") or "UNKNOWN"
        if sess not in buckets:
            buckets[sess] = {"trades": 0, "wins": 0, "pnl": 0.0}
        b = buckets[sess]
        b["trades"] += 1
        pnl = r.get("pnl")
        if pnl is not None:
            b["pnl"]  += pnl
            b["wins"] += 1 if pnl > 0 else 0

    out  = []
    seen = set()
    for sess in SESSION_ORDER:
        if sess not in buckets:
            continue
        b   = buckets[sess]
        wr  = round(b["wins"] / b["trades"] * 100, 1) if b["trades"] else None
        pnl = round(b["pnl"], 2)
        out.append({"": _traffic(wr, pnl), "Session": sess,
                    "Trades": b["trades"], "WR%": wr, "P&L": pnl})
        seen.add(sess)
    for sess, b in buckets.items():
        if sess in seen:
            continue
        wr  = round(b["wins"] / b["trades"] * 100, 1) if b["trades"] else None
        pnl = round(b["pnl"], 2)
        out.append({"": _traffic(wr, pnl), "Session": sess,
                    "Trades": b["trades"], "WR%": wr, "P&L": pnl})

    if not out:
        _no_data(f"No session data ({label}).")
        return
    st.caption(label)
    st.dataframe(
        pd.DataFrame(out).style
            .apply(lambda col: [_wr_bg(v) for v in col], subset=["WR%"])
            .format({"WR%": _fmt_wr, "P&L": _fmt_pnl}),
        use_container_width=True, hide_index=True,
    )


if source_sel == "ALL":
    sc1, sc2 = st.columns(2)
    with sc1:
        _session_table(live_rows, "LIVE")
    with sc2:
        _session_table(paper_rows, "PAPER")
elif source_sel == "LIVE":
    _session_table(live_rows, "LIVE")
else:
    _session_table(paper_rows, "PAPER")


# ── SECTION 4: DAY OF WEEK ────────────────────────────────────────────────────

st.markdown('<div class="section-hd">Day of Week Performance</div>', unsafe_allow_html=True)


def _dow_table(rows, label):
    buckets: dict = {}
    for r in rows:
        dow = r.get("dow")
        if dow is None:
            continue
        py_dow = (int(dow) - 1) % 7  # SQLite %w 0=Sun,1=Mon → Python 0=Mon
        if py_dow not in buckets:
            buckets[py_dow] = {"trades": 0, "wins": 0, "pnl": 0.0}
        b = buckets[py_dow]
        b["trades"] += 1
        pnl = r.get("pnl")
        if pnl is not None:
            b["pnl"]  += pnl
            b["wins"] += 1 if pnl > 0 else 0

    out = []
    for d in range(5):  # Mon–Fri only
        if d not in buckets:
            continue
        b   = buckets[d]
        wr  = round(b["wins"] / b["trades"] * 100, 1) if b["trades"] else None
        pnl = round(b["pnl"], 2)
        out.append({"": _traffic(wr, pnl), "Day": DAY_NAMES[d],
                    "Trades": b["trades"], "WR%": wr, "P&L": pnl})

    if not out:
        _no_data(f"No day-of-week data ({label}).")
        return
    st.caption(label)
    st.dataframe(
        pd.DataFrame(out).style
            .apply(lambda col: [_wr_bg(v) for v in col], subset=["WR%"])
            .format({"WR%": _fmt_wr, "P&L": _fmt_pnl}),
        use_container_width=True, hide_index=True,
    )


if source_sel == "ALL":
    dc1, dc2 = st.columns(2)
    with dc1:
        _dow_table(live_rows, "LIVE")
    with dc2:
        _dow_table(paper_rows, "PAPER")
elif source_sel == "LIVE":
    _dow_table(live_rows, "LIVE")
else:
    _dow_table(paper_rows, "PAPER")


# ── SECTION 5: FILTER EFFECTIVENESS ─────────────────────────────────────────

st.markdown('<div class="section-hd">Filter Effectiveness — Blocked Signals</div>', unsafe_allow_html=True)

# Shadow paper trades — signals blocked by session filter or margin rejection
try:
    conn        = get_connection()
    cur         = conn.cursor()
    cur.execute("""
        SELECT checked_at, signal, simulated_pnl, outcome, notes, session
        FROM paper_trades
        WHERE strategy_name = ? AND symbol = ?
          AND signal LIKE 'SHADOW%'
        ORDER BY checked_at DESC
    """, (strategy_sel, symbol_sel))
    shadow_rows = [dict(r) for r in cur.fetchall()]
    conn.close()
except Exception as e:
    shadow_rows = []
    st.error(f"DB error: {e}")

# Blocked webhook alerts — for webhook-sourced strategies (swiftalgo)
try:
    conn        = get_connection()
    wh_outcomes = get_webhook_outcomes(conn, days=90)
    wh_outcomes = [r for r in wh_outcomes if r.get("symbol") == symbol_sel]
    conn.close()
except Exception:
    wh_outcomes = []

if shadow_rows:
    resolved = [r for r in shadow_rows if r["outcome"] in ("WIN", "LOSS")]
    pending  = [r for r in shadow_rows if r["outcome"] == "PENDING"]
    st.markdown(
        f"**Blocked signals (shadow log)** — "
        f"{len(shadow_rows)} total · {len(resolved)} resolved · {len(pending)} pending"
    )
    if resolved:
        s_wins = sum(1 for r in resolved if r["outcome"] == "WIN")
        s_wr   = round(s_wins / len(resolved) * 100, 1)
        s_pnl  = round(sum((r["simulated_pnl"] or 0) for r in resolved), 2)
        if s_wr < 45:
            verdict = "✅ Good to block — WR below threshold"
        elif s_wr >= 55:
            verdict = "🔴 Consider unblocking — high WR when fired"
        else:
            verdict = "🟡 Ambiguous — accumulate more data"
        st.caption(
            f"WR if unblocked: **{s_wr:.1f}%** | Simulated P&L: **${s_pnl:+.2f}** — {verdict}"
        )

    df_shadow = pd.DataFrame([{
        "Date":    (r["checked_at"] or "")[:16].replace("T", " "),
        "Signal":  r["signal"],
        "Session": r.get("session") or "—",
        "Outcome": r["outcome"],
        "Sim P&L": _fmt_pnl(r.get("simulated_pnl")),
        "Notes":   r.get("notes") or "",
    } for r in shadow_rows[:25]])
    st.dataframe(df_shadow, use_container_width=True, hide_index=True)

elif wh_outcomes:
    st.markdown(f"**Blocked webhook alerts** — {len(wh_outcomes)} resolved")
    df_wh = pd.DataFrame([{
        "Date":         (r.get("timestamp") or "")[:16].replace("T", " "),
        "Direction":    r.get("direction"),
        "Block Reason": r.get("block_reason"),
        "Outcome":      r.get("outcome"),
        "Est P&L":      _fmt_pnl(r.get("estimated_pnl")),
    } for r in wh_outcomes[:25]])
    st.dataframe(df_wh, use_container_width=True, hide_index=True)

else:
    _no_data("No blocked signals found for this strategy/symbol yet.")


# ── SECTION 6: VIX + ATR (live only) ────────────────────────────────────────

st.markdown('<div class="section-hd">VIX & ATR Context</div>', unsafe_allow_html=True)

if source_sel == "PAPER":
    st.info("VIX/ATR context only available for live trades.", icon="ℹ️")
else:
    vix_src = [r for r in live_rows if r.get("vix_level") is not None]
    atr_src = sorted(
        [r for r in live_rows if r.get("atr_at_entry") is not None],
        key=lambda r: r["atr_at_entry"],
    )

    vc1, vc2 = st.columns(2)

    with vc1:
        st.markdown("**VIX Buckets**")
        if not vix_src:
            _no_data("No VIX data for this selection.")
        else:
            vbuckets: dict = {}
            vorder = ["Low (<15)", "Normal (15-20)", "Elevated (20-25)", "High (>25)"]
            for r in vix_src:
                v = r["vix_level"]
                k = ("Low (<15)" if v < 15 else "Normal (15-20)" if v < 20
                     else "Elevated (20-25)" if v < 25 else "High (>25)")
                if k not in vbuckets:
                    vbuckets[k] = {"trades": 0, "wins": 0, "pnl": 0.0}
                vbuckets[k]["trades"] += 1
                pnl = r.get("pnl")
                if pnl is not None:
                    vbuckets[k]["pnl"]  += pnl
                    vbuckets[k]["wins"] += 1 if pnl > 0 else 0
            vrows = []
            for k in vorder:
                if k not in vbuckets:
                    continue
                b  = vbuckets[k]
                wr = round(b["wins"] / b["trades"] * 100, 1) if b["trades"] else None
                vrows.append({"VIX": k, "Trades": b["trades"],
                              "WR%": wr, "P&L": round(b["pnl"], 2)})
            st.dataframe(
                pd.DataFrame(vrows).style
                    .apply(lambda col: [_wr_bg(v) for v in col], subset=["WR%"])
                    .format({"WR%": _fmt_wr, "P&L": _fmt_pnl}),
                use_container_width=True, hide_index=True,
            )

    with vc2:
        st.markdown("**ATR Regime (terciles)**")
        if len(atr_src) < 6:
            _no_data("Need ≥ 6 trades with ATR data.")
        else:
            n  = len(atr_src)
            t1 = atr_src[n // 3]["atr_at_entry"]
            t2 = atr_src[2 * n // 3]["atr_at_entry"]
            abuckets: dict = {"Low": [], "Medium": [], "High": []}
            for r in atr_src:
                pnl = r.get("pnl")
                if pnl is None:
                    continue
                atr   = r["atr_at_entry"]
                label = "Low" if atr <= t1 else "Medium" if atr <= t2 else "High"
                abuckets[label].append(pnl)
            arows = []
            for label, pnls in abuckets.items():
                if not pnls:
                    continue
                w = sum(1 for p in pnls if p > 0)
                arows.append({
                    "ATR": label, "Trades": len(pnls),
                    "WR%": round(w / len(pnls) * 100, 1),
                    "P&L": round(sum(pnls), 2),
                })
            if arows:
                st.dataframe(
                    pd.DataFrame(arows).style
                        .apply(lambda col: [_wr_bg(v) for v in col], subset=["WR%"])
                        .format({"WR%": _fmt_wr, "P&L": _fmt_pnl}),
                    use_container_width=True, hide_index=True,
                )
                st.caption(
                    f"Low ≤ {t1:.4f} · Medium ≤ {t2:.4f} · High > {t2:.4f}"
                )
            else:
                _no_data("No resolved ATR data.")


# ── SECTION 7: TRADE LOG ─────────────────────────────────────────────────────

st.markdown('<div class="section-hd">Trade Log</div>', unsafe_allow_html=True)

if not all_rows:
    _no_data("No trades for this selection.")
else:
    log_display = []
    for r in all_rows:
        ts  = r.get("timestamp") or ""
        dow = r.get("dow")
        py_dow = (int(dow) - 1) % 7 if dow is not None else None
        log_display.append({
            "Date":      ts[:16].replace("T", " ") if ts else "—",
            "Direction": r.get("direction") or "—",
            "Session":   r.get("session") or "—",
            "Day":       DAY_NAMES.get(py_dow, "?") if py_dow is not None else "—",
            "P&L":       _fmt_pnl(r.get("pnl")),
            "Status":    r.get("status") or "—",
            "VIX":       f"{r['vix_level']:.1f}" if r.get("vix_level") is not None else "—",
        })

    total_pages = max(1, math.ceil(len(log_display) / PAGE_SIZE))
    pg_key = "ctx_page"
    if pg_key not in st.session_state:
        st.session_state[pg_key] = 0
    pg = max(0, min(st.session_state[pg_key], total_pages - 1))

    st.dataframe(
        pd.DataFrame(log_display[pg * PAGE_SIZE : (pg + 1) * PAGE_SIZE]),
        use_container_width=True, hide_index=True,
    )
    st.caption(f"Page {pg + 1} of {total_pages}  ·  {len(log_display)} total trades")

    pc1, pc2, _ = st.columns([1, 1, 6])
    with pc1:
        if st.button("◀ Prev", disabled=(pg == 0)):
            st.session_state[pg_key] = pg - 1
            st.rerun()
    with pc2:
        if st.button("Next ▶", disabled=(pg >= total_pages - 1)):
            st.session_state[pg_key] = pg + 1
            st.rerun()
