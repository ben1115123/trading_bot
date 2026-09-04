"""Provenance of the spread numbers the backtest engine is parameterised by.

Zero imports beyond stdlib hashlib, no side effects — same safe-import contract
as symbols.py, engine_version.py and instrument_limits.py.

WHY THIS EXISTS SEPARATELY FROM engine_version:
`engine_version` versions the trade model's STRUCTURE — how a trade is entered,
sized, exited, priced. Spread is a PARAMETER that structure is fed. The two
change independently: someone can swap the spread numbers without touching a
line of engine logic, and `engine_version` would not move. A row from months
ago must still answer "which spread numbers produced this", so the model NAME
is stamped per row and the table CONTENT is hashed alongside it. A name can be
kept while the numbers change underneath it; a hash cannot.

The same reasoning applies to MIN_SL_DIST, which is currently an uncalibrated
hand-set table that drives sizing on 45-55% of FX entries with no provenance at
all — recorded as finding 14 in docs/SESSION_20260812_FINDINGS.md, not fixed.

CURRENT STATE (2026-09-04, pass B): `measured-2026-09-median` is STAMPED AND
APPLIED. engine.py crosses the book in PRICE units — half the measured spread
at entry on the side taken, half at exit on the side crossed — under
engine_version parity-v3.

The predecessor `flat-roundtrip-dollars-UNCALIBRATED` subtracted a flat
per-round-trip dollar constant from SPREAD_COSTS at exit. That was not what
live pays: live crosses the book at ENTRY, in price units, which shifts both
trigger levels rather than deducting a fee — so it was wrong in units, wrong
in timing, and did not scale with position size. It is retained in the History
below because rows stamped with it still exist and must stay readable.

It is left in place deliberately rather than replaced with a guess:
  - NORMAL_SPREADS covers only US500, EURUSD and DAX. Three of the four
    rostered FX symbols (GBPUSD, AUDUSD, USDCAD) have no value anywhere, so a
    "provisional" table would be inventing 3 of 4 numbers.
  - SPREAD_COSTS cannot be divided back into price units: those dollars embed
    an assumed lot size, so the arithmetic would invent both the spread and the
    position size it assumed.
  - trades.spread was NULL on all 906 rows, so there was nothing to calibrate
    from. Capture starts 2026-08-16; a per-symbol distribution is ~1-2 days of
    stream samples away, session-stratified inside a week.

Replacing it is deliberately a LATER commit, on measured data. When that lands:
register the new model name below, stamp it, and bump engine_version too --
changing how spread is applied IS a structural change.
"""

import hashlib

# Names the spread treatment a result row was produced under. Stamped into
# backtest_results.spread_model and walkforward_runs.spread_model.
CURRENT_SPREAD_MODEL = "measured-2026-09-median"

# History:
#   flat-roundtrip-dollars-UNCALIBRATED
#       engine.py SPREAD_COSTS, flat USD per round trip, subtracted at exit.
#       Provenance: none. Origin of the numbers unknown, never measured
#       against a real quote, never revised. Treat every figure produced
#       under this model as optimistic by an unquantified amount.
#   measured-2026-09-median
#       Measured and frozen 2026-09-03 (pass A); STAMPED AND APPLIED
#       2026-09-04 (pass B, engine_version parity-v3). Per-symbol median,
#       PRICE units, from signal_log spread samples over two complete Mon-Fri
#       cycles (see MEASURED_SPREADS_2026_09 below). Half is crossed at entry
#       on the side taken and half at exit on the side crossed.
#       In pass A the name was registered here but NOT stamped, because the
#       stamp must describe what the engine actually does — flipping it early
#       would have mislabelled every row written in between. That is why the
#       two passes exist.
#       TAIL IS UNCALIBRATED: median only. Not usable for risk of ruin.


# ---------------------------------------------------------------------------
# MEASURED, FROZEN, AND DELIBERATELY NOT YET IN USE
# ---------------------------------------------------------------------------
# Pass A of two. This table is measured and hashed; pass B applies it to
# engine.py, recalibrates NORMAL_SPREADS and bumps engine_version (changing
# how spread is applied IS a structural change). Until pass B lands, nothing
# reads this dict and CURRENT_SPREAD_MODEL above is unchanged.
#
# UNITS: PRICE units — the same units signal_log.spread is stored in.
# EURUSD 0.00006 is 0.6 pips, NOT 6 pips. The model being replaced is wrong in
# units (flat dollars per round trip), so the readable equivalent is written
# out beside every row rather than left to be inferred.
#
# 🔴 THE TAIL IS UNCALIBRATED. These are MEDIANS. They describe what a typical
# placeable entry costs and say NOTHING about the wide tail. RISK-OF-RUIN AND
# DRAWDOWN WORK MUST NOT USE THIS TABLE — ruin lives in the tail. The
# pre-parity ruin table was already wrong by more than an order of magnitude
# (5.58% against a measured 67.3–84.3%); feeding a median-only spread into
# that calculation is how it happens a second time.
#
# Generated by scripts/build_spread_table.py against pinned bounds. Re-running
# that script must reproduce this dict and its sha exactly; the bounds are
# what makes that true, because the sample pool grows every five minutes.
MEASURED_SPREADS_2026_09 = {
    "EURUSD": 6e-05,    # 0.60 pips
    "GBPUSD": 9e-05,    # 0.90 pips
    "AUDUSD": 6e-05,    # 0.60 pips
    "USDCAD": 0.00013,  # 1.30 pips
    "US500":  0.6,      # 0.60 index points
    "US100":  2.0,      # 2.00 index points
}

# spread_table_sha(MEASURED_SPREADS_2026_09) — recorded so a later edit that
# keeps the dict name is detectable without re-deriving it.
MEASURED_SPREADS_2026_09_SHA = "c0c905fc6c071dd4"

# Per-symbol provenance. A "measured" table with n=3 for a symbol is not
# meaningfully better than a guess, and that has to be visible at the point of
# use rather than buried in a commit message.
#
# `filter` is the same predicate for every row and is NOT a refinement — it is
# a prerequisite. The raw pool carries closed-book quotes the 900s staleness
# guard does not catch; calibrating on it yields a constant ~10x too wide,
# reproducing the NORMAL_SPREADS error this work exists to fix.
#
# `p90`/`max` are CONTEXT ONLY and are deliberately not in the table above.
# They are here so that the tail's shape is visible next to the median that
# ignores it.
MEASURED_SPREADS_2026_09_PROVENANCE = {
    "EURUSD": {"n": 917,  "p90": 6e-05,   "max": 0.00027},
    "GBPUSD": {"n": 908,  "p90": 9e-05,   "max": 0.00054},
    "AUDUSD": {"n": 907,  "p90": 9e-05,   "max": 0.00036},
    "USDCAD": {"n": 896,  "p90": 0.00021, "max": 0.00084},
    "US500":  {"n": 1074, "p90": 0.6,     "max": 0.6},
    "US100":  {"n": 906,  "p90": 2.0,     "max": 2.0},
}

# Applies to every symbol above. Bounds are frozen: SINCE inclusive, UNTIL
# exclusive, two complete Mon-Fri cycles.
MEASURED_SPREADS_2026_09_WINDOW = {
    "since": "2026-08-16T00:00",
    "until": "2026-08-29T00:00",
    "filter": "get_spread_samples(market_open_only=True) "
              "-> market_hours.is_entry_allowed",
    "source": "signal_log.spread, VPS DB, collapsed to one sample per "
              "(symbol, minute)",
    "measured_at": "2026-09-03",
}

# HOUR 21 IS ABSENT BY CONSTRUCTION AND IS NOT A COVERAGE GAP. The 21:00
# rollover gate sets is_entry_allowed False for the whole hour, every day, all
# instruments, and that is exactly the predicate the filter uses — so a
# market-open-filtered pool CANNOT contain an hour-21 sample. The cost model
# prices trades the bot can actually place, and it never places one then. An
# hour-21 median would price a trade that cannot exist and would bias the
# table high (FX widens 11–19x in that hour, measured 2026-08-24).
#
# KNOWN LIMITATION OF THE MODEL SHAPE, not of the filter: is_entry_allowed
# governs ENTRIES. A position held through Friday 20:45 to Sunday 23:00 is
# still EXITED at reopen spreads (GBPUSD measured at 26 pips), and that cost is
# excluded here. A single round-trip constant cannot express an asymmetric
# entry/exit cost — that needs a different model shape, not a different filter.


def spread_table_sha(table: dict | None) -> str | None:
    """Content hash of the spread parameter table, stamped beside the model
    name so an edit that keeps the name is still detectable after the fact.

    Returns None when the current model has no per-symbol table — which is the
    case today: the flat constant is not keyed the same way, and a hash of
    "nothing measured" would imply more rigour than exists.
    """
    if not table:
        return None
    canonical = ";".join(f"{k}={table[k]!r}" for k in sorted(table))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]
