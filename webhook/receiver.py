from fastapi import APIRouter, Request
from bot.execute_trade import place_trade_from_alert
import json

router = APIRouter()

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
        result = place_trade_from_alert(data)
        print("✅ Trade function returned:", result)

    except Exception as e:
        print("❌ Trade execution error:", e)
        return {
            "status": "error",
            "message": "Trade execution failed"
        }

    return {"status": "ok"}