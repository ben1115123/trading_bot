import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from database.db import get_connection
from database.paper_filters import paper_where, unresolvable_count_sql

st.set_page_config(page_title="Strategy Pipeline · Trading Bot", layout="wide")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from styles import inject_css
inject_css()


def fetch_paper_data(symbol_filter: str = "All", tf_filter: str = "All",
                     strategy_filter: str = "All", source_filter: str = "All",
                     shadow_mode: str = "Real only") -> dict:
    """INSPECTION SURFACE. Unlike pages 01/07 this shows every resolver model —
    a version bump must not blank the page — so paper_model is surfaced as a
    column instead of filtered. Shadow rows are TOGGLED, never hidden: they are
    counterfactuals for deliberately blocked signals and are the only
    measurement of whether a blocking filter helps (findings doc finding 17).
    """
    _inc = {"Real only": False, "Shadow only": "only", "Both": True}[shadow_mode]
    _frag, _fparams = paper_where(include_shadow=_inc, paper_model=None)
    conn = get_connection()
    try:
        cur = conn.cursor()

        cur.execute(f"""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN outcome='WIN'     THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN outcome='LOSS'    THEN 1 ELSE 0 END) as losses,
                   SUM(CASE WHEN outcome='PENDING' THEN 1 ELSE 0 END) as pending,
                   -- paper-v2: total is no longer wins+losses+pending. Rows
                   -- that will never resolve terminate as REFUSED/EXPIRED/
                   -- NO_HISTORY, and an unexplained shortfall in a headline
                   -- count is indistinguishable from data loss — so the page
                   -- SAYS what it dropped rather than letting the arithmetic
                   -- stop reconciling.
                   {unresolvable_count_sql()} as unresolvable,
                   COALESCE(SUM(simulated_pnl), 0) as total_pnl
            FROM paper_trades WHERE 1=1 {_frag}
        """, _fparams)
        overall = dict(cur.fetchone())

        cur.execute(f"""
            SELECT symbol, strategy_name, timeframe,
                   COUNT(*) as total,
                   SUM(CASE WHEN outcome='WIN'  THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) as losses,
                   COALESCE(SUM(simulated_pnl), 0) as total_pnl
            FROM paper_trades WHERE 1=1 {_frag}
            GROUP BY symbol, strategy_name, timeframe
            ORDER BY symbol ASC
        """, _fparams)
        by_symbol = [dict(r) for r in cur.fetchall()]

        conditions: list = [_frag.replace(" AND ", "", 1)] if _frag else []
        params: list = list(_fparams)
        if symbol_filter != "All":
            conditions.append("symbol = ?")
            params.append(symbol_filter)
        if tf_filter != "All":
            conditions.append("timeframe = ?")
            params.append(tf_filter)
        if strategy_filter != "All":
            conditions.append("strategy_name = ?")
            params.append(strategy_filter)
        if source_filter == "tradingview_webhook":
            conditions.append("strategy_name IN ('smc')")
        elif source_filter == "live_signal_loop":
            conditions.append("strategy_name NOT IN ('smc')")
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        cur.execute(f"""
            SELECT * FROM paper_trades {where}
            ORDER BY id DESC LIMIT 200
        """, params)
        trades = [dict(r) for r in cur.fetchall()]

        cur.execute(f"""
            SELECT checked_at, simulated_pnl FROM paper_trades
            WHERE simulated_pnl IS NOT NULL {_frag}
            ORDER BY id ASC
        """, _fparams)
        eq_rows = [dict(r) for r in cur.fetchall()]

    finally:
        conn.close()

    return {
        "overall":   overall,
        "by_symbol": by_symbol,
        "trades":    trades,
        "eq_rows":   eq_rows,
    }


def fetch_active_paper_strategies() -> list:
    """All active + paper strategies. Stats from trades (active) or paper_trades (paper).

    The paper_stats CTE uses the canonical predicate: real rows only. A
    strategy's pipeline stats must not include counterfactuals for signals a
    filter blocked.
    """
    _cfrag, _cparams = paper_where(paper_model=None)
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"""
            WITH trade_stats AS (
                SELECT symbol, strategy_name,
                       COUNT(*)                                          AS total,
                       SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)         AS wins,
                       SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END)         AS losses,
                       COALESCE(SUM(pnl), 0)                            AS total_pnl
                FROM trades
                GROUP BY symbol, strategy_name
            ),
            paper_stats AS (
                SELECT symbol, timeframe, strategy_name,
                       COUNT(*)                                          AS total,
                       SUM(CASE WHEN outcome='WIN'  THEN 1 ELSE 0 END)  AS wins,
                       SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END)  AS losses,
                       COALESCE(SUM(simulated_pnl), 0)                  AS total_pnl
                FROM paper_trades WHERE 1=1 {_cfrag}
                GROUP BY symbol, timeframe, strategy_name
            )
            SELECT
                a.symbol, a.timeframe, a.strategy_name, a.score, a.status,
                CASE a.strategy_name WHEN 'smc' THEN 'webhook' ELSE 'loop' END AS src,
                COALESCE(
                    CASE a.status WHEN 'active' THEN ts.total   ELSE ps.total   END, 0
                ) AS total,
                COALESCE(
                    CASE a.status WHEN 'active' THEN ts.wins    ELSE ps.wins    END, 0
                ) AS wins,
                COALESCE(
                    CASE a.status WHEN 'active' THEN ts.losses  ELSE ps.losses  END, 0
                ) AS losses,
                COALESCE(
                    CASE a.status WHEN 'active' THEN ts.total_pnl ELSE ps.total_pnl END, 0
                ) AS total_pnl,
                b.win_rate     AS bt_win_rate,
                b.total_profit AS bt_pnl
            FROM active_strategy a
            LEFT JOIN trade_stats ts
                   ON a.status = 'active'
                  AND ts.symbol        = a.symbol
                  AND ts.strategy_name = a.strategy_name
            LEFT JOIN paper_stats ps
                   ON a.status = 'paper'
                  AND ps.symbol        = a.symbol
                  AND ps.timeframe     = a.timeframe
                  AND ps.strategy_name = a.strategy_name
            LEFT JOIN backtest_results b ON b.id = a.backtest_id
            WHERE a.status IN ('active', 'paper')
            ORDER BY
                CASE a.status WHEN 'active' THEN 0 ELSE 1 END,
                total DESC,
                a.symbol ASC
        """, _cparams)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""
<h1 style="margin-bottom:4px">Strategy Pipeline</h1>
<p style="color:#8B949E;font-size:13px;margin-top:0">All active and paper strategies — live pipeline view</p>
""", unsafe_allow_html=True)

d = fetch_paper_data()
o = d["overall"]

total        = o["total"]        or 0
wins         = o["wins"]         or 0
losses       = o["losses"]       or 0
pending      = o["pending"]      or 0
unresolvable = o["unresolvable"] or 0
tot_pnl      = o["total_pnl"]    or 0.0
resolved = wins + losses
win_rate = (wins / resolved * 100) if resolved > 0 else 0.0


# ── KPI Cards ─────────────────────────────────────────────────────────────────

st.markdown('<div class="section-hd">Paper Summary</div>', unsafe_allow_html=True)

pnl_cls  = "pos" if tot_pnl >= 0 else "neg"
pnl_sign = "+" if tot_pnl >= 0 else ""

st.markdown(f"""
<div class="kpi-grid">
  <div class="kpi-card blue">
    <div class="kpi-label">Total Signals</div>
    <div class="kpi-value">{total}</div>
    <div class="kpi-sub">All paper signals fired</div>
  </div>
  <div class="kpi-card {"green" if resolved > 0 and win_rate >= 50 else ("red" if resolved > 0 else "blue")}">
    <div class="kpi-label">Sim Win Rate</div>
    <div class="kpi-value">{"—" if resolved == 0 else f"{win_rate:.1f}<span style='font-size:16px'>%</span>"}</div>
    <div class="kpi-sub">{"Awaiting resolution" if resolved == 0 else f"{wins}W / {losses}L"}</div>
  </div>
  <div class="kpi-card {"green" if resolved > 0 and tot_pnl >= 0 else ("red" if resolved > 0 else "blue")}">
    <div class="kpi-label">Sim P&amp;L</div>
    <div class="kpi-value {pnl_cls if resolved > 0 else ""}">{"—" if resolved == 0 else f"{pnl_sign}${tot_pnl:,.2f}"}</div>
    <div class="kpi-sub">Simulated cumulative</div>
  </div>
  <div class="kpi-card amber">
    <div class="kpi-label">Pending</div>
    <div class="kpi-value">{pending}</div>
    <div class="kpi-sub">{f"{unresolvable} unresolvable" if unresolvable else "Awaiting P&amp;L resolution"}</div>
  </div>
</div>
""", unsafe_allow_html=True)

if unresolvable:
    st.caption(
        f"{unresolvable} of {total} signals terminated without a P&L "
        f"(REFUSED / EXPIRED / NO_HISTORY) and are excluded from win rate and "
        f"P&L. Total signals ≠ wins + losses + pending by exactly this count — "
        f"see the Outcome column and `resolution_reason`."
    )


# ── Strategy Cards ────────────────────────────────────────────────────────────

st.markdown('<div class="section-hd">Strategy Pipeline</div>', unsafe_allow_html=True)

pipeline_tf_sel = st.selectbox(
    "Timeframe", ["All", "HOUR", "15MIN"], label_visibility="visible",
    key="pipeline_tf_filter",
)


def _render_pipeline_card(row: dict) -> str:
    n      = row["total"]     or 0
    w      = row["wins"]      or 0
    l_     = row["losses"]    or 0
    pnl    = row["total_pnl"] or 0.0
    res    = w + l_
    wr     = (w / res * 100) if res > 0 else None
    status = row.get("status", "paper")
    src    = row.get("src", "loop")

    if status == "active":
        badge    = "🔵 Live"
        badge_bg = "#1D4ED822"
        badge_c  = "#3B82F6"
        border_c = "#1D4ED8"
    elif n > 0:
        badge    = "🟢 Firing"
        badge_bg = "#22C55E22"
        badge_c  = "#22C55E"
        border_c = "#22C55E"
    else:
        badge    = "⏳ Awaiting"
        badge_bg = "#8B949E22"
        badge_c  = "#8B949E"
        border_c = "#30363D"

    src_badge = (
        '<span style="font-size:10px;color:#F59E0B;background:#F59E0B22;'
        'padding:2px 6px;border-radius:4px;margin-left:6px">📡 webhook</span>'
        if src == "webhook" else
        '<span style="font-size:10px;color:#22C55E;background:#22C55E22;'
        'padding:2px 6px;border-radius:4px;margin-left:6px">🔄 loop</span>'
    )

    wr_lbl  = "Win Rate"     if status == "active" else "Sim Win Rate"
    pnl_lbl = "P&amp;L"     if status == "active" else "Sim P&amp;L"

    wr_str = f"{wr:.1f}%" if wr is not None else "—"
    wr_c   = "#3B82F6"    if (wr or 0) >= 50 else "#8B5CF6"
    wr_badge = (
        f'<span style="background:{wr_c}22;color:{wr_c};'
        f'padding:2px 8px;border-radius:4px;font-weight:700">{wr_str}</span>'
        if wr is not None else "—"
    )

    pnl_str = (f"+${pnl:,.2f}" if pnl >= 0 else f"-${abs(pnl):,.2f}") if res > 0 else "$0.00"
    pnl_c   = ("#22C55E" if pnl >= 0 else "#EF4444") if res > 0 else "#8B949E"

    bt_wr  = row.get("bt_win_rate")
    bt_pnl = row.get("bt_pnl")
    bt_wr_str  = f"{bt_wr * 100:.1f}%"  if bt_wr  is not None else "—"
    bt_pnl_str = (f"+${bt_pnl:,.2f}" if bt_pnl >= 0 else f"-${abs(bt_pnl):,.2f}") if bt_pnl is not None else "—"
    bt_pnl_c   = ("#22C55E" if bt_pnl >= 0 else "#EF4444") if bt_pnl is not None else "#8B949E"

    return f"""
    <div style="background:#161B22;border:1px solid {border_c};
                border-radius:10px;padding:16px 20px;margin-bottom:8px">
      <div style="display:flex;justify-content:space-between;
                  align-items:center;margin-bottom:12px">
        <div style="font-size:12px;font-weight:600;color:#3B82F6">
          {row['symbol']} · {row['timeframe'] or '—'} · {row['strategy_name']}{src_badge}
        </div>
        <span style="background:{badge_bg};color:{badge_c};padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600">{badge}</span>
      </div>
      <div class="info-tile"><div class="lbl">Strategy</div>
        <div class="val">{row['strategy_name']}</div></div>
      <div class="info-tile"><div class="lbl">Signals</div>
        <div class="val">{n}</div></div>
      <div class="info-tile"><div class="lbl">{wr_lbl}</div>
        <div class="val">{wr_badge}</div></div>
      <div class="info-tile"><div class="lbl">{pnl_lbl}</div>
        <div class="val" style="color:{pnl_c}">{pnl_str}</div></div>
      <div class="info-tile" style="border-top:1px solid #21262D;
        margin-top:8px;padding-top:8px">
        <div class="lbl">Backtest Win Rate</div>
        <div class="val">{bt_wr_str}</div></div>
      <div class="info-tile"><div class="lbl">Backtest P&amp;L</div>
        <div class="val" style="color:{bt_pnl_c}">{bt_pnl_str}</div></div>
    </div>
    """


paper_strats = fetch_active_paper_strategies()
if pipeline_tf_sel != "All":
    paper_strats = [r for r in paper_strats if r["timeframe"] == pipeline_tf_sel]

if paper_strats:
    COLS = 3
    other_rows = [r for r in paper_strats if r["timeframe"] not in ("HOUR", "15MIN")]
    for tf_label, tf_value in (("HOUR", "HOUR"), ("15MIN", "15MIN"), ("PAPER · OTHER", None)):
        tf_rows = other_rows if tf_value is None else [r for r in paper_strats if r["timeframe"] == tf_value]
        if not tf_rows:
            continue
        st.markdown(
            f'<div style="font-size:11px;font-weight:700;letter-spacing:0.05em;'
            f'color:#8B949E;margin:12px 0 8px">{tf_label}</div>',
            unsafe_allow_html=True,
        )
        for i in range(0, len(tf_rows), COLS):
            batch = tf_rows[i : i + COLS]
            cols  = st.columns(COLS)
            for col, row in zip(cols, batch):
                with col:
                    st.markdown(_render_pipeline_card(row), unsafe_allow_html=True)
else:
    st.info("No strategies configured.")


# ── Simulated Equity Curve ────────────────────────────────────────────────────

st.markdown('<div class="section-hd">Simulated Equity Curve</div>', unsafe_allow_html=True)

if d["eq_rows"]:
    df_eq = pd.DataFrame(d["eq_rows"])
    df_eq["cumulative_pnl"] = df_eq["simulated_pnl"].cumsum()
    final_val  = df_eq["cumulative_pnl"].iloc[-1]
    line_color = "#3B82F6" if final_val >= 0 else "#8B5CF6"
    fill_color = "rgba(59,130,246,0.08)" if final_val >= 0 else "rgba(139,92,246,0.08)"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_eq["checked_at"],
        y=df_eq["cumulative_pnl"],
        mode="lines",
        line=dict(color=line_color, width=2),
        fill="tozeroy",
        fillcolor=fill_color,
        hovertemplate="<b>%{x}</b><br>Sim P&L: $%{y:,.2f}<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor="#161B22",
        plot_bgcolor="#161B22",
        font=dict(family="Inter, sans-serif", color="#8B949E", size=11),
        xaxis=dict(showgrid=True, gridcolor="#21262D", zeroline=False,
                   tickfont=dict(color="#8B949E"), title=None),
        yaxis=dict(showgrid=True, gridcolor="#21262D", zeroline=True,
                   zerolinecolor="#30363D", tickprefix="$",
                   tickfont=dict(color="#8B949E"), title=None),
        margin=dict(l=0, r=0, t=8, b=0),
        height=260,
        hovermode="x unified",
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.markdown("""
    <div style="background:#161B22;border:1px solid #30363D;border-radius:10px;
                padding:32px;text-align:center;color:#8B949E;font-size:13px">
      No resolved paper trades yet — equity curve appears once trades close with P&amp;L.
    </div>
    """, unsafe_allow_html=True)


# ── Full Signal Log ───────────────────────────────────────────────────────────

st.markdown('<div class="section-hd">Signal Log</div>', unsafe_allow_html=True)

_all_syms    = ["All"] + sorted({r["symbol"] for r in d["by_symbol"]})
_all_tfs     = ["All"] + sorted({r["timeframe"] for r in d["by_symbol"] if r["timeframe"]})
_all_strats  = ["All", "stoch_rsi", "stoch_rsi_confluence", "williams_r", "bb_squeeze",
                "supertrend", "fvg", "smc", "london_breakout",
                "ny_session_momentum", "ema_pullback", "rsi_divergence_session", "silver_bullet"]
_all_sources = ["All", "live_signal_loop", "tradingview_webhook"]
_shadow_modes = ["Real only", "Both", "Shadow only"]

f_col1, f_col2, f_col3, f_col4, f_col5 = st.columns([1, 1, 1, 1, 1])
with f_col1:
    sym_sel    = st.selectbox("Symbol",   _all_syms,    label_visibility="collapsed")
with f_col2:
    tf_sel     = st.selectbox("TF",       _all_tfs,     label_visibility="collapsed")
with f_col3:
    strat_sel  = st.selectbox("Strategy", _all_strats,  label_visibility="collapsed")
with f_col4:
    source_sel = st.selectbox("Source",   _all_sources, label_visibility="collapsed")
with f_col5:
    # TOGGLE, not a hide. Shadow rows are counterfactuals for deliberately
    # blocked signals — separable, never discarded (findings doc finding 17).
    shadow_sel = st.selectbox("Shadow", _shadow_modes, label_visibility="collapsed")

d_filtered = fetch_paper_data(symbol_filter=sym_sel, tf_filter=tf_sel,
                               strategy_filter=strat_sel, source_filter=source_sel,
                               shadow_mode=shadow_sel)
st.caption(
    f"Showing: **{shadow_sel}** · all resolver models. "
    "Rows from different `paper_model` values are NOT comparable — read the "
    "column before comparing any two numbers here."
)

if d_filtered["trades"]:
    df_t = pd.DataFrame(d_filtered["trades"])
    display_cols = [
        "checked_at", "symbol", "timeframe", "strategy_name",
        "signal", "entry_price", "sl", "tp", "simulated_pnl", "outcome",
        "paper_model",
    ]
    df_t = df_t[[c for c in display_cols if c in df_t.columns]]
    df_t["checked_at"] = df_t["checked_at"].apply(lambda t: t[:16] if t else "—")
    st.dataframe(
        df_t,
        use_container_width=True,
        hide_index=True,
        column_config={
            "checked_at":    st.column_config.TextColumn("Time"),
            "symbol":        st.column_config.TextColumn("Symbol"),
            "timeframe":     st.column_config.TextColumn("TF"),
            "strategy_name": st.column_config.TextColumn("Strategy"),
            "signal":        st.column_config.TextColumn("Signal"),
            "entry_price":   st.column_config.NumberColumn("Entry", format="%.2f"),
            "sl":            st.column_config.NumberColumn("SL", format="%.2f"),
            "tp":            st.column_config.NumberColumn("TP", format="%.2f"),
            "simulated_pnl": st.column_config.NumberColumn("Sim P&L", format="$%.2f"),
            "outcome":       st.column_config.TextColumn("Outcome"),
        },
    )
else:
    st.markdown("""
    <div style="background:#161B22;border:1px solid #30363D;border-radius:10px;
                padding:24px;text-align:center;color:#8B949E;font-size:13px">
      No paper trades found.
    </div>
    """, unsafe_allow_html=True)
