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

**Fixing requires — scope decided 2026-08-12: fix the ENGINE CONTRACT, not
the strategies.** This is not a `williams_r` bug; 21 of 34 strategies omit
the same contract (finding 12). Two halves, **both required**:

1. **A default TP rule when a strategy supplies none** — an R-multiple. The
   multiple itself must be **decided against observed live behaviour, not
   guessed**.
2. **A hard failure when neither `sl_price` nor `tp_price` is present and no
   default applies.** The silent `sig.get("tp_price")` returning `None` is
   the actual defect. **A default alone makes the silence quieter rather
   than fixing it** — the next strategy to omit the contract would still run
   without anyone being told.

Also required: correct `RISK_PER_TRADE` to 10.0 and delete the false
comment; **audit the 13 emitting strategies' existing TP rules against live
behaviour** — emitting something is not evidence of emitting the right
thing, and those rules have never been checked; then regenerate all affected
evidence under an `engine_version` marker (see finding 11).

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
2. **The clamp masks implausible `sl_distance` instead of rejecting it.**
   See the correction and the full clamp survey immediately below.

### Correction (2026-08-12) — the lot-floor breach has fired in PAPER only

An earlier characterisation in this session called the lot-floor breach
"no longer theoretical." That overstates it. Corrected:

| Table | Rows scanned | Out-of-band prices | MAX clamp (lot>10, SL<1 pip) | MIN clamp (lot<0.1, SL>100 pips) |
|---|---|---|---|---|
| `paper_trades` | 1,447 | **1** (id=824) | **5** | **1** (id=824) |
| `trades` (live) | 894 | **0** | **0** | **0** |

**The live ledger is clean.** Zero scale-corrupted prices and zero clamp hits
in either direction across 894 rows. **Live lot-floor risk remains
theoretical.** The breach is real in paper, across 6 rows total.

id=824 is also **unique**, not the largest of many — it is the only
out-of-band price in either table.

### The second distortion class — MAX-clamp under-risking (5 paper rows)

Found by the same survey, opposite direction to id=824:

```
id=133  EURUSD  sl=0.88 pips  lot=11.33 -> clamped 10  pnl=-8.83
id=218  EURUSD  sl=0.89 pips  lot=11.21 -> clamped 10  pnl=-8.92
id=253  EURUSD  sl=0.40 pips  lot=24.92 -> clamped 10  pnl=-4.01
id=334  EURUSD  sl=0.20 pips  lot=48.92 -> clamped 10  pnl=+2.04
id=335  EURUSD  sl=0.20 pips  lot=48.92 -> clamped 10  pnl=+2.04
```

Sub-pip stops compute lot sizes of 11–49, clamped down to the 10.0 maximum.
These trades are **under-risked**: they book ±$2–9 where the model intended
±$10 / ±$20.

**This contaminates a promotion criterion.** Compressing the P&L
distribution reduces variance while leaving the mean roughly intact, which
**inflates Sharpe** — and `Sharpe >= 0.08` is one of the four R:R-adjusted
promotion criteria. The criterion is measured on data the clamp has
artificially smoothed.

**Consequence for the fix:** the `sl_distance` sanity bound must **reject at
both ends**, not just the floor. A sub-pip stop is as implausible as a
2.5-price-unit one, and clamping either is how both distortions got into the
record silently.

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

### Related hazard — the image contains frozen copies of host logs

`Dockerfile:11` is `COPY . .`, so the build-time contents of `logs/` are
baked into the image. The container therefore holds files with the **same
names and formats** as the live host logs, frozen at build time:

| File | Container copy | Host (live) |
|---|---|---|
| `watchdog.log` | 664,804 bytes, frozen **Jul 24 21:10** | 1,407,383 bytes, **Aug 12 17:30** |
| `daily_summary.log` | 5,615 bytes, **Jul 23** | 12,795 bytes, **Aug 11** |
| `watchdog_alerts.jsonl` | 668 bytes, Jul 20 | 668 bytes, Jul 20 |

**Reading `/app/logs/watchdog.log` inside the container returns data ~3
weeks stale that looks live.** This is the unverified-controls class
(finding 9) in a new place: a source that appears authoritative and is not.

**Corollary — `database/` is baked too.** `COPY . .` also copies the
build-time `database/` directory (including `trades.db` and any `trades.bak-*`
files) into the image, where it is hidden at runtime by the
`./database:/app/database` volume mount. Two consequences: image bloat, and —
**if the volume mount ever failed or were misconfigured, the container would
silently run against a build-time database snapshot** rather than failing.

Mitigation to consider: a `.dockerignore` excluding `logs/` and `database/`.

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

## 12. 21 of 34 strategies omit the `sl_price`/`tp_price` contract

**Broken:** the engine reads `sig.get("tp_price")` and silently accepts
`None`. Most strategies never set it. There is no error — the strategy just
runs with no take-profit.

**This is the scope-defining finding for the engine fix.** It establishes
that finding 1 is a contract violation across the codebase, not a
`williams_r` bug.

**21 emit neither `sl_price` nor `tp_price`:**

`bb_squeeze`, `connors_rsi2`, `donchian_breakout`, `ema_cross_volume`,
`ema_ribbon`, `fvg`, `ichimoku`, `keltner`, `macd_crossover`, `macd_rsi`,
`orb`, `rsi`, `rsi_divergence`, `rsi_mean_reversion`, `smc`, `stoch_rsi`,
`stoch_rsi_confluence`, `supertrend`, `vwap_ema`, `vwap_mean_reversion`,
**`williams_r`**

**13 emit both:**

`ema_pullback`, `ema_ribbon_pullback`, `engulfing_candle`, `hull_momentum`,
`inside_bar_breakout`, `kama_crossover`, `london_breakout`,
`market_structure_break`, `ny_session_momentum`, `regime_adaptive`,
`rsi_divergence_session`, `silver_bullet`, `supertrend_ema_filter`

**Evidence** (verified as real emission, not comment matches):

```python
# ema_pullback.py:72 — emitter, initialises the keys up front
signals = [{"index": i, "signal": "NONE", "sl_price": None, "tp_price": None} for i in range(n)]
# ema_pullback.py:149-150
"sl_price": round(sl_price, 6),
"tp_price": round(tp_price, 6),

# stoch_rsi.py:46-57 — non-emitter
signals.append({"index": i, "signal": "BUY"})
# supertrend.py:50-56 — non-emitter, identical shape
```

**Two generations.** The 21 non-emitters are essentially the original
strategy set, written before the `sl_price`/`tp_price` signal-dict contract
existed. The 13 emitters were written against it. Nothing enforces the
contract, so the split is invisible at runtime.

**Fixing requires:** the engine-contract fix scoped in finding 1 — default
plus hard failure. Fixing 21 strategies individually would work once and
invite the same omission on strategy 35.

---

## 13. The live roster's backtest provenance

**Broken:** most live rows have no recorded backtest provenance, and every
row that has some used a non-emitting strategy.

**Evidence** — all 8 live `active_strategy` rows:

| id | Symbol | TF | Strategy | backtest_id | Row exists | Emits tp_price? |
|---|---|---|---|---|---|---|
| 33 | US100 | HOUR | supertrend | 73401 | YES | **No** |
| 2 | US500 | HOUR | stoch_rsi | 1705 | YES | **No** |
| 34 | AUDUSD | 15MIN | williams_r | **NULL** | — | **No** |
| 22 | EURUSD | 15MIN | williams_r | **NULL** | — | **No** |
| 32 | GBPUSD | 15MIN | williams_r | **NULL** | — | **No** |
| 36 | USDCAD | 15MIN | williams_r | **NULL** | — | **No** |
| 11 | EURUSD | HOUR | swiftalgo | NULL | — | n/a (webhook, never backtested) |
| 13 | US500 | HOUR | swiftalgo | NULL | — | n/a |

**Only 2 of 8 live rows carry a `backtest_id`, and both use non-emitting
strategies — so 100% of backtest-derived live promotions rest on evidence
the engine could not have modelled correctly.**

**The other 6 have `backtest_id = NULL`**, meaning the **four `williams_r` FX
instances — the three highest-exposure ones among them — have no backtest
provenance recorded at all.** Their justification exists only as CLAUDE.md
prose plus the local `walkforward_runs` rows, which per finding 7 contain
zero `walk_forward` rows for `williams_r`.

**Across all 31 roster rows:** 17 (55%) have `backtest_id = NULL`; the 14
that carry one all resolve to rows that still exist (no dangling
references); **26 of 31 use a strategy that omits `tp_price`** (only 4
`ema_pullback` rows and 1 `ny_session_momentum` row use emitters; the 2
swiftalgo rows are webhook-driven and never backtested).

**Invalidates:** the premise that the roster is backed by reproducible
backtest evidence. For the williams_r FX instances there is no stored
evidence to re-examine at all.

---

## 14. `MIN_SL_DIST` — an uncalibrated table that now drives sizing
*(added 2026-08-16 during the engine parity work — recorded, NOT fixed)*

**Broken:** `MIN_SL_DIST` (was `_MIN_SL_DIST` in `bot/live_signal_loop.py`,
moved to `instrument_limits.py` at parity-v1) is a hand-set table with **no
recorded provenance** — no measurement, no date, no source, no sample size.
Nobody knows where the numbers came from or when they were last true.

**Why it matters now more than it did:** until 2026-08-16 the table existed
only on the live path. The parity work imported it into the backtest engine,
where it **materially drives sizing**: the floor binds on **45-55% of
williams_r FX signal entries** (AUDUSD 55.2%, USDCAD 52.2%, EURUSD 47.7%,
GBPUSD 44.9%), and on 95-100% of index candles. On a floored trade the floor —
not the strategy, not the market — sets the stop distance, and therefore sets
the position size and the entire P&L of that trade.

**Evidence it is unverified:** the values are suspiciously round
(0.00050 for EURUSD/AUDUSD/USDCAD/EURGBP, 0.00060 for GBPUSD, exactly 3.0/4.0/
5.0 for US500/US100/DAX). The stated rationale is IG's per-instrument minimum
stop distance, but **that minimum has never been read back from IG** —
`fetch_market_by_epic` exposes `minNormalStopOrLimitDistance` per epic and
nothing in the codebase consults it. ROADMAP Tier 5 already lists "dynamic
min-distance floors (read IG per-instrument minimums at session start,
replacing hardcoded values)" as a prerequisite, which concedes the point.

**Same failure class as spread (finding 15 below / commit 4 work), discovered
second.** Both are model *parameters* rather than model *structure*:
`engine_version` versions the structure and says nothing about the numbers the
structure is parameterised by. A future reader cannot tell, from a
`backtest_results` row, which `MIN_SL_DIST` values produced it.

**Fixing requires:** read `minNormalStopOrLimitDistance` per epic at session
start and reconcile against the hardcoded table — expect disagreement, since
these values predate several epic changes; give the table the same stamped
provenance being built for spread (`spread_table_sha` pattern: a content hash
plus per-symbol `n`/date-range/source), so a row records which parameter set
it used; and decide explicitly whether the floor should be the broker minimum,
a volatility floor, or both — right now it silently serves as both and is
calibrated as neither.

**Do not fix during the parity sequence.** Changing the floor changes sizing on
half of all trades, which would confound the parity before/after comparison
that is the entire point of that sequence. Fix after the gauntlet regenerates,
and bump `engine_version` when it lands.

---

## 15. `NORMAL_SPREADS` — an uncalibrated constant behind a LIVE gate that has never fired
*(added 2026-08-16 during spread-capture work — recorded, NOT fixed)*

**Broken, on two independent levels.** The second is worse than the first.

### Level 1 — the constant looks ~5x wrong
First real measurement of EURUSD's dealing spread (2026-08-16, capture commit
36fac3b) reads **~0.00015, i.e. ~1.5 pips — on a thin Sunday pre-open book,
which is the WIDEST it should ever be.** `NORMAL_SPREADS["EURUSD"]` is
`0.0008` = **8 pips**. Since `should_block_spread` blocks at `2x normal`, the
effective EURUSD threshold is **~16 pips**, against a real spread that is
roughly a tenth of that even at its worst.

Like `MIN_SL_DIST` (finding 14) and the engine's `SPREAD_COSTS`, the table has
**no provenance** — no measurement, no date, no source. It covers only 3
symbols (`US500`, `EURUSD`, `DAX`) and none of GBPUSD/AUDUSD/USDCAD.

**The error direction matters:** too wide makes the filter PERMISSIVE. A
protective gate that is calibrated wrong in the permissive direction reports
success by staying silent, which is indistinguishable from working.

### Level 2 — the gate is structurally dead, not merely permissive
`webhook/receiver.py:216` reads the spread from the **inbound payload**:

```python
current_spread = safe_float(data.get("spread"))
if should_block_spread(symbol, current_spread):
```

and `should_block_spread` opens with `if current_spread is None: return False`
("fails open if no spread data"). **The TradingView payload has never carried a
`spread` field.** Verified against every stored alert:

| Check | Result |
|---|---|
| `webhook_log` rows, all time | 382 |
| payloads containing a `spread` key | **0** |
| `spread_filter` blocks, all time | **0** |
| `signal_log` rows mentioning spread (loop path has no spread gate at all) | **0 of 80,175** |

Every other webhook filter has fired — `session_filter` 150, `day_of_week` 27,
`daily_loss_limit` 15, `friday_block` 1, `strategy_inactive` 1. The spread
filter is the only one with zero. It short-circuits on the `None` guard before
the threshold is ever consulted, so **fixing the constant alone would change
nothing.** This is documented in CLAUDE.md as an active protection ("5. Spread
filter: blocks if current_spread > 2× NORMAL_SPREADS[symbol]").

**Third instance of the pattern**, after spread (`SPREAD_COSTS`) and
`MIN_SL_DIST`: a hand-set, unmeasured table trusted as if calibrated. And a
fresh instance of the unverified-controls class (finding 9) — a control
believed to be in place, never empirically confirmed, whose silence was read as
"nothing to block."

**Invalidates:** any claim that live trades are protected against spread
blowouts. They are not, and have never been.

**Fixing requires** (deliberately NOT during the parity sequence, same
reasoning as finding 14 — changing a live gate mid-sequence confounds the
before/after):
1. Feed the gate a real spread. The webhook path must read the current quote
   itself rather than trusting the payload; `execute_trade.last_spread` and
   `candle_stream.get_spread()` (both added 36fac3b) now supply exactly this.
2. **Re-derive the threshold from measured data rather than inheriting the
   `2x` multiplier** — `2x` of a wrong baseline is arbitrary, and the right
   form is probably a percentile of the observed distribution.
3. Recalibrate `NORMAL_SPREADS` from the same measurements that produce the
   engine's spread table in commit 5, so the backtest and the live gate cannot
   disagree about what "normal" means.
4. Extend to all rostered symbols, not 3.

---

## 16. USDCAD paper P&L understated ~1,900x — a missing dict key
*(added 2026-08-16, Stage 2 Phase 1 — recorded, NOT fixed)*

**Broken:** `_EPIC_VALUE_PER_POINT` (`bot/live_signal_loop.py:735-740`) is a
**third independent copy** of the value-per-point table, and it omits USDCAD.
The resolver reads it as `.get(symbol, 1.0)` (`:791`), so USDCAD silently
sizes against `vpp = 1.0` instead of `10000.0`.

**Consequence:** `lot = risk/(sl_dist × 1.0)` = `10/0.0005` = 20,000, clamped
down to the 10.0 maximum, then `pnl = raw_pnl × 10 × 1.0`. Every USDCAD paper
trade books roughly **one two-thousandth** of its intended value.

**Evidence** — measured across all resolved paper rows:

| symbol | n | avg abs(pnl) |
|---|---|---|
| **USDCAD** | **97** | **$0.008** |
| AUDUSD | 174 | $13.72 |
| US500 | 231 | $14.97 |
| GBPUSD | 234 | $15.11 |
| EURUSD | 713 | $17.41 |
| US100 | 63 | $19.70 |
| BTC | 29 | $20.69 |
| DAX | 13 | $22.84 |

Worked example, id=893: `entry=1.40841 sl=1.40891`, `sl_dist=0.00050`. Correct
lot 2.02 → **−$10.00**. Stored: **−$0.0050**. Total USDCAD paper P&L across 97
trades: **−$0.049**.

**Also latent: EURGBP and USDJPY are absent from the same dict.** Neither has
paper rows yet; both would fail identically the moment one is added.

**Fourth instance of the duplicated-instrument-table class**, after
`EPIC_CONFIG`/`SYMBOLS` in `candle_stream.py` (2026-07-20 bug 2, which cost
USDCAD seven days of signals) and the `MIN_SL_DIST` copy resolved at parity-v1.
`instrument_limits.py` was created for exactly this and arrived **one stage too
late** to prevent it — the resolver's copy was never audited when the live-path
copy was consolidated.

**Invalidates:** every USDCAD paper statistic. USDCAD reads as flat because its
P&L is quantised to fractions of a cent, not because the strategy is neutral.

**Fixing requires:** a single `VALUE_PER_POINT` in `instrument_limits.py`
imported by all three consumers, and a **`KeyError` rather than a `.get()`
default** — a silent fallback is what turned a missing key into 97 wrong rows.

---

## 17. 557 shadow rows resolved and aggregated as real trades
*(added 2026-08-16, Stage 2 Phase 1 — recorded, NOT fixed)*

**Broken:** shadow rows are counterfactuals for signals that were
**deliberately blocked** — session gates, correlation caps, margin rejections.
They are written to `paper_trades` with a `SHADOW_BUY`/`SHADOW_SELL` prefix so
the blocked path can be A/B compared against the taken one. Two places lose
that distinction:

1. `bot/live_signal_loop.py:749` strips the prefix before resolution:
   `.replace("PAPER_", "").replace("SHADOW_", "")`. Shadow rows resolve
   through exactly the same path as real paper trades.
2. `database/models.py:686-696` `get_paper_trade_stats()` aggregates
   `FROM paper_trades` with **no signal filter at all** — no `WHERE`, no
   `GROUP BY signal`.

**Scale — 36% of all resolved rows:**

| signal | LOSS | WIN | PENDING |
|---|---|---|---|
| PAPER_BUY | 309 | 204 | 1 |
| PAPER_SELL | 332 | 161 | 0 |
| **SHADOW_BUY** | **147** | **102** | **9** |
| **SHADOW_SELL** | **197** | **102** | **9** |

997 real, **557 shadow**, 19 pending.

**Invalidates: every paper statistic ever quoted from this system.** That
includes the promotion-criteria table showing `US500 ema_pullback` clearing the
R:R-adjusted bar, the paper win rates in CLAUDE.md's strategy tables, and
dashboard pages 07 and 08. The contamination is not random — shadow rows are by
construction the signals a filter judged *worse*, so mixing them in biases every
strategy's apparent performance in an unknown direction and by an unknown
amount.

**Do NOT stop writing them or delete them.** Their counterfactual value is the
entire reason they exist — they are the only measurement of whether a blocking
filter helps. The requirement is **separability**, not removal.

**Fixing requires:** filter at aggregation (every stats consumer), keep
resolution as-is so the counterfactual continues to be measured, and expose a
deliberate `include_shadow=False` parameter so a caller has to opt in rather
than opt out.

---

## 18. `models.py` writes columns `db.py` never creates — a fresh DB cannot log
*(added 2026-08-16, Stage 2 — FIXED in the same commit that records it)*

**Broken:** two columns are written by `database/models.py` but never created
by `database/db.py`. On the VPS both exist by historical accident, so live
logging works. **Any database built purely from `init_db()` raises
`OperationalError` on every write to them.**

Reproduced by building a fresh DB from the pre-fix `db.py` and calling the
writers directly:

```
log_signal_check: OperationalError: table signal_log has no column named spread
log_paper_trade : OperationalError: table paper_trades has no column named session
```

### 18a — `paper_trades.session`
`log_paper_trade` has INSERTed into `session` while `db.py` creates it in
neither the `CREATE TABLE` nor any `ALTER`. Origin is the 2026-05-30 market-
context work (`b5f4b57`), which wired `session` into `trades` and into the
paper INSERT but only migrated the `trades` table.

### 18b — `signal_log.spread` — self-inflicted, one commit old, and the most instructive item in this file

**The warning against this exact mistake was written as a code comment in the
same commit that made it, one table over.**

`36fac3b` (spread capture) added `ALTER TABLE signal_log ADD COLUMN spread
REAL` at line ~224, while `CREATE TABLE IF NOT EXISTS signal_log` sits at line
~328. On an existing database the ALTER worked. On a fresh one the table did
not yet exist, the bare `except` swallowed the error, the later CREATE built
the table without the column, and every `log_signal_check()` raised.

The same commit, on the `walkforward_runs` migration, carries this comment:

> *"Must run AFTER the CREATE above — on a fresh DB the table would not yet
> exist and the ALTER would be silently swallowed by the except, leaving the
> column missing."*

Identified, written down, and then violated in the same diff. **Knowing a trap
and encoding that knowledge as prose is not the same as being protected from
it** — the walkforward_runs migration was placed correctly *because it was
written second, next to its own CREATE*; the signal_log one was written next to
a different migration block and inherited that block's position.

**Consequence for the commit that introduced it:** `36fac3b` was the spread
CAPTURE commit. Its entire purpose was to start accumulating spread
observations. On any fresh database it would have captured **nothing**, while
appearing deployed. It was **one lost volume mount away from silently not
capturing at all** — and the failure mode would have been invisible in exactly
the way finding 9's unverified-controls class describes: silence read as
"nothing to record."

**The bare `except Exception: pass` is what made it silent.** It cannot
distinguish "column already exists" (expected, benign, happens on every restart)
from "table does not exist" (a real ordering bug). Both are swallowed
identically.

### Full audit — are there others? **No. These two only.**
Every `INSERT INTO` and `UPDATE ... SET` in `models.py` was checked against a
schema built purely from `init_db()`: **15 INSERT sites across 14 tables, 3
UPDATE sites.** Result before the fix: 2 problems (the two above). After: **0**.

Clean tables: `trades` (20 cols), `positions`, `heartbeat`,
`candle_source_compare`, `backtest_results` (18), `backtest_trades`,
`active_strategy`, `active_strategy_history`, `correlation_events`,
`webhook_log`, `webhook_outcome_log`, `walkforward_runs` (18).

### Sharpens the `.dockerignore` justification in `14c3c17`
That commit argued excluding `database/*.db` improves the failed-mount case:
*"a failed or misconfigured mount now yields an empty auto-created DB and
therefore no trading, instead of silently running against a build-time
snapshot."* **That statement was incomplete.** The auto-created DB could not
log a paper trade or a signal check at all — the loop would have raised on
every cycle. Still preferable to trading on stale strategy config, but the
degraded state was worse than described.

**Fix applied:** both columns added to their `CREATE TABLE` DDL *and* kept as
`ALTER` migrations positioned **after** the corresponding CREATE, matching the
`walkforward_runs` pattern. Verified on a fresh DB: `init_db()` idempotent
across two runs, all three writers succeed, static audit clean.

**Standing lesson:** an `ALTER TABLE` migration must sit after its table's
`CREATE`, and a bare `except` around schema changes hides ordering bugs
indefinitely. **A migration that has only ever run against an existing database
has not been tested.** Every schema change from here should be verified against
a DB built purely from `init_db()`, not only against the deployed one — the
deployed database's history papers over exactly this class of defect.

**DEFERRED, agreed but not this commit:** narrow the bare
`except Exception: pass` around each migration to `sqlite3.OperationalError`
with a message check, so "duplicate column name" passes and "no such table"
raises. That converts this whole class from silent to loud.

---

## 19. Two dashboard pages count "win" differently — and the disagreement is a symptom
*(added 2026-08-16, Stage 2 — recorded, deliberately NOT fixed in commit 2)*

**Broken:** two definitions of a winning paper trade coexist in the dashboards.

| Site | Basis |
|---|---|
| `01_overview.py:83` | `SUM(CASE WHEN simulated_pnl > 0 ...)` — **P&L sign** |
| `07_performance.py:671,681`, `08_paper.py:31,41` | `SUM(CASE WHEN outcome='WIN' ...)` — **outcome** |

Two pages have been reporting different win rates for the same strategies, and
nobody noticed.

### Scale: small, and it is not the interesting part
Across the 1,554 resolved rows, exactly **2 disagree**:

| Case | Rows |
|---|---|
| `outcome='WIN'` but `pnl <= 0` | 0 |
| `outcome='LOSS'` but `pnl > 0` | **2** |
| `pnl` exactly 0 | 0 |
| `pnl IS NULL` | 0 |

Per-strategy win rate is identical under both bases for every strategy except
one:

| strategy | n | WR by outcome | WR by pnl sign | delta |
|---|---|---|---|---|
| **supertrend** | 117 | **32.48%** | **34.19%** | **+1.71 pp** |
| williams_r | 846 | 37.23% | 37.23% | 0.00 |
| stoch_rsi | 319 | 30.41% | 30.41% | 0.00 |
| ema_pullback | 126 | 40.48% | 40.48% | 0.00 |
| *(all others)* | | | | 0.00 |

**No promotion decision turned on this.** `supertrend` EURUSD 15MIN is a paper
row and 1.71 pp does not cross any criterion boundary. Recording it because
"two definitions of the primary metric" is a defect regardless of current
magnitude, and because of what the two rows turn out to be.

### The disagreement is a SYMPTOM of a degenerate bracket
Both rows are `paper_trades` id **334** and **335**, EURUSD `supertrend`
`PAPER_SELL`:

```
entry=1.1469204425811768   sl=1.1469   tp=1.1469
SELL requires tp < entry < sl  ->  1.1469 < 1.14692 < 1.1469  ->  WRONG-SIDE
simulated_pnl=+2.0443   outcome=LOSS
```

`sl == tp`. A zero-width bracket where both levels sit on the same side of
entry. The resolver detects `high >= sl` → `LOSS`, then computes
`raw_pnl = entry - sl = +0.0000204` — **positive, because the stop is on the
wrong side.** Hence a LOSS with positive P&L.

**These are the same rows as finding 3's MAX-clamp survey** (ids 334/335,
"sl=0.20 pips, lot=48.92 → clamped 10"). One defect surfacing three ways: a
degenerate bracket, a lot clamp, and a win-basis disagreement.

**3 of 1,573 priced rows have wrong-side levels** (1 BUY, 2 SELL).

**`parity-v2`'s `EngineContractError` rejects exactly this condition in the
backtest engine** — `BUY requires sl_price < entry < tp_price`, and the SELL
mirror. The paper resolver has no equivalent check, which is why the same
malformed signal is rejected by one synthetic model and monetised by the other.
Another instance of findings 2's "two independent synthetic models" problem.

### Which basis is correct: `outcome`. `01_overview.py` is the wrong one.
A win is "the take-profit was reached", not "the arithmetic came out positive":

1. **`outcome` states what happened**; P&L sign is a downstream consequence
   that can invert when the bracket is malformed — as it does here. Defining
   the metric by the consequence lets a data defect silently reclassify a
   trade.
2. **`outcome` handles the third state.** `PENDING` is excluded naturally,
   whereas P&L sign counts a zero-P&L row as neither win nor loss, silently
   shrinking the denominator.
3. **It matches the engine**, which books `exit_reason` (`tp_hit`/`sl_stop`)
   and derives P&L from it, never the reverse.

**Fix, when it is taken (NOT commit 2 — that commit changes what is counted,
not how):** `01_overview.py:83` moves to the `outcome` basis, AND the resolver
gains the wrong-side/degenerate-bracket rejection the engine already has, so
rows like 334/335 are refused rather than reinterpreted. Fixing the count alone
would hide the malformed rows instead of surfacing them.

---

## Sequencing

| Work | Depends on | Notes |
|---|---|---|
| `status` default fix (3 layers) | — | Independent; do first |
| Cron writes `'paper'` only | status fix | Subsumes finding 5 |
| **Engine contract fix** (findings 1, 12) | — | Default TP **and** hard failure. Regenerates all evidence |
| Audit the 13 emitters' TP rules | engine contract fix | Emitting ≠ emitting correctly; never checked |
| Paper resolver (finding 2) | — | **Sibling to engine parity, not a subtask** |
| `sl_distance` sanity bound | paper resolver | Must **reject at both ends** — floor and ceiling (finding 3 correction) |
| `engine_version` marking | engine parity | See below |
| Quarantine id=824, re-baseline | finding 2 | Includes correcting CLAUDE.md |
| Gauntlet regeneration | engine parity + marking | Regeneration, not reproduction |
| Promotion-time verdict check | `walkforward_runs` | Refuse to cite a verdict with no row — would have caught both EURUSD and AUDUSD (finding 7) |
| `logs/` + `candle_cache/` volumes | — | Fold in with the `collect_candles` decision |
| `/tmp` state files | volume work | `candle_stream_fallback_state.json`, `watchdog_state.json` lose alert-dedup cooldowns on restart |
| `.dockerignore` for `logs/`, `database/` | — | Stops baking stale copies into the image (finding 10) |

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
containing **three** different risk sizes (see the correction below) and an
unadjusted pre-spread PF — false authority is worse than no gate. **And per
finding 17 that sample is contaminated with shadow rows**, so the trade count
itself is not what it appears.

**CORRECTION (2026-08-16) — the risk eras are THREE, not two.** This file said
"$10 and $15". Recovered exactly from stored data, not inferred: for an
unclamped LOSS the resolver's algebra gives `pnl = −risk` precisely, so reading
`simulated_pnl` off `paper_trades` yields **$10: 597 rows, $15: 245, $3: 57,
other (clamped): 86**. Confirmed against `git log` on `risk_manager.py`:

| From | Paper risk |
|---|---|
| before 2026-06-12 | per-symbol `RISK_PER_TRADE_OVERRIDE` (no `is_paper` branch existed) |
| 2026-06-12 (`4e1fa80`) | **$15** — `is_paper=True` introduced, forcing the module default |
| 2026-07-02 (`1060609`) | **$3** — account-rebuild throttle |
| 2026-07-08 (`0ee8551`) | **$10** — demo validation |

Four regimes including the pre-`is_paper` era. Any re-baseline must key off the
row's own recovered risk, not a single assumed constant.

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
