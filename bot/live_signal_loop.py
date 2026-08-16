#!/usr/bin/env python3
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.run_backtest import _fetch_yfinance_candles, STRATEGIES
from database.models import get_active_strategies, log_signal_check, log_paper_trade, \
    get_pending_paper_trades, resolve_paper_trade, update_trade_context, upsert_heartbeat, \
    log_candle_source_compare, log_correlation_event
from database.db import get_connection
from filters.vix_filter import get_current_vix, VIX_CAUTION_THRESHOLD
from risk_manager import get_risk_per_trade
from bot.notifier import send_telegram
from bot.candle_stream import get_candles as get_stream_candles, get_spread as get_stream_spread
from backend.backtesting.regime import classify_regimes
from symbols import SYMBOLS

CANDLE_SOURCE = os.getenv("CANDLE_SOURCE", "yfinance").lower()  # 'yfinance' (default,
                                                                 # unchanged) | 'ig_stream'
_PIP_SIZE = {
    "EURUSD": 0.0001, "GBPUSD": 0.0001, "AUDUSD": 0.0001, "EURGBP": 0.0001,
    "USDCAD": 0.0001,
    "USDJPY": 0.01,
    "US500": 1.0, "US100": 1.0, "DAX": 1.0,
}

MARKET_CLOSE = {
    "US500": {"hour": 20, "minute": 45},
    "US100": {"hour": 20, "minute": 45},
    "DAX":   {"hour": 16, "minute": 30},
    "BTC":   None,
}

TIMEFRAME_SECONDS: dict[str, int] = {"5MIN": 300, "15MIN": 900, "HOUR": 3600, "DAY": 86400}

_SYMBOL_DECIMALS: dict[str, int] = {
    "EURUSD": 5, "GBPUSD": 5, "EURGBP": 5, "AUDUSD": 5, "USDCAD": 5,
    "USDJPY": 3,
    "US500": 2, "US100": 2, "DAX": 2,
    "XAUUSD": 2,
}

# Moved to instrument_limits.py 2026-08-16 so the backtest engine reads the
# same floor instead of a copy (engine.py cannot import this module — cycle via
# scripts.run_backtest, plus bot.execute_trade opens an IG session on import).
# Aliased to the old private name so every call site below is unchanged.
from instrument_limits import MIN_SL_DIST as _MIN_SL_DIST, VALUE_PER_POINT


def _round_precision(symbol: str) -> int:
    return _SYMBOL_DECIMALS.get(symbol, 4)


_raw_paper    = os.getenv("PAPER_TRADE_SYMBOLS", "")
PAPER_SYMBOLS: set[str] = {s.strip() for s in _raw_paper.split(",") if s.strip()}

MAX_TRADES_PER_DAY    = 20     # bug catcher only
MAX_TRADES_PER_SYMBOL = 6      # bug catcher only

_last_signal: dict[str, str] = {}
_last_shadow_signal: dict[str, str] = {}
_last_checked: dict[str, datetime] = {}
_last_daily_loss_alert: dict[tuple, str] = {}  # (symbol, strategy_name) -> date fired
_ema200_cache: dict = {}  # symbol → (ema200, price_vs_ema200, cached_hour_key)

# Stream-staleness guard (CANDLE_SOURCE=ig_stream path only): subscribed+
# connected does not guarantee fresh ticks — a buffer can silently freeze.
# Indices get no yfinance fallback (off-session yfinance staleness is the
# exact failure mode this whole flip was meant to fix) — they skip instead.
STREAM_STALE_MULTIPLIER = 3
_INDEX_SYMBOLS = {"US500", "US100", "DAX"}
_last_stale_stream_alert: dict[str, datetime] = {}

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


_CORRELATION_WATCH_SYMBOLS = {"EURUSD", "GBPUSD", "AUDUSD", "USDCAD"}
_CORRELATION_MIN_COUNT = 3


def _check_correlation_cluster(strategy_name: str = "williams_r") -> None:
    """Report-only (2026-07-22): flag 3+ same-strategy OPEN positions, same
    direction, across USD pairs at once. NOT a gate — logs to
    correlation_events so frequency can be measured before deciding whether
    to gate it (ROADMAP.md Tier 4 correlation/exposure limits). Direction is
    the raw BUY/SELL signal per symbol, not USD-exposure-normalized (e.g.
    USDCAD SELL is actually long USD, opposite of EURUSD/GBPUSD/AUDUSD SELL)
    — fine for counting literal same-direction clusters like today's
    incident, but report-only is as far as raw-direction counting goes.

    TODO before any BLOCKING logic is built on this table: normalize to net
    USD exposure direction first. Raw same-direction across mixed base/quote
    USD pairs (USDCAD is USD-as-base, the other three are USD-as-quote) is
    not the same underlying bet — gating on the unnormalized signal would be
    wrong.
    """
    conn = get_connection()
    try:
        placeholders = ",".join("?" * len(_CORRELATION_WATCH_SYMBOLS))
        rows = conn.execute(f"""
            SELECT symbol, direction FROM trades
            WHERE status = 'OPEN' AND strategy_name = ?
            AND symbol IN ({placeholders})
        """, [strategy_name, *_CORRELATION_WATCH_SYMBOLS]).fetchall()
    finally:
        conn.close()

    by_direction: dict[str, list[str]] = {}
    for row in rows:
        by_direction.setdefault(row["direction"], []).append(row["symbol"])

    for direction, symbols in by_direction.items():
        unique_symbols = sorted(set(symbols))
        # Trigger on distinct pairs, not raw position count — 2 open EURUSD
        # positions isn't the diversification-across-pairs risk this exists
        # to catch (found live 2026-07-22: dedup key allows re-entry on the
        # same symbol across signal cycles, so raw counts double up).
        if len(unique_symbols) >= _CORRELATION_MIN_COUNT:
            msg = (f"CORRELATION CLUSTER: {len(unique_symbols)} pairs / "
                   f"{len(symbols)} positions — {strategy_name} {direction} "
                   f"open together ({', '.join(unique_symbols)})")
            print(f"[signal_loop] {msg}")
            log_correlation_event(strategy_name, direction, unique_symbols)
            send_telegram(msg, level="INFO")


def _risk_check(symbol: str, stats: dict, strategy_name: str | None = None) -> str | None:
    """Returns reason string if blocked, None if ok to trade.
    Loss limit is the real guardrail.
    Trade counts are safety nets for runaway signals only.
    """
    from risk.daily_loss import is_daily_loss_limit_breached, DAILY_LOSS_LIMIT_USD
    if is_daily_loss_limit_breached(symbol=symbol, strategy_name=strategy_name):
        return f"daily loss limit hit ({symbol}/{strategy_name}, limit ${DAILY_LOSS_LIMIT_USD})"

    if stats["total_trades"] >= MAX_TRADES_PER_DAY:
        return f"max daily trades reached ({MAX_TRADES_PER_DAY})"

    if strategy_name != "williams_r":
        sym_count = stats["by_symbol"].get(symbol, 0)
        if sym_count >= MAX_TRADES_PER_SYMBOL:
            return f"max trades for {symbol} today ({MAX_TRADES_PER_SYMBOL})"

    return None


def _is_paper_trade(symbol: str, timeframe: str) -> bool:
    return symbol in PAPER_SYMBOLS or f"{symbol}_{timeframe}" in PAPER_SYMBOLS


def _log_candle_comparison(symbol: str, timeframe: str, yf_candles: list) -> None:
    """Parallel validation: yfinance vs IG stream latest-close delta. Called
    from both branches regardless of which source is CANDLE_SOURCE-primary
    (pre-flip: yfinance drives trades, this validates against stream;
    post-flip: stream drives trades, this validates against yfinance as a
    one-week confirmation window) -- never blocks or affects the actual
    trading fetch path above it.
    yf_candles[-2] matches this file's existing convention (candles[-1] is
    the in-progress current candle). The stream buffer, by contrast, only
    ever contains genuinely completed candles (CONS_END-gated / REST is
    inherently complete), so stream_candles[-1] is already the latest
    completed one -- no [-2] needed there.
    """
    stream_candles = get_stream_candles(symbol, timeframe)
    if not stream_candles or len(yf_candles) < 2:
        return
    yf_last = yf_candles[-2]
    stream_last = stream_candles[-1]
    pip_size = _PIP_SIZE.get(symbol, 1.0)
    delta = (yf_last["close"] - stream_last["close"]) / pip_size
    log_candle_source_compare({
        "symbol": symbol, "timeframe": timeframe,
        "yf_close": yf_last["close"], "yf_time": str(yf_last.get("time")),
        "stream_close": stream_last["close"], "stream_time": str(stream_last.get("time")),
        "delta_pips": round(delta, 2),
    })


def _check_symbol(symbol: str, active: dict, vix_level: float | None = None,
                   candle_cache: dict | None = None) -> None:
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
        # Capture-only spread sample, taken on EVERY check rather than only on
        # trades. Live trades run ~1 per symbol per day, so a trade-only sample
        # needs ~100 days to characterise a symbol; checks give ~96-480/day and
        # a usable distribution in 1-2 days. None when the stream has nothing
        # fresh (off-session, pre-warm-up, yfinance mode).
        "spread":        get_stream_spread(symbol),
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
        risk_reason = _risk_check(symbol, stats, strategy_name)
        if risk_reason:
            print(f"[signal_loop] [{symbol}] risk limit: {risk_reason}")
            if risk_reason.startswith("daily loss limit hit"):
                global _last_daily_loss_alert
                _today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                _key = (symbol, strategy_name)
                if _last_daily_loss_alert.get(_key) != _today:
                    _last_daily_loss_alert[_key] = _today
                    send_telegram(
                        f"DAILY LOSS LIMIT HIT — {symbol}/{strategy_name} paused until midnight UTC",
                        level="ERROR")
            log_data["signal"] = "BLOCKED"
            log_data["error"]  = f"risk limit: {risk_reason}"
            log_signal_check(log_data)
            return

    strat_cls = STRATEGIES.get(strategy_name)
    if strat_cls is None:
        print(f"[signal_loop] [{symbol}] Unknown strategy: {strategy_name} — skipping (no candle fetch)")
        return

    cache_key = (symbol, timeframe)
    if candle_cache is not None and cache_key in candle_cache:
        candles, fetch_err = candle_cache[cache_key]
    else:
        if CANDLE_SOURCE == "ig_stream":
            candles = get_stream_candles(symbol, timeframe)
            fetch_err = None if candles is not None else "ig_stream buffer not warm yet"

            if candles:
                _age_secs = (datetime.now(timezone.utc) - _candle_dt(candles[-1])).total_seconds()
                _stale_threshold = STREAM_STALE_MULTIPLIER * TIMEFRAME_SECONDS.get(timeframe, 3600)

                # A closed candle can never be timestamped in the future — any
                # negative age is invalid data, not freshness. Caught live
                # 2026-07-15: a REST-warmed candle mislabeled 8h ahead of real
                # UTC (account-timezone bug in candle_stream.py, now fixed)
                # sailed through this guard as "fresh" because age was negative,
                # not > threshold. Treat negative age as stale unconditionally.
                if _age_secs > _stale_threshold or _age_secs < 0:
                    # Subscribed+connected does not guarantee fresh ticks — caught
                    # live 2026-07-15: index Lightstreamer topics stopped delivering
                    # CONS_END items while FX topics kept updating normally, and the
                    # stream buffer silently served a >6h-stale candle with no
                    # self-correction. Indices don't get a yfinance fallback here —
                    # off-session yfinance staleness is the exact failure mode that
                    # produced the min-deal-size incident, so an untrusted-stale
                    # source is worse than skipping the symbol outright.
                    _now_alert  = datetime.now(timezone.utc)
                    _last_alert = _last_stale_stream_alert.get(symbol)
                    _should_alert = _last_alert is None or (_now_alert - _last_alert) > timedelta(hours=6)

                    if symbol in _INDEX_SYMBOLS:
                        print(f"[signal_loop] [{symbol}/{timeframe}] STREAM STALE "
                              f"(age={_age_secs/60:.0f}min > {_stale_threshold/60:.0f}min) — "
                              f"index, yfinance untrusted off-session — skipping symbol this cycle")
                        if _should_alert:
                            _last_stale_stream_alert[symbol] = _now_alert
                            send_telegram(
                                f"{symbol}/{timeframe} signals paused — stream stale, yfinance untrusted",
                                level="WARN",
                            )
                        candles = None
                        fetch_err = f"stream stale (age={_age_secs/60:.0f}min) — index, skipped"
                    else:
                        print(f"[signal_loop] [{symbol}/{timeframe}] STREAM STALE "
                              f"(age={_age_secs/60:.0f}min > {_stale_threshold/60:.0f}min) — "
                              f"FX, falling back to yfinance for this fetch")
                        if _should_alert:
                            _last_stale_stream_alert[symbol] = _now_alert
                            send_telegram(f"{symbol}/{timeframe} stream stale — falling back to yfinance", level="WARN")
                        try:
                            candles   = _fetch_yfinance_candles(symbol, timeframe, 500)
                            fetch_err = None
                        except Exception as e:
                            candles   = None
                            fetch_err = f"stream stale AND yfinance fallback failed: {e}"
                else:
                    print(f"[signal_loop] [{symbol}/{timeframe}] candle source: ig_stream "
                          f"({len(candles)} candles, latest={candles[-1].get('time')})")

            if candles:
                # Post-flip verification window: comparison logger keeps running
                # inverted (stream now authoritative, yfinance the secondary/
                # reference series) — same candle_source_compare table, same
                # _log_candle_comparison function, just called from this branch
                # too now. Best-effort: yfinance fetch failure here must never
                # block the live (stream-driven) trading path above it.
                try:
                    yf_candles = _fetch_yfinance_candles(symbol, timeframe, 500)
                    if yf_candles:
                        _log_candle_comparison(symbol, timeframe, yf_candles)
                except Exception as e:
                    print(f"[signal_loop] [{symbol}] post-flip comparison log failed: {e}")
        else:
            try:
                candles   = _fetch_yfinance_candles(symbol, timeframe, 500)
                fetch_err = None
            except Exception as e:
                candles   = None
                fetch_err = e
            if candles:
                try:
                    _log_candle_comparison(symbol, timeframe, candles)
                except Exception as e:
                    print(f"[signal_loop] [{symbol}] candle comparison log failed: {e}")
        if candle_cache is not None:
            candle_cache[cache_key] = (candles, fetch_err)

    if fetch_err is not None:
        print(f"[signal_loop] [{symbol}] candle fetch failed: {fetch_err}")
        log_data["error"] = f"candle fetch error: {fetch_err}"
        log_signal_check(log_data)
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

    try:
        regime = classify_regimes(candles)[-2]
    except Exception:
        regime = None

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
                    "regime":        regime,
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
                "regime":        regime,
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
            "regime":        regime,
        })
        log_signal_check(log_data)
        print(f"[signal_loop] [{symbol}/{timeframe}] PAPER {signal} logged — not executed")
        return

    from risk.concurrent_positions import is_concurrent_limit_breached, get_open_position_count
    if is_concurrent_limit_breached(symbol, strategy_name):
        _stack_n = get_open_position_count(symbol, strategy_name) + 1
        print(f"[signal_loop] [{symbol}/{strategy_name}] concurrent position limit hit — skipping {signal}")
        _cap_now = datetime.now(timezone.utc)
        log_paper_trade({
            "checked_at":    _cap_now.isoformat(),
            "symbol":        symbol,
            "strategy_name": strategy_name,
            "timeframe":     timeframe,
            "candle_time":   candle_time,
            "signal":        f"SHADOW_{signal}",
            "entry_price":   entry,
            "sl":            sl,
            "tp":            tp,
            "outcome":       "PENDING",
            "params_json":   params_json if isinstance(params_json, str) else json.dumps(params_json),
            "session":       _get_session(_cap_now.hour),
            "notes":         f"SHADOW: skipped — concurrent position limit, would be {_stack_n}th stack",
            "regime":        regime,
        })
        log_data["signal"] = f"BLOCKED_CONCURRENT_{signal}"
        log_data["error"]  = f"concurrent position limit: {_stack_n}th stack on {symbol}/{strategy_name}"
        log_signal_check(log_data)
        return

    # Collect market context at signal time
    _now_utc = datetime.now(timezone.utc)
    _ctx: dict = {
        "vix_level":    vix_level,
        "atr_at_entry": round(sl_dist, 4),
        "day_of_week":  _now_utc.weekday(),
        "session":      _get_session(_now_utc.hour),
        # Was hardcoded None, which is the entire reason trades.spread was
        # NULL on all 906 rows — the column and write path always existed.
        # Filled from execute_trade.last_spread after place_trade returns
        # (below), since the dealing spread is only known once the quote has
        # been read. Seeded here with the stream's observation as a fallback
        # for the case where place_trade never reached its quote.
        "spread":       get_stream_spread(symbol),
        "regime":       regime,
    }
    try:
        _ema, _pve = _get_ema200(symbol)
        _ctx["ema200_daily"]    = _ema
        _ctx["price_vs_ema200"] = _pve
    except Exception:
        _ctx["ema200_daily"]    = None
        _ctx["price_vs_ema200"] = None

    import bot.execute_trade as execute_trade
    try:
        result = execute_trade.place_trade(
            symbol, action, sl=sl, tp=tp,
            strategy_name=strategy_name,
            source="live_signal_loop",
            yf_entry=entry,
            timeframe=timeframe,
        )
        placed = 1 if result else 0
        log_data["trade_placed"] = placed
        if not result:
            log_data["error"] = execute_trade.last_reject_reason.get(
                symbol, "place_trade returned False"
            )
        print(f"[signal_loop] [{symbol}] trade placed={placed}")
        if placed:
            try:
                # Prefer the dealing spread actually observed at execution —
                # that is the quote the trade crossed. Falls back to the
                # stream seed set above if place_trade never got that far.
                _exec_spread = execute_trade.last_spread.get(symbol)
                if _exec_spread is not None:
                    _ctx["spread"] = _exec_spread
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


# _EPIC_VALUE_PER_POINT DELETED 2026-08-16 — it was a third copy of the
# value-per-point table and it OMITTED USDCAD, so `.get(symbol, 1.0)` returned
# 1.0 and every USDCAD paper trade booked ~1/2000th of its value across 97 rows
# (findings doc finding 16). Now reads instrument_limits.VALUE_PER_POINT, the
# single source shared with execute_trade and the backtest engine.


def _bracket_error(signal: str, entry, sl, tp) -> str | None:
    """Reject malformed SL/TP brackets, mirroring the backtest engine's
    EngineContractError conditions (backend/backtesting/engine.py::_resolve_sl_tp).

    Returns a reason string when the bracket is unusable, else None.

    WHY: paper_trades ids 253, 334 and 335 carry sl == tp — a zero-width
    bracket with both levels on the same side of entry. The resolver detected a
    "LOSS" and then computed raw_pnl from the wrong side, booking a LOSS with
    POSITIVE P&L (+$2.04). Those same rows are finding 3's MAX-clamp entries and
    finding 19's win-basis disagreement: one defect, three symptoms. parity-v2
    rejects this in the backtest engine; the resolver had no equivalent check,
    so the same malformed signal was refused by one synthetic model and
    monetised by the other.

    This REFUSES rather than reinterprets. Fixing the win-basis count alone
    would have hidden these rows instead of surfacing them (finding 19).
    """
    if entry is None or sl is None or tp is None:
        return "missing entry/sl/tp"
    side = "BUY" if "BUY" in (signal or "") else ("SELL" if "SELL" in (signal or "") else None)
    if side is None:
        return f"unrecognised signal {signal!r}"
    if sl == tp:
        return f"zero-width bracket (sl == tp == {sl})"
    if side == "BUY" and not (sl < entry < tp):
        return f"wrong-side BUY bracket (need sl < entry < tp, got {sl} / {entry} / {tp})"
    if side == "SELL" and not (tp < entry < sl):
        return f"wrong-side SELL bracket (need tp < entry < sl, got {tp} / {entry} / {sl})"
    return None


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
        _bad = _bracket_error(trade.get("signal"), entry, sl, tp)
        if _bad:
            # Refuse, loudly. Left PENDING rather than resolved: a malformed
            # row must not acquire a P&L, and must stay visible rather than be
            # silently written off.
            print(f"[resolver] [{symbol}] id={trade['id']} REFUSED — {_bad}")
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
                # [symbol], never .get(symbol, default) — a KeyError on an
                # unregistered symbol is correct and would have caught the
                # USDCAD omission on its first paper trade (finding 16).
                value_per_point = VALUE_PER_POINT[symbol]
                sl_distance = abs(entry - sl)
                if sl_distance <= 0:
                    # Abort, mirroring risk_manager:30-32 which returns None and
                    # makes place_trade refuse. The old code booked at the 0.1
                    # minimum, inventing a position live would never have opened.
                    print(f"[resolver] [{symbol}] id={trade['id']} REFUSED — "
                          f"sl_distance={sl_distance} (entry={entry} sl={sl})")
                    continue
                lot_size = get_risk_per_trade(symbol, is_paper=True) / (sl_distance * value_per_point)
                # Round THEN clamp, matching risk_manager:36-44 and the backtest
                # engine. The resolver clamped without ever rounding, so its lot
                # sizes disagreed with both other models at the boundaries.
                lot_size = round(lot_size, 2)
                lot_size = max(0.1, min(10.0, lot_size))
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

        _candle_cache: dict[tuple, tuple] = {}
        _checked_this_cycle: list[str] = []

        for symbol in SYMBOLS:
            try:
                active_list = get_active_strategies(symbol=symbol)
            except Exception as e:
                print(f"[signal_loop] [{symbol}] get_active_strategies failed, skipping: {e}")
                send_telegram(f"SIGNAL LOOP ERROR {symbol}: {e}", level="ERROR")
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
                    _check_symbol(symbol, active, vix_level=_vix_level, candle_cache=_candle_cache)
                    _last_checked[(symbol, timeframe, strategy_name)] = datetime.now(timezone.utc)
                    _checked_this_cycle.append(f"{symbol}/{timeframe}/{strategy_name}")
                except Exception as e:
                    print(f"[signal_loop] [{symbol}/{timeframe}] unhandled error: {e}")
                    send_telegram(f"SIGNAL LOOP ERROR {symbol}: {e}", level="ERROR")

        print(f"[signal_loop] Checked this cycle ({len(_checked_this_cycle)}): {_checked_this_cycle}")
        print(f"[signal_loop] Candle fetches this cycle: {len(_candle_cache)} unique (symbol,timeframe) pairs")

        try:
            _check_correlation_cluster()
        except Exception as e:
            print(f"[signal_loop] correlation cluster check failed: {e}")

        try:
            upsert_heartbeat("signal_loop", f"{len(_checked_this_cycle)} strategies checked")
        except Exception as e:
            print(f"[signal_loop] heartbeat upsert failed: {e}")

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
