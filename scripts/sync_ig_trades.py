#!/usr/bin/env python3
import os
import sys
import argparse
import json
import re
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from trading_ig import IGService
from database.db import get_connection
from database.models import close_trade

INSTRUMENT_TO_SYMBOL = {
    "US 500 Cash ($1)":      "US500",
    "US Tech 100 Cash ($1)": "US100",
    "Bitcoin ($0.1)":        "BTC",
    "Spot Gold ($1)":        "XAUUSD",
    "Germany 40 Cash (£1)":  "DAX",
    "EUR/USD Mini":          "EURUSD",  # CS.D.EURUSD.MINI.IP — verify name on first live trade
}


def _parse_pnl(raw) -> float | None:
    if raw is None:
        return None
    try:
        return float(re.sub(r"[^0-9.\-]", "", str(raw).replace("+", "")))
    except (ValueError, TypeError):
        return None


def _to_float(val) -> float | None:
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def _get_trade_by_reference(ref: str) -> dict | None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM trades WHERE deal_reference = ? OR deal_id = ? LIMIT 1",
            (ref, ref),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _insert_imported_trade(data: dict) -> int:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO trades
            (timestamp, symbol, direction, size, entry_price,
             deal_reference, close_price, close_time, pnl,
             source, strategy_name, status)
            VALUES
            (:timestamp, :symbol, :direction, :size, :entry_price,
             :deal_reference, :close_price, :close_time, :pnl,
             :source, :strategy_name, :status)
        """, data)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _fill_pnl(trade_id: int, close_price, close_time, pnl) -> None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE trades SET close_price = ?, close_time = ?, pnl = ?
            WHERE id = ? AND pnl IS NULL
        """, (close_price, close_time, pnl, trade_id))
        conn.commit()
    finally:
        conn.close()


def _get_trade_by_open(symbol: str, direction: str,
                       open_level: float, open_date: str) -> dict | None:
    """
    Fallback lookup when IG transaction reference (8-char) doesn't match
    stored deal_reference (16-char). Matches by symbol + direction + entry
    price + date. No status filter — poller may have CLOSED the trade already
    while pnl remains NULL.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM trades
            WHERE symbol = ?
            AND direction = ?
            AND ABS(entry_price - ?) < 1.0
            AND DATE(timestamp) = DATE(?)
            AND pnl IS NULL
            LIMIT 1
        """, (symbol, direction, open_level, open_date))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _is_already_logged(ref: str, symbol: str, direction: str,
                        entry_price: float | None, open_time: str) -> bool:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id FROM trades
            WHERE deal_reference = ?
            AND source != 'ig_import'
        """, (ref,))
        if cur.fetchone():
            return True
        if entry_price is not None:
            cur.execute("""
                SELECT id FROM trades
                WHERE symbol = ? AND direction = ?
                AND ABS(entry_price - ?) < 1.0
                AND source IN ('tradingview_webhook',
                               'live_signal_loop', 'signal_loop')
                AND DATE(timestamp) = DATE(?)
            """, (symbol, direction, entry_price, open_time))
            if cur.fetchone():
                return True
        return False
    finally:
        conn.close()


def sync_ig_trades(days: int = 7, confirm: bool = False) -> dict:
    print("Initializing IG session...")
    ig = IGService(
        os.getenv("IG_USERNAME"),
        os.getenv("IG_PASSWORD"),
        os.getenv("IG_API_KEY"),
        acc_type="LIVE",
    )
    ig.create_session()

    from_dt = datetime.utcnow() - timedelta(days=days)
    print(f"Fetching IG transactions since {from_dt.strftime('%Y-%m-%d')}...")

    try:
        transactions = ig.fetch_transaction_history(
            trans_type="ALL_DEAL",
            from_date=from_dt,
        )
    except Exception as e:
        print(f"ERROR fetching transactions: {e}")
        return {"closed": 0, "filled": 0, "skipped": 0, "error": str(e)}

    if transactions is None or transactions.empty:
        print("No transactions returned from IG.")
        return {"closed": 0, "filled": 0, "skipped": 0}

    print(f"Found {len(transactions)} transaction(s)\n")

    inserted = closed = filled = skipped = 0

    for _, tx in transactions.iterrows():
        ref         = str(tx.get("reference", "") or "").strip()
        close_price = _to_float(tx.get("closeLevel"))
        close_time  = str(tx.get("dateUtc") or datetime.now(timezone.utc).isoformat())
        pnl         = _parse_pnl(tx.get("profitAndLoss"))

        if not ref:
            skipped += 1
            continue

        trade = _get_trade_by_reference(ref)

        if trade is None:
            instrument = str(tx.get("instrumentName", "")).strip()
            symbol = INSTRUMENT_TO_SYMBOL.get(instrument)
            if symbol is None:
                print(f"  SKIP  ref={ref} instrument={instrument!r} — unknown")
                skipped += 1
                continue
            size_raw   = str(tx.get("size", "0")).strip()
            size       = abs(_to_float(size_raw) or 0.0)
            direction  = "BUY" if not size_raw.startswith("-") else "SELL"
            open_time  = str(tx.get("openDateUtc") or close_time)
            entry_price = _to_float(tx.get("openLevel"))
            if _is_already_logged(ref, symbol, direction, entry_price, open_time):
                open_direction = "SELL" if direction == "BUY" else "BUY"
                fill_trade = _get_trade_by_open(
                    symbol, open_direction, entry_price, open_time
                )
                if fill_trade and fill_trade["pnl"] is None:
                    print(f"  FILL  fallback id={fill_trade['id']} "
                          f"{symbol} {open_direction} @ {entry_price} pnl={pnl}")
                    if confirm:
                        _fill_pnl(fill_trade["id"], close_price, close_time, pnl)
                    filled += 1
                    continue
                print(f"  SKIP  ref={ref} {symbol} {direction} @ {entry_price} — already logged")
                skipped += 1
                continue
            print(f"  INSERT ref={ref} {symbol} {direction} size={size} entry={entry_price} pnl={pnl}")
            if confirm:
                _insert_imported_trade({
                    "timestamp":      open_time,
                    "symbol":         symbol,
                    "direction":      direction,
                    "size":           size,
                    "entry_price":    entry_price,
                    "deal_reference": ref,
                    "close_price":    close_price,
                    "close_time":     close_time,
                    "pnl":            pnl,
                    "source":         "ig_import",
                    "strategy_name":  "manual",
                    "status":         "CLOSED",
                })
            inserted += 1
            continue

        if trade["status"] == "OPEN":
            print(f"  CLOSE id={trade['id']} ref={ref} pnl={pnl} close_price={close_price}")
            if confirm:
                close_trade(trade["deal_id"], close_price, close_time, pnl)
            closed += 1

        elif trade["pnl"] is None:
            print(f"  FILL  id={trade['id']} ref={ref} pnl={pnl}")
            if confirm:
                _fill_pnl(trade["id"], close_price, close_time, pnl)
            filled += 1

        else:
            skipped += 1

    print(f"\n{'Applied' if confirm else '[Dry run]'}:")
    print(f"  Inserted (new import):  {inserted}")
    print(f"  Closed (OPEN → CLOSED): {closed}")
    print(f"  Filled (missing P&L):   {filled}")
    print(f"  Skipped (no change):    {skipped}")
    if not confirm and (inserted + closed + filled) > 0:
        print("\nRe-run with --confirm to apply changes.")
    print(json.dumps({"inserted": inserted, "closed": closed, "filled": filled, "skipped": skipped}))

    return {"inserted": inserted, "closed": closed, "filled": filled, "skipped": skipped}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync closed trades from IG transaction history")
    parser.add_argument("--days",    type=int, default=7,   help="Lookback window in days (default: 7)")
    parser.add_argument("--confirm", action="store_true",   help="Apply changes (default: dry run)")
    args = parser.parse_args()
    sync_ig_trades(days=args.days, confirm=args.confirm)
