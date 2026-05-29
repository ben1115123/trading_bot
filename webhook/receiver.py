import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from bot.execute_trade import place_trade_from_alert
from filters.webhook_filters import (
    should_block_macro_event,
    should_block_session,
    should_block_spread,
)
from database.models import get_webhook_strategy, log_paper_trade, log_webhook_alert

logger = logging.getLogger(__name__)
router = APIRouter()

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
        print(f"[WEBHOOK] {symbol} {direction} at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")

        for key in ("long_sl", "long_tp", "short_sl", "short_tp"):
            data[key] = safe_float(data.get(key))

        # --- market close block ---
        from bot.live_signal_loop import _is_blocked
        if _is_blocked(symbol):
            print(f"[webhook] {symbol} blocked — near market close")
            _log_wh(ts, symbol, direction, "swiftalgo", raw_payload, "BLOCKED", "friday_block")
            return {"status": "blocked", "reason": "near_market_close"}

        # --- daily loss limit ---
        from risk.daily_loss import is_daily_loss_limit_breached, DAILY_LOSS_LIMIT_USD
        if is_daily_loss_limit_breached():
            print(f"[webhook] Daily loss limit hit (limit ${DAILY_LOSS_LIMIT_USD}) — blocking")
            _log_wh(ts, symbol, direction, "swiftalgo", raw_payload, "BLOCKED", "daily_loss_limit")
            return {"status": "blocked", "reason": "daily_loss_limit"}

        # --- webhook filters ---
        if should_block_session(symbol):
            logger.warning(f"[webhook] {symbol} filtered: outside_session")
            _log_wh(ts, symbol, direction, "swiftalgo", raw_payload, "BLOCKED", "session_filter")
            return {"status": "filtered", "reason": "outside_session", "symbol": symbol}

        if should_block_macro_event():
            logger.warning(f"[webhook] {symbol} filtered: macro_event_window")
            _log_wh(ts, symbol, direction, "swiftalgo", raw_payload, "BLOCKED", "macro_event")
            return {"status": "filtered", "reason": "macro_event_window", "symbol": symbol}

        current_spread = safe_float(data.get("spread"))
        if should_block_spread(symbol, current_spread):
            logger.warning(f"[webhook] {symbol} filtered: spread_too_wide")
            _log_wh(ts, symbol, direction, "swiftalgo", raw_payload, "BLOCKED", "spread_filter")
            return {"status": "filtered", "reason": "spread_too_wide", "symbol": symbol}

        # --- swiftalgo routing via active_strategy status ---
        strategy_row = get_webhook_strategy(symbol, "swiftalgo")
        if strategy_row:
            status = strategy_row.get("status", "active")
            if status == "inactive":
                print(f"[webhook] {symbol} swiftalgo inactive — blocking")
                _log_wh(ts, symbol, direction, "swiftalgo", raw_payload, "BLOCKED", "strategy_inactive")
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
                    "strategy_name": "swiftalgo",
                    "timeframe":     "HOUR",
                    "candle_time":   datetime.now(timezone.utc).isoformat(),
                    "signal":        signal,
                    "entry_price":   entry_price,
                    "sl":            sl,
                    "tp":            tp,
                    "outcome":       "PENDING",
                    "params_json":   "{}",
                })
                print(f"[webhook] {symbol} swiftalgo PAPER {signal} logged (entry≈{entry_price})")
                _log_wh(ts, symbol, direction, "swiftalgo", raw_payload, "PAPER",
                        notes="routed to paper_trades")
                return {"status": "paper", "symbol": symbol, "signal": signal}

        result = place_trade_from_alert(data)
        print("✅ Trade function returned:", result)
        deal_ref = result.get("deal_reference") if isinstance(result, dict) else None
        _log_wh(ts, symbol, direction, "swiftalgo", raw_payload, "EXECUTED",
                deal_reference=deal_ref)

    except Exception as e:
        print("❌ Trade execution error:", e)
        _log_wh(ts, symbol, direction, "swiftalgo", raw_payload, "BLOCKED",
                "execution_error", notes=str(e)[:500])
        return {"status": "error", "message": "Trade execution failed"}

    return {"status": "ok"}
