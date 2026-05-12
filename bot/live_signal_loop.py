#!/usr/bin/env python3
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.run_backtest import _fetch_yfinance_candles, STRATEGIES
from database.models import get_active_strategies, log_signal_check, log_paper_trade, \
    get_pending_paper_trades, resolve_paper_trade

SYMBOLS = ["US500", "US100", "DAX", "BTC"]

MARKET_CLOSE = {
    "US500": {"hour": 20, "minute": 0},
    "US100": {"hour": 20, "minute": 0},
    "DAX":   {"hour": 16, "minute": 30},
    "BTC":   None,
}

TIMEFRAME_SECONDS: dict[str, int] = {"5MIN": 300, "HOUR": 3600, "DAY": 86400}

_raw_paper    = os.getenv("PAPER_TRADE_SYMBOLS", "")
PAPER_SYMBOLS: set[str] = {s.strip() for s in _raw_paper.split(",") if s.strip()}

MAX_DAILY_LOSS_USD    = 75.0   # primary guardrail — hard stop
MAX_TRADES_PER_DAY    = 20     # bug catcher only
MAX_TRADES_PER_SYMBOL = 6      # bug catcher only

_last_signal: dict[str, str] = {}
_last_checked: dict[str, datetime] = {}


def _is_due(symbol: str, timeframe: str) -> bool:
    interval = TIMEFRAME_SECONDS.get(timeframe, 3600)
    last = _last_checked.get((symbol, timeframe))
    if last is None:
        return True
    return (datetime.now(timezone.utc) - last).total_seconds() >= interval * 0.9


def _is_blocked(symbol: str) -> bool:
    close = MARKET_CLOSE.get(symbol)
    if close is None:
        return False
    now = datetime.now(timezone.utc)
    weekday = now.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun

    if weekday == 5:
        return True

    if weekday == 6:
        return now.hour < 22

    if weekday == 4:
        if now.hour > 19 or (now.hour == 19 and now.minute >= 45):
            return True

    close_mins = close["hour"] * 60 + close["minute"]
    now_mins   = now.hour * 60 + now.minute

    # Block 1 hour before close
    return now_mins >= (close_mins - 60)


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
            if any(k in epic for k in ["SPTRD", "NASDAQ", "DAX"]):
                deal_id   = pos.get("dealId")
                direction = "SELL" if pos.get("direction") == "BUY" else "BUY"
                size      = pos.get("size")
                expiry    = pos.get("expiry", "-")
                print(f"[weekend_close] Closing {deal_id} {epic} {direction} size={size}")
                try:
                    ig_service.close_open_position(
                        deal_id=deal_id,
                        direction=direction,
                        epic=epic,
                        expiry=expiry,
                        order_type="MARKET",
                        size=size,
                    )
                    print(f"[weekend_close] ✓ Closed {deal_id}")
                except Exception as e:
                    print(f"[weekend_close] ✗ Failed to close {deal_id}: {e}")
    except Exception as e:
        print(f"[weekend_close] Error fetching positions: {e}")


def _get_daily_stats() -> dict:
    from database.db import get_connection
    conn = get_connection()
    try:
        cur = conn.cursor()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        cur.execute("""
            SELECT COUNT(*) as n,
                   COALESCE(SUM(CASE WHEN pnl < 0 THEN pnl ELSE 0 END), 0) as losses
            FROM trades
            WHERE source IN ('signal_loop', 'live_signal_loop')
            AND DATE(timestamp) = ?
        """, (today,))
        row = dict(cur.fetchone())

        cur.execute("""
            SELECT symbol, COUNT(*) as n
            FROM trades
            WHERE source IN ('signal_loop', 'live_signal_loop')
            AND DATE(timestamp) = ?
            GROUP BY symbol
        """, (today,))
        by_symbol = {r["symbol"]: r["n"] for r in cur.fetchall()}

        return {
            "total_trades": row["n"],
            "total_losses": abs(row["losses"]),
            "by_symbol":    by_symbol,
        }
    finally:
        conn.close()


def _risk_check(symbol: str, stats: dict) -> str | None:
    """Returns reason string if blocked, None if ok to trade.
    Loss limit is the real guardrail.
    Trade counts are safety nets for runaway signals only.
    """
    if stats["total_losses"] >= MAX_DAILY_LOSS_USD:
        return (f"daily loss limit hit "
                f"(${stats['total_losses']:.2f} >= "
                f"${MAX_DAILY_LOSS_USD})")

    if stats["total_trades"] >= MAX_TRADES_PER_DAY:
        return f"max daily trades reached ({MAX_TRADES_PER_DAY})"

    sym_count = stats["by_symbol"].get(symbol, 0)
    if sym_count >= MAX_TRADES_PER_SYMBOL:
        return f"max trades for {symbol} today ({MAX_TRADES_PER_SYMBOL})"

    return None


def _is_paper_trade(symbol: str, timeframe: str) -> bool:
    return symbol in PAPER_SYMBOLS or f"{symbol}_{timeframe}" in PAPER_SYMBOLS


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

    stats       = _get_daily_stats()
    risk_reason = _risk_check(symbol, stats)
    if risk_reason:
        print(f"[signal_loop] [{symbol}] risk limit: {risk_reason}")
        log_data["signal"] = "BLOCKED"
        log_data["error"]  = f"risk limit: {risk_reason}"
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

    if _last_signal.get((symbol, timeframe)) == dedup_key:
        print(f"[signal_loop] [{symbol}/{timeframe}] duplicate {signal} for {candle_time} — skipping")
        log_signal_check(log_data)
        return

    _last_signal[(symbol, timeframe)] = dedup_key

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

    if _is_paper_trade(symbol, timeframe):
        log_data["signal"] = f"PAPER_{signal}"
        log_paper_trade({
            "checked_at":    datetime.now(timezone.utc).isoformat(),
            "symbol":        symbol,
            "strategy_name": strategy_name,
            "timeframe":     timeframe,
            "candle_time":   candle_time,
            "signal":        f"PAPER_{signal}",
            "entry_price":   entry,
            "sl":            sl,
            "tp":            tp,
            "outcome":       "PENDING",
            "params_json":   params_json if isinstance(params_json, str) else json.dumps(params_json),
        })
        log_signal_check(log_data)
        print(f"[signal_loop] [{symbol}/{timeframe}] PAPER {signal} logged — not executed")
        return

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


def _candle_dt(candle: dict):
    try:
        dt = datetime.fromisoformat(str(candle.get("time", "")).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def _resolve_pending_paper_trades() -> None:
    trades = get_pending_paper_trades()
    if not trades:
        return
    print(f"[resolver] {len(trades)} pending paper trade(s) to check")
    for trade in trades:
        symbol    = trade["symbol"]
        timeframe = trade.get("timeframe", "HOUR")
        signal    = (trade.get("signal") or "").upper().replace("PAPER_", "")
        entry     = trade["entry_price"]
        sl        = trade["sl"]
        tp        = trade["tp"]
        if signal not in ("BUY", "SELL"):
            continue
        try:
            signal_dt = datetime.fromisoformat(
                str(trade.get("candle_time", "")).replace("Z", "+00:00")
            )
            if signal_dt.tzinfo is None:
                signal_dt = signal_dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        try:
            candles = _fetch_yfinance_candles(symbol, timeframe, 100)
        except Exception as e:
            print(f"[resolver] [{symbol}] candle fetch failed: {e}")
            continue
        later   = [c for c in candles if _candle_dt(c) > signal_dt]
        outcome = None
        pnl     = None
        for candle in later:
            if signal == "BUY":
                if candle["low"] <= sl:
                    outcome, pnl = "LOSS", sl - entry
                    break
                if candle["high"] >= tp:
                    outcome, pnl = "WIN", tp - entry
                    break
            else:
                if candle["high"] >= sl:
                    outcome, pnl = "LOSS", entry - sl
                    break
                if candle["low"] <= tp:
                    outcome, pnl = "WIN", entry - tp
                    break
        if outcome:
            resolve_paper_trade(trade["id"], outcome, round(pnl, 4))
            print(f"[resolver] [{symbol}/{timeframe}] id={trade['id']} → {outcome} pnl={pnl:.4f}")
        else:
            print(f"[resolver] [{symbol}/{timeframe}] id={trade['id']} still PENDING")


def _loop() -> None:
    print("[signal_loop] Starting signal loop (5-min wake, timeframe-aware)")
    while True:
        now = datetime.now(timezone.utc)
        print(f"\n[signal_loop] === Cycle at {now.strftime('%Y-%m-%d %H:%M:%S UTC')} ===")

        _resolve_pending_paper_trades()

        if _should_weekend_close():
            _weekend_close_positions()

        for symbol in SYMBOLS:
            for active in get_active_strategies(symbol=symbol):
                timeframe = active.get("timeframe", "HOUR")
                if not _is_due(symbol, timeframe):
                    continue
                try:
                    _check_symbol(symbol, active)
                    _last_checked[(symbol, timeframe)] = datetime.now(timezone.utc)
                except Exception as e:
                    print(f"[signal_loop] [{symbol}/{timeframe}] unhandled error: {e}")

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
