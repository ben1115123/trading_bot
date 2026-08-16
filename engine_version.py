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
"""

CURRENT_ENGINE_VERSION = "parity-v1"

# Bumped when the trade model changed, not when the code changed. The rule:
# bump only if two runs of the same strategy over the same candles would now
# produce different trades or different P&L. The sizing unit does exactly
# that — measured on AUDUSD 15MIN williams_r, trades 419 -> 391 and PF
# 1.115 -> 1.246, so pre-parity-v0 rows are not comparable to these.
