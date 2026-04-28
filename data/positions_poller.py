import threading
import time
import re
from datetime import datetime, timezone, timedelta


def _parse_pnl(raw) -> float | None:
    """Parse IG profitAndLoss string e.g. '+$15.23' or '-$4.50' to float."""
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


def _fetch_close_data(ig_service, deal_id: str, deal_reference: str = None, entry_time: str = None, lookback_hours: int = 48, max_attempts: int = 5, retry_delay: int = 10) -> dict | None:
    """
    Find close data for a deal in IG transaction history.
    Primary: reference == deal_reference (IG echoes dealReference in transaction history).
    Fallback: openDateUtc within 60s of entry_time (used when deal_reference is missing).
    Retries up to max_attempts times with retry_delay seconds between each attempt
    to handle fast-closing trades where IG hasn't settled the transaction yet.
    """
    try:
        for attempt in range(1, max_attempts + 1):
            print(f"Positions poller: fetching close data for {deal_id} attempt {attempt}/{max_attempts}...")
            time.sleep(retry_delay)

            from_dt = datetime.utcnow() - timedelta(hours=lookback_hours)
            transactions = ig_service.fetch_transaction_history(
                trans_type="ALL_DEAL",
                from_date=from_dt,
            )
            if transactions is None or transactions.empty:
                print(f"Positions poller: no transaction history returned (attempt {attempt}/{max_attempts})")
                continue

            match = None

            if deal_reference and "reference" in transactions.columns:
                match = transactions[transactions["reference"] == deal_reference]

            if (match is None or match.empty) and entry_time and "openDateUtc" in transactions.columns:
                try:
                    entry_dt = datetime.fromisoformat(entry_time.replace("Z", "+00:00"))
                    def _near_entry(val):
                        try:
                            dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            return abs((dt - entry_dt).total_seconds()) < 60
                        except Exception:
                            return False
                    match = transactions[transactions["openDateUtc"].apply(_near_entry)]
                except Exception as e:
                    print(f"Positions poller: entry_time match failed for {deal_id}: {e}")

            if match is not None and not match.empty:
                row = match.iloc[0]
                return {
                    "close_price":  _to_float(row.get("closeLevel")),
                    "close_time":   row.get("dateUtc") or datetime.now(timezone.utc).isoformat(),
                    "realised_pnl": _parse_pnl(row.get("profitAndLoss")),
                }

            print(f"Positions poller: no match attempt {attempt}/{max_attempts} for {deal_id}")

        print(f"Positions poller: no transaction match for {deal_id} after {max_attempts} attempts — will use fallback")
        return None
    except Exception as e:
        print(f"Positions poller: transaction history lookup failed: {e}")
        return None


def _detect_and_close_trades(ig_service, ensure_session, active_deal_ids: list) -> None:
    """
    Compare open trades in DB against currently open IG positions.
    For any deal that has disappeared, mark it closed in the trades table.
    """
    from database.models import get_open_trade_deal_ids, get_positions, close_trade, get_trade_by_deal_id

    open_in_db = get_open_trade_deal_ids()
    if not open_in_db:
        return

    active_set = set(active_deal_ids)
    disappeared = [d for d in open_in_db if d not in active_set]
    if not disappeared:
        return

    # Snapshot positions table before clearing — used as fallback close data
    pos_snapshot = {p["deal_id"]: p for p in get_positions()}

    for deal_id in disappeared:
        # Try transaction history first (accurate close price + realised P&L)
        trade_row = get_trade_by_deal_id(deal_id) or {}
        close_data = _fetch_close_data(
            ig_service,
            deal_id,
            deal_reference=trade_row.get("deal_reference"),
            entry_time=trade_row.get("timestamp"),
        )

        if close_data is None:
            # Fall back to last known position data (within 30s of actual close)
            pos = pos_snapshot.get(deal_id, {})
            close_data = {
                "close_price":  pos.get("current_price"),
                "close_time":   datetime.now(timezone.utc).isoformat(),
                "realised_pnl": pos.get("unrealised_pnl"),
            }
            print(f"Positions poller: using fallback close data for {deal_id}")

        rows = close_trade(
            deal_id,
            close_price=close_data["close_price"],
            close_time=close_data["close_time"],
            realised_pnl=close_data["realised_pnl"],
        )
        if rows:
            print(
                f"Positions poller: closed trade {deal_id} "
                f"price={close_data['close_price']} pnl={close_data['realised_pnl']}"
            )
        else:
            print(f"Positions poller: deal {deal_id} not found in trades table (not logged)")


def _poll_loop():
    from bot.execute_trade import ig_service, ensure_session, EPIC_CONFIG
    from database.models import upsert_position, clear_closed_positions

    EPIC_TO_SYMBOL = {
        v["epic"]: (k, v["value_per_point"])
        for k, v in EPIC_CONFIG.items()
    }

    _consecutive_empty = 0

    while True:
        try:
            ensure_session()
            df = ig_service.fetch_open_positions()

            if df is not None and not df.empty:
                _consecutive_empty = 0
                active_deals = []

                for _, row in df.iterrows():
                    deal_id    = row.get("position.dealId")
                    epic       = row.get("market.epic")
                    direction  = row.get("position.direction")
                    size       = row.get("position.size")
                    open_price = row.get("position.openLevel") or row.get("position.level")
                    bid        = row.get("market.bid")
                    offer      = row.get("market.offer")

                    if not deal_id or not epic:
                        continue

                    symbol_info = EPIC_TO_SYMBOL.get(epic)
                    if not symbol_info:
                        print(
                            f"WARNING: deal_id {deal_id} epic {epic} not in EPIC_CONFIG "
                            f"— skipping close detection for this deal to be safe"
                        )
                        active_deals.append(deal_id)
                        continue

                    symbol, vpp = symbol_info
                    current_price = bid if direction == "BUY" else offer

                    if current_price is not None and open_price is not None:
                        if direction == "BUY":
                            unrealised_pnl = round((current_price - open_price) * size * vpp, 2)
                        else:
                            unrealised_pnl = round((open_price - current_price) * size * vpp, 2)
                    else:
                        unrealised_pnl = None

                    upsert_position({
                        "deal_id":        deal_id,
                        "symbol":         symbol,
                        "direction":      direction,
                        "size":           size,
                        "open_price":     open_price,
                        "current_price":  current_price,
                        "unrealised_pnl": unrealised_pnl,
                        "updated_at":     datetime.now(timezone.utc).isoformat(),
                    })
                    active_deals.append(deal_id)

                _detect_and_close_trades(ig_service, ensure_session, active_deals)
                clear_closed_positions(active_deals)
                print(f"Positions updated: {len(active_deals)} open")

            else:
                _consecutive_empty += 1
                if _consecutive_empty < 2:
                    print(f"Positions: none open ({_consecutive_empty}/2 — waiting to confirm)")
                else:
                    print(f"Positions: none open (2/2 — confirming closes)")
                    _detect_and_close_trades(ig_service, ensure_session, [])
                    clear_closed_positions([])

        except Exception as e:
            print("Positions poller error:", e)

        time.sleep(30)


def _get_closed_trades_missing_pnl_recent(hours: int = 2) -> list:
    from database.db import get_connection
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, deal_id, deal_reference, timestamp, close_time
            FROM trades
            WHERE status = 'CLOSED'
              AND pnl IS NULL
              AND close_time > datetime('now', ?)
        """, (f"-{hours} hours",))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def _update_trade_pnl(trade_id: int, close_price, close_time, pnl) -> int:
    from database.db import get_connection
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


def _deferred_pnl_loop():
    from bot.execute_trade import ig_service, ensure_session

    DEFERRED_INTERVAL = 300   # 5 minutes between scans
    GIVE_UP_MINUTES   = 30    # give up if close was > 30 min ago

    while True:
        time.sleep(DEFERRED_INTERVAL)
        try:
            ensure_session()
            pending = _get_closed_trades_missing_pnl_recent(hours=2)
            if not pending:
                continue

            for t in pending:
                deal_id  = t["deal_id"]
                trade_id = t["id"]

                try:
                    close_dt = datetime.fromisoformat(
                        str(t["close_time"]).replace("Z", "+00:00"))
                    if close_dt.tzinfo is None:
                        close_dt = close_dt.replace(tzinfo=timezone.utc)
                    age_mins = (datetime.now(timezone.utc) - close_dt).total_seconds() / 60
                except Exception:
                    age_mins = 0

                if age_mins > GIVE_UP_MINUTES:
                    print(f"WARNING: could not fetch P&L for {deal_id} "
                          f"after {GIVE_UP_MINUTES}min — manual backfill required")
                    continue

                close_data = _fetch_close_data(
                    ig_service, deal_id,
                    deal_reference=t.get("deal_reference"),
                    entry_time=t.get("timestamp"),
                    max_attempts=1,
                    retry_delay=1,
                )
                if close_data:
                    rows = _update_trade_pnl(
                        trade_id,
                        close_data["close_price"],
                        close_data["close_time"],
                        close_data["realised_pnl"],
                    )
                    if rows:
                        print(f"Positions poller (deferred): updated P&L for "
                              f"{deal_id} pnl={close_data['realised_pnl']}")
        except Exception as e:
            print(f"Positions poller deferred P&L loop error: {e}")


def start_poller():
    t = threading.Thread(target=_poll_loop, daemon=True)
    t.start()
    print("Positions poller started (30s interval)")
    d = threading.Thread(target=_deferred_pnl_loop, daemon=True)
    d.start()
    print("Positions poller deferred P&L checker started (5min interval)")
