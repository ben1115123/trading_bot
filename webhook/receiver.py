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
from database.models import get_webhook_strategy, log_paper_trade

logger = logging.getLogger(__name__)
router = APIRouter()

SYMBOL_ALIASES = {
    "SPX500": "US500",
    "NAS100": "US100",
    "SP500":  "US500",
    "NDX100": "US100",
    "US30":   "US500",
}


def parse_float(val):
    try:
        if val is None or str(val).lower() == "null":
            return None
        return float(val)
    except (ValueError, TypeError):
        return None


@router.post("/webhook")
async def webhook_endpoint(request: Request):

    try:
        body = await request.body()
        data = json.loads(body)

    except json.JSONDecodeError as e:
        print("❌ JSON Decode Error:", e)
        print("❌ Raw body:", body.decode())
        return {"status": "error", "message": "Invalid JSON received"}

    except Exception as e:
        print("❌ Unexpected error:", e)
        return {"status": "error", "message": "Unexpected error"}

    print("✅ Webhook received:", data)

    try:
        symbol = data.get("symbol", "")
        symbol = SYMBOL_ALIASES.get(symbol, symbol)
        data["symbol"] = symbol

        for key in ("long_sl", "long_tp", "short_sl", "short_tp"):
            data[key] = parse_float(data.get(key))

        # --- market close block ---
        from bot.live_signal_loop import _is_blocked
        if _is_blocked(symbol):
            print(f"[webhook] {symbol} blocked — near market close")
            return {"status": "blocked", "reason": "near_market_close"}

        # --- daily loss limit ---
        from risk.daily_loss import is_daily_loss_limit_breached, DAILY_LOSS_LIMIT_USD
        if is_daily_loss_limit_breached():
            print(f"[webhook] Daily loss limit hit (limit ${DAILY_LOSS_LIMIT_USD}) — blocking")
            return {"status": "blocked", "reason": "daily_loss_limit"}

        # --- webhook filters ---
        if should_block_session(symbol):
            logger.info(f"[webhook] {symbol} filtered: outside_session")
            return {"status": "filtered", "reason": "outside_session", "symbol": symbol}

        if should_block_macro_event():
            logger.warning(f"[webhook] {symbol} filtered: macro_event_window")
            return {"status": "filtered", "reason": "macro_event_window", "symbol": symbol}

        current_spread = parse_float(data.get("spread"))
        if should_block_spread(symbol, current_spread):
            logger.warning(f"[webhook] {symbol} filtered: spread_too_wide")
            return {"status": "filtered", "reason": "spread_too_wide", "symbol": symbol}

        # --- swiftalgo routing via active_strategy status ---
        strategy_row = get_webhook_strategy(symbol, "swiftalgo")
        if strategy_row:
            status = strategy_row.get("status", "active")
            if status == "inactive":
                print(f"[webhook] {symbol} swiftalgo inactive — blocking")
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
                return {"status": "paper", "symbol": symbol, "signal": signal}

        result = place_trade_from_alert(data)
        print("✅ Trade function returned:", result)

    except Exception as e:
        print("❌ Trade execution error:", e)
        return {"status": "error", "message": "Trade execution failed"}

    return {"status": "ok"}
