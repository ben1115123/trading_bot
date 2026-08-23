"""Parse and log IG's historical-price-data allowance.

Zero imports beyond the stdlib, no side effects — same safe-import contract as
symbols.py, engine_version.py and instrument_limits.py. backend/backtesting/
engine.py must be importable by a backtest without dragging in a live IG
session, so this module may never grow a project import.

WHY THIS EXISTS
---------------
IG returns the remaining weekly historical-data budget on EVERY successful
/prices response:

    {"prices": [...], "instrumentType": "INDICES",
     "allowance": {"remainingAllowance": 9800,
                   "totalAllowance": 10000,
                   "allowanceExpiry": 411183}}

Both call sites did `result.get("prices")` and dropped the rest. The meter was
in hand on every call and was never read — so the weekly budget was an
invisible shared resource, and nothing anywhere knew when it resets.

Measured 2026-08-23: the DEMO account was at zero, a numpoints=1 request on
three separate epics was refused outright, and scripts/collect_candles.py had
logged 222 consecutive quota errors and produced zero candles. None of that was
visible until someone went looking, because the number that would have shown it
coming was being discarded on the way past.

Same class as candle_source_compare before 2026-08-20: the data was present and
correct, and had no reader. A delta of -114,008,596 pips sat unread for 28 days
for exactly this reason.

WHAT IT DOES NOT DO
-------------------
It does not throttle. It reports. A caller that wants to reserve budget for the
live path reads `remaining` off the returned dict and decides for itself —
putting a refusal in here would make a logging helper able to stop a warm-up.

It never raises. A malformed or absent allowance block returns None and logs
nothing, because a diagnostic that can break the warm-up path it instruments is
worse than no diagnostic.
"""
from datetime import datetime, timedelta, timezone

# IG's documented weekly budget for non-Pro accounts. Recorded for context in
# the log line only — the authoritative number is totalAllowance off the wire,
# which is why the log prints that and not this.
DOCUMENTED_WEEKLY_ALLOWANCE = 10_000


def parse_allowance(result) -> dict | None:
    """Pull the allowance block out of an IG /prices response.

    Returns {"remaining", "total", "expiry_secs", "resets_at", "used_pct"} or
    None if the response carries no usable allowance block.
    """
    try:
        block = result.get("allowance") if hasattr(result, "get") else None
        # v3 /prices nests it under metadata; v2 puts it at the top level.
        if not block and hasattr(result, "get"):
            meta = result.get("metadata") or {}
            block = meta.get("allowance") if hasattr(meta, "get") else None
        if not block:
            return None

        remaining = block.get("remainingAllowance")
        total = block.get("totalAllowance")
        expiry = block.get("allowanceExpiry")
        if remaining is None:
            return None

        resets_at = None
        if isinstance(expiry, (int, float)):
            resets_at = (datetime.now(timezone.utc)
                         + timedelta(seconds=float(expiry))).isoformat()

        used_pct = None
        if isinstance(total, (int, float)) and total:
            used_pct = 100.0 * (1.0 - float(remaining) / float(total))

        return {
            "remaining": remaining,
            "total": total,
            "expiry_secs": expiry,
            "resets_at": resets_at,
            "used_pct": used_pct,
        }
    except Exception:
        return None


def log_allowance(source: str, result, symbol: str = "", timeframe: str = "") -> dict | None:
    """Print the allowance at INFO and return the parsed dict (or None).

    `source` names the call site so the two consumers of the one shared budget
    are distinguishable in a log — that distinction is the whole point, since
    the collector starving candle_stream is invisible if both print the same
    prefix.
    """
    parsed = parse_allowance(result)
    if not parsed:
        return None
    try:
        who = f"{symbol}/{timeframe}" if symbol or timeframe else "-"
        used = f"{parsed['used_pct']:.1f}%" if parsed["used_pct"] is not None else "?"
        print(f"[ig_allowance] {source} {who}: "
              f"remaining={parsed['remaining']} of {parsed['total']} "
              f"({used} used), resets_at={parsed['resets_at']} "
              f"(expiry={parsed['expiry_secs']}s)")
    except Exception:
        pass
    return parsed
