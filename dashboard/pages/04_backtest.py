import sys
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import pandas as pd
from database.models import get_backtest_results, get_backtest_trades, get_active_strategy

st.set_page_config(page_title="Backtest · Trading Bot", layout="wide")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from styles import inject_css
inject_css()


# ── Score ─────────────────────────────────────────────────────────────────────

def _is_eligible(row) -> bool:
    stype = row.get("strategy_type") or "swing"
    min_trades = 5 if stype == "daytrading" else 10
    if (row.get("total_trades") or 0) < min_trades:
        return False
    if (row.get("total_profit") or 0) <= 0:
        return False
    if (row.get("win_rate") or 0) <= 0.5:
        return False
    benchmark = row.get("benchmark_return")
    if benchmark is not None and (row.get("total_profit", 0) / 1000) <= benchmark:
        return False
    return True


def _compute_scores(df: pd.DataFrame) -> pd.Series:
    def norm(s, invert=False):
        mn, mx = s.min(), s.max()
        if mx == mn:
            return pd.Series([0.5] * len(s), index=s.index)
        n = (s - mn) / (mx - mn)
        return 1 - n if invert else n

    wr = norm(df["win_rate"].fillna(0))
    pr = norm(df["total_profit"].fillna(0))
    dd = norm(df["max_drawdown"].fillna(0), invert=True)
    sr = norm(df["sharpe_ratio"].fillna(0))
    return (wr * 0.4 + pr * 0.3 + dd * 0.2 + sr * 0.1).round(4)


# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""
<h1 style="margin-bottom:4px">Backtest Results</h1>
<p style="color:#8B949E;font-size:13px;margin-top:0">Strategy performance — Phase 3</p>
""", unsafe_allow_html=True)


# ── Run Backtest Panel ────────────────────────────────────────────────────────

with st.expander("▶ Run New Backtest", expanded=False):
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        rb_symbol = st.selectbox("Symbol", ["US500", "US100", "BTC"], key="rb_symbol")
    with col2:
        rb_tf = st.selectbox("Timeframe", ["HOUR", "DAY", "MINUTE"], key="rb_tf")
    with col3:
        rb_strat = st.selectbox("Strategy", ["rsi", "supertrend"], key="rb_strat")
    with col4:
        rb_count = st.number_input("Candles", min_value=100, max_value=2000, value=500, step=100, key="rb_count")
    rb_sweep = st.checkbox("Parameter sweep (runs all param combinations)", key="rb_sweep")

    if st.button("Run Backtest", type="primary"):
        script = str(Path(__file__).resolve().parent.parent.parent / "scripts" / "run_backtest.py")
        cmd = [sys.executable, script,
               "--symbol", rb_symbol,
               "--timeframe", rb_tf,
               "--strategy", rb_strat,
               "--count", str(int(rb_count))]
        if rb_sweep:
            cmd.append("--sweep")
        with st.spinner("Running backtest — this may take 30–60 seconds..."):
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                cwd=str(Path(__file__).resolve().parent.parent.parent),
            )
        if proc.returncode == 0:
            st.success("Backtest complete!")
            st.code(proc.stdout or "(no output)")
        else:
            st.error("Backtest failed.")
            st.code(proc.stderr or proc.stdout or "(no output)")
        st.rerun()


# ── Load data ─────────────────────────────────────────────────────────────────

type_filter = st.sidebar.multiselect(
    "Strategy type", ["swing", "daytrading"], default=["swing", "daytrading"],
    key="type_filter")

rows = get_backtest_results()
if type_filter:
    rows = [r for r in rows if r.get("strategy_type", "swing") in type_filter]

if not rows:
    st.markdown("""
    <div style="background:#161B22;border:1px solid #30363D;border-radius:12px;
                padding:48px 32px;text-align:center;margin:24px 0">
      <div style="font-size:16px;font-weight:600;color:#E6EDF3;margin-bottom:8px">
        No backtest results yet
      </div>
      <div style="font-size:13px;color:#8B949E;max-width:360px;margin:0 auto;line-height:1.6">
        Use the "Run New Backtest" panel above to generate results.
      </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

df = pd.DataFrame(rows)
df["score"] = _compute_scores(df)
df["win_rate_pct"]    = (df["win_rate"].fillna(0) * 100).round(1)
df["benchmark_pct"]   = (df["benchmark_return"].fillna(0) * 100).round(2)
df = df.sort_values("score", ascending=False).reset_index(drop=True)

active = get_active_strategy()
df["is_active"] = df.apply(lambda r:
    active is not None and
    r["strategy_name"] == active["strategy_name"] and
    r["symbol"] == active["symbol"] and
    r["timeframe"] == active["timeframe"],
    axis=1
)
df["eligible"] = df.apply(_is_eligible, axis=1)
df["is_active"] = df["is_active"] & df["eligible"]


# ── Summary table ─────────────────────────────────────────────────────────────

st.markdown('<div class="section-hd">All Runs</div>', unsafe_allow_html=True)

show_eligible_only = st.checkbox("Show eligible only", value=True, key="show_eligible")

fcol1, fcol2, _ = st.columns([2, 2, 6])
with fcol1:
    all_strategies = ["All"] + sorted(df["strategy_name"].unique().tolist())
    strat_filter = st.selectbox("Strategy", all_strategies, key="strat_filter")
with fcol2:
    sym_filter = st.selectbox("Symbol", ["All", "US500", "US100", "BTC"], key="sym_filter")

df_display = df[df["eligible"]].copy() if show_eligible_only else df.copy()
if strat_filter != "All":
    df_display = df_display[df_display["strategy_name"] == strat_filter]
if sym_filter != "All":
    df_display = df_display[df_display["symbol"] == sym_filter]

disp_cols = ["id", "strategy_name", "symbol", "timeframe", "total_trades",
             "win_rate_pct", "total_profit", "max_drawdown",
             "sharpe_ratio", "benchmark_pct", "score", "eligible", "is_active", "run_at"]
disp_cols = [c for c in disp_cols if c in df_display.columns]

eligible_df = df[df["eligible"]]
best_per_symbol = set(eligible_df.groupby("symbol")["score"].idxmax().values) if not eligible_df.empty else set()

event = st.dataframe(
    df_display[disp_cols],
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "id":            st.column_config.NumberColumn("ID",        format="%d", width="small"),
        "strategy_name": st.column_config.TextColumn("Strategy"),
        "symbol":        st.column_config.TextColumn("Symbol"),
        "timeframe":     st.column_config.TextColumn("TF"),
        "total_trades":  st.column_config.NumberColumn("Trades",    format="%d"),
        "win_rate_pct":  st.column_config.NumberColumn("Win %",     format="%.1f%%"),
        "total_profit":  st.column_config.NumberColumn("Profit $",  format="$%.2f"),
        "max_drawdown":  st.column_config.NumberColumn("Drawdown $",format="$%.2f"),
        "sharpe_ratio":  st.column_config.NumberColumn("Sharpe",    format="%.3f"),
        "benchmark_pct": st.column_config.NumberColumn("Benchmark", format="%.2f%%"),
        "score":         st.column_config.ProgressColumn("Score", min_value=0, max_value=1, format="%.3f"),
        "eligible":      st.column_config.CheckboxColumn("Eligible", width="small"),
        "is_active":     st.column_config.CheckboxColumn("Active", width="small"),
        "run_at":        st.column_config.TextColumn("Run At"),
    },
)

sel = event.selection.rows
if sel:
    st.session_state["inspect_run_id"] = int(df_display.iloc[sel[0]]["id"])

best_rows = eligible_df[eligible_df.index.isin(best_per_symbol)][["symbol", "strategy_name", "timeframe", "score"]] if not eligible_df.empty else pd.DataFrame()
if not best_rows.empty:
    st.caption("Best per symbol: " + "  |  ".join(
        f"**{r['symbol']}** → {r['strategy_name']} {r['timeframe']} (score {r['score']:.3f})"
        for _, r in best_rows.iterrows()
    ))


# ── Run inspector ─────────────────────────────────────────────────────────────

st.markdown('<div class="section-hd">Inspect Run</div>', unsafe_allow_html=True)

if df_display.empty:
    st.info("No runs match the current filters.")
    st.stop()

run_options = {
    f"ID {int(r['id'])} — {r['strategy_name']} {r['symbol']} {r['timeframe']}  "
    f"[trades={int(r['total_trades'])}  profit=${r['total_profit']:.2f}  score={r['score']:.3f}]": int(r["id"])
    for _, r in df_display.iterrows()
}
option_ids = list(run_options.values())
stored_id = st.session_state.get("inspect_run_id")
default_idx = option_ids.index(stored_id) if stored_id in option_ids else 0

selected_label = st.selectbox("Select run", list(run_options.keys()), index=default_idx, key="inspect_run")
selected_id = run_options[selected_label]
st.session_state["inspect_run_id"] = selected_id
selected_row = df[df["id"] == selected_id].iloc[0]

trades = get_backtest_trades(selected_id)


# ── Equity curve ──────────────────────────────────────────────────────────────

st.markdown(f"**Equity Curve** — {selected_row['strategy_name']} {selected_row['symbol']} {selected_row['timeframe']}")

if trades:
    trade_df = pd.DataFrame(trades)
    trade_df["trade_num"]      = range(1, len(trade_df) + 1)
    trade_df["cumulative_pnl"] = trade_df["pnl"].cumsum().round(2)

    chart_df = trade_df.set_index("trade_num")[["cumulative_pnl"]]
    chart_df.columns = ["Cumulative P&L ($)"]
    st.line_chart(chart_df)

    # ── Trade drilldown ───────────────────────────────────────────────────────

    with st.expander(f"Trade Drilldown — {len(trades)} trades"):
        show_cols = ["entry_time", "exit_time", "direction",
                     "entry_price", "exit_price", "pnl", "duration_mins"]
        show_cols = [c for c in show_cols if c in trade_df.columns]
        st.dataframe(
            trade_df[show_cols],
            use_container_width=True,
            hide_index=True,
            column_config={
                "entry_time":    st.column_config.TextColumn("Entry"),
                "exit_time":     st.column_config.TextColumn("Exit"),
                "direction":     st.column_config.TextColumn("Dir", width="small"),
                "entry_price":   st.column_config.NumberColumn("Entry $",    format="%.2f"),
                "exit_price":    st.column_config.NumberColumn("Exit $",     format="%.2f"),
                "pnl":           st.column_config.NumberColumn("P&L $",      format="$%.2f"),
                "duration_mins": st.column_config.NumberColumn("Duration",   format="%d min"),
            },
        )
else:
    st.info("No individual trades stored for this run.")


# ── Parameter comparison ──────────────────────────────────────────────────────

siblings = df[
    (df["strategy_name"] == selected_row["strategy_name"]) &
    (df["symbol"]        == selected_row["symbol"]) &
    (df["timeframe"]     == selected_row["timeframe"])
]

if len(siblings) > 1:
    st.markdown(f'<div class="section-hd">Parameter Comparison — '
                f'{selected_row["strategy_name"]} {selected_row["symbol"]} {selected_row["timeframe"]}'
                f' ({len(siblings)} runs)</div>', unsafe_allow_html=True)

    comp_cols = ["params_json", "total_trades", "win_rate_pct",
                 "total_profit", "max_drawdown", "sharpe_ratio", "benchmark_pct", "score"]
    comp_cols = [c for c in comp_cols if c in siblings.columns]

    st.dataframe(
        siblings[comp_cols].sort_values("score", ascending=False),
        use_container_width=True,
        hide_index=True,
        column_config={
            "params_json":   st.column_config.TextColumn("Params"),
            "total_trades":  st.column_config.NumberColumn("Trades",    format="%d"),
            "win_rate_pct":  st.column_config.NumberColumn("Win %",     format="%.1f%%"),
            "total_profit":  st.column_config.NumberColumn("Profit $",  format="$%.2f"),
            "max_drawdown":  st.column_config.NumberColumn("Drawdown $",format="$%.2f"),
            "sharpe_ratio":  st.column_config.NumberColumn("Sharpe",    format="%.3f"),
            "benchmark_pct": st.column_config.NumberColumn("Benchmark", format="%.2f%%"),
            "score":         st.column_config.ProgressColumn("Score", min_value=0, max_value=1, format="%.3f"),
        },
    )
