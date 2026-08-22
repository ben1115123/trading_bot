#!/usr/bin/env python3
"""
Fetch 15MIN candles from Twelve Data and save to the candle
cache for run_backtest.py (--source alphavantage).

Free key: twelvedata.com (no credit card)
Read from .env: TWELVEDATA_API_KEY=your_key_here

Free tier: 8 requests/minute — 8s sleep between calls.

Paginates via end_date to fetch further back than one
5000-candle batch:
  EURUSD (24hr market): 6 batches  -> ~10 months, ~20,000 candles
  US500/DAX/US100 (market hours): 2 batches -> ~18 months, ~10,000 candles

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
    "GBPUSD": "GBP/USD",
    "USDJPY": "USD/JPY",
    "EURGBP": "EUR/GBP",
    "NZDUSD": "NZD/USD",
    # Merged in from an uncommitted VPS-side edit, 2026-08-22. Both machines
    # had diverging uncommitted changes to these two dicts; this is the union.
    "AUDUSD": "AUD/USD",
    "USDCAD": "USD/CAD",
}

# Number of 5000-candle batches per symbol (paginated via end_date)
BATCH_COUNT = {
    "EURUSD": 6,
    "US500":  2,
    "DAX":    2,
    "US100":  2,
    "GBPUSD": 6,
    "USDJPY": 6,
    "EURGBP": 6,
    "NZDUSD": 6,
    "AUDUSD": 6,
    "USDCAD": 6,
}


def _request(td_symbol: str, end_date: str = None, start_date: str = None) -> dict:
    api_key = os.getenv("TWELVEDATA_API_KEY")
    if not api_key:
        raise RuntimeError("TWELVEDATA_API_KEY not set in .env")
    params = {
        "symbol": td_symbol,
        "interval": INTERVAL,
        "outputsize": OUTPUTSIZE,
        "apikey": api_key,
    }
    if end_date:
        params["end_date"] = end_date
    if start_date:
        params["start_date"] = start_date
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


def _load_existing_cache(symbol: str) -> list:
    path = CACHE_DIR / f"{symbol}_{TIMEFRAME}_AV.json"
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def fetch_symbol(symbol: str, sleep_before_first: bool, incremental: bool = False) -> list:
    td_symbol = SYMBOL_MAP[symbol]

    if incremental:
        existing = _load_existing_cache(symbol)
        if existing:
            last_ts = existing[-1]["time"]
            print(f"Incremental mode: {len(existing):,} cached candles, latest={last_ts}")
            if sleep_before_first:
                print(f"Sleeping {SLEEP_SECONDS}s (rate limit)...")
                time.sleep(SLEEP_SECONDS)
            print(f"Fetching {symbol} {TIMEFRAME} ({td_symbol}) latest batch (start_date={last_ts})...")
            data = _request(td_symbol, start_date=last_ts)
            new_candles = _parse_candles(data)
            added = [c for c in new_candles if c["time"] > last_ts]
            print(f"  {len(new_candles):,} candles returned, {len(added):,} new since {last_ts}")
            if not added:
                print(f"  No new candles — cache already up to date.")
                return existing
            all_candles = existing + added
            seen = {}
            for c in all_candles:
                seen[c["time"]] = c
            return sorted(seen.values(), key=lambda c: c["time"])
        else:
            print(f"No existing cache for {symbol} — falling back to full fetch.")

    num_batches = BATCH_COUNT[symbol]
    all_candles = []
    end_date = None
    for batch in range(1, num_batches + 1):
        if batch > 1 or sleep_before_first:
            print(f"Sleeping {SLEEP_SECONDS}s (rate limit)...")
            time.sleep(SLEEP_SECONDS)

        suffix = f" (end_date={end_date})" if end_date else ""
        print(f"Fetching {symbol} {TIMEFRAME} ({td_symbol}) batch {batch}/{num_batches}{suffix}...")
        data = _request(td_symbol, end_date=end_date)
        candles = _parse_candles(data)

        if not candles:
            print(f"  batch {batch}: 0 candles — stopping pagination")
            break

        print(f"  batch {batch}: {len(candles):,} candles ({candles[0]['time']} to {candles[-1]['time']})")
        all_candles.extend(candles)

        if len(candles) < OUTPUTSIZE:
            print(f"  batch {batch}: returned < {OUTPUTSIZE} — no more history, stopping pagination")
            break

        end_date = candles[0]["time"]

    seen = {}
    for c in all_candles:
        seen[c["time"]] = c
    return sorted(seen.values(), key=lambda c: c["time"])


def main():
    parser = argparse.ArgumentParser(description="Fetch 15MIN candles from Twelve Data (paginated).")
    parser.add_argument("--symbols", default="EURUSD,US500,DAX,US100",
                        help="Comma-separated symbols (default: EURUSD,US500,DAX,US100)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print configs without making API calls")
    parser.add_argument("--incremental", action="store_true",
                        help="Only fetch candles newer than the existing cache (1 API call per symbol)")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",")]
    for s in symbols:
        if s not in SYMBOL_MAP:
            print(f"Unknown symbol '{s}'. Supported: {list(SYMBOL_MAP)}")
            sys.exit(1)

    if args.dry_run:
        for s in symbols:
            num_batches = BATCH_COUNT[s]
            print(f"[dry-run] {s} {TIMEFRAME} -> symbol={SYMBOL_MAP[s]} interval={INTERVAL} "
                  f"outputsize={OUTPUTSIZE} batches={num_batches} "
                  f"(target ~{num_batches * OUTPUTSIZE:,} candles)")
        print("\nDry run complete — no API calls made, no files written.")
        return

    CACHE_DIR.mkdir(exist_ok=True)

    summary = []
    for i, symbol in enumerate(symbols):
        candles = fetch_symbol(symbol, sleep_before_first=(i > 0), incremental=args.incremental)

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
