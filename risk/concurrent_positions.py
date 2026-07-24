from database.db import get_connection

MAX_CONCURRENT_PER_SYMBOL = 1


def get_open_position_count(symbol: str, strategy_name: str) -> int:
    """
    OPEN position count for one (symbol, strategy_name) instance, read from
    trades.status='OPEN' — the same field positions_poller maintains (set to
    OPEN by log_trade on placement, flipped to CLOSED only after
    _verify_closed_on_ig confirms against the broker). Not a live IG poll:
    this is the DB's last-known state, same source _check_correlation_cluster
    already uses for its OPEN-position query.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE status = 'OPEN' AND symbol = ? AND strategy_name = ?",
            (symbol, strategy_name),
        ).fetchone()
        return int(row[0])
    finally:
        conn.close()


def is_concurrent_limit_breached(symbol: str, strategy_name: str,
                                  limit: int = MAX_CONCURRENT_PER_SYMBOL) -> bool:
    """
    True if this (symbol, strategy_name) instance already has >= limit OPEN
    positions. Race window: count is read here, then place_trade() runs its
    own IG round-trip (session check, market fetch, create_open_position)
    before log_trade() writes the new row — another signal for the same
    (symbol, strategy_name) landing in that window would not be counted and
    could stack past the limit. live_signal_loop processes symbols
    sequentially within one cycle with no threading, and per-(symbol,
    timeframe, strategy_name) dedup already prevents the same instance firing
    twice in one cycle, so the only realistic opening is a signal from a
    different timeframe on the same (symbol, strategy_name) landing mid
    place_trade() — narrow, not closed by this check alone.
    """
    count = get_open_position_count(symbol, strategy_name)
    print(f"[concurrent_positions] {symbol}/{strategy_name}: {count} OPEN / limit {limit}")
    return count >= limit
