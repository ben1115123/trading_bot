#!/usr/bin/env python3
"""
Fetch HOUR historical OHLCV candles from yfinance in date-range
chunks and stitch into one cache file per symbol — works around
yfinance's per-request limits.

15MIN requires Twelve Data — see fetch_twelvedata.py
(Yahoo only retains ~60 days of 15m history total, regardless of
requested date range — confirmed not viable for 2yr 15MIN data.)

Output cache files use the "AV" suffix for run_backtest.py
compatibility (--source alphavantage):
  scripts/candle_cache/{SYMBOL}_HOUR_AV.json

Usage:
  python3 scripts/fetch_historical.py
  python3 scripts/fetch_historical.py --symbol EURUSD
  python3 scripts/fetch_historical.py --dry-run
"""
import argparse
import json
import time
from datetime import date, timedelta
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent / "candle_cache"
SLEEP_SECONDS = 1
TIMEFRAME = "HOUR"

SYMBOL_MAP = {
    "US500":  "^GSPC",
    "EURUSD": "EURUSD=X",
    "DAX":    "^GDAXI",
    "US100":  "^NDX",
}

TF_CONFIG = {"interval": "1h", "total_days": 1825, "chunk_days": 720}


def _date_chunks(total_days: int, chunk_days: int) -> list:
    end_date = date.today()
    start_date = end_date - timedelta(days=total_days)
    chunks = []
    current = start_date
    while current < end_date:
        chunk_end = min(current + timedelta(days=chunk_days), end_date)
        chunks.append((current, chunk_end))
        current = chunk_end
    return chunks


def _fetch_chunk(ticker: str, interval: str, start: date, end: date) -> list:
    import yfinance as yf
    df = yf.download(ticker, start=start.isoformat(), end=end.isoformat(),
                     interval=interval, auto_adjust=True, progress=False)
    if df.empty:
        return []
    candles = []
    for ts, row in df.iterrows():
        try:
            def _get(col):
                val = row[col]
                return float(val.iloc[0]) if hasattr(val, "iloc") else float(val)
            o, h, l, c = _get("Open"), _get("High"), _get("Low"), _get("Close")
        except Exception:
            continue
        if any(v != v for v in [o, h, l, c]):
            continue
        try:
            vol = _get("Volume")
        except Exception:
            vol = 0.0
        candles.append({"time": str(ts), "open": o, "high": h, "low": l, "close": c, "volume": vol})
    return candles


def fetch_symbol(symbol: str, dry_run: bool = False) -> list:
    ticker = SYMBOL_MAP[symbol]
    chunks = _date_chunks(TF_CONFIG["total_days"], TF_CONFIG["chunk_days"])

    if dry_run:
        print(f"[dry-run] {symbol} {TIMEFRAME} ({ticker}, interval={TF_CONFIG['interval']}): "
              f"{len(chunks)} chunks, {chunks[0][0]} to {chunks[-1][1]}")
        return []

    all_candles = []
    for i, (chunk_start, chunk_end) in enumerate(chunks, 1):
        if i > 1:
            time.sleep(SLEEP_SECONDS)
        candles = _fetch_chunk(ticker, TF_CONFIG["interval"], chunk_start, chunk_end)
        print(f"  {symbol} {TIMEFRAME}: chunk {i}/{len(chunks)} "
              f"({chunk_start} to {chunk_end})... {len(candles):,} candles")
        all_candles.extend(candles)

    seen = {}
    for c in all_candles:
        seen[c["time"]] = c
    merged = sorted(seen.values(), key=lambda c: c["time"])
    return merged


def main():
    parser = argparse.ArgumentParser(description="Fetch chunked HOUR candles via yfinance.")
    parser.add_argument("--symbol", default=None, choices=list(SYMBOL_MAP),
                        help="Single symbol (default: all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print fetch plan without making API calls")
    args = parser.parse_args()

    symbols = [args.symbol] if args.symbol else list(SYMBOL_MAP)

    if not args.dry_run:
        CACHE_DIR.mkdir(exist_ok=True)

    summary = []
    for symbol in symbols:
        candles = fetch_symbol(symbol, dry_run=args.dry_run)

        if args.dry_run:
            continue

        out_path = CACHE_DIR / f"{symbol}_{TIMEFRAME}_AV.json"
        with open(out_path, "w") as f:
            json.dump(candles, f)

        if candles:
            start, end = candles[0]["time"][:10], candles[-1]["time"][:10]
            print(f"  {symbol} {TIMEFRAME}: complete — {len(candles):,} candles saved")
            print(f"  ({start} to {end})")
            summary.append((symbol, len(candles), start, end))
        else:
            print(f"  {symbol} {TIMEFRAME}: complete — 0 candles saved")
            summary.append((symbol, 0, "-", "-"))

    if args.dry_run:
        print("\nDry run complete — no API calls made, no files written.")
        return

    print("\nSummary:")
    header = f"{'Symbol':<8} {'TF':<6} {'Candles':>9}  {'Date Range'}"
    print(header)
    print("-" * len(header))
    for symbol, count, start, end in summary:
        print(f"{symbol:<8} {TIMEFRAME:<6} {count:>9,}  {start} to {end}")


if __name__ == "__main__":
    main()
