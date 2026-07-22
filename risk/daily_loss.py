from database.db import get_connection
from datetime import datetime, timezone

DAILY_LOSS_LIMIT_USD = 75.0


def get_today_realised_pnl(symbol: str | None = None, strategy_name: str | None = None) -> float:
    """
    Realised P&L today, optionally scoped to one (symbol, strategy_name)
    instance. No args = old all-sources-combined total.
    Uses close_time (not open timestamp) — only counts closed trades.
    """
    conn = get_connection()
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        query = """
            SELECT COALESCE(SUM(pnl), 0)
            FROM trades
            WHERE date(close_time) = ?
            AND pnl IS NOT NULL
        """
        params: list = [today]
        if symbol is not None:
            query += " AND symbol = ?"
            params.append(symbol)
        if strategy_name is not None:
            query += " AND strategy_name = ?"
            params.append(strategy_name)
        row = conn.execute(query, params).fetchone()
        return float(row[0])
    finally:
        conn.close()


def is_daily_loss_limit_breached(symbol: str | None = None, strategy_name: str | None = None,
                                  limit: float = DAILY_LOSS_LIMIT_USD) -> bool:
    """
    Returns True if today's realised P&L for this (symbol, strategy_name)
    instance is <= -limit. Each instance gets its own $75 budget — a FRAGILE
    strategy's bad day (e.g. GBPUSD williams_r) must not block an unrelated
    instance (e.g. AUDUSD williams_r) even when they share a strategy_name.
    No args = old all-sources-combined behavior.
    """
    today_pnl = get_today_realised_pnl(symbol, strategy_name)
    scope = f"{symbol or 'ALL'}/{strategy_name or 'ALL'}"
    print(f"[daily_loss] Daily P&L check [{scope}]: {today_pnl:.2f} / -{limit:.2f} limit")
    return today_pnl <= -limit
