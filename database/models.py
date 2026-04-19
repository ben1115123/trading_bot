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
