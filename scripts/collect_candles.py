#!/usr/bin/env python3
"""
Lightweight 15MIN candle collector — runs on VPS via cron.

Fetches the latest 15MIN candles from IG for EURUSD, US500, DAX and
appends new ones to scripts/candle_cache/{SYMBOL}_15MIN_IG.json
(same format as the Alpha Vantage cache: list of
{time, open, high, low, close, volume}).

Self-contained IG session — does not import execute_trade.py.
Wrapped in try/except so failure cannot affect the live bot.

Cron (VPS):
# */15 * * * * cd /home/ubuntu/trading_bot && \
#     python scripts/collect_candles.py >> logs/candles.log 2>&1
"""
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from trading_ig import IGService

from backend.backtesting.engine import fetch_candles
from ig_env import get_ig_credentials

CACHE_DIR = Path(__file__).resolve().parent / "candle_cache"
SYMBOLS = ["EURUSD", "US500", "DAX"]
TIMEFRAME = "15MIN"
FETCH_COUNT = 50  # plenty to cover gaps even if cron missed a few runs


def create_ig_session() -> IGService:
    username = os.getenv("IG_USERNAME")
    password = os.getenv("IG_PASSWORD")
    api_key, acc_type = get_ig_credentials()
    svc = IGService(username, password, api_key, acc_type=acc_type)
    svc.create_session()
    return svc


def _cache_path(symbol: str) -> Path:
    return CACHE_DIR / f"{symbol}_{TIMEFRAME}_IG.json"


def _load_existing(symbol: str) -> list:
    path = _cache_path(symbol)
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def _save(symbol: str, candles: list) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    with open(_cache_path(symbol), "w") as f:
        json.dump(candles, f)


def collect_symbol(ig: IGService, symbol: str) -> None:
    existing = _load_existing(symbol)
    existing_times = {c["time"] for c in existing}
    last_time = existing[-1]["time"] if existing else None

    fetched = fetch_candles(ig, symbol, TIMEFRAME, FETCH_COUNT)
    new_candles = [c for c in fetched if c["time"] not in existing_times]

    if last_time:
        new_candles = [c for c in new_candles if c["time"] > last_time]

    if not new_candles:
        print(f"{symbol} {TIMEFRAME}: no new candles, total: {len(existing):,}")
        return

    combined = existing + new_candles
    combined.sort(key=lambda c: c["time"])
    _save(symbol, combined)
    print(f"Collected {len(new_candles)} new {symbol} {TIMEFRAME} candles, total: {len(combined):,}")


def main():
    try:
        ig = create_ig_session()
    except Exception as e:
        print(f"[collect_candles] Failed to create IG session: {e}")
        return

    for symbol in SYMBOLS:
        try:
            collect_symbol(ig, symbol)
        except Exception as e:
            print(f"[collect_candles] {symbol}: failed — {e}")


if __name__ == "__main__":
    main()
