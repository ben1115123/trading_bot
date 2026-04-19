import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.db import init_db
import streamlit as st
from styles import inject_css

init_db()

st.set_page_config(
    page_title="Trading Bot",
    page_icon="assets/icon.svg" if Path("assets/icon.svg").exists() else ":chart_with_upwards_trend:",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()

st.markdown("""
<div style="display:flex;align-items:center;gap:14px;margin-bottom:8px">
  <div style="background:linear-gradient(135deg,#1E40AF,#3B82F6);border-radius:10px;
              width:42px;height:42px;display:flex;align-items:center;justify-content:center;
              font-size:20px;flex-shrink:0">
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white"
         stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>
    </svg>
  </div>
  <div>
    <div style="font-size:22px;font-weight:700;color:#E6EDF3;font-family:Inter,sans-serif;
                letter-spacing:-0.02em">Trading Bot</div>
    <div style="font-size:12px;color:#8B949E;font-family:Inter,sans-serif">Live Account · IG Markets</div>
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown('<div class="section-hd">Navigation</div>', unsafe_allow_html=True)
st.markdown("""
<div style="color:#8B949E;font-size:13px;line-height:1.7">
Use the sidebar to navigate:<br>
<strong style="color:#E6EDF3">Overview</strong> — KPIs, equity curve, recent trades<br>
<strong style="color:#E6EDF3">Trade Log</strong> — full history with filters &amp; export<br>
<strong style="color:#E6EDF3">Calendar</strong> — daily P&amp;L heatmap<br>
<strong style="color:#E6EDF3">Backtest</strong> — strategy results (Phase 3)
</div>
""", unsafe_allow_html=True)
