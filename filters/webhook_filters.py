import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Normal spreads per symbol — tune after observation
NORMAL_SPREADS = {
    "US500":  0.6,
    "EURUSD": 0.0008,
    "DAX":    1.0,
}

# Active session windows in UTC (start_hour, end_hour)
SESSION_WINDOWS = {
    "EURUSD": (6, 21),   # London pre-market through NY close
    "US500":  (7, 21),   # London open through US close
    "DAX":    (7, 16),   # European session
}

# High-impact macro events
# Format: (year, month, day, hour_utc, minute_utc, label)
# Update this list every Sunday for the coming week
MACRO_EVENTS = [
    # (2026, 6, 11, 18, 0,  "FOMC"),
    # (2026, 6,  6, 12, 30, "NFP"),
    # (2026, 6, 11, 12, 30, "CPI"),
]
MACRO_BLOCK_MINUTES = 30


def should_block_session(symbol: str) -> bool:
    """Block trades outside active session hours. Returns False if symbol has no window."""
    window = SESSION_WINDOWS.get(symbol.upper())
    if not window:
        return False
    hour_utc = datetime.now(timezone.utc).hour
    start, end = window
    if not (start <= hour_utc < end):
        logger.warning(
            f"[WEBHOOK_FILTER] {symbol} outside session ({start}-{end} UTC) — skipping"
        )
        return True
    return False


def should_block_spread(symbol: str, current_spread: float | None) -> bool:
    """Block if spread exceeds 2× normal. Fails open if no spread data."""
    if current_spread is None:
        return False
    normal = NORMAL_SPREADS.get(symbol.upper())
    if normal and current_spread > normal * 2:
        logger.warning(
            f"[WEBHOOK_FILTER] {symbol} spread {current_spread} > 2× normal {normal} — skipping"
        )
        return True
    return False


def should_block_day_of_week(symbol: str) -> bool:
    """Block trades on historically poor performing days per symbol."""
    DAY_BLOCKS = {
        "US500": [0],      # Monday only — Tuesday removed pending more data
        # "US100": [0],    # Monday — add when US100 reactivated
    }
    blocked_days = DAY_BLOCKS.get(symbol.upper(), [])
    if not blocked_days:
        return False
    day = datetime.now(timezone.utc).weekday()  # Monday=0, Sunday=6
    if day in blocked_days:
        logger.warning(
            f"[WEBHOOK_FILTER] {symbol} blocked on day {day} (Mon=0) — day-of-week filter"
        )
        return True
    return False


def should_block_macro_event() -> bool:
    """Block within MACRO_BLOCK_MINUTES of any known event."""
    now = datetime.now(timezone.utc)
    for (y, mo, d, h, mi, label) in MACRO_EVENTS:
        event_dt = datetime(y, mo, d, h, mi, tzinfo=timezone.utc)
        diff_mins = abs((now - event_dt).total_seconds() / 60)
        if diff_mins <= MACRO_BLOCK_MINUTES:
            logger.warning(
                f"[WEBHOOK_FILTER] Within {MACRO_BLOCK_MINUTES}min of {label} — skipping"
            )
            return True
    return False
