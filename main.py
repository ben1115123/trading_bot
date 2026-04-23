from fastapi import FastAPI
from webhook.receiver import router
from data.positions_poller import start_poller
from database.db import init_db

app = FastAPI()

app.include_router(router)


@app.on_event("startup")
def on_startup():
    init_db()
    start_poller()


@app.get("/")
def home():
    return {"status": "bot running"}


print("Trading bot starting...")