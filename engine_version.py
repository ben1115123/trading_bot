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
"""

CURRENT_ENGINE_VERSION = "pre-parity-v0"

# Set deliberately to pre-parity-v0, NOT to a new version. This commit only
# adds the marking; the engine itself is untouched and still produces the
# pre-parity model, so labelling new rows as anything else would be a lie.
# The constant bumps in the commit that actually changes the trade model.
