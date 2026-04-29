#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.db import get_connection
from database.models import close_trade
from data.positions_poller import _parse_pnl, _to_float


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


def sync_ig_trades(days: int = 7, confirm: bool = False) -> dict:
    print("Initializing IG session...")
    from bot.execute_trade import ig_service, ensure_session
    ensure_session()

    from_dt = datetime.utcnow() - timedelta(days=days)
    print(f"Fetching IG transactions since {from_dt.strftime('%Y-%m-%d')}...")

    try:
        transactions = ig_service.fetch_transaction_history(
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

    closed = filled = skipped = 0

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
            print(f"  SKIP  ref={ref} — not in DB")
            skipped += 1
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
    print(f"  Closed (OPEN → CLOSED): {closed}")
    print(f"  Filled (missing P&L):   {filled}")
    print(f"  Skipped (no change):    {skipped}")
    if not confirm and (closed + filled) > 0:
        print("\nRe-run with --confirm to apply changes.")

    return {"closed": closed, "filled": filled, "skipped": skipped}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync closed trades from IG transaction history")
    parser.add_argument("--days",    type=int, default=7,   help="Lookback window in days (default: 7)")
    parser.add_argument("--confirm", action="store_true",   help="Apply changes (default: dry run)")
    args = parser.parse_args()
    sync_ig_trades(days=args.days, confirm=args.confirm)
