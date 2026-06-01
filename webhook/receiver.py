import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from bot.execute_trade import place_trade_from_alert
from filters.webhook_filters import (
    should_block_day_of_week,
    should_block_macro_event,
    should_block_session,
    should_block_spread,
)
from database.models import get_webhook_strategy, log_paper_trade, log_webhook_alert, update_trade_context

logger = logging.getLogger(__name__)
router = APIRouter()

_ema200_wh_cache: dict = {}  # symbol → (ema200, price_vs, hour_key)


def _get_session(hour: int) -> str:
    if 7 <= hour <= 8:   return "LONDON_OPEN"
    if 9 <= hour <= 12:  return "LONDON_MID"
    if 13 <= hour <= 15: return "NY_OPEN"
    if 16 <= hour <= 18: return "NY_MID"
    if 19 <= hour <= 20: return "NY_CLOSE"
    return "OFF_HOURS"


def _ema200_context(symbol: str) -> tuple:
    """Returns (ema200_daily, price_vs_ema200). Cached per symbol per UTC hour."""
    hour_key = datetime.now(timezone.utc).strftime("%Y%m%d%H")
    cached = _ema200_wh_cache.get(symbol)
    if cached and cached[2] == hour_key:
        return cached[0], cached[1]
    try:
        from scripts.run_backtest import _fetch_yfinance_candles
        candles = _fetch_yfinance_candles(symbol, "DAY", 250)
        if len(candles) < 200:
            return None, None
        closes = [c["close"] for c in candles]
        k = 2 / 201
        ema = closes[0]
        for c in closes[1:]:
            ema = c * k + ema * (1 - k)
        pve = "ABOVE" if closes[-1] > ema else "BELOW"
        _ema200_wh_cache[symbol] = (round(ema, 4), pve, hour_key)
        # Evict stale entries
        for old_sym in [s for s, v in _ema200_wh_cache.items() if v[2] != hour_key]:
            del _ema200_wh_cache[old_sym]
        return round(ema, 4), pve
    except Exception:
        return None, None


def _atr14(symbol: str) -> float | None:
    """ATR14 from last 60 hourly candles via yfinance."""
    try:
        from scripts.run_backtest import _fetch_yfinance_candles
        candles = _fetch_yfinance_candles(symbol, "HOUR", 60)
        if len(candles) < 15:
            return None
        trs = []
        for i in range(1, len(candles)):
            h  = candles[i]["high"]
            l  = candles[i]["low"]
            pc = candles[i - 1]["close"]
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        return round(sum(trs[-14:]) / 14, 4)
    except Exception:
        return None

SYMBOL_ALIASES = {
    "SPX500": "US500",
    "NAS100": "US100",
    "SP500":  "US500",
    "NDX100": "US100",
    "US30":   "US500",
}


def safe_float(val):
    try:
        if val is None or str(val).strip() in ("null", "None", ""):
            return None
        return float(val)
    except (ValueError, TypeError):
        return None


def _log_wh(ts: str, symbol: str, direction: str, strategy_name: str | None,
             raw_payload: str | None, result: str,
             block_reason: str | None = None, deal_reference: str | None = None,
             notes: str | None = None) -> None:
    try:
        log_webhook_alert({
            "timestamp":     ts,
            "symbol":        symbol,
            "direction":     direction,
            "strategy_name": strategy_name,
            "raw_payload":   raw_payload,
            "result":        result,
            "block_reason":  block_reason,
            "deal_reference": deal_reference,
            "notes":         notes,
        })
    except Exception:
        pass


@router.post("/webhook")
async def webhook_endpoint(request: Request):

    body = b""
    try:
        body = await request.body()
        data = json.loads(body)

    except json.JSONDecodeError as e:
        ts = datetime.now(timezone.utc).isoformat()
        raw = body.decode(errors="replace") if body else ""
        print("❌ JSON Decode Error:", e)
        print("❌ Raw body:", raw)
        _log_wh(ts, "unknown", "unknown", None, raw[:4000], "BLOCKED", "invalid_payload")
        return {"status": "error", "message": "Invalid JSON received"}

    except Exception as e:
        ts = datetime.now(timezone.utc).isoformat()
        print("❌ Unexpected error:", e)
        _log_wh(ts, "unknown", "unknown", None, None, "BLOCKED", "invalid_payload", notes=str(e))
        return {"status": "error", "message": "Unexpected error"}

    print("✅ Webhook received:", data)

    # Capture context before inner try so the except block can reference them
    ts          = datetime.now(timezone.utc).isoformat()
    raw_payload = json.dumps(data)
    raw_sym     = data.get("symbol", "unknown")
    symbol      = SYMBOL_ALIASES.get(raw_sym, raw_sym)
    direction   = "unknown"

    try:
        data["symbol"] = symbol

        direction = (
            "BUY"  if str(data.get("buy_signal",  "0")) == "1" else
            "SELL" if str(data.get("sell_signal", "0")) == "1" else
            "NONE"
        )
        strategy_name = data.get("strategy", "swiftalgo")
        print(f"[WEBHOOK] {symbol} {direction} at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")

        for key in ("long_sl", "long_tp", "short_sl", "short_tp"):
            data[key] = safe_float(data.get(key))

        # --- market close block ---
        from bot.live_signal_loop import _is_blocked
        if _is_blocked(symbol):
            print(f"[webhook] {symbol} blocked — near market close")
            _log_wh(ts, symbol, direction, strategy_name, raw_payload, "BLOCKED", "friday_block")
            return {"status": "blocked", "reason": "near_market_close"}

        # --- daily loss limit ---
        from risk.daily_loss import is_daily_loss_limit_breached, DAILY_LOSS_LIMIT_USD
        if is_daily_loss_limit_breached():
            print(f"[webhook] Daily loss limit hit (limit ${DAILY_LOSS_LIMIT_USD}) — blocking")
            _log_wh(ts, symbol, direction, strategy_name, raw_payload, "BLOCKED", "daily_loss_limit")
            return {"status": "blocked", "reason": "daily_loss_limit"}

        # --- day-of-week filter ---
        if should_block_day_of_week(symbol):
            _log_wh(ts, symbol, direction, strategy_name, raw_payload, "BLOCKED", "day_of_week",
                    notes=f"Monday block — {symbol} historically poor on Mondays (33% WR US500, 8% WR US100)")
            return {"status": "blocked", "reason": "day_of_week"}

        # --- webhook filters ---
        if should_block_session(symbol):
            logger.warning(f"[webhook] {symbol} filtered: outside_session")
            _log_wh(ts, symbol, direction, strategy_name, raw_payload, "BLOCKED", "session_filter")
            return {"status": "filtered", "reason": "outside_session", "symbol": symbol}

        if should_block_macro_event():
            logger.warning(f"[webhook] {symbol} filtered: macro_event_window")
            _log_wh(ts, symbol, direction, strategy_name, raw_payload, "BLOCKED", "macro_event")
            return {"status": "filtered", "reason": "macro_event_window", "symbol": symbol}

        current_spread = safe_float(data.get("spread"))
        if should_block_spread(symbol, current_spread):
            logger.warning(f"[webhook] {symbol} filtered: spread_too_wide")
            _log_wh(ts, symbol, direction, strategy_name, raw_payload, "BLOCKED", "spread_filter")
            return {"status": "filtered", "reason": "spread_too_wide", "symbol": symbol}

        # --- strategy routing via active_strategy status ---
        strategy_row = get_webhook_strategy(symbol, strategy_name)
        if not strategy_row:
            print(f"[webhook] {symbol} {strategy_name} — no active_strategy row, blocking")
            _log_wh(ts, symbol, direction, strategy_name, raw_payload, "BLOCKED", "no_active_strategy")
            return {"status": "blocked", "reason": "no_active_strategy", "symbol": symbol}

        status = strategy_row.get("status", "active")
        if status == "inactive":
            print(f"[webhook] {symbol} {strategy_name} inactive — blocking")
            _log_wh(ts, symbol, direction, strategy_name, raw_payload, "BLOCKED", "strategy_inactive")
            return {"status": "blocked", "reason": "strategy_inactive", "symbol": symbol}

        if status == "paper":
            buy_signal  = str(data.get("buy_signal",  "0")) == "1"
            sell_signal = str(data.get("sell_signal", "0")) == "1"
            if buy_signal:
                sl          = data.get("long_sl")
                tp          = data.get("long_tp")
                signal      = "PAPER_BUY"
                entry_price = round((sl + tp) / 2, 5) if sl and tp else None
            elif sell_signal:
                sl          = data.get("short_sl")
                tp          = data.get("short_tp")
                signal      = "PAPER_SELL"
                entry_price = round((sl + tp) / 2, 5) if sl and tp else None
            else:
                return {"status": "ok", "note": "no_signal", "symbol": symbol}
            log_paper_trade({
                "checked_at":    datetime.now(timezone.utc).isoformat(),
                "symbol":        symbol,
                "strategy_name": strategy_name,
                "timeframe":     "HOUR",
                "candle_time":   datetime.now(timezone.utc).isoformat(),
                "signal":        signal,
                "entry_price":   entry_price,
                "sl":            sl,
                "tp":            tp,
                "outcome":       "PENDING",
                "params_json":   "{}",
            })
            print(f"[webhook] {symbol} {strategy_name} PAPER {signal} logged (entry≈{entry_price})")
            _log_wh(ts, symbol, direction, strategy_name, raw_payload, "PAPER",
                    notes="routed to paper_trades")
            return {"status": "paper", "symbol": symbol, "signal": signal}

        result = place_trade_from_alert(data)
        print("✅ Trade function returned:", result)
        deal_ref = result.get("deal_reference") if isinstance(result, dict) else None
        _log_wh(ts, symbol, direction, strategy_name, raw_payload, "EXECUTED",
                deal_reference=deal_ref)

        # Persist market context — failures are silent, never block trade
        try:
            _now = datetime.now(timezone.utc)
            _ema, _pve = _ema200_context(symbol)
            _wh_ctx = {
                "spread":          current_spread,
                "vix_level":       None,
                "ema200_daily":    _ema,
                "price_vs_ema200": _pve,
                "atr_at_entry":    _atr14(symbol),
                "day_of_week":     _now.weekday(),
                "session":         _get_session(_now.hour),
            }
            try:
                from filters.vix_filter import get_current_vix
                _wh_ctx["vix_level"] = get_current_vix()
            except Exception:
                pass
            update_trade_context(symbol, "tradingview_webhook", _wh_ctx)
        except Exception:
            pass

    except Exception as e:
        print("❌ Trade execution error:", e)
        _log_wh(ts, symbol, direction, strategy_name, raw_payload, "BLOCKED",
                "execution_error", notes=str(e)[:500])
        return {"status": "error", "message": "Trade execution failed"}

    return {"status": "ok"}
