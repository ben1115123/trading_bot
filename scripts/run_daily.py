#!/usr/bin/env python3
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.run_backtest import (
    _fetch_yfinance_candles, _save_cache, _save_run,
    STRATEGIES, PARAM_GRIDS,
)
from backend.backtesting.engine import run_parameter_sweep
from scripts.score_strategies import score_strategies
from scripts.select_strategy import select_strategy

SYMBOLS      = ["US500", "US100", "BTC"]
CANDLE_COUNT = 2000
TIMEFRAME    = "HOUR"

LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "daily_run.log"


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG_PATH.parent.mkdir(exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")


def main() -> None:
    log("=== Daily run starting ===")
    total_runs         = 0
    strategies_updated = 0
    errors             = 0

    # ── A+B: fetch candles + sweep all strategies per symbol ──────────────────
    candles_by_symbol: dict = {}

    for symbol in SYMBOLS:
        log(f"Fetching {CANDLE_COUNT} {TIMEFRAME} candles for {symbol}...")
        try:
            candles = _fetch_yfinance_candles(symbol, TIMEFRAME, CANDLE_COUNT)
            _save_cache(symbol, TIMEFRAME, CANDLE_COUNT, candles, "yfinance")
            candles_by_symbol[symbol] = candles
            log(f"  {symbol}: {len(candles)} candles fetched and cached")
        except Exception as e:
            log(f"  ERROR fetching {symbol}: {e}")
            errors += 1

    for symbol, candles in candles_by_symbol.items():
        for strat_name, strat_cls in STRATEGIES.items():
            if strat_name not in PARAM_GRIDS:
                continue
            try:
                results = run_parameter_sweep(
                    strat_cls, candles, symbol, PARAM_GRIDS[strat_name]
                )
                for r in results:
                    _save_run(strat_cls, symbol, TIMEFRAME, r, r["params"], "swing")
                total_runs += len(results)
                log(f"  {symbol} {strat_name}: {len(results)} runs saved")
            except Exception as e:
                log(f"  ERROR {symbol} {strat_name}: {e}")
                errors += 1

    # ── C: score ──────────────────────────────────────────────────────────────
    log("Scoring strategies...")
    try:
        eligible = score_strategies()
        log(f"  {len(eligible)} eligible strategies found")
    except Exception as e:
        log(f"  ERROR scoring: {e}")
        errors += 1

    # ── D: select ─────────────────────────────────────────────────────────────
    log("Selecting active strategies per symbol...")
    try:
        results = select_strategy()
        strategies_updated = sum(1 for v in results.values() if v is not None)
        log(f"  {strategies_updated}/3 symbols updated")
    except Exception as e:
        log(f"  ERROR selecting: {e}")
        errors += 1

    log(
        f"=== Daily run complete — {total_runs} backtests run, "
        f"{strategies_updated} strategies updated, {errors} errors ==="
    )


if __name__ == "__main__":
    main()
