#!/usr/bin/env python3
"""
Fetch 2yr 15MIN candles from Twelve Data and save to the candle
cache for run_backtest.py (--source alphavantage).

Free key: twelvedata.com (no credit card)
Read from .env: TWELVEDATA_API_KEY=your_key_here

Free tier: 8 requests/minute — 8s sleep between calls.

Usage:
  python3 scripts/fetch_twelvedata.py
  python3 scripts/fetch_twelvedata.py --symbols EURUSD,US500
  python3 scripts/fetch_twelvedata.py --dry-run
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

CACHE_DIR = Path(__file__).resolve().parent / "candle_cache"
BASE_URL = "https://api.twelvedata.com/time_series"
SLEEP_SECONDS = 8
TIMEFRAME = "15MIN"
INTERVAL = "15min"
OUTPUTSIZE = 5000

SYMBOL_MAP = {
    "EURUSD": "EUR/USD",
    "US500":  "SPY",
    "DAX":    "EWG",
    "US100":  "QQQ",
}


def _request(td_symbol: str) -> dict:
    api_key = os.getenv("TWELVEDATA_API_KEY")
    if not api_key:
        raise RuntimeError("TWELVEDATA_API_KEY not set in .env")
    params = {
        "symbol": td_symbol,
        "interval": INTERVAL,
        "outputsize": OUTPUTSIZE,
        "apikey": api_key,
    }
    resp = requests.get(BASE_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") == "error":
        raise RuntimeError(f"Twelve Data error: {data}")
    return data


def _parse_candles(data: dict) -> list:
    values = data.get("values", [])
    candles = []
    for v in values:
        candles.append({
            "time":   v["datetime"],
            "open":   float(v["open"]),
            "high":   float(v["high"]),
            "low":    float(v["low"]),
            "close":  float(v["close"]),
            "volume": float(v.get("volume", 0) or 0),
        })
    candles.sort(key=lambda c: c["time"])
    return candles


def main():
    parser = argparse.ArgumentParser(description="Fetch 15MIN candles from Twelve Data.")
    parser.add_argument("--symbols", default="EURUSD,US500,DAX,US100",
                        help="Comma-separated symbols (default: EURUSD,US500,DAX,US100)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print configs without making API calls")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",")]
    for s in symbols:
        if s not in SYMBOL_MAP:
            print(f"Unknown symbol '{s}'. Supported: {list(SYMBOL_MAP)}")
            sys.exit(1)

    if args.dry_run:
        for s in symbols:
            print(f"[dry-run] {s} {TIMEFRAME} -> symbol={SYMBOL_MAP[s]} interval={INTERVAL} "
                  f"outputsize={OUTPUTSIZE}")
        print("\nDry run complete — no API calls made, no files written.")
        return

    CACHE_DIR.mkdir(exist_ok=True)

    summary = []
    for i, symbol in enumerate(symbols):
        if i > 0:
            print(f"Sleeping {SLEEP_SECONDS}s (rate limit)...")
            time.sleep(SLEEP_SECONDS)

        td_symbol = SYMBOL_MAP[symbol]
        print(f"Fetching {symbol} {TIMEFRAME} ({td_symbol})...")
        data = _request(td_symbol)
        candles = _parse_candles(data)

        out_path = CACHE_DIR / f"{symbol}_{TIMEFRAME}_AV.json"
        with open(out_path, "w") as f:
            json.dump(candles, f)

        if candles:
            start, end = candles[0]["time"][:10], candles[-1]["time"][:10]
            print(f"  Saved {len(candles):,} candles to {out_path}")
            summary.append((symbol, len(candles), start, end))
        else:
            print(f"  WARNING: 0 candles returned for {symbol}")
            summary.append((symbol, 0, "-", "-"))

    print("\nSummary:")
    header = f"{'Symbol':<8} {'TF':<6} {'Candles':>9}  {'Date Range'}"
    print(header)
    print("-" * len(header))
    for symbol, count, start, end in summary:
        print(f"{symbol:<8} {TIMEFRAME:<6} {count:>9,}  {start} to {end}")


if __name__ == "__main__":
    main()
