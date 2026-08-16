"""Version of the PAPER RESOLVER's simulated-P&L model.

Zero imports, no side effects — same safe-import contract as symbols.py,
engine_version.py, instrument_limits.py and spread_model.py.

SEPARATE FROM engine_version ON PURPOSE. The paper resolver
(`bot/live_signal_loop.py::_resolve_pending_paper_trades`) and the backtest
engine are two INDEPENDENT synthetic models that feed the same promotion
decisions. Findings doc finding 2 is explicit that they are siblings, not
subtask and parent: fixing one leaves the other. Stamping paper rows with
`engine_version` would imply a coupling that does not exist, and would make a
paper row appear to change model every time the engine did.

Spread provenance is NOT duplicated here — `paper_trades` reuses the
`spread_model` field and `spread_model.py` constant introduced for
backtest_results in 36fac3b. One spread model, stamped wherever it applies.

WHAT THIS VERSIONS: how a resolved paper trade's simulated P&L is produced —
outcome detection, sizing, value-per-point, spread treatment, price scale.
Bump only when a change would make the same stored signal resolve to a
different simulated_pnl.

History:
  pre-parity-v0  Everything written before 2026-08-16, and everything written
                 until the resolver defects are actually fixed. Known-invalid:
                 no spread deducted anywhere; no ig_scale conversion on the
                 paper write path (see paper_trades id=824, a native
                 points-scale EURUSD price that booked -$2,500); sl_distance
                 clamped but never validated; lot size clamped but never
                 rounded, unlike live and the engine; a zero stop distance
                 silently sized to the 0.1 minimum instead of aborting;
                 USDCAD sized against value_per_point 1.0 instead of 10000.0
                 because it is missing from a third copy of that table
                 (finding 16); and 557 shadow rows resolved and aggregated as
                 though they were real trades (finding 17).

                 Risk per trade also varied across four regimes inside this
                 one version — per-symbol overrides before 2026-06-12, then
                 $15, then $3 from 2026-07-02, then $10 from 2026-07-08. The
                 `risk_per_trade` column exists to record it per row instead
                 of forcing that recovery again; it is NULL until the
                 re-baseline populates it.

                 Rows carrying this version are history, never evidence.
"""

CURRENT_PAPER_MODEL = "pre-parity-v0"

# Set deliberately to pre-parity-v0, NOT to a new version. This commit adds
# the stamp and nothing else — the resolver is untouched and still produces
# the defective model, so labelling new rows as anything else would be a lie.
# Same reasoning, and the same sequencing, as engine_version's first commit:
# the stamp lands BEFORE any behaviour change so that no row can ever be
# written unmarked. The constant bumps in the commit that actually changes how
# simulated_pnl is computed.
