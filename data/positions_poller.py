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


def _fetch_close_data(ig_service, deal_id: str, lookback_hours: int = 2) -> dict | None:
    """
    Try to find close data for deal_id in IG transaction history.
    Returns dict with close_price, close_time, realised_pnl or None.
    """
    try:
        from_dt = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        transactions = ig_service.fetch_transaction_history(
            trans_type="DEAL",
            from_date=from_dt,
        )
        if transactions is None or transactions.empty:
            return None

        match = transactions[transactions["reference"] == deal_id]
        if match.empty:
            return None

        row = match.iloc[0]
        return {
            "close_price":   _to_float(row.get("closeLevel")),
            "close_time":    row.get("dateUtc") or datetime.now(timezone.utc).isoformat(),
            "realised_pnl":  _parse_pnl(row.get("profitAndLoss")),
        }
    except Exception as e:
        print(f"Positions poller: transaction history lookup failed: {e}")
        return None


def _detect_and_close_trades(ig_service, ensure_session, active_deal_ids: list) -> None:
    """
    Compare open trades in DB against currently open IG positions.
    For any deal that has disappeared, mark it closed in the trades table.
    """
    from database.models import get_open_trade_deal_ids, get_positions, close_trade

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
        close_data = _fetch_close_data(ig_service, deal_id)

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

    while True:
        try:
            ensure_session()
            df = ig_service.fetch_open_positions()

            if df is not None and not df.empty:
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
                        print(f"Positions poller: unknown epic {epic}, skipping")
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
                # No open positions — close any DB trades that are still marked OPEN
                _detect_and_close_trades(ig_service, ensure_session, [])
                clear_closed_positions([])
                print("Positions: none open")

        except Exception as e:
            print("Positions poller error:", e)

        time.sleep(30)


def start_poller():
    t = threading.Thread(target=_poll_loop, daemon=True)
    t.start()
    print("Positions poller started (30s interval)")
