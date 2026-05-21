import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from database.db import get_connection

st.set_page_config(page_title="Paper Trading · Trading Bot", layout="wide")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from styles import inject_css
inject_css()


def fetch_paper_data(symbol_filter: str = "All", tf_filter: str = "All") -> dict:
    conn = get_connection()
    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN outcome='WIN'     THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN outcome='LOSS'    THEN 1 ELSE 0 END) as losses,
                   SUM(CASE WHEN outcome='PENDING' THEN 1 ELSE 0 END) as pending,
                   COALESCE(SUM(simulated_pnl), 0) as total_pnl
            FROM paper_trades
        """)
        overall = dict(cur.fetchone())

        cur.execute("""
            SELECT symbol, strategy_name, timeframe,
                   COUNT(*) as total,
                   SUM(CASE WHEN outcome='WIN'  THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) as losses,
                   COALESCE(SUM(simulated_pnl), 0) as total_pnl
            FROM paper_trades
            GROUP BY symbol, strategy_name, timeframe
            ORDER BY symbol ASC
        """)
        by_symbol = [dict(r) for r in cur.fetchall()]

        conditions: list = []
        params: list = []
        if symbol_filter != "All":
            conditions.append("symbol = ?")
            params.append(symbol_filter)
        if tf_filter != "All":
            conditions.append("timeframe = ?")
            params.append(tf_filter)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        cur.execute(f"""
            SELECT * FROM paper_trades {where}
            ORDER BY id DESC LIMIT 200
        """, params)
        trades = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT checked_at, simulated_pnl FROM paper_trades
            WHERE simulated_pnl IS NOT NULL
            ORDER BY id ASC
        """)
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
    """All active_strategy rows with status='paper', LEFT JOINed to paper_trades
    and backtest_results. Returns rows with 0-signal entries for new strategies."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                a.symbol, a.timeframe, a.strategy_name, a.score,
                COUNT(p.id)                                              AS total,
                SUM(CASE WHEN p.outcome='WIN'  THEN 1 ELSE 0 END)       AS wins,
                SUM(CASE WHEN p.outcome='LOSS' THEN 1 ELSE 0 END)       AS losses,
                COALESCE(SUM(p.simulated_pnl), 0)                       AS total_pnl,
                b.win_rate                                               AS bt_win_rate,
                b.total_profit                                           AS bt_pnl
            FROM active_strategy a
            LEFT JOIN paper_trades p
                   ON p.symbol        = a.symbol
                  AND p.timeframe     = a.timeframe
                  AND p.strategy_name = a.strategy_name
            LEFT JOIN backtest_results b ON b.id = a.backtest_id
            WHERE a.status = 'paper'
            GROUP BY a.symbol, a.timeframe, a.strategy_name
            ORDER BY total DESC, a.symbol ASC
        """)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""
<h1 style="margin-bottom:4px">Paper Trading Log</h1>
<p style="color:#8B949E;font-size:13px;margin-top:0">Simulated signals — not executed on live account</p>
""", unsafe_allow_html=True)

d = fetch_paper_data()
o = d["overall"]

total    = o["total"]    or 0
wins     = o["wins"]     or 0
losses   = o["losses"]   or 0
pending  = o["pending"]  or 0
tot_pnl  = o["total_pnl"] or 0.0
resolved = wins + losses
win_rate = (wins / resolved * 100) if resolved > 0 else 0.0


# ── KPI Cards ─────────────────────────────────────────────────────────────────

st.markdown('<div class="section-hd">Summary</div>', unsafe_allow_html=True)

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
    <div class="kpi-sub">Awaiting P&amp;L resolution</div>
  </div>
</div>
""", unsafe_allow_html=True)


# ── Strategy Cards ────────────────────────────────────────────────────────────

st.markdown('<div class="section-hd">Paper Strategies</div>', unsafe_allow_html=True)

paper_strats = fetch_active_paper_strategies()
if paper_strats:
    COLS = 3
    for i in range(0, len(paper_strats), COLS):
        batch = paper_strats[i : i + COLS]
        cols  = st.columns(COLS)
        for col, row in zip(cols, batch):
            with col:
                n   = row["total"]     or 0
                w   = row["wins"]      or 0
                l_  = row["losses"]    or 0
                pnl = row["total_pnl"] or 0.0
                res = w + l_
                wr  = (w / res * 100) if res > 0 else None

                firing   = n > 0
                badge    = "🟢 Firing"  if firing else "⏳ Awaiting signals"
                badge_bg = "#22C55E22" if firing else "#8B949E22"
                badge_c  = "#22C55E"   if firing else "#8B949E"
                border_c = "#22C55E"   if firing else "#30363D"

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

                st.markdown(f"""
                <div style="background:#161B22;border:1px solid {border_c};
                            border-radius:10px;padding:16px 20px;margin-bottom:8px">
                  <div style="display:flex;justify-content:space-between;
                              align-items:center;margin-bottom:12px">
                    <div style="font-size:12px;font-weight:600;color:#3B82F6">
                      {row['symbol']} · {row['timeframe'] or '—'} · {row['strategy_name']}
                    </div>
                    <span style="background:{badge_bg};color:{badge_c};padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600">{badge}</span>
                  </div>
                  <div class="info-tile"><div class="lbl">Strategy</div>
                    <div class="val">{row['strategy_name']}</div></div>
                  <div class="info-tile"><div class="lbl">Signals</div>
                    <div class="val">{n}</div></div>
                  <div class="info-tile"><div class="lbl">Sim Win Rate</div>
                    <div class="val">{wr_badge}</div></div>
                  <div class="info-tile"><div class="lbl">Sim P&amp;L</div>
                    <div class="val" style="color:{pnl_c}">{pnl_str}</div></div>
                  <div class="info-tile" style="border-top:1px solid #21262D;
                    margin-top:8px;padding-top:8px">
                    <div class="lbl">Backtest Win Rate</div>
                    <div class="val">{bt_wr_str}</div></div>
                  <div class="info-tile"><div class="lbl">Backtest P&amp;L</div>
                    <div class="val" style="color:{bt_pnl_c}">{bt_pnl_str}</div></div>
                </div>
                """, unsafe_allow_html=True)
else:
    st.info("No paper strategies configured.")


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

_all_syms = ["All"] + sorted({r["symbol"] for r in d["by_symbol"]})
_all_tfs  = ["All"] + sorted({r["timeframe"] for r in d["by_symbol"] if r["timeframe"]})

f_col1, f_col2 = st.columns([1, 1])
with f_col1:
    sym_sel = st.selectbox("Symbol", _all_syms, label_visibility="collapsed")
with f_col2:
    tf_sel  = st.selectbox("Timeframe", _all_tfs, label_visibility="collapsed")

d_filtered = fetch_paper_data(symbol_filter=sym_sel, tf_filter=tf_sel)

if d_filtered["trades"]:
    df_t = pd.DataFrame(d_filtered["trades"])
    display_cols = [
        "checked_at", "symbol", "timeframe", "strategy_name",
        "signal", "entry_price", "sl", "tp", "simulated_pnl", "outcome",
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
