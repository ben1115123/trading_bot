import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import pandas as pd
from database.db import get_connection

st.set_page_config(page_title="Backtest · Trading Bot", layout="wide")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from styles import inject_css
inject_css()


# ── Data ─────────────────────────────────────────────────────────────────────

def fetch_backtest_results():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM backtest_results ORDER BY score DESC, run_at DESC")
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


results = fetch_backtest_results()


# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""
<h1 style="margin-bottom:4px">Backtest Results</h1>
<p style="color:#8B949E;font-size:13px;margin-top:0">Strategy performance comparison — populated in Phase 3</p>
""", unsafe_allow_html=True)


# ── Content ───────────────────────────────────────────────────────────────────

if not results:
    st.markdown("""
    <div style="background:#161B22;border:1px solid #30363D;border-radius:12px;
                padding:48px 32px;text-align:center;margin:24px 0">
      <div style="width:48px;height:48px;border-radius:50%;background:#1C2333;
                  display:flex;align-items:center;justify-content:center;
                  margin:0 auto 16px">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none"
             stroke="#3B82F6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <line x1="12" y1="8" x2="12" y2="12"/>
          <line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
      </div>
      <div style="font-size:16px;font-weight:600;color:#E6EDF3;margin-bottom:8px">
        No backtest results yet
      </div>
      <div style="font-size:13px;color:#8B949E;max-width:360px;margin:0 auto;line-height:1.6">
        Backtest results will appear here automatically once Phase 3 is complete.
        The scoring formula weights win rate (40%), profit (30%), drawdown (20%), and Sharpe (10%).
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-hd">Table Structure — Ready for Phase 3</div>', unsafe_allow_html=True)
    placeholder_cols = ["strategy_name", "symbol", "timeframe", "total_trades",
                        "win_rate", "profit", "drawdown", "sharpe_ratio", "score", "run_at"]
    st.dataframe(pd.DataFrame(columns=placeholder_cols), use_container_width=True, hide_index=True)

else:
    df = pd.DataFrame(results)
    cols = [c for c in
        ["strategy_name", "symbol", "timeframe", "total_trades",
         "win_rate", "profit", "drawdown", "sharpe_ratio", "score", "run_at"]
        if c in df.columns]

    # Highlight best strategy
    best_idx = df["score"].idxmax() if "score" in df.columns else None

    st.dataframe(
        df[cols],
        use_container_width=True,
        hide_index=True,
        column_config={
            "strategy_name": st.column_config.TextColumn("Strategy"),
            "symbol":        st.column_config.TextColumn("Symbol"),
            "timeframe":     st.column_config.TextColumn("TF"),
            "total_trades":  st.column_config.NumberColumn("Trades",   format="%d"),
            "win_rate":      st.column_config.NumberColumn("Win %",    format="%.1f%%"),
            "profit":        st.column_config.NumberColumn("Profit",   format="$%.2f"),
            "drawdown":      st.column_config.NumberColumn("Drawdown", format="%.1f%%"),
            "sharpe_ratio":  st.column_config.NumberColumn("Sharpe",   format="%.2f"),
            "score":         st.column_config.ProgressColumn("Score",  min_value=0, max_value=1, format="%.3f"),
            "run_at":        st.column_config.TextColumn("Run At"),
        },
    )
