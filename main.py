from fastapi import FastAPI
from webhook.receiver import router
from data.positions_poller import start_poller

app = FastAPI()

app.include_router(router)


@app.on_event("startup")
def on_startup():
    start_poller()


@app.get("/")
def home():
    return {"status": "bot running"}


print("Trading bot starting...")