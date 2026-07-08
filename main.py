from fastapi import FastAPI
from webhook.receiver import router
from data.positions_poller import start_poller
from bot.live_signal_loop import start_signal_loop
from bot.candle_stream import start_candle_stream
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


print("Trading bot starting...")