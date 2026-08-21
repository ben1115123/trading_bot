"""Spread-relative-to-stop gate. SHADOW ONLY — logs, does not block.

Zero project imports, no side effects — same safe-import contract as
symbols.py, engine_version.py, instrument_limits.py and market_hours.py. Both
entry paths (bot/live_signal_loop.py and webhook/receiver.py) import THIS
module. Do not copy the threshold into either caller: this tree has been bitten
four times by independently-hardcoded duplicate tables (symbols.py,
instrument_limits.py, _EPIC_VALUE_PER_POINT, candle_stream.EPIC_MAP), and each
time the copies diverged by OMISSION rather than by contradiction, which is the
harder failure to see.

WHAT THIS MEASURES, AND WHY IT IS NOT `should_block_spread`
-----------------------------------------------------------
`filters/webhook_filters.py::should_block_spread` has never blocked a single
alert in its lifetime, and reviving it is not possible — it is the wrong SHAPE,
not merely mis-fed and mis-tuned (findings doc finding 15, severity amended
2026-08-21). Three independent blockers:

  1. NORMAL_SPREADS holds only US500/EURUSD/DAX. GBPUSD, AUDUSD, USDCAD and
     US100 are absent, so `if normal and ...` fails OPEN for four of the six
     traded symbols even when a live spread IS supplied.
  2. EURUSD's 0.0008 blocks at 16 pips. The measured hour-21 EURUSD median is
     6.3 pips — it would not block the blowout it most needs to.
  3. Structural, and decisive: its signature takes no `sl_distance`. What
     matters is spread RELATIVE TO THE STOP, and that predicate cannot be
     expressed in `(symbol, current_spread)`.

So: revive the INPUT (a live spread, from candle_stream.get_spread, rather than
a TradingView payload key that has never once been present in 382 stored
payloads), replace the SHAPE. That is what this module is.

THE RATIO
---------
    ratio = spread / sl_distance          both in PRICE units, same scale

`sl_distance` is the distance from entry to the stop AFTER the _MIN_SL_DIST
floor has been applied — the stop actually sent to IG, not the raw candle
range. Using the unfloored range would understate the ratio on exactly the
trades this gate exists to catch, since the floor binds on 45-55% of FX
entries (finding 14).

THE MECHANISM CEILING — ratio >= 1.0
------------------------------------
At ratio >= 1.0 the bid/ask straddle spans the ENTIRE stop. The position is not
mispriced, it is arithmetically lost at entry: it opens already at or through
its own stop and closes within ~60-90 seconds.

This claim needs no calibration and no imputation. Measured directly:

    ratio >= 1.0   ->   8 trades, 0 winners, net -$74.64

That is the floor of what is known here and it stands on its own, independent
of everything below. RATIO_CEILING is recorded separately from SHADOW_K for
exactly that reason — one is a fact about arithmetic, the other is a tuning
choice under uncertainty. Do not merge them.

WHY SHADOW_K IS 0.25 AND NOT 0.10
---------------------------------
The empirical crossover in the historical record sits at ratio ~= 0.10. Every
band below it clears the 33.3% win rate that a 2R payoff needs to break even;
every band above it fails:

    ratio band     n    WR%    exp$     vs 33.3% breakeven
    0.00-0.04    101   41.6   -0.49     ABOVE
    0.04-0.06    101   39.6   -1.28     ABOVE
    0.06-0.08    122   36.1   -1.14     ABOVE
    0.08-0.10    109   45.9   +2.12     ABOVE   <- only positive band
    0.10-0.12    171   26.9   -2.39     below
    0.12-0.14    137   25.5   -2.32     below
    0.14-0.17     91   28.6   -1.20     below
    0.17-0.20     20   30.0   -0.79     below
    0.20-0.25     25   24.0   -3.65     below
    0.25-0.40     37   13.5   -5.13     below
    >= 0.40       11    0.0   -8.05     below

k = 0.10 is NOT used, for three reasons, and the first is the important one:

  1. THE CROSSOVER IS CONFOUNDED BY IMPUTATION. trades.spread was a hardcoded
     None until 2026-08-16, so 837 of the 925 usable rows carry an IMPUTED
     symbol-hour median rather than a measured spread. Where the spread is
     imputed it is a per-(symbol,hour) CONSTANT, so ratio collapses to
     `constant / sl_distance` — i.e. the "spread gate" is substantially a
     TIGHT-STOP gate wearing a spread gate's clothes. The two cannot be
     separated on this data.
  2. THE UNCONFOUNDED SUBSET DOES NOT REPRODUCE IT. On the n=88 rows with a
     genuinely measured spread, the 0.15-0.25 band shows 31.6% WR / +$0.03 —
     no crossover visible. Small and noisy, but it is the only clean evidence
     there is, and it does not confirm 0.10.
  3. k=0.10 would block 492 of 925 trades. That is not a tail gate, it is a
     different trading system.

0.25 is chosen as a TAIL gate: FX ratio p90 is 0.196 and p99 is 1.012, so 0.25
sits just above p90 (~5% of entries) and well clear of the 1.0 ceiling. It
blocks 48 historical trades of which 5 were winners, saving $278.41.

RECALIBRATE when trades.spread has real coverage across all hours and weekdays
— the same precondition the spread-table gate in CLAUDE.md is waiting on, and
blocked by the same missing data. Until then this module BLOCKS NOTHING.

STATUS: SHADOW. would_block() reports; no caller acts on it. Promoting it to a
live gate is a separate, deliberate change and must not happen as a side effect
of tuning k.
"""

# Ratio at or above which the spread spans the entire stop. Arithmetic, not a
# tuning parameter — see the module docstring. Measured: 8 trades, 0 winners.
RATIO_CEILING = 1.0

# Shadow threshold. A tail gate at roughly FX p90. NOT the empirical crossover
# (~0.10), which is confounded by imputation — see the module docstring before
# changing this.
SHADOW_K = 0.25

# Flip to True ONLY as a deliberate promotion, never while tuning SHADOW_K.
ENFORCE = False

MODEL = "spread-gate-shadow-v1-k0.25-UNCALIBRATED"


def spread_ratio(spread, sl_distance):
    """spread / sl_distance, or None when either input is unusable.

    Returns None rather than 0.0 on missing data. The distinction matters:
    0.0 reads as "measured, and tight", None reads as "not measured", and
    conflating them is how a fail-open filter looks like a passing one. Every
    caller must treat None as UNKNOWN, never as safe.
    """
    if spread is None or sl_distance is None:
        return None
    try:
        spread = float(spread)
        sl_distance = float(sl_distance)
    except (TypeError, ValueError):
        return None
    if sl_distance <= 0 or spread < 0:
        return None
    if spread != spread or sl_distance != sl_distance:   # NaN
        return None
    return spread / sl_distance


def evaluate(symbol, spread, sl_distance, k=None):
    """Assess one prospective entry. Never raises, never blocks.

    Returns a dict:
      ratio          float | None   None means NOT MEASURED, not "safe"
      would_block    bool           ratio >= k
      over_ceiling   bool           ratio >= RATIO_CEILING (arithmetically lost)
      k              float          threshold applied
      reason         str | None     stable string for signal_log / notes
      model          str            MODEL stamp

    `reason` strings are the marker test for this gate — a shadow gate that
    fires must leave a positive signal naming itself, never be inferred from
    an absence. Keep them stable; anything grepping for this control matches
    on them.
    """
    k = SHADOW_K if k is None else k
    ratio = spread_ratio(spread, sl_distance)

    if ratio is None:
        return {"ratio": None, "would_block": False, "over_ceiling": False,
                "k": k, "reason": None, "model": MODEL}

    over_ceiling = ratio >= RATIO_CEILING
    would_block = ratio >= k

    reason = None
    if over_ceiling:
        # Reported separately from an ordinary breach because it is a
        # different kind of claim — see RATIO_CEILING.
        reason = (f"SHADOW spread gate: ratio {ratio:.3f} >= ceiling "
                  f"{RATIO_CEILING} — spread spans the entire stop "
                  f"({symbol}, spread={spread}, sl_dist={sl_distance})")
    elif would_block:
        reason = (f"SHADOW spread gate: ratio {ratio:.3f} >= k {k} "
                  f"({symbol}, spread={spread}, sl_dist={sl_distance})")

    return {"ratio": ratio, "would_block": would_block,
            "over_ceiling": over_ceiling, "k": k,
            "reason": reason, "model": MODEL}


def should_block(symbol, spread, sl_distance, k=None):
    """Live-gate form. Returns False while ENFORCE is False — always, today.

    Exists so that promoting the gate is a one-line, reviewable change at ONE
    site rather than an edit spread across both entry paths. Callers may wire
    this in now; it is inert until ENFORCE flips.
    """
    if not ENFORCE:
        return False
    return evaluate(symbol, spread, sl_distance, k)["would_block"]
