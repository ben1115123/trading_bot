#!/usr/bin/env python3
"""
CLI entry point for Phase 3 backtesting.

Usage:
  python scripts/run_backtest.py --symbol US500 --timeframe HOUR --strategy rsi --count 500
  python scripts/run_backtest.py --symbol BTC --timeframe DAY --strategy supertrend --count 500 --sweep
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CACHE_DIR = Path(__file__).resolve().parent / "candle_cache"
CACHE_MAX_AGE_SECONDS = 86400  # 24 hours

YF_SYMBOLS   = {"US500": "^GSPC", "US100": "^NDX", "BTC": "BTC-USD"}
YF_INTERVALS = {"5MIN": "5m", "HOUR": "1h", "DAY": "1d"}
YF_PERIODS   = {"5m": "60d", "1h": "730d", "1d": "5y"}


def _fetch_yfinance_candles(symbol: str, timeframe: str, count: int) -> list:
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
        candles.append({"time": str(ts), "open": o, "high": h, "low": l, "close": c})
    return candles[-count:]


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

from backend.backtesting.engine import fetch_candles, run_backtest, run_parameter_sweep
from backend.backtesting.metrics import (
    calc_win_rate, calc_max_drawdown, calc_sharpe_ratio, calc_total_profit,
)
from backend.strategies.rsi import RSIStrategy
from backend.strategies.supertrend import SuperTrendStrategy
from backend.strategies.vwap_ema import VWAPEMAStrategy
from backend.strategies.ema_ribbon import EMARibbonStrategy
from backend.strategies.bb_squeeze import BBSqueezeStrategy
from backend.strategies.rsi_divergence import RSIDivergenceStrategy
from backend.strategies.orb import ORBStrategy
from database.models import insert_backtest_result, insert_backtest_trade

STRATEGIES = {
    "rsi":        RSIStrategy,
    "supertrend": SuperTrendStrategy,
    "vwap_ema":   VWAPEMAStrategy,
    "ema_ribbon":  EMARibbonStrategy,
    "bb_squeeze":     BBSqueezeStrategy,
    "rsi_divergence": RSIDivergenceStrategy,
    "orb":            ORBStrategy,
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
}


def create_ig_session() -> IGService:
    username = os.getenv("IG_USERNAME")
    password = os.getenv("IG_PASSWORD")
    api_key  = os.getenv("IG_API_KEY")
    svc = IGService(username, password, api_key, acc_type="LIVE")
    svc.create_session()
    return svc


def _save_run(strategy_class, symbol, timeframe, result, params) -> int:
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
    }
    backtest_id = insert_backtest_result(row)
    for t in trades:
        insert_backtest_trade({**t, "backtest_id": backtest_id})
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


def main():
    parser = argparse.ArgumentParser(description="Run strategy backtest against IG historical data.")
    parser.add_argument("--symbol",    required=True,       help="US500 | US100 | BTC")
    parser.add_argument("--timeframe", required=True,       help="MINUTE | HOUR | DAY")
    parser.add_argument("--strategy",  required=True,       help="rsi | supertrend")
    parser.add_argument("--count",     type=int, default=500, help="Number of candles to fetch (default: 500)")
    parser.add_argument("--sweep",         action="store_true", help="Run full parameter sweep")
    parser.add_argument("--cache",         action="store_true", help="Cache candles to disk; load if fresh (<24h)")
    parser.add_argument("--refresh-cache", action="store_true", help="Force re-fetch even if cache exists")
    parser.add_argument("--source",        default="ig", choices=["ig", "yfinance"],
                        help="Data source: ig (default) or yfinance (free, no API limit)")
    args = parser.parse_args()

    strategy_key = args.strategy.lower()
    if strategy_key not in STRATEGIES:
        print(f"Unknown strategy '{args.strategy}'. Available: {list(STRATEGIES)}")
        sys.exit(1)

    strategy_class = STRATEGIES[strategy_key]

    candles = None
    if args.cache and not args.refresh_cache:
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

    if args.sweep:
        param_grid = PARAM_GRIDS[strategy_key]
        combos = 1
        for v in param_grid.values():
            combos *= len(v)
        print(f"Running parameter sweep ({combos} combinations): {param_grid}\n")

        sweep_results = run_parameter_sweep(strategy_class, candles, args.symbol, param_grid)

        for r in sweep_results:
            params = r["params"]
            bid = _save_run(strategy_class, args.symbol, args.timeframe, r, params)
            _print_run(strategy_class.name, args.symbol, args.timeframe, r, params, bid)

        print(f"Saved {len(sweep_results)} runs to database.")
    else:
        strategy = strategy_class()
        params   = strategy.params
        print(f"Running single backtest with params={params}\n")

        result = run_backtest(strategy, candles, args.symbol)
        bid    = _save_run(strategy_class, args.symbol, args.timeframe, result, params)
        _print_run(strategy_class.name, args.symbol, args.timeframe, result, params, bid)
        print(f"Saved to database (backtest_id={bid}).")


if __name__ == "__main__":
    main()
