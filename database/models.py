from datetime import datetime, timezone
from database.db import get_connection


def log_trade(trade_data: dict) -> int:
    """
    Insert a trade record into the trades table.

    Args:
        trade_data (dict): Trade data with keys:
            - timestamp (optional): ISO format string, defaults to UTC now
            - symbol (required): Trading symbol
            - direction (required): 'BUY' or 'SELL'
            - size (required): Trade size/lot
            - entry_price (required): Entry price
            - sl (optional): Stop loss price
            - tp (optional): Take profit price
            - deal_id (optional): IG deal ID
            - pnl (optional): Profit/loss (NULL until closed)
            - source (optional): Source of signal, defaults to 'indicator'
            - strategy_name (optional): Strategy name, defaults to 'manual'
            - status (optional): Trade status, defaults to 'OPEN'

    Returns:
        int: The id (lastrowid) of the inserted trade
    """
    # Validate required fields at start (Fix C2)
    required = ('symbol', 'direction', 'size', 'entry_price')
    missing = [f for f in required if f not in trade_data]
    if missing:
        raise ValueError(f"log_trade missing required fields: {missing}")

    # Work on a copy to avoid mutating caller's dict (Fix I1)
    data = trade_data.copy()

    # Set defaults for optional fields
    if 'timestamp' not in data:
        data['timestamp'] = datetime.now(timezone.utc).isoformat()
    if 'source' not in data:
        data['source'] = 'indicator'
    if 'strategy_name' not in data:
        data['strategy_name'] = 'manual'
    if 'status' not in data:
        data['status'] = 'OPEN'

    # Set optional nullable fields to None if not provided
    if 'sl' not in data:
        data['sl'] = None
    if 'tp' not in data:
        data['tp'] = None
    if 'deal_id' not in data:
        data['deal_id'] = None
    if 'pnl' not in data:
        data['pnl'] = None

    conn = get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO trades
            (timestamp, symbol, direction, size, entry_price, sl, tp,
             deal_id, pnl, source, strategy_name, status)
            VALUES
            (:timestamp, :symbol, :direction, :size, :entry_price, :sl, :tp,
             :deal_id, :pnl, :source, :strategy_name, :status)
        """, data)

        conn.commit()
        trade_id = cursor.lastrowid
    finally:
        conn.close()

    return trade_id


def upsert_position(pos: dict) -> None:
    required = ('deal_id', 'symbol', 'direction', 'size', 'open_price', 'updated_at')
    missing = [f for f in required if f not in pos]
    if missing:
        raise ValueError(f"upsert_position missing required fields: {missing}")

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO positions
                (deal_id, symbol, direction, size, open_price,
                 current_price, unrealised_pnl, updated_at)
            VALUES
                (:deal_id, :symbol, :direction, :size, :open_price,
                 :current_price, :unrealised_pnl, :updated_at)
            ON CONFLICT(deal_id) DO UPDATE SET
                current_price  = excluded.current_price,
                unrealised_pnl = excluded.unrealised_pnl,
                updated_at     = excluded.updated_at
        """, {
            "deal_id":       pos["deal_id"],
            "symbol":        pos["symbol"],
            "direction":     pos["direction"],
            "size":          pos["size"],
            "open_price":    pos["open_price"],
            "current_price": pos.get("current_price"),
            "unrealised_pnl": pos.get("unrealised_pnl"),
            "updated_at":    pos["updated_at"],
        })
        conn.commit()
    finally:
        conn.close()


def get_positions() -> list:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM positions ORDER BY updated_at DESC")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def clear_closed_positions(active_deal_ids: list) -> None:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        if active_deal_ids:
            placeholders = ",".join("?" * len(active_deal_ids))
            cursor.execute(
                f"DELETE FROM positions WHERE deal_id NOT IN ({placeholders})",
                active_deal_ids,
            )
        else:
            cursor.execute("DELETE FROM positions")
        conn.commit()
    finally:
        conn.close()


def close_trade(deal_id: str, close_price=None, close_time=None, realised_pnl=None) -> int:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE trades
            SET close_price = ?,
                close_time  = ?,
                pnl         = ?,
                status      = 'CLOSED'
            WHERE deal_id = ?
              AND status   = 'OPEN'
        """, (close_price, close_time, realised_pnl, deal_id))
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def get_open_trade_deal_ids() -> list:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT deal_id FROM trades WHERE status = 'OPEN' AND deal_id IS NOT NULL")
        return [row["deal_id"] for row in cursor.fetchall()]
    finally:
        conn.close()


def get_trade_by_deal_id(deal_id: str) -> dict | None:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trades WHERE deal_id = ? LIMIT 1", (deal_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def insert_backtest_result(result: dict) -> int:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO backtest_results
                (strategy_name, symbol, timeframe, run_at,
                 candles_total, candles_train, candles_test,
                 total_trades, win_rate, total_profit, max_drawdown,
                 sharpe_ratio, benchmark_return, params_json)
            VALUES
                (:strategy_name, :symbol, :timeframe, :run_at,
                 :candles_total, :candles_train, :candles_test,
                 :total_trades, :win_rate, :total_profit, :max_drawdown,
                 :sharpe_ratio, :benchmark_return, :params_json)
        """, result)
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def insert_backtest_trade(trade: dict) -> None:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO backtest_trades
                (backtest_id, entry_time, exit_time, direction,
                 entry_price, exit_price, pnl, duration_mins)
            VALUES
                (:backtest_id, :entry_time, :exit_time, :direction,
                 :entry_price, :exit_price, :pnl, :duration_mins)
        """, trade)
        conn.commit()
    finally:
        conn.close()


def get_backtest_results() -> list:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM backtest_results ORDER BY run_at DESC")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_backtest_trades(backtest_id: int) -> list:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM backtest_trades WHERE backtest_id = ? ORDER BY entry_time ASC",
            (backtest_id,)
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_recent_trades(limit: int = 10) -> list:
    """
    Retrieve the most recent trades from the trades table.

    Args:
        limit (int): Number of trades to return, ordered by id DESC.
                    Defaults to 10.

    Returns:
        list: List of dicts, each representing a trade row
    """
    # Guard against limit <= 0 (Fix I2)
    if limit <= 0:
        raise ValueError(f"limit must be a positive integer, got {limit}")

    conn = get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT *
            FROM trades
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))

        rows = cursor.fetchall()
    finally:
        conn.close()

    # Convert sqlite3.Row objects to dicts
    trades = [dict(row) for row in rows]

    return trades
