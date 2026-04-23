import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import time
import streamlit as st
import pandas as pd
from datetime import datetime, timezone
from database.models import get_positions

st.set_page_config(page_title="Live Positions · Trading Bot", layout="wide")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from styles import inject_css
inject_css()


# ── Data ─────────────────────────────────────────────────────────────────────

def fetch_positions():
    return get_positions()


# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""
<h1 style="margin-bottom:4px">Live Positions</h1>
<p style="color:#8B949E;font-size:13px;margin-top:0">Open positions with live unrealised P&amp;L — refreshes every 30 seconds</p>
""", unsafe_allow_html=True)

positions = fetch_positions()

if not positions:
    st.markdown("""
    <div style="background:#161B22;border:1px solid #30363D;border-radius:10px;
                padding:48px;text-align:center;color:#8B949E;font-size:14px">
      <div style="font-size:32px;margin-bottom:12px">—</div>
      No open positions.<br>Positions appear here within 30 seconds of a trade being placed.
    </div>
    """, unsafe_allow_html=True)
    time.sleep(30)
    st.rerun()

df = pd.DataFrame(positions)
df["updated_at"] = pd.to_datetime(df["updated_at"], errors="coerce", utc=True)

now = datetime.now(timezone.utc)
df["duration_min"] = df["updated_at"].apply(
    lambda t: int((now - t).total_seconds() / 60) if pd.notna(t) else None
)


# ── KPI row ───────────────────────────────────────────────────────────────────

total_positions = len(df)
total_pnl = df["unrealised_pnl"].sum() if "unrealised_pnl" in df.columns else 0.0
total_pnl = total_pnl if pd.notna(total_pnl) else 0.0
pnl_sign  = "+" if total_pnl >= 0 else ""
pnl_class = "pos" if total_pnl >= 0 else "neg"
pnl_color = "green" if total_pnl >= 0 else "red"

st.markdown(f"""
<div class="kpi-grid" style="grid-template-columns:repeat(auto-fit,minmax(160px,1fr));margin-bottom:16px">
  <div class="kpi-card blue">
    <div class="kpi-label">Open Positions</div>
    <div class="kpi-value">{total_positions}</div>
    <div class="kpi-sub">across all symbols</div>
  </div>
  <div class="kpi-card {pnl_color}">
    <div class="kpi-label">Unrealised P&amp;L</div>
    <div class="kpi-value {pnl_class}">{pnl_sign}${total_pnl:,.2f}</div>
    <div class="kpi-sub">live estimate</div>
  </div>
</div>
""", unsafe_allow_html=True)


# ── Table ─────────────────────────────────────────────────────────────────────

df_display = df[[
    "symbol", "direction", "size", "open_price",
    "current_price", "unrealised_pnl", "duration_min", "deal_id"
]].copy()

df_display["unrealised_pnl"] = df_display["unrealised_pnl"].apply(
    lambda v: f"+${v:,.2f}" if isinstance(v, (int, float)) and not pd.isna(v) and v >= 0
    else (f"-${abs(v):,.2f}" if isinstance(v, (int, float)) and not pd.isna(v) else "—")
)

df_display["duration_min"] = df_display["duration_min"].apply(
    lambda m: f"{m}m" if m is not None else "—"
)

st.dataframe(
    df_display,
    use_container_width=True,
    hide_index=True,
    column_config={
        "symbol":        st.column_config.TextColumn("Symbol"),
        "direction":     st.column_config.TextColumn("Dir"),
        "size":          st.column_config.NumberColumn("Size",          format="%.2f"),
        "open_price":    st.column_config.NumberColumn("Open Price",    format="$%.2f"),
        "current_price": st.column_config.NumberColumn("Current Price", format="$%.2f"),
        "unrealised_pnl": st.column_config.TextColumn("Unrealised P&L"),
        "duration_min":  st.column_config.TextColumn("Open For"),
        "deal_id":       st.column_config.TextColumn("Deal ID"),
    },
)

st.caption(f"Last updated: {now.strftime('%H:%M:%S')} UTC")

time.sleep(30)
st.rerun()
