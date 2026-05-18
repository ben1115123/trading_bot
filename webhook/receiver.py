from fastapi import APIRouter, Request
from bot.execute_trade import place_trade_from_alert
from database.db import get_connection
from datetime import datetime, timezone
import json

router = APIRouter()

WEBHOOK_DAILY_LOSS_LIMIT = 75.0

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


def _get_webhook_losses_today() -> float:
    conn = get_connection()
    try:
        cur = conn.cursor()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cur.execute("""
            SELECT COALESCE(
                ABS(SUM(CASE WHEN pnl < 0 THEN pnl ELSE 0 END)),
                0) as losses
            FROM trades
            WHERE source = 'tradingview_webhook'
            AND DATE(timestamp) = ?
            AND pnl IS NOT NULL
        """, (today,))
        return cur.fetchone()["losses"]
    finally:
        conn.close()


@router.post("/webhook")
async def webhook_endpoint(request: Request):

    try:
        body = await request.body()
        data = json.loads(body)

    except json.JSONDecodeError as e:
        print("❌ JSON Decode Error:", e)
        print("❌ Raw body:", body.decode())

        return {
            "status": "error",
            "message": "Invalid JSON received"
        }

    except Exception as e:
        print("❌ Unexpected error:", e)
        return {
            "status": "error",
            "message": "Unexpected error"
        }

    print("✅ Webhook received:", data)

    try:
        symbol = data.get("symbol", "")
        symbol = SYMBOL_ALIASES.get(symbol, symbol)
        data["symbol"] = symbol

        for key in ("long_sl", "long_tp", "short_sl", "short_tp"):
            data[key] = parse_float(data.get(key))

        from bot.live_signal_loop import _is_blocked
        if _is_blocked(symbol):
            print(f"[webhook] {symbol} blocked — near market close")
            return {"status": "blocked", "reason": "near market close"}

        webhook_losses = _get_webhook_losses_today()
        if webhook_losses >= WEBHOOK_DAILY_LOSS_LIMIT:
            print(f"[webhook] SwiftAlgo daily loss limit hit "
                  f"(${webhook_losses:.2f} >= "
                  f"${WEBHOOK_DAILY_LOSS_LIMIT}) — blocking trade")
            return {"status": "blocked",
                    "reason": "daily loss limit hit"}

        result = place_trade_from_alert(data)
        print("✅ Trade function returned:", result)

    except Exception as e:
        print("❌ Trade execution error:", e)
        return {
            "status": "error",
            "message": "Trade execution failed"
        }

    return {"status": "ok"}