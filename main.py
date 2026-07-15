from fastapi import FastAPI
from webhook.receiver import router
from data.positions_poller import start_poller
from bot.live_signal_loop import start_signal_loop
from bot.candle_stream import start_candle_stream, debug_buffer_tail
from database.db import init_db

app = FastAPI()

app.include_router(router)


@app.on_event("startup")
def on_startup():
    init_db()
    start_poller()
    start_signal_loop()
    start_candle_stream()


@app.get("/")
def home():
    return {"status": "bot running"}


@app.get("/debug/candles/{symbol}/{timeframe}")
def debug_candles(symbol: str, timeframe: str, n: int = 10):
    """Diagnostic only — raw candle_stream buffer tail, bypassing the
    20-candle warm threshold. Not used by any trading path."""
    return {"candles": debug_buffer_tail(symbol.upper(), timeframe.upper(), n)}


print("Trading bot starting...")