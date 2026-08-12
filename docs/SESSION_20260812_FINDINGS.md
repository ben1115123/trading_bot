# Session Findings — 2026-08-12

Durable record of defects found during a read-only VPS audit and the
subsequent deactivation work. Written as findings, not narrative.

Scope of the session: investigate long-running wide-SL/TP positions →
state-of-system handoff → deactivation of two live strategies. The
deactivation work is tracked separately; this file records what the
investigation surfaced.

**Nothing in this file is fixed.** Each finding states what it invalidates
and what fixing it requires. Sequencing is at the end.

---

## 1. Engine parity — the backtest models a different strategy than live runs

**Broken:** `backend/backtesting/engine.py` applies **no take-profit** for
`williams_r`, and sizes at `$15` risk while live sizes at `$10`.

**Evidence:**

- `engine.py:291` — `"tp_price": sig.get("tp_price")`. The engine only
  applies a TP if the strategy's signal dict carries one.
- `backend/strategies/williams_r.py` — `generate_signals` emits
  `{"index": i, "signal": "BUY"|"SELL"|"NONE"}`. It **never sets
  `tp_price`**, so `tp_price` is always `None` and the TP branch at
  `engine.py:185-212` is dead code for this strategy.
- Confirmed empirically: re-running the engine over 2026-07-24 → 08-13
  with the rostered params produced **403 trades, exit reasons
  `{signal: 148, sl_stop: 255}` — zero `tp_hit`**.
- `engine.py:30` — `RISK_PER_TRADE = 15.0  # USD, matches live bot`.
  **The comment is false.** `risk_manager.py` uses `RISK_PER_TRADE = 10`.
- `engine.py:232` — every SL exit books a flat `-RISK_PER_TRADE -
  spread_cost` = `-$15.75`, not a modelled fill.

**Live behaviour it fails to model:** 59 of 197 post-cap live closes (30%)
exited at TP, contributing **100% of live gross wins ($1,159.18)**. The
engine cannot represent the mechanism that generates every winning live
trade.

Secondary divergence in the opposite direction: the engine closes on an
opposing signal (`engine.py:241-257`, `exit_reason: "signal"`, 148 of 403
trades). Live has no reversal exit — `bot/live_signal_loop.py`'s only close
path is `_weekend_close_positions()`, filtered to `["SPTRD", "NASDAQ",
"DAX"]` epics (line 176), so FX exits on SL/TP only. Measured cost of the
missing reversal exit over 46 affected live trades: **+$26.76** — a near
wash, and *not* the main divergence.

**Invalidates:** every `backtest_results` row (268,117 on VPS, 5,329
local), every score derived from them, and every promotion decision that
used them — see finding 2 of Part 2 for the count.

**Fixing requires:** decide whether TP is the strategy's responsibility
(emit `tp_price`) or the engine's (apply a default R multiple); correct
`RISK_PER_TRADE` to 10.0 and delete the false comment; then regenerate all
affected evidence under an `engine_version` marker (see finding 11).

---

## 2. Paper resolver — a second synthetic model, inconsistent with the first

**Broken:** the paper P&L model deducts no spread, applies no `ig_scale`
conversion, and clamps an implausible `sl_distance` instead of rejecting it.

**Evidence:** `bot/live_signal_loop.py`, `_resolve_pending_paper_trades()`
(defined line 731):

```python
# 763-774 — outcome + raw price distance, no spread term
if candle["low"]  <= sl:  outcome, raw_pnl = "LOSS", sl - entry   # BUY
if candle["high"] >= tp:  outcome, raw_pnl = "WIN",  tp - entry   # BUY

# 780-789 — sizing and P&L
sl_distance = abs(entry - sl)
lot_size = get_risk_per_trade(symbol, is_paper=True) / (sl_distance * value_per_point)
lot_size = max(0.1, min(10.0, lot_size))          # clamps, never validates
simulated_pnl = raw_pnl * lot_size * value_per_point
```

Because `lot_size = risk / (sl_dist × vpp)`, a loss resolves algebraically
to exactly `−risk` and a win to `(tp_dist/sl_dist) × risk`. The output is
the SL/TP rule replayed against candles — not a fill model. It also assumes
fills exactly at SL/TP with zero slippage and books TP on any wick that
grazes the level.

**The two synthetic models are mirror images of each other, and neither
matches live:**

| | Backtest engine | Paper resolver | Live |
|---|---|---|---|
| Take-profit | **absent** (williams_r) | applied | applied |
| Reversal exit | applied | **absent** | **absent** |
| Spread | `SPREAD_COSTS` subtracted | **none** | real |
| Risk size | **$15** | $10 | $10 |
| Loss booking | flat `−RISK − spread` | `raw_pnl × lot × vpp` | broker fill |
| Scale conversion | n/a (cache data) | **missing** — see finding 3 | via `ig_scale` |
| Sizing guard | clamp `[0.1, 10.0]` | clamp `[0.1, 10.0]`, no sanity check | clamp, no sanity check |

**Invalidates:** the criterion "PF ≥ 1.3 **after estimated spread**" has
never been applied to anything. Every paper PF, expectancy and Sharpe figure
is pre-spread.

Measured effect of deducting static `NORMAL_SPREADS`: roughly **$0.30–$1.50
per trade**, decisive against a `> $2.00` expectancy threshold. It
eliminates one of the two strategies that currently pass promotion criteria
(`EURUSD ny_session_momentum`, expectancy $0.41 → negative).

**Fixing requires:** this is a **sibling to finding 1, not a subtask.** Two
independent synthetic models feed promotion decisions; fixing one leaves the
other. Minimum scope: deduct spread (static `NORMAL_SPREADS` first,
captured-at-signal-time properly); route paper prices through
`ig_scale.to_decimal()`; add an `sl_distance` sanity bound that rejects
rather than clamps; exclude or re-baseline mixed-risk-size history.

Related: `trades.spread` is NULL on every live position inspected — the live
path does not populate it either. Signal-time capture fixes both.

---

## 3. `paper_trades` id=824 — one scale-corrupted row, −$2,500

**Broken:** a native points-scale price reached `paper_trades` unconverted
and, via the lot-floor clamp, produced a −$2,500 simulated loss.

**Evidence:**

```
id=824  2026-07-21T19:35:31  EURUSD bb_squeeze  PAPER_BUY
entry=11403.2  sl=11400.7  tp=11408.2  simulated_pnl=-2500.00
```

Those are native points-scale prices — the documented
`CS.D.EURUSD.MINI.IP` quirk on DEMO account Z67Y2C, where EURUSD quotes as
`11403.2` rather than `1.14032`. Every other bb_squeeze row is decimal
(`1.15553`, `1.16077`, …).

Arithmetic: `sl_distance = |11403.2 − 11400.7| = 2.5`, treated as a decimal
price distance → `lot_size = 15 / (2.5 × 10000) = 0.0006`, **clamped up to
the 0.1 minimum** → `pnl = −2.5 × 0.1 × 10000 = −$2,500.00`.

**Invalidates:** every summary quoting EURUSD bb_squeeze at
**−$2,453.93 over 32 trades**, including this repo's CLAUDE.md and the
promotion-criteria table produced earlier this session.

**Corrected figures — excluding id=824, the other 31 trades sum to
`+$46.07`**, expectancy `−$76.69` → `+$1.49`. The strategy's paper record is
mildly positive, not catastrophic. It still fails promotion criteria on PF
and expectancy; the point is that the headline number was one bad row
misrepresenting 31 clean ones.

**Two structural problems this exposes:**

1. The paper-trade path has **no `ig_scale` conversion**. CLAUDE.md lists
   the boundary conversion sites as `execute_trade.py`,
   `positions_poller.py`, `candle_stream.py`, `sync_ig_trades.py`. The paper
   logging path is not among them.
2. The lot-floor breach is **no longer theoretical**. The same
   `max(0.1, ...)` clamp exists on the live path, where SL > 100 pips would
   silently push actual risk above the intended $10. id=824 is that
   mechanism, already fired, in paper.

**Fixing requires:** quarantine id=824 (do not delete — it is the evidence);
re-baseline every dependent summary; the conversion and sanity-bound work in
finding 2.

---

## 4. `status` default — a silent paper→live promotion bypass

**Broken:** cron can promote a `paper` strategy to `active` with no gate,
because the status default is fail-open at three independent layers.

**Evidence:**

| Layer | Location | Behaviour |
|---|---|---|
| Caller | `scripts/select_strategy.py:217` (`_select_for_symbol`) | omits `status` from the payload |
| Caller | `scripts/select_strategy.py:250` (`seed_initial_strategy`) | spreads `**seed`; no `SEED_STRATEGIES` entry contains `status` |
| Helper | `database/models.py:367-368` | `if 'status' not in data: data['status'] = 'active'` |
| Schema | `database/db.py` DDL (both migration blocks) | `status TEXT DEFAULT 'active'` |

Amplified by the upsert in `models.py`:

```sql
ON CONFLICT(symbol, timeframe, strategy_name) DO UPDATE SET
    ...
    status = excluded.status,
```

`excluded.status` is unconditional — an existing `paper` row is overwritten
by the defaulted incoming value.

**100% of runtime callers inherit the default.** There are exactly two, both
in `select_strategy.py`, and neither passes `status`. No other code writes
`active_strategy` (`db.py`'s two INSERTs are one-shot schema migrations that
carry `status` through verbatim; all five dashboard pages are read-only).

**Has it fired? No — audited all 40 `active_strategy_history` rows, zero
paper→active transitions by cron.** It has not fired for a structural reason,
not a safe one: cron writes only `US500`/`US100`/`BTC` at `HOUR`
(`_select_for_symbol` filters `timeframe == "HOUR"`), and the only paper rows
ever in those slots — `stoch_rsi_confluence US500 HOUR` (id 26) and
`williams_r US500 HOUR` (id 6) — never out-scored the incumbent by the
required `+0.05`. **The paper pipeline was protected by a scoring threshold,
not by design.**

**Invalidates:** the assumption that paper status is a safety boundary. It is
advisory.

**Fixing requires:** make `status` a required parameter that raises when
absent (no legitimate caller breaks — there is no correct caller today);
change the `ON CONFLICT` clause to never auto-promote `paper` → `active`;
change the DDL default to `'paper'`. All three layers, or it leaks.

---

## 5. First-activation branch has no score threshold

**Broken:** when a symbol has no active row for a timeframe,
`_select_for_symbol` promotes the top-scoring candidate **unconditionally**.

**Evidence:** `scripts/select_strategy.py`:

```python
current = get_active_strategy(symbol=symbol, timeframe="HOUR")
if current is None:
    reason = f"No active strategy for {symbol} — first activation"
```

`get_active_strategy` filters `status='active'`. The `+0.05` improvement
guard applies only in the `else` branch, when an incumbent exists.

**This is the mechanism that put `US100 HOUR supertrend` live.** On
2026-06-12 06:15:31 every US100 HOUR row was set `inactive` (ids 1, 12, 15,
21, 27 share that timestamp). Four days later, 2026-06-16 06:02:28, cron
found `current is None`, took the unconditional branch, and activated
`supertrend` — `active_strategy_history` id 33, reason `"No active strategy
for US100 — first activation"`. It was never a paper row; it went
**nonexistent → live**, with zero paper trades and zero human review, and
remained undocumented in CLAUDE.md for ~8 weeks.

**Operational consequence recorded for the deactivation work:** setting a
symbol's only active HOUR row to `inactive` **recreates this precondition**.
Deactivating `US500 stoch_rsi` (id 2) and `US100 supertrend` (id 33) without
first disabling the selector would arm exactly this branch on both symbols,
with the US500 candidate pool containing two paper rows.

**Fixing requires:** apply a threshold (or an explicit human gate) to first
activation, not only to switches. Subsumed if cron is restricted to writing
`'paper'` only.

---

## 6. `STRATEGY_BLOCKLIST` is an allowlist by omission

**Broken:** the blocklist enumerates `(symbol, timeframe, strategy_name)`
tuples. Any strategy name not enumerated is permitted, so the guarantee is
"these specific names are blocked," not "this symbol is blocked."

**Evidence:** CLAUDE.md states all US100 strategies have been blocklisted
since 2026-06-12. `("US100", "HOUR", "supertrend")` is **not in the set** —
which is why finding 5's promotion succeeded four days later. The US100
entries cover `stoch_rsi, rsi, williams_r, macd_rsi, rsi_divergence,
swiftalgo, smc, ema_pullback, ny_session_momentum, silver_bullet,
london_breakout, rsi_divergence_session` — supertrend was simply never
listed.

**A symbol-wide mechanism already existed and was not being used:**

```python
# scripts/select_strategy.py, ~line 155
# Symbols blocked entirely — cron will not promote any strategy
SYMBOL_BLOCKLIST = {"BTC"}
```

Enforced in `select_strategy()` at the symbol loop, before
`_select_for_symbol` is called. Adding `"US100"` makes CLAUDE.md's existing
claim true; it was a one-token gap.

**Also latent:** 10 of the 22 US100 tuples are **unreachable code** —
`_select_for_symbol` filters candidates to `timeframe == "HOUR"` before the
blocklist check, so every 15MIN and 5MIN tuple has never been evaluated. The
blocklist reads as broader coverage than it has ever provided.

**Remaining exposure on US500** after adding `("US500","HOUR","stoch_rsi")`:
five sweepable strategy names remain unblocked at US500 HOUR —
`williams_r`, `stoch_rsi_confluence`, `ema_pullback`, `fvg`, `smc` — two of
which are current paper rows subject to finding 4.

---

## 7. `walkforward_runs` — the evidence base is largely absent

**Broken:** the walk-forward verdicts cited as promotion justification have
no persisted record on the trading machine, and the most-cited one has no
persisted record anywhere.

**Evidence:**

| | VPS | Local (`database/trades.db`, last written 2026-07-22) |
|---|---|---|
| `walkforward_runs` rows | **0** | 276 |

Local breakdown: `stability_map` 204, `walk_forward` 36, `monte_carlo` 35,
`permutation` 1.

**All 36 `walk_forward` rows are `first_bar_breakout` (US100/US500). There
are zero `walk_forward` rows for `williams_r` on any symbol.**

| CLAUDE.md claim (AUDUSD williams_r) | Status |
|---|---|
| walk-forward ROBUST, median PF 1.285 | **Data** — but stored inside the *permutation* row's `extra_json` (`real_median_pf: 1.285`, `real_verdict: "ROBUST"`) |
| 83.3% windows profitable, 6 windows | **Prose only.** No `walk_forward` row ⇒ no `windows_json` ⇒ the per-window breakdown is unrecoverable |
| stability plateau, 23 contiguous cells at PF ≥ 1.1 | **Data** — 84 cells, 25 at median_pf ≥ 1.1. See finding 8 for what the phrasing omits |
| permutation 96th percentile | **Data** — 200 `synthetic_median_pfs` stored; percentile recomputable |
| Monte Carlo p5=$707 → p95=$2621 | **Data, exact match** (`pnl_p5: 706.99`, `pnl_p95: 2621.07`, `account: 500.0`, `risk_per_trade: 10.0`, `n_trades: 1227`) |

Provenance is recorded: `cache_file=AUDUSD_15MIN_AV.json`, 29,995 candles,
2025-06-19 → 2026-06-29.

**Root cause:** `walkforward_runs` was created 2026-07-22. The AUDUSD
promotion was 2026-07-15 — the justifying run predates the table.

**The finding is the recurrence, not the absence.** CLAUDE.md already
documents this exact gap for EURUSD williams_r — *"root cause irreproducible
because walk-forward runs were never persisted (no DB row, no saved
output)."* That was written as a one-off explaining a single discrepancy.
**The same defect silently applied to AUDUSD**, the Phase-3 lead candidate,
whose ROBUST verdict is the single most-cited piece of promotion evidence in
the file — and went unnoticed for four weeks. One unpersisted run is an
incident; two, including the flagship, is a missing practice.

**Invalidates:** any claim that re-running the gauntlet on a corrected engine
would *reproduce* or *contradict* a prior result. For walk-forward it is
**regeneration, not reproduction** — there is no artifact to diff against.
Stability map, permutation and Monte Carlo *can* be compared, since those
rows exist locally.

**Do not copy the local rows to the VPS.** They were produced by the
pre-parity engine; relocating them puts invalid evidence where the selector
and dashboards can reach it. If they move at all, it should be after the
parity fix, marked `pre-parity-v0`, explicitly as an archive.

Local DB backed up 2026-08-12 to `database/trades.bak-20260812T173249Z.db`
(276/276 `walkforward_runs` rows, `integrity_check ok`) — it was the sole
copy.

---

## 8. Stability map — the "plateau" is one robust cell

**Broken:** CLAUDE.md's phrasing describes a PF contour as a plateau of
robust configurations.

**Evidence:** the 84 AUDUSD `stability_map` rows carry verdicts:

| Verdict | Cells |
|---|---|
| FRAGILE | 38 |
| MARGINAL | 34 |
| REJECT | 11 |
| **ROBUST** | **1** |

25 cells clear median_pf ≥ 1.1 (max 1.285), so "23 contiguous cells at
PF ≥ 1.1" is substantively correct as a contour. But exactly **one cell in
the entire map earns a ROBUST verdict.**

**Invalidates:** the inference a reader draws from "stability-map plateau (23
contiguous cells, not a spike)" — that the strategy sits in a broad robust
region. It sits at a single robust point inside a mostly-fragile field.

---

## 9. Unverified controls — the recurring failure class

**The class:** *a control believed to be in place that was never empirically
confirmed.* Four instances surfaced in one session.

1. **`service cron reload` is a no-op.** `/etc/init.d/cron` maps
   `reload|force-reload` to `log_daemon_msg` + `log_end_msg 0`, with the
   comment `# cron reloads automatically`. **It signals nothing and returns
   success.** Had it been used as the remedy it would have reported clean and
   changed nothing.
2. **`collect_candles` cron recorded as disabled 2026-06-28** — demonstrably
   still firing every 15 minutes ~7 weeks later. Most likely an in-container
   edit lost to a subsequent rebuild, i.e. instance 3 realised historically.
3. **In-container cron edits do not survive a rebuild.** `/etc/cron.d/trading-bot`
   is baked from `scripts/crontab` at build time (`Dockerfile:18`). Editing
   the container file works until the next `up -d --build`, which silently
   restores the original.
4. **A probe that invalidates its own precondition returns a false negative.**
   A background check sampling a sentinel file 32 seconds after the cleanup
   step deleted it reported `MARKER_ABSENT` for an event that had demonstrably
   occurred.

**General remedy — the marker test.** When disabling something, prove the
disable took effect with a **positive signal**. Do not infer it from absence
of activity: absence is consistent with both "disabled" and "would have fired
but didn't happen to." Construct a probe that differs between the two states —
a temporary artifact only the new configuration can produce — observe it, then
remove it.

Applied 2026-08-12 to verify a cron disable: a one-shot cron line writing a
timestamped sentinel, scheduled 5 minutes out, `%` escaped as `\%` (unescaped
`%` is a newline separator in crontab), with ≥2 minutes of lead for cron's
per-minute mtime poll. It fired at 17:11:01 — **that**, not the silence of the
disabled job, established the disable.

**Corollary 1:** a test whose positive and negative branches produce the same
observation proves nothing. The first proposed check here — watch the `*/15`
collector fire — was discarded because that line is identical in the old and
new tables, so it fires either way.

**Corollary 2:** a probe must be invalidated when its artifact is cleaned up,
or its result read against the cleanup timestamp.

---

## 10. `logs/` and `scripts/candle_cache/` are not volumes

**Broken:** code writes results to container-local paths that are destroyed on
every rebuild.

**Evidence:** `docker-compose.yml` mounts exactly one volume for the bot and
dashboard services:

```yaml
volumes:
  - ./database:/app/database
```

`/app/logs/` and `/app/scripts/candle_cache/` are container-local.

**Affected:** `logs/daily_run.log` (present in container, absent on host —
the dashboard's cron-status panel parses it), `logs/candles.log` (5,419 lines
of collector history), `scripts/candle_cache/*_15MIN_IG.json` (~398 candles ×
3 symbols). All destroyed by `docker-compose up -d --build`.

This partly explains why `collect_candles` coverage is thin: it re-accumulates
from scratch after each deploy. Data span 2026-07-28 → 08-13 holds ~399
candles per symbol where contiguous 15MIN collection would hold ~1,530
(≈26% capture, consistent with an observed 86% run-level failure rate against
`error.public-api.exceeded-account-historical-data-allowance`).

Host-side paths (`logs/watchdog.log`, `logs/watchdog_alerts.jsonl`) are
written by host cron and **do** persist — this is why the watchdog was
deliberately placed on the host.

**Invalidates:** any assumption that a log-derived figure can be re-checked
later on the machine.

---

## 11. Local and VPS `backtest_results` are different corpora

**Broken:** the two databases are not stale copies of one dataset; they are
independent datasets that have never been reconciled.

**Evidence:**

| Table | Local | VPS |
|---|---|---|
| `backtest_results` | 5,329 | **268,117** |
| `backtest_trades` | 267,571 | 2,608,572 |
| `walkforward_runs` | 276 | **0** |
| `trades` | 5 | 950+ |
| `paper_trades` | 0 | populated |
| `signal_log` | 0 | 75,900 |

VPS `backtest_results` spans 2026-04-27 → 2026-08-12 and is fed by the
`run_daily.py` cron. Local is a research database fed by manual sweeps.

**Invalidates:** any cross-comparison between local and VPS backtest figures
made to date. CLAUDE.md notes the divergence ("VPS backtest_results table
diverges from local — local sweep results exist in local trades.db only"), but
the scale is larger than that phrasing suggests: **the entire walk-forward
evidence base for the live roster does not exist on the trading machine at
all.**

Also affected: `active_strategy.backtest_id` is only meaningful against the
database it was written in. Rows promoted by VPS cron point at VPS
`backtest_results` ids; rows promoted manually from local analysis may point
at local ids or be `NULL`.

---

## Sequencing

| Work | Depends on | Notes |
|---|---|---|
| `status` default fix (3 layers) | — | Independent; do first |
| Cron writes `'paper'` only | status fix | Subsumes finding 5 |
| Engine parity (finding 1) | — | Regenerates all evidence |
| Paper resolver (finding 2) | — | **Sibling to engine parity, not a subtask** |
| `engine_version` marking | engine parity | See below |
| Quarantine id=824, re-baseline | finding 2 | Includes correcting CLAUDE.md |
| Gauntlet regeneration | engine parity + marking | Regeneration, not reproduction |
| `logs/` + `candle_cache/` volumes | — | Fold in with the `collect_candles` decision |

**`engine_version` marking scheme** (agreed, not yet implemented): a
`NOT NULL DEFAULT 'pre-parity-v0'` column on `backtest_results`; semantic
versions, not commit SHAs — bump only when the trade model changes;
`get_backtest_results()` filters to the current version by default;
`score_strategies()` **raises** rather than ranks if it sees a mixed set;
`active_strategy.score` nulled or flagged at the boundary, since a stale
pre-parity score gates the `+0.05` switch threshold.

**Promotion criteria enforcement** (agreed): advisory report for one full
cycle, then hybrid — hard gate on numeric criteria, advisory on correlation
and judgement calls. Overrides must be impossible to make silently and must
record `engine_version` alongside the metric snapshot. Rationale: applied as
literally written today, the criteria pass `US500 ema_pullback` on 58 trades
containing two different risk sizes ($10 and $15) and an unadjusted
pre-spread PF — false authority is worse than no gate.

---

## Appendix — AUDUSD hard gate resolution (draft)

Drafted for ROADMAP.md; not yet applied. Both amendments incorporated.

> ### HARD GATE — RESOLVED 2026-08-12: Branch B (DIVERGES)
>
> **Gate condition met.** Required 40+ clean single-position post-cap
> demo-live AUDUSD trades. Delivered: **51 post-cap trades, 50 closed**,
> verified clean by interval-overlap scan — zero overlapping `[entry, close]`
> pairs on AUDUSD, and zero on EURUSD/GBPUSD/USDCAD. The concurrent-position
> cap (`risk/concurrent_positions.py`, deployed 2026-07-24 21:13:48 UTC) held
> without exception.
>
> **Result vs promotion basis.**
>
> | | Promotion basis | Live demo actual |
> |---|---|---|
> | Profit factor | median **1.285** | **0.71** |
> | Windows profitable | 83.3% | — |
> | Win rate | — | 26.0% |
> | Net | — | **−$109.07** |
> | Expectancy | — | **−$2.18/trade** |
>
> AUDUSD was the only roster strategy to clear the full ROBUST gauntlet. It is
> the **worst live performer of the four williams_r instances**. Across all
> four the backtest-to-live ranking inverts: predicted AUDUSD > EURUSD >
> GBPUSD > USDCAD; observed USDCAD ≈ EURUSD > GBPUSD > AUDUSD.
>
> **Diagnosis: ENGINE FLATTERY.** The backtest models a different strategy
> from the one running live — no take-profit for `williams_r`
> (`engine.py:291` reads `tp_price`, `WilliamsRStrategy` never emits it; zero
> `tp_hit` across 403 trades), while live took profit on 30% of exits and
> **100% of live gross wins came through TP**. Plus `RISK_PER_TRADE = 15.0`
> against live `$10`. See SESSION_20260812_FINDINGS.md finding 1.
>
> **Execution residue is ruled out.** Concurrent cap holding (zero overlaps,
> all four symbols); poller clean (4/4 tracked, ~30s cadence, DB matching IG
> deal-for-deal); stops attached broker-side on every open position
> (`stopLevel`/`limitLevel` present, `controlledRisk: false`); sizing
> arithmetically correct (every live trade prices to ≈$10). Execution did what
> it was told; the instruction was wrong.
>
> **The stability-map claim in CLAUDE.md overstates what the data shows.**
> "23 contiguous cells at PF ≥ 1.1" is a **profit-factor contour, not a
> plateau of robust configurations.** Of the 84 recorded cells:
> **FRAGILE 38, MARGINAL 34, REJECT 11, ROBUST 1.** Twenty-five clear
> PF ≥ 1.1, so the contour is real — but exactly one cell in the map earns a
> ROBUST verdict.
>
> **No comparison baseline exists.** There is **no `walk_forward` row for
> `williams_r` on any symbol**, VPS or local. The "83.3% of 6 windows"
> figure survives only as prose. `walkforward_runs` was created 2026-07-22,
> one week after the 2026-07-15 promotion, so the justifying run was never
> persisted. What exists locally: the headline verdict (stored inside the
> permutation row's `extra_json`), the 84-cell stability map, a 200-iteration
> permutation test, and 25 Monte Carlo rows including the Phase-5 ruin sweep.
>
> **The finding is the recurrence, not the absence.** CLAUDE.md already
> documents this gap for EURUSD williams_r. The same defect silently applied
> to AUDUSD, the flagship, and went unnoticed for four weeks. Verdicts must be
> written to `walkforward_runs` when produced, or they are not evidence.
>
> **Overfit residue is NOT ruled out.** The engine defect is sufficient to
> explain a large divergence but does not establish that these parameters
> would generalise on a correct engine. The stability map and permutation
> result were computed by the same flawed engine and inherit the same defect —
> they establish robustness *within a model that cannot take profit*.
>
> Re-running the gauntlet on the corrected engine is therefore
> **regeneration, not reproduction**: for walk-forward there is no prior
> artifact to diff against. Stability map, permutation and Monte Carlo permit
> a genuine before/after comparison, provided the old rows are marked
> `pre-parity-v0` and never mixed with post-fix results.
>
> **What the gate blocks until then:** promotion or commitment of any new
> strategy (Branch B); Tier 3 hunts do not open; exploration remains allowed
> but no result from the current engine constitutes promotion evidence.
> Re-certification requires the engine parity fix, the paper-resolver sibling
> fix, a full gauntlet regeneration, and fresh comparison against live demo
> data collected under the corrected model.
