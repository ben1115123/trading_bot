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

> **⛔ ROOT CAUSE SUPERSEDED — see finding 25 (2026-08-18).** Point 1 below
> is true as literally written but is **not the cause**, and the fix it
> implies is actively wrong. The candle buffer that feeds the paper write
> sites is already decimal (`_mid_ohlc` and `_rest_fetch` both guard and
> convert, since `839aeee`, twelve days before id=824), so adding
> `to_decimal` at the write sites would DOUBLE-CONVERT. The real mechanism
> is a single Lightstreamer tick delivered in points scale while `ig_scale`
> held a correct decimal classification, making `to_decimal` a no-op —
> recovered from `candle_source_compare` at `2026-07-21T19:20:32`,
> `delta_pips = -114,008,596`. Read finding 25 before acting on this
> section.

**Two structural problems this exposes:**

1. The paper-trade path has **no `ig_scale` conversion**. CLAUDE.md lists
   the boundary conversion sites as `execute_trade.py`,
   `positions_poller.py`, `candle_stream.py`, `sync_ig_trades.py`. The paper
   logging path is not among them. *(True, but harmless and not the cause —
   see the note above.)*
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

## 20. A fourth `_MIN_SL_DIST` copy — and why absence beats contradiction as a failure mode
*(added 2026-08-16, Stage 2 — recorded, deliberately NOT fixed)*

**Broken:** `bot/execute_trade.py:113` carries its own `_MIN_SL_DIST`, separate
from the copy consolidated into `instrument_limits.py` at parity-v1. Reconciled
cell by cell against the shared table: **no conflicts**, but it is **missing
EURGBP, USDJPY and XAUUSD**.

**Not fixed, and the reason is scope not oversight:** this table sits on the
**live execution path** — it sets the stop distance actually sent to IG.
Consolidating it changes live SL behaviour, which would confound the parity
before/after the whole sequence exists to measure. Same reasoning as findings
14 and 15. Fold it in after the gauntlet regenerates, and treat it as a live
change with its own verification, not as housekeeping.

### The general lesson — this is the important half

Across **all four** instrument-table instances found so far
(`EPIC_CONFIG`/`SYMBOLS` in `candle_stream.py`, `MIN_SL_DIST` in the live loop,
`_EPIC_VALUE_PER_POINT` in the resolver, and this one):

> **No cell has EVER contradicted another. Every single divergence was an
> ABSENCE.**

That asymmetry is the whole problem. A contradiction — the same symbol with two
different values in two files — is caught the first time anyone diffs them, and
it announces itself as obviously wrong. An absence announces nothing: the
lookup succeeds, returns a plausible default, and the arithmetic proceeds
confidently. Finding 16 is the clean example — USDCAD missing from one dict,
`.get(symbol, 1.0)` returning `1.0`, and 97 paper rows silently booking
1/2000th of their value for two months.

**Standing rule, not a local fix: look instrument tables up by `[symbol]`,
never `.get(symbol, default)`.** A `KeyError` on an unregistered symbol is
correct behaviour — loud, immediate, at the first use. The default is what
converts a missing key into wrong numbers that look right. Applied at
paper-v1 to `VALUE_PER_POINT`; `MIN_SL_DIST` and the remaining tables should
follow when they are next touched.

### Addendum (2026-08-17) — the `.get(key, default)` variant, and 4 latent instances

Finding 22 turned up a **second form** of the same defect, and it is the more
deceptive one. The standing rule above targets `.get(symbol, default)` on
instrument tables, where the key is genuinely absent. This variant is:

> **`.get(key, default)` against a row from `SELECT *`, where the key is ALWAYS
> present and holds `None`.** The default is dead code. It has never fired and
> never will.

`trade.get("timeframe", "HOUR")` read as a safe fallback for nine weeks. It was
not a fallback at all — `get_pending_paper_trades()` does `SELECT *`, so
`timeframe` is always a key, and a NULL column hands back `None`. The resolver
then called `None.upper()` and raised, every cycle, for 40+ days.

**Audited across the codebase. Four more instances, all reading
`active_strategy` rows via `SELECT *`:**

| site | key | dead default |
|---|---|---|
| `bot/candle_stream.py:327` | `timeframe` | `"HOUR"` |
| `bot/candle_stream.py:328` | `strategy_name` | `""` |
| `bot/live_signal_loop.py:329` | `timeframe` | `"HOUR"` |
| `bot/live_signal_loop.py:1008-1010` | `timeframe` / `strategy_name` / `strategy_type` | `"HOUR"` / `""` / `"swing"` |

**Not firing today** — those three columns hold zero NULLs in
`active_strategy` on the VPS. **Recorded, deliberately not fixed**: they sit on
the live candle-subscription and signal-check paths, and this commit's job was
the resolver. Fold into the next `candle_stream` touch.

**Their failure mode is worse than the resolver's, and that is the point.** The
resolver *crashed* — loud, repeated, and ultimately findable. These four would
not crash. `None` flows into the downstream membership tests
(`strategy_name not in STRATEGIES`, `timeframe not in _LS_SCALE_FOR_TIMEFRAME`)
and the pair is **silently skipped**: no exception, no log line, just a
`(symbol, timeframe)` that quietly stops being subscribed. That is precisely
the USDCAD shape from Bug 2 — a candle buffer that was never created, reported
only as "buffer not warm yet" for seven days.

So the general rule needs its second half stated:

> **A default is only a safety net when the key can actually be missing.**
> Against a `SELECT *` row, prefer `row["key"]` and handle NULL explicitly.
> `.get(key, default)` there does not defend anything — it disguises a NULL as
> a deliberate value.

### XAUUSD will now raise, and that is correct
`XAUUSD` appears in `execute_trade`'s floor table and in
`instrument_limits.MIN_SL_DIST`, but **not** in `VALUE_PER_POINT` — no epic is
registered for it anywhere and it has never traded. If gold is ever enabled,
the value-per-point lookup will **`KeyError` rather than silently size at
1.0**. That is the intended behaviour of the standing rule above.
**Do not read that KeyError as a regression** — it is the check working, and
the fix is to register XAUUSD's real contract value, not to reinstate a
default.

---

## 21. Paper resolver price source — ACCEPTED DIVERGENCE, not a to-do
*(added 2026-08-17, Stage 2 — decided, closed)*

The resolver reads yfinance while live execution reads the IG stream
(`CANDLE_SOURCE=ig_stream` since 2026-07-15). That is a real divergence between
the paper model and live, and it is **recorded here as accepted permanently**,
not as a deferred item. Nothing about the resolver's source is scheduled to
change.

**Why the stream cannot serve this consumer — three independent reasons, any
one of which is sufficient:**

1. **Buffer depth.** `bot/candle_stream.py:69` caps at `MAX_BUFFER = 500`, but
   the live depth is set by warm-up plus uptime, not by the cap — measured on
   the VPS 2026-08-17, **no buffer held more than 216 candles**. And 500
   candles is not a fixed span of *time*: it is whatever that instrument's
   trading calendar covers.

   | buffer | candles | span |
   |---|---|---|
   | EURUSD 15MIN | 216 | **4.4 days** |
   | US100 15MIN | 214 | 11.4 days |
   | US500 HOUR | 205 | 40.9 days |

   The oldest currently pending row is **47.6 days** (id=398). Nothing in the
   buffer set reaches it, and the shortest-spanning buffer misses by an order
   of magnitude. Deepening is not a constant change either — it is
   per-(symbol, timeframe) resident memory in the bot process.
2. **In-memory, reset on restart.** The buffers are process state; on restart
   the process re-warms to `WARMUP_COUNT = 200` candles (`candle_stream.py:66`)
   and everything earlier is gone. Measured: the current container has been up
   since **2026-08-16T16:23:27Z with `RestartCount=0`**, and EURUSD 15MIN's
   oldest candle is **2026-08-12T19:30** — the warm-up reach, not a history.
   A resolver reading this would return different outcomes for the same row
   depending on how recently the container was recreated, and deploys recreate
   it routinely.
3. **Coverage follows the roster — but at two different granularities, and the
   coarser one is not the safe one.** `_needed_pairs()`
   (`candle_stream.py:310`) derives `(symbol, timeframe)` pairs from
   `get_active_strategies`, and **warm-up runs only over those pairs**. The
   Lightstreamer subscription is built separately as a **cross product**,
   `epics_needing × scales_needed` (`candle_stream.py:620-621`). So
   deactivating a strategy removes its warm-up immediately, while its
   subscription survives incidentally for as long as some *other* pair keeps
   both its epic and its scale alive.

   Measured, and this is the case that matters: **`(US100, HOUR)` is not in the
   7-pair warm-up list**, yet its buffer exists with **5 candles, the earliest
   2026-08-14T21:00** — fed by cross-product ticks alone. `paper_trades`
   **id=1459** signalled **2026-08-12T13:01**, two days before the buffer's
   first candle. Unreachable.

   Full loss shows on symbols with no active pairs at all: **DAX HOUR, DAX
   15MIN and BTC HOUR are all length 0**.

   The point is not that one row is unreachable. It is that the data source
   disappears **exactly when you most want that strategy's paper record
   completed** — when judging whether the deactivation was right — and that a
   partially-surviving cross-product subscription makes the loss *look*
   intermittent rather than announcing itself.

**Why a half-migration is worse than the divergence.** "Stream when available,
yfinance otherwise" makes outcome provenance a function of container uptime and
subscription state at resolution time — neither of which is recorded anywhere in
the row. Two rows with identical signals could then be resolved by different
price sources with no way to tell which, after the fact. A single consistent
wrong-ish source is auditable; a silently-varying one is not. Compare finding
20's general lesson: the dangerous failure is the one that announces nothing.

**The only path that changes this** is durable candle storage — a persisted
IG-sourced cache (`--source ig_cache`, `scripts/collect_candles.py`) deep enough
to cover a 14-day resolution window, which the resolver could query by time
range rather than by buffer position. That is a separate project with its own
volume, retention and backfill decisions (see finding 10 — `candle_cache/` is
not even a volume today). **Until that exists, yfinance is the resolver's
source, by decision.**

---

## 22. The resolver's resolution window was never the signal's window
*(added 2026-08-17, Stage 2 — quantified, fix in Stage 2 items 1+2)*

**Broken:** `_resolve_pending_paper_trades()` asks for 100 candles and then
filters to those after the signal. For any row older than 100 candles, **every
candle it examines postdates the signal by weeks**, and it books whichever
level was touched first in that far-future window.

**Mechanism — `count` never controlled the fetch.**
`scripts/run_backtest.py::_fetch_yfinance_candles` downloads a **fixed period**
and only then trims:

```python
period = YF_PERIODS[interval]          # 15m → "60d", 1h → "730d"
df = yf.download(ticker, period=period, interval=interval, ...)
...
return candles[-count:]                # count is a TAIL TRIM, not a range
```

**The available window is two different numbers, and the gap is itself a
finding.** `YF_PERIODS["15m"] = "60d"` is what the code **requests**. A
measurement of one actual 15MIN response returned **5,592 candles spanning 80.9
days** — yfinance returns **more** than the configured period asks for. Neither
number is wrong; they answer different questions, and only the measured one
describes what the resolver can actually reach.

Record both, and treat the discrepancy as live: **the difference between what a
data source is asked for and what it returns is an undocumented assumption**,
and this project has been bitten by that class repeatedly — IG's REST
`snapshotTime` in account-local time, yfinance intraday timestamps in
exchange-local time, `scalingFactor` not predicting which epics need conversion
(see CLAUDE.md, CANDLE_SOURCE and Price scale quirk). Same shape every time: a
value assumed from configuration or a field name rather than measured from the
response.

The 14-day expiry sits well inside **either** figure, so nothing in the fix
depends on resolving this. Do not build anything on the 80.9-day number without
re-measuring — it is one observation of a third-party API's behaviour, not a
documented contract.

The resolver's call is `_fetch_yfinance_candles(symbol, timeframe, 100)`
(`bot/live_signal_loop.py:803`), so it receives **the most recent 100 candles**
— 25 hours at 15MIN — regardless of when the signal fired. Then:

```python
later = [c for c in candles if _candle_dt(c) > signal_dt]
```

For a row whose signal predates that 25-hour tail, the predicate is **true for
all 100 candles**. Nothing is filtered out. The loop walks a window ~36 days
downstream of the signal and returns the first SL or TP touch it finds there.

**This is not truncation. It is the wrong window entirely.** A truncated window
resolves a subset of the correct bars and otherwise stays PENDING — safe. This
resolves a *disjoint* set of bars and returns a confident WIN/LOSS.

**Measured impact on the current pending set: 4 of 9 resolvable rows (44%) flip
outcome under a correct window** — ids **424, 433, 512, 532**, all EURUSD.
⚠️ **UNVERIFIED-AT-WRITE — see the provenance note below.**

### ⚠️ Provenance of the counts in findings 21 and 22

Every row-level number in these two findings came from a **prior-session
measurement against the VPS database**, and none of it was re-checkable at the
time of writing: the **local `database/trades.db` holds zero `paper_trades`
rows** (the corpus split of finding 11, in a form that bites documentation
rather than backtests).

Carried unverified: **9 resolvable pending**, **4 flips (424, 433, 512, 532)**,
**1,554 resolved**, **9 swiftalgo NULL-timeframe rows**, **10 others staying
PENDING**, **47-day oldest pending**, **id=1459 unsubscribed**.

**These numbers are not stable by nature.** Pending rows resolve on every
signal-loop cycle, so the set measured on one day is not the set that exists on
the next — a row counted as "resolvable" can become resolved, and a new pending
row can appear, without anything being wrong. Two of these figures are
load-bearing: **4-of-9 is the headline of this finding**, and **the 9 swiftalgo
rows drive the expiry decision**.

**Required before the Stage 2 window fix lands: re-measure all of the above on
the VPS and amend this section with the result** — including "unchanged" if
that is what it is. An unverified figure that turns out to still be right must
be *shown* to be right; per the marker-test rule in finding 9, absence of a
contradiction is not confirmation.

### ✅ Re-verified on the VPS, 2026-08-17 — headline holds, counts moved

Read-only against `/home/ubuntu/trading_bot/database/trades.db`, plus a
re-run of the flip counterfactual against live yfinance.

| Figure | At write | Re-verified | |
|---|---|---|---|
| Flips | 4 of 9 — 424, 433, 512, 532, all EURUSD | **4 of 9 — 424, 433, 512, 532, all EURUSD** | **reproduced exactly** |
| swiftalgo NULL-timeframe rows | 9 | **9** | unchanged |
| Resolved rows | 1,554 | **1,565** | +11 |
| Pending rows | 19 | **16** | −3 |
| Non-swiftalgo pending ("the others") | 10 | **7** | −3 |
| Oldest pending | 47 days | **47.6 days (id=398)** | unchanged |
| id=1459 unsubscribed | asserted | **mechanism corrected, conclusion holds** | see finding 21 reason 3 |

The moved counts are the expected behaviour of a live system, not a
contradiction: rows resolve every cycle and new ones arrive. The two
load-bearing figures — the 4-of-9 flip and the 9 swiftalgo rows — are exactly
as measured.

**The counterfactual, with the mechanism visible in the lag column:**

```
id= 424 EURUSD SELL sig=2026-07-01 06:13 | wrong=LOSS @ 2026-08-10 21:00 | right=WIN  @ 2026-07-01 09:00 | FLIP  (wrong window starts 40d after signal)
id= 433 EURUSD SELL sig=2026-07-01 11:57 | wrong=LOSS @ 2026-08-10 21:00 | right=WIN  @ 2026-07-01 12:00 | FLIP  (40d)
id= 512 EURUSD BUY  sig=2026-07-07 12:23 | wrong=WIN  @ 2026-08-10 21:00 | right=LOSS @ 2026-07-07 16:00 | FLIP  (34d)
id= 532 EURUSD SELL sig=2026-07-07 18:32 | wrong=LOSS @ 2026-08-10 21:00 | right=WIN  @ 2026-07-07 19:00 | FLIP  (34d)
id=1012 US500  BUY  sig=2026-07-30 09:21 | wrong=WIN  @ 2026-07-30 13:30 | right=WIN  @ 2026-07-30 13:30 | same  (0d)  <- control
```

Two things this makes visible that the summary figure alone does not. Every
correct-window resolution lands **within hours** of its signal, which is what a
15MIN/HOUR bracket should do; every wrong-window EURUSD resolution lands on the
**same** far-future bar, `2026-08-10 21:00`, because all four are reading the
same recent tail and returning whichever level it grazed first. And **id=1012
is the control**: it is the one row young enough that its wrong window starts
0 days after the signal, so wrong and right agree. The defect switches on
precisely when the row outlives the tail.

### ⚠️ Discovered during re-verification: those 9 rows have NEVER been resolved at all

The live resolver does not misresolve them. **It crashes on them, every cycle,
and has since they were written.** From `docker logs trading_bot-bot-1`:

```
[resolver] 16 pending paper trade(s) to check
[resolver] [US500] candle fetch failed: 'NoneType' object has no attribute 'upper'
[resolver] [EURUSD] candle fetch failed: 'NoneType' object has no attribute 'upper'
...   (exactly 9 of these, every cycle)
[resolver] [US100/HOUR] id=1459 still PENDING
```

Cause: `timeframe = trade.get("timeframe", "HOUR")` — `.get`'s default fires on
a **missing key**, not on a **present NULL**. `get_pending_paper_trades()` does
`SELECT *`, so the key is always present, and a NULL column yields `None`. The
`"HOUR"` default has never once been used. `_fetch_yfinance_candles` then does
`timeframe.upper()` and raises.

Three consequences:

1. **The 4-of-9 flip is a counterfactual, not an observed misresolution.** It
   is computed under an *assumed* HOUR granularity, which is precisely the
   assumption the EXPIRE decision refuses to make. Stated exactly: *had* these
   rows been resolvable, 44% of them would have been booked wrong. The window
   defect itself is not in doubt — the code path is unambiguous and applies to
   every row old enough — but this particular set demonstrates it by
   simulation, and the finding must not be read as "4 rows were resolved
   wrongly."
2. **It strengthens the EXPIRE decision to two independent reasons.** These
   rows cannot resolve (permanent crash) *and* resolving them would require
   inventing a granularity. Either alone is sufficient.
3. **It is a live instance of the exact distinction Stage 2 item 2 exists to
   draw.** A permanent, structural failure — a malformed row that will raise
   identically forever — is swallowed by the resolver's generic
   `except Exception` and printed in the same words as a transient network
   failure, then retried every five minutes indefinitely. The fix must
   classify the `timeframe is None` case explicitly rather than let the 14-day
   expiry mop it up, or a NULL-timeframe row written tomorrow will crash-loop
   for a fortnight before anything notices.

Not a `.get(symbol, default)` instance (finding 20's standing rule), but the
same family: **a default that silently never fires is indistinguishable from
one that fires correctly, until something downstream raises.**

### The unmeasurable part — and why it changes the re-baseline framing

Any already-resolved row that was older than its window **at the moment it was
resolved** went through this same path. There are **1,554 resolved rows**. How
many were affected cannot be determined:

> **`paper_trades` has no resolution timestamp.** `checked_at` is the *signal*
> time, not the resolution time. There is no stored value from which row-age-at-
> resolution can be reconstructed.

So the re-baseline framing must be stated as **both** of the following at once,
and neither clause may be dropped:

- outcomes on resolved rows are **taken as given** — they are the only record
  that exists; and
- they are **demonstrably wrong for a subset whose size is unknowable**.

This is not the usual "historical numbers came from a worse model" caveat that
`engine_version` handles. `engine_version` answers *are these two rows
comparable*; it cannot answer *was this individual row resolved against the
right bars*, because the input that would decide it was never recorded.

**This wording must appear in the re-baseline commit message and in the
re-baseline script's header comment — not only in this file.** A caveat that
lives only in a findings doc is one `git log` away from invisible.

### `resolved_at` — added going forward, deliberately NOT backfilled

The Stage 2 fix adds `paper_trades.resolved_at`, written at resolution time. It
is **not** backfilled, and that is a decision, not an omission: **there is
nothing to backfill from.** Any value written into it for the 1,554 existing
rows would be inferred, and an inferred timestamp in a column whose entire
purpose is auditing resolution timing would manufacture exactly the false
confidence this finding is about. The rows stay NULL. NULL means "resolved
before resolution time was recorded, age-at-resolution unknown" — which is the
true state.

---

## 23. `_is_blocked` has NEVER blocked FX — the control that was never confirmed
*(added 2026-08-17, Stage 2 — FIXED same day)*

**Broken:** the market-hours block did not apply to a single FX symbol, and
never had. `bot/live_signal_loop.py:126` opened with:

```python
close = MARKET_CLOSE.get(symbol)
if close is None:
    return False          # <-- every FX symbol exits HERE
```

`MARKET_CLOSE` contains **only `US500`, `US100`, `DAX`, `BTC`**. EURUSD,
GBPUSD, AUDUSD and USDCAD are absent, so `.get` returned `None` and the
function returned `False` **before reaching the Saturday, Sunday or Friday
branches below it**. Those branches were unreachable for FX for the entire
life of the file.

**Consequence, measured: 21 weekend trades were placed** — EURUSD 5, GBPUSD 7,
AUDUSD 4, USDCAD 2, BTC 3 — at exactly the timestamps where the measured
spread is **10–17 pips**. The bot was opening positions at the widest spreads
it ever sees, while the control everyone believed was in place did nothing.

**Two failure classes at once:**

1. **Fourth instance of `.get(key, default)` with an absent key** (findings 16,
   20, 22) — and **the first on the LIVE TRADING PATH**. The earlier three cost
   wrong numbers; this one placed real orders.
2. **Unverified controls** (finding 9). A filter believed active, never
   confirmed, silently inert. Nothing ever tested it — and absence of weekend
   trades would not have proved anything either, because most weekend cycles
   died downstream anyway.

**What made the silence look like normal operation:** `near market close` is
the single largest weekend `signal_log` error at **8,207 occurrences** across
23,496 weekend checks. The checks ran all weekend and mostly failed later in
the pipeline — on stale candles, unwarm buffers, or IG rejections — so the logs
looked busy and unremarkable. A control doing nothing looked identical to a
control working, because something *else* was usually stopping the trade.

### The root confusion: venue session vs entry policy

The function answered one boolean for two different questions, and that is why
the hole was invisible:

| | question | nature |
|---|---|---|
| **venue session** | can IG deal at all? | a **fact** about the market |
| **entry policy** | will *we* open a position? | a **preference**, narrower |

A shut book and a thin-but-open reopen are both "blocked" under one boolean,
yet they are opposites for analysis: the first produces quotes nobody could
trade on, the second produces real quotes we simply choose to avoid. Filtering
observations needs the fact; gating a trade needs both. `market_hours.py` now
splits them into `is_market_open()` and `is_entry_allowed()`.

### IG exposes no session data — the constant is derived from our own record

Verified 2026-08-17 via `fetch_market_by_epic` on CS.D.EURUSD.MINI.IP,
CS.D.GBPUSD.MINI.IP and IX.D.SPTRD.IFMM.IP:

| field | value |
|---|---|
| `instrument.openingHours` | **`null`** on every epic — present, unpopulated |
| `instrument.rolloverDetails` | `null` |
| `snapshot.marketStatus` | populated, but **live only** — cannot say what the status was last Sunday, so it cannot classify a stored row |

So the session is derived from **our own trade record** — successful
`live_signal_loop` FX opens by UTC weekday and hour:

```
Sun    . . . . . . . . . . . . . . . . . . . .  4  3  4  7      <- deals resume 20:00
Mon    8 10 7 3 5 2 8 10 10 2 6 5 4 6 9 5 1 1 1 3 1 1 2 2
Fri   11 10 13 8 6 7 12 7 6 9 5 6 5 5 5 1 . .  2 1 1  . . .     <- last deal ~21:00
Sat    . . . . . . . . . . . . . . . . . . . . . . . .          <- zero, all hours
```

Corroborated by IG's own rejections: `MARKET_CLOSED_WITH_EDITS` ×3 on Sat
2026-07-25 00:00, and `MARKET_OFFLINE` on Sun 2026-07-26 **21:20** — inside the
reopen ramp, which is why the reopen is treated as ragged rather than a clean
edge. **That provenance is restated in `market_hours.py`'s docstring**, because
a measured constant whose derivation lives only in a findings file becomes an
assumed constant the first time someone edits it.

### A second unverified constant, found while fixing the first

Writing the replacement, an index intraday close was nearly added from
`MARKET_CLOSE` (20:45) and CLAUDE.md's Market Hours table ("US500/US100 close
20:00 UTC"). **Neither survives contact with the trade record**, which holds
**18 index opens at or after 20:00 UTC — US500 10, US100 8 — every one
accepted by IG**:

```
US500  hour 20:00 -> 23:00 opens:  5  2  1  2
US100  hour 20:00 -> 23:00 opens:  .  3  1  4
```

Had it been added, it would have blocked trades that currently happen and that
the venue evidently permits.

**Same class as `NORMAL_SPREADS` (finding 15) and `MIN_SL_DIST` (finding 14):
a stated constant nobody ever checked against the record.** Two documents
asserted the same wrong number, which made it look corroborated — a second
source repeating an unverified claim is not verification.

**Establishing the real index session is explicitly NOT done here.** It needs
its own measurement, and this finding is about FX. `market_hours.py` carries no
index intraday rule, with the counts above written in as the reason it is
absent — so the next person sees measured evidence for the omission rather than
an apparent oversight to helpfully fix.

### Three disagreeing weekend boundaries in the tree — recorded, not merged

| value | where | governs |
|---|---|---|
| **Sun 20:00 UTC** | `market_hours.SESSION_REOPEN_HOUR` | measured venue reopen |
| **Sun 23:00 UTC** | `market_hours.FX_ENTRY_REOPEN_HOUR` | entry policy (matches `_is_blocked`'s original intent) |
| **Sun 22:00 UTC** | `scripts/watchdog.py::_is_market_hours` | heartbeat-staleness alerting only |

The watchdog copy is **legitimately separate and must not import
`market_hours.py`**: it runs on the host under cron, stdlib-only with no
project imports, so that it still works when the container is dead — which is
the entire point of a watchdog. It gates alerting, never a trade. Recorded so
the next person to notice the disagreement has a reference point rather than
assuming one of the three is a bug.

### Did blocking the weekend cost anything? Measured before fixing

The aggregate initially argued *against* the fix — weekend entries were the
only profitable FX subset:

| | n | net | mean | WR |
|---|---|---|---|---|
| weekend entries | 17 | **+$104.30** | +$6.14 | 52.9% |
| weekday entries | 559 | −$826.98 | −$1.48 | 30.1% |

Split at the 23:00 policy boundary, it resolves completely:

| | n | net | mean | WR |
|---|---|---|---|---|
| thin reopen 20:00–22:59 | 10 | **−$9.29** | −$0.93 | **30.0%** |
| post-23:00 | 7 | **+$113.59** | +$16.23 | 85.7% |
| weekday baseline | 559 | −$826.98 | −$1.48 | **30.1%** |

The thin-reopen window performs **exactly like the weekday baseline** — 30.0%
against 30.1%. The wide spread buys nothing. All of the profit sits after
23:00, where spreads are already normal.

**The mechanism is visible in the hold times.** Five of the thin-window trades
were closed within two minutes of entry at full risk:

```
id=844 EURUSD  Sun 20:35:30 -> 20:36:00   30s   -$10.00
id=845 AUDUSD  Sun 20:35:45 -> 20:35:44   ~0s   -$10.00
id=846 GBPUSD  Sun 21:05:37 -> 21:05:42    5s   -$10.00
id=727 GBPUSD  Sun 20:45:42 -> 20:47:29  107s   -$ 9.95
id=728 AUDUSD  Sun 21:15:55 -> 21:15:54   ~0s   -$10.00
```

A 10–17 pip spread against a candle-range stop breaches the stop **on the
spread alone**, before any price movement. These are not losing trades; they
are trades that were never viable.

> **CAVEAT, and it constrains what may be claimed.** n=7 and n=10 are small.
> The post-23:00 85.7% WR is **NOT an edge estimate** and nothing should be
> built on it. The only defensible claim here is the narrow one: **the thin
> window costs nothing measurable**, so refusing it forfeits nothing.

**Fixed 2026-08-17.** `market_hours.py` (leaf, zero imports) holds both
predicates; `_is_blocked` is a thin call to `is_entry_allowed`. `MARKET_CLOSE`
is left in place, marked dead, as the evidence.

---

## 24. id=941 — a closed trade with no recorded outcome
*(added 2026-08-17 — recorded, NOT fixed)*

`trades` id **941**: USDCAD, opened Sun 2026-08-09 21:52:16, `status='CLOSED'`
at 21:53:28 — **72 seconds later** — with **`pnl` NULL and `close_price`
NULL**.

**It is unique.** Of **915** CLOSED trades, it is the **only** one with a NULL
`pnl`. (The other three NULLs in the table are `status='OPEN'`, which is
correct.) So this is not a systemic gap in the close path; it is one row that
lost its outcome.

**Context, not yet explanation:** it sits inside the thin Sunday reopen window
of finding 23, alongside the five trades that were stopped out within two
minutes at full risk. It is plausibly the same event — an instant
spread-triggered stop — that additionally failed to record a fill price. The
deferred P&L checker gives up after 24 hours, so nothing will retry it now.

**Why it is recorded rather than patched:** a closed trade with no recorded
outcome is a **hole in the ledger**, and the ledger is the only evidence base
for every promotion decision. Inventing a plausible P&L for it would be the
`resolved_at` mistake in a worse place. It should be understood, then either
recovered from IG transaction history (`scripts/reaudit_close_prices.py` is the
existing tool) or explicitly marked unrecoverable — not silently filled.

Note for whoever picks this up: two other rows have a `close_time` **one second
EARLIER** than their `timestamp` (id 728: 21:15:55 → 21:15:54; id 845:
20:35:45 → 20:35:44). Negative holding periods. Both are thin-reopen trades
too. Same neighbourhood, possibly the same clock/ordering defect.

---

## 25. id=824 EXPLAINED — a single anomalous tick, and the guard that cannot catch it
*(added 2026-08-18 — supersedes finding 3's root-cause account and closes the
ig_scale-at-write-sites item)*

### The scoped item was built on a premise that does not hold

An item was carried for several sessions to "add `ig_scale` conversion at the
four paper write sites". **It should not be built, and the reasoning behind it
was wrong on three counts.**

1. **The guards already exist, at every path that fills a candle buffer.** All
   landed in `839aeee` (2026-07-09):

   | path | guard | conversion |
   |---|---|---|
   | `_mid_ohlc` (live ticks) | `is_resolved` :400 | `to_decimal` :408-409 |
   | `_rest_fetch` (REST warm-up) | `is_resolved` :219 | `to_decimal` :236-239 |
   | `_yfinance_fallback` | n/a | n/a — yfinance is natively decimal |
   | loop's stale-fallback `_fetch_yfinance_candles` | n/a | n/a — natively decimal |

   The four write sites read `candle["close"]/["high"]/["low"]` out of that
   buffer, which is already decimal. **Adding `to_decimal` there would
   DOUBLE-CONVERT** — dividing an already-decimal EURUSD price by 10,000 a
   second time. The proposed fix was worse than the defect.

2. **The dates rule the story out.** id=824 is `2026-07-21`, **twelve days
   after** those guards shipped, with EURUSD inside `CHECKED_SYMBOLS`.
   Finding 3's account — "the paper-trade path has no `ig_scale` conversion" —
   is true as literally stated but is **not the cause**, because the prices it
   receives were already converted upstream.

3. **The risk-source half was also a non-issue.** The resolver already calls
   `get_risk_per_trade(symbol, is_paper=True)`, and that function returns
   `RISK_PER_TRADE` **before** consulting `RISK_PER_TRADE_OVERRIDE` — paper
   risk deliberately ignores per-symbol overrides, which CLAUDE.md documents
   as intended. Not a missing call.

### What actually happened — recovered from `candle_source_compare`

The comparison logger stores every cycle's stream close against the yfinance
reference. It recorded the event directly:

```
2026-07-21T19:05:32  yf=1.1406410932540894  stream=1.14032   delta_pips=3.21
2026-07-21T19:20:32  yf=1.140380859375      stream=11402.0   delta_pips=-114008596.19   <-- HERE
2026-07-21T19:35:31  yf=1.1406410932540894  stream=1.14026   delta_pips=3.81
```

**One cycle. One tick. Points-scale, unconverted, straight into the buffer.**

The full sequence:

1. `ig_scale` had EURUSD classified as **`divisor = 1.0`** — and that
   classification was **correct**. Verified live 2026-08-18: REST
   `snapshot.bid` for `CS.D.EURUSD.MINI.IP` is **1.1578**, decimal, and
   `_classify` returns 1.0 for it.
2. At 19:20:32 the Lightstreamer stream delivered a tick valued **11402.0** —
   points scale, disagreeing with the REST snapshot that classification was
   based on.
3. `to_decimal` with `divisor = 1.0` is a **no-op**. The value entered the
   `(EURUSD, 15MIN)` buffer unchanged.
4. The comparison logger noticed — `delta_pips = -114,008,596` — **and nothing
   alerted on it.** It was written to a table and never read.
5. The signal loop reads `candles[-2]`, not `candles[-1]`. So the poisoned
   19:15 candle was *not* acted on in the cycle that ingested it. **Fifteen
   minutes later it aged into the `candles[-2]` slot**, `bb_squeeze` signalled
   on it, and `entry=11403.2 / sl=11400.7 / tp=11408.2` was written as id=824.

That last step is why the row looks isolated and inexplicable: the corrupted
candle and the corrupted row are **one cycle apart**, and at 19:35 the
*latest* candle was healthy decimal again. Anyone checking the buffer at the
moment of the write would have found nothing wrong.

### Why `is_resolved` / `to_decimal` structurally cannot catch this

**Classification succeeded and was right.** There was no ambiguity, no
`PriceScaleAmbiguous`, no unresolved symbol, no alert — the guard did exactly
what it was designed to do. The design assumes **one scale per (account,
epic)**, sampled once from the REST snapshot and applied to every
Lightstreamer tick. It has no answer for the two endpoints disagreeing for a
single tick.

> **The gap, stated generally: `ig_scale` validates the SCALE, never the
> VALUE.** `_EXPECTED_DECIMAL_RANGE` already encodes what a plausible decimal
> price is for every checked symbol — it is consulted at classification time
> and never again. A post-conversion band check in `_mid_ohlc` would have
> dropped this tick on arrival for the cost of one comparison.

### Breadth — measured, not assumed

- **1 anomaly in 19,852 `candle_source_compare` rows**, spanning
  2026-07-08 → 2026-08-18. That single row is the one above.
- **1 out-of-band price in 1,623 `paper_trades` rows** (id=824).
- **0 out-of-band prices in 918 `trades` rows** — no live order was ever
  placed on a points-scale price. The `candles[-2]` delay is a plausible part
  of why: a one-cycle poisoning has to survive 15 minutes and then produce a
  signal.

So this is genuinely rare, was never a live-money event, and does not justify
a broad refactor. It justifies **one cheap band check**.

### ⚠️ Collateral finding — the EURUSD points-scale quirk is NOT currently in effect

CLAUDE.md's Price scale quirk section states that `CS.D.EURUSD.MINI.IP`
quotes in native points scale (`bid=11423.3`) on DEMO account Z67Y2C.
**Measured 2026-08-18, that is no longer true:**

| symbol | REST `snapshot.bid` | classified divisor | live stream buffer |
|---|---|---|---|
| EURUSD | 1.1578 | **1.0** | 1.15817 |
| GBPUSD | 1.35445 | 1.0 | 1.354845 |
| AUDUSD | 0.7106 | 1.0 | — |
| USDCAD | 1.38712 | 1.0 | — |
| US500 | 7740.36 | 1.0 | 7746.9 |

**Every symbol classifies to `divisor = 1.0`, so the entire `ig_scale`
conversion layer is currently a no-op.** It is doing nothing except the
classification check — which is precisely why the one anomalous tick passed
through untouched.

Two consequences worth holding:

- The quirk was real when documented (every pre-2026-07-08 EURUSD trade is
  decimal, every post-switch one was points), so **the scale changed under us
  at least twice**. `init_price_scales(force=True)` on session recreate exists
  for exactly this and should stay.
- **Do not delete `ig_scale` as dead weight** because it currently converts
  nothing. Its value is the classification and the raise-on-ambiguity, and the
  account has already demonstrated it can flip.

### Recommended fix — NOT built here

A post-conversion band check in `_mid_ohlc` (and `_rest_fetch`), reusing
`_EXPECTED_DECIMAL_RANGE`: if the converted close falls outside the symbol's
plausible decimal band, **drop the tick and alert** rather than buffer it.
Cheap, uses a table that already exists, and would have caught this on arrival
instead of 15 minutes later in a paper row.

It is a **live-path change** — `_mid_ohlc` feeds live entry prices and the
SL/TP actually sent to IG — so it needs its own commit, its own permission and
its own verification. Recorded here, deliberately not bundled.

Related and still open: `is_resolved` returns `True` for any symbol outside
`CHECKED_SYMBOLS` (finding 20's fail-open shape on the conversion path).

---

## 26. The `ig_scale` conversion layer is currently a NO-OP — and the docs say otherwise
*(added 2026-08-18 — outranks finding 25, which is one symptom of it)*

**Measured live on DEMO account Z67Y2C, 2026-08-18:**

| symbol | REST `snapshot.bid` | classified divisor | live stream buffer |
|---|---|---|---|
| EURUSD | 1.1578 | **1.0** | 1.15817 |
| GBPUSD | 1.35445 | **1.0** | 1.354845 |
| AUDUSD | 0.7106 | **1.0** | — |
| USDCAD | 1.38712 | **1.0** | — |
| US500 | 7740.36 | **1.0** | 7746.9 |

**Every checked symbol classifies to `divisor = 1.0`. `to_decimal` and
`to_native` currently divide and multiply by one.** The entire conversion
layer is arithmetically inert.

### The documented quirk is not in effect

CLAUDE.md's *Price scale quirk* section asserts, in the present tense, that
`CS.D.EURUSD.MINI.IP` quotes in native points scale (`bid=11423.3`) on this
account. **It does not, and has not for some time.** The claim was true when
written — the 2026-07-08 rejections and the id=824 tick both prove points-scale
data was real — but it describes a past state.

**The scale has therefore flipped at least twice:**

1. decimal on LIVE (TW75S) — every pre-2026-07-08 EURUSD trade has a decimal
   `entry_price`
2. points on DEMO (Z67Y2C) after the 2026-07-08 switch — the quirk as
   documented
3. **decimal on DEMO now** — measured above

Nobody changed accounts between 2 and 3. **The broker changed the
representation underneath a running system**, and nothing noticed, because
`init_price_scales` re-derives on session recreate and silently produced a
different answer.

### What `ig_scale` is actually for — and why it must not be deleted

It is tempting to read "every divisor is 1.0" as "this module does nothing,
delete it." **That is exactly wrong.** Its value was never the arithmetic:

- **The classification** is what notices a flip. It is the only thing in the
  system that ever compares a price against what that price *ought to* look
  like.
- **The raise-on-ambiguity** (`PriceScaleAmbiguous` → Telegram ERROR → symbol
  blocked) is the safety property. A reading that fits neither band stops
  trading rather than guessing.
- **`init_price_scales(force=True)` on session recreate is load-bearing**, and
  transition 2→3 is the proof: a cached divisor from before a flip would be
  silently wrong afterwards, and `force=True` is the only thing that
  re-derives it.

The module is a **detector wearing a converter's clothes**. Judge it on
whether it would catch the next flip, not on whether it currently multiplies
by anything.

### Consequence for finding 25

The single anomalous tick passed through untouched *because* `divisor = 1.0`
made `to_decimal` a no-op. Had the account still been in points-scale mode,
the same anomalous tick would have been divided by 10,000 and buffered as
`1.1402` — plausible, in-band, and **completely undetectable**. The no-op
state is what left the bad value visibly wrong.

That is worth sitting with: **the current configuration is the one in which
this class of fault is most visible.** A band check (finding 25's recommended
fix) is what makes detection independent of which mode the account happens to
be in.

---

## 27. Write-only sinks — the detector that fired and went unheard
*(added 2026-08-18 — audit, nothing fixed)*

Finding 25's anomaly was **caught perfectly, in real time, by an existing
control**:

```
2026-07-21T19:20:32  EURUSD 15MIN  yf=1.140380859375  stream=11402.0
                     delta_pips = -114,008,596.19
```

`candle_source_compare` recorded it the moment it happened, with a magnitude
no human could misread. It then sat in the table for **28 days** while the
corrupted row it produced was investigated twice and written up with the wrong
root cause.

**This is the unverified-controls class (finding 9) inverted.** Finding 9 is
about a control that never fired and whose silence was mistaken for success.
This is a control that **fired correctly and had no listener**. Both fail the
same way — nobody learns anything — but this one is worse value for money,
because the detection work was already done and paid for.

> **A detector with no consumer is not a control. It is a log.**

### Audit — every table, writers vs readers

| table | writers | readers | rows (VPS) | verdict |
|---|---|---|---|---|
| `candle_source_compare` | 1 | **0** | **19,859** | **write-only** |
| `correlation_events` | 1 | 1 *(dead)* | **3,732** | **write-only in practice** |
| `walkforward_runs` | 1 | 0 | 0 | write-only; also empty on VPS (finding 11) |
| `webhook_outcome_log` | 1 | 1 | 179 | read by dashboard page 10 |
| `backtest_trades` | 1 | 1 | 2,608,572 | read by dashboard page 04 |
| `positions` | 1 | 2 | 3 | fine |
| `signal_log`, `paper_trades`, `trades`, `active_strategy`, `heartbeat`, `webhook_log`, `backtest_results`, `active_strategy_history` | — | ≥2 | — | fine |

**Two genuine write-only sinks, and the second is worse than the first.**

**`correlation_events` — 3,732 rows, and `get_correlation_events()` is defined
but has ZERO callers.** CLAUDE.md is explicit that this table exists to
"measure frequency before deciding whether to build blocking logic (Tier 4
prerequisite)". The measurement ran for 27 days (2026-07-22 → 2026-08-18) and
produced **3,341 SELL clusters against 391 BUY** — a nearly 9:1 skew that is
exactly the sort of thing the decision was waiting on. **The decision has
never been made, because nobody read the data it was waiting for.**

A partial mitigation exists: the correlation check also sends a Telegram INFO
alert, so the events were not literally invisible. But a per-event alert is
not an aggregate, and 3,732 alerts over 27 days is closer to noise than to a
finding.

### Log files — better, but check the direction

| file | writer | reader |
|---|---|---|
| `logs/watchdog_alerts.jsonl` | `scripts/watchdog.py` | ✅ `scripts/daily_summary.py` |
| `logs/ledger_reaudit_*.jsonl` | `scripts/reaudit_close_prices.py` | none — acceptable, it is an audit artifact for humans |

`watchdog_alerts.jsonl` is the pattern to copy: written by one process,
**consumed by a scheduled summary that a human actually receives**.

### The general rule

> **Every detector needs a named consumer at the time it is built** — a
> dashboard panel, a summary line, or an alert threshold. "We will query it
> when we need it" is how 19,859 rows and 3,732 rows both became invisible.
> If no consumer can be named, the honest options are to not build it, or to
> write down explicitly that it is a passive archive nobody watches.

**Nothing fixed here.** The obvious candidates — an anomaly threshold on
`candle_source_compare`, and an aggregate of `correlation_events` on a
dashboard page — are both small, but they are decisions about what to watch,
not mechanical fixes.

---

## Standing rule — when to bump a model stamp

Three stamps now exist: **`engine_version`** (backtest trade model),
**`paper_model`** (paper resolver outcome model), **`spread_model`** (the cost
parameterisation). All three answer the same question — *are these two rows
comparable?* — so all three take the same test:

> **Would two runs over the same row and the same candles produce a different
> result?**
> **Yes → bump. No → do not bump.**

Nothing else decides it. Not the size of the diff, not how many files changed,
not whether the change feels significant, and **never a commit SHA** — a SHA
changes on commits that cannot move a number, which makes it useless for the
one question the field exists to answer.

Worked example, the paper-v1 → **paper-v2** bump (Stage 2):

| Change | Same row + same candles → different result? | Bump? |
|---|---|---|
| Window derived from signal time instead of a tail trim | **Yes** — different bars decide the outcome, so WIN can become LOSS (finding 22) | **Yes** |
| Terminal outcomes `EXPIRED` / `NO_HISTORY` / persistent `REFUSED` | **Yes** — rows that v1 would eventually have booked as WIN/LOSS now terminate elsewhere, changing every aggregate's denominator | **Yes** |
| `resolved_at` column added | **No** — pure metadata, no outcome or P&L moves | No |
| Log wording, comments, refactors | **No** | No |

The bump is carried by the first two. `resolved_at` rides along in the same
commit because the schema is being touched anyway — **riding along in a
versioned commit is not the same as justifying the version**, and conflating
the two is how stamps drift into meaning "something changed", which is not a
useful thing for a stamp to mean.

### Related standing rule — where misclassification costs are asymmetric, the default goes to the cheap side

Recorded alongside the stamp rule because it decided the shape of the paper-v2
fix and this codebase has repeatedly defaulted the other way.

When code must classify something it cannot always identify — is this error
permanent or transient, is this signal real or noise, is this row countable —
**the two mistakes rarely cost the same, and the unrecognised case must land on
whichever side is cheaper to be wrong about.**

Applied in `_classify_fetch_error`: structural failures are an **allowlist**,
and anything unrecognised falls through to transient.

| mistake | cost |
|---|---|
| transient classified as structural | a resolvable row is killed permanently |
| structural classified as transient | a dead row retries until it EXPIRES |

The second is bounded and self-correcting; the first is not. So the default is
transient — *even though* that is precisely the behaviour that let finding 22's
`AttributeError` retry for 40+ days. The fix is not to flip the default, it is
to name the structural cases explicitly.

The codebase's habitual direction is the opposite, and each instance cost
something: `.get(symbol, 1.0)` returning a plausible value-per-point rather
than raising (finding 16, 97 rows at 1/2000th value); `status` defaulting to
the permissive branch (finding 4); the VIX filter failing open. The rule is not
"always fail closed" — a VIX API blip should not halt trading. It is that the
direction must be **chosen from the cost asymmetry and stated**, not inherited
from whichever default was easiest to write.

Corollary: a stamp bump is **not** a quality claim. `parity-v2` takes profit
and `parity-v1` does not, but neither is calibrated (see the spread residual).
The stamp says *incomparable*, never *better*.

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
| Quarantine id=824, re-baseline | finding 2 | Includes correcting CLAUDE.md. **Framing per finding 22**: outcomes taken as given AND demonstrably wrong for an unmeasurable subset — must appear in the commit message and script comment, not only in the findings file |
| Resolution window + terminal outcomes | finding 22 | Derive window from signal time; REFUSED / EXPIRED / NO_HISTORY distinct from transient failure; `resolved_at` forward-only |
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
