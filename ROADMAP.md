# TRADING BOT — DEVELOPMENT ROADMAP
Last updated: 2026-07-16
Rule: this file is updated whenever a tier item 
completes or a gate decision resolves.

## HARD GATE (governs everything below)
AUDUSD reconciliation read at 40+ clean post-flip 
demo-live trades certifies whether backtest verdicts 
predict real execution. Until it resolves:
- Exploration (running backtests) is allowed anytime
- Promotion/commitment of ANY new strategy is blocked
Branch A (demo TRACKS backtest): ruler certified → 
Tier 3 hunts proceed with confidence.
Branch B (DIVERGES): diagnose why (execution residue 
vs engine flattery vs overfit residue), fix engine, 
re-certify before hunting.

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

## TIER 2 — THE FORK (running now)
- [ ] AUDUSD reconciliation read (trigger: 40+ clean 
  trades; prompt spec exists in session notes — 
  realized vs backtest WR/expectancy/RR/regime, plus 
  post-flip entry-gap "after" number)
- [ ] July 21: GBPUSD + stoch_rsi FRAGILE review 
  gate (demo performance vs walk-forward profiles)

## TIER 3 — EDGE INVENTORY EXPANSION 
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

## TIER 4 — REGIME ORCHESTRATION 
(requires ≥2-3 gauntlet-passed edges; v1 portfolio 
REJECTed because the pool was weak, not the switching)
- [ ] Volatility-targeted sizing (position ∝ 1/ATR, 
  constant risk across vol regimes)
- [ ] Correlation/exposure limits (EURUSD+GBPUSD+
  AUDUSD long = one USD bet; hard gate before live)
- [ ] Regime portfolio v2 (regime-multiplier sizing 
  across the real edge inventory; portfolio itself 
  must pass walk-forward as a unit)
- [ ] AI regime-detector: LLM market-structure read 
  as challenger classifier vs ADX baseline. 
  Shadow-logged 100+ signals, promoted to sizing 
  input only if it beats baseline. NEVER wired 
  directly to execution. Human-gated ticket pattern 
  if any discretionary overlay is ever built.

## TIER 5 — LIVE RETURN (Branch A only)
One strategy at a time, 2 weeks apart. Sizing from 
the MC ruin table: ~1% of account per trade ≈ 5.6% 
ruin; 2% is proven reckless. Ladder: $100→$200→$500. 
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
