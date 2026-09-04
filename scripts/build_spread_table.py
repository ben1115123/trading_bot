#!/usr/bin/env python3
"""Measure and freeze the per-symbol spread table from captured signal_log samples.

PASS A OF TWO. This script MEASURES and FREEZES. It does not apply anything:
the engine still subtracts the flat SPREAD_COSTS dollar constant, and
spread_model.CURRENT_SPREAD_MODEL still names that constant. Applying the
measured table to the engine, recalibrating NORMAL_SPREADS and bumping
engine_version are pass B.

    THE TAIL IS UNCALIBRATED. This table is a per-symbol MEDIAN and nothing
    else. It says what a typical placeable entry costs; it says NOTHING about
    the wide tail. RISK-OF-RUIN AND DRAWDOWN WORK MUST NOT USE THIS TABLE —
    ruin lives in the tail, and a median-only model will report a ruin
    probability that is optimistic by an unquantified amount. The pre-parity
    ruin table was already wrong by more than an order of magnitude
    (5.58% vs 67.3-84.3%); feeding it a median-only spread is how that
    happens a second time.

UNITS: PRICE units, the same units signal_log.spread is stored in.
EURUSD 0.00006 is 0.6 pips, not 6 pips. Several tables in CLAUDE.md quote pips
for readability and the model being replaced here is wrong in units
(flat dollars), so both representations are printed side by side — a unit
error should be visible, not inferred.

WHY THE BOUNDS ARE PINNED: the sample pool grows every five minutes, so an
unbounded query is not reproducible and the content hash stamped beside a
result row would drift under it. SINCE/UNTIL below are frozen. Re-running this
script must reproduce the table and the sha byte for byte.

READ ONLY. Issues no IG request and writes nothing to the database.
"""
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from statistics import median

# Runs in the bot container (docker cp + docker exec), because signal_log lives
# in the VPS DB only — the local trades.db does not have these rows
# (finding 11, local-vs-VPS corpus split). Falls back to the repo root so an
# accidental local run fails on the empty pool with a readable message rather
# than on an import.
sys.path.insert(0, "/app" if os.path.isdir("/app") else
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import get_spread_samples          # noqa: E402
from spread_model import spread_table_sha               # noqa: E402

# ---------------------------------------------------------------- frozen pool
# Two complete Mon-Fri cycles. CLAUDE.md's gate prefers two weeks over one:
# one cycle gives ~20 observations per hour, two gives ~40 and a realistic
# chance of catching a news day, which is where the tail actually lives.
# (The tail is not modelled here — see the header — but a pool that never saw
# one is a worse basis even for a median.)
#
# SINCE is inclusive, UNTIL is EXCLUSIVE. SINCE reaches back to Sun 2026-08-16
# deliberately: entry is permitted from 23:00 Sunday, so the Sunday-evening
# rows after that hour are inside the cost model's domain. The excluded
# Sunday reopen ramp (20:00-22:59) is dropped by the market-open filter, not
# by these bounds.
SINCE = "2026-08-16T00:00"
UNTIL = "2026-08-29T00:00"

SYMBOLS = ["EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "US500", "US100"]

# For the human-readable second column only. FX quotes in pips (1 pip =
# 0.0001); the indices are quoted in index points and are already 1:1, so
# their "readable" column is the same number with a different label. This
# mirrors the Value/Point column of the canonical asset table.
READABLE = {
    "EURUSD": (10000, "pips"), "GBPUSD": (10000, "pips"),
    "AUDUSD": (10000, "pips"), "USDCAD": (10000, "pips"),
    "US500":  (1, "points"),   "US100":  (1, "points"),
}

# Entry is permitted 00:00-20:00 and 22:00-23:00 UTC.
#
# HOUR 21 IS EXCLUDED BY CONSTRUCTION AND IS NOT A GAP. The 21:00 rollover
# gate sets market_hours.is_entry_allowed False for the whole hour, every day,
# all instruments, and that predicate is exactly what
# get_spread_samples(market_open_only=True) filters on. A market-open-filtered
# pool therefore CANNOT contain an hour-21 sample. Waiting for one is waiting
# forever - this is the second instance of CRITERIA AGE AGAINST THE SYSTEM
# THEY MEASURE. The cost model prices trades the bot can actually place, and
# it never places one in hour 21.
PERMITTED_HOURS = set(range(0, 21)) | {22, 23}
REQUIRED_HOURS_EXPLICIT = {18, 19, 20, 22}   # the hours that failed on 2026-08-17
REQUIRED_WEEKDAYS = {0, 1, 2, 3, 4}          # Mon-Fri
MIN_SAMPLES = 480

_WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def load(symbol: str) -> list:
    """Filtered, frozen sample pool for one symbol.

    market_open_only=True is NOT optional here and must never be flipped for
    calibration: the raw pool carries closed-book quotes that the 900s
    staleness guard does not catch, and calibrating on it produces a constant
    ~10x too wide - the exact NORMAL_SPREADS error this work exists to fix.
    """
    rows = get_spread_samples(symbol=symbol, since=SINCE, market_open_only=True)
    return [r for r in rows if r["minute"] < UNTIL]


def percentile(values: list, q: float) -> float:
    """Nearest-rank percentile. Deterministic, no interpolation, no numpy."""
    s = sorted(values)
    idx = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[idx]


def main() -> int:
    print("=" * 72)
    print("SPREAD TABLE - MEASURE AND FREEZE (pass A: not applied to engine)")
    print(f"frozen bounds: SINCE={SINCE} (incl)  UNTIL={UNTIL} (excl)")
    print("filter: get_spread_samples(market_open_only=True) "
          "-> market_hours.is_entry_allowed")
    print("units: PRICE units, as stored in signal_log.spread")
    print("=" * 72)

    pools, failures = {}, []

    print("\n--- STEP 1: GATE, ENUMERATED PER SYMBOL ---")
    for sym in SYMBOLS:
        rows = load(sym)
        pools[sym] = rows
        if not rows:
            print(f"\n{sym}: n=0 - NO DATA IN FROZEN WINDOW")
            failures.append(f"{sym}: empty pool")
            continue

        mins = [r["minute"] for r in rows]
        hours = sorted({int(m[11:13]) for m in mins})
        wds = sorted({datetime.fromisoformat(m).replace(tzinfo=timezone.utc).weekday()
                      for m in mins})
        by_hour = Counter(int(m[11:13]) for m in mins)

        print(f"\n{sym}:")
        print(f"  n after filtering : {len(rows)}")
        print(f"  first sample      : {min(mins)}")
        print(f"  last sample       : {max(mins)}")
        print(f"  UTC hours present : {hours}")
        print(f"  weekdays present  : {[_WD[d] for d in wds]}")
        print(f"  per-hour counts   : "
              f"{ {h: by_hour[h] for h in sorted(by_hour)} }")

        # Criterion 1 - enumerate what is missing rather than asserting a bool.
        missing = sorted(PERMITTED_HOURS - set(hours))
        if missing:
            print(f"  !! PERMITTED HOURS EMPTY: {missing}")
            failures.append(f"{sym}: permitted hours empty {missing}")
        else:
            print(f"  ok  all {len(PERMITTED_HOURS)} permitted hours present")
        still = sorted(REQUIRED_HOURS_EXPLICIT - set(hours))
        if still:
            print(f"  !! REQUIRED HOURS 18/19/20/22 EMPTY: {still}")
            failures.append(f"{sym}: required hours empty {still}")
        if 21 in hours:
            # Would mean the rollover gate is not doing what CLAUDE.md says.
            print("  !! HOUR 21 PRESENT - rollover gate or filter has changed")
            failures.append(f"{sym}: hour 21 present in filtered pool")

        # Criterion 2
        miss_wd = sorted(REQUIRED_WEEKDAYS - set(wds))
        if miss_wd:
            print(f"  !! WEEKDAYS MISSING: {[_WD[d] for d in miss_wd]}")
            failures.append(f"{sym}: weekdays missing {[_WD[d] for d in miss_wd]}")
        else:
            print("  ok  Mon-Fri all present")

        # Criterion 3
        if len(rows) < MIN_SAMPLES:
            print(f"  !! n={len(rows)} < {MIN_SAMPLES}")
            failures.append(f"{sym}: n={len(rows)} < {MIN_SAMPLES}")
        else:
            print(f"  ok  n={len(rows)} >= {MIN_SAMPLES}")

    if failures:
        print("\n--- GATE FAILED. TABLE NOT BUILT. ---")
        for f in failures:
            print(f"  {f}")
        return 1
    print("\n--- GATE PASSED on all six symbols ---")

    # ------------------------------------------------------------ STEP 2
    print("\n--- STEP 2: THE TABLE (median) + context (p90, max) ---")
    print(f"{'symbol':8} {'n':>5}  {'MEDIAN(price)':>14} {'median(read)':>14}  "
          f"{'p90(price)':>11} {'max(price)':>11}")
    table = {}
    for sym in SYMBOLS:
        vals = [r["spread"] for r in pools[sym]]
        med = round(median(vals), 8)
        table[sym] = med
        factor, unit = READABLE[sym]
        print(f"{sym:8} {len(vals):>5}  {med:>14.8f} "
              f"{med * factor:>9.2f} {unit:4}  "
              f"{round(percentile(vals, 0.90), 8):>11.8f} "
              f"{round(max(vals), 8):>11.8f}")
    print("\np90 and max are CONTEXT ONLY and are NOT in the table. "
          "The tail is uncalibrated.")

    # ------------------------------------------------------------ STEP 3
    sha = spread_table_sha(table)
    print("\n--- STEP 3: FROZEN ARTIFACT ---")
    print("MEASURED_SPREADS_2026_09 = {")
    for sym in SYMBOLS:
        n = len(pools[sym])
        mins = [r["minute"] for r in pools[sym]]
        print(f"    {sym!r:10}: {table[sym]!r},"
              f"   # n={n}, {min(mins)[:10]}..{max(mins)[:10]}")
    print("}")
    print(f"spread_table_sha = {sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
