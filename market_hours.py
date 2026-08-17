"""Market session and entry-policy windows, in one place.

Zero imports, no side effects — same safe-import contract as symbols.py,
engine_version.py, instrument_limits.py, spread_model.py and paper_model.py.

TWO DIFFERENT QUESTIONS, DELIBERATELY SEPARATE FUNCTIONS
--------------------------------------------------------
`bot/live_signal_loop.py::_is_blocked` conflated these into one boolean, and
the conflation is why the FX hole survived (findings doc finding 23):

  is_market_open(symbol, when)    Can the venue deal at all?
                                  A fact about the market. Used to decide
                                  whether an OBSERVATION is real — e.g. a
                                  spread sample from a shut book is not a
                                  quote anyone could have traded on.

  is_entry_allowed(symbol, when)  Will WE open a position?
                                  A policy on top of the fact. Narrower:
                                  it also refuses the thin Sunday reopen and
                                  the Friday pre-weekend window, neither of
                                  which the venue forbids.

Never use is_entry_allowed to filter observations: it would discard real
market data because of a risk preference. Never use is_market_open to gate an
entry: it would permit the reopen window.

PROVENANCE OF THESE CONSTANTS — measured, not assumed
-----------------------------------------------------
IG exposes NO session data on this account. Verified 2026-08-17 against
`fetch_market_by_epic` for CS.D.EURUSD.MINI.IP, CS.D.GBPUSD.MINI.IP and
IX.D.SPTRD.IFMM.IP:

  instrument.openingHours    null on every epic (field present, unpopulated)
  instrument.rolloverDetails null
  snapshot.marketStatus      populated ("TRADEABLE") but LIVE ONLY — it
                             cannot say what the status was last Sunday, so
                             it cannot classify a stored row

So the FX session below is derived from OUR OWN trade record: successful
`live_signal_loop` FX opens counted by UTC weekday and hour, all history to
2026-08-17.

    Sun    . . . . . . . . . . . . . . . . . . . .  4  3  4  7
    Mon    8 10 7 3 5 2 8 10 10 2 6 5 4 6 9 5 1 1 1 3 1 1 2 2
    Fri   11 10 13 8 6 7 12 7 6 9 5 6 5 5 5 1 . .  2 1 1  . . .
    Sat    . . . . . . . . . . . . . . . . . . . . . . . .
           0                    hour (UTC)                  23

Corroborated by IG's own rejections: MARKET_CLOSED_WITH_EDITS x3 on Sat
2026-07-25 00:00, and MARKET_OFFLINE on Sun 2026-07-26 21:20 — the latter
inside the reopen ramp, which is why the reopen is treated as ragged rather
than a clean edge.

Re-derive these numbers if the broker or account changes. They describe IG
demo account Z67Y2C in 2026, not a universal FX calendar.

KNOWN DISAGREEMENT, RECORDED ON PURPOSE
---------------------------------------
Three Sunday boundaries exist in this tree:

  20:00 UTC  measured venue reopen (here, SESSION_REOPEN_HOUR)
  23:00 UTC  entry policy (here, ENTRY_REOPEN_HOUR; matches the intent
             already written into _is_blocked)
  22:00 UTC  scripts/watchdog.py::_is_market_hours

The watchdog copy is LEGITIMATELY separate and must not import this module:
it runs on the host under cron, stdlib-only with no project imports, so that
it still works when the container is dead — which is the entire point of a
watchdog. Its window only gates heartbeat-staleness alerting, never a trade.
Recorded here so the next person to find the disagreement has a reference
point instead of assuming one of them is a bug.
"""

from datetime import datetime

# --- venue session (fact) --------------------------------------------------

# FX: continuous Sunday reopen -> Friday close.
SESSION_REOPEN_HOUR = 20   # Sunday, UTC — first hour with observed deals
SESSION_CLOSE_HOUR = 21    # Friday, UTC — last observed deal hour + 1

# NO INDEX INTRADAY CLOSE RULE HERE, DELIBERATELY.
#
# CLAUDE.md states US500/US100 "close 20:00 UTC" and MARKET_CLOSE carries
# 20:45. Neither is what the account does: the trade record holds 18 index
# opens at or after 20:00 UTC (US500 10, US100 8), spread across 20:00-23:59,
# every one of them accepted by IG.
#
#   US500  hour 20:00->23:00 counts:  5  2  1  2
#   US100  hour 20:00->23:00 counts:  .  3  1  4
#
# So an intraday close added here would block trades that currently happen and
# that the venue evidently permits. Index CFDs quote around the cash session
# rather than stopping with it.
#
# This is left OUT rather than guessed. Establishing the real index session
# needs its own measurement, and it is not what finding 23 is about.

# 24/7, never closed.
_ALWAYS_OPEN = {"BTC"}

# --- entry policy (preference on top of the fact) --------------------------

# No entries before this hour on Sunday, even though the venue deals from
# 20:00. Measured cost of the 20:00-22:59 window (finding 23): 10 FX trades,
# net -$9.29, WR 30.0% — indistinguishable from the 30.1% weekday baseline,
# and 5 of them were stopped out within 2 minutes at full risk because a
# 10-17 pip spread breaches a candle-range stop on the spread alone.
#
# 23:00 is also what the old _is_blocked already intended for the instruments
# it actually reached, so this preserves index behaviour unchanged.
ENTRY_REOPEN_HOUR = 23

# No new entries from this time on Friday, any instrument.
FRIDAY_ENTRY_CUTOFF_MIN = 20 * 60 + 45


def _minutes(when: datetime) -> int:
    return when.hour * 60 + when.minute


def is_market_open(symbol: str, when: datetime) -> bool:
    """Can the venue deal `symbol` at `when`? A fact about the market.

    Use for classifying observations (spread samples, quotes). Do NOT use to
    gate an entry — it permits the thin Sunday reopen.
    """
    symbol = (symbol or "").upper()
    if symbol in _ALWAYS_OPEN:
        return True

    weekday = when.weekday()          # Mon=0 .. Sun=6

    if weekday == 5:                  # Saturday — zero deals ever observed
        return False
    if weekday == 6:                  # Sunday — closed until the reopen
        if when.hour < SESSION_REOPEN_HOUR:
            return False
    elif weekday == 4:                # Friday — closes for the weekend
        if when.hour >= SESSION_CLOSE_HOUR:
            return False

    return True


def is_entry_allowed(symbol: str, when: datetime) -> bool:
    """Will we OPEN a position in `symbol` at `when`? Policy, not fact.

    Strictly narrower than is_market_open. Every rule added here is a risk
    preference and must carry its evidence.
    """
    symbol = (symbol or "").upper()

    if not is_market_open(symbol, when):
        return False

    if symbol in _ALWAYS_OPEN:
        return True

    weekday = when.weekday()

    # Sunday: sit out the thin reopen even though the venue deals.
    #
    # Applies to EVERY instrument except the always-open ones, not just FX.
    # The old _is_blocked reached this rule for US500/US100/DAX (they were in
    # MARKET_CLOSE) and blocked them until 23:00; scoping it to FX here would
    # have LOOSENED indices, which is not what this fix is for. The evidence
    # in finding 23 is FX-specific, so extending the rule to indices is
    # preserving prior behaviour, not a new claim about them.
    if weekday == 6 and when.hour < ENTRY_REOPEN_HOUR:
        return False

    # Friday: no new positions into the weekend gap.
    if weekday == 4 and _minutes(when) >= FRIDAY_ENTRY_CUTOFF_MIN:
        return False

    return True
