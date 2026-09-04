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

  parity-v3      2026-09-04. MEASURED SPREAD, APPLIED TO PRICES AT THE
                 CROSSED SIDE. Collapses TWO of parity-v2's listed
                 divergences into one change, because they are one thing:
                 applying spread at entry IS the offer/bid entry-price fix.

                 Removed: SPREAD_COSTS and the flat per-round-trip dollar
                 deduction at exit. That model was wrong in units (dollars,
                 not price), wrong in timing (deducted at exit, paid at
                 entry), did not scale with position size, and none of its 12
                 numbers had ever been measured against a real quote.

                 Added: per-symbol measured medians from
                 spread_model.MEASURED_SPREADS_2026_09 (PRICE units,
                 spread_table_sha c0c905fc6c071dd4, n=896-1074 per symbol over
                 2026-08-16..2026-08-29, market-open filtered). Half the
                 spread is crossed at entry and half at exit:
                   entry  — BUY fills at close+half (lifts the ask),
                            SELL at close-half (hits the bid). The FILL, not
                            the mid, anchors sl/tp and sl_dist, as live does.
                   exits  — a LONG is closed by selling and is therefore
                            evaluated against BID (candle -half); a SHORT
                            against ASK (candle +half). Applies to the
                            intrabar sl/tp ladder AND to the close-based
                            session_close/max_hold/signal exits.
                 An unmeasured symbol raises UnmeasuredSpreadError rather than
                 falling back — a fallback would put two cost models inside
                 one engine_version.

                 NAMED RESIDUAL — THE PRICE SERIES IDENTITY IS ASSUMED, NOT
                 SHOWN. The symmetric application above is correct only if the
                 vendor caches carry a MID. Measured on candle_source_compare
                 (2026-09-04), restricted to rows whose yfinance and IG-stream
                 candles share an IDENTICAL timestamp, against IG stream mid:
                 AUDUSD n=2451 mean +2.434 pips (+8.1x its half-spread);
                 EURUSD n=3182 +3.209 (+10.7x); GBPUSD n=3345 +0.340 (+0.76x);
                 USDCAD n=2840 -0.935 (-1.44x). A bid series would read -1.0x
                 on every symbol and an ask series +1.0x; these signs DISAGREE
                 and the magnitudes span 0.76x-10.7x, so no bid/ask hypothesis
                 fits. The offsets are symbol-specific VENDOR price-level
                 differences, and on EURUSD and AUDUSD they are an order of
                 magnitude LARGER than the spread this version models. Mid is
                 assumed because the data cannot resolve the question, and
                 that assumption is recorded here rather than made silently.

                 STILL DIVERGENT at parity-v3: entry LAG (live fills 25-55min
                 after the decision candle), weekend handling, session
                 windows, and the vendor-vs-IG price-level offset above.
                 Spread modelling and entry price are no longer on this list.

                 🔴 THE SPREAD TABLE IS MEDIAN-ONLY AND ITS TAIL IS
                 UNCALIBRATED. RISK-OF-RUIN AND DRAWDOWN WORK MUST NOT USE IT.
"""

CURRENT_ENGINE_VERSION = "parity-v3"

# Bumped when the trade model changed, not when the code changed. The rule:
# bump only if two runs of the same strategy over the same candles would now
# produce different trades or different P&L. The sizing unit does exactly
# that — measured on AUDUSD 15MIN williams_r, trades 419 -> 391 and PF
# 1.115 -> 1.246, so pre-parity-v0 rows are not comparable to these.
