#!/usr/bin/env python3
"""
CLI entry point for Phase 3 backtesting.

Usage:
  python scripts/run_backtest.py --symbol US500 --timeframe HOUR --strategy rsi --count 500
  python scripts/run_backtest.py --symbol BTC --timeframe DAY --strategy supertrend --count 500 --sweep
"""
import argparse
import itertools
import json
import sqlite3
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CACHE_DIR = Path(__file__).resolve().parent / "candle_cache"
CACHE_MAX_AGE_SECONDS = 86400  # 24 hours

YF_SYMBOLS   = {"US500": "^GSPC", "US100": "^NDX", "BTC": "BTC-USD", "DAX": "^GDAXI", "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X", "AUDUSD": "AUDUSD=X", "USDCAD": "USDCAD=X"}
YF_INTERVALS = {"5MIN": "5m", "15MIN": "15m", "HOUR": "1h", "DAY": "1d"}
YF_PERIODS   = {"5m": "60d", "15m": "60d", "1h": "730d", "1d": "5y"}


def _fetch_yfinance_candles(symbol: str, timeframe: str, count: int | None) -> list:
    """Fetch candles from yfinance.

    count is a TAIL TRIM applied AFTER the download, not a range selector — the
    download size is fixed by YF_PERIODS per interval and `count` has never
    influenced it. Pass count=None to skip the trim and receive the full
    downloaded history.

    That distinction is not cosmetic: the paper resolver asked for 100 and then
    filtered to candles after its signal, which for any row older than the
    100-candle tail left EVERY returned candle passing the filter — so it
    resolved against a window weeks downstream of the signal rather than a
    truncated one (findings doc finding 22). Callers that need a window
    relative to a timestamp must take the full history and slice by time.
    """
    try:
        import yfinance as yf
    except ImportError:
        raise RuntimeError("yfinance not installed — run: pip install yfinance")
    ticker   = YF_SYMBOLS.get(symbol.upper())
    interval = YF_INTERVALS.get(timeframe.upper())
    if not ticker or not interval:
        raise ValueError(f"Unknown symbol/timeframe for yfinance: {symbol} {timeframe}")
    period = YF_PERIODS[interval]
    df = yf.download(ticker, period=period, interval=interval,
                     auto_adjust=True, progress=False)
    if df.empty:
        raise RuntimeError(f"yfinance returned no data for {ticker}")
    candles = []
    for ts, row in df.iterrows():
        try:
            # Handle both flat and MultiIndex columns
            def _get(col):
                val = row[col]
                return float(val.iloc[0]) if hasattr(val, "iloc") else float(val)
            o, h, l, c = _get("Open"), _get("High"), _get("Low"), _get("Close")
        except Exception:
            continue
        if any(v != v for v in [o, h, l, c]):
            continue
        try:
            vol = _get("Volume")
        except Exception:
            vol = 0.0
        candles.append({"time": str(ts), "open": o, "high": h, "low": l, "close": c, "volume": vol})
    return candles if count is None else candles[-count:]


def _load_alphavantage_candles(symbol: str, timeframe: str) -> list:
    path = CACHE_DIR / f"{symbol.upper()}_{timeframe.upper()}_AV.json"
    if not path.exists():
        raise RuntimeError(
            f"No Alpha Vantage cache found at {path}. "
            f"Run: python3 scripts/fetch_historical.py --symbol {symbol.upper()} --timeframe {timeframe.upper()}"
        )
    with open(path) as f:
        return json.load(f)


def _load_ig_cache_candles(symbol: str, timeframe: str) -> list:
    path = CACHE_DIR / f"{symbol.upper()}_{timeframe.upper()}_IG.json"
    if not path.exists():
        raise RuntimeError(
            f"No IG-collected cache found at {path}. "
            f"Run scripts/collect_candles.py on the VPS to start building this cache."
        )
    with open(path) as f:
        return json.load(f)


def _cache_path(symbol: str, timeframe: str, count: int, source: str = "ig") -> Path:
    suffix = "_yf" if source == "yfinance" else ""
    return CACHE_DIR / f"{symbol.upper()}_{timeframe.upper()}_{count}{suffix}.json"


def _load_cache(symbol: str, timeframe: str, count: int, source: str = "ig") -> list | None:
    path = _cache_path(symbol, timeframe, count, source)
    if not path.exists():
        return None
    if time.time() - path.stat().st_mtime > CACHE_MAX_AGE_SECONDS:
        return None
    with open(path) as f:
        return json.load(f)


def _save_cache(symbol: str, timeframe: str, count: int, candles: list, source: str = "ig") -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    with open(_cache_path(symbol, timeframe, count, source), "w") as f:
        json.dump(candles, f)

from dotenv import load_dotenv
load_dotenv()

from trading_ig import IGService

from ig_env import get_ig_credentials
import backend.backtesting.engine as engine_mod
from backend.backtesting.engine import (provenance, 
    fetch_candles, run_backtest, run_parameter_sweep, run_walk_forward, run_stability_map,
    WF_TRAIN_MONTHS, WF_MIN_WINDOWS,
)
from backend.backtesting.metrics import (
    calc_win_rate, calc_max_drawdown, calc_sharpe_ratio, calc_total_profit, calc_profit_factor,
)
from backend.backtesting.robustness import (
    compute_plateau_metrics, find_clusters, bootstrap_mc, permutation_test,
)
from backend.strategies.rsi import RSIStrategy
from backend.strategies.supertrend import SuperTrendStrategy
from backend.strategies.vwap_ema import VWAPEMAStrategy
from backend.strategies.ema_ribbon import EMARibbonStrategy
from backend.strategies.bb_squeeze import BBSqueezeStrategy
from backend.strategies.rsi_divergence import RSIDivergenceStrategy
from backend.strategies.orb import ORBStrategy
from backend.strategies.ichimoku import IchimokuStrategy
from backend.strategies.keltner import KeltnerChannelStrategy
from backend.strategies.stoch_rsi import StochRSIStrategy
from backend.strategies.stoch_rsi_confluence import StochRSIConfluenceStrategy
from backend.strategies.ema_cross_volume import EMACrossVolumeStrategy
from backend.strategies.vwap_mean_reversion import VWAPMeanReversionStrategy
from backend.strategies.connors_rsi2 import ConnorsRSI2Strategy
from backend.strategies.williams_r import WilliamsRStrategy
from backend.strategies.macd_rsi import MACDRSIStrategy
from backend.strategies.fvg import FVGStrategy
from backend.strategies.london_breakout import LondonBreakoutStrategy
from backend.strategies.smc import SMCStrategy
from backend.strategies.silver_bullet import SilverBulletStrategy
from backend.strategies.ny_session_momentum import NYSessionMomentumStrategy
from backend.strategies.ema_pullback import EMAPullbackStrategy
from backend.strategies.rsi_divergence_session import RSIDivergenceSessionStrategy
from backend.strategies.rsi_mean_reversion import RSIMeanReversionStrategy
from backend.strategies.macd_crossover import MACDCrossoverStrategy
from backend.strategies.donchian_breakout import DonchianBreakoutStrategy
from backend.strategies.inside_bar_breakout import InsideBarBreakoutStrategy
from backend.strategies.engulfing_candle import EngulfingCandleStrategy
from backend.strategies.regime_adaptive import RegimeAdaptiveStrategy
from backend.strategies.market_structure_break import MarketStructureBreakStrategy
from backend.strategies.kama_crossover import KAMACrossoverStrategy
from backend.strategies.ema_ribbon_pullback import EMARibbonPullbackStrategy
from backend.strategies.hull_momentum import HullMomentumStrategy
from backend.strategies.supertrend_ema_filter import SupertrendEMAFilterStrategy
from database.models import (insert_backtest_result, insert_backtest_trades,
                             insert_walkforward_run, get_roster_row)

STRATEGIES = {
    "rsi":        RSIStrategy,
    "supertrend": SuperTrendStrategy,
    "vwap_ema":   VWAPEMAStrategy,
    "ema_ribbon":  EMARibbonStrategy,
    "bb_squeeze":     BBSqueezeStrategy,
    "rsi_divergence": RSIDivergenceStrategy,
    "orb":            ORBStrategy,
    "ichimoku":       IchimokuStrategy,
    "keltner":        KeltnerChannelStrategy,
    "stoch_rsi":        StochRSIStrategy,
    "stoch_rsi_confluence": StochRSIConfluenceStrategy,
    "ema_cross_volume":     EMACrossVolumeStrategy,
    "vwap_mean_reversion":  VWAPMeanReversionStrategy,
    "connors_rsi2":         ConnorsRSI2Strategy,
    "williams_r":           WilliamsRStrategy,
    "macd_rsi":             MACDRSIStrategy,
    "fvg":                  FVGStrategy,
    "london_breakout":      LondonBreakoutStrategy,
    "smc":                  SMCStrategy,
    "silver_bullet":        SilverBulletStrategy,
    "ny_session_momentum":  NYSessionMomentumStrategy,
    "ema_pullback":         EMAPullbackStrategy,
    "rsi_divergence_session": RSIDivergenceSessionStrategy,
    "rsi_mean_reversion":   RSIMeanReversionStrategy,
    "macd_crossover":       MACDCrossoverStrategy,
    "donchian_breakout":    DonchianBreakoutStrategy,
    "inside_bar_breakout":  InsideBarBreakoutStrategy,
    "engulfing_candle":        EngulfingCandleStrategy,
    "regime_adaptive":         RegimeAdaptiveStrategy,
    "market_structure_break":  MarketStructureBreakStrategy,
    "kama_crossover":          KAMACrossoverStrategy,
    "ema_ribbon_pullback":     EMARibbonPullbackStrategy,
    "hull_momentum":           HullMomentumStrategy,
    "supertrend_ema_filter":   SupertrendEMAFilterStrategy,
}

PARAM_GRIDS = {
    "rsi": {
        "period":     [7, 14, 21],
        "overbought": [65, 70, 75],
        "oversold":   [25, 30, 35],
    },
    "supertrend": {
        "period":     [7, 10, 14],
        "multiplier": [2.0, 3.0, 4.0],
    },
    "vwap_ema": {
        "ema_period":      [10, 20, 50],
        "vwap_deviation":  [0.001, 0.002, 0.005],
    },
    "ema_ribbon": {
        "fast": [5, 8, 13],
        "mid":  [13, 21, 34],
        "slow": [34, 55, 89],
    },
    "bb_squeeze": {
        "period":             [10, 20, 30],
        "std_dev":            [1.5, 2.0, 2.5],
        "squeeze_threshold":  [0.001, 0.002, 0.003],
    },
    "rsi_divergence": {
        "rsi_period": [7, 14, 21],
        "lookback":   [3, 5, 8],
        "overbought": [65, 70, 75],
        "oversold":   [25, 30, 35],
    },
    "orb": {
        "candles_in_range":  [3, 6, 12],
        "breakout_buffer":   [0.0005, 0.001, 0.002],
    },
    "ichimoku": {
        "tenkan":       [7, 9, 13],
        "kijun":        [20, 26, 34],
        "senkou_b":     [44, 52, 60],
        "displacement": [26],
    },
    "keltner": {
        "ema_period": [15, 20, 30],
        "atr_period": [7, 10, 14],
        "multiplier": [1.5, 2.0, 2.5],
    },
    "stoch_rsi": {
        "rsi_period":   [9, 14, 21],
        "stoch_period": [9, 14, 21],
        "k_smooth":     [3],
        "d_smooth":     [3],
        "oversold":     [15, 20, 25],
        "overbought":   [75, 80, 85],
    },
    "stoch_rsi_confluence": {
        "rsi_period":     [14],
        "stoch_period":   [14],
        "k_smooth":       [3],
        "d_smooth":       [3],
        "oversold":       [20],
        "overbought":     [80],
        "session_filter": [True, False],
        "atr_filter":     [True, False],
        "atr_period":     [14],
        "atr_lookback":   [50],
    },
    "ema_cross_volume": {
        "fast":       [5, 8, 13],
        "slow":       [13, 21, 34],
        "vol_period": [10, 20],
    },
    "vwap_mean_reversion": {
        "std_dev_entry": [1.0, 1.5, 2.0],
        "std_dev_exit":  [0.2],
        "lookback":      [10, 20, 30],
    },
    "connors_rsi2": {
        "oversold":   [5, 10, 15],
        "overbought": [85, 90, 95],
        "sma_long":   [100, 200],
        "sma_exit":   [3, 5, 10],
    },
    "williams_r": {
        "period":     [10, 14, 21],
        "oversold":   [-80, -85, -90],
        "overbought": [-10, -15, -20],
    },
    "macd_rsi": {
        "fast":       [8, 12],
        "slow":       [21, 26],
        "signal":     [7, 9],
        "rsi_period": [14],
        "ema_period": [50, 100],
    },
    "fvg": {
        "atr_period":     [10, 14, 21],
        "min_gap_atr":    [0.2, 0.3, 0.5],
        "expiry_candles": [5, 10, 15],
    },
    "smc": {
        "swing_lookback":     [3, 5, 8, 10],
        "min_gap_atr":        [0.3, 0.5, 0.7],
        "fvg_expiry":         [10, 15],
        "atr_period":         [10, 14],
        "use_session_filter": [False],
    },
    "london_breakout": {
        "min_range_pips":   [3, 5, 8, 10],
        "breakout_buffer":  [0.0, 0.3, 0.5],
        "tp_multiplier":    [1.0, 1.5, 2.0, 2.5],
        "use_ema_filter":   [False, True],
        "range_start_hour": [6],
        "range_end_hour":   [7],
        "entry_window_end": [9],
    },
    "silver_bullet": {
        "kill_start":     [13],
        "kill_end":       [16],
        "min_gap_atr":    [0.2, 0.3, 0.5],
        "fvg_expiry":     [5, 8, 12],
        "atr_period":     [10, 14],
        "swing_lookback": [5, 10, 15],
        "tp_swing_bars":  [10, 20],
        "use_htf_bias":   [False, True],
    },
    "ny_session_momentum": {
        "range_minutes":   [30, 60],
        "min_range_pips":  [3, 5, 8],
        "breakout_buffer": [0.0, 0.3],
        "tp_multiplier":   [1.0, 1.5, 2.0],
        "fade_mode":       [True, False],
    },
    "ema_pullback": {
        "ema_fast":     [8, 13],
        "ema_slow":     [21, 50],
        "min_move_atr": [1.0, 1.5, 2.0],
        "sl_atr_mult":  [1.0, 1.5],
        "tp_atr_mult":  [2.0, 2.5, 3.0],
    },
    "rsi_divergence_session": {
        "rsi_period":      [9, 14],
        "divergence_bars": [8, 12, 16],
        "min_rsi_diff":    [3, 5, 8],
        "sl_atr_mult":     [1.0, 1.5],
        "tp_atr_mult":     [2.0, 2.5],
    },
    "regime_adaptive": {
        "ema_fast":        [8, 13],
        "ema_slow":        [21, 50],
        "atr_trend_mult":  [1.0, 1.2, 1.5],
        "bb_std":          [1.5, 2.0],
        "sl_atr_mult":     [1.0, 1.5],
        "tp_atr_mult":     [2.0, 2.5, 3.0],
    },
    "market_structure_break": {
        "swing_bars":   [8, 10, 15, 20],
        "sl_atr_mult":  [1.0, 1.5],
        "tp_atr_mult":  [2.0, 2.5, 3.0],
    },
    "kama_crossover": {
        "period":        [8, 10, 14],
        "slope_window":  [2, 3, 5],
        "atr_min_filter": [0.00030],
        "min_sl_dist":    [0.00050],
    },
}

# Grids for --stability-map (full walk-forward per cell, not single-split).
# Deliberately separate from PARAM_GRIDS (single-split sweep) — stability
# maps are much more expensive per cell so grids here should stay coarse.
STABILITY_GRIDS = {
    "williams_r": {
        "period":     [8, 10, 12, 14, 16, 18, 21],
        "oversold":   [-95, -90, -85, -80],
        "overbought": [-20, -15, -10],
    },
}


def create_ig_session() -> IGService:
    username, password, api_key, acc_type = get_ig_credentials()
    svc = IGService(username, password, api_key, acc_type=acc_type)
    svc.create_session()
    return svc


def _save_run(strategy_class, symbol, timeframe, result, params,
              strategy_type: str = "swing") -> int:
    trades   = result["trades"]
    win_rate = calc_win_rate(trades)
    profit   = calc_total_profit(trades)
    drawdown = calc_max_drawdown(trades)
    sharpe   = calc_sharpe_ratio(trades)

    row = {
        "strategy_name":    strategy_class.name,
        "symbol":           symbol.upper(),
        "timeframe":        timeframe.upper(),
        "run_at":           datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "candles_total":    result["candles_total"],
        "candles_train":    result["candles_train"],
        "candles_test":     result["candles_test"],
        "total_trades":     len(trades),
        "win_rate":         win_rate,
        "total_profit":     profit,
        "max_drawdown":     drawdown,
        "sharpe_ratio":     sharpe,
        "benchmark_return": result["benchmark_return"],
        "params_json":      json.dumps(params),
        "strategy_type":    strategy_type,
    }
    backtest_id = insert_backtest_result(row)
    insert_backtest_trades([{**t, "backtest_id": backtest_id} for t in trades])
    return backtest_id


def _print_run(strategy_name, symbol, timeframe, result, params, backtest_id=None):
    trades   = result["trades"]
    win_rate = calc_win_rate(trades)
    profit   = calc_total_profit(trades)
    drawdown = calc_max_drawdown(trades)
    sharpe   = calc_sharpe_ratio(trades)
    bench    = result["benchmark_return"]

    id_label = f"  [id={backtest_id}]" if backtest_id else ""
    print(f"  {strategy_name}  params={params}  {symbol} {timeframe}{id_label}")
    print(f"  Candles: total={result['candles_total']}  train={result['candles_train']}  test={result['candles_test']}")
    print(f"  Trades={len(trades)}  WinRate={win_rate*100:.1f}%  Profit=${profit:.2f}  Drawdown=${drawdown:.2f}  Sharpe={sharpe:.3f}")
    print(f"  Benchmark return={bench*100:.2f}%")
    print()


def _print_walk_forward(strategy_name, symbol, timeframe, wf, params):
    print(f"  {strategy_name}  params={params}  {symbol} {timeframe}  [WALK-FORWARD]")
    if wf["shrunk_train"]:
        print(f"  Insufficient data for {WF_TRAIN_MONTHS}mo train / {WF_MIN_WINDOWS}+ windows "
              f"— shrunk train to {wf['train_months_used']}mo")
    print(f"  {len(wf['windows'])} test window(s)\n")
    print(f"  {'Window':<8}{'Test period':<26}{'Trades':<8}{'WR%':<8}{'P&L':<12}{'PF':<8}")
    for i, w in enumerate(wf["windows"], 1):
        period = f"{w['train_end'].date()} -> {w['test_end'].date()}"
        wr = f"{w['win_rate']*100:.1f}"
        pf = f"{w['profit_factor']:.2f}" if w["has_trades"] else "N/A"
        print(f"  {i:<8}{period:<26}{w['trades']:<8}{wr:<8}{w['pnl']:<12.2f}{pf:<8}")
    print()
    print(f"  Median PF:          {wf['median_pf']}")
    print(f"  Windows profitable: {wf['pct_profitable']}%")
    if wf["worst_window"]:
        ww = wf["worst_window"]
        print(f"  Worst window PF:    {ww['profit_factor']:.2f}  "
              f"({ww['train_end'].date()} -> {ww['test_end'].date()})")
    print(f"  Combined P&L:       ${wf['combined_pnl']:.2f}  "
          f"({len(wf['combined_trades'])} trades across all windows)")
    print(f"  VERDICT: {wf['verdict']} — {wf['verdict_reason']}")
    print()


def _cache_fingerprint(candles: list, cache_file: str) -> dict:
    return {
        "cache_file":         cache_file,
        "cache_candle_count": len(candles),
        "cache_date_start":   str(candles[0]["time"]) if candles else None,
        "cache_date_end":     str(candles[-1]["time"]) if candles else None,
    }


def _persist_wf_run(run_type, strategy_name, symbol, timeframe, params, fingerprint,
                    windows=None, verdict=None, median_pf=None, pct_profitable=None,
                    extra=None, params_source=None, prov=None) -> int:
    # params_source rides in extra_json rather than a new column: it is
    # provenance about the run, and walkforward_runs already carries the cache
    # fingerprint there in spirit. A reader checking whether a verdict describes
    # the deployed configuration looks here.
    extra = dict(extra or {})
    extra["params_source"] = params_source
    # Provenance from the engine result, not from the constant. Before
    # 2026-08-22 nothing passed spread_table, so insert_walkforward_run's
    # default hashed None and spread_table_sha was NULL on every row ever
    # written -- the tamper-detection the column exists for did not exist.
    prov = dict(prov or {})
    return insert_walkforward_run({
        **({"engine_version": prov["engine_version"]} if prov.get("engine_version") else {}),
        **({"spread_model": prov["spread_model"]} if prov.get("spread_model") else {}),
        **({"spread_table_sha": prov["spread_table_sha"]} if prov.get("spread_table_sha") else {}),
        "run_type":       run_type,
        "strategy_name":  strategy_name,
        "symbol":         symbol,
        "timeframe":      timeframe,
        "params_json":    json.dumps(params),
        "windows_json":   json.dumps(windows, default=str) if windows is not None else None,
        "verdict":        verdict,
        "median_pf":      median_pf,
        "pct_profitable": pct_profitable,
        "extra_json":     json.dumps(extra, default=str) if extra is not None else None,
        **fingerprint,
    })


def _pf_block(pf: float) -> str:
    if pf >= 1.2:
        return "██"
    if pf >= 1.0:
        return "▓▓"
    return "░░"


def _print_stability_heatmaps(stability: dict) -> None:
    keys = stability["keys"]  # e.g. ["period", "oversold", "overbought"]
    grid = stability["grid"]
    if keys != ["period", "oversold", "overbought"]:
        # Generic fallback — flat cell list, no heatmap layout assumed.
        for cell in stability["cells"]:
            print(f"  {cell['params']}  PF={cell['median_pf']}  {cell['pct_profitable']}% windows")
        return

    periods = grid["period"]
    by_key = {(c["params"]["period"], c["params"]["oversold"], c["params"]["overbought"]): c
              for c in stability["cells"]}

    print(f"\n  Legend: ██ PF>=1.2   ▓▓ PF 1.0-1.2   ░░ PF<1.0\n")
    for overbought in grid["overbought"]:
        for oversold in grid["oversold"]:
            print(f"  overbought={overbought}  oversold={oversold}")
            print(f"  period:   " + "".join(f"{p:>6}" for p in periods))
            row_pf  = "  PF:      "
            row_win = "  windows: "
            for p in periods:
                cell = by_key[(p, oversold, overbought)]
                row_pf  += f"  {_pf_block(cell['median_pf'])}  "
                row_win += f"{cell['pct_profitable']:>5.0f}%"
            print(row_pf)
            print(row_win)
            print()


def _print_plateau_report(plateau: dict) -> None:
    bc, bp = plateau["best_cell"], plateau["best_plateau"]
    print(f"  Best single cell:  {bc['params']}  PF={bc['median_pf']}  "
          f"neighbor_avg={bc['neighbor_avg_pf']}")
    if bp:
        print(f"  Best PLATEAU:      {bp['params']}  PF={bp['median_pf']}  "
              f"neighbor_avg={bp['neighbor_avg_pf']}  <- recommended over best single cell")
    if plateau["spike_flag"]:
        print(f"  ⚠️  SPIKE flag: best cell's neighbors average PF < 1.0 — "
              f"isolated result, overfit signature")
    print()


def _print_clusters(clusters: list) -> None:
    if not clusters:
        print("  No contiguous region with median PF >= threshold found.\n")
        return
    print(f"  {len(clusters)} region(s) found (largest first):")
    for i, c in enumerate(clusters, 1):
        print(f"  Region {i}: size={c['size']} cells, center={c['center_params']}, "
              f"center PF={c['center_cell']['median_pf']}")
    print()


def _print_mc(mc: dict) -> None:
    if "error" in mc:
        print(f"  MC error: {mc['error']}\n")
        return
    print(f"  Bootstrap MC: {mc['n_iter']} iterations, {mc['n_trades']} trades/path, "
          f"${mc['account']:.0f} account, ${mc['risk_per_trade']:.0f} risk/trade")
    print(f"  P&L    p5={mc['pnl_p5']:.2f}  p25={mc['pnl_p25']:.2f}  median={mc['pnl_median']:.2f}  "
          f"p75={mc['pnl_p75']:.2f}  p95={mc['pnl_p95']:.2f}")
    print(f"  MaxDD  p5={mc['dd_p5']:.2f}  p25={mc['dd_p25']:.2f}  median={mc['dd_median']:.2f}  "
          f"p75={mc['dd_p75']:.2f}  p95={mc['dd_p95']:.2f}")
    print(f"  RISK OF RUIN (drawdown > ${mc['ruin_threshold_dollars']:.0f}): {mc['risk_of_ruin_pct']}%")
    print()


def _print_permutation(perm: dict) -> None:
    print(f"  Real median PF: {perm['real_median_pf']}  ({perm['real_verdict']})")
    print(f"  Synthetic (noise) median PF, {perm['n_iter']} runs: {perm['synthetic_pf_median']}")
    print(f"  Real result percentile vs synthetic distribution: {perm['percentile']}%")
    verdict = "EDGE CONFIRMED (>95th percentile)" if perm["edge_confirmed"] else "NOT DISTINGUISHABLE FROM NOISE (<=95th percentile)"
    print(f"  {verdict}")
    print()


def main():
    from database.db import init_db
    init_db()  # idempotent — ensures walkforward_runs (and any other pending migration) exists

    parser = argparse.ArgumentParser(description="Run strategy backtest against IG historical data.")
    parser.add_argument("--symbol",    required=True,       help="US500 | US100 | BTC")
    parser.add_argument("--timeframe", required=True,       help="MINUTE | HOUR | DAY")
    parser.add_argument("--strategy",  required=True,       help="rsi | supertrend")
    parser.add_argument("--count",     type=int, default=500, help="Number of candles to fetch (default: 500)")
    parser.add_argument("--sweep",         action="store_true", help="Run full parameter sweep")
    parser.add_argument("--cache",         action="store_true", help="Cache candles to disk; load if fresh (<24h)")
    parser.add_argument("--refresh-cache", action="store_true", help="Force re-fetch even if cache exists")
    parser.add_argument("--source",         default="ig", choices=["ig", "yfinance", "alphavantage", "ig_cache"],
                        help="Data source: ig (default), yfinance, alphavantage (cached, 2yr 15MIN), or ig_cache (self-collected)")
    parser.add_argument("--type",           default="swing", choices=["swing", "daytrading"],
                        help="Strategy type label stored in DB (default: swing)")
    parser.add_argument("--session-filter", default=None, choices=["US", "24_7"],
                        help="Only generate signals during session: US (market hours) or 24_7")
    parser.add_argument("--max-hold",       type=int, default=None,
                        help="Force-close trades after N candles (e.g. 78 = one US day at 5MIN)")
    parser.add_argument("--walk-forward",   action="store_true",
                        help="Rolling walk-forward validation (train=6mo/test=1mo/step=1mo, "
                             "shrinks to 4mo train if <4 windows) instead of the 80/20 split")
    parser.add_argument("--stability-map",  action="store_true",
                        help="Full walk-forward across a parameter grid (STABILITY_GRIDS) instead "
                             "of a single param set — per-cell PF/window%%, plateau/spike analysis, "
                             "contiguous-region clusters")
    parser.add_argument("--monte-carlo",    action="store_true",
                        help="Bootstrap trade-sequence resampling. Standalone: strategy's default "
                             "params. Combined with --stability-map: auto-applies to top-N plateau cells")
    parser.add_argument("--permutation",    action="store_true",
                        help="Masters-method permutation test — shuffle log returns to destroy price "
                             "structure, compare real result's percentile vs the synthetic distribution")
    parser.add_argument("--mc-iter",   type=int, default=1000, help="Monte Carlo iterations (default 1000)")
    parser.add_argument("--perm-iter", type=int, default=200,  help="Permutation test iterations (default 200)")
    parser.add_argument("--cluster-threshold", type=float, default=1.1,
                        help="Min median PF for a stability-map cell to count toward cluster regions")
    parser.add_argument("--top-n", type=int, default=5,
                        help="Top plateau cells to auto-MC when --stability-map + --monte-carlo")
    parser.add_argument("--from-roster", action="store_true",
                        help="Take params from active_strategy for this (symbol,timeframe,strategy). "
                             "REQUIRED for any run that will be used as promotion evidence — "
                             "see findings doc finding 28.")
    parser.add_argument("--roster-db", default=None,
                        help="Path to the DB whose active_strategy is authoritative. "
                             "REQUIRED IN PRACTICE with --from-roster: the roster lives on "
                             "the VPS, and the local DB carries phantom rows. See finding 28.")
    parser.add_argument("--params", default=None,
                        help="Literal params as JSON, e.g. '{\"period\": 21}'. For exploration. "
                             "Mutually exclusive with --from-roster.")
    args = parser.parse_args()

    strategy_key = args.strategy.lower()
    if strategy_key not in STRATEGIES:
        print(f"Unknown strategy '{args.strategy}'. Available: {list(STRATEGIES)}")
        sys.exit(1)

    strategy_class = STRATEGIES[strategy_key]

    # --- parameter resolution -------------------------------------------------
    #
    # findings doc finding 28: until 2026-08-22 there was no way to express the
    # rostered configuration here, so walk-forward, Monte Carlo and permutation
    # all silently ran strategy_class() file defaults. GBPUSD 15MIN williams_r is
    # rostered period=21 against a class default of 14 — validating it without
    # this produced a verdict for a strategy that has never traded.
    #
    # Provenance travels with the result. `params_source` is persisted on every
    # walkforward_runs row so a reader can tell a roster-validated verdict from
    # an exploratory one without re-deriving it.
    if args.from_roster and args.params:
        print("--from-roster and --params are mutually exclusive.")
        sys.exit(1)

    cli_params = None
    params_source = "file-defaults"
    if args.from_roster:
        if args.roster_db:
            # Read the authoritative roster directly rather than through
            # database.db, whose DATABASE_PATH is per-host. Read-only URI: a
            # validation run must never write to the production DB it is
            # reading the roster out of.
            _rconn = sqlite3.connect(f"file:{args.roster_db}?mode=ro", uri=True)
            _rconn.row_factory = sqlite3.Row
            try:
                _r = _rconn.execute(
                    "SELECT * FROM active_strategy WHERE symbol=? AND timeframe=? "
                    "AND strategy_name=? LIMIT 1",
                    (args.symbol.upper(), args.timeframe.upper(), strategy_key)).fetchone()
                row = dict(_r) if _r else None
            finally:
                _rconn.close()
            print(f"[params] roster source: {args.roster_db}")
        else:
            print("[params] ⚠️  --from-roster without --roster-db reads THIS HOST's DB. "
                  "The local dev DB carries 3 phantom active_strategy rows that match no "
                  "deployed strategy (finding 28) — a run can succeed and silently validate "
                  "a fiction. Pass --roster-db pointing at a copy of the VPS database.")
            row = get_roster_row(args.symbol.upper(), args.timeframe.upper(), strategy_key)
        if row is None:
            print(f"--from-roster: no active_strategy row for "
                  f"({args.symbol.upper()}, {args.timeframe.upper()}, {strategy_key}). "
                  f"Refusing to fall back to file defaults — that is the bug this flag exists "
                  f"to prevent (findings doc finding 28).")
            sys.exit(1)
        raw = row.get("params_json")
        if not raw:
            print(f"--from-roster: active_strategy id={row.get('id')} has params_json NULL. "
                  f"Nothing to validate against. Refusing to guess.")
            sys.exit(1)
        cli_params = json.loads(raw) if isinstance(raw, str) else raw
        params_source = f"roster:active_strategy.id={row.get('id')}"
        print(f"[params] from roster: active_strategy id={row.get('id')} "
              f"status={row.get('status')!r} -> {cli_params}")
    elif args.params:
        cli_params = json.loads(args.params)
        params_source = "cli-literal"
        print(f"[params] literal from --params: {cli_params}")
    else:
        print(f"[params] ⚠️  FILE DEFAULTS ({strategy_class(params=None).params}). "
              f"NOT roster-validated — do not use this run as promotion evidence. "
              f"Pass --from-roster for that.")

    candles = None
    if args.source == "alphavantage":
        print(f"Loading {args.symbol} {args.timeframe} candles from Alpha Vantage cache...")
        candles = _load_alphavantage_candles(args.symbol, args.timeframe)[-args.count:]
        print(f"Loaded {len(candles)} candles.")
    elif args.source == "ig_cache":
        print(f"Loading {args.symbol} {args.timeframe} candles from IG-collected cache...")
        candles = _load_ig_cache_candles(args.symbol, args.timeframe)[-args.count:]
        print(f"Loaded {len(candles)} candles.")
    elif args.cache and not args.refresh_cache:
        candles = _load_cache(args.symbol, args.timeframe, args.count, args.source)
        if candles:
            print(f"Loaded {len(candles)} candles from cache ({args.symbol} {args.timeframe} {args.count} [{args.source}]).")

    if candles is None:
        if args.source == "yfinance":
            print(f"Fetching {args.count} {args.timeframe} candles for {args.symbol} via yfinance...")
            candles = _fetch_yfinance_candles(args.symbol, args.timeframe, args.count)
        else:
            print(f"Connecting to IG Markets...")
            ig = create_ig_session()
            print(f"Session created.")
            print(f"Fetching {args.count} {args.timeframe} candles for {args.symbol}...")
            candles = fetch_candles(ig, args.symbol, args.timeframe, args.count)
        print(f"Fetched {len(candles)} candles.")
        if args.cache or args.refresh_cache:
            _save_cache(args.symbol, args.timeframe, args.count, candles, args.source)
            print(f"Saved to cache.")
    print()

    cache_file_name = {
        "alphavantage": f"{args.symbol.upper()}_{args.timeframe.upper()}_AV.json",
        "ig_cache":     f"{args.symbol.upper()}_{args.timeframe.upper()}_IG.json",
    }.get(args.source, _cache_path(args.symbol, args.timeframe, args.count, args.source).name)
    fingerprint = _cache_fingerprint(candles, cache_file_name)

    if args.stability_map:
        # NOTE: a line here used to read `engine_mod.RISK_PER_TRADE = 10.0`.
        # It was DEAD as of parity-v1, which removed engine.py's module-level
        # RISK_PER_TRADE literal and moved sizing to
        # risk_manager.get_risk_per_trade(symbol) — so the assignment merely
        # created an attribute nothing reads, while reading as though risk were
        # being configured here. Removed 2026-08-22. Per-symbol risk now comes
        # from RISK_PER_TRADE_OVERRIDE via the engine's own sizing path.
        if strategy_key not in STABILITY_GRIDS:
            # A missing grid must never read as "the stability stage passed".
            # Persist an explicit REDUCED_GAUNTLET marker row so the absence is
            # a positive record rather than a silent gap — same reasoning as
            # the marker test in CLAUDE.md's Unverified Controls. A reader
            # querying walkforward_runs for this strategy now finds a row that
            # says the stage was deliberately not run, and why.
            print(f"No STABILITY_GRIDS entry for '{strategy_key}'. Available: {list(STABILITY_GRIDS)}")
            print("Recording a REDUCED_GAUNTLET marker row rather than exiting silently.")
            _persist_wf_run("stability_map", strategy_class.name, args.symbol, args.timeframe,
                            cli_params if cli_params is not None else {}, fingerprint,
                            verdict="REDUCED_GAUNTLET",
                            extra={"reason": "no STABILITY_GRIDS entry for this strategy",
                                   "stage_skipped": "stability_map",
                                   "available_grids": sorted(STABILITY_GRIDS)},
                            params_source=params_source, prov=provenance())
            sys.exit(1)
        grid = STABILITY_GRIDS[strategy_key]
        combos = 1
        for v in grid.values():
            combos *= len(v)
        print(f"Sweep size: {combos} cells x full walk-forward each — {strategy_key} {args.symbol} {args.timeframe}")
        print(f"Grid: {grid}\n")

        stability = run_stability_map(strategy_class, candles, args.symbol, grid,
                                      max_hold_candles=args.max_hold, session_filter=args.session_filter)
        _print_stability_heatmaps(stability)

        plateau = compute_plateau_metrics(stability)
        _print_plateau_report(plateau)

        clusters = find_clusters(stability, threshold=args.cluster_threshold)
        _print_clusters(clusters)

        for cell in stability["cells"]:
            _persist_wf_run("stability_map", strategy_class.name, args.symbol, args.timeframe,
                            cell["params"], fingerprint,
                            verdict=cell["verdict"], median_pf=cell["median_pf"],
                            pct_profitable=cell["pct_profitable"],
                            extra={"neighbor_avg_pf": cell.get("neighbor_avg_pf")},
                            params_source="stability-grid", prov=stability)
        print(f"Persisted {len(stability['cells'])} cells to walkforward_runs.")

        if args.monte_carlo:
            ranked = sorted((c for c in stability["cells"] if c.get("neighbor_avg_pf") is not None),
                            key=lambda c: c["neighbor_avg_pf"], reverse=True)[:args.top_n]
            print(f"\nAuto Monte Carlo on top-{len(ranked)} plateau cells "
                  f"(MC every parameter set, not just one):\n")
            for cell in ranked:
                print(f"  {cell['params']}  (plateau neighbor_avg={cell['neighbor_avg_pf']})")
                mc = bootstrap_mc(cell["combined_trades"], n_iter=args.mc_iter,
                                  engine_version=stability.get("engine_version"))
                _print_mc(mc)
                _persist_wf_run("monte_carlo", strategy_class.name, args.symbol, args.timeframe,
                                cell["params"], fingerprint, extra=mc,
                                params_source="stability-grid", prov=stability)
        return

    if args.monte_carlo and not args.walk_forward:
        params = cli_params if cli_params is not None else strategy_class().params
        wf = run_walk_forward(strategy_class, candles, args.symbol, params=params,
                              max_hold_candles=args.max_hold, session_filter=args.session_filter)
        print(f"Base walk-forward: median PF={wf['median_pf']}  verdict={wf['verdict']}\n")
        mc = bootstrap_mc(wf["combined_trades"], n_iter=args.mc_iter,
                          engine_version=wf.get("engine_version"))
        _print_mc(mc)
        _persist_wf_run("monte_carlo", strategy_class.name, args.symbol, args.timeframe,
                        params, fingerprint, verdict=wf["verdict"], median_pf=wf["median_pf"],
                        pct_profitable=wf["pct_profitable"], extra=mc,
                        params_source=params_source, prov=wf)
        if not args.permutation:
            return

    if args.permutation:
        params = cli_params if cli_params is not None else strategy_class().params
        print(f"Permutation test ({args.perm_iter} synthetic runs)...\n")
        perm = permutation_test(strategy_class, candles, args.symbol, params, n_iter=args.perm_iter,
                                max_hold_candles=args.max_hold, session_filter=args.session_filter)
        _print_permutation(perm)
        _persist_wf_run("permutation", strategy_class.name, args.symbol, args.timeframe,
                        params, fingerprint, verdict=perm["real_verdict"],
                        median_pf=perm["real_median_pf"], extra=perm,
                        params_source=params_source, prov=perm)
        return

    if args.walk_forward:
        if args.sweep:
            param_grid = PARAM_GRIDS[strategy_key]
            combos = 1
            for v in param_grid.values():
                combos *= len(v)
            print(f"Running walk-forward parameter sweep ({combos} combinations): {param_grid}\n")
            keys = list(param_grid.keys())
            for combo in itertools.product(*param_grid.values()):
                params = dict(zip(keys, combo))
                wf = run_walk_forward(strategy_class, candles, args.symbol, params=params,
                                      max_hold_candles=args.max_hold, session_filter=args.session_filter)
                _print_walk_forward(strategy_class.name, args.symbol, args.timeframe, wf, params)
                _persist_wf_run("walk_forward", strategy_class.name, args.symbol, args.timeframe,
                                params, fingerprint, windows=wf["windows"], verdict=wf["verdict"],
                                median_pf=wf["median_pf"], pct_profitable=wf["pct_profitable"],
                                params_source="param-sweep-grid", prov=wf)
            print(f"Overfitting reminder: {combos} parameter combinations were walk-forward "
                  f"tested. Even walk-forward results can overfit across a wide sweep — "
                  f"treat top results as candidates, not conclusions.")
        else:
            params = cli_params if cli_params is not None else strategy_class().params
            wf = run_walk_forward(strategy_class, candles, args.symbol, params=params,
                                  max_hold_candles=args.max_hold, session_filter=args.session_filter)
            _print_walk_forward(strategy_class.name, args.symbol, args.timeframe, wf, params)
            _persist_wf_run("walk_forward", strategy_class.name, args.symbol, args.timeframe,
                            params, fingerprint, windows=wf["windows"], verdict=wf["verdict"],
                            median_pf=wf["median_pf"], pct_profitable=wf["pct_profitable"],
                            params_source=params_source, prov=wf)
        return

    if args.sweep:
        param_grid = PARAM_GRIDS[strategy_key]
        combos = 1
        for v in param_grid.values():
            combos *= len(v)
        print(f"Running parameter sweep ({combos} combinations): {param_grid}\n")

        sweep_results = run_parameter_sweep(
            strategy_class, candles, args.symbol, param_grid,
            max_hold_candles=args.max_hold,
            session_filter=args.session_filter,
        )

        for r in sweep_results:
            params = r["params"]
            bid = _save_run(strategy_class, args.symbol, args.timeframe, r, params,
                            strategy_type=args.type)
            _print_run(strategy_class.name, args.symbol, args.timeframe, r, params, bid)

        print(f"Saved {len(sweep_results)} runs to database.")
        print(f"Overfitting reminder: {combos} parameter combinations were tested in this "
              f"sweep. Best-looking result may be due to chance — validate promising "
              f"candidates out-of-sample (e.g. --walk-forward) before promoting.")
    else:
        strategy = strategy_class()
        params   = strategy.params
        print(f"Running single backtest with params={params}\n")

        result = run_backtest(strategy, candles, args.symbol,
                              max_hold_candles=args.max_hold,
                              session_filter=args.session_filter)
        bid    = _save_run(strategy_class, args.symbol, args.timeframe, result, params,
                           strategy_type=args.type)
        _print_run(strategy_class.name, args.symbol, args.timeframe, result, params, bid)
        print(f"Saved to database (backtest_id={bid}).")


if __name__ == "__main__":
    main()
