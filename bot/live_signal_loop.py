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
    get_pending_paper_trades, resolve_paper_trade, update_trade_context
from filters.vix_filter import get_current_vix, VIX_CAUTION_THRESHOLD
from risk_manager import get_risk_per_trade

SYMBOLS = ["US500", "US100", "DAX", "BTC", "EURUSD", "GBPUSD"]

MARKET_CLOSE = {
    "US500": {"hour": 20, "minute": 45},
    "US100": {"hour": 20, "minute": 45},
    "DAX":   {"hour": 16, "minute": 30},
    "BTC":   None,
}

TIMEFRAME_SECONDS: dict[str, int] = {"5MIN": 300, "15MIN": 900, "HOUR": 3600, "DAY": 86400}

_SYMBOL_DECIMALS: dict[str, int] = {
    "EURUSD": 5, "GBPUSD": 5, "EURGBP": 5,
    "USDJPY": 3,
    "US500": 2, "US100": 2, "DAX": 2,
    "XAUUSD": 2,
}

_MIN_SL_DIST: dict[str, float] = {
    "EURUSD": 0.00050,
    "GBPUSD": 0.00060,
    "EURGBP": 0.00050,
    "USDJPY": 0.050,
    "US500":  3.0,
    "US100":  4.0,
    "DAX":    5.0,
    "XAUUSD": 1.50,
}


def _round_precision(symbol: str) -> int:
    return _SYMBOL_DECIMALS.get(symbol, 4)


_raw_paper    = os.getenv("PAPER_TRADE_SYMBOLS", "")
PAPER_SYMBOLS: set[str] = {s.strip() for s in _raw_paper.split(",") if s.strip()}

MAX_TRADES_PER_DAY    = 20     # bug catcher only
MAX_TRADES_PER_SYMBOL = 6      # bug catcher only

_last_signal: dict[str, str] = {}
_last_shadow_signal: dict[str, str] = {}
_last_checked: dict[str, datetime] = {}
_ema200_cache: dict = {}  # symbol → (ema200, price_vs_ema200, cached_hour_key)

# Per-strategy session blocks: (strategy_name, symbol, timeframe) → set of sessions to block
# Blocked signals are shadow-logged to paper_trades for outcome tracking.
STRATEGY_SESSION_BLOCKS: dict[tuple, set] = {
    ("williams_r", "EURUSD", "15MIN"): {"NY_MID"},
}


def _get_session(hour: int) -> str:
    if 7 <= hour <= 8:   return "LONDON_OPEN"
    if 9 <= hour <= 12:  return "LONDON_MID"
    if 13 <= hour <= 15: return "NY_OPEN"
    if 16 <= hour <= 18: return "NY_MID"
    if 19 <= hour <= 20: return "NY_CLOSE"
    return "OFF_HOURS"


def _get_ema200(symbol: str) -> tuple:
    """Returns (ema200_daily, price_vs_ema200). Cached per hour per symbol."""
    hour_key = datetime.now(timezone.utc).strftime("%Y%m%d%H")
    cached = _ema200_cache.get(symbol)
    if cached and cached[2] == hour_key:
        return cached[0], cached[1]
    try:
        candles = _fetch_yfinance_candles(symbol, "DAY", 250)
        if len(candles) < 200:
            return None, None
        closes = [c["close"] for c in candles]
        k = 2 / 201
        ema = closes[0]
        for c in closes[1:]:
            ema = c * k + ema * (1 - k)
        pve = "ABOVE" if closes[-1] > ema else "BELOW"
        result = (round(ema, 4), pve)
        _ema200_cache[symbol] = (result[0], result[1], hour_key)
        return result
    except Exception:
        return None, None


def _is_due(symbol: str, timeframe: str, strategy_name: str = "") -> bool:
    interval = TIMEFRAME_SECONDS.get(timeframe, 3600)
    last = _last_checked.get((symbol, timeframe, strategy_name))
    if last is None:
        return True
    return (datetime.now(timezone.utc) - last).total_seconds() >= interval * 0.9


def _is_blocked(symbol: str) -> bool:
    close = MARKET_CLOSE.get(symbol)
    if close is None:
        return False
    now = datetime.now(timezone.utc)
    weekday = now.weekday()

    # Saturday — always blocked
    if weekday == 5:
        return True

    # Sunday — blocked until 23:00 UTC (IG reopens)
    if weekday == 6:
        return now.hour < 23

    now_mins = now.hour * 60 + now.minute

    # Friday — block from 20:45 UTC
    if weekday == 4:
        return now_mins >= (20 * 60 + 45)

    # Mon-Thu — 24h trading, no block
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
                        level=None,
                        order_type="MARKET",
                        quote_id=None,
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
            SELECT COUNT(*) as n
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
            "by_symbol":    by_symbol,
        }
    finally:
        conn.close()


def _risk_check(symbol: str, stats: dict) -> str | None:
    """Returns reason string if blocked, None if ok to trade.
    Loss limit is the real guardrail.
    Trade counts are safety nets for runaway signals only.
    """
    from risk.daily_loss import is_daily_loss_limit_breached, DAILY_LOSS_LIMIT_USD
    if is_daily_loss_limit_breached():
        return f"daily loss limit hit (all sources combined, limit ${DAILY_LOSS_LIMIT_USD})"

    if stats["total_trades"] >= MAX_TRADES_PER_DAY:
        return f"max daily trades reached ({MAX_TRADES_PER_DAY})"

    sym_count = stats["by_symbol"].get(symbol, 0)
    if sym_count >= MAX_TRADES_PER_SYMBOL:
        return f"max trades for {symbol} today ({MAX_TRADES_PER_SYMBOL})"

    return None


def _is_paper_trade(symbol: str, timeframe: str) -> bool:
    return symbol in PAPER_SYMBOLS or f"{symbol}_{timeframe}" in PAPER_SYMBOLS


def _check_symbol(symbol: str, active: dict, vix_level: float | None = None) -> None:
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

    is_paper = _is_paper_trade(symbol, timeframe) or active.get("status") == "paper"

    if not is_paper:
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

    # Shadow logging — confluence filters blocked a signal that would
    # otherwise have fired. Log it to paper_trades for A/B comparison.
    if sig.get("shadow_blocked") and (_is_paper_trade(symbol, timeframe) or active.get("status") == "paper"):
        shadow_dir    = sig.get("shadow_direction")
        shadow_signal = "BUY" if shadow_dir == 1 else "SELL" if shadow_dir == -1 else None
        if shadow_signal:
            shadow_dedup_key = f"{symbol}_SHADOW_{shadow_signal}_{candle_time}"
            if _last_shadow_signal.get((symbol, timeframe, strategy_name)) != shadow_dedup_key:
                _last_shadow_signal[(symbol, timeframe, strategy_name)] = shadow_dedup_key
                _entry   = candle["close"]
                _sl_dist = candle["high"] - candle["low"]
                if shadow_signal == "BUY":
                    _sl, _tp = round(_entry - _sl_dist, 5), round(_entry + _sl_dist * 2, 5)
                else:
                    _sl, _tp = round(_entry + _sl_dist, 5), round(_entry - _sl_dist * 2, 5)
                log_paper_trade({
                    "checked_at":    datetime.now(timezone.utc).isoformat(),
                    "symbol":        symbol,
                    "strategy_name": strategy_name,
                    "timeframe":     timeframe,
                    "candle_time":   candle_time,
                    "signal":        f"SHADOW_{shadow_signal}",
                    "entry_price":   _entry,
                    "sl":            _sl,
                    "tp":            _tp,
                    "outcome":       "PENDING",
                    "params_json":   params_json if isinstance(params_json, str) else json.dumps(params_json),
                    "notes":         f"SHADOW: filtered by {sig.get('shadow_reason')}",
                })
                print(f"[signal_loop] [{symbol}/{timeframe}/{strategy_name}] SHADOW {shadow_signal} "
                      f"logged (filtered by {sig.get('shadow_reason')})")

    if signal not in ("BUY", "SELL"):
        print(f"[signal_loop] [{symbol}] signal={signal} — no trade")
        log_signal_check(log_data)
        return

    if _last_signal.get((symbol, timeframe, strategy_name)) == dedup_key:
        print(f"[signal_loop] [{symbol}/{timeframe}/{strategy_name}] duplicate {signal} for {candle_time} — skipping")
        log_signal_check(log_data)
        return

    _last_signal[(symbol, timeframe, strategy_name)] = dedup_key

    entry        = candle["close"]
    _sig_sl      = sig.get("sl_price")
    _sig_tp      = sig.get("tp_price")
    if _sig_sl is not None and _sig_tp is not None:
        # Strategy provides range-based SL/TP (e.g. london_breakout)
        sl_dist = abs(entry - _sig_sl) or (candle["high"] - candle["low"])
        if signal == "BUY":
            action = "buy"
            sl     = round(float(_sig_sl), 5)
            tp     = round(float(_sig_tp), 5)
        else:
            action = "sell"
            sl     = round(float(_sig_sl), 5)
            tp     = round(float(_sig_tp), 5)
    else:
        # Default: SL/TP from candle range
        _raw_dist = candle["high"] - candle["low"]
        sl_dist = max(_raw_dist, _MIN_SL_DIST.get(symbol, _raw_dist))
        if sl_dist > _raw_dist:
            print(
                f"[signal_loop] [{symbol}] candle range "
                f"{_raw_dist:.5f} below floor {sl_dist:.5f} — using floor"
            )
        _prec   = _round_precision(symbol)
        if signal == "BUY":
            action = "buy"
            sl     = round(entry - sl_dist, _prec)
            tp     = round(entry + sl_dist * 2, _prec)
        else:
            action = "sell"
            sl     = round(entry + sl_dist, _prec)
            tp     = round(entry - sl_dist * 2, _prec)

    print(f"[signal_loop] [{symbol}] {signal} — sl={sl} tp={tp}")

    # Per-strategy session gate
    _gate_now    = datetime.now(timezone.utc)
    _gate_sess   = _get_session(_gate_now.hour)
    _sess_blocks = STRATEGY_SESSION_BLOCKS.get((strategy_name, symbol, timeframe), set())
    if _gate_sess in _sess_blocks:
        print(
            f"[signal_loop] [{symbol}/{timeframe}/{strategy_name}] "
            f"{signal} blocked — session {_gate_sess}"
        )
        _shadow_sess_key = f"{symbol}_SHADOW_{signal}_{candle_time}_sess_{_gate_sess}"
        if _last_shadow_signal.get((symbol, timeframe, strategy_name)) != _shadow_sess_key:
            _last_shadow_signal[(symbol, timeframe, strategy_name)] = _shadow_sess_key
            log_paper_trade({
                "checked_at":    _gate_now.isoformat(),
                "symbol":        symbol,
                "strategy_name": strategy_name,
                "timeframe":     timeframe,
                "candle_time":   candle_time,
                "signal":        f"SHADOW_{signal}",
                "entry_price":   entry,
                "sl":            sl,
                "tp":            tp,
                "outcome":       "PENDING",
                "session":       _gate_sess,
                "params_json":   params_json if isinstance(params_json, str) else json.dumps(params_json),
                "notes":         f"SHADOW: blocked by session filter ({_gate_sess})",
            })
            print(
                f"[signal_loop] [{symbol}/{timeframe}/{strategy_name}] "
                f"SHADOW {signal} logged (session {_gate_sess})"
            )
        log_data["signal"] = f"BLOCKED_SESSION_{_gate_sess}"
        log_data["error"]  = f"session block: {_gate_sess}"
        log_signal_check(log_data)
        return

    if is_paper:
        log_data["signal"] = f"PAPER_{signal}"
        _paper_now = datetime.now(timezone.utc)
        log_paper_trade({
            "checked_at":    _paper_now.isoformat(),
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
            "session":       _get_session(_paper_now.hour),
        })
        log_signal_check(log_data)
        print(f"[signal_loop] [{symbol}/{timeframe}] PAPER {signal} logged — not executed")
        return

    # Collect market context at signal time
    _now_utc = datetime.now(timezone.utc)
    _ctx: dict = {
        "vix_level":    vix_level,
        "atr_at_entry": round(sl_dist, 4),
        "day_of_week":  _now_utc.weekday(),
        "session":      _get_session(_now_utc.hour),
        "spread":       None,
    }
    try:
        _ema, _pve = _get_ema200(symbol)
        _ctx["ema200_daily"]    = _ema
        _ctx["price_vs_ema200"] = _pve
    except Exception:
        _ctx["ema200_daily"]    = None
        _ctx["price_vs_ema200"] = None

    from bot.execute_trade import place_trade
    try:
        result = place_trade(
            symbol, action, sl=sl, tp=tp,
            strategy_name=strategy_name,
            source="live_signal_loop",
            yf_entry=entry,
            timeframe=timeframe,
        )
        placed = 1 if result else 0
        log_data["trade_placed"] = placed
        if not result:
            log_data["error"] = "place_trade returned False"
        print(f"[signal_loop] [{symbol}] trade placed={placed}")
        if placed:
            try:
                update_trade_context(symbol, "live_signal_loop", _ctx)
            except Exception:
                pass
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


_EPIC_VALUE_PER_POINT = {
    "US500": 1.0, "US100": 1.0, "DAX": 1.0, "BTC": 0.1,
    "EURUSD": 10000.0,  # CS.D.EURUSD.MINI.IP: $1/pip, 0.0001 pip, contract=10k
    "GBPUSD": 10000.0,  # $1/pip, 0.0001 pip, contract=10k — same as EURUSD
}


def _resolve_pending_paper_trades() -> None:
    trades = get_pending_paper_trades()
    if not trades:
        return
    print(f"[resolver] {len(trades)} pending paper trade(s) to check")
    for trade in trades:
        symbol    = trade["symbol"]
        timeframe = trade.get("timeframe", "HOUR")
        signal    = (trade.get("signal") or "").upper().replace("PAPER_", "").replace("SHADOW_", "")
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
        later      = [c for c in candles if _candle_dt(c) > signal_dt]
        outcome    = None
        raw_pnl    = None
        for candle in later:
            if signal == "BUY":
                if candle["low"] <= sl:
                    outcome, raw_pnl = "LOSS", sl - entry
                    break
                if candle["high"] >= tp:
                    outcome, raw_pnl = "WIN", tp - entry
                    break
            else:
                if candle["high"] >= sl:
                    outcome, raw_pnl = "LOSS", entry - sl
                    break
                if candle["low"] <= tp:
                    outcome, raw_pnl = "WIN", entry - tp
                    break
        if outcome:
            if entry is None:
                resolve_paper_trade(trade["id"], outcome, 0.0)
                print(f"[resolver] [{symbol}/{timeframe}] id={trade['id']} → {outcome} (no entry_price, pnl=0)")
            else:
                value_per_point = _EPIC_VALUE_PER_POINT.get(symbol, 1.0)
                sl_distance = abs(entry - sl)
                if sl_distance > 0:
                    lot_size = get_risk_per_trade(symbol, is_paper=True) / (sl_distance * value_per_point)
                    lot_size = max(0.1, min(10.0, lot_size))
                else:
                    lot_size = 0.1
                simulated_pnl = raw_pnl * lot_size * value_per_point
                resolve_paper_trade(trade["id"], outcome, round(simulated_pnl, 4))
                print(
                    f"[resolver] [{symbol}/{timeframe}] id={trade['id']} → {outcome} "
                    f"raw={raw_pnl:.4f} lot={lot_size:.4f} pnl=${simulated_pnl:.2f}"
                )
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

        _vix_level: float | None = None
        _vix_blocked = False
        try:
            _vix_level = get_current_vix()
            if _vix_level is not None:
                _vix_blocked = _vix_level >= VIX_CAUTION_THRESHOLD
        except Exception:
            _vix_blocked = False

        for symbol in SYMBOLS:
            try:
                active_list = get_active_strategies(symbol=symbol)
            except Exception as e:
                print(f"[signal_loop] [{symbol}] get_active_strategies failed, skipping: {e}")
                continue
            for active in active_list:
                timeframe     = active.get("timeframe", "HOUR")
                strategy_name = active.get("strategy_name", "")
                strategy_type = active.get("strategy_type", "swing")
                is_paper      = _is_paper_trade(symbol, timeframe) or active.get("status") == "paper"
                if not _is_due(symbol, timeframe, strategy_name):
                    continue
                if strategy_type == "swing" and not is_paper and _vix_blocked:
                    print(f"[signal_loop] VIX elevated — skipping {symbol} {strategy_name} entry")
                    continue
                try:
                    _check_symbol(symbol, active, vix_level=_vix_level)
                    _last_checked[(symbol, timeframe, strategy_name)] = datetime.now(timezone.utc)
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
