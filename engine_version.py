"""Backtest engine trade-model version.

Zero imports, no side effects — same safe-import contract as symbols.py, so
engine.py, models.py and scripts can all depend on it without cycles.

WHAT THIS VERSIONS: the engine's *trade model* — how a simulated trade is
entered, sized, exited and priced. Not the code, not the schema, not the
strategies. Bump ONLY when a change would make two runs of the same strategy
on the same candles produce different trades or different P&L.

Do NOT use commit SHAs. A SHA changes on every commit including ones that
cannot move a number; the point of this field is to answer "are these two
rows comparable?", and only a semantic version answers that.

History:
  pre-parity-v0  Everything written before 2026-08-16. Known-invalid: the
                 engine applies no take-profit for the 21 strategies that
                 never emit tp_price, sizes at $15 against live $10, applies
                 no _MIN_SL_DIST floor, and books every SL exit at a flat
                 -RISK_PER_TRADE regardless of the actual stop price.
                 See docs/SESSION_20260812_FINDINGS.md findings 1 and 12.
                 Rows carrying this version are history, never evidence.

  parity-v1      2026-08-16. SIZING UNIT ONLY — the take-profit contract is
                 still broken here. Fixed in this step: _MIN_SL_DIST floor now
                 applied (was absent entirely); risk sourced from
                 risk_manager.get_risk_per_trade per-symbol ($10, was a
                 hardcoded $15); lot clamp order matched to live (round then
                 clamp); unsizeable trades aborted instead of forced to the
                 0.1 minimum; SL exits booked from the actual stop price
                 instead of a flat -RISK_PER_TRADE.

                 *** DO NOT GENERATE PROMOTION EVIDENCE AT parity-v1. ***
                 21 of 34 strategies still run with no take-profit, which is
                 the defect that produced the AUDUSD divergence. This version
                 exists so that rows written between the sizing fix and the
                 contract fix are distinguishable, not because it is a model
                 worth measuring against. Wait for parity-v2.

  parity-v2      2026-08-16. The sl_price/tp_price CONTRACT. Three branches
                 mirroring live_signal_loop.py:552 — neither supplied gets the
                 engine default (tp = entry +/- DEFAULT_TP_R * floored stop,
                 DEFAULT_TP_R = 2.0, the measured live rule); both supplied are
                 passed through UNCHANGED, so the 13 emitters keep their own
                 designs including the three that are not R-multiples; exactly
                 one supplied raises EngineContractError. Also raises on
                 non-finite levels, wrong-side levels, and a non-positive stop
                 distance after flooring.

                 Exit ladder made explicit: sl_stop/tp_hit are intrabar and
                 outrank session_close/max_hold/signal, which are evaluated at
                 the bar's close. Order within the intrabar pair is the new
                 `intrabar_priority` flag ('sl' default = pessimistic; the old
                 code silently took TP-first). `reversal_exit` defaults False
                 to match live FX, which has no reversal exit at all. Every
                 run now reports `ambiguous_bars` so the size of the intrabar
                 assumption is visible rather than inferred.

                 STILL DIVERGENT at parity-v2, deliberately out of scope for
                 the whole sequence: spread modelling (commit 4), entry price
                 (live deals at offer/bid, engine uses the candle close), entry
                 lag (live fills 25-55min later), weekend handling, and session
                 windows. parity-v2 is the first version where the engine takes
                 profit at all — it is not yet a faithful execution model.
"""

CURRENT_ENGINE_VERSION = "parity-v2"

# Bumped when the trade model changed, not when the code changed. The rule:
# bump only if two runs of the same strategy over the same candles would now
# produce different trades or different P&L. The sizing unit does exactly
# that — measured on AUDUSD 15MIN williams_r, trades 419 -> 391 and PF
# 1.115 -> 1.246, so pre-parity-v0 rows are not comparable to these.
