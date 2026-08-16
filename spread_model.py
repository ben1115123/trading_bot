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

CURRENT STATE: NOTHING HERE IS MEASURED.
`flat-roundtrip-dollars-UNCALIBRATED` names what engine.py actually does today:
subtracts a flat per-round-trip dollar constant from SPREAD_COSTS at exit. That
is not what live pays. Live crosses the book at ENTRY, in price units, which
shifts both trigger levels rather than deducting a fee — so the current model
is wrong in units, wrong in timing, and does not scale with position size.

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
CURRENT_SPREAD_MODEL = "flat-roundtrip-dollars-UNCALIBRATED"

# History:
#   flat-roundtrip-dollars-UNCALIBRATED
#       engine.py SPREAD_COSTS, flat USD per round trip, subtracted at exit.
#       Provenance: none. Origin of the numbers unknown, never measured
#       against a real quote, never revised. Treat every figure produced
#       under this model as optimistic by an unquantified amount.
#   (next) measured-YYYY-MM-X
#       Per-symbol, one-way, PRICE units, from captured samples. Must record
#       n, date range and source per symbol — a "measured" table with n=3 for
#       a symbol is not meaningfully better than a guess, and that has to be
#       visible at the point of use, not buried in a commit message.


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
