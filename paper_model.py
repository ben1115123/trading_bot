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

  paper-v1       2026-08-16. THREE STRAIGHT BUGS plus a bracket rejection —
                 all wrong under any model, none of them modelling choices:
                   - value_per_point now read from instrument_limits.
                     VALUE_PER_POINT by [symbol] rather than a third local copy
                     via .get(symbol, 1.0). USDCAD was missing from that copy,
                     so 97 rows booked ~1/2000th of their value (finding 16).
                     USDJPY is 100, not 10000 — JPY pips are 0.01.
                   - lot size rounded THEN clamped, matching risk_manager and
                     the backtest engine. The resolver clamped without ever
                     rounding, disagreeing with both at the boundaries.
                   - a zero/negative stop distance ABORTS instead of booking at
                     the 0.1 lot minimum, mirroring risk_manager:30-32.
                   - malformed brackets (sl == tp, or levels on the wrong side
                     of entry) are REFUSED, mirroring the backtest engine's
                     EngineContractError. Rows 253/334/335 carried sl == tp and
                     booked a LOSS with POSITIVE P&L; those same rows are
                     finding 3's MAX-clamp entries and finding 19's win-basis
                     disagreement. One defect, three symptoms.

                 STILL DEFECTIVE at paper-v1, deliberately: no spread deducted,
                 no ig_scale conversion on the paper write path, resolution
                 still against yfinance regardless of CANDLE_SOURCE, no
                 resolution timeout, and the 100-candle window can mis-resolve
                 a stale trade. Those are model changes and land at paper-v2.

                 The win-basis inconsistency (finding 19) is NOT fixed here.
                 Rejection surfaces the malformed rows; changing the count
                 would have hidden them.

  paper-v2       2026-08-17. The RESOLUTION WINDOW and the outcome vocabulary.
                   - The window is now derived from the row's signal time
                     instead of a 100-candle tail trim. `count` never
                     controlled the fetch (_fetch_yfinance_candles downloads a
                     fixed period and slices the tail), so for any row older
                     than that tail EVERY returned candle passed the
                     "after the signal" filter and the row resolved against a
                     window weeks downstream of its own signal. Not truncation
                     — a disjoint window. Costs zero extra API calls; the same
                     download always happened.
                   - PENDING no longer means two things. Three terminal
                     outcomes separate "not resolved yet" from "will never
                     resolve": REFUSED (the row is unusable), EXPIRED (past the
                     14-day relevance horizon), NO_HISTORY (the source
                     provably cannot cover the signal's window). All three
                     carry simulated_pnl = NULL, never 0.0.
                   - Fetch exceptions are classified instead of swallowed.
                     Structural (AttributeError/TypeError/KeyError/ValueError)
                     terminates; everything else stays PENDING and retries.
                     Unknown deliberately falls to transient — see
                     _classify_fetch_error for why the polarity is not
                     symmetric.
                   - resolved_at and resolution_reason recorded per row.

                 THE BUMP IS CARRIED BY THE WINDOW AND THE OUTCOME SET, not by
                 the new columns. Same row, same candles, different result:
                 a stale row that booked a WIN off a far-future bar now books
                 a LOSS, or terminates without a P&L at all. resolved_at rides
                 along in the same commit because the schema was being touched
                 anyway — riding along is not the same as justifying the
                 version.

                 STILL DEFECTIVE at paper-v2, deliberately: no spread deducted,
                 no ig_scale conversion on the paper write path, and resolution
                 remains against yfinance regardless of CANDLE_SOURCE. That
                 last one is now an ACCEPTED DIVERGENCE rather than a to-do —
                 findings doc finding 21.
"""

CURRENT_PAPER_MODEL = "paper-v2"

# Bumped per the standing rule: would two runs over the same row and the same
# candles produce a different result? Yes — the resolution window changed, so
# different bars decide the outcome, and rows that would have booked a WIN or
# LOSS now terminate as REFUSED/EXPIRED/NO_HISTORY, changing every aggregate's
# denominator. paper-v1 rows are not comparable to paper-v2 rows.
