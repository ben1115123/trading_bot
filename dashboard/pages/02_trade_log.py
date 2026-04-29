import sys
import subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import pandas as pd
from database.db import get_connection

st.set_page_config(page_title="Trade Log · Trading Bot", layout="wide")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from styles import inject_css
inject_css()


# ── Data ─────────────────────────────────────────────────────────────────────

def fetch_all_trades():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM trades ORDER BY id DESC")
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""
<h1 style="margin-bottom:4px">Trade Log</h1>
<p style="color:#8B949E;font-size:13px;margin-top:0">Full trade history with filters and CSV export</p>
""", unsafe_allow_html=True)

trades = fetch_all_trades()


# ── Sync from IG ──────────────────────────────────────────────────────────────

with st.expander("↻ Sync from IG", expanded=False):
    sync_days = st.number_input("Lookback days", min_value=1, max_value=90, value=7, step=1, key="sync_days")
    col_dry, col_apply, _ = st.columns([1, 1, 5])
    with col_dry:
        dry_run = st.button("Dry run", key="sync_dry")
    with col_apply:
        apply_sync = st.button("Apply sync", type="primary", key="sync_apply")

    if dry_run or apply_sync:
        script = str(Path(__file__).resolve().parent.parent.parent / "scripts" / "sync_ig_trades.py")
        cmd = [sys.executable, script, "--days", str(int(sync_days))]
        if apply_sync:
            cmd.append("--confirm")
        with st.spinner("Syncing from IG..."):
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                cwd=str(Path(__file__).resolve().parent.parent.parent),
            )
        if proc.returncode == 0:
            st.success("Sync complete")
            st.code(proc.stdout or "(no output)")
        else:
            st.error("Sync failed")
            st.code(proc.stderr or proc.stdout or "(no output)")
        if apply_sync and proc.returncode == 0:
            st.rerun()


if not trades:
    st.markdown("""
    <div style="background:#161B22;border:1px solid #30363D;border-radius:10px;
                padding:48px;text-align:center;color:#8B949E;font-size:14px">
      <div style="font-size:32px;margin-bottom:12px">—</div>
      No trades recorded yet.<br>Trades will appear here after the bot executes.
    </div>
    """, unsafe_allow_html=True)
    st.stop()

df_raw = pd.DataFrame(trades)
df_raw["timestamp"] = pd.to_datetime(df_raw["timestamp"], errors="coerce", utc=True)


# ── Sidebar filters ───────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown('<div class="section-hd" style="margin-top:0">Filters</div>', unsafe_allow_html=True)

    symbols     = ["All"] + sorted(df_raw["symbol"].dropna().unique().tolist())
    directions  = ["All", "BUY", "SELL"]
    strategies  = ["All"] + sorted(df_raw["strategy_name"].dropna().unique().tolist())
    statuses    = ["All"] + sorted(df_raw["status"].dropna().unique().tolist())

    sel_symbol    = st.selectbox("Symbol",    symbols)
    sel_direction = st.selectbox("Direction", directions)
    sel_strategy  = st.selectbox("Strategy",  strategies)
    sel_status    = st.selectbox("Status",    statuses)

    min_date = df_raw["timestamp"].min().date() if not df_raw["timestamp"].isna().all() else None
    max_date = df_raw["timestamp"].max().date() if not df_raw["timestamp"].isna().all() else None
    if min_date and max_date:
        date_range = st.date_input("Date Range", value=(min_date, max_date))
    else:
        date_range = None


# ── Apply filters ─────────────────────────────────────────────────────────────

df = df_raw.copy()

if sel_symbol    != "All": df = df[df["symbol"]        == sel_symbol]
if sel_direction != "All": df = df[df["direction"]     == sel_direction]
if sel_strategy  != "All": df = df[df["strategy_name"] == sel_strategy]
if sel_status    != "All": df = df[df["status"]        == sel_status]

if date_range and len(date_range) == 2:
    start, end = date_range
    df = df[(df["timestamp"].dt.date >= start) & (df["timestamp"].dt.date <= end)]


# ── Summary row ───────────────────────────────────────────────────────────────

filtered_total = len(df)
filtered_pnl   = df["pnl"].sum() if "pnl" in df.columns else 0.0
pnl_sign       = "+" if filtered_pnl >= 0 else ""
pnl_class      = "pos" if filtered_pnl >= 0 else "neg"

st.markdown(f"""
<div class="kpi-grid" style="grid-template-columns:repeat(auto-fit,minmax(160px,1fr));margin-bottom:16px">
  <div class="kpi-card blue">
    <div class="kpi-label">Showing</div>
    <div class="kpi-value">{filtered_total}</div>
    <div class="kpi-sub">of {len(df_raw)} trades</div>
  </div>
  <div class="kpi-card {'green' if filtered_pnl >= 0 else 'red'}">
    <div class="kpi-label">Filtered P&amp;L</div>
    <div class="kpi-value {pnl_class}">{pnl_sign}${filtered_pnl:,.2f}</div>
    <div class="kpi-sub">Closed trades only</div>
  </div>
</div>
""", unsafe_allow_html=True)


# ── Table ─────────────────────────────────────────────────────────────────────

display_cols = [c for c in
    ["id", "timestamp", "symbol", "direction", "size", "entry_price", "sl", "tp",
     "pnl", "status", "deal_id", "source", "strategy_name"]
    if c in df.columns]

df_display = df[display_cols].copy()

# Format timestamp to readable string
if "timestamp" in df_display.columns:
    df_display["timestamp"] = df_display["timestamp"].dt.strftime("%Y-%m-%d %H:%M")

# Format P&L
if "pnl" in df_display.columns:
    df_display["pnl"] = df_display["pnl"].apply(
        lambda v: f"+${v:,.2f}" if pd.notna(v) and v > 0
        else (f"-${abs(v):,.2f}" if pd.notna(v) and v < 0
        else "—")
    )

st.dataframe(
    df_display,
    use_container_width=True,
    hide_index=True,
    height=480,
    column_config={
        "id":            st.column_config.NumberColumn("ID",       format="%d"),
        "timestamp":     st.column_config.TextColumn("Timestamp"),
        "symbol":        st.column_config.TextColumn("Symbol"),
        "direction":     st.column_config.TextColumn("Dir"),
        "size":          st.column_config.NumberColumn("Size",     format="%.2f"),
        "entry_price":   st.column_config.NumberColumn("Entry",    format="$%.2f"),
        "sl":            st.column_config.NumberColumn("SL",       format="$%.2f"),
        "tp":            st.column_config.NumberColumn("TP",       format="$%.2f"),
        "pnl":           st.column_config.TextColumn("P&L"),
        "status":        st.column_config.TextColumn("Status"),
        "deal_id":       st.column_config.TextColumn("Deal ID"),
        "source":        st.column_config.TextColumn("Source"),
        "strategy_name": st.column_config.TextColumn("Strategy"),
    },
)


# ── Export ────────────────────────────────────────────────────────────────────

csv = df_display.to_csv(index=False).encode("utf-8")

col_exp, _ = st.columns([1, 5])
with col_exp:
    st.download_button(
        label="Export CSV",
        data=csv,
        file_name="trade_log.csv",
        mime="text/csv",
    )
