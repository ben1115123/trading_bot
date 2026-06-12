#!/usr/bin/env python3
"""
Resolve blocked webhook alerts: would they have won or lost if executed?

For each unresolved BLOCKED alert (last 7 days, with SL/TP in raw_payload),
fetch 15MIN candles after the block timestamp and check whether SL or TP
would have been hit first within 20 candles. Writes results to
webhook_outcome_log.

Usage:
    python scripts/resolve_webhook_outcomes.py            # resolve + write
    python scripts/resolve_webhook_outcomes.py --dry-run  # print only
"""
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from database.db import get_connection
from database.models import get_unresolved_blocked_alerts, insert_webhook_outcome
from scripts.run_backtest import _fetch_yfinance_candles, YF_SYMBOLS

TIMEFRAME    = "15MIN"
CANDLE_COUNT = 2000
MAX_CANDLES  = 20
ESTIMATED_PNL = {"WIN": 15.00, "LOSS": -15.00}


def _resolve_one(alert: dict, candles: list) -> dict:
    """Determine outcome for a single blocked alert against fetched candles."""
    block_ts = pd.to_datetime(alert["timestamp"], utc=True)
    direction = alert["direction"]
    sl = alert["sl_price"]
    tp = alert["tp_price"]

    future = []
    for c in candles:
        try:
            ctime = pd.to_datetime(c["time"], utc=True)
        except Exception:
            continue
        if ctime > block_ts:
            future.append((ctime, c))

    future.sort(key=lambda x: x[0])
    future = future[:MAX_CANDLES]

    age = datetime.now(timezone.utc) - block_ts.to_pydatetime()
    if age > timedelta(days=7) and not future:
        return {"outcome": "EXPIRED", "candles_to_hit": None,
                "price_at_outcome": None, "outcome_at": None}

    for idx, (ctime, c) in enumerate(future, start=1):
        if direction == "BUY":
            if c["low"] <= sl:
                return {"outcome": "LOSS", "candles_to_hit": idx,
                        "price_at_outcome": sl, "outcome_at": str(ctime)}
            if c["high"] >= tp:
                return {"outcome": "WIN", "candles_to_hit": idx,
                        "price_at_outcome": tp, "outcome_at": str(ctime)}
        elif direction == "SELL":
            if c["high"] >= sl:
                return {"outcome": "LOSS", "candles_to_hit": idx,
                        "price_at_outcome": sl, "outcome_at": str(ctime)}
            if c["low"] <= tp:
                return {"outcome": "WIN", "candles_to_hit": idx,
                        "price_at_outcome": tp, "outcome_at": str(ctime)}

    return {"outcome": "UNKNOWN", "candles_to_hit": None,
            "price_at_outcome": None, "outcome_at": None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                         help="Print what would be resolved without writing to DB")
    args = parser.parse_args()

    conn = get_connection()
    try:
        alerts = get_unresolved_blocked_alerts(conn, limit=100)
    finally:
        if args.dry_run:
            conn.close()

    if not alerts:
        print("0 alerts to resolve.")
        if not args.dry_run:
            conn.close()
        return

    print(f"{len(alerts)} unresolved blocked alerts with valid SL/TP found.")

    # Group by symbol to limit yfinance calls
    by_symbol: dict = {}
    for a in alerts:
        by_symbol.setdefault(a["symbol"], []).append(a)

    candles_by_symbol: dict = {}
    for symbol in by_symbol:
        if symbol.upper() not in YF_SYMBOLS:
            print(f"  Skipping {symbol}: no yfinance mapping")
            continue
        try:
            candles_by_symbol[symbol] = _fetch_yfinance_candles(symbol, TIMEFRAME, CANDLE_COUNT)
        except Exception as e:
            print(f"  ERROR fetching candles for {symbol}: {e}")
            candles_by_symbol[symbol] = []
        time.sleep(1)

    resolved = 0
    skipped = 0

    for alert in alerts:
        symbol = alert["symbol"]
        candles = candles_by_symbol.get(symbol, [])
        if not candles:
            skipped += 1
            continue

        try:
            result = _resolve_one(alert, candles)
        except Exception as e:
            print(f"  ERROR resolving alert id={alert['id']}: {e}")
            skipped += 1
            continue

        block_time_str = alert["timestamp"]
        try:
            block_hhmm = pd.to_datetime(block_time_str, utc=True).strftime("%H:%M")
        except Exception:
            block_hhmm = block_time_str

        outcome = result["outcome"]
        if outcome in ("WIN", "LOSS"):
            detail = f"({'TP' if outcome == 'WIN' else 'SL'} hit at candle {result['candles_to_hit']})"
        else:
            detail = ""
        print(
            f"Resolved: {symbol} {alert['direction']} blocked at {block_hhmm} "
            f"→ {outcome} {detail}".strip()
        )

        if args.dry_run:
            resolved += 1
            continue

        estimated_pnl = ESTIMATED_PNL.get(outcome)
        insert_webhook_outcome(conn, {
            "webhook_log_id":   alert["id"],
            "symbol":           symbol,
            "direction":        alert["direction"],
            "block_reason":     alert["block_reason"],
            "block_timestamp":  alert["timestamp"],
            "sl_price":         alert["sl_price"],
            "tp_price":         alert["tp_price"],
            "outcome":          outcome,
            "outcome_at":       result["outcome_at"],
            "candles_to_hit":   result["candles_to_hit"],
            "price_at_outcome": result["price_at_outcome"],
            "estimated_pnl":    estimated_pnl,
            "resolved_at":      datetime.now(timezone.utc).isoformat(),
        })
        resolved += 1

    if not args.dry_run:
        conn.close()

    print(f"\n{resolved} alerts resolved, {skipped} skipped.")


if __name__ == "__main__":
    main()
