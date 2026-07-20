#!/usr/bin/env python3
"""
Ledger re-audit — cross-checks every CLOSED trade since the demo switch
(2026-07-08) against IG's real transaction history to find rows where
data/positions_poller.py's pre-fix fallback matcher (unfiltered by symbol)
borrowed a sibling trade's close_price/pnl instead of the trade's own.

Root cause fixed in data/positions_poller.py on 2026-07-20 (see CLAUDE.md).
This script is the one-time (re-runnable) ledger correction for damage done
before that fix landed.

Dry run (default): reports every contaminated row, corrects nothing.
--confirm: backs up trades.db, applies corrections, logs each correction
           to logs/ledger_reaudit_<UTC timestamp>.jsonl.

Read-only against IG (transaction history fetch only, no orders placed).
"""
import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from trading_ig import IGService
from database.db import get_connection, DATABASE_PATH
from ig_env import get_ig_credentials
import ig_scale

# Same map as data/positions_poller.py's fix — confirmed live against this
# account 2026-07-20 via fetch_market_by_epic per symbol.
INSTRUMENT_TO_SYMBOL = {
    "US 500 Cash ($1)":      "US500",
    "US Tech 100 Cash ($1)": "US100",
    "Germany 40 Cash ($1)":  "DAX",
    "Bitcoin ($0.1)":        "BTC",
    "EUR/USD Mini":          "EURUSD",
    "GBP/USD Mini":          "GBPUSD",
    "AUD/USD Mini":          "AUDUSD",
    "USD/CAD Mini":          "USDCAD",
}

DEMO_SWITCH = "2026-07-08T00:00:00+00:00"

# Local epic map for ig_scale classification only -- deliberately not
# importing bot.execute_trade (its module-level recreate_session() would
# open a second IG session), same rationale as sync_ig_trades.py.
_EPIC_MAP_FOR_SCALE = {
    "US500":  "IX.D.SPTRD.IFMM.IP",
    "US100":  "IX.D.NASDAQ.IFMM.IP",
    "BTC":    "CS.D.BITCOIN.CFBMU.IP",
    "DAX":    "IX.D.DAX.IFMS.IP",
    "EURUSD": "CS.D.EURUSD.MINI.IP",
    "GBPUSD": "CS.D.GBPUSD.MINI.IP",
    "USDCAD": "CS.D.USDCAD.MINI.IP",
    "AUDUSD": "CS.D.AUDUSD.MINI.IP",
}

CLOSE_TOL = 0.00005   # relative tolerance on close_price
PNL_TOL   = 0.02      # absolute tolerance ($) on pnl


def _parse_pnl(raw):
    if raw is None:
        return None
    try:
        return float(re.sub(r"[^0-9.\-]", "", str(raw).replace("+", "")))
    except (ValueError, TypeError):
        return None


def _to_float(val):
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def _parse_dt(raw):
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def main(confirm: bool):
    print("Connecting to IG (read-only session — transaction history only, no orders)...")
    username, password, api_key, acc_type = get_ig_credentials()
    ig = IGService(username, password, api_key, acc_type=acc_type)
    ig.create_session()
    ig_scale.init_price_scales(ig, _EPIC_MAP_FOR_SCALE, force=True)

    from_dt = _parse_dt(DEMO_SWITCH) - timedelta(days=1)
    tx = ig.fetch_transaction_history(trans_type="ALL_DEAL", from_date=from_dt.replace(tzinfo=None), page_size=500)
    if tx is None or tx.empty:
        print("No transactions returned from IG — aborting, nothing to audit against.")
        return
    print(f"Fetched {len(tx)} IG transactions since {from_dt.date()}")

    by_ref = {}
    for _, row in tx.iterrows():
        ref = str(row.get("reference", "") or "").strip()
        if ref:
            by_ref.setdefault(ref, []).append(row)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, deal_id, deal_reference, symbol, direction, timestamp,
               close_price, close_time, pnl, status, source
        FROM trades
        WHERE status = 'CLOSED'
          AND timestamp >= ?
        ORDER BY id
    """, (DEMO_SWITCH,))
    trades = [dict(r) for r in cur.fetchall()]
    print(f"Auditing {len(trades)} closed trades since demo switch (2026-07-08)...\n")

    contaminated = []
    unmatched = []
    ambiguous = []

    for t in trades:
        ref = t.get("deal_reference")
        match_row = None

        if ref and ref in by_ref:
            rows = by_ref[ref]
            if len(rows) == 1:
                match_row = rows[0]
            else:
                ambiguous.append({"id": t["id"], "reason": f"{len(rows)} tx rows share reference {ref}"})
                continue
        else:
            entry_dt = _parse_dt(t["timestamp"])
            if entry_dt is None:
                unmatched.append({"id": t["id"], "reason": "unparseable entry timestamp"})
                continue
            candidates = []
            for _, row in tx.iterrows():
                inst = str(row.get("instrumentName", "")).strip()
                if INSTRUMENT_TO_SYMBOL.get(inst) != t["symbol"]:
                    continue
                odt = _parse_dt(row.get("openDateUtc"))
                if odt is None:
                    continue
                if abs((odt - entry_dt).total_seconds()) < 60:
                    candidates.append(row)
            if len(candidates) == 1:
                match_row = candidates[0]
            elif len(candidates) > 1:
                ambiguous.append({"id": t["id"], "symbol": t["symbol"],
                                   "reason": f"{len(candidates)} same-symbol candidates within 60s, no reference to disambiguate"})
                continue
            else:
                unmatched.append({"id": t["id"], "symbol": t["symbol"], "reason": "no matching IG transaction found"})
                continue

        true_close = ig_scale.to_decimal(t["symbol"], _to_float(match_row.get("closeLevel")))
        true_pnl = _parse_pnl(match_row.get("profitAndLoss"))

        stored_close = t.get("close_price")
        stored_pnl = t.get("pnl")

        close_bad = (
            true_close is not None and
            (stored_close is None or abs(stored_close - true_close) > CLOSE_TOL * max(1.0, abs(true_close)))
        )
        pnl_bad = (
            true_pnl is not None and
            (stored_pnl is None or abs(stored_pnl - true_pnl) > PNL_TOL)
        )

        if close_bad or pnl_bad:
            contaminated.append({
                "id": t["id"], "deal_id": t["deal_id"], "symbol": t["symbol"],
                "direction": t["direction"], "timestamp": t["timestamp"],
                "stored_close_price": stored_close, "true_close_price": true_close,
                "stored_pnl": stored_pnl, "true_pnl": true_pnl,
                "matched_reference": str(match_row.get("reference")),
            })

    print("=== RESULTS ===")
    print(f"Total closed trades audited: {len(trades)}")
    print(f"Matched cleanly, no contamination: {len(trades) - len(contaminated) - len(unmatched) - len(ambiguous)}")
    print(f"Contaminated rows found:           {len(contaminated)}")
    print(f"Unmatched (no IG tx found):         {len(unmatched)}")
    print(f"Ambiguous (multiple candidates):    {len(ambiguous)}")

    if contaminated:
        print("\n--- Contaminated rows (stored vs true) ---")
        for c in contaminated:
            print(json.dumps(c))
    if unmatched:
        print("\n--- Unmatched ---")
        for u in unmatched:
            print(json.dumps(u))
    if ambiguous:
        print("\n--- Ambiguous ---")
        for a in ambiguous:
            print(json.dumps(a))

    if not confirm:
        print(f"\n[Dry run] {len(contaminated)} row(s) would be corrected. Re-run with --confirm to back up DB and apply.")
        conn.close()
        return

    if not contaminated:
        print("\nNothing to correct.")
        conn.close()
        return

    db_path = Path(DATABASE_PATH)
    backup_path = db_path.with_name(f"{db_path.stem}.bak-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}{db_path.suffix}")
    shutil.copy2(db_path, backup_path)
    print(f"\nBacked up DB to {backup_path}")

    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"ledger_reaudit_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.jsonl"

    applied = 0
    with open(log_path, "w") as logf:
        for c in contaminated:
            cur.execute(
                "UPDATE trades SET close_price = ?, pnl = ? WHERE id = ?",
                (c["true_close_price"], c["true_pnl"], c["id"]),
            )
            logf.write(json.dumps({**c, "corrected_at": datetime.now(timezone.utc).isoformat()}) + "\n")
            applied += 1
        conn.commit()

    print(f"Applied {applied} correction(s). Audit log: {log_path}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-audit trades ledger close_price/pnl against real IG transaction history")
    parser.add_argument("--confirm", action="store_true", help="Back up DB and apply corrections (default: dry run, report only)")
    args = parser.parse_args()
    main(confirm=args.confirm)
