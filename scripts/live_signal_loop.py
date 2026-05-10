#!/usr/bin/env python3
"""
Phase 6 — Live signal loop.
Every HOUR: fetch candles → run active strategy → execute if signal fires.
Paper trade mode: set PAPER_TRADE_SYMBOLS=DAX,US100_5MIN in .env.
"""
import os
import sys
import time
import json
import logging
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.run_backtest import _fetch_yfinance_candles, STRATEGIES
from database.models import get_active_strategy
from bot.execute_trade import place_trade

LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "signal_loop.log"
LOG_PATH.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s UTC [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_PATH),
    ],
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

SYMBOLS = ["US500", "US100", "DAX"]
CANDLE_COUNT = 100

# UTC hour at which no new trades are opened (0 = always open)
MARKET_CLOSE_UTC: dict[str, int] = {
    "US500": 21,
    "US100": 21,
    "DAX":   16,
    "BTC":    0,
}

POLL_INTERVAL_SECONDS = 3600

_paper_raw = os.getenv("PAPER_TRADE_SYMBOLS", "")
PAPER_SYMBOLS: set[str] = {s.strip() for s in _paper_raw.split(",") if s.strip()}

_last_signal: dict[str, str] = {}


def _is_market_open(symbol: str) -> bool:
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5 and symbol in ("US500", "US100", "DAX"):
        return False
    close_hour = MARKET_CLOSE_UTC.get(symbol, 0)
    if close_hour and now.hour >= close_hour:
        return False
    return True


def _compute_atr(candles: list, period: int = 14) -> float | None:
    if len(candles) < period + 1:
        return None
    trs = []
    for i in range(1, len(candles)):
        h  = candles[i]["high"]
        l  = candles[i]["low"]
        pc = candles[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period


def _run_symbol(symbol: str, row: dict) -> None:
    strat_name = row["strategy_name"]
    timeframe  = row["timeframe"]
    params     = json.loads(row["params_json"])
    loop_key   = f"{symbol}_{timeframe}"

    if strat_name not in STRATEGIES:
        log.warning(f"{symbol}: strategy '{strat_name}' not in registry")
        return

    log.info(f"{symbol} | strategy={strat_name} tf={timeframe}")

    try:
        candles = _fetch_yfinance_candles(symbol, timeframe, CANDLE_COUNT)
    except Exception as e:
        log.error(f"{symbol}: candle fetch failed — {e}")
        return

    strat   = STRATEGIES[strat_name](**params)
    signals = strat.generate_signals(candles)

    if not signals:
        log.info(f"{symbol}: no signals generated")
        return

    direction = signals[-1]["signal"]  # BUY | SELL | NONE
    log.info(f"{symbol}: latest signal = {direction}")

    if direction == "NONE":
        _last_signal[loop_key] = "NONE"
        return

    if _last_signal.get(loop_key) == direction:
        log.info(f"{symbol}: duplicate {direction} — skip")
        return

    if not _is_market_open(symbol):
        log.info(f"{symbol}: market closed — skip {direction}")
        return

    atr = _compute_atr(candles)
    if atr is None:
        log.warning(f"{symbol}: ATR unavailable — skip trade")
        return

    close   = candles[-1]["close"]
    sl_dist = round(atr * 1.5, 2)
    tp_dist = round(atr * 2.5, 2)

    if direction == "BUY":
        sl = round(close - sl_dist, 2)
        tp = round(close + tp_dist, 2)
    else:
        sl = round(close + sl_dist, 2)
        tp = round(close - tp_dist, 2)

    paper_key = symbol if timeframe == "HOUR" else f"{symbol}_{timeframe}"
    is_paper  = paper_key in PAPER_SYMBOLS

    if is_paper:
        log.info(f"[PAPER] {symbol} {direction} | close={close} sl={sl} tp={tp} atr={atr:.2f}")
        _last_signal[loop_key] = direction
        return

    log.info(f"{symbol}: placing {direction} | close={close} sl={sl} tp={tp}")
    try:
        place_trade(
            symbol=symbol,
            action=direction.lower(),
            sl=sl,
            tp=tp,
            strategy_name=strat_name,
            source="live_signal_loop",
        )
        _last_signal[loop_key] = direction
    except Exception as e:
        log.error(f"{symbol}: place_trade failed — {e}")


def main() -> None:
    log.info(f"Live signal loop starting | symbols={SYMBOLS} | paper={PAPER_SYMBOLS or 'none'}")

    while True:
        cycle_start = time.monotonic()
        log.info("--- hourly cycle ---")

        for symbol in SYMBOLS:
            rows = get_active_strategy(symbol=symbol)
            if not rows:
                log.info(f"{symbol}: no active strategy — skip")
                continue
            if isinstance(rows, dict):
                rows = [rows]
            for row in rows:
                try:
                    _run_symbol(symbol, row)
                except Exception as e:
                    log.error(f"{symbol}: unexpected error — {e}")
            time.sleep(1)

        elapsed   = time.monotonic() - cycle_start
        sleep_for = max(0, POLL_INTERVAL_SECONDS - elapsed)
        log.info(f"Cycle done in {elapsed:.1f}s. Sleeping {sleep_for:.0f}s.")
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()
