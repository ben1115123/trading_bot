# TRADING BOT — DEVELOPMENT ROADMAP
Last updated: 2026-08-16
Rule: this file is updated whenever a tier item 
completes or a gate decision resolves.

## HARD GATE — RESOLVED 2026-08-12: Branch B (DIVERGES)

**Gate condition met.** Required 40+ clean single-position 
post-cap demo-live AUDUSD trades. Delivered: **51 post-cap 
trades, 50 closed**, verified clean by interval-overlap 
scan — zero overlapping `[entry, close]` pairs on AUDUSD, 
and zero on EURUSD/GBPUSD/USDCAD. The concurrent-position 
cap (`risk/concurrent_positions.py`, deployed 
2026-07-24 21:13:48 UTC) held without exception.

**Result vs promotion basis.**

| | Promotion basis | Live demo actual |
|---|---|---|
| Profit factor | median **1.285** | **0.71** |
| Windows profitable | 83.3% | — |
| Win rate | — | 26.0% |
| Net | — | **−$109.07** |
| Expectancy | — | **−$2.18/trade** |

AUDUSD was the only roster strategy to clear the full 
ROBUST gauntlet. It is the **worst live performer of the 
four williams_r instances**. Across all four the 
backtest-to-live ranking inverts: predicted AUDUSD > 
EURUSD > GBPUSD > USDCAD; observed USDCAD ≈ EURUSD > 
GBPUSD > AUDUSD.

**Diagnosis: ENGINE FLATTERY.** The backtest models a 
different strategy from the one running live — no 
take-profit for `williams_r` (`engine.py:291` reads 
`tp_price`, `WilliamsRStrategy` never emits it; zero 
`tp_hit` across 403 trades), while live took profit on 
30% of exits and **100% of live gross wins came through 
TP**. Plus `RISK_PER_TRADE = 15.0` against live `$10`. 
See SESSION_20260812_FINDINGS.md finding 1.

**Execution residue is ruled out.** Concurrent cap holding 
(zero overlaps, all four symbols); poller clean (4/4 
tracked, ~30s cadence, DB matching IG deal-for-deal); 
stops attached broker-side on every open position 
(`stopLevel`/`limitLevel` present, `controlledRisk: 
false`); sizing arithmetically correct (every live trade 
prices to ≈$10). Execution did what it was told; the 
instruction was wrong.

**AMENDMENT 1 — the stability-map claim overstates the 
data.** "23 contiguous cells at PF ≥ 1.1" is a 
**profit-factor contour, not a plateau of robust 
configurations.** Of the 84 recorded cells: FRAGILE 38, 
MARGINAL 34, REJECT 11, **ROBUST 1.** Twenty-five clear 
PF ≥ 1.1, so the contour is real — but exactly one cell 
in the map earns a ROBUST verdict.

**AMENDMENT 2 — no comparison baseline exists.** There is 
**no `walk_forward` row for `williams_r` on any symbol**, 
VPS or local. The "83.3% of 6 windows" figure survives 
only as prose. `walkforward_runs` was created 2026-07-22, 
one week after the 2026-07-15 promotion, so the 
justifying run was never persisted. What exists locally: 
the headline verdict (inside the permutation row's 
`extra_json`), the 84-cell stability map, a 200-iteration 
permutation test, and 25 Monte Carlo rows including the 
Phase-5 ruin sweep. **The finding is the recurrence, not 
the absence** — this file already documented the same gap 
for EURUSD williams_r as a one-off. It silently applied to 
the flagship too, unnoticed for four weeks. Verdicts must 
be written to `walkforward_runs` when produced, or they 
are not evidence.

**Overfit residue is NOT ruled out.** The engine defect is 
sufficient to explain a large divergence but does not 
establish that these parameters would generalise on a 
correct engine. The stability map and permutation result 
were computed by the same flawed engine and inherit the 
same defect — they establish robustness *within a model 
that cannot take profit*.

Re-running the gauntlet on the corrected engine is 
therefore **regeneration, not reproduction**: for 
walk-forward there is no prior artifact to diff against. 
Stability map, permutation and Monte Carlo permit a 
genuine before/after comparison, provided the old rows 
are marked `pre-parity-v0` and never mixed with post-fix 
results.

**What the gate blocks until re-certification:** promotion 
or commitment of ANY new strategy; Tier 3 hunts do not 
open. Exploration remains allowed, but **no result from 
the current engine constitutes promotion evidence.** 
Re-certification requires the engine parity fix, the 
paper-resolver sibling fix, a full gauntlet regeneration, 
and fresh comparison against live demo data collected 
under the corrected model.

## STAGE 1 — ENGINE PARITY: COMPLETE except commit 5
Landed 2026-08-16 in four commits.

- [x] **e0f51f8 — engine_version marking.** Three-version progression: 
  `pre-parity-v0` (all 268,117 existing rows, history not evidence) → 
  `parity-v1` (sizing only, half-fixed) → `parity-v2` (current). 
  `get_backtest_results()` filters to current; `score_strategies()` 
  raises rather than ranking across models.
- [x] **14c3c17 — sizing unit.** MIN_SL_DIST floor (shared via 
  `instrument_limits.py`, not copied), risk via 
  `get_risk_per_trade`, clamp order matched to live, unsizeable 
  trades aborted, SL booked from the actual stop price. Also 
  `.dockerignore` for `database/`+`logs/`, closing the 
  failed-mount hazard.
- [x] **0fdbe7e — the contract.** Three branches, `DEFAULT_TP_R = 
  2.0` for non-emitters only, `EngineContractError` on a 
  half-specified signal, explicit exit ladder, 
  `intrabar_priority='sl'`, `reversal_exit=False`, 
  `ambiguous_bars` reported every run. **tp_hit non-zero for the 
  first time.**
- [x] **36fac3b — spread capture.** Real observations flowing into 
  `trades.spread` and `signal_log.spread` from two zero-extra-call 
  sources. Flat constant deliberately retained and named, not 
  deleted. No version bump — instrumentation, not a model change.

- [ ] **COMMIT 5 — spread option B. GATED on ~2 days of WEEKDAY 
  spread data** (capture started Sunday 2026-08-16 pre-open; those 
  samples are real but not representative — EURUSD read ~1.5 pips 
  on a thin book, GBPUSD ~14.6). Half-spread at entry, 
  spread-shifted trigger levels, flat constant deleted. Bumps 
  `engine_version` — changing how spread is applied IS structural. 
  Also recalibrates `NORMAL_SPREADS` from the same measurements and 
  re-derives the live filter threshold rather than inheriting `2x` 
  (finding 15).

**Result after Stage 1:** AUDUSD PF live 0.71 vs v1 1.246 vs v2 
1.085. Converging, still flattering, spread the known residual. 
**Still not promotion evidence.**

**Key finding — TP and reversal exit are ENTANGLED.** Neither 
change alone explains the result, which is why the missing 
take-profit survived months of runs. See CLAUDE.md for the 
isolation table.

**Still NOT modelled after Stage 1** (out of scope for the whole 
sequence): entry price (live deals at offer/bid, engine uses the 
candle close), entry lag (25-55min), weekend handling, session 
windows.

## STAGE 2 — PAPER RESOLVER (next after commit 5)
Sibling to engine parity, not a subtask — two independent 
synthetic models feed promotion decisions and fixing one leaves 
the other. Deduct spread (now measurable), route prices through 
`ig_scale.to_decimal()`, add an `sl_distance` sanity bound that 
**rejects at both ends**, quarantine `paper_trades` id=824. 
See findings doc finding 2.

## STAGE 3+ — after the paper resolver
Steps 1-3 of the original sequence (engine contract, 
`engine_version` marking, paper resolver) are Stage 1 and Stage 2 
above. What remains, in order:

1. **Re-validation** — regenerate the gauntlet under the 
   corrected engine. Audit the 13 emitting strategies' TP 
   rules while here: emitting something is not evidence of 
   emitting the right thing, and those rules have never 
   been checked.
2. **Promotion gate** — advisory report for one full 
   cycle, then hybrid: hard gate on numeric criteria, 
   advisory on correlation and judgement calls. Overrides 
   impossible to make silently; must record 
   `engine_version` alongside the metric snapshot. Refuse 
   to cite a walk-forward verdict that has no 
   `walkforward_runs` row — that alone would have caught 
   both EURUSD and AUDUSD.

Independent of the above, do first (cheap, unblocks 
nothing but closes a live hole): the `status` fail-open 
default at all three layers, and restricting cron to 
writing `'paper'` only.

## TIER 1 — COMPLETE (2026-07-16)
Quota-fallback alert dedup; yfinance-fallback UTC 
fix (3rd timezone bug of its class); drift 
investigation (post-flip increase = decision-to-
execution lag + mid-vs-dealing artifact, NOT a 
regression). 
HELD: SL DRIFT alert threshold raise (until 
mid-vs-dealing fix makes drift cleanly measurable). 
DEFERRED: mid-vs-dealing comparison fix (cosmetic; 
batch with future reanchor review).

## TIER 2 — THE FORK — RESOLVED 2026-08-12 (Branch B)
- [x] **AUDUSD reconciliation read — DONE.** 51 post-cap 
  clean trades, 50 closed. Verdict: DIVERGES. PF 0.71 vs 
  1.285 promotion basis. Diagnosis engine flattery, 
  execution ruled out, overfit residue not ruled out. 
  Full detail in the HARD GATE section above. The 
  40-trade bar was met on the post-cap sample only — the 
  pre-cap history (49 closed, 37 stacked) never counted, 
  per the 2026-07-25 clock reset.
- [ ] **GBPUSD + stoch_rsi FRAGILE review gate — STILL 
  OPEN, now ~4 weeks overdue** (was scheduled July 21). 
  Partly overtaken by events: `US500 HOUR stoch_rsi` was 
  deactivated 2026-08-13 on invalid-evidence grounds 
  (history row 42), so only the GBPUSD half remains 
  live. GBPUSD id 32 runs `period=21/-90/-20`, which is 
  **not** the config any walk-forward run used — the 
  review needs its real params pulled first.
- [ ] **NEW — selector re-arm decision.** The daily 
  selector is inert as of 2026-08-15 (cron line commented 
  + all three of its symbols blocklisted). It stays inert 
  until the engine fix and `engine_version` marking land; 
  re-arming is a deliberate decision, not a default, and 
  requires undoing both layers.

Superseded wording of both Tier 2 items (the pre-cap 
clock reset, the -$219.63 stacking analysis, the 
original 30/40-trade trigger spec) is in git history at 
commit b0c7261 and earlier.

## TIER 3 — EDGE INVENTORY EXPANSION 
**BLOCKED — does not open.** The hard gate resolved 
Branch B, which explicitly holds Tier 3 hunts shut until 
re-certification on a corrected engine. Exploration is 
still allowed; no result from the current engine counts 
as promotion evidence. Items below are queued, not 
started.
(post-reconciliation; the actual priority — edge 
inventory is the bottleneck, not orchestration)
- [ ] Pairs trading research: EURUSD/GBPUSD/AUDUSD 
  spread cointegration, z-score entry/exit, hard 
  regime-break stop. Genuinely new edge class 
  (market-neutral) vs exhausted directional space.
- [ ] H4 momentum/trend re-test: Donchian, MACD, 
  KAMA, supertrend on H4 through the FULL gauntlet. 
  All prior momentum failures were 15MIN-specific; 
  H4 is where trend edges structurally survive or 
  the concept dies fairly. Needs deeper H4 history 
  (see data sources).
- [ ] TP-method improvement on AUDUSD: candle-range 
  TP is a noisy proxy. Test ATR-based (proper 
  re-test), structure-based (swing/S-R), partial 
  exits. Full gauntlet, on the validated edge only.
- [ ] Deflated Sharpe ratio added as a standard 
  gauntlet gate (corrects for ~60 strategies 
  tested; Bailey & López de Prado).
- [ ] Academic strategy library as idea source 
  (Quantpedia free tier or similar): filter for 
  FX/CFD/intraday-applicable subset; ignore papers' 
  in-sample stats; full gauntlet per candidate.
- [ ] Liquidity-sweep reversal (ICT "Session Raid"/
  "Judas Swing" family): mechanically defined as 
  prior-session high/low breach + reversal 
  confirmation, session-timed. Structurally novel 
  vs current mean-reversion/momentum roster (trades 
  a specific microstructure event). Full gauntlet. 
  NOTE: ICT concepts are discretionary heuristics — 
  the edge is in OUR mechanical definition, not the 
  ICT label; the video's tier ranking is unverified 
  marketing. Test the rule, ignore the branding.
- [ ] OTE (Optimal Trade Entry) = Fib 62-79% 
  trend-pullback entry. Test as a variant within 
  the H4 trend-pullback hunt, not standalone — 
  it's the same family as ema_pullback.
- EXPLICITLY SKIP: Silver Bullet (video admits edge 
  is in an undisclosed filter stack — overfitting 
  risk), and discretionary order-block/FVG patterns 
  that require human judgment to define.

## TIER 4 — REGIME ORCHESTRATION 
(requires ≥2-3 gauntlet-passed edges; v1 portfolio 
REJECTed because the pool was weak, not the switching)
- [ ] Volatility-targeted sizing (position ∝ 1/ATR, 
  constant risk across vol regimes)
- [ ] Correlation/exposure limits (EURUSD+GBPUSD+
  AUDUSD long = one USD bet; hard gate before live).
  LIVE EVIDENCE 2026-07-22: all 3 williams_r USD-pair
  instances (GBPUSD/EURUSD/AUDUSD) went SELL same day,
  all lost together — no longer hypothetical. Report-
  only cluster logging shipped same day
  (correlation_events table, bot/live_signal_loop.py
  _check_correlation_cluster, 3+ distinct pairs same
  direction) to measure frequency before gating.
  Direction is raw per-symbol signal, NOT USD-exposure
  normalized (USDCAD is USD-as-base, opposite polarity
  from the other three) — normalize before any
  blocking logic is built on this data.
- [ ] Regime portfolio v2 (regime-multiplier sizing 
  across the real edge inventory; portfolio itself 
  must pass walk-forward as a unit)
- [ ] AI regime-detector: LLM market-structure read 
  as challenger classifier vs ADX(14) baseline.
  INPUT SPEC: raw recent candle sequence as 
  structured text — [{t,o,h,l,c}] x ~50 candles + 
  session/VIX context. NOT chart images: our candles 
  exist as exact OHLC numbers; rendering to pixels 
  and vision-reading them is a lossy round-trip. 
  Charts are for humans, numbers are for the AI.
  OUTPUT: structure-aware regime label (e.g. 
  RANGE-EXHAUSTION, LATE-TREND, COMPRESSION) — 
  richer than the 3 ADX buckets, specifically 
  targeting ADX's known lag/maturity blindspot 
  (leading hypothesis for the mean-reversion-wins-
  in-TREND anomaly).
  EVALUATION: shadow-logged alongside ADX's bucket 
  on every signal, 100+ outcomes required, promoted 
  to a sizing input only if its labels separate 
  winners/losers better than ADX baseline. 
  NEVER wired to execution.
- [ ] AI strategy-generation front-end (post-Tier-3, 
  requires certified ruler + deflated Sharpe gate 
  in place): LLM generates gauntlet-ready strategy 
  files from two sources, in priority order:
  (a) PRIORITY — hypotheses mined from our own 
  regime-tagged trade ledger ("Version 3"): feed the 
  LLM structured anomalies (per-regime/session WR, 
  entry-context candle sequences around winners vs 
  losers) and have it generate competing testable 
  explanations + strategy/filter variants for each. 
  First work orders queued: (1) the mean-reversion-
  wins-in-TREND regime anomaly, (2) GBPUSD's 
  NEUTRAL-bucket loss concentration, (3) losing-
  entry post-mortem pattern mining.
  (b) SECONDARY — academic/library concepts 
  (Quantpedia etc.) translated to engine format.
  INVARIANTS: AI proposes, gauntlet disposes 
  (walk-forward → stability → permutation → MC → 
  deflated Sharpe), human gates every promotion, 
  auto-deploy never. Expect the standard ~93-98% 
  candidate failure rate — generation raises 
  throughput, not the pass rate.
  EXPLICITLY OUT OF SCOPE: discretionary market-
  analysis agents producing opinions/conviction 
  scores (the "AI hedge fund desk" pattern) — 
  unfalsifiable, philosophically opposed to this 
  system.

## OUTSTANDING — monitoring & housekeeping
- [ ] **`candle_stream` heartbeat is unmonitored.** 
  `scripts/watchdog.py` checks only `signal_loop` 
  staleness. A dead candle stream would page nobody. 
  Needs a market-hours-aware rule (same Sun 22:00 – 
  Fri 21:00 UTC shape the signal_loop check uses); 
  weekend silence is normal and must not alert.
- [ ] `/app/logs/daily_run.log` no longer written 
  (run_daily disabled) — dashboard page 01's cron-status 
  panel now parses a missing file and reads permanently 
  stale. Cosmetic; fix or remove the panel.
- [ ] 51 dangling Docker images on the VPS (2026-08-15). 
  Not pruned. Check before the next rebuild.

## TIER 5 — LIVE RETURN (Branch A only)
**Branch B resolved, so this tier is not reachable on 
the current evidence.** 
One strategy at a time, 2 weeks apart. Sizing from 
the MC ruin table: ~1% of account per trade ≈ 5.6% 
ruin; 2% is proven reckless. Ladder: $100→$200→$500. 
NOTE: the ruin table was computed on a $500 account 
from pre-parity-engine AUDUSD trades. The demo account 
holds $19,542.89, so demo survival tests none of it; 
the percentages must be regenerated post-fix before 
they gate any live sizing. 
Demo runs forever as permanent staging. 
Prerequisites: correlation limits live, dynamic 
min-distance floors (read IG per-instrument minimums 
at session start, replacing hardcoded values).

## DATA SOURCES & TOOLS (filed, build when needed)
- IG-native stream cache → becomes backtest data 
  (~3 months depth): closes the last feed gap; add 
  --source ig_cache to engine
- OANDA demo API: free candle history to 2005, 
  per-request limits (no weekly quota) → deep H4/
  Daily history for Tier 3 hunts. DATA SOURCE ONLY 
  — no execution migration.
- OpenBB: free fundamentals/options/macro → for 
  macro-event protection (XAUUSD prerequisite) and 
  any news-aware regime work
- TradingView/Pine: signal-source-only via webhooks 
  (swiftalgo pattern). Never candles, never 
  backtesting — different price universe than IG.
- Regime-column integrity: 12 of 99 post-07-11 
  trades have NULL regime (tagging gap, cause 
  undiagnosed). The regime column is the AI layer's 
  primary fuel — diagnose the missing code path, 
  fix, and backfill the 12 from stored candle 
  history before Tier 4 work begins.

## PAPER ENGINE REALISM PASS (optional, low priority)
Only if paper screening becomes a bottleneck: 
(a) apply measured slippage to simulated entries, 
(b) verify two-sided spread, (c) pessimistic 
SL-first straddle resolution [highest value — 
current paper WR likely inflated], (d) log would-be 
rejections. Paper's role is cheap conservative 
screening; demo-live is the truth. Current fragiles' 
green dashboard numbers are favorable-window 
artifacts — do NOT re-promote on dashboard P&L.

## STANDING PRINCIPLES
1. Edge inventory is the bottleneck, not regime 
   detection or generation. Build edges first.
2. Full gauntlet before roster entry: walk-forward → 
   stability map → permutation → Monte Carlo → 
   deflated Sharpe. No exceptions.
3. Content-sourced architecture ideas admissible; 
   content-sourced performance claims never.
4. Any analysis of a rostered strategy pulls real 
   params from active_strategy first.
5. Verdicts that move money must be persisted 
   (walkforward_runs) and auditable.
6. Claims about system state get verified against 
   ground truth (git log, deployed files, DB) before 
   actions build on them.
7. Base rate: expect ~93-98% of candidates to fail 
   the gauntlet. That is the method working.
