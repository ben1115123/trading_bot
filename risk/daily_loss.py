from database.db import get_connection
from datetime import datetime, timezone

DAILY_LOSS_LIMIT_USD = 75.0


def get_today_realised_pnl() -> float:
    """
    Total realised P&L today across ALL sources.
    Single source of truth for daily loss limit.
    Uses close_time (not open timestamp) — only counts closed trades.
    """
    conn = get_connection()
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        row = conn.execute("""
            SELECT COALESCE(SUM(pnl), 0)
            FROM trades
            WHERE date(close_time) = ?
            AND pnl IS NOT NULL
        """, (today,)).fetchone()
        return float(row[0])
    finally:
        conn.close()


def is_daily_loss_limit_breached(limit: float = DAILY_LOSS_LIMIT_USD) -> bool:
    """
    Returns True if today's total realised P&L (all sources) is <= -limit.
    """
    today_pnl = get_today_realised_pnl()
    print(f"[daily_loss] Daily P&L check: {today_pnl:.2f} / -{limit:.2f} limit")
    return today_pnl <= -limit
