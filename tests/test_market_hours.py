"""Behaviour tests for market_hours and the spread market-open filter.

Two things are pinned here.

1. THE FX HOLE MUST NOT COME BACK. `_is_blocked` never blocked an FX symbol
   because MARKET_CLOSE held no FX key and `.get` returned None (findings doc
   finding 23). 21 weekend trades were placed as a result. The regression test
   for that is not "does the function exist" — it is "does EURUSD block on a
   Saturday", asserted against a constructed timestamp, because the live
   control's silence proved nothing for months.

2. THE SPREAD FILTER MUST NOT MOVE MEDIANS. The filter's job is to remove
   observations taken against a shut book. If it ever changes a median it is
   reshaping the data rather than removing contamination, which is the exact
   failure it exists to prevent.
"""
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market_hours import is_market_open, is_entry_allowed

UTC = timezone.utc

# 2026-08-14 Fri, 08-15 Sat, 08-16 Sun, 08-11 Tue
FRI, SAT, SUN, TUE = 14, 15, 16, 11


def when(day, hour, minute=0):
    return datetime(2026, 8, day, hour, minute, tzinfo=UTC)


# --- the regression that matters -------------------------------------------

def test_fx_blocked_on_saturday():
    """The hole itself. Returned False for every FX symbol before 2026-08-17."""
    for symbol in ("EURUSD", "GBPUSD", "AUDUSD", "USDCAD"):
        assert not is_market_open(symbol, when(SAT, 12)), symbol
        assert not is_entry_allowed(symbol, when(SAT, 12)), symbol


def test_fx_blocked_across_the_whole_weekend():
    """Not just Saturday noon — every hour of it."""
    for hour in range(24):
        assert not is_entry_allowed("EURUSD", when(SAT, hour))
    for hour in range(23):          # Sunday up to the 23:00 reopen
        assert not is_entry_allowed("EURUSD", when(SUN, hour))


# --- venue session vs entry policy -----------------------------------------

def test_reopen_window_is_open_but_not_tradeable():
    """The distinction the old single boolean could not express.

    20:00-22:59 Sunday: IG deals (measured), we decline (measured cost).
    """
    for hour in (20, 21, 22):
        assert is_market_open("EURUSD", when(SUN, hour)), hour
        assert not is_entry_allowed("EURUSD", when(SUN, hour)), hour


def test_entry_allowed_is_strictly_narrower_than_market_open():
    """Invariant: entry_allowed implies market_open, never the reverse."""
    for symbol in ("EURUSD", "US500", "BTC"):
        for day in (FRI, SAT, SUN, TUE):
            for hour in range(24):
                t = when(day, hour)
                if is_entry_allowed(symbol, t):
                    assert is_market_open(symbol, t), (symbol, day, hour)


# --- boundaries ------------------------------------------------------------

def test_sunday_reopen_boundary():
    assert not is_entry_allowed("EURUSD", when(SUN, 22, 59))
    assert is_entry_allowed("EURUSD", when(SUN, 23, 1))


def test_friday_cutoff_boundary():
    assert is_entry_allowed("EURUSD", when(FRI, 20, 44))
    assert not is_entry_allowed("EURUSD", when(FRI, 20, 46))


def test_friday_venue_close():
    assert is_market_open("EURUSD", when(FRI, 20, 44))
    assert not is_market_open("EURUSD", when(FRI, 21, 1))


def test_weekday_unrestricted():
    for hour in range(24):
        assert is_market_open("EURUSD", when(TUE, hour)), hour
        assert is_entry_allowed("EURUSD", when(TUE, hour)), hour


def test_btc_never_closes():
    for day in (FRI, SAT, SUN, TUE):
        for hour in (0, 12, 21, 23):
            assert is_market_open("BTC", when(day, hour))
            assert is_entry_allowed("BTC", when(day, hour))


def test_indices_unchanged_by_the_fx_fix():
    """Scope guard. The fix was FX-only; indices must behave as before.

    The old _is_blocked DID reach indices (they are in MARKET_CLOSE), so their
    results are the reference. Any change here means the fix leaked.
    """
    def old_is_blocked(symbol, now):
        market_close = {"US500": 1, "US100": 1, "DAX": 1, "BTC": None}
        if market_close.get(symbol) is None:
            return False
        weekday = now.weekday()
        if weekday == 5:
            return True
        if weekday == 6:
            return now.hour < 23
        if weekday == 4:
            return now.hour * 60 + now.minute >= 20 * 60 + 45
        return False

    for symbol in ("US500", "US100", "DAX"):
        for day in (FRI, SAT, SUN, TUE):
            for hour in range(24):
                t = when(day, hour)
                assert old_is_blocked(symbol, t) == (not is_entry_allowed(symbol, t)), \
                    f"index behaviour changed: {symbol} day={day} hour={hour}"


def test_symbol_case_and_none_are_safe():
    assert not is_entry_allowed("eurusd", when(SAT, 12))
    assert not is_entry_allowed("", when(SAT, 12))


# --- the spread filter's contract ------------------------------------------

def _median_of(samples):
    return statistics.median([s["spread"] for s in samples])


def test_filter_removes_shut_book_without_moving_the_median():
    """The test of record for the filter.

    Built from the shape of the real 2026-08-16/17 pool: a tight weekday core
    plus wide weekend observations. The filter must drop every weekend sample
    and leave the median untouched.
    """
    samples = []
    # Monday core: 40 observations at the real measured EURUSD spread
    for i in range(40):
        samples.append({"symbol": "EURUSD",
                        "minute": f"2026-08-17T{i % 24:02d}:{(i * 7) % 60:02d}",
                        "spread": 0.00006})
    # Weekend contamination: shut-book and reopen values, all far wider
    for hour, spread in ((6, 0.00105), (11, 0.00105), (16, 0.00105),
                         (20, 0.00094), (21, 0.00099), (22, 0.00105)):
        samples.append({"symbol": "EURUSD",
                        "minute": f"2026-08-16T{hour:02d}:01",
                        "spread": spread})

    def keep(rows):
        out = []
        for r in rows:
            t = datetime.fromisoformat(r["minute"]).replace(tzinfo=UTC)
            if is_entry_allowed(r["symbol"], t):
                out.append(r)
        return out

    filtered = keep(samples)

    assert len(filtered) == 40, "every weekend observation must drop out"
    assert max(s["spread"] for s in filtered) == 0.00006
    assert _median_of(filtered) == _median_of(samples), \
        "filter moved the median — it is reshaping data, not removing contamination"


def test_filter_keeps_the_real_post_reopen_quote():
    """Sun 23:01 is the first tradeable minute, not contamination.

    The measured pool has exactly one >3 pip survivor at this timestamp
    (USDCAD 5.7 pips). It must be kept: it is a cost the bot can really incur.
    """
    t = datetime(2026, 8, 16, 23, 1, tzinfo=UTC)
    assert is_entry_allowed("USDCAD", t)
