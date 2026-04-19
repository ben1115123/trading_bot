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
    # Set defaults for optional fields
    if 'timestamp' not in trade_data:
        trade_data['timestamp'] = datetime.now(timezone.utc).isoformat()
    if 'source' not in trade_data:
        trade_data['source'] = 'indicator'
    if 'strategy_name' not in trade_data:
        trade_data['strategy_name'] = 'manual'
    if 'status' not in trade_data:
        trade_data['status'] = 'OPEN'

    # Set optional nullable fields to None if not provided
    if 'sl' not in trade_data:
        trade_data['sl'] = None
    if 'tp' not in trade_data:
        trade_data['tp'] = None
    if 'deal_id' not in trade_data:
        trade_data['deal_id'] = None
    if 'pnl' not in trade_data:
        trade_data['pnl'] = None

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO trades
        (timestamp, symbol, direction, size, entry_price, sl, tp,
         deal_id, pnl, source, strategy_name, status)
        VALUES
        (:timestamp, :symbol, :direction, :size, :entry_price, :sl, :tp,
         :deal_id, :pnl, :source, :strategy_name, :status)
    """, trade_data)

    conn.commit()
    trade_id = cursor.lastrowid
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
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM trades
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()
    conn.close()

    # Convert sqlite3.Row objects to dicts
    trades = [dict(row) for row in rows]

    return trades
