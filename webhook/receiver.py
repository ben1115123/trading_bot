from fastapi import APIRouter, Request
from bot.execute_trade import place_trade_from_alert

router = APIRouter()

@router.post("/webhook")
async def webhook_endpoint(request: Request):

    data = await request.json()
    print("Webhook received:", data)

    result = place_trade_from_alert(data)

    print("Trade function returned:", result)

    return {"status": "ok"}