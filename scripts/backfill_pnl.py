#!/usr/bin/env python3
"""
Backfill pnl for CLOSED trades where pnl IS NULL.

Usage:
    python scripts/backfill_pnl.py           # dry run — prints findings, writes nothing
    python scripts/backfill_pnl.py --confirm # apply updates
"""
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.db import get_connection
from data.positions_poller import _fetch_close_data

LOOKBACK_HOURS = 120


def _get_closed_trades_missing_pnl() -> list:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, deal_id, deal_reference, timestamp, symbol, direction
            FROM trades
            WHERE pnl IS NULL AND status = 'CLOSED'
            ORDER BY id ASC
        """)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def _apply_update(trade_id: int, close_price, close_time, pnl) -> int:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE trades
            SET close_price = ?,
                close_time  = ?,
                pnl         = ?
            WHERE id = ?
              AND pnl IS NULL
        """, (close_price, close_time, pnl, trade_id))
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Backfill missing P&L for closed trades")
    parser.add_argument("--confirm", action="store_true", help="Write updates (default: dry run)")
    args = parser.parse_args()

    print("Initializing IG session...")
    from bot.execute_trade import ig_service, ensure_session
    ensure_session()

    print("\n--- DIAGNOSTIC: IG transaction history ---")
    _from_dt = datetime.utcnow() - timedelta(hours=LOOKBACK_HOURS)
    _txns = ig_service.fetch_transaction_history(trans_type="ALL_DEAL", from_date=_from_dt)
    if _txns is None or _txns.empty:
        print("fetch_transaction_history returned empty/None")
    else:
        print(f"txn rows returned: {len(_txns)}")
        print(f"txn columns: {list(_txns.columns)}")
        if "openDateUtc" in _txns.columns:
            print(f"openDateUtc sample: {_txns['openDateUtc'].tolist()[:5]}")
        if "reference" in _txns.columns:
            print(f"reference sample:   {_txns['reference'].tolist()[:5]}")
    print("--- END DIAGNOSTIC ---\n")

    trades = _get_closed_trades_missing_pnl()
    if not trades:
        print("No closed trades with pnl=NULL. Nothing to do.")
        return

    print(f"\nFound {len(trades)} closed trade(s) with pnl=NULL:\n")

    findings = []

    for t in trades:
        deal_id       = t["deal_id"]
        deal_reference = t.get("deal_reference")
        print(f"  id={t['id']}  {t['symbol']} {t['direction']}")
        print(f"    deal_id={deal_id}  deal_reference={deal_reference}")
        print(f"    entry_time={t.get('timestamp')}")

        # Primary: match via deal_reference (for trades placed after this fix)
        close_data = _fetch_close_data(
            ig_service,
            deal_id,
            deal_reference=deal_reference,
            entry_time=t.get("timestamp"),
            lookback_hours=LOOKBACK_HOURS,
        )

        # Secondary: try deal_id as the reference value (old trades pre-fix,
        # where deal_reference column was NULL — IG may have echoed dealId instead)
        if close_data is None and deal_reference is None and deal_id:
            print(f"    deal_reference missing — retrying with deal_id as reference...")
            close_data = _fetch_close_data(
                ig_service,
                deal_id,
                deal_reference=deal_id,
                entry_time=t.get("timestamp"),
                lookback_hours=LOOKBACK_HOURS,
            )

        if close_data:
            print(f"    FOUND  close_price={close_data['close_price']}  "
                  f"pnl={close_data['realised_pnl']}  "
                  f"close_time={close_data['close_time']}")
            findings.append((t["id"], close_data))
        else:
            print(f"    NOT FOUND in transaction history — will remain NULL")

        print()

    print("=" * 55)
    print(f"Matches: {len(findings)} / {len(trades)}")

    if not findings:
        print("Nothing to update.")
        return

    if not args.confirm:
        print("\nDry run — no changes written.")
        print("Re-run with --confirm to apply.")
        return

    print("\nApplying updates...")
    for trade_id, close_data in findings:
        rows = _apply_update(
            trade_id,
            close_data["close_price"],
            close_data["close_time"],
            close_data["realised_pnl"],
        )
        if rows:
            print(f"  id={trade_id}  pnl={close_data['realised_pnl']}  UPDATED")
        else:
            print(f"  id={trade_id}  skipped (pnl already set by concurrent write)")

    print("\nDone.")


if __name__ == "__main__":
    main()
