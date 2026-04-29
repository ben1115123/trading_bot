import sys
from pathlib import Path
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

def fetch_summary():
    conn = get_connection()
    try:
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) as n FROM trades")
        total = cur.fetchone()["n"]

        cur.execute("SELECT COUNT(*) as n FROM trades WHERE pnl > 0")
        wins = cur.fetchone()["n"]

        cur.execute("SELECT COUNT(*) as n FROM trades WHERE pnl < 0")
        losses = cur.fetchone()["n"]

        cur.execute("SELECT SUM(pnl) as s FROM trades WHERE pnl IS NOT NULL")
        row = cur.fetchone()
        total_pnl = row["s"] or 0.0

        cur.execute("""
            SELECT strategy_name, symbol, timeframe, strategy_type, score, activated_at
            FROM active_strategy ORDER BY activated_at DESC LIMIT 1
        """)
        strategy_row = cur.fetchone()

        try:
            cur.execute("""
                SELECT strategy_name, symbol, timeframe, score, reason, changed_at
                FROM active_strategy_history ORDER BY changed_at DESC LIMIT 5
            """)
            history_rows = [dict(r) for r in cur.fetchall()]
        except Exception:
            history_rows = []

        cur.execute("SELECT * FROM trades ORDER BY id DESC LIMIT 10")
        recent = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT timestamp, pnl FROM trades
            WHERE pnl IS NOT NULL ORDER BY id ASC
        """)
        pnl_rows = [dict(r) for r in cur.fetchall()]

    finally:
        conn.close()

    win_rate = (wins / total * 100) if total > 0 else 0.0
    return total, wins, losses, win_rate, total_pnl, strategy_row, history_rows, recent, pnl_rows


total, wins, losses, win_rate, total_pnl, strategy_row, history_rows, recent, pnl_rows = fetch_summary()


# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""
<h1 style="margin-bottom:4px">Overview</h1>
<p style="color:#8B949E;font-size:13px;margin-top:0">Live account performance summary</p>
""", unsafe_allow_html=True)


# ── KPI Cards ─────────────────────────────────────────────────────────────────

pnl_class = "pos" if total_pnl >= 0 else "neg"
pnl_sign  = "+" if total_pnl >= 0 else ""

st.markdown(f"""
<div class="kpi-grid">
  <div class="kpi-card blue">
    <div class="kpi-label">Total Trades</div>
    <div class="kpi-value">{total}</div>
    <div class="kpi-sub">{wins}W / {losses}L</div>
  </div>
  <div class="kpi-card {'green' if win_rate >= 50 else 'amber'}">
    <div class="kpi-label">Win Rate</div>
    <div class="kpi-value">{win_rate:.1f}<span style="font-size:16px">%</span></div>
    <div class="kpi-sub">{wins} winning trades</div>
  </div>
  <div class="kpi-card {'green' if total_pnl >= 0 else 'red'}">
    <div class="kpi-label">Total P&amp;L</div>
    <div class="kpi-value {pnl_class}">{pnl_sign}${total_pnl:,.2f}</div>
    <div class="kpi-sub">Closed trades only</div>
  </div>
</div>
""", unsafe_allow_html=True)


# ── Active Strategy ───────────────────────────────────────────────────────────

st.markdown('<div class="section-hd">Active Strategy</div>', unsafe_allow_html=True)

if strategy_row:
    _tf       = strategy_row['timeframe'] or "—"
    _type     = strategy_row['strategy_type'] or "—"
    _score    = f"{strategy_row['score']:.3f}" if strategy_row['score'] else "—"
    _activated = strategy_row['activated_at'][:10] if strategy_row['activated_at'] else "—"
    st.markdown(f"""
    <div class="info-band">
      <div class="info-tile">
        <div class="lbl">Strategy</div>
        <div class="val">{strategy_row['strategy_name']}</div>
      </div>
      <div class="info-tile">
        <div class="lbl">Symbol</div>
        <div class="val">{strategy_row['symbol']}</div>
      </div>
      <div class="info-tile">
        <div class="lbl">Timeframe</div>
        <div class="val">{_tf}</div>
      </div>
      <div class="info-tile">
        <div class="lbl">Type</div>
        <div class="val">{_type}</div>
      </div>
      <div class="info-tile">
        <div class="lbl">Score</div>
        <div class="val">{_score}</div>
      </div>
      <div class="info-tile">
        <div class="lbl">Activated</div>
        <div class="val">{_activated}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if history_rows:
        st.markdown('<div class="section-hd">Strategy History</div>', unsafe_allow_html=True)
        hist_df = pd.DataFrame(history_rows)
        hist_df = hist_df.rename(columns={
            "changed_at":     "Changed",
            "strategy_name":  "Strategy",
            "symbol":         "Symbol",
            "timeframe":      "TF",
            "score":          "Score",
            "reason":         "Reason",
        })
        st.dataframe(hist_df, use_container_width=True, hide_index=True)
else:
    st.markdown("""
    <div style="background:#161B22;border:1px solid #30363D;border-radius:10px;
                padding:16px 20px;color:#8B949E;font-size:13px">
      No active strategy configured yet.
    </div>
    """, unsafe_allow_html=True)


# ── Equity Curve ──────────────────────────────────────────────────────────────

st.markdown('<div class="section-hd">Equity Curve</div>', unsafe_allow_html=True)

if pnl_rows:
    df_pnl = pd.DataFrame(pnl_rows)
    df_pnl["cumulative_pnl"] = df_pnl["pnl"].cumsum()

    line_color  = "#22C55E" if df_pnl["cumulative_pnl"].iloc[-1] >= 0 else "#EF4444"
    fill_color  = "rgba(34,197,94,0.08)" if line_color == "#22C55E" else "rgba(239,68,68,0.08)"

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


# ── Last 10 Trades ────────────────────────────────────────────────────────────

st.markdown('<div class="section-hd">Last 10 Trades</div>', unsafe_allow_html=True)

if recent:
    df = pd.DataFrame(recent)

    display_cols = [c for c in
        ["timestamp", "symbol", "direction", "size", "entry_price", "sl", "tp", "pnl", "status", "deal_id"]
        if c in df.columns]

    # Format P&L with sign
    if "pnl" in df.columns:
        df["pnl"] = df["pnl"].apply(
            lambda v: f"+${v:,.2f}" if isinstance(v, (int, float)) and v > 0
            else (f"-${abs(v):,.2f}" if isinstance(v, (int, float)) and v < 0 else "—")
        )

    st.dataframe(
        df[display_cols],
        use_container_width=True,
        hide_index=True,
        column_config={
            "timestamp":   st.column_config.TextColumn("Time"),
            "symbol":      st.column_config.TextColumn("Symbol"),
            "direction":   st.column_config.TextColumn("Dir"),
            "size":        st.column_config.NumberColumn("Size", format="%.2f"),
            "entry_price": st.column_config.NumberColumn("Entry", format="$%.2f"),
            "sl":          st.column_config.NumberColumn("SL",    format="$%.2f"),
            "tp":          st.column_config.NumberColumn("TP",    format="$%.2f"),
            "pnl":         st.column_config.TextColumn("P&L"),
            "status":      st.column_config.TextColumn("Status"),
            "deal_id":     st.column_config.TextColumn("Deal ID"),
        },
    )
else:
    st.markdown("""
    <div style="background:#161B22;border:1px solid #30363D;border-radius:10px;
                padding:24px;text-align:center;color:#8B949E;font-size:13px">
      No trades recorded yet. Trades will appear here after the bot executes.
    </div>
    """, unsafe_allow_html=True)
