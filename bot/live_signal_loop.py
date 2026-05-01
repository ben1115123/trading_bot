#!/usr/bin/env python3
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.run_backtest import _fetch_yfinance_candles, STRATEGIES
from database.models import get_active_strategy, log_signal_check

SYMBOLS = ["US500", "US100", "BTC"]

MARKET_CLOSE_UTC = {
    "US500": 20,
    "US100": 20,
    "BTC":   None,
}

TIMEFRAME_SECONDS: dict[str, int] = {"5MIN": 300, "HOUR": 3600, "DAY": 86400}

_last_signal: dict[str, str] = {}
_last_checked: dict[str, datetime] = {}


def _is_due(symbol: str, timeframe: str) -> bool:
    interval = TIMEFRAME_SECONDS.get(timeframe, 3600)
    last = _last_checked.get(symbol)
    if last is None:
        return True
    return (datetime.now(timezone.utc) - last).total_seconds() >= interval * 0.9


def _is_blocked(symbol: str) -> bool:
    close_hour = MARKET_CLOSE_UTC.get(symbol)
    if close_hour is None:
        return False
    now = datetime.now(timezone.utc)
    if now.hour >= close_hour:
        return True
    # Extra block on Friday — no new trades after 19:45
    if now.weekday() == 4 and now.hour >= 19 and now.minute >= 45:
        return True
    return False


def _should_weekend_close() -> bool:
    now = datetime.now(timezone.utc)
    # Friday between 20:40 and 21:00 UTC
    return now.weekday() == 4 and now.hour == 20 and now.minute >= 40


def _weekend_close_positions() -> None:
    print("[signal_loop] Friday close — closing all US500/US100 positions")
    from bot.execute_trade import ig_service, ensure_session
    try:
        ensure_session()
        positions = ig_service.fetch_open_positions()
        if positions is None or positions.empty:
            print("[signal_loop] No open positions to close")
            return
        for _, pos in positions.iterrows():
            epic = pos.get("epic", "")
            if any(k in epic for k in ["SPTRD", "NASDAQ"]):
                deal_id   = pos.get("dealId")
                direction = "SELL" if pos.get("direction") == "BUY" else "BUY"
                size      = pos.get("size")
                expiry    = pos.get("expiry", "-")
                ig_service.close_open_position(
                    deal_id=deal_id,
                    direction=direction,
                    epic=epic,
                    expiry=expiry,
                    level=None,
                    order_type="MARKET",
                    quote_id=None,
                    size=size,
                )
                print(f"[signal_loop] Closed {deal_id} ({epic})")
    except Exception as e:
        print(f"[signal_loop] Weekend close error: {e}")


def _check_symbol(symbol: str, active: dict) -> None:
    strategy_name = active["strategy_name"]
    timeframe     = active.get("timeframe", "HOUR")
    params_json   = active.get("params_json") or "{}"
    params        = json.loads(params_json) if isinstance(params_json, str) else params_json

    log_data: dict = {
        "symbol":        symbol,
        "strategy_name": strategy_name,
        "timeframe":     timeframe,
        "candle_time":   None,
        "signal":        "NONE",
        "trade_placed":  0,
        "error":         None,
    }

    if _is_blocked(symbol):
        print(f"[signal_loop] [{symbol}] blocked — near market close")
        log_data["signal"] = "BLOCKED"
        log_data["error"]  = "near market close"
        log_signal_check(log_data)
        return

    try:
        candles = _fetch_yfinance_candles(symbol, timeframe, 500)
    except Exception as e:
        print(f"[signal_loop] [{symbol}] candle fetch failed: {e}")
        log_data["error"] = f"candle fetch error: {e}"
        log_signal_check(log_data)
        return

    strat_cls = STRATEGIES.get(strategy_name)
    if strat_cls is None:
        print(f"[signal_loop] [{symbol}] Unknown strategy: {strategy_name} — skipping")
        return

    try:
        signals = strat_cls(params=params).generate_signals(candles)
    except Exception as e:
        print(f"[signal_loop] [{symbol}] generate_signals failed: {e}")
        log_data["error"] = f"signal generation error: {e}"
        log_signal_check(log_data)
        return

    if not signals or len(signals) < 2:
        log_signal_check(log_data)
        return

    # Use candles[-2] — last completed candle; [-1] is the in-progress current candle
    sig         = signals[-2]
    candle      = candles[-2]
    signal      = sig.get("signal", "NONE")
    candle_time = str(candle.get("time", ""))
    dedup_key   = f"{symbol}_{signal}_{candle_time}"

    log_data["signal"]      = signal
    log_data["candle_time"] = candle_time

    if signal not in ("BUY", "SELL"):
        print(f"[signal_loop] [{symbol}] signal={signal} — no trade")
        log_signal_check(log_data)
        return

    if _last_signal.get(symbol) == dedup_key:
        print(f"[signal_loop] [{symbol}] duplicate {signal} for {candle_time} — skipping")
        log_signal_check(log_data)
        return

    _last_signal[symbol] = dedup_key

    # SL/TP from candle range — matches backtesting engine's sl_dist = high - low
    sl_dist = candle["high"] - candle["low"]
    entry   = candle["close"]
    if signal == "BUY":
        action = "buy"
        sl     = round(entry - sl_dist, 4)
        tp     = round(entry + sl_dist * 2, 4)
    else:
        action = "sell"
        sl     = round(entry + sl_dist, 4)
        tp     = round(entry - sl_dist * 2, 4)

    print(f"[signal_loop] [{symbol}] {signal} — sl={sl} tp={tp}")

    from bot.execute_trade import place_trade
    try:
        result = place_trade(
            symbol, action, sl=sl, tp=tp,
            strategy_name=strategy_name,
            source="live_signal_loop",
        )
        placed = 1 if result else 0
        log_data["trade_placed"] = placed
        if not result:
            log_data["error"] = "place_trade returned False"
        print(f"[signal_loop] [{symbol}] trade placed={placed}")
    except Exception as e:
        log_data["error"] = f"place_trade error: {e}"
        print(f"[signal_loop] [{symbol}] place_trade error: {e}")

    log_signal_check(log_data)


def _loop() -> None:
    print("[signal_loop] Starting signal loop (5-min wake, timeframe-aware)")
    while True:
        now = datetime.now(timezone.utc)
        print(f"\n[signal_loop] === Cycle at {now.strftime('%Y-%m-%d %H:%M:%S UTC')} ===")

        if _should_weekend_close():
            _weekend_close_positions()

        for symbol in SYMBOLS:
            active = get_active_strategy(symbol=symbol)
            if active is None:
                continue
            timeframe = active.get("timeframe", "HOUR")
            if not _is_due(symbol, timeframe):
                continue
            try:
                _check_symbol(symbol, active)
                _last_checked[symbol] = datetime.now(timezone.utc)
            except Exception as e:
                print(f"[signal_loop] [{symbol}] unhandled error: {e}")

        now            = datetime.now(timezone.utc)
        secs_past_5min = (now.minute % 5) * 60 + now.second
        sleep_secs     = max(30, 300 - secs_past_5min)
        print(f"[signal_loop] Sleeping {sleep_secs}s until next 5-min boundary")
        time.sleep(sleep_secs)


def start_signal_loop() -> None:
    import threading
    t = threading.Thread(target=_loop, daemon=True, name="live_signal_loop")
    t.start()
    print("[signal_loop] Thread started")


if __name__ == "__main__":
    _loop()
