# Operations Log — dated records moved out of CLAUDE.md

Split out 2026-09-02. CLAUDE.md had reached 204,375 chars and every dated
check, deploy and rehearsal was appending to it.

**This file is the SOLE COPY of everything in it.** It was moved here, never
duplicated — CLAUDE.md is not a superset of it and the findings doc does not
contain it. Each section left a stub in CLAUDE.md saying where it went and why
it mattered.

Verification records, deploy records and rehearsal results. Diagnoses of
defects live in `docs/SESSION_20260812_FINDINGS.md`; standing rules learned
from them stay in CLAUDE.md under Unverified Controls.

---

<!-- moved from CLAUDE.md 2026-09-02 -->

## Backtest Engine Parity — Stage 1 (2026-08-16)

Four commits: `e0f51f8` marking → `14c3c17` sizing → `0fdbe7e` contract →
`36fac3b` spread capture. Driven by the AUDUSD hard gate resolving Branch B:
the backtest was modelling a different strategy from the one running live.

### engine_version — three versions, what each means
`engine_version.py` (repo root, zero imports). Versions the trade model's
**structure**. Bump only if two runs of the same strategy over the same candles
would produce different trades or different P&L. **Never commit SHAs.**

| version | meaning |
|---|---|
| `pre-parity-v0` | Everything before 2026-08-16. No take-profit for 21 of 34 strategies, $15 risk vs live $10, no SL floor, SL exits booked at a flat `-RISK`. **History, never evidence.** All 268,117 VPS rows and 276 local `walkforward_runs` rows carry this. |
| `parity-v1` | Sizing only. Floor applied, risk via `get_risk_per_trade`, clamp order matched to live, unsizeable trades aborted, SL booked from the actual stop price. **Half-fixed — still no TP. Generate no evidence at v1.** |
| `parity-v2` | **Current.** The `sl_price`/`tp_price` contract. |

`get_backtest_results()` filters to the current version by default;
`engine_version=None` reads all (archive/inspection only — dashboard page 04).
`score_strategies()` raises `MixedEngineVersionError` rather than ranking
across models.

### parity-v2 — what the engine now does
- **Three-branch contract** mirroring `live_signal_loop.py:552`. Neither price
  supplied → `DEFAULT_TP_R = 2.0` off the floored candle range (the *measured*
  live rule, not a guess: 569 real williams_r trades span R:R 1.941–2.040,
  median exactly 2.000). Both supplied → **passed through unchanged**, so the
  13 emitters keep their own designs including the three that aren't
  R-multiples. Exactly one → `EngineContractError`, raised not logged.
- **`MIN_SL_DIST` floor** imported from `instrument_limits.py` — one source
  shared with the live path, never a copy.
- **Honest sizing**: `get_risk_per_trade(symbol)`, round-then-clamp, abort when
  unsizeable.
- **SL exits booked from the actual stop price**, `exit_price` recording
  `sl_price`.
- **Exit ladder**: `sl_stop`/`tp_hit` are intrabar and outrank
  `max_hold`/`signal`, which are evaluated at the bar's close.
  `intrabar_priority` default **`"sl"`** (pessimistic — and the more likely
  resolution, since a 1R stop is nearer than a 2R target). `ambiguous_bars`
  reported on every run: measured 0.0–1.8% of trades.
- **`reversal_exit` default `False`**, matching live FX which has none.

### ⚠️ The entanglement finding — why this hid for months
**TP and reversal exit mask each other. Neither change alone explains the
result**, so neither would have shown up in isolation. AUDUSD 15MIN:

```
v1 baseline: no TP, reversal ON     n=391  net=$512.46  PF=1.246  tp_hit=0
+TP only     (reversal still ON)    n=388  net=$476.69  PF=1.241  tp_hit=57
reversal OFF only (still no TP)     n= 17  net=$122.59  PF=1.723  tp_hit=0
v2: TP + reversal OFF               n=221  net=$124.45  PF=1.085  tp_hit=82
```
TP alone barely moves PF — the reversal exit was already closing positions
before the target. Reversal-off alone is degenerate — without a TP a position
has almost no way to close. **Only together do they resemble live.**

### Where the numbers stand — converging, still flattering
| | AUDUSD PF |
|---|---|
| Live demo actual (51 post-cap clean trades) | **0.71** |
| `parity-v1` | 1.246 |
| `parity-v2` | **1.085** |

**Spread is the known remaining residual.** Still not promotion evidence.

### Spread — capture live, model deliberately unchanged
`trades.spread` was 906 NULLs from **one hardcoded `None`** in
`live_signal_loop`; column, write path and aggregation query all existed.
Now captured from two sources, both costing **zero extra IG calls**:
`execute_trade.last_spread` (the quote `place_trade` already fetches) and
`candle_stream.get_spread()` (BID/OFR already arrive on every tick and were
being averaged away). Per-check sampling gives 96–480 observations/symbol/day
vs ~1/symbol/day from trades alone.

**The flat `SPREAD_COSTS` constant is deliberately LEFT IN PLACE and named,
not deleted** — removing it would make every backtest look better while being
no more correct. Every result row now carries `spread_model`
(`flat-roundtrip-dollars-UNCALIBRATED`) and `spread_table_sha`, because
`engine_version` versions structure while spread is a *parameter*, and a name
can be kept while numbers change underneath it.

Use `get_spread_samples()` to read samples — it collapses to one observation
per `(symbol, minute)`. Raw `signal_log` rows carry ~1.75× duplication,
unevenly (EURUSD 480 checks/day vs AUDUSD 96).

### ❌ What is still NOT modelled after Stage 1
Out of scope for the entire parity sequence, still divergent from live:

| row | mechanic | live | engine |
|---|---|---|---|
| 1 | entry price | deals at `offer`/`bid` | candle close |
| 2 | entry lag | fills 25–55 min after the signal candle | close of the signal bar |
| 16 | weekend | blocks Sat, Sun until 23:00, Fri from 20:45 | only where data has gaps |
| 17 | session window | per-strategy windows | one hardcoded 13:30–21:00 UTC |

Plus spread until commit 5. **`parity-v2` is the first version that takes
profit at all — it is not yet a faithful execution model.**

### Uncalibrated-parameter findings (see docs/SESSION_20260812_FINDINGS.md)
Three instances of the same pattern, all recorded and **none fixed**:
`SPREAD_COSTS` (the engine constant), **finding 14 `MIN_SL_DIST`** (drives
sizing on 45–55% of FX entries, IG's `minNormalStopOrLimitDistance` never read
back), and **finding 15 `NORMAL_SPREADS`** (see the correction below).


---

<!-- moved from CLAUDE.md 2026-09-02 -->

## Engine parity work — caveats to carry forward (2026-08-16)

### ⚠️ The 36/36 contract result is NOT full coverage
`EngineContractError` enforces "emit BOTH `sl_price` and `tp_price`, or
NEITHER". Checked across every strategy module on real candles: **zero
violations, 13 emit both, 21 emit neither.**

**But `orb` and `first_bar_breakout` produced ZERO signals on the test
candles**, so they are contract-**untested**, not contract-clean. Nothing was
observed either way for those two. The first real run that makes them fire is
the first test of their compliance — if one of them emits only one price, it
will raise at that point, and that is the check working, not a regression.
Do not read "36/36" as proof all 36 are compliant.

(Count is 36 rather than 34 because it includes the untracked working-tree
strategies `liquidity_sweep` and `first_bar_breakout`.)

### ⚠️ `score_strategies()` returning `[]` is ambiguous — resolve before re-arming
`get_backtest_results()` filters to `CURRENT_ENGINE_VERSION`. After each
version bump there are zero rows at the current version until the gauntlet is
regenerated, so `score_strategies()` returns `[]` rather than raising. That is
correct — an empty single-version set is legitimate, not a mixed-model error —
and it is harmless **only because the selector is inert at both layers**.

The hazard is for whenever the selector is re-armed: from the outside,
**"no candidates at this engine_version" and "selector working but idle" look
identical.** Both produce silence, no rows written, no error. That is the same
absence-is-not-evidence trap as the cron disable (see Unverified Controls).

Before re-arming, make the two states distinguishable — e.g. have the selector
log explicitly when the candidate pool is empty *and why* (zero rows at
`engine_version=X`), so a silent selector can be told apart from a starved one
by a positive signal rather than inferred from nothing happening.


---

<!-- moved from CLAUDE.md 2026-09-02 -->

## ✅ CONTROLS AWAITING FIRST REAL FIRE — THE LIST IS NOW EMPTY

Every control that was waiting on a first production fire has now been observed
firing, each with a positive signal rather than inferred from silence. **Keep
this section**: an empty list is a claim, and the dates below are what backs it.

| control | deployed | first real fire | `signal_log.error` string |
|---|---|---|---|
| FX weekend block | 2026-08-17 | ✅ **Sat 2026-08-22** | `market closed — weekend` |
| 21:00 rollover gate | 2026-08-21 | ✅ **Sun 2026-08-23**, weekday case **Mon 2026-08-24** | `entry window closed — daily rollover hour` |
| collector disable → IG warm-up | 2026-08-23 | ✅ **Mon 2026-08-25 04:02 UTC** | `source=IG REST` in the warm-up log |
| shadow spread gate | (before 2026-08-21) | ✅ **Mon 2026-08-25 04:04 UTC** | `SHADOW spread gate: ratio ...` |

**The shadow gate's first fire**, caught on the first cycle after the
2026-08-25 deploy:

```
SHADOW spread gate: ratio 0.250 >= k 0.25 (GBPUSD, spread=0.00015, sl_dist=0.0006)
```

It fired on a **paper** signal, exactly as designed — `risk/spread_gate.py`
sits before the paper/live branch — and **the trade still logged as
`PAPER_BUY`.** That is the passing observation: `ENFORCE=False` means the gate
reports and blocks nothing. The standing rule is unchanged and now has a
baseline to read against: this string must never be the sole explanation for a
*missing* trade while `ENFORCE` is False.

Nothing is currently awaiting a first fire. **Add a row here before deploying
the next dated control, not after** — the value of this table is that it was
written while the control was still unobserved.


---

<!-- moved from CLAUDE.md 2026-09-02 -->

## ✅ CHECK 3 — PASSED 2026-08-25. The warm-up reaches IG. `CANDLE_SOURCE=ig_stream` is true end to end for the first time.

Both claims now have evidence. The second one was the whole point of the
change, and it took two days and an allowance reset to become observable:

| claim | status | evidence |
|---|---|---|
| the collector no longer runs | ✅ **VERIFIED 2026-08-23 14:31 UTC** | marker test, below |
| `candle_stream` warm-up now reaches IG instead of yfinance | ✅ **VERIFIED 2026-08-25 04:02 UTC** | 7/7 pairs `source=IG REST`, zero fallback |

**The observation, exactly as it was predicted before it was made** (the
passing string was written into this file on 2026-08-23, before the run):

```
[candle_stream] warm-up US500/15MIN: 200 candles (source=IG REST)
[ig_allowance] candle_stream REST US500/15MIN: remaining=9000 of 10000 (10.0% used),
               resets_at=2026-09-01T04:02:18+00:00 (expiry=604798s)
```

All seven warm-up pairs returned `source=IG REST`. **Zero
`source=yfinance (quota fallback)` lines, zero quota errors, on the whole
start-up.** That log line is only producible by IG actually serving the
request.

**The collector was the blocker, and the fix working is what proves it.** Until
2026-08-23 the collector took 100,800 points/week of a 10,000/week budget,
exhausted it in ~16.7 hours, and left `_warm_up` and `_backfill_gap` falling
through to yfinance on every pair for the rest of the week. `CANDLE_SOURCE=ig_stream`
was half true — IG ticks, **yfinance seed data**. Stop the drain, let the
allowance reset, and the warm-up reaches IG on the first attempt. That is the
causal claim tested rather than argued.

**This deploy was a legitimate CHECK 3 observation, not a self-manufactured
one** — per the distinction drawn when the check was written. The deploy was
scheduled for its own reasons (gated on CHECK 2, code waiting since 2026-08-23),
and `source=IG REST` cannot be faked by restarting: only IG serving the request
produces it. Contrast CHECK 1's criterion 4, where a restart *did* manufacture
an artifact resembling the passing state.

### ✅ The reset time is now KNOWN — 2026-09-01T04:02 UTC

`resets_at=2026-09-01T04:02:18+00:00 (expiry=604799s)` — a rolling 7-day window
that begins at the first request after a reset, **not** a fixed weekly boundary.

This number was **arriving on every successful `/prices` response for the life
of the system and was discarded** by both consumers doing
`result.get("prices")`. Finding 35 made it visible; this is the first time it
has ever been read. Before 2026-08-23 the reset time was simply unknown, and
every plan that depended on it was a guess.

⚠️ The window is anchored to the first request after a reset, so it **moves**.
Do not hardcode 04:02 as a recurring weekly time — read `resets_at` off the
next successful response.

**Marker test result (positive signal, not silence).** A one-shot cron line was
added in the same edit that commented the collector, scheduled 6 minutes out,
`%` escaped as `\%`:
- it **fired at `2026-08-23T14:31:01Z`** → cron was alive and had re-read
  `/etc/cron.d/trading-bot` after the change;
- the `*/15` collector run due at **14:30 did not fire** — `candles.log` stayed
  at 243 lines with mtime `14:15:04`, its last pre-edit write.

Cron demonstrably working and reading that exact file in the same window, so
the 14:30 no-show is a real disable rather than a dead daemon. Marker line
removed immediately after observation; in-container md5 back to the committed
value.

*(The prospective reasoning that stood here — why the second claim could not be
checked before the reset, what PASSING would look like, and why the
post-CHECK-2 deploy would be a legitimate rather than self-manufactured
observation — has been folded into the result block above. It was all correct
and the prediction held exactly, which is the argument for writing such things
before the run rather than after.)*

### ⚠️ The rebuild cost DOUBLE the prediction — 2,800 points, not 1,400

This section predicted `WARMUP_COUNT` 200 x 7 pairs = **1,400 points, ~14% of
the weekly 10,000**. The measured cost was **2,800 points, 28%** — fourteen
REST calls, not seven. Gap-backfill fires immediately after warm-up, re-fetches
200 points per pair, and leaves the buffer at the same 200 candles warm-up had
just produced. **Zero gained, 1,400 spent, on every reconnect.**

That is **finding 37**, and it is scoped there but deliberately **not fixed** —
it is being kept separate from the post-reset measurement work. Read it before
planning any allowance budget: at 2,800 points per restart the weekly allowance
funds **three** of them.

### ⛔ The two unknowns are STILL UNMEASURED — the probe exhausted the allowance

The instruction above ("measure the two unknowns promptly rather than letting
the rest drain on reconnects") was followed on 2026-08-25, and the probe
designed to do it **consumed the remaining ~7,200 points and measured neither.**

Root cause is a single unchecked assumption — *a request that fails is a
request that was free*. It is not: `numpoints=100000` and `50000` came back
`error.price-history.io-error`, **not** a quota error, meaning IG attempted and
charged them. By the third request a **four-bar** date-range window was being
refused. Full account, and the general rule it produced, in **finding 38** and
in the Unverified Controls section below.

Still unknown, now until after 2026-09-01T04:02 UTC:
1. **Max `numpoints` per request** — bracketed only as "attempted, IO error, at
   50,000+". No accepted value has ever been measured above 200.
2. **How far back `MINUTE_15` reaches per epic** — entirely unknown. The
   index-backfill sizing (~17,000 points per index symbol) remains a guess.

**When the allowance resets, probe from the SMALLEST request upward**, reading
`allowance.remainingAllowance` off each response before escalating. A one-hour
date-range window is four bars. Do not bracket from above.

### 🔴 LIVE EXPOSURE until 2026-09-01T04:02 UTC — bounded, no action available

The historical allowance is at zero for a week. Stated honestly rather than
minimised:

- **Live trading is unaffected in steady state.** Lightstreamer ticks do not
  draw on the historical allowance. Buffers were warmed from IG REST during the
  2026-08-25 deploy, and both heartbeats, the cycle cadence and paper signal
  firing were all confirmed healthy afterwards.
- **The exposure is a stream reconnect.** If the stream drops before the reset,
  `_warm_up` / `_backfill_gap` fall back to yfinance — which **for indices is
  the off-session staleness the 2026-07-15 `CANDLE_SOURCE` flip existed to
  fix.** FX fallback is comparatively benign; US500/US100 is the real risk.
- **No action is available.** The allowance cannot be refilled early, and
  restarting to re-warm would itself need the allowance. The only mitigations
  are not restarting the container and not running historical fetches. Both are
  already the case.
- **This is a self-inflicted, one-week window.** Recording it rather than
  discovering it later, per the same rule that governs undocumented backups and
  re-opened drift.

CHECK 1 **passed on 2026-08-22 and in full on 2026-08-23** — the control is
verified. One of its four criteria was found to be mis-specified and re-scoped
to Sunday; that is a defect in the checklist, not in the control. **CHECK 2
passed on 2026-08-24** and **CHECK 3 on 2026-08-25.** All three are closed.

Delete none of these sections. A control recorded as verified when it never
fired is the same error as a monitoring gap recorded as outstanding while the
monitor existed — and the dated result blocks are what distinguish the two.


---

<!-- moved from CLAUDE.md 2026-09-02 -->

## ✅ CHECK 1 — FX market-hours block (deployed 2026-08-17) — VERIFIED IN FULL 2026-08-22/23

`_is_blocked` never blocked FX. `MARKET_CLOSE` holds only US500/US100/DAX/BTC,
so every FX symbol hit `.get(symbol) is None → return False` before reaching
any weekend rule. **21 weekend trades were placed as a result**, at exactly the
timestamps where measured spread is 10–17 pips. Fixed by `market_hours.py`
(`is_market_open` = venue fact, `is_entry_allowed` = our policy);
`_is_blocked` is now a thin call. Findings doc finding 23.

**THE FIRST REAL WEEKEND AFTER THIS DEPLOY IS THE ACTUAL TEST.** Everything
verified so far used *constructed* timestamps. This control has never once
fired for FX in production, so — per the marker-test rule in Unverified
Controls — its silence proves nothing on its own.

**That Saturday is 2026-08-22.** Confirm all three:

1. FX symbols log `BLOCKED` in `signal_log` with reason
   `market closed — weekend` (not the old `near market close`)
2. **Zero** FX entries in `trades` over the weekend
3. The `signal_loop` heartbeat kept beating through a fully-blocked cycle
   (`upsert_heartbeat` is outside the per-symbol loop, but prove it, don't
   infer it)

Also confirm spread sampling **continues** while blocked — `signal_log.spread`
non-null on FX rows during the blocked window. The sample is taken before the
block check and the blocked branch still calls `log_signal_check`; that
ordering is load-bearing and commented as such, because the thin reopen is the
most expensive window we have and the one we least want to go blind on.

### ✅ OBSERVED Sat 2026-08-22 05:27 UTC — CONTROL WORKS. VERIFIED.

> **READ THIS FIRST.** One of the four criteria below is marked as not met.
> **That is not a defect in the control.** The block itself is confirmed
> working on every criterion that tests it. Criterion 4 was *mis-specified*
> when it was written — it asked for an observation that is impossible on a
> Saturday for reasons unrelated to the block, and it has been re-scoped to
> Sunday. Do not read "criterion 4 failed" as "the weekend block is broken."
> It is not, and the evidence for that is criteria 1–3 plus the trade count.

**Status: FX weekend block is VERIFIED IN PRODUCTION.** First real weekend
after the deploy, and the first time this control has ever fired for FX.

- **Positive control:** 266 `signal_log` rows exist on 2026-08-22, so the loop
  was running and the test genuinely ran.
- **Criterion 1 PASS.** All 266 rows carry `signal='BLOCKED'` and
  `error='market closed — weekend'` — exactly that string, nothing else, and
  all four FX symbols present: EURUSD 116, GBPUSD 44, AUDUSD 22, USDCAD 22
  (plus US500 40, US100 22).
- **Criterion 2 PASS.** Zero `trades` rows on 2026-08-22. This is the control
  that had never once fired for FX before 2026-08-17 — 21 weekend trades were
  placed under the old code.
- **Criterion 3 PASS.** `signal_loop` heartbeat current (05:25:59) through
  fully-blocked cycles.
- **Criterion 4 — NOT A FAILURE OF THE CONTROL. The criterion was
  mis-specified.** Nothing about the weekend block is in question here; this
  criterion tests the *spread-sampling ordering*, which is a different
  mechanism that happens to have been bundled into the same checklist.
  `signal_log.spread` is **NULL on all 266 rows**. This is NOT the load-bearing
  ordering failing. The ordering is correct — the sample is still taken before
  the block check. There is simply **nothing to sample**: the Lightstreamer
  stream disconnects at the Friday close (`candle_stream` heartbeat last beat
  `2026-08-21T22:00:00`), so `get_stream_spread` has no quote and correctly
  returns `None`. A spread from a shut book is not a quote anyone could have
  traded on — which is exactly what `market_hours.is_market_open` exists to say.

**The criterion conflated two different blocked windows**, and as written it
would have reported a false failure every Saturday:

| blocked window | venue | stream | spread expected |
|---|---|---|---|
| Saturday, all day | **shut** | down | **NULL — correct, nothing to sample** |
| Sunday 20:00–22:59 UTC reopen | **open** | up | **non-NULL — this is the real test** |

The load-bearing ordering only matters where the venue is open and *we* decline
to enter. That is the Sunday reopen, not Saturday. **Re-test criterion 4 on
Sunday 2026-08-23 between 20:00 and 22:59 UTC**: FX `signal_log` rows should
carry `error='entry window closed — thin reopen / pre-weekend policy'` **with
`spread` non-null**. If spread is NULL *there*, the ordering has genuinely
broken.

This is the self-invalidating-probe rule applied to a written check: on
Saturday the probe cannot observe the passing state at all, so its negative
carried no information about the thing it claimed to test.

### ✅ CRITERION 4 RE-TESTED AND PASSED — Sun 2026-08-23 20:00–22:59 UTC

**CHECK 1 IS NOW VERIFIED IN FULL.** The Saturday NULL was the shut book,
exactly as diagnosed — not the ordering failing.

- **Positive control:** 144 `signal_log` rows, `20:11:02` → `22:56:03`, all
  four FX symbols (EURUSD 63, GBPUSD 24, AUDUSD 12, USDCAD 12) plus US500 21,
  US100 12. The loop was running; the test genuinely ran.
- **Reason strings: 144/144 `BLOCKED`**, every row an exact expected string,
  zero NULL, zero others.
- **Spread: 111 of 111 FX rows NON-NULL**, 37/37 in each of hours 20, 21, 22.
  The load-bearing ordering holds — sample taken before the block check, and
  the blocked branch still calls `log_signal_check`.
- **Zero `trades` rows** in the window and across all of 2026-08-23; zero
  `trade_placed=1`.
- **14 unbroken cycles** at 15-minute cadence through fully-blocked cycles.
  `heartbeat` is an upsert, so past beats are unrecoverable — the row
  timestamps are the durable evidence here, not the heartbeat table.

**The captured spreads are why the policy exists.** First reopen sample per
symbol: **GBPUSD 0.0026 (26 pips)**, AUDUSD 0.0013, USDCAD 0.00133, EURUSD
0.00019. GBPUSD ran **wider than the 10–17 pip range quoted elsewhere in this
file** — raise that upper bound when the spread table is built.

### 🔴 CORRECTION — the rollover gate fires at 21:xx on SUNDAY

Surfaced by this check, contradicting CHECK 2's table below:

| hour (Sun 2026-08-23) | reason logged | rows |
|---|---|---|
| 20 | `entry window closed — thin reopen / pre-weekend policy` | 48 |
| **21** | **`entry window closed — daily rollover hour`** | **48** |
| 22 | `entry window closed — thin reopen / pre-weekend policy` | 48 |

CHECK 2 asserts Sunday 21:30 is blocked by *"the **Sunday reopen** rule
(23:00), not this one"*. **Wrong — the rollover branch wins the ordering in
`_block_reason`.** Two consequences:

1. **The 21:00 rollover gate has ALREADY had its first real fire** — real
   clock, 2026-08-23 21:00–21:59 UTC, 48 rows — a day earlier than CHECK 2
   said was reachable.
2. That table's reasoning was argued, never observed. Same shape as every
   conclusion-by-argument this file warns about. Do not re-derive the ordering
   from it.

**What ABSENCE would mean.** Zero FX rows carrying `market closed — weekend`
on Saturday is **not** evidence the block works — it is equally consistent with
the loop not running at all. Positive control first: confirm `signal_log` has
**any** rows on 2026-08-22. Rows present and none carrying the reason → the
block is broken. No rows at all → the loop was down and the test did not run;
reschedule, do not conclude. (`candle_stream`'s heartbeat legitimately goes
quiet at weekends — `watchdog.check_heartbeat` early-returns outside
Sun 22:00 – Fri 21:00 UTC — so a silent candle_stream is the gate working, not
a fault. `signal_loop` should keep beating.)

Until that observation exists, this control is verified only against
constructed timestamps.


---

<!-- moved from CLAUDE.md 2026-09-02 -->

## ✅ CHECK 2 — 21:00 UTC rollover gate (deployed 2026-08-21) — VERIFIED IN FULL 2026-08-24

> ### ✅ THE GATE HAS FIRED ON A REAL CLOCK — Sun 2026-08-23 21:00–21:59 UTC
>
> **48 `signal_log` rows** carrying `entry window closed — daily rollover hour`,
> found while re-testing CHECK 1's criterion 4. **This is no longer a
> first-exercise check.** Monday still runs — see "What Monday still tests"
> below — but read the correction first, because the reason the gate was
> thought unreachable until Monday is more instructive than the gate itself.

`market_hours.is_entry_allowed` refuses entries in the 21:00 UTC hour, **all
instruments**, checked before the `_ALWAYS_OPEN` short-circuit so BTC is
covered. Rationale, evidence table and the DAX/BTC-are-mechanism-not-evidence
caveat live in the `market_hours.py` comment; do not restate them here.

**Marker verification: 33 assertions in the deployed image, all against
CONSTRUCTED `datetime` values.** Superseded by the real-clock fire above; kept
because the constructed assertions are still what pins the boundary minutes.

### 🔴 THE CORRECTION — and HOW the claim was wrong

This table stood here until 2026-08-24. The Sunday row was **false**:

| | `is_entry_allowed` | `is_market_open` | who blocks |
|---|---|---|---|
| Fri 2026-08-21 21:30 | False | **False** | venue already shut |
| Sat 2026-08-22 21:30 | False | False | venue shut |
| Sun 2026-08-23 21:30 | False | True | ~~the **Sunday reopen** rule (23:00), not this one~~ → ❌ **OBSERVED: THIS GATE.** 48 rows logged `daily rollover hour` |
| Mon 2026-08-24 21:30 | False | True | this gate — ~~first genuine exercise~~ **not first; see below** |

**The claim was ARGUED, NEVER OBSERVED — and it was not even argued from the
code.** Both relevant functions check the rollover **first**, and both say so
in a comment:

- `market_hours.is_entry_allowed` tests `when.hour == ROLLOVER_BLOCK_HOUR`
  before the `weekday == 6 and hour < ENTRY_REOPEN_HOUR` reopen rule.
- `live_signal_loop._block_reason` mirrors it deliberately, commented
  *"Checked before the reopen/pre-weekend catch-all so the rollover hour is
  attributable on its own … Ordering here MUST mirror is_entry_allowed's rule
  order."*

So the code was explicit, self-documenting, and the opposite of what this file
claimed. The claim came from **which rule felt semantically dominant** — "it's
the Sunday reopen, so the Sunday rule governs" — rather than from reading
either function or watching either fire. **A conclusion reached by argument
where an observation was cheap and available.** Same shape as finding 29 and as
the self-invalidating-probe rule; this is the file's own mechanism catching the
file.

**The consolation is that it was caught by a scheduled check rather than by an
incident**, and caught only because CHECK 1 criterion 4 grouped `signal_log`
rows by hour instead of asserting a single expected string. A check that
matched only the reason it expected would have passed and taught nothing.

### What Monday 2026-08-24 21:00–21:59 UTC still tests

Not a first fire. Three things the Sunday observation genuinely does not cover:

1. **`is_market_open` is True for a different reason.** Sunday it is True
   because the venue reopened at 22:00; Monday it is True as an ordinary
   trading day. The gate is reached through a different path.
2. **The Sunday reopen rule is not also live.** On Sunday both rules would
   have blocked, so the observation shows which one *reports* — not that the
   rollover gate blocks anything the reopen rule would have let through.
   Monday is the first hour where **this gate is the only thing** standing
   between a due signal and an entry.
3. **Criterion 1's exact-string test is now the interesting part**, and its
   meaning is unchanged: the pre-weekend string appearing in hour 21 means the
   ordering has drifted. That test was correct all along — it is the
   *prediction table* that was wrong, not the criterion.

### ✅ VERIFIED Mon 2026-08-24 21:00–21:59 UTC — ALL SIX CRITERIA PASSED

**The weekday case is confirmed. CHECK 2 is closed.** Queried
`2026-08-25` from the durable `signal_log` rows (`checked_at`, ISO with `T`,
`+00:00`), every criterion run as an enumeration and the distribution reported
before the verdict, per ENUMERATE, DON'T ASSERT.

- **Criterion 0 — positive control PASS.** 48 rows, `21:10:46` → `21:55:41`,
  all six symbols: EURUSD 21, GBPUSD 8, US500 7, AUDUSD 4, US100 4, USDCAD 4.
  The loop was running; the test genuinely ran.
- **Criterion 1 — reason strings PASS.** `GROUP BY symbol, signal, error`
  returned **one bucket**: all 48 rows `BLOCKED` /
  `entry window closed — daily rollover hour`, the exact string. Zero rows
  carry `thin reopen / pre-weekend policy`, zero NULL, zero others. The
  ordering in `_block_reason` has **not** drifted from `is_entry_allowed`.
- **Criterion 2 — spread PASS.** 48/48 non-null, indices included. The
  load-bearing ordering holds: sample taken before the block check, blocked
  branch still calls `log_signal_check`.
- **Criterion 3 — zero entries PASS.** Zero `trades` rows in hour 21 and zero
  across all of 2026-08-24; all 48 rows `trade_placed=0`; zero `paper_trades`
  in the hour. **Reinforced by a second positive control: 58 `paper_trades`
  rows exist elsewhere on 2026-08-24**, so the loop demonstrably produced
  entries that day and the hour-21 absence is the gate acting, not a dead loop.
  Without that row the criterion's absence would have carried no information.
- **Criterion 4 — cadence PASS.** Unbroken 15-minute cycles across the window
  from the durable row timestamps, not the heartbeat upsert: 20:10 / 20:25 /
  20:40 / 20:55 → **21:10 / 21:25 / 21:40 / 21:55** → 22:10 / 22:25 / 22:40 /
  22:55. No gap.
- **Criterion 5 — all six symbols PASS, and the indices MATCH FX.** US500 (7
  rows) and US100 (4) carry the identical error string and non-null spreads.
  US500's 7 vs US100's 4 is the extra 21:30 cycle where US500 and EURUSD were
  `_is_due` — a cadence artifact, not differing gate behaviour.

**What Monday tested that Sunday could not**, as scoped in advance:
`is_market_open` was True as an ordinary trading day rather than via the 22:00
reopen, and the Sunday reopen rule was **not** also live — so this is the first
hour where this gate alone stood between a due signal and an entry.

#### 📏 Rollover-hour spreads — measured, and the indices are the interesting part

| symbol | min | max | ~normal | ratio at max |
|---|---|---|---|---|
| **GBPUSD** | 0.00169 (16.9 pips) | 0.00169 | ~1.5 pips | ~11x |
| USDCAD | 0.00133 (13.3 pips) | 0.00133 | ~0.9 pips | ~15x |
| EURUSD | 0.00028 | 0.00116 (11.6 pips) | ~1.0 pips | ~12x |
| AUDUSD | 0.00061 | 0.00116 (11.6 pips) | ~0.6 pips | ~19x |
| **US500** | **1.5** | **1.5** | 1.5 | **~1x — flat** |
| **US100** | **5.0** | **5.0** | 5.0 | **~1x — flat** |

⛔ **THESE MUST NOT ENTER THE SPREAD TABLE.** Same exclusion as the shut-book
and Sunday-reopen samples, same reason: every row was taken while
`market_hours.is_entry_allowed` was **False**, and
`get_spread_samples(market_open_only=True)` filters on exactly that predicate.
Including them biases the median **high**. They are evidence **for** the policy,
never inputs **to** the cost model.

**The indices being flat is itself a finding, and only an all-symbols query
could show it.** FX widens 11–19x in the rollover hour; US500 and US100 do not
move at all. So **the rollover widening is an FX phenomenon**, and the gate —
which checks `ROLLOVER_BLOCK_HOUR` *before* the `_ALWAYS_OPEN` short-circuit,
deliberately covering 24/7 instruments — is **broader than the evidence base
that justifies it.**

**This is NOT a reason to narrow the gate.** Recorded because it is the kind of
thing that goes unnoticed until someone re-derives the rule from its rationale
and finds the rationale does not cover every instrument it applies to. Three
points in its favour as it stands: the index sample is small (11 rows across
one hour); an all-instruments rule has no per-symbol branch to drift; and
blocking entries in a low-liquidity hour costs little on instruments that are
not widening anyway. If the gate is ever revisited, **this measurement is the
starting point, and it needs more than one hour of index data first.**

Exactly the outcome ENUMERATE, DON'T ASSERT predicts: criterion 5 was written
to include symbols believed irrelevant, and the difference between them is
visible only because both were in the output.

---

*(The five criteria as originally written are kept below unchanged. They were
correct — including criterion 1's exact-string test, which is what would have
caught an ordering drift. It was the prediction table above them that was
wrong, and that correction is recorded in place rather than edited away.)*

### On Mon 2026-08-24, after 22:00 UTC, confirm all five

**Run every query as an enumeration, not an assertion** — see "ENUMERATE,
DON'T ASSERT". Criterion 4 of CHECK 1 found the error in *this section* only
because it grouped by hour instead of testing for the string it expected.
Report the distributions first, verdicts second.

0. **Positive control before anything else:** `signal_log` has **any** rows in
   21:00–21:59 UTC on that date. No rows means the test did not run.
1. `signal_log` rows exist in 21:00–21:59 UTC with
   `error = 'entry window closed — daily rollover hour'` — the **exact** string,
   distinct from `'entry window closed — thin reopen / pre-weekend policy'`.
   Getting the pre-weekend string instead means the rollover branch is being
   shadowed by an earlier rule and the ordering in `_block_reason` has drifted
   from `is_entry_allowed`. **Query it as `GROUP BY symbol, error`**, not as an
   equality test.
2. **Zero** `trades` rows with `substr(timestamp,12,2) = '21'` on that date.
3. `signal_log.spread` **non-null** on FX rows inside the blocked window —
   sampling must continue through the block. Same load-bearing ordering as
   CHECK 1: the sample is taken before the block check and the blocked branch
   still calls `log_signal_check`. The rollover hour is the widest-spread hour
   of the day and the single most valuable hour to keep sampling.
4. `signal_loop` heartbeat kept beating through a fully-blocked cycle.
   (`heartbeat` is an upsert, so past beats are unrecoverable — the durable
   evidence is unbroken 15-minute `signal_log` cycle timestamps across the
   window, as used on 2026-08-23.)
5. **Report what the INDICES did in that hour, not only FX.** The gate is
   all-instruments — `is_entry_allowed` checks `ROLLOVER_BLOCK_HOUR` *before*
   the `_ALWAYS_OPEN` short-circuit, specifically so a 24/7 instrument is
   covered too. US500 and US100 are in the window and log every cycle. The
   evidence base behind the rule is FX-specific, so **an index behaving
   differently is exactly the thing that would not appear in an FX-only
   query.** Enumerate all six symbols; if indices match FX, that is a result
   worth one line, and if they do not, it is the finding.

**What ABSENCE would mean — read this before concluding anything.** No rows
carrying that reason on Monday is **not** evidence the gate works. It is
equally consistent with:
- no strategy being `_is_due` during that hour (15MIN cadence, so plausible);
- the roster being all-paper — *paper strategies still reach `_check_symbol`
  and still log*, so this should not suppress it, but confirm rather than
  assume;
- the container not carrying the code.

Distinguish them with a positive control before drawing a conclusion: confirm
`signal_log` has **any** rows at all in that hour on that date. If it has rows
and none carry the reason, the gate is broken. If it has no rows at all, the
loop was not checking and the test simply did not run — reschedule, do not
conclude.

### ✅ The shadow ratio gate has fired — 2026-08-25 04:04 UTC

`risk/spread_gate.py`, `ENFORCE=False`, k=0.25. It only evaluates on an actual
BUY/SELL, so it was unexercised until a signal landed. It sits before the
paper/live branch, so a **paper** signal exercises it — and that is exactly
what happened, on the first cycle after the 2026-08-25 deploy:

```
signal_log id: GBPUSD 2026-08-25T04:04:01 PAPER_BUY
error: SHADOW spread gate: ratio 0.250 >= k 0.25 (GBPUSD, spread=0.00015, sl_dist=0.0006)
```

**The passing observation is the pairing**: the gate reported *and* the row is
`PAPER_BUY`, i.e. the trade was still taken. `ENFORCE=False` reports and blocks
nothing, confirmed rather than assumed. The ratio landed exactly on k — 0.250
against a 0.25 threshold — which is a boundary case worth knowing the gate
evaluates with `>=`.

The standing rule is unchanged and now has a baseline to read against: this
string must **never** appear as the cause of a *skipped* trade while `ENFORCE`
is False. If a trade is ever missing and this string is the only explanation,
the shadow gate has been promoted by accident.


---

<!-- moved from CLAUDE.md 2026-09-02 -->

## ✅ DEPLOY 2026-08-25 — queue SHIPPED, drift CLEARED

**The deploy queue is empty and the 2026-08-23 drift entry is closed.** Gated
on CHECK 2, which passed on 2026-08-24; shipped the following morning.

| | |
|---|---|
| running image | `sha256:9da8a7927a09`, built **2026-08-25 04:02 UTC** |
| image contains | `715bc18` — same as `origin/main` at deploy time |
| carried in | **16 commits**, `591dc3a..715bc18`, resolved from `git log` at deploy time rather than from a list |

The queue was resolved with `git rev-list --count 591dc3a..origin/main` against
the running image's commit, exactly as the previous entry instructed — **not**
from an enumerated list. That rule was written after an enumerated list went
stale within one commit, and it held: the queue had grown from 5 to 16 between
the note being written and the deploy happening.

**Runtime-reachable in what shipped:** `4323dea` (the `scripts/crontab`
collector disable, the new `ig_allowance.py`, and its two additive
`log_allowance` call sites in `candle_stream._rest_fetch` and
`engine.fetch_candles`). `40d716b`, `be0138c` and `6145779` touch the backtest
engine only — `bot/live_signal_loop.py` does not import
`backend.backtesting.engine`, so they are unreachable from the loop, webhook,
poller or execution path. Everything else is docs.

**Post-deploy verification — every item a positive observation, none inferred
from silence:**

1. ✅ in-container `/etc/cron.d/trading-bot` md5
   **`0f1cc206193f5d30341c3db530357b06`**, byte-matching the committed
   `scripts/crontab`. **This was the one that mattered most**: the collector
   disable existed in the container only as a `docker cp` (lost on rebuild per
   Unverified Controls instance 3), and this rebuild is what made it permanent.
   One active cron line, the 06:10 Stage E job.
2. ✅ **CHECK 3 PASSED** — 7/7 warm-up pairs `source=IG REST`, zero yfinance
   fallback, `[ig_allowance]` printing live. See the CHECK 3 result block,
   including the two things it cost.
3. ✅ finding 29's rule: `ig_allowance` imports, `bot.live_signal_loop` imports
   with `STRATEGIES: 34`, and `main` / `webhook.receiver` /
   `data.positions_poller` all import clean. Run **before and after** the
   deploy; the pre-deploy baseline was identical, so a post-deploy pass is a
   comparison rather than an isolated reading. `ig_allowance.py` confirmed
   present at `/app/ig_allowance.py` — a new module imported by two files in
   the loop's import graph, whose absence would stop the bot booting.
4. ✅ stamps unchanged: `parity-v2`.
5. ✅ `localhost:80` 200, `/health` 200, `/webhook` 405; all three containers up.
6. ✅ both heartbeats beating after the restart, a full cycle logged, and
   `signal_log.spread` non-null on every FX symbol. The **shadow spread gate
   fired for the first time** on the same cycle — see CHECK 2's section.

**The next deploy has no queue.** Re-verify the crontab md5 anchor above
whenever one is built; it is the check that catches a rebuild silently
reverting the collector disable.

⚠️ **Do not rebuild before 2026-09-01T04:02 UTC without a reason that
outweighs the cost.** A restart now re-warms all seven pairs against an
**exhausted** historical allowance, so every buffer falls back to yfinance —
for indices, the off-session staleness the 2026-07-15 flip existed to fix. See
the live-exposure note in the CHECK 3 section.


---

<!-- moved from CLAUDE.md 2026-09-02 -->

## ✅ DEPLOY 2026-08-22 — earlier drift CLEARED

The repo/image drift recorded here from 2026-08-21 is **resolved**. Kept as a
short record rather than deleted, because "the image matches the repo" is an
assumption every verify-the-deploy step in this file makes, and the date it
became true again is worth knowing.

| | |
|---|---|
| running image | `sha256:42f5585b3e34`, built **2026-08-22 18:07 UTC** |
| image contains | `591dc3a` — same as `origin/main` at deploy time |
| carried in | `7d6e961`, `1d3725d`, `66e4d54`, `3708a49`, plus `d6f1c8c` (finding 31 columns) and `591dc3a` (Stage 4 export/import) |

**Post-deploy verification — every item a positive observation, none inferred
from silence:**

- committed `scripts/crontab` md5 **`aea93925651e8ee24ce7d52e70b3434d`**, and
  in-container `/etc/cron.d/trading-bot` matches byte-for-byte. The disable
  survived the rebuild.
- **finding 29's rule**: `bot.live_signal_loop` imports in the deployed image,
  `STRATEGIES: 34`. `main`, `webhook.receiver` and `data.positions_poller` all
  import clean too.
- `docker exec … scripts/run_backtest.py --help` now offers **`--from-roster`
  and `--roster-db`**, which failed with `unrecognized arguments` before this
  deploy.
- stamps unchanged: **`parity-v2` / `paper-v2` /
  `flat-roundtrip-dollars-UNCALIBRATED`**.
- `localhost:80` 200, `/health` 200, `/webhook` 405. All three containers up.
- both heartbeats beating after the restart (`signal_loop` 18:09:18,
  `candle_stream` 18:08:32), a 15-key cycle logged, and `signal_log.spread` is
  **non-null on AUDUSD (0.00053) and USDCAD (0.00061)**.

⚠️ **Do not read that last spread observation as CHECK 1's criterion 4.** It is
a Saturday: the venue is shut, and those numbers exist only because the
container restart re-warmed the stream from a **closed book**. Pre-deploy the
same column was NULL on all six symbols for the whole day. It proves the
sampling path survived the deploy — nothing more. Criterion 4 still needs the
**Sunday reopen**, per the CHECK 1 result block.

⚠️ **The restart burned IG historical-data quota** re-warming every buffer:
`error.public-api.exceeded-account-historical-data-allowance` on GBPUSD/15MIN,
USDCAD/15MIN, US100/15MIN, US500/15MIN and US500/HOUR, all falling back to
yfinance. Expected, deduped per the 2026-07-16 cooldown, and self-clearing —
but a weekday rebuild pays this cost during live hours, so prefer weekends.

Note for anyone probing a deployed container: `python3 -c "import
webhook.receiver"` **creates a fresh IG session on import** (documented gotcha).
Three such probes in a row on 2026-08-22 produced three session recreations and
a run of `[ig_scale] market fetch failed` lines on the FX epics. That is the
probe's own cost, not a fault in the deploy — but it is a real cost, so probe
imports sparingly.


---

<!-- moved from CLAUDE.md 2026-09-02 -->

## Stage 4 DRESS REHEARSAL — one strategy, 2026-08-23

AUDUSD 15MIN `williams_r`, `--from-roster --roster-db ./roster.db` against a VPS
snapshot (`git_head 591dc3a`, host `trading-bot`, 31 rows). Run before Stage 4
so that anything surprising surprises us on one strategy rather than thirteen.
It did.

**Wall clock: 1 minute 46 seconds**, against a 27-minute estimate — roughly 15x
faster. Breakdown, all four stages sequential on 29,995 candles:

| stage | duration | persisted |
|---|---|---|
| single backtest | ~1 s | 1 `backtest_results` row |
| walk-forward | ~2 s | 1 `walkforward_runs` row |
| permutation (200 synthetic runs) | 70 s | 1 row |
| stability map, 84 cells + MC top-5 | 33 s | 84 + 5 rows |

Plus ~1 min for export → scp → import → read-back → re-import. **The 27-minute
figure should not be carried into Stage 4 planning.** Thirteen strategies is
minutes, not hours — which changes what is worth parallelising (nothing) and
removes the main argument for running a reduced gauntlet.

### ✅ BOTH REHEARSAL DEFECTS FIXED — commit `40d716b`, 2026-08-23

The two findings below were fixed and the rehearsal re-run end to end before
Stage 4. Kept in full because *what they were* is the reusable lesson.

- **Cells now persist the moment they are produced**, via an `on_cell` callback
  on `run_stability_map`. Verified by interrupting a sweep at 25s: **72 of 84
  cells survived**, all with windows. Pre-fix that number is 0 by construction.
- **Cells now store the full per-window list.** Verified by reconstruction, not
  by presence: all 84 cells reproduce their stored `median_pf` and
  `pct_profitable` from their stored windows using the engine's own median rule
  — on the local DB and again after import on the VPS. A column that cannot
  rebuild the verdict it sits next to is decorative; this one is not.
- **No `engine_version` bump, and that was checked rather than assumed**: the
  re-run returns the identical verdict distribution (FRAGILE 22 / MARGINAL 12 /
  REJECT 50) and the identical single-backtest figure. Persistence changed, the
  trade model did not.
- **Cost: 1m46s → 1m48s**, export file 61 KB → 200 KB.
- `neighbor_avg_pf` is merged in after the sweep (it is a property of a cell's
  neighbours and cannot exist when the cell is written) via
  `models.update_walkforward_extra`, which **merges rather than replaces** so it
  can never drop `params_source` or an import stamp.

**✅ The permutation row's windows were fixed too** (2026-08-23). It stores the
REAL walk-forward's per-window breakdown, so **both legs of the row are now
checkable from the row alone**: `median_pf` rebuilds from `windows_json`
(1.0784, exact), and `percentile` rebuilds from `synthetic_median_pfs` (100.0,
exact). The 200 synthetic runs' windows are deliberately NOT stored — their unit
of analysis is the distribution of medians, which `extra_json` already carries in
full, and 200 window lists would bloat the row for nothing.

`monte_carlo` rows still carry `windows_json` NULL, correctly: a bootstrap
resamples a P&L list and has no windows to record.

**The pre-fix rehearsal rows are KEPT AND MARKED, not deleted** — 91 rows on
each of local and VPS now carry `extra_json.superseded_by` and
`superseded_reason`. Their verdicts are correct and reproduce exactly in the
replacement batch; what they cannot do is show the windows that produced them.
That distinction is the whole point, and deleting them would erase the evidence
that the defect existed.

### 🔴 FINDING 1 (fixed) — the stability map persisted in a BATCH AT THE END

`run_stability_map()` computes all 84 cells, returns, and only then does
`run_backtest.py` loop over `stability["cells"]` calling `_persist_wf_run`.
Measured: computation 03:59:00 → 03:59:29, **all 84 rows written 03:59:29 →
03:59:32**. Nothing is durable until the whole map finishes.

**This is the walkforward_runs gap one layer up.** That table exists because the
2026-07-15 AUDUSD verdict was console-only and is now unrecoverable. Persisting
at the end reintroduces exactly that exposure: a crash, an OOM, a Ctrl-C or a
laptop sleep at cell 80 of 84 loses all 84 cells' work with no partial record
and no way to tell how far it got.

At 33 seconds for AUDUSD this is survivable. **It is the wrong shape for a
13-strategy batch**, and it is the one stage where the fix matters, because it
is also the most expensive stage. Every other stage already persists as it
produces: the `--sweep` walk-forward writes inside its loop, and the auto-MC
writes inside its loop. Only the map defers. Fix is to persist per cell inside
`run_stability_map`'s loop, or to yield cells — **not done here**, recorded so
Stage 4 does not run 13 strategies on this shape by default.

### Also found

- **🔴 FINDING 2 (fixed) — `windows_json` was NULL on all 84 stability cells.**
  `run_stability_map` stored `windows` as a COUNT, so a cell recorded its
  verdict, median PF and pct-profitable but not the per-window breakdown that
  produced them. That is precisely the detail whose absence made the 2026-07-15
  AUDUSD result unrecoverable — reproduced, in the table built to prevent it, on
  the stage that generates 84 verdicts at a time rather than one.
- **`STABILITY_GRIDS` contains ONLY `williams_r`.** A 13-strategy Stage 4 would
  emit **12 `REDUCED_GAUNTLET` markers** and one real stability map. The marker
  mechanism works (verified below), so this is not silent — but "Stage 4 ran the
  full gauntlet" would be true of one roster row out of thirteen.
- **The VPS `walkforward_runs` table had ZERO rows** before this import. All 280
  local rows were local-only. Finding 11's corpus split was total for that
  table, not partial.
- **`export_roster.py` run INSIDE the container records `git_head = NULL`** —
  `git` is not installed in the image and `/app` is not a work tree. Run it on
  the VPS **host** (read-only access to the DB works fine as `ubuntu`); only
  writes are blocked. A roster snapshot with a NULL git_head is the
  no-provenance case the script exists to prevent.

### ⚠️ parity-v2 makes the AUDUSD stability picture materially WORSE

Same 84-cell grid, same cache, roster params — but under `parity-v2` rather
than the pre-parity engine whose numbers this file records elsewhere:

| verdict | pre-parity (recorded above) | **parity-v2 (this run)** |
|---|---|---|
| ROBUST | 1 | **0** |
| FRAGILE | 38 | 22 |
| MARGINAL | 34 | 12 |
| REJECT | 11 | **50** |

**REJECT goes from 11 of 84 to 50 of 84, and the single ROBUST cell is gone.**
Best cell is `period=10, oversold=-95, overbought=-20`, median PF 1.2022, 66.7%
windows — FRAGILE, not ROBUST. The correction in Active Strategies that already
downgraded "robust plateau" to "one robust point in a mostly-fragile field" now
goes further: under the current engine there is no robust point at all.

Consistent with the rest: the single backtest reproduced this file's documented
parity-v2 figure **exactly** — `n=221, net=$124.45` — so the engine is behaving
as recorded. Walk-forward on the full cache: **FRAGILE**, median PF 1.0784,
50.0% of windows profitable, 585 trades, worst window PF 0.83. Permutation:
real result at the **100.0th percentile** of 200 synthetic runs under
`seed=42`, EDGE CONFIRMED — the signal is not noise, it is a real but fragile
edge that the demo record (PF 0.71 live) says is not currently profitable after
costs.

⚠️ **State that as "at the resolution floor", never as "100%".** At
`n_iter=200` the p-value floor is 0.00498, so 100.0 means only *no synthetic run
beat the real one* — it cannot separate a result at the 99.6th percentile from
one at the 99.99th. The unseeded runs that preceded it gave 98.5 and 99.0 (2 and
1 synthetics above the real result). **All three are the same claim at this
resolution**; the spread is the tail noise the floor exists to warn about, not
disagreement.

**Seeding history, kept as the evidence for finding 32.** Before 2026-08-23 both
`permutation_test` and `bootstrap_mc` ran `seed=None` and stored no seed, so
re-running the identical gauntlet on identical candles moved the percentile
98.5 → 99.0 and every MC cell. Both now REQUIRE an explicit seed
(`UnseededRunError` otherwise), store it on the row, and stamp
`reproducible: true/false`. `--seed` defaults to 42, so reproducibility is the
default rather than an option.

Verified both ways, because **a seed that changes nothing is as broken as no
seed**: same seed twice → all 200 synthetic medians identical and every MC
distribution field equal; different seed → both move. Separately the
*deterministic* stages were confirmed deterministic — two independent stability
maps agreed on **84/84** cells for verdict, median PF and pct-profitable.

Monte Carlo on the top-5 plateau cells reports **risk of ruin 67.3%–84.3%**
(`seed=42`, reproducible) at
$10 risk on a $500 account. That is the $500 planning account, not the demo
account — see the Phase-5 Sizing Reference for why the demo cannot produce a
ruin event — but it is far worse than the pre-parity ruin table's 5.58% at the
same fraction, and that table is explicitly flagged there as needing
regeneration under the fixed engine. **This is that regeneration's first data
point, and it says the old table was optimistic by more than an order of
magnitude.**

### Mechanisms confirmed working (positive observations, not silence)

- **MC stamp hardening refuses an unstamped trade list.** `bootstrap_mc` with no
  `engine_version` → `UnstampedTradesError`; with `pre-parity-v0` → refuses to
  resample across trade models; with `parity-v2` → accepts and stamps the
  result. All three branches exercised, including the passing one.
- **`REDUCED_GAUNTLET` marker persists when a grid is missing.** Forced with
  `bb_squeeze` (no `STABILITY_GRIDS` entry): one `stability_map` row, verdict
  `REDUCED_GAUNTLET`, carrying `engine_version`, `spread_model`,
  `spread_table_sha`, full cache fingerprint, and
  `extra_json.params_source = "roster:active_strategy.id=24"`.
- **Every stage stamps correctly**: all 91 rows `parity-v2` /
  `flat-roundtrip-dollars-UNCALIBRATED` / `1ca5c7cb03b2ccc2`, zero rows with a
  NULL `cache_file`.
- **Round trip to the VPS**: 1 `backtest_results` + 91 `walkforward_runs`
  exported, imported, read back with `produced_on = LAPTOP-6PF6QIRR` and
  `roster_snapshot.git_head = 591dc3a` intact; **re-import inserted 0, skipped
  92.** Idempotent on production.

### Operational sequence the rehearsal established

The VPS `database/trades.db` is **root-owned**, so:

```

# VPS host — backup works (read-only source), and git_head resolves here
python3 scripts/export_roster.py --out /tmp/roster.db
python3 -c "import sys;sys.path.insert(0,'.');from scripts.import_stage4 import backup_target;backup_target('database/trades.db','/home/ubuntu/backups')"

# import must run IN the container — same file via the ./database volume
docker cp /tmp/stage4_<stamp>.db trading_bot-bot-1:/tmp/
docker exec trading_bot-bot-1 python3 /app/scripts/import_stage4.py     --file /tmp/stage4_<stamp>.db --target /app/database/trades.db --no-backup --confirm
```

`--no-backup` is correct **only** because the host took one first. Record it in
the Database Backups table in the same change.


---

<!-- moved from CLAUDE.md 2026-09-02 -->

## Infrastructure Incidents
2026-08-15: Selector-disable deploy (commit 9e5f21a). `run_daily` 06:00 cron
permanently disabled in `scripts/crontab`; Stage E added at 06:10;
`SYMBOL_BLOCKLIST` widened to all three selector symbols. Rebuild verified by
marker test, not by absence. **Open positions at the time: 937 EURUSD, 939
AUDUSD (both 2026-08-07 williams_r SELLs), 964 GBPUSD, 965 USDCAD (both opened
2026-08-14 14:00 UTC).** 938 and 954 from the earlier handoff had closed by
then — the roster churns, never carry a hardcoded position list forward.

2026-07-02: Found stale systemd service (tradingbot.service) running
since Apr 12 alongside Docker container — both sharing same IG account,
same DB, same repo. Duplicate signal loop was firing live trades on
stale Apr-12 code for 3+ months undetected. Process killed, systemd
service disabled. Docker-only policy confirmed — no systemd services
should run the bot.


---

<!-- moved from CLAUDE.md 2026-09-02 -->

## Completed ✅
- Phase 1A: SQLite database + table schemas
- Phase 1B: Streamlit dashboard (4 pages)
- Phase 1C: Docker Compose on VPS (3 containers)
- Phase 1D: Nginx remote access live
- Phase 2A: Live trade logging → database
- Phase 2B: Positions poller + close detection
            Consecutive empty counter, deal_reference
            match, timezone fix, deferred P&L checker
- Phase 3:  Backtesting engine complete
- Phase 4:  11 strategies built and backtested
            yfinance as default data source
            connors_rsi2 added (daily bars only — not active)
- Phase 5:  Strategy Selector complete
            active_strategy unique on symbol+timeframe
            Morning cron auto-selects best per symbol+TF
- Phase 6:  Daily Automation complete
            bot/live_signal_loop.py — unified loop,
            timeframe-aware, wakes every 5min
            scripts/run_daily.py — 6am UTC cron
            scripts/sync_ig_trades.py — self-contained,
            duplicate-safe IG import
            dashboard pages 01-08 complete
            signal_log table — heartbeat monitoring
            paper_trades table — forward test tracking
            Source labels: swiftalgo/signal_loop/manual/ig_import
            Active HOUR live: US500 stoch_rsi, US100 stoch_rsi
            Active HOUR paper: DAX rsi, BTC vwap_ema
            Active 5MIN paper: US100 stoch_rsi

---


---


## 📏 Spread table — gate re-verification and measurement run, 2026-09-03

Dated detail for the CLAUDE.md GATE section, which carries the standing
conclusion and the six medians. This is the run; the numbers are current state
and live there.

**Pass A of two: measured and frozen, NOT applied.** `engine.py` untouched,
`CURRENT_ENGINE_VERSION` unchanged, `CURRENT_SPREAD_MODEL` still
`flat-roundtrip-dollars-UNCALIBRATED`, `SPREAD_COSTS` untouched. The stamp must
keep describing what the engine actually does or every row written between
pass A and pass B is mislabelled.

Produced by `scripts/build_spread_table.py`, run in the bot container against
the VPS DB (`signal_log` exists there only — finding 11). No IG request issued.

**Frozen bounds:** `SINCE=2026-08-16T00:00` inclusive, `UNTIL=2026-08-29T00:00`
exclusive — two complete Mon–Fri cycles. `SINCE` reaches into Sunday 08-16
deliberately: entry is permitted from 23:00 Sunday, so those rows are inside
the cost model's domain, while the excluded 20:00–22:59 reopen ramp is dropped
by the filter rather than by the bounds.

**Filter:** `get_spread_samples(market_open_only=True)` →
`market_hours.is_entry_allowed`. Never `market_open_only=False` for
calibration.

### Gate, enumerated per symbol — all six PASSED

| symbol | n | first | last | permitted hours present | weekdays |
|---|---|---|---|---|---|
| EURUSD | 917 | 2026-08-16T23:01 | 2026-08-28T20:35 | 23/23 | Mon–Fri (+Sun) |
| GBPUSD | 908 | 2026-08-16T23:01 | 2026-08-28T20:36 | 23/23 | Mon–Fri (+Sun) |
| AUDUSD | 907 | 2026-08-16T23:01 | 2026-08-28T20:36 | 23/23 | Mon–Fri (+Sun) |
| USDCAD | 896 | 2026-08-16T23:01 | 2026-08-28T20:36 | 23/23 | Mon–Fri (+Sun) |
| US500 | 1074 | 2026-08-16T23:10 | 2026-08-28T20:35 | 23/23 | Mon–Fri (+Sun) |
| US100 | 906 | 2026-08-16T23:11 | 2026-08-28T20:35 | 23/23 | Mon–Fri (+Sun) |

Hours present on every symbol: `[0..20, 22, 23]`. Criterion 1's specifically
named hours 18/19/20/22 — the ones that were empty on 2026-08-17 — are all
present. **Hour 21 absent on all six, by construction, not as a gap** (the
script asserts its ABSENCE and would flag its presence as a rollover-gate
change). Criterion 3's ≥480 cleared by 1.9–2.2x on every symbol.

Per-hour counts, EURUSD as the representative shape (the others match within a
sample or two):

```
{0:41, 1:40, 2:40, 3:40, 4:40, 5:40, 6:38, 7:39, 8:40, 9:40, 10:40, 11:40,
 12:40, 13:41, 14:41, 15:40, 16:41, 17:41, 18:41, 19:41, 20:39, 22:33, 23:41}
```

Hour 22 is the thin one on every symbol (32–37 against ~40) and the reason is
structural, not thin data: Sunday 22:00 is inside the excluded reopen ramp and
Friday 22:00 is after the weekly close, so only Mon–Thu contribute — 8 days
across the window rather than 10.

`Sun` appearing in the weekday set is the Sunday 23:00–23:59 permitted window,
not reopen-ramp contamination.

### The measurement

| symbol | n | median (price) | median (readable) | p90 | max |
|---|---|---|---|---|---|
| EURUSD | 917 | 0.00006 | 0.60 pips | 0.00006 | 0.00027 |
| GBPUSD | 908 | 0.00009 | 0.90 pips | 0.00009 | 0.00054 |
| AUDUSD | 907 | 0.00006 | 0.60 pips | 0.00009 | 0.00036 |
| USDCAD | 896 | 0.00013 | 1.30 pips | 0.00021 | 0.00084 |
| US500 | 1074 | 0.6 | 0.60 index points | 0.6 | 0.6 |
| US100 | 906 | 2.0 | 2.00 index points | 2.0 | 2.0 |

`p90` and `max` are context only and are not in the table. **The tail is
uncalibrated and risk-of-ruin work must not use this table.**

`spread_table_sha = c0c905fc6c071dd4`

### Reproducibility, verified rather than asserted

The script was run three times. All three printed the identical dict and the
identical sha — **and the live pool grew between the runs** (samples after
`2026-09-03T18:13` entered `signal_log` while they were executing). That is
what makes it a real reproducibility check rather than a repeated read of a
static table: the bounds, not the quiet, are what pinned the result.

### Two observations outside the criteria

1. **US500 and US100 have ZERO dispersion in the window** — median = p90 = max,
   exactly 0.6 and 2.0 on every one of 1,074 and 906 samples. That is not a
   market distribution; it is a broker-fixed spread on the index CFDs during
   permitted hours. It sits consistently beside CHECK 2's rollover-hour
   measurement (US500 flat at 1.5, US100 flat at 5.0), which reads as a second
   fixed tier rather than a widening. **Consequence for pass B: for the two
   indices the "median" carries no information about variability, because there
   is none to carry — any tail work on them needs a different data source, not
   a higher percentile of this one.**
2. **EURUSD median = p90** (both 0.00006), so 90% of the pool sits at the
   floor. The FX distributions are extremely tight inside permitted hours;
   all four have max/median ratios of 4.5–6.5x, entirely in the last decile.

### Why hour 21 is not waited for

Recorded here because it is the second instance of CRITERIA AGE AGAINST THE
SYSTEM THEY MEASURE and the criterion was already re-scoped on 2026-08-31: the
21:00 rollover gate sets `is_entry_allowed` False for the whole hour, all
instruments, and that is the exact predicate the filter uses. No amount of
accumulation can produce an hour-21 sample in a market-open-filtered pool.

---


## 📏 parity-v3 — measured spread applied to prices, 2026-09-04

Dated detail. The standing conclusion, the version meaning and the residual
live in CLAUDE.md and `engine_version.py`.

Pass B of two. Pass A measured and froze the table (2026-09-03) without
applying it; this applies it, flips `CURRENT_SPREAD_MODEL` to
`measured-2026-09-median`, and bumps `CURRENT_ENGINE_VERSION` to `parity-v3`.

### STEP 0 — the price-series identity, and why it is a RESIDUAL not a finding

The symmetric half-spread application is only correct if the vendor caches
carry a **mid**. `candle_source_compare` was the available evidence:
`delta_pips = (yf_close - stream_close) / pip_size`, and `stream_close` is
explicit mid — `(BID_CLOSE + OFR_CLOSE)/2`, `candle_stream.py:551-560`. So a
bid series should read −1.0× its half-spread on every symbol, an ask series
+1.0× on every symbol.

**First cut was contaminated and it had to be found before the numbers meant
anything.** The comparison differences `yf_candles[-2]` against
`stream_candles[-1]` — *different bars* — so it carries a price-drift term.
Measured: the median timestamp gap is 0 minutes on FX but the mean is 24–43
minutes, and on the indices the median gap is 390–510 minutes. Restricting to
rows whose two timestamps are **identical** removes the drift term:

| symbol | n (same-timestamp) | mean delta | half-spread | ratio |
|---|---|---|---|---|
| AUDUSD | 2451 | **+2.434 pips** | 0.30 | **+8.1×** |
| EURUSD | 3182 | **+3.209 pips** | 0.30 | **+10.7×** |
| GBPUSD | 3345 | **+0.340 pips** | 0.45 | **+0.76×** |
| USDCAD | 2840 | **−0.935 pips** | 0.65 | **−1.44×** |

**The signs disagree and the magnitudes span 0.76×–10.7×.** Neither the bid
hypothesis nor the ask hypothesis fits: both predict one sign on all four and
a ratio near 1.0. What the data actually shows is symbol-specific **vendor
price-level differences**, and on EURUSD and AUDUSD those are an order of
magnitude larger than the spread this commit models.

**Verdict: INDETERMINATE.** Mid assumed, symmetric application, recorded as a
named residual in the `parity-v3` History entry and the commit message rather
than assumed silently.

**The larger implication, which is NOT fixed here:** on EURUSD and AUDUSD the
backtest corpus differs from tradeable IG prices by more than the cost this
commit adds. Spread parity is now modelled; **price-level parity is not**, and
it is the bigger number of the two.

US100 excluded from the verdict as instructed (its ~100-pip divergence is
documented off-session yfinance staleness). US500/US100 are shown above only
in the timestamp-gap measurement, where their 390–510 minute median gaps are
themselves the reason they cannot contribute.

### STEP 3 — reconstruction, AUDUSD 15MIN williams_r

Identical candles (`AUDUSD_15MIN_AV.json`, 29,995), identical params
(`period=14, oversold=-85, overbought=-20`, roster id 34), identical seed 42.
"Before" was run from a clean `git archive HEAD` tree so the comparison is
against real pre-change code, not a remembered number.

**Direction predicted before running: costs rise, so PF must fall.** Old
AUDUSD cost was a flat $0.60 per round trip; the measured 0.6-pip spread at
typical sizing is ≈$1.00.

| | parity-v2 | parity-v3 |
|---|---|---|
| trades | 221 | **234** |
| win rate | 37.1% | **34.2%** |
| **profit factor** | **1.0849** | **1.0431** |
| net profit | $124.45 | **$66.03** |
| max drawdown | $149.61 | $169.99 |
| Sharpe | 0.0388 | 0.0198 |

PF −3.9%, net profit −47%. **The parity-v2 figure reproduces CLAUDE.md's
recorded AUDUSD parity-v2 PF of 1.085 exactly**, which is independent evidence
the baseline tree is the right one.

Trade count *rose* (221 → 234) rather than falling. That is the fill shifting
the SL/TP anchors and the exit ladder evaluating against the crossed side, so
different bars trigger — not merely the same trades costing more.

Walk-forward at parity-v3: median PF 1.0514, 66.7% windows profitable, 607
trades over 6 windows, **MARGINAL**.

### Stamps, checked on the written row rather than in the code

That column was NULL on every row ever written until 2026-08-22 and
code-reading missed it, so both were read back after writing:

```
backtest_results id=5332   engine_version=parity-v3
                           spread_model=measured-2026-09-median
                           spread_table_sha=c0c905fc6c071dd4
walkforward_runs id=554    engine_version=parity-v3
                           spread_model=measured-2026-09-median
                           spread_table_sha=c0c905fc6c071dd4
```

`UnmeasuredSpreadError` verified by positive signal on all six unmeasured
symbols (DAX, USDJPY, EURGBP, NZDUSD, XAUUSD, BTC) and end-to-end: a real
`--symbol DAX` backtest aborts with it rather than silently using the old
constant.

---

## 📏 Spread-table dispersion, the 09-03 reconnect, and the date-banner misread

Three pass-A observations, dated detail. Standing conclusions in CLAUDE.md.

### 1. US500 and US100 have ZERO dispersion — a posted tier, not a distribution

In the frozen pool (2026-08-16 → 2026-08-29, market-open filtered), median =
p90 = max on both indices: **0.6 on all 1,074 US500 samples and 2.0 on all 906
US100 samples.** Not one sample differs.

That is a broker-posted spread, not a market distribution. It matches CHECK 2's
rollover-hour measurement, which found the same two symbols flat at 1.5 and
5.0 while FX widened 11–19× — i.e. IG posts **two fixed tiers** on the index
CFDs and switches between them, rather than quoting a varying book.

**Consequence: no percentile of this pool can ever give the indices a tail.**
p99, p999 and max are all 0.6 and 2.0 by construction. An index tail needs a
different data source — tick-level quotes, or the rollover/reopen tiers treated
as the tail rather than derived from one.

FX is the opposite shape: EURUSD's median equals its p90 (0.00006), and all
four pairs carry max/median ratios of 4.5–6.5× entirely inside the last decile.

### 2. The 2026-09-03 16:06 reconnect — the discriminating observation

The change-1 burn window could not test the fix: it contained **zero
disconnects**, and `_backfill_gap` only runs from `_reconnect_supervisor`, once
per connect. A pre-change container would have burned zero in that window too.

A real reconnect then happened, unprompted:

```
2026-09-03T15:59:53Z  [candle_stream] disconnected — will reconnect
2026-09-03T16:06:52Z  [candle_stream] connected
```

Seven minutes down, two backoff steps. On reconnect, enumerated:

- **6 pairs FETCHED** — AUDUSD/EURUSD/GBPUSD/US100/US500/USDCAD 15MIN, each
  `buffer now 355 (source=IG REST)`, i.e. genuinely stale after seven minutes
  and correctly *not* skipped.
- **1 pair SKIPPED** — US500/HOUR, `buffer current — newest bar is 0 bucket(s)
  back`. The HOUR bucket had not turned over.
- Meter: 9,980 → 8,780 = **1,200 points**, against **1,400** pre-change.

**This closes the ordinary-gap case for change 1.** `_bars_missing` did exactly
what it was built to do on a real reconnect — skipped the one buffer that was
current, fetched the six that were not.

⚠️ **The storm case remains UNTESTED.** The 2026-08-28 failure was 511
backfills from reconnects seconds apart, against buffers a previous reconnect
had just filled. A single seven-minute outage does not exercise that path, and
nothing here should be read as if it did.

### 3. The harness date banner is not a clock

On 2026-09-03 the session context asserted the date was 2026-09-04. The spread
pool's last sample was `2026-09-03T18:00`, which against the banner reads as
**~19 hours of weekday silence** — a dead signal loop. An incident check was
started on that basis.

There was no incident. VPS and local WSL both read `2026-09-03T18:13:30Z`,
VPS NTP-synced and NTP active. The data was **13 minutes old**. The banner was
the only wrong clock in the room.

Same family as the rest of Unverified Controls: a conclusion resting on an
absence — here, absence of recent rows — where the absence was manufactured by
the measuring instrument rather than by the system. **Check freshness against a
real clock on the machine that owns the data**, never against the session's
own idea of the date.

---


## 📏 Stage 4 pre-flight — profit_factor and the residual's dispersion, 2026-09-04

Dated detail. Standing conclusions and the numbers a future decision reads are
in CLAUDE.md.

### Item 1 — `profit_factor` was a MISSING COLUMN, not a NULL one

The 2026-09-03 report said "NULL on every row". That was wrong, and the way it
was wrong is the useful part: the check was
`dict(row).get("profit_factor")`, and **`.get()` cannot distinguish an absent
key from a NULL value** — both return `None`. `PRAGMA table_info` settled it in
one call:

```
local  backtest_results: has profit_factor -> False
VPS    backtest_results: has profit_factor -> False
       walkforward_runs: median_pf         -> present since creation
```

Three-part fix, forward-only:
1. `database/db.py` — `ALTER TABLE backtest_results ADD COLUMN profit_factor REAL`,
   in the existing try/except migration idiom.
2. `database/models.py` — `profit_factor` added to the INSERT column list and
   VALUES, bound from `**result` with **no `.get()` fallback**, exactly like
   `:win_rate` and `:sharpe_ratio`. A caller that omits it must raise rather
   than write NULL, because writing NULL is how the column stayed empty.
3. `scripts/run_backtest.py` — `pf = calc_profit_factor(trades)` and
   `"profit_factor": pf` in the saved row. The SAME function the walk-forward
   path calls; no second implementation.

**Verification — two independent derivations agreeing, not absence of error.**
Fresh row `backtest_id=5333` (AUDUSD 15MIN williams_r, parity-v3):

| | |
|---|---|
| stored `profit_factor` | **1.0431** |
| derived from that row's `backtest_trades` (gross_win 1599.82 / gross_loss 1533.79, n=234) | **1.0431** |
| agree | **True** |

Row also carries `engine_version=parity-v3`,
`spread_model=measured-2026-09-median`, `spread_table_sha=c0c905fc6c071dd4`.

**Guard verified by positive signal**, not by reading the code: an
`insert_backtest_result` call omitting the key raises
`ProgrammingError: You did not supply a value for binding parameter
:profit_factor`, and no partial row was written (`_guardtest` count 0).

**Forward-only.** After the migration: 5,333 local rows, **5,332 NULL**, 1
populated. Nothing backfilled — every pre-existing row is `pre-parity-v3` and
is history, not evidence.

⛔ **The migration has NOT reached the VPS** (nothing was deployed this pass).
It must, before the Stage 4 import runs.

### Item 2 — the step-0 residual VARIES; it does not cancel

Pass B established the mean. The mean alone is consistent with two opposite
conclusions, so the second moment was the missing input. Identical-timestamp
subset, pips:

| symbol | n | mean | stdev | Q1 | Q3 | IQR | full spread | stdev/spread | IQR/spread |
|---|---|---|---|---|---|---|---|---|---|
| EURUSD | 3182 | +3.209 | 1.021 | 2.81 | 3.78 | 0.97 | 0.60 | **1.70×** | 1.62× |
| GBPUSD | 3345 | +0.340 | 1.039 | −0.09 | 0.84 | 0.93 | 0.90 | 1.15× | 1.03× |
| AUDUSD | 2451 | +2.434 | 0.750 | 2.04 | 2.84 | 0.80 | 0.60 | 1.25× | 1.33× |
| USDCAD | 2841 | −0.935 | 1.448 | −1.05 | 0.05 | 1.10 | 1.30 | 1.11× | 0.85× |

Variance decomposition: pooled stdev across all four **1.978 pips**, mean
within-symbol stdev **1.093 pips**. A constant per-symbol offset would drive
the within-symbol figure toward zero.

**Verdict: varying and material.** The bar-to-bar variation is **1.1×–1.7× the
entire spread parity-v3 models**, on every pair. EURUSD's 1.70× is the
deciding number. The offset is not a uniform shift that cancels through
differencing — it is per-bar noise landing on SL/TP trigger evaluation.

This does not invalidate parity-v3; modelling spread correctly remains
correct. It says the next parity gain is larger than the one just banked, and
that residual backtest-vs-live divergence should be attributed here first.

---


## 📏 Stage 4 batch — full run record, 2026-09-04

Dated detail. The verdict table, the three non-runs and the standing
conclusions are in CLAUDE.md.

**Batch window:** start `2026-09-04T02:10:20Z`, end `02:24:20Z` — **14 minutes
for 11 strategies x 4 stages**. Roster snapshot `/tmp/roster.db` exported on the
VPS HOST (`git_head=cc9055d`, `source_host=trading-bot`, 31 rows, taken
`02:05:47Z`), scp'd local, run with `--from-roster --roster-db ./roster.db
--seed 42`.

### Schema, enumerated before and after

```
LOCAL  backtest_results (27) ... 'cache_date_end', 'profit_factor'      <- no import_json
VPS    backtest_results (27) ... 'cache_date_end', 'import_json'        <- no profit_factor
       walkforward_runs (19)  identical on both
VPS after migration:
       backtest_results (28) ... 'import_json', 'profit_factor'
```

**Both reported 27 columns before the migration while differing in content.**
A count-based comparison would have passed. This is why the check is
`PRAGMA table_info` and a set difference, not a length.

### Backups

| file | when | rows |
|---|---|---|
| `trades.bak-20260904T020447Z.db` | 02:04:47, host, manual pre-flight | 996 / 268,119 / 182, integrity ok |
| `trades.bak-20260904T022720Z.db` | import's own rule-5, pre-write | 996 / 268,119 / 182, integrity ok |
| `trades.bak-20260904T022739Z.db` | idempotency re-run, post-import | deleted — duplicates live state |

The rule-5 backups were written **inside the container** and rescued to the
host afterwards. See the backup-dir defect in CLAUDE.md.

### Import

```
[validate] backtest_results: 10 rows OK  spread_table_sha=c0c905fc6c071dd4
[validate] walkforward_runs: 471 rows OK spread_table_sha=c0c905fc6c071dd4
[schema] mirror verified against database/db.py — {'backtest_results': 24,
         'walkforward_runs': 19} reference columns, no drift
[schema] backtest_results: adding ['profit_factor']
[WROTE] backtest_results: inserted=10 skipped_existing=0  268119 -> 268129
[WROTE] walkforward_runs: inserted=471 skipped_existing=0  182 -> 653
```

Re-run unchanged, immediately after:

```
[WROTE] backtest_results: inserted=0 skipped_existing=10   268129 -> 268129
[WROTE] walkforward_runs: inserted=0 skipped_existing=471  653 -> 653
```

**Idempotent.** `backtest_trades` for the 10 imported ids: **0 rows** —
expected per gotcha 5, not a failed import. All 10 landed with
`profit_factor` NOT NULL, `spread_model=measured-2026-09-median`,
`spread_table_sha=c0c905fc6c071dd4`. VPS ids 268122-268131.

`run_type` totals for the 471: `stability_map` 426 (5 x 84 + 6 markers),
`monte_carlo` 25, `walk_forward` 10, `permutation` 10.

### The importer had to be given parity-v3 constants explicitly

The container's `/app` is still at `cc9055d`, i.e. `parity-v2` /
`flat-roundtrip-dollars-UNCALIBRATED`, because nothing was deployed. The
import's rule-1 check compares each row's `engine_version` against
`CURRENT_ENGINE_VERSION` **as imported from the code it is running under**, so
the first attempt refused:

```
REFUSED: backtest_results row (local id=5334) carries engine_version
'parity-v3' != 'parity-v2'. Never mix trade models.
```

Resolved by running the importer from `/tmp/pv3`, carrying the repo's HEAD
`engine_version.py` and `spread_model.py`, so `sys.path` resolved the
constants to `parity-v3`. **The running container was not modified** — verified
by reading `/app`'s constants afterwards (still `parity-v2`) and by
`RestartCount=0`.

⚠️ **Consequence, and it is a real one: the 10 imported rows are INVISIBLE to
the deployed selector and dashboard.** `get_backtest_results()` filters to
`CURRENT_ENGINE_VERSION`, which on the VPS is still `parity-v2`. The rows are
present and correct but nothing on that box reads them until a deploy. That is
safe — they cannot influence a promotion decision from where they sit — but it
means Stage 4's output is not yet live-visible.

---


## 📏 Post-Stage-4 cleanup — 2026-09-04

Dated detail. Standing conclusions in CLAUDE.md.

### A. The backup that did not exist, and the guard that now refuses

`import_stage4.py`'s rule-5 backup printed a filename, a byte count and
`integrity_check ok` — twice — while writing to the container's ephemeral
layer. `DEFAULT_BACKUP_DIR` is a HOST path; gotcha 3 forces the script to run
INSIDE the container. 650 MB, invisible from the host, absent from the
Database Backups table, destroyed by the next rebuild.

Device IDs inside the container, which is what the guard now compares:

```
/app/database          st_dev=2049   <- the bind mount (persistent)
/home/ubuntu/backups   st_dev=50     <- container overlay (ephemeral)
/tmp                   st_dev=50
```

**Guard seen to fire**, on the exact path that failed silently:

```
REFUSED: backup dir '/home/ubuntu/backups' is on a DIFFERENT filesystem from
the target '/app/database/trades.db'. Inside the container that means the
container's own writable layer — ephemeral, invisible to the host, and gone on
the next rebuild, while this run would still report a successful backup. Point
--backup-dir at a path on the bind-mounted volume (e.g. alongside the
database), or take the backup on the HOST and pass --no-backup.
```

### B. One bug, two symptoms

**Root cause:** `main()` in `scripts/run_backtest.py` dispatches as a chain of
`if <flag>: ... return` blocks — `stability_map`, `monte_carlo`, `permutation`,
`walk_forward`, `sweep` — each returning before the single-backtest save.

**Symptom 1 fixed:** multiple mode flags now exit 2 and name them.

```
REFUSED: 4 mode flags passed together: --stability-map --monte-carlo
         --permutation --walk-forward.
         These do NOT compose — main() dispatches as a chain of
         `if <flag>: ... return`, so only --stability-map would run and the
         rest would be silently dropped.
```

Three composites remain allowed because they are real pairings within one
branch: `--stability-map --monte-carlo`, `--walk-forward --monte-carlo`,
`--walk-forward --sweep`.

**Symptom 2 fixed:** the no-grid branch proves runnability on a probe backtest
before writing its marker.

| strategy | verdict written |
|---|---|
| `ny_session_momentum` (raises `EngineContractError`) | **`NOT_RUNNABLE`**, with the exception in `extra_json.runnability_error` |
| `bb_squeeze` (runnable, no grid) | `REDUCED_GAUNTLET`, `runnable=True` — regression check |

**What reads `walkforward_runs.verdict`, enumerated before a new value was
chosen: NOTHING.** No `get_walkforward*` in `models.py`; the only DB access is
`merge_extra_json` by id. `score_strategies()` and `select_strategy.py` read
`backtest_results`. No dashboard page references the table. The only
verdict-value comparisons (`v in ("ROBUST","MARGINAL")`, `v == "ROBUST"`) are
in the untracked `scripts/explore_liquidity_sweep.py` and operate on
in-memory dicts. An unknown value therefore cannot be silently mishandled.

### B3. Production enumeration, before any change

All six VPS `REDUCED_GAUNTLET` rows replayed locally under their own roster
params against their own caches:

```
   id symbol tf    strategy              RUNNABLE
  369 EURUSD 15MIN stoch_rsi             YES
  372 EURUSD 15MIN bb_squeeze            YES
  375 EURUSD 15MIN supertrend            YES
  378 US500  HOUR  stoch_rsi_confluence  YES
  379 EURUSD 15MIN ny_session_momentum   *** NO *** EngineContractError
  382 GBPUSD 15MIN ema_pullback          YES

NOT RUNNABLE: 1 of 6 -> ids [379]
```

id 379 was the one that surfaced during Stage 4, but that it is the ONLY one
is now measured rather than assumed.

**Annotated, not deleted.** Read back from the VPS:

```
  id=379 EURUSD 15MIN ny_session_momentum
    verdict          : NOT_RUNNABLE
    original_verdict : REDUCED_GAUNTLET
    runnable         : False
    annotated_at     : 2026-09-04T02:43:53.071440+00:00
    annotation       : NOT A RESULT. This row was written by the no-grid
                       branch of --stability-map, which persisted its marker
                       BEFORE any backtest ran...
```

Verdict distribution after: `REJECT` 412, `FRAGILE` 123, `MARGINAL` 76, `None`
35, `REDUCED_GAUNTLET` 5, `NOT_RUNNABLE` 1, `ROBUST` 1.

Backup first, on the HOST: `trades.bak-20260904T024323Z.db`, 325,763,072
bytes, 996 trades / 268,129 backtest_results / 653 walkforward_runs,
`integrity_check ok`.

### C. The pre-registration figure

Heading read "EXPECT 12 OF 13"; correct is **8 of 13**. Verified against
`roster.db`: 31 rows, 13 `status='paper'`, and `williams_r` holds five of the
thirteen (ids 6, 22, 32, 34, 36). `STABILITY_GRIDS` contains only
`williams_r`, so five get 84-cell maps and eight get markers.

The error generalises: **`STABILITY_GRIDS` is keyed by strategy NAME while the
roster is counted in ROWS**, and one name can hold several rows. With 12 in
the heading, a correct run returning 6 markers would have been flagged as
anomalous — the check would have manufactured the alarm it exists to prevent.

---


## 📏 Swiftalgo webhook silence — unrestricted audit, 2026-09-04

Dated detail. Standing conclusion sits next to the Active Strategies table in
CLAUDE.md, where the "live" claim it corrects is made.

**Why the query was framed this way.** The proposed check was "swiftalgo
alerts on Fridays 03:00–04:00 UTC". That is a NON-SEPARATING observation: the
rows were believed silent since 2026-08-06, so a zero is equally consistent
with *"this hour is quiet"* and *"this webhook has been dead for a month"*.
Same defect as the 2026-09-02 allowance test. The audit was therefore run
**unrestricted** — whole table, no date filter, no hour filter, no result
filter.

`webhook_log` is the right table: `webhook/receiver.py` logs through `_log_wh`
on **every** terminal path including blocked ones, which is why the all-time
result split is `BLOCKED` 194 / `EXECUTED` 175 / `REJECTED` 13 rather than
executions only.

### Extent

```
webhook_log: 382 rows, 2026-05-29T09:20:02Z .. 2026-08-06T00:01:06Z
```

| symbol | strategy | n | last arrival |
|---|---|---|---|
| US500 | swiftalgo | 144 | **2026-08-06T00:01:06Z** (BLOCKED, session_filter) |
| EURUSD | swiftalgo | 237 | **2026-08-05T14:19:01Z** |
| US500 | smc | 1 | 2026-06-25T14:30:03Z |

### The two windows

| window | EURUSD | US500 |
|---|---|---|
| last 30 days (≥ 2026-08-05) | **1** | **1** |
| the 30 before that (07-06 → 08-05) | **105** | **60** |

The two "last 30 days" rows **are** the final arrivals listed above. Rows in
`webhook_log` since 2026-08-06: **1**, which is the 08-06 row itself.

Monthly: `2026-05` 5, `2026-06` 188, `2026-07` 170, `2026-08` 19, then
nothing. Cross-checked independently against `trades`: last
`source='tradingview_webhook'` trade is `2026-08-05T14:19:03Z`, 215 all-time.

**Verdict: the inherited "silent since 2026-08-06" claim is CORRECT**, and
sharper than inherited — ~5.5 arrivals/day to zero, overnight, sustained 29
days. It is now verified in-session rather than carried forward.

### Nothing would have reported it

- `scripts/watchdog.py` — no reference to `webhook_log`.
- `scripts/daily_summary.py` — no reference to `webhook_log`.
- `heartbeat` table — `signal_loop` and `candle_stream` only. No webhook row.

So the only **rostered-active** signal source has no liveness check, while the
two paper-only loops have two each. The daily summary reports *trades opened*,
so a dead source reads as a quiet day. Recorded as a monitoring gap in
CLAUDE.md.

### Effect on the deploy decision — stated, because it inverts a risk

The deploy was held partly on "a rebuild could lose an in-flight webhook".
Measured, that hazard is currently **empty**. This does not retroactively
justify a market-hours rebuild: the hold was correct on the information
available, and the point of the measurement is that the hazard had been
**unmeasured in both directions** until someone looked without a filter on.

---


## 📏 Swiftalgo retirement — roster flip and evidence, 2026-09-04

Dated detail. The standing conclusion — **retired by decision, not an outage,
do not diagnose** — sits next to the Active Strategies table in CLAUDE.md,
where the "live" claim it replaces was made.

### The flip

`active_strategy` ids **11** (EURUSD HOUR swiftalgo) and **13** (US500 HOUR
swiftalgo), `active` → `inactive` at **2026-09-04T10:20:58.246542Z**.

`inactive` deliberately. `webhook/receiver.py:265` is
`status = strategy_row.get("status", "active")` and the only branches are
`inactive` (blocks) and `paper`; **anything unrecognised falls through to live
execution** (finding 4's fail-open default), so an invented value like
`retired` would have been the one unsafe choice.

Status vocabulary after: `inactive` **18**, `paper` **13**, `active` **0**.

Backup first, host-side: `trades.bak-20260904T102031Z.db`, 325,836,800 bytes,
996 trades / 268,129 backtest_results / 653 walkforward_runs / 31
active_strategy, `integrity_check ok`, verified present from the host.

### Dashboard effect — PREDICTED first, then confirmed

| page | query | predicted | actual |
|---|---|---|---|
| `01_overview.py:111` | `status IN ('active','live','paper')` | 15 → 13 | **15 → 13** ✓ |
| `07_performance.py:170` | `status = 'active'` | 2 → 0 (panel empties) | **2 → 0** ✓ |
| `09_webhook_log.py:57` | no status filter, `_icons` | ✅ active → ❌ inactive | **✅ → ❌** ✓ |

Both dashboard queries were run verbatim against the DB before and after. No
surprise — which is the point of predicting first.

### The evidence that the silence is real, and that no code caused it

- Last arrival, any symbol / any result: **`2026-08-06T00:01:06Z`** (US500,
  `BLOCKED session_filter`).
- Last EURUSD arrival: `2026-08-05T14:19:01Z`.
- Last webhook-sourced trade: **`2026-08-05T14:19:03Z`** (`trades`,
  `source='tradingview_webhook'`, 215 all-time).
- Monthly `webhook_log`: `2026-05` 5 → `06` **188** → `07` **170** → `08`
  **19** → **0**.
- **`git log --since=2026-07-25 --until=2026-08-14` contains exactly TWO
  commits, both docs** — `b0c7261` and `afd7f69`, the 2026-08-12 audit
  write-ups. **No code change was involved and none should be looked for.**

### `.db-shm` / `.db-wal` — the assumption that was wrong

They were taken to be leftovers from the `docker cp` rescue. Measured: the
backups are `journal_mode=wal` (inherited from the source by
`Connection.backup()`), so **any read, including `mode=ro`, recreates them.**
Moved aside, the `.db` verified self-contained (`integrity_check ok`, 996 /
268,119 / 182), and they **reappeared on the very next read** — including on a
backup that had had none until an earlier verification opened it.

12 files, ~200 KB total, against a 3.5 GB directory. **Listed, not removed:**
deleting them is undone by the next integrity check, and a rule that silently
reverses itself is worse than a documented exception.

---


## 📏 Dukascopy corpus evaluation — full run record, 2026-09-04

Dated detail. The decision-grade numbers live in CLAUDE.md.

### Client selection — what was verified, not assumed

- `python3-venv` is **absent** in this WSL (`ensurepip` missing,
  `apt install python3.12-venv` would need sudo). Rather than install a system
  package for a measurement, `pip3 install --target <scratchpad>/dukalib` was
  used with `PYTHONPATH`. Same isolation, no system change, and
  `requirements.txt` untouched.
- **`dukascopy-python` 4.0.1** installed cleanly and imports. `dukascopy-node`
  was not needed and was not tried — node 20.20.2 / npm 10.8.2 are present if
  a second opinion is ever wanted.
- `datafeed.dukascopy.com` reachable (HTTP 200) before any pull.

### Symbol resolution — enumerated from the library, not guessed

1,380 instrument constants across 25 groups. FX resolved on the first attempt:
`INSTRUMENT_FX_MAJORS_{EUR_USD,GBP_USD,AUD_USD,USD_CAD}`.

**Indices did NOT resolve by the obvious names.** Searching `SPX`, `NAS`,
`GER`, `DAX` returned only equities and ETFs — `INSTRUMENT_UK_SPX_GB_GBX`,
`INSTRUMENT_NORWAY_NAS_NO_NOK`, `INSTRUMENT_ETF_CFD_DE_TECDAXE_DE_EUR`. Any of
those would have been a silent wrong-instrument substitution of exactly the
SPY/QQQ/EWG kind. The real ones live under the `IDX` group (24 constants) and
are named `INSTRUMENT_IDX_AMERICA_E_SANDP_500`,
`INSTRUMENT_IDX_AMERICA_E_NQ_100`, `INSTRUMENT_IDX_EUROPE_E_DAAX`.

**This is why the level check is non-negotiable**: three plausible-looking
names were available and all three were wrong.

### Method

`fetch(instrument, interval, offer_side, start, end)` returns a UTC-indexed
pandas frame. **M15 was requested from the library directly** — tick was not
pulled. BID and ASK fetched separately and inner-joined on timestamp;
`mid = (close_bid + close_ask)/2`, matching `engine.py:139-156`.

Pull: 4 symbols x 2 sides, `2024-09-04 .. 2026-09-04`. ~49,800 bars per side
per symbol; ran in background, completed cleanly.

Comparison joined Dukascopy mid to `candle_source_compare.stream_close` (IG
stream mid, `(BID_CLOSE+OFR_CLOSE)/2`) on **identical bar timestamps**, with
the Twelve Data leg reproduced as a control from the same table's `yf_close`
where `yf_time == stream_time`. `|delta| <= 50 pips` guard on both legs, the
same as the earlier residual work, so the numbers are directly comparable.

### Tail decomposition — why the stdev column is misleading

| symbol | leg | p50 | p90 | p95 | p99 | max | >3 pips |
|---|---|---|---|---|---|---|---|
| EURUSD | Dukascopy | 0.20 | 0.75 | 2.77 | 5.35 | 22.70 | 5.0% |
| EURUSD | Twelve Data | 3.30 | 4.22 | 4.54 | 5.46 | 10.03 | **65.8%** |
| GBPUSD | Dukascopy | 0.30 | 0.71 | 3.45 | 5.10 | 14.40 | 5.9% |
| GBPUSD | Twelve Data | 0.55 | 1.53 | 2.05 | 3.63 | 13.75 | 1.9% |
| AUDUSD | Dukascopy | 0.25 | 0.55 | 5.10 | 5.10 | 13.30 | 5.5% |
| AUDUSD | Twelve Data | 2.44 | 3.28 | 3.58 | 4.29 | 8.08 | 18.5% |
| USDCAD | Dukascopy | 0.50 | 1.20 | 6.95 | 6.95 | 6.95 | 7.1% |
| USDCAD | Twelve Data | 0.65 | 3.45 | 4.25 | 5.35 | 10.55 | 13.1% |

Dukascopy's p50 and p90 are better on **all four**. Its stdev is worse on all
four. Both are true and they are not in conflict: the distribution is a tight
core plus a 5–7% tail, against Twelve Data's uniformly displaced body. On
EURUSD, Twelve Data's p50 error (3.30 pips) is **larger than Dukascopy's p99**
would be if the tail were removed.

GBPUSD is the one symbol where Twelve Data has the thinner tail (1.9% vs 5.9%
beyond 3 pips) while still losing on p50 and p90. Worth a second look before
building.

### Gaps

104 weekend gaps per symbol over 2 years — exactly 52/year, so the series is
complete. Remaining gaps >1h number 4–6 per symbol and are all holidays:
24.2h at 2025-12-31 and 2024-12-31, ~14–15h at 12-25 in both years.

### Fences honoured

No file written to `scripts/candle_cache/`. No `requirements.txt` change.
Nothing wired into the engine. No VPS access, no container change, no
`/prices` request. `execute_trade.py` untouched. The 20 MB pull sits in the
session scratchpad only.

---


## 📏 Dukascopy tail resolution + corpus build — 2026-09-04

Dated detail. Verdict and file table in CLAUDE.md.

### The methodological error that had to be fixed first

The first pass at the discriminators produced a nonsense internal
inconsistency: EURUSD showed **213 tail entries but only 22 distinct
timestamps**. `candle_source_compare` is written once per
`_check_symbol` call, i.e. **once per strategy**, so a symbol watched by five
paper strategies contributes five rows per bar.

Deduplicating to one observation per `(symbol, minute)`:

| | raw | distinct | factor |
|---|---|---|---|
| all rows, EURUSD | 5,062 | 3,892 | 1.30× |
| all rows, GBPUSD | 5,123 | 3,947 | 1.30× |
| all rows, AUDUSD | 4,371 | 3,236 | 1.35× |
| all rows, USDCAD | 3,447 | 2,672 | 1.29× |
| **EURUSD tail bars** | **213** | **16** | **13.3×** |

The overall duplication is a uniform ~1.3×, but the **tail** bars were
duplicated ~13×. The divergent timestamps were re-logged across many cycles,
which is what a stale stream buffer being read repeatedly looks like. Every
number below is on the deduplicated set. The previously reported "5–7% of bars
beyond 3 pips" was an artifact of this and is corrected to **0.4–0.8%**.

This is the dedup caveat `database/models.py::get_spread_samples` already
documents, encountered in a table nobody had applied it to.

### (a) Hour-of-day

Pooled tail rate (|delta| > 3 pips), deduplicated, all four FX symbols:

```
  21:00  paired= 394 tail= 39   9.9%   <- daily rollover, is_entry_allowed FALSE
  20:00  paired= 490 tail=  7   1.4%
  16:00  paired= 528 tail=  7   1.3%
  06:00  paired= 609 tail=  5   0.8%
  ...    thirteen hours at exactly 0.0%
```

Per-symbol share of tails in hours where `is_entry_allowed` is False:
GBPUSD 84%, USDCAD 67%, AUDUSD 31%, EURUSD 12%.

### (b) Cross-symbol coincidence

66 distinct timestamps carry at least one tail bar:

| on N of 4 symbols | count | share |
|---|---|---|
| 1 | 56 | **84.8%** |
| 2 | 7 | 10.6% |
| 3 | 1 | 1.5% |
| 4 | 2 | 3.0% |

Per-symbol tail rates 0.4–0.8%. Against 2,620 timestamps observed on all four
symbols, independence predicts **0.000** all-four coincidences; **2** were
observed. Two genuine market-wide events; the rest is independent scatter.

### (c) Persistence

| symbol | tail bars | runs | single-bar | longest |
|---|---|---|---|---|
| EURUSD | 16 | 14 | 13 (93%) | 3 |
| GBPUSD | 31 | 27 | 25 (93%) | 3 |
| AUDUSD | 13 | 13 | 13 (100%) | 1 |
| USDCAD | 21 | 20 | 19 (95%) | 2 |

### (d) Against our own capture's gaps

Tail bars within 60 min after a >1h gap in the IG capture: EURUSD 0/16 (0%),
AUDUSD 2/13 (15%), GBPUSD 6/31 (19%), USDCAD 5/21 (24%). Real but not
dominant — and a reminder that the IG side is our own capture, with its own
reconnects, not a reference truth.

### GBPUSD

31 tail bars, **26 of them (84%) in blocked hours**. Restricted to
entry-allowed hours: n=3,745, mean **−0.046**, stdev **0.419**, >3 pips
**0.1%**. Against Twelve Data's all-hours stdev of 1.035, that is ~2.5×
tighter. The caveat came entirely from hours the bot never trades.

### The build

`scripts/fetch_dukascopy.py`, 12 files, ~45 MB total, into
`scripts/candle_cache/` (gitignored, so the data is not committed — only the
script and this record are).

Mid built as `(bid+ask)/2` on each of open/high/low/close independently, read
from `backend/backtesting/engine.py` rather than assumed, with the same NaN
guard. BID and ASK fetched separately and inner-joined on timestamp.

The script embeds the level check and **refuses to write** a file whose last
close is more than 10% from the IG reference — the SPY/QQQ/EWG signature. Run
on the written files: US500 7751.40 vs 7671 (1.010×), US100 29527.58 vs 29289
(1.008×) at 15MIN; 1.010× / 1.008× at HOUR.

**Additive-only proof:** md5 of all 24 pre-existing cache files captured before
the run and re-verified after — 0 mismatches, 0 missing.

Nothing consumes these files yet: no `--source dukascopy` branch, no default
changed, Stage 4 not re-run.

---


## 📏 Unique-observation recomputation + noise floor — 2026-09-04

Dated detail. Conclusions and the numbers a decision reads are in CLAUDE.md.

### Was the earlier comparison deduped? NO — established from the data

The earlier three-way table iterated `candle_source_compare` rows and looked
each up in Dukascopy, so a bar observed N times contributed N deltas. The n
values are the fingerprint: EURUSD Dukascopy leg reported **4,280**; the
deduplicated count is **3,842**, and the raw row count for EURUSD is 5,062 with
3,892 distinct `stream_time`. Row-based, confirmed.

### The two tables do NOT share a duplication shape

The task asked this be verified rather than assumed, and they disagree:

```
candle_source_compare (15MIN FX), by checked_at minute:
   AUDUSD rows=4373 distinct=4373 factor=1.00
   EURUSD rows=5064 distinct=5064 factor=1.00
   GBPUSD rows=5125 distinct=5125 factor=1.00
   USDCAD rows=3449 distinct=3449 factor=1.00

signal_log, same symbols, by checked_at minute:
   AUDUSD rows= 5668 distinct=5668 factor=1.00
   EURUSD rows=40782 distinct=9717 factor=4.20
   GBPUSD rows=15367 distinct=8261 factor=1.86
   USDCAD rows= 5069 distinct=5069 factor=1.00
```

`signal_log` duplicates **per strategy** (`_check_symbol` runs once per
rostered strategy; EURUSD carries five). `candle_source_compare` does **not** —
`_log_candle_comparison` is called once per symbol per cycle from
`live_signal_loop.py:500/512`. Its duplication is a different thing entirely:
**by `stream_time`, 1.29–1.35×**, because the 5-minute loop re-observes the
same completed 15-minute bar across several cycles.

My earlier note calling this "one row per strategy" for
`candle_source_compare` was wrong about the mechanism, though right that a
dedup was needed. Corrected here and in CLAUDE.md.

### Row-based vs unique-based, side by side (pips)

| sym | leg | basis | n | mean | stdev | IQR | p50 | p90 |
|---|---|---|---|---|---|---|---|---|
| EURUSD | Dukascopy | ROWS | 4280 | −0.274 | 1.283 | 0.45 | 0.20 | 0.75 |
| EURUSD | Dukascopy | **UNIQUE** | 3842 | **−0.062** | **0.624** | 0.40 | 0.20 | 0.40 |
| EURUSD | TwelveData | ROWS | 3207 | 3.210 | 1.018 | 0.96 | 3.30 | 4.22 |
| EURUSD | TwelveData | **UNIQUE** | 3109 | 3.311 | 0.857 | 0.93 | 3.33 | 4.23 |
| GBPUSD | Dukascopy | ROWS | 4340 | 0.129 | 1.088 | 0.65 | 0.30 | 0.71 |
| GBPUSD | Dukascopy | **UNIQUE** | 3901 | **−0.063** | **0.712** | 0.60 | 0.30 | 0.55 |
| GBPUSD | TwelveData | ROWS | 3379 | 0.340 | 1.035 | 0.92 | 0.55 | 1.53 |
| GBPUSD | TwelveData | **UNIQUE** | 3281 | 0.351 | 1.048 | 0.96 | 0.57 | 1.57 |
| AUDUSD | Dukascopy | ROWS | 3609 | −0.258 | 1.232 | 0.45 | 0.25 | 0.55 |
| AUDUSD | Dukascopy | **UNIQUE** | 3188 | **−0.047** | **0.501** | 0.40 | 0.20 | 0.40 |
| AUDUSD | TwelveData | ROWS | 2470 | 2.434 | 0.749 | 0.80 | 2.44 | 3.28 |
| AUDUSD | TwelveData | **UNIQUE** | 2469 | 2.434 | 0.749 | 0.80 | 2.44 | 3.28 |
| USDCAD | Dukascopy | ROWS | 2858 | 0.349 | 1.835 | 1.00 | 0.50 | 1.20 |
| USDCAD | Dukascopy | **UNIQUE** | 2633 | **−0.076** | **0.730** | 0.90 | 0.45 | 0.85 |
| USDCAD | TwelveData | ROWS | 2878 | −0.936 | 1.444 | 1.10 | 0.65 | 3.45 |
| USDCAD | TwelveData | **UNIQUE** | 2583 | −0.993 | 1.418 | 1.10 | 0.65 | 3.45 |

Dukascopy's stdev roughly halves on dedup (1.283→0.624, 1.088→0.712,
1.232→0.501, 1.835→0.730). Twelve Data's moves by less than 0.2 on every
symbol and is unchanged on AUDUSD. The duplicated bars were the ones where
Dukascopy and IG disagreed.

### Ordering on unique observations

Dukascopy wins **|mean|, stdev, IQR, p50 and p90 on all four symbols** — 20 of
20 comparisons. Nothing flips in Twelve Data's favour.

### Entry-allowed noise floor, all four

| symbol | n | mean | stdev | IQR | p90 abs | >1 pip | spread | stdev/spread | p90/spread |
|---|---|---|---|---|---|---|---|---|---|
| EURUSD | 3689 | −0.057 | 0.607 | 0.40 | 0.35 | 1.1% | 0.60 | 1.01 | 0.58 |
| GBPUSD | 3745 | −0.056 | 0.524 | 0.60 | 0.50 | 1.3% | 0.90 | 0.58 | 0.56 |
| AUDUSD | 3081 | −0.056 | 0.459 | 0.40 | 0.35 | 0.9% | 0.60 | 0.77 | 0.58 |
| USDCAD | 2556 | −0.055 | 0.596 | 0.90 | 0.80 | 4.0% | 1.30 | 0.46 | 0.62 |

Pooled 0.547 pips of noise against 0.850 pips of modelled spread = **64%**.

The four means agree to three decimals (−0.055 to −0.057) across four
instruments — too uniform for a per-symbol vendor offset; it reads as a
constant sub-tick or rounding artifact somewhere in one pipeline. Noted, not
chased.

---


## 📏 Dukascopy Stage 4 re-run — full run record, 2026-09-04

Dated detail. Verdict table and conclusions in CLAUDE.md.

**Window:** 11:50:40Z → ~12:41Z, ~50 minutes for 13 strategies x 4 stages. Longer
than the Twelve Data batch's 14 minutes because the corpus is 49,803 candles
against 29,995 and each of the 5 x 84 stability cells is a full walk-forward.

### Wiring, verified by positive signal

`--source dukascopy` added to `run_backtest.py`: a loader, a dispatch branch, a
`choices` entry and a `cache_file_name` mapping. **The default is unchanged
(`ig`).** Proof it is selectable rather than a silent default — same strategy,
params and seed, two corpora:

```
id=5344  cache_file=AUDUSD_15MIN_AV.json    trades=234  PF=1.0431
id=5345  cache_file=AUDUSD_15MIN_DUKA.json  trades=268  PF=0.8168
```

The AV row reproduces the earlier Stage 4 figure exactly (234 / 1.0431), which
is what establishes the existing path still resolves to what it always did.

### Rank order, both ways

```
OLD (Twelve Data)                        NEW (Dukascopy)
 1. GBPUSD 15MIN ema_pullback  2.2452     1. US100  15MIN ema_pullback  1.4573
 2. EURUSD 15MIN supertrend    1.1536     2. EURUSD 15MIN williams_r    1.1202
 3. EURUSD 15MIN bb_squeeze    1.1033     3. GBPUSD 15MIN williams_r    1.0280
 4. EURUSD 15MIN williams_r    1.0670     4. US500  15MIN ema_pullback  0.9968
 5. AUDUSD 15MIN williams_r    1.0431     5. AUDUSD 15MIN williams_r    0.9254
 6. EURUSD 15MIN stoch_rsi     0.9362     6. EURUSD 15MIN stoch_rsi     0.8579
 7. US500  HOUR  williams_r    0.9281     7. EURUSD 15MIN supertrend    0.8129
 8. GBPUSD 15MIN williams_r    0.8919     8. US500  HOUR  williams_r    0.7796
 9. USDCAD 15MIN williams_r    0.8671     9. EURUSD 15MIN bb_squeeze    0.7710
10. US500  HOUR  stoch_rsi_conf 0.1041   10. USDCAD 15MIN williams_r    0.7010
                                         11. US500  HOUR  stoch_rsi_conf 0.6630
                                         12. GBPUSD 15MIN ema_pullback  0.4837
```

Rank movement on the 10 common strategies: GBPUSD ema_pullback **+9**, GBPUSD
williams_r **−6**, EURUSD bb_squeeze +4, EURUSD supertrend +3, EURUSD
williams_r −3, AUDUSD williams_r −2, EURUSD stoch_rsi −2, and three moving 1.

**Concordant pairs 24 of 45. Kendall tau +0.067.**

### The prediction, scored honestly

| predicted | outcome |
|---|---|
| rankings change | **HIT** — tau +0.067 |
| EURUSD moves most (offset 5.5x spread) | **MISS** — moved 2–4 places |
| AUDUSD moves most (4.1x) | **MISS** — moved 2 |
| GBPUSD moves least (0.4x) | **MISS** — the two biggest movers, +9 and −6 |
| USDCAD moves least (0.8x) | hit — moved 1 |

The mechanism was misidentified. **Offset magnitude did not predict movement;
sample size did.** GBPUSD `ema_pullback` at 23 trades produced the best PF in
the old batch (2.2452) and the worst in the new (0.4837). Strategies with 200+
trades moved a few places at most. Writing the specific shape down in advance
is what made this scoreable rather than a vague "it moved, as expected".

### Span control

Every common strategy re-run at matched candle counts. Full table in CLAUDE.md;
the pattern is that the matched column tracks the full-span column rather than
the old one, so the corpus is the cause and the extra span is not. Those 10
control rows were deleted locally before export — a methodological control
rather than Stage 4 results, and keeping them would have placed two rows per
strategy on the VPS at different counts.

### Import

```
[validate] backtest_results: 12 rows OK  spread_table_sha=c0c905fc6c071dd4
[validate] walkforward_runs: 477 rows OK spread_table_sha=c0c905fc6c071dd4
[schema] mirror verified against database/db.py — no drift
[WROTE] backtest_results: inserted=12  skipped=0    268129 -> 268141
[WROTE] walkforward_runs: inserted=477 skipped=0    653 -> 1130
re-run: inserted=0 skipped=12 / inserted=0 skipped=477, counts static
```

The first export used the default 10-minute `--since` margin and swept in 14
rows rather than 12 — the two Item-A wiring-verification runs at 11:49, one of
them an **Alpha Vantage** row. Caught by comparing against the derived
expectation of 12; re-exported with `--since-margin-minutes 0`. The margin
exists for the non-monotonic WSL clock, and here both clocks agreed, so zero
was safe.

Backup host-side first: `trades.bak-20260904T124236Z.db`, 325,861,376 bytes,
`integrity_check ok`, recorded in the Database Backups table in the same change.

The importer again needed `parity-v3` constants from `/tmp/pv3` because the
deployed `/app` is still `cc9055d` (parity-v2) — **the deploy remains held to
Saturday.** Container untouched, `RestartCount=0`.

---


<!-- moved from CLAUDE.md 2026-09-04 — ETF-cache blocker on ids 29/30 — LIFTED by the Dukascopy index corpus -->

## ⛔ US500 / US100 15MIN caches are ETF prices — BLOCKER, same class as DAX

`scripts/candle_cache/US500_15MIN_AV.json` and `US100_15MIN_AV.json` were
fetched through `scripts/fetch_twelvedata.py`, whose `SYMBOL_MAP` routes
**`"US500" -> "SPY"`** and **`"US100" -> "QQQ"`**. Those are **ETFs, not the
indices**. Measured 2026-08-22:

| cache | last close | median 15MIN bar range | real index |
|---|---|---|---|
| `US500_15MIN_AV.json` (SPY) | **729.08** | 1.42 | ^GSPC ≈ **7,481** (~10.3x) |
| `US100_15MIN_AV.json` (QQQ) | **705.54** | 2.20 | ^NDX ≈ 26,000 (~37x) |
| `US500_HOUR_5000_yf.json` (^GSPC) | 7,481.46 | 21.45 | correct |

**Consequences, identical in shape to the DAX blocker below:**
- `MIN_SL_DIST["US500"] = 3.0` against a median bar range of **1.42** — the
  floor binds on most bars, exactly the pathology that makes DAX unusable.
  `US100` is 4.0 against 2.20.
- `VALUE_PER_POINT` is 1.0 for both, meaning "one index point". A point of SPY
  is not a point of ^GSPC, so every lot size and P&L on these candles is off by
  the scale factor.
- The HOUR cache is fine — it came from yfinance `^GSPC`. **The defect is
  per-file, not per-symbol**, so "US500 has a cache" is not the question; which
  file, from which source, is.

**Retroactively taints recorded numbers.** The `ema_pullback` figures in this
file — US500 15MIN "44 bt trades, 45.5% WR, PF 1.57" and US100 15MIN "86% of 72
combos profitable, PF 3.17 best" — were produced on ETF-scaled candles. Treat
them as void, not merely pre-parity.

**Blocks Stage 4 for `active_strategy` ids 29 (US500 15MIN ema_pullback) and
30 (US100 15MIN ema_pullback)** until the caches are re-fetched from an index
source and the scale verified against IG. yfinance `^GSPC`/`^NDX` at 15MIN is
capped at 60 days, which is not enough span for a walk-forward; Twelve Data
would need an index symbol that the free tier may not carry. **Unresolved — do
not paper over it by re-running on the ETF files.**

**✅ RESOLVED 2026-08-23 — "may not carry" is now measured, and the answer is
no.** Probed with the project key: `SPX` and `NDX` both return *"This symbol is
available starting with the Grow or Venture plan"*; `IXIC`/`GDAXI` are invalid
symbols; **`DAX` on Twelve Data is a $47 NASDAQ ETF**, not the index. The
SPY/QQQ/EWG map was not carelessness — it is what the free tier permits.
**ids 29 and 30 stay blocked**, and there is no substitution available this
week at any tier we hold.

**If index exposure must be tested now, HOUR is the honest route.** yfinance 1h
reaches 730 days and `US500_HOUR_5000_yf.json` is genuine `^GSPC` at index
scale — that cache is fine and always was. 15MIN indices are unavailable, and
saying so is better than running the gauntlet on ETF candles and stamping the
output `parity-v2`. See IG Historical Allowance for the full source table.

### Audit result (2026-08-22) — what is contaminated

`SYMBOL_MAP` audited in full: **all 7 FX entries are correct** (they map to real
pairs). **All 3 index entries are ETF proxies** — `US500->SPY`, `US100->QQQ`,
`DAX->EWG`.

⛔ **DO NOT "just fix the mapping" — measured 2026-08-23, it cannot be fixed at
this tier.** `SPX` and `NDX` return *"available starting with the Grow or
Venture plan"*; `IXIC`/`GDAXI` are invalid symbols; and **`DAX` on Twelve Data
resolves 200 OK to a $47 NASDAQ ETF** — a *different* wrong instrument from
`EWG`, which is how a "fix" produces a second contamination with a fresh
signature. Whoever wrote `SYMBOL_MAP` picked what the free tier permitted; this
was never carelessness. Full probe table in findings doc finding 30. Contamination is confined to `*_15MIN_AV.json` for those three
symbols; **every `*_yf.json` is correctly index-scaled** (verified by price
level). The defect is per-FILE, not per-symbol.

| table (local DB) | contaminated | of | identify with |
|---|---|---|---|
| `backtest_results` | **1,166** | 5,329 | `symbol IN ('US500','US100','DAX') AND timeframe='15MIN' AND candles_total > 5000` |
| `walkforward_runs` | **82** | 276 | `symbol IN ('US500','US100','DAX') AND cache_file LIKE '%_AV.json'` |

Rows are **marked, not deleted**. Safe today because every one is
`engine_version='pre-parity-v0'` and `get_backtest_results()` filters to the
current version — they are reachable only via `engine_version=None`.
`backtest_results` has **no cache-provenance column**, so its count is an
inference from `candles_total`; add `cache_file` there if provenance work
resumes. Full detail in findings doc finding 30.

This is the third instance of the class: DAX (same cause, see below), EURUSD
points-vs-decimal on the DEMO account (see Price scale quirk), and now these
two. **Always check a cache's price level against the instrument it claims to
be before trusting a backtest built on it.**

---

<!-- moved from CLAUDE.md 2026-09-04 — Stage 4 Twelve Data results — SUPERSEDED by the Dukascopy re-run (tau +0.067) -->

## ✅ STAGE 4 (TWELVE DATA) — 10 of 13 on parity-v3, 2026-09-04 — SUPERSEDED

⚠️ **The results below were produced on the Twelve Data corpus and the
rankings did not survive the corpus change (tau +0.067). Retained as the record
of what was believed, not as evidence.** See the Dukascopy re-run above.

**Result in one line: ZERO promotable strategies. One MARGINAL, one FRAGILE,
eight REJECT.** That is the outcome the pre-registration below anticipated, and
nothing in the batch contradicts it.

| symbol | tf | strategy | walk-forward | median PF | permutation | stability |
|---|---|---|---|---|---|---|
| AUDUSD | 15MIN | williams_r | **MARGINAL** | **1.0514** | MARGINAL | 84 cells — REJECT 59, MARGINAL 16, FRAGILE 9, **ROBUST 0** |
| USDCAD | 15MIN | williams_r | **FRAGILE** | 1.0004 | FRAGILE | 84 — REJECT 69, FRAGILE 8, MARGINAL 7 |
| US500 | HOUR | williams_r | REJECT | 0.9900 | REJECT | 84 — FRAGILE 40, REJECT 38, MARGINAL 5, **ROBUST 1** |
| EURUSD | 15MIN | williams_r | REJECT | 0.9709 | REJECT | 84 — REJECT 63, MARGINAL 14, FRAGILE 7 |
| GBPUSD | 15MIN | williams_r | REJECT | 0.9454 | REJECT | 84 — REJECT 67, FRAGILE 9, MARGINAL 8 |
| EURUSD | 15MIN | bb_squeeze | REJECT | 0.8892 | REJECT | REDUCED_GAUNTLET |
| EURUSD | 15MIN | stoch_rsi | REJECT | 0.8837 | REJECT | REDUCED_GAUNTLET |
| EURUSD | 15MIN | supertrend | REJECT | 0.8821 | REJECT | REDUCED_GAUNTLET |
| GBPUSD | 15MIN | ema_pullback | REJECT | 0.6607 | REJECT | REDUCED_GAUNTLET |
| US500 | HOUR | stoch_rsi_confluence | REJECT | 0.0000 | REJECT | REDUCED_GAUNTLET |

**Single-backtest PF (with `profit_factor` now actually populated):** GBPUSD
ema_pullback 2.2452 (23 trades), EURUSD supertrend 1.1536 (56), EURUSD
bb_squeeze 1.1033 (45), EURUSD williams_r 1.067 (219), AUDUSD williams_r 1.0431
(234), EURUSD stoch_rsi 0.9362 (199), US500 williams_r 0.9281 (57), GBPUSD
williams_r 0.8919 (219), USDCAD williams_r 0.8671 (209), US500
stoch_rsi_confluence 0.1041 (20).

**Note the disagreement between the two columns and do not resolve it by
picking the friendlier one:** GBPUSD `ema_pullback` has the highest
single-backtest PF in the batch (2.2452) on **23 trades**, and the *worst*
walk-forward median in the batch (0.6607). The single number is the one an
eyeball lands on; the walk-forward is the one with out-of-sample windows behind
it.

### 3 of 13 were NOT run, and the reasons differ

- **ids 29 (US500 15MIN) and 30 (US100 15MIN) `ema_pullback` — HELD, not
  failed.** The ETF-cache blocker still applies and was re-verified
  empirically rather than taken from this file: `US500_15MIN_AV.json` last
  close **729.08** against IG's US500 at **7745** (0.094x, SPY), and
  `US100_15MIN_AV.json` **705.54** against **29480** (0.024x, QQQ). Running
  them would have produced `parity-v3`-stamped rows on ETF candles and
  imported them into the table the selector reads.
- **id 28 EURUSD 15MIN `ny_session_momentum` — FAILED, and the failure is
  PRE-EXISTING.** `EngineContractError: SELL requires tp_price < entry <
  sl_price, got tp=1.16781 entry=1.16776 sl=1.1686` at idx=1103. Re-run on a
  clean `parity-v2` tree: **same idx, same tp, same sl, only entry differs by
  the 0.00003 half-spread — and it fails there too.** So its roster params
  (`tp_multiplier: 1.0`, `breakout_buffer: 0.0`) emit a wrong-side take-profit,
  and this strategy has not been validly backtestable since the contract
  landed on 2026-08-16. Not caused by parity-v3, not fixed here.
  ⚠️ **It still wrote a `REDUCED_GAUNTLET` stability marker**, because that
  branch short-circuits before running a backtest. That marker is on the VPS.
  **It is not evidence the strategy ran** — the absence of any
  `walk_forward`, `permutation` or `backtest_results` row for it is the tell.

### ✅ id 379 ANNOTATED ON THE VPS — the marker that read as a result

`walkforward_runs` id **379** (EURUSD 15MIN `ny_session_momentum`) carried
`REDUCED_GAUNTLET`, written by the no-grid branch **before any backtest ran**,
for a strategy that raises `EngineContractError` and cannot be backtested at
all. Corrected 2026-09-04 to **`NOT_RUNNABLE`**, with the exception text,
`original_verdict`, `annotated_at` and a plain-English `annotation` merged
into `extra_json`.

**Annotated, not deleted** — a deleted row leaves no trace the defect
happened; an annotated row documents itself and the change is reversible from
the row alone.

**All six VPS `REDUCED_GAUNTLET` rows were probed for runnability first, not
just the one that surfaced** (ids 369, 372, 375, 378, 379, 382, each replayed
under its own roster params against its own cache). **Exactly one failed.**
That is now a measured result rather than an assumption. Post-change
distribution: `REDUCED_GAUNTLET` 5, `NOT_RUNNABLE` 1.

---

<!-- moved from CLAUDE.md 2026-09-04 — both Stage 4 pre-registrations — the batch they predicted has now run -->

### 🔒 PRE-REGISTRATION — DUKASCOPY STAGE 4 RE-RUN, written 2026-09-04 BEFORE the batch

Same engine (`parity-v3`), same spread model (`measured-2026-09-median`,
`c0c905fc6c071dd4`), **different corpus**. Any movement is attributable to the
data alone.

#### The noise floor, per symbol, as a ratio to that symbol's own spread

| symbol | noise stdev | spread | **ratio** | roster rows |
|---|---|---|---|---|
| **EURUSD** | 0.607 | 0.60 | **1.01** ← worst | **5 of 13** |
| AUDUSD | 0.459 | 0.60 | 0.77 | 1 |
| GBPUSD | 0.524 | 0.90 | 0.58 | 2 |
| USDCAD | 0.596 | 1.30 | 0.46 ← best | 1 |
| pooled | 0.547 | 0.850 | **0.64** | |

🔴 **EURUSD is the LEAST resolvable symbol and carries FIVE of the thirteen
roster rows.** Its per-bar noise is a full spread width. So **EURUSD results
carry the widest error bars precisely because they are the most numerous** —
the temptation will be to read the biggest block of results as the most
reliable, and it is the least. State any EURUSD conclusion with that attached.

#### Trigger vs aggregate — which conclusions each supports

| | status | supports |
|---|---|---|
| **Aggregate PF, net P&L, win rate** | ✅ **trustworthy now** — the mean error is ±0.06 pips and averages down over hundreds of trades | comparing strategies to each other; comparing old corpus to new; verdict-level conclusions |
| **Per-bar trigger evaluation** | ❌ **NOT resolvable** at ~0.5–1.0 spread widths — noise can flip whether a bar touched an SL or TP | any claim about a specific trade, a specific bar, exact trade counts, or a PF difference smaller than the noise |

**This is the material change from the Twelve Data era.** Its +3.2 pip EURUSD
mean was a *bias* that never averaged down at any trade count. A ±0.06 mean
does. So aggregate comparisons are meaningful for the first time.

#### What each outcome would MEAN — written before, because afterwards either will feel like confirmation

- **RANKINGS CHANGED** → the old Stage 4 conclusions were **corpus artifacts**.
  The Twelve Data corpus was shaping which strategies looked good, not merely
  adding noise. Everything ranked on it is void, not just imprecise.
- **RANKINGS HELD** → the strategy conclusions are **about the strategies**.
  A +3.2 pip systematic offset failed to reorder them, which is strong evidence
  the ordering reflects strategy behaviour rather than data.

**Both are informative. I expect RANKINGS TO CHANGE**, and I am recording the
specific shape so a vague "it moved" cannot be claimed as a hit:
- **EURUSD (offset +3.31 pips = 5.5x its spread) and AUDUSD (+2.43 = 4.1x)
  should move MOST.**
- **GBPUSD (+0.35 = 0.4x) and USDCAD (−0.99 = 0.8x) should move LEAST.**
- Early signal already seen while wiring the loader: **AUDUSD 15MIN
  `williams_r` goes PF 1.0431 → 0.8168**, same engine, same params, same seed.
  Consistent with that prediction.
- **US500/US100 15MIN `ema_pullback` (ids 29, 30) have NO comparison** — their
  old figures were measured on ETF candles and are void, not merely different.

#### Derived expected verdict counts — DERIVED, not carried

Read at run time from `roster.db` and `run_backtest.py`, not from this file:

```
paper roster rows                                    13
  STABILITY_GRIDS keys                     = ['williams_r']
  rows whose strategy_name IS in GRIDS      =  5  (ids 6, 22, 32, 34, 36)
  rows whose strategy_name is NOT in GRIDS  =  8  (ids 23,24,25,26,28,29,30,31)
  id 28 ny_session_momentum raises EngineContractError on BOTH corpora
    (TwelveData idx=1103, Dukascopy idx=9523 — corpus-independent defect)
```

| outcome | expected | derivation |
|---|---|---|
| full 84-cell stability maps | **5** | roster rows with a grid |
| `stability_map` rows from those | **420** | 5 x 84 |
| `REDUCED_GAUNTLET` markers | **7** | 8 without a grid, minus id 28 |
| `NOT_RUNNABLE` markers | **1** | id 28 |
| total `stability_map` rows | **428** | 420 + 7 + 1 |
| `backtest_results` rows | **12** | 13 minus id 28 |
| `walk_forward` rows | **12** | ″ |
| `permutation` rows | **12** | ″ |

**The last pre-registration said 12 of 13 reduced and was wrong because it
counted strategy NAMES where the system counts roster ROWS.** This one is
derived from both sources at run time and shows its working.

### 🔒 PRE-REGISTERED INTERPRETATION — written 2026-09-04, BEFORE the batch ran

The entry above pre-registers the VERDICT SHAPE. This one pre-registers **what
the NUMBERS can support**, and it is written first for the same reason.

**The measured cache-vs-IG-mid residual is VARYING, not a constant offset.**
Per-symbol stdev **0.750–1.448 pips**, pooled **1.978**, i.e. **1.1×–1.7× the
entire spread parity-v3 models**. A constant offset would cancel through
differencing; this one does not, and it lands on SL/TP trigger evaluation.

Two consequences, and they point in opposite directions:

- **RELATIVE comparison across the roster IS meaningful.** The residual applies
  equally to every strategy on a given symbol, so ordering within a symbol is
  not corrupted by it.
- **ABSOLUTE PF is NOT resolvable at these margins.** Walk-forward already sits
  at median PF **1.0514**. A per-bar noise term larger than the modelled spread
  cannot be netted out of a number that close to 1.0.

> **THEREFORE: NO PROMOTION DECISION FOLLOWS FROM THIS BATCH, whatever the
> ordering looks like.** A strategy that comes back "best" is the best of
> thirteen measurements whose error bars overlap.

**Added 2026-09-04 — THE CORPUS NOISE FLOOR, for the re-run on Dukascopy
data.** Entry-allowed hours, unique observations, Dukascopy mid vs IG mid:
stdev **0.607 / 0.524 / 0.459 / 0.596 pips** (EURUSD / GBPUSD / AUDUSD /
USDCAD) against modelled spreads of 0.60 / 0.90 / 0.60 / 1.30 — i.e.
**46–101% of one spread width, pooled 64%.** So: **an edge smaller than
~0.5–0.6 pips per bar cannot be distinguished from corpus error.** Note the
difference from the Twelve Data era, and it is the whole reason the corpus
changed: the means are now ±0.06 pips, so the systematic component averages
away over trades. Twelve Data's +3.2 pip EURUSD mean was a *bias* that never
did.

**Thirteen rows near 1.0 will otherwise read as a ranking.** That is the
specific misreading this entry exists to pre-empt — it is the same shape as
the pre-parity scores that promoted `US100 HOUR supertrend` unreviewed, where
an ordering was treated as evidence because it was the only thing on the
screen.

What WOULD change this: a smaller residual (index-scale 15MIN candles from a
single source, or a cache-vs-IG level correction), or a strategy whose PF is
far enough from 1.0 that a ~1-pip-per-bar noise term cannot explain it. Neither
is in this batch.

---

<!-- moved from CLAUDE.md 2026-09-04 — the 2026-09-04 deploy-hold decision and its pre-flight — reason now void, queue stale -->

## ⏸️ DEPLOY HELD TO SATURDAY 2026-09-05 — parity-v3 queue, 9 commits

**Decided 2026-09-04 09:34Z, pre-flight complete, nothing changed on the VPS.**
The deploy was planned as a weekend window; it was actually **Friday, market
open** (`is_entry_allowed=True` on all six symbols, 138 `signal_log` rows in
15 minutes all carrying spread). Held.

**The reason, stated precisely, because it is not the obvious one:** alert loss
during a rebuild is not *likely* — it is **UNDETECTABLE**. A lost webhook is
silent, unretryable and unrecorded. Every other risk in this deploy announces
itself: a failed migration raises, a bad image fails healthcheck, a wrong stamp
shows in the row. This one would leave **a permanent absence to reason from**,
which this file has repeatedly shown is the hardest evidence to recover.

And there is **no upside pressure forcing the trade**: nothing is being
promoted, and the 10 invisible parity-v3 rows are currently *a safety
property* — `get_backtest_results()` filters to `CURRENT_ENGINE_VERSION`, so
while the container runs parity-v2 they cannot influence anything.

*(Subsequently measured: the webhook has been silent for 29 days, so the
hazard was empty in fact. That does not change the decision — it was the right
call on the information available, and the measurement is what converted an
unmeasured hazard into a known one. See the swiftalgo silence section.)*

### Pre-flight, complete and re-usable — EXCEPT the allowance

| item | state at 2026-09-04 |
|---|---|
| queue | **9 commits**, `cc9055d..0648f1e`, resolved from `git log` against the running image's commit — never from a list |
| running image | `sha256:d936077b2424` @ `cc9055d`, `RestartCount=0`, started 2026-09-02T01:29:33Z |
| `execute_trade.py` | untouched across all 9 |
| migration | **NO-OP confirmed** — VPS `backtest_results` already 28 cols with `profit_factor` (gained during the Stage 4 import). `walkforward_runs` 19 |
| disk | 24G free, backups 3.2G, **30** dangling images (26 on 08-22) — not blocking |
| rollback target | image `d936077b2424` @ `cc9055d` |

⚠️ **RE-READ THE ALLOWANCE IMMEDIATELY BEFORE THE REBUILD — do not reuse the
2026-09-04 number.** It stood at **remaining 8,780**, `resets_at`
**2026-09-10T12:43:44Z**, `expiry=592610s`, last read 2026-09-03T16:06:54Z, and
the meter has been **linear**: 10,000 → 9,980 (a 2×10-point probe) → 8,780
(6×200 on the 09-03 16:06 reconnect). Budget ≤1,400 for the restart (200 per
pair that fetches; 1,200 if one buffer is already current).

### What Saturday can and cannot verify — decide this BEFORE the run

**Verifiable with the market shut** — all change-specific:
migration no-op; stamps reading `parity-v3` / `measured-2026-09-median` /
`c0c905fc6c071dd4`; **selector row count 0 → 10** through
`get_backtest_results()`'s own query path (the observable this deploy exists to
produce); per-pair warm-up `[ig_allowance]` enumeration with a skip line naming
its reason for every pair that did not fetch; crontab md5; container health.

⏸️ **DEFERRED — live spread sampling.** `signal_log` rows carrying non-null
`spread` cannot be observed with the book shut. **This is a STANDING HEALTH
CHECK, not a verification of this diff** — nothing in the 9-commit queue
touches `_record_spread` or the Lightstreamer path. Do not report it as
passed, and do not report it as failed. **What closes it:** at the Sunday
~23:00 UTC reopen, confirm `signal_log` rows since the reopen carry non-null
`spread` across all six symbols — the same shape as CHECK 1's 111/111.

⏸️ **DEFERRED — anything depending on live ticks or entry-permitted hours**,
for the same reason and closed by the same reopen.

---

<!-- moved from CLAUDE.md 2026-09-04 — spread-table gate narrative — the gate passed and the table is now APPLIED -->

## ✅ GATE PASSED 2026-09-03 — spread table MEASURED AND FROZEN, not yet applied

The market-open filter shipped 2026-08-17 (`get_spread_samples(market_open_only=True)`,
predicate `market_hours.is_entry_allowed`). **The gate below was re-verified
against the frozen pool on 2026-09-03 and passed on all six symbols.** The
criteria are retained unchanged beneath — they are the standing spec, and the
one that was re-scoped (criterion 1, hour 21) is the reason this section is
worth reading before touching the table again.

**Full per-symbol enumeration, per-hour counts, the reproducibility check and
two out-of-criteria observations → `docs/OPERATIONS_LOG.md`.** That record
matters and is not filler: it carries the finding that US500 and US100 have
**zero dispersion** in the window (median = p90 = max on 1,074 and 906
samples), i.e. a broker-fixed spread rather than a distribution — which means
no percentile of this pool can give those two a tail.

---

<!-- moved from CLAUDE.md 2026-09-04 — pass-A staging, the gate acceptance criteria and the pass-A status table — all superseded by pass B -->

### ⏸️ PASS A OF TWO — nothing is applied yet, and that is deliberate

**Nothing in the engine reads this table.** `engine.py` is untouched,
`CURRENT_ENGINE_VERSION` is unchanged, `SPREAD_COSTS` is intact, and
`CURRENT_SPREAD_MODEL` **still reads `flat-roundtrip-dollars-UNCALIBRATED`**
because that is still exactly what the engine does. The name
`measured-2026-09-median` is **registered in `spread_model.py`'s History
comment only**. Flipping the stamp before the engine changes would mislabel
every row written in between — which is the single failure the stamp exists to
prevent.

**Pass B, a separate change:** apply the table in `engine.py` (one-way, at
entry, in price units — not a flat dollar deduction at exit), recalibrate
`NORMAL_SPREADS`, flip `CURRENT_SPREAD_MODEL`, and **bump `engine_version`** —
changing how spread is applied IS a structural change.

**Why not on 2026-08-17's pool:** n was fine (65–89/symbol, and the filtered
distribution has only 2 distinct values, so the median is statistically
solid). **Coverage was not.** Hours **18:00–22:00 UTC had ZERO samples on
every symbol** — including the ~21:00 UTC daily rollover, the most reliably
wide weekday period there is. A median built then would not be thin, it would
be **biased low**: the same error as calibrating on the shut book, opposite
sign, and harder to catch because the number looks plausible.

### ✅ The allowance exhaustion does NOT affect this gate — verified, not assumed

The IG historical allowance is at zero until 2026-09-01T04:02 UTC (see IG
Historical Allowance). **Friday's coverage check is unaffected**, and this was
confirmed two ways rather than reasoned about:

- **By code.** `signal_log.spread` comes from
  `live_signal_loop.py:382` → `candle_stream.get_spread()`, which reads the
  module-level `_last_spread` buffer. That buffer is written only by
  `_record_spread`, called from the **Lightstreamer tick handler**
  (`candle_stream.py:578`) — the same function that upserts the `candle_stream`
  heartbeat. It is never written by `_rest_fetch`. BID/OFR arrive on the tick
  stream, which draws no historical allowance.
- **By observation, which is the part that matters.** In the 8+ hours entirely
  *after* the allowance hit zero, **381 of 381 `signal_log` rows carry a
  non-null spread** across all four FX symbols. A code-reading alone would have
  been the same shape of argument this file repeatedly warns about; the row
  count is the positive signal.

So the two-week coverage accumulation continues through the dead-allowance
week. The only thing at risk from the exhaustion is candle **warm-up** on a
reconnect, not spread sampling.

### Acceptance criteria — ALL must hold

1. **Every hour in which entry is PERMITTED must be represented — that is
   00:00–20:00 and 22:00–23:00 UTC**, and **18:00–20:00 plus 22:00
   specifically present**. This is the criterion that failed on 2026-08-17
   (evening hours genuinely empty), and it is the criterion that was
   **RE-SCOPED on 2026-08-31** — see below.

   > 🔴 **HOUR 21 IS EXCLUDED BY CONSTRUCTION, NOT BY THIN DATA. Do not wait
   > for it; it will never arrive.** `get_spread_samples(market_open_only=True)`
   > filters on `market_hours.is_entry_allowed`, and the 21:00 rollover gate
   > sets that **False for the whole hour, every day, all instruments**. A
   > market-open-filtered pool therefore **cannot** contain an hour-21 sample.
   > Measured 2026-08-31: hour 21 is empty on all six symbols in the filtered
   > pool, while the **raw** pool holds 53 hour-21 EURUSD samples and
   > `signal_log` shows every hour-21 row on 08-24→08-27 carrying a non-null
   > spread (EURUSD 21/21, GBPUSD 8/8, US500 7/7, …). The data was collected;
   > the filter discards it. Verified directly:
   > `is_entry_allowed('EURUSD', Wed 21:00) = False`, `20:30` and `22:00` both
   > `True`.

   **Consequence, stated so nobody later reads it as a gap: the cost model
   will have NO rollover-hour data, and that is CORRECT.** The model prices
   trades the bot can actually place, and it never places one in hour 21. This
   is the same parity argument that chose `is_entry_allowed` over
   `is_market_open` as the filter in the first place — the constant feeds a
   cost model for placeable trades, not a description of the market. An
   hour-21 median would price a trade that cannot exist, and (per CHECK 2's
   measurement: FX widening 11–19x in that hour) would bias the table **high**
   exactly the way the shut-book and Sunday-reopen samples do. Those samples
   are already excluded here for the same reason and by the same predicate.

2. **Every weekday Mon–Fri represented.**
3. **≥ ~480 samples/symbol** after filtering (~97/day × 5 trading days).
4. **If any PERMITTED hour is still empty: do NOT build.** Report which hours,
   and wait. Hour 21 being empty is not such a case and never will be.

### Preference: two weeks, not one

One Mon–Fri cycle is the *minimum* — it gives ~20 observations per hour. Two
weeks gives **~40 per hour** and a realistic chance of catching a news day
(NFP/CPI/FOMC), which is where the tail actually lives. Build at one week only
if something downstream is blocked on it; otherwise prefer two.

### When it is built — status after pass A (2026-09-03)

| item | pass A | note |
|---|---|---|
| name makes **median-only** explicit | ✅ | `measured-2026-09-median`, registered in `spread_model.py`'s History comment. **Not yet stamped** — `CURRENT_SPREAD_MODEL` stays on the flat constant until pass B, because the stamp must describe what the engine does |
| `spread_table_sha` populated | ✅ | `c0c905fc6c071dd4`, recorded as `MEASURED_SPREADS_2026_09_SHA` and re-derivable from the dict |
| provenance in code per symbol | ✅ | `_PROVENANCE` (n, p90, max) + `_WINDOW` (bounds, filter, source, measured_at) |
| commit message and script comment state the tail is uncalibrated | ✅ | both, plus a block in `spread_model.py` and the head of this section |
| **applied in `engine.py`** | ⏸️ **pass B** | one-way at entry in price units, replacing the flat exit deduction |
| **`NORMAL_SPREADS` recalibrated** | ⏸️ **pass B** | still ~5x too wide, still the reason the webhook spread filter would block nothing even if it received a value |
| **`engine_version` bumped** | ⏸️ **pass B** | changing how spread is applied IS structural |

---

<!-- moved from CLAUDE.md 2026-09-04 — the webhook_log measurement that established the swiftalgo silence, and the retirement reasoning -->

#### ⛔ SWIFTALGO IS RETIRED — the silence is a DECISION, not an outage

**The TradingView source was retired by the operator.** The silence from
2026-08-06 is **expected**. There is nothing to diagnose and nothing to
restore. **Do not investigate it as an outage** — this session came within one
prompt of doing exactly that, and a future reader finding two rows flipped on
2026-09-04 plus a month of silence will be tempted the same way.

**ids 11 and 13 set `status='inactive'` on 2026-09-04T10:20:58Z.** They read
`active` until then, which asserted something false — the same class as the
id-379 marker that read as a result and wasn't.

`inactive` was used deliberately, and **a new value such as `retired` would
have been unsafe.** `webhook/receiver.py:265` is
`status = strategy_row.get("status", "active")`, and the only branches are
`inactive` (blocks) and `paper` (paper path) — **anything unrecognised falls
through to LIVE EXECUTION.** That is finding 4's fail-open default. `inactive`
is the only value with an explicit blocking branch, and 18 rows now carry it.

⚠️ **`active_strategy` has NO notes column**, so those two rows carry a status
and a bare `updated_at` and nothing else. This section is the only place the
reason exists.

**There are now ZERO `status='active'` rows in the roster** — 18 `inactive`,
13 `paper`. Nothing in the system trades live.

**The receiver machinery is left DORMANT, deliberately.** It is harmless, costs
nothing, and is there if a source is ever wired up again. Removing it would
mean touching the execution path.

*(The measurement that established the silence is retained below — it is what
converted an assumption into a fact, and its shape is reusable.)*

**Measured 2026-09-04, unrestricted — the whole `webhook_log` table, no date
or hour filter.** "Rostered active" and "receiving alerts" are two different
claims and only the first was ever checked.

| | |
|---|---|
| last arrival, **any** symbol / **any** strategy / **any** result | **`2026-08-06T00:01:06Z`** (US500, `BLOCKED session_filter`) |
| last EURUSD arrival | `2026-08-05T14:19:01Z` |
| last webhook-sourced trade | `2026-08-05T14:19:03Z` |
| arrivals in the **last 30 days** | **EURUSD 1, US500 1** — and both ARE those final rows |
| arrivals in the **30 days before that** | **EURUSD 105, US500 60** |
| rows in `webhook_log` since 2026-08-06 | **1**, which is the 08-06 row itself |

Monthly, whole table: `2026-05` 5, `2026-06` 188, `2026-07` 170, `2026-08`
**19** — then nothing. **The path went from ~5.5 arrivals/day to zero,
overnight, and stayed there for 29 days.**

This is not "a quiet hour". The upstream TradingView alert has stopped firing
— expired, deleted, or otherwise broken — and **no code in this repo would
ever have told anyone.** The 2026-08-21 verification in this section's heading
confirmed the `active_strategy` ROWS exist; it did not and could not confirm
that anything arrives.

⚠️ **Read every claim in this file about swiftalgo being "live" against that
date.** The rows are active, the routing works, the filters work — and there
has been no traffic to route since 2026-08-05.

**~~Cause not yet diagnosed.~~ CAUSE KNOWN: the operator retired the source.**
No investigation is warranted. Corroborating: `git log --since=2026-07-25
--until=2026-08-14` contains **only two commits, both docs** (the 2026-08-12
audit write-ups) — **no code change was involved and none should be looked
for.**

**Consequence for deploys, recorded because it inverts a risk assessment:**
the "a rebuild loses an in-flight webhook" hazard is, right now, **empty** —
nothing has arrived in 29 days. That does NOT retroactively justify rebuilding
during market hours; it means the hazard was unmeasured in both directions
until someone looked.

---

<!-- moved from CLAUDE.md 2026-09-04 — the 2026-09-04 index level check and the ROW-based source comparison — the latter superseded by the unique-observation recompute below it -->

### It clears the index blocker — verified by PRICE LEVEL, not by name

| symbol | Dukascopy instrument | last close | IG 2026-08-23 | ratio | |
|---|---|---|---|---|---|
| US500 | `INSTRUMENT_IDX_AMERICA_E_SANDP_500` | **7674.60** | 7671 | **1.000** | ✅ index scale |
| US100 | `INSTRUMENT_IDX_AMERICA_E_NQ_100` | **29354.15** | 29289 | **1.002** | ✅ index scale |
| DAX | `INSTRUMENT_IDX_EUROPE_E_DAAX` | **26226.65** | 26108 | **1.005** | ✅ index scale |

**These are indices, not ETF proxies** — the SPY/QQQ/EWG defect that voided ids
29/30 is absent. Depth: **45,485–45,700 M15 bars, 23.9 months** on all three,
against a requirement of ~10 (`WF_TRAIN_MONTHS=6` + `WF_MIN_WINDOWS=4`).

⚠️ Checked by level against the 08-23 snapshots, exactly as the blocker
demands. The name never proved anything and still doesn't.

### It is a far better execution-matched series than Twelve Data

Identical-timestamp bars only, Dukascopy mid built as `(bid+ask)/2` — the same
construction as `engine.py:139-156`, so there is no bid/mid confound. Both legs
measured against the same IG stream mid. **All values in pips.**

| symbol | leg | n | mean | stdev | IQR | **median abs err** | **% bars >3 pips** |
|---|---|---|---|---|---|---|---|
| EURUSD | **Dukascopy** | 4280 | **−0.274** | 1.283 | **0.45** | **0.20** | **5.0%** |
| EURUSD | Twelve Data | 3207 | +3.210 | 1.018 | 0.96 | 3.30 | **65.8%** |
| GBPUSD | **Dukascopy** | 4340 | **+0.129** | 1.088 | **0.65** | **0.30** | 5.9% |
| GBPUSD | Twelve Data | 3379 | +0.340 | 1.035 | 0.92 | 0.55 | 1.9% |
| AUDUSD | **Dukascopy** | 3609 | **−0.258** | 1.232 | **0.45** | **0.25** | **5.5%** |
| AUDUSD | Twelve Data | 2470 | +2.434 | 0.749 | 0.80 | 2.44 | 18.5% |
| USDCAD | **Dukascopy** | 2858 | **+0.349** | 1.835 | **1.00** | **0.50** | **7.1%** |
| USDCAD | Twelve Data | 2878 | −0.936 | 1.444 | 1.10 | 0.65 | 13.1% |

**Usable overlap: 2026-07-08 → 2026-09-04, 58 days** — bounded by how long the
bot has been capturing `candle_source_compare`, not by Dukascopy.

**The systematic vendor offset is GONE.** Every Dukascopy mean is **sub-pip**
(0.13–0.35) against Twelve Data's +3.210 EURUSD and +2.434 AUDUSD — an
**11.7× and 9.4×** reduction. That offset was the named residual behind
`parity-v3`, and on EURUSD/AUDUSD it was larger than the entire spread the
engine models.

🔴 **READ THE STDEV COLUMN CAREFULLY — it is the one place Twelve Data wins,
and it is misleading.** Dukascopy's stdev is higher on all four, but its
**IQR is roughly half** and its **median absolute error is 5–16× smaller**.
The higher stdev is **entirely tails**: 5–7% of Dukascopy bars carry a large
error, while Twelve Data is *uniformly* displaced — **65.8% of its EURUSD bars
are more than 3 pips from IG mid**, which is the +3.2 offset showing up as
near-universal error. A tighter core with a thin tail beats a wide, biased
body for SL/TP trigger evaluation. GBPUSD is the single exception (1.9% vs
5.9% beyond 3 pips) and should be looked at again before any build.

---

<!-- moved from CLAUDE.md 2026-09-04 — the four-way tail investigation (hour-of-day, cross-symbol coincidence, persistence, capture gaps) and the GBPUSD caveat reversal -->

### ✅ THE TAIL IS RESOLVED — non-traded hours plus single-bar artifacts

**Verdict: CONFINED TO NON-TRADED HOURS, with the remainder single-bar
artifacts. Not real market divergence, and not a Dukascopy corpus defect. No
cleaning step is justified — every bar is kept.**

🔴 **First, a correction to the numbers in the section above.** The ">3 pips on
5–7% of bars" figure was measured on RAW `candle_source_compare` rows, and that
table logs **once per strategy CHECK**, not once per bar. Deduplicating to one
observation per `(symbol, minute)`:

| | raw rows | distinct | factor |
|---|---|---|---|
| overall | 5,062 (EURUSD) | 3,892 | **1.30×** |
| **the tail bars specifically** | 213 (EURUSD) | **16** | **13.3×** |

**The tail was over-represented tenfold relative to the data as a whole.** The
same divergent timestamps were re-logged across many cycles — consistent with a
stale stream buffer being read repeatedly. **Deduplicated, the true tail rate
is 0.4–0.8%, not 5–7%.** This is the dedup caveat `get_spread_samples`'
docstring already warns about, hit in a new place.

**(a) Hour-of-day — decisive.** Pooled tail rate by UTC hour:

| hour | 21:00 | 20:00 | 16:00 | every other hour |
|---|---|---|---|---|
| tail rate | **9.9%** | 1.4% | 1.3% | **≤0.8%**, thirteen hours at 0.0% |

**Hour 21 is the daily rollover** — the hour FX is already measured widening
**11–19×**, and the hour `is_entry_allowed` is False for every instrument every
day. 39 of ~100 pooled tail timestamps sit there. Share of each symbol's tails
falling in hours the bot may not enter: **GBPUSD 84%, USDCAD 67%, AUDUSD 31%,
EURUSD 12%**.

**(b) Cross-symbol coincidence — the strongest discriminator.** Of 66 distinct
timestamps carrying a tail bar, **84.8% appear on ONE symbol only**; 10.6% on
two, 1.5% on three, **3.0% (2 timestamps) on all four**. Against 2,620
timestamps observed on all four symbols, independence predicts **0.000**
all-four coincidences and **2** were observed. So there are exactly two genuine
market-wide events; **the other 85% is per-symbol scatter, not a feed-level or
market-level fault.**

**(c) Persistence — bad ticks, not repricing.** Single-bar runs: EURUSD 93%,
GBPUSD 93%, AUDUSD **100%**, USDCAD 95%. Longest run anywhere: **3 bars**. A
genuine repricing persists; these revert on the next bar.

**(d) Our own capture's gaps.** Tail bars within 60 min after a >1h gap in our
IG capture: EURUSD 0%, AUDUSD 15%, GBPUSD 19%, USDCAD 24%. A real contribution
— **the IG side is our own capture with its own reconnects** — but not the
dominant term.

#### GBPUSD specifically — the caveat is answered, and it reverses

GBPUSD was the one symbol where Twelve Data had the thinner tail (1.9% vs
5.9%). **84% of GBPUSD's tail bars fall in hours the bot cannot enter.**
Restricted to entry-allowed hours:

| GBPUSD, `is_entry_allowed` hours only | n | mean | stdev | >3 pips |
|---|---|---|---|---|
| **Dukascopy vs IG mid** | **3,745** | **−0.046** | **0.419** | **0.1%** |
| Twelve Data (all hours, for reference) | 3,379 | +0.340 | 1.035 | 1.9% |

**stdev 0.419 against 1.035 — Dukascopy is ~2.5× tighter on the hours that
actually matter.** The caveat was an artifact of including hours the bot never
trades.

#### Why no cleaning step

The single-bar spikes are bad-tick-shaped, but they are 0.4–0.8% of bars,
mostly in hours never traded, and **the comparison is symmetric — it cannot say
which feed is wrong.** Removing them would be editing raw market data on a
guess. `is_entry_allowed` governs ENTRIES, not candle availability: a backtest
needs continuous bars to evaluate holds across excluded hours. **Every bar is
kept.**

### What this does NOT resolve

- ~~**Nothing is built.**~~ **BUILT 2026-09-04** — 12 `*_DUKA.json` caches,
  see below. Still no dependency added and nothing wired into the engine.
- **The 58-day overlap bounds the comparison, not the corpus.** These n's come
  from the bot's own capture window; a longer verdict needs more capture time,
  not a bigger pull.
- **Tick data was deliberately not pulled.** Two years of tick for four
  symbols is gigabytes and is not needed for this question. It is worth
  revisiting for the intrabar-ordering assumption `parity-v2` currently
  handles pessimistically (`intrabar_priority='sl'`) — **later, not now.**

---

<!-- moved from CLAUDE.md 2026-09-04 — the two dated verifications of the gap-backfill fix — the post-deploy enumeration and the real-reconnect ordinary-gap case -->

#### ✅ VERIFIED 2026-09-02 01:27–01:32 UTC — restart cost HALVED, 1,400 not 2,800

Enumerated per pair, per the corrected predicate. Deploy `cc9055d`,
image rebuilt 01:27:25 UTC.

**(1) One `[ig_allowance]` line per pair that reached IG — SEVEN, named:**

| pair | remaining after its call |
|---|---|
| AUDUSD/15MIN | 5,590 |
| EURUSD/15MIN | 5,390 |
| GBPUSD/15MIN | 5,190 |
| US100/15MIN | 4,990 |
| US500/15MIN | 4,790 |
| US500/HOUR | 4,590 |
| USDCAD/15MIN | 4,390 |

All seven `source=IG REST`, zero yfinance fallback, zero quota errors.

**(2) A skip line naming its reason for every pair that did NOT fetch — SEVEN,
the same seven, all in the backfill pass:**

```
[candle_stream] gap backfill AUDUSD/15MIN: skipped, no REST request —
    buffer current — newest bar is 0 bucket(s) back, nothing complete is missing
```
…identically for EURUSD/15MIN, GBPUSD/15MIN, US100/15MIN, US500/15MIN,
US500/HOUR, USDCAD/15MIN. **No pair is silent in both lists** — that was the
case worth checking, and it did not occur.

**(3) Remaining delta == 200 x (pairs that fetched), from the enumeration:**
5,790 → 4,390 = **1,400 = 200 x 7**. Backfill contributed **0**.

`ig_allowance` line count for the whole boot: **7**, not 14. Non-skipped
backfill fetches since restart: **0**.

**Against the pre-change baseline: 2,800 → 1,400.** The weekly allowance now
funds ~7 restarts instead of 3.

Rest of the post-deploy check, every item a positive observation:
- **finding 29 full import check, in-container, before AND after** — 17/17
  modules import clean both times (the local check was partial: no fastapi, so
  `main` and `webhook.receiver` were never exercised there). `STRATEGIES: 34`,
  `_bars_missing` callable in the image.
- in-container `/etc/cron.d/trading-bot` md5 **`0f1cc206193f5d30341c3db530357b06`**,
  byte-matching the committed `scripts/crontab`. One active line, the 06:10
  Stage E job.
- `/app/ig_allowance.py` present.
- stamps unchanged: **`parity-v2` / `paper-v2` /
  `flat-roundtrip-dollars-UNCALIBRATED`**.
- both heartbeats resumed after the restart — `candle_stream` 01:30:39,
  `signal_loop` 01:31:51 (its pre-restart beat was 01:26:38; the post-restart
  one was **waited for**, not inferred).
- spread sampling flowing: **13 of 13** `signal_log` rows since the restart
  carry a non-null spread, all six symbols present (EURUSD 5, US500 3,
  GBPUSD 2, AUDUSD 1, US100 1, USDCAD 1).
- `localhost:80` 200, `/health` 200, `/webhook` 405; all three containers up.

#### ✅ ORDINARY-GAP CASE CLOSED 2026-09-03 — a real reconnect, enumerated

The burn window could not test this fix: it held **zero disconnects**, and
`_backfill_gap` runs only from `_reconnect_supervisor`, once per connect — so a
**pre-change** container would have burned zero in that window too. The window
was non-diagnostic. A real reconnect then supplied the missing observation:

```
2026-09-03T15:59:53Z  [candle_stream] disconnected — will reconnect
2026-09-03T16:06:52Z  [candle_stream] connected
```

- **6 pairs FETCHED** (AUDUSD/EURUSD/GBPUSD/US100/US500/USDCAD 15MIN), each
  `buffer now 355 (source=IG REST)` — genuinely stale after seven minutes and
  correctly **not** skipped.
- **1 pair SKIPPED** — US500/HOUR, `buffer current — 0 bucket(s) back`.
- Meter **9,980 → 8,780 = 1,200 points**, against 1,400 pre-change.

`_bars_missing` did exactly what it exists to do on a real gap: skipped the one
current buffer, fetched the six that were not.

⚠️ **The STORM case is still UNTESTED.** 2026-08-28 was 511 backfills from
reconnects *seconds* apart against buffers a previous reconnect had just
filled. One seven-minute outage does not exercise that path. Do not read this
as closing it.

**⏸️ HOLD — the finding-38 probe is deliberately NOT run.** Observe the
post-change daily burn first. Pre-change it was ~4,210 per 18 hours with no
restart; if change 1 works that should fall sharply, and the size of the drop
is what says how much of the ~2,790 spare is genuinely free rather than
reserved against reconnects. Budget the probe against the observed rate, not
against the headline remaining.

---

<!-- moved from CLAUDE.md 2026-09-04 — the container-overlay backup defect write-up and the backup-table discipline narratives -->

#### ⛔ `import_stage4.py`'s rule-5 backup went to the CONTAINER, not the host

**Found 2026-09-04 by listing the host directory after the import, not by the
run reporting a problem — it reported success.** `DEFAULT_BACKUP_DIR` is
`/home/ubuntu/backups`, a HOST path, but gotcha 3 forces the script to run
INSIDE the container (the VPS `trades.db` is root-owned). Inside, that path
resolves to the container's own writable layer: **ephemeral, invisible to the
host, absent from this table, and destroyed by the next rebuild.** Two backups
totalling 650 MB landed there. A rollback would have had nothing to roll back
to, and the console said `integrity_check ok` both times.

The two gotchas are individually correct and jointly produce this: "backup on
the host, import in the container" (gotcha 2) versus "the DB is root-owned so
you must be in the container" (gotcha 3). Fixed by an `st_dev` check —
`/app/database` is the bind mount, so a backup dir on a different device is on
the overlay, and the script now REFUSES instead of writing a backup that will
not exist when it is needed.

All verified `integrity_check ok`. **None is disposable.** Take new ones with
the SQLite online backup API (`Connection.backup()`), never `cp` — `cp` on a
live DB with an open WAL can produce a torn copy.

**Directory now totals ~2.3 GB** (8 files, 28 GB free on `/`). The Aug-17 file
sat here undocumented for four days; an unlisted 320 MB file is how the next
disk-pressure investigation starts from a wrong baseline. If a backup is taken,
it goes in this table in the same change.

**It happened again.** `trades.bak-20260821T190857Z.db` was found unlisted on
2026-08-22, one day after the rule above was written into this table — and its
*purpose* is now unrecoverable, which is the part that matters. Its contents are
byte-identical in row counts to the 18:41 backup taken 27 minutes earlier, so
it is very probably a second pre-deploy snapshot from the same session, but
"very probably" is exactly what a record exists to replace. `import_stage4.py`
now prints a warning naming this table on every backup it takes; that is a
prompt, not a guarantee.

⚠️ **Whoever writes the next backup: the VPS `database/trades.db` is owned by
`root`, not `ubuntu`.** A backup or import run as `ubuntu` on the host fails
with `sqlite3.OperationalError: attempt to write a readonly database`. Run it
inside the bot container (`docker exec trading_bot-bot-1 …`, same file via the
shared `./database` volume) or as root. Discovered by the failure on
2026-08-22, not by reading permissions.

`/home/ubuntu/backups` was root-owned `755` until 2026-08-21, so a backup run
as `ubuntu` failed outright. Directory is now `ubuntu:ubuntu`; the pre-existing
files keep their original ownership.

---

<!-- moved from CLAUDE.md 2026-09-04 — the Twelve Data price-level residual analysis (mean and second moment) — the corpus it measured has been replaced by Dukascopy -->

#### ⚠️ NAMED RESIDUAL — the price series identity is ASSUMED, not shown

The symmetric application is correct only if the vendor caches carry a **mid**.
`candle_source_compare` cannot settle it. Restricted to rows whose yfinance and
IG-stream candles share an **identical timestamp** (removing a drift term worth
24–43 min of mean gap on FX), against IG stream mid:

| symbol | n | mean delta | half-spread | ratio |
|---|---|---|---|---|
| AUDUSD | 2451 | +2.434 pips | 0.30 | **+8.1×** |
| EURUSD | 3182 | +3.209 pips | 0.30 | **+10.7×** |
| GBPUSD | 3345 | +0.340 pips | 0.45 | +0.76× |
| USDCAD | 2840 | −0.935 pips | 0.65 | **−1.44×** |

A bid series reads −1.0× on **every** symbol; an ask series +1.0×. **These
signs disagree and the magnitudes span 0.76×–10.7×**, so no bid/ask hypothesis
fits — these are symbol-specific **vendor price-level offsets**. Mid is assumed
because the data cannot resolve it.

##### 📏 The residual's SECOND MOMENT — it VARIES, and that is what decides the cost

The mean alone supports two opposite conclusions. A near-**constant** offset
largely cancels: entry, stop and TP all shift together and P&L is a function of
**differences**, so a uniform 3.2-pip EURUSD shift would be close to cosmetic.
An offset that **varies bar to bar** is unmodelled noise on every trigger
evaluation. Measured on the same identical-timestamp subset, in pips:

| symbol | n | mean | **stdev** | IQR | full spread | **stdev/spread** | IQR/spread |
|---|---|---|---|---|---|---|---|
| EURUSD | 3182 | +3.209 | **1.021** | 0.97 | 0.60 | **1.70×** | 1.62× |
| GBPUSD | 3345 | +0.340 | **1.039** | 0.93 | 0.90 | 1.15× | 1.03× |
| AUDUSD | 2451 | +2.434 | **0.750** | 0.80 | 0.60 | 1.25× | 1.33× |
| USDCAD | 2841 | −0.935 | **1.448** | 1.10 | 1.30 | 1.11× | 0.85× |

Mean within-symbol stdev **1.093 pips** against a pooled 1.978 — a constant
per-symbol offset would drive the within-symbol figure toward zero, and it does
not go there.

🔴 **VERDICT: VARYING AND MATERIAL, not constant-and-cancelling.** The
bar-to-bar variation is **1.1×–1.7× the ENTIRE spread parity-v3 models** on
every one of the four pairs — EURUSD's 1.70× is the number that decides it. So
the corpus carries per-bar price noise larger than the cost just modelled, and
it lands directly on SL/TP trigger evaluation, where it is not a wash.

**What this does NOT do:** it does not invalidate parity-v3. Modelling spread
correctly is still correct. It says the *next* parity gain is bigger than the
one just banked, and that any residual backtest-vs-live divergence should be
attributed here before anywhere else.

**The bigger number this exposes, and it is NOT fixed:** on EURUSD and AUDUSD
the backtest corpus differs from tradeable IG prices by **more than the spread
this commit models**. Spread parity is now done; **price-level parity is not**.

**Still divergent at parity-v3:** entry LAG (live fills 25–55 min later),
weekend handling, session windows, and that price-level offset.

Full run record, the contaminated first cut, and the stamp read-back →
`docs/OPERATIONS_LOG.md`.

`get_backtest_results()` filters to the current version by default;
`engine_version=None` reads all (archive/inspection only — dashboard page 04).
`score_strategies()` raises `MixedEngineVersionError` rather than ranking
across models.

---

<!-- moved from CLAUDE.md 2026-09-04 — the Dukascopy re-run's per-strategy comparison, the matched-candle-count span control, and the 8-of-8 count reconciliation -->

### Old vs new, per strategy

| symbol | tf | strategy | old PF | new PF | Δ | old wf | new wf | trades o/n |
|---|---|---|---|---|---|---|---|---|
| GBPUSD | 15MIN | ema_pullback | **2.2452** | **0.4837** | **−1.762** | REJECT | REJECT | 23/85 |
| US500 | HOUR | stoch_rsi_confluence | 0.1041 | 0.6630 | +0.559 | REJECT | **FRAGILE** | 20/36 |
| EURUSD | 15MIN | supertrend | 1.1536 | 0.8129 | −0.341 | REJECT | REJECT | 56/173 |
| EURUSD | 15MIN | bb_squeeze | 1.1033 | 0.7710 | −0.332 | REJECT | REJECT | 45/79 |
| USDCAD | 15MIN | williams_r | 0.8671 | 0.7010 | −0.166 | FRAGILE | **REJECT** | 209/491 |
| US500 | HOUR | williams_r | 0.9281 | 0.7796 | −0.149 | REJECT | REJECT | 57/121 |
| GBPUSD | 15MIN | williams_r | 0.8919 | 1.0280 | +0.136 | REJECT | REJECT | 219/424 |
| AUDUSD | 15MIN | williams_r | 1.0431 | 0.9254 | −0.118 | **MARGINAL** | **REJECT** | 234/467 |
| EURUSD | 15MIN | stoch_rsi | 0.9362 | 0.8579 | −0.078 | REJECT | REJECT | 199/453 |
| EURUSD | 15MIN | williams_r | 1.0670 | 1.1202 | +0.053 | REJECT | REJECT | 219/450 |
| **US100** | **15MIN** | **ema_pullback** | VOID | **1.4573** | — | — | **FRAGILE** | —/84 |
| **US500** | **15MIN** | **ema_pullback** | VOID | 0.9968 | — | — | REJECT | —/125 |

ids 29/30 have **no comparison** — their old figures were ETF-scaled and void.
They ran for the first time on real index data; **US100 `ema_pullback` is now
the highest-PF strategy in the batch at 1.4573, FRAGILE.**

**Still zero promotable.** Best walk-forward verdict anywhere is FRAGILE. The
only MARGINAL from the old run (AUDUSD `williams_r`) fell to REJECT.

### Span was NOT the explanation — controlled

The Dukascopy run used 49,803 candles against Twelve Data's 29,995, so span was
a confound. Re-ran every common strategy at **matched candle counts**:

| strategy | old (TD) | new (DUKA, full) | **ctrl (DUKA, matched)** |
|---|---|---|---|
| GBPUSD ema_pullback | 2.2452 | 0.4837 | **0.4544** |
| AUDUSD williams_r | 1.0431 | 0.9254 | **0.8168** |
| USDCAD williams_r | 0.8671 | 0.7010 | **0.6307** |
| EURUSD williams_r | 1.0670 | 1.1202 | **1.2166** |
| US500 stoch_rsi_confluence | 0.1041 | 0.6630 | **0.6605** |

**The matched-count column tracks the full-span column, not the old column.**
The corpus is the cause; the extra span is not.

*(Those 10 control rows were deleted from the local DB before export — they are
a methodological control, not Stage 4 results, and leaving them would put two
rows per strategy on the VPS at different candle counts. Their numbers are
here, which is where their value is.)*

### Counts — 8 of 8 derived expectations matched exactly

| item | expected | actual |
|---|---|---|
| full 84-cell maps | 5 | **5** |
| stability rows from those | 420 | **420** |
| `REDUCED_GAUNTLET` | 7 | **7** |
| `NOT_RUNNABLE` | 1 | **1** |
| `stability_map` total | 428 | **428** |
| `backtest_results` | 12 | **12** |
| `walk_forward` | 12 | **12** |
| `permutation` | 12 | **12** |

Derived at run time from `roster.db` + `STABILITY_GRIDS`, not carried. id 28
`ny_session_momentum` raises `EngineContractError` on **both** corpora
(TwelveData idx=1103, Dukascopy idx=9523) — a corpus-independent strategy
defect, re-verified this pass.

Import: **12 + 477 inserted**, re-import **0 inserted / 489 skipped**, VPS
`backtest_results` 268,129 → 268,141. Backup `trades.bak-20260904T124236Z.db`.

---

<!-- moved from CLAUDE.md 2026-09-04 — the import-step scoping written before scripts/import_stage4.py existed -->

### The import step — SCOPED, NOT BUILT. Build before Stage 4 executes.

**What comes home:** only rows produced by the run — `backtest_results` and
`walkforward_runs` where `engine_version = CURRENT_ENGINE_VERSION` **and**
`run_at` / `created_at >= <batch start>`. Nothing else. The local DB also holds
5,329 pre-parity `backtest_results` and 276 `walkforward_runs`, 1,166 and 82 of
which are ETF-contaminated (finding 30); **none of that crosses**.

**In what form:** a standalone sqlite file with the same two table schemas, same
column names and order — `stage4_<UTCstamp>.db`. Same shape as
`export_roster.py`, and for the same reason: a file that can be inspected before
it is trusted.

⛔ **NEVER copy the local `trades.db` over the VPS one.** It would destroy the
live `trades`, `paper_trades`, `signal_log` and `active_strategy` tables. The
import is additive, row by row, or it does not happen.

**How rows are stamped.** Each already carries `engine_version`, `spread_model`,
`spread_table_sha` and `params_source` (roster / literal / grid / file-default).
The import must additionally record that the row was **produced off-host**:
`produced_on` (hostname), `imported_at`, and the `roster_snapshot` git HEAD the
params came from.

`walkforward_runs` can hold that in `extra_json` today. **`backtest_results`
cannot — it has no such field, and no cache-provenance columns either.** That is
finding 31, and it means the two pieces of work are the same piece: the columns
finding 31 proposes (`cache_file`, `cache_candle_count`, `cache_date_start`,
`cache_date_end`) are exactly what an imported row needs to be auditable.
**Build finding 31's migration first**, then the import.

**Import rules, all refusals rather than warnings:**
1. Refuse any row whose `engine_version` ≠ current — never mix trade models.
2. Refuse any row whose `spread_model` ≠ current — spread is a parameter, and a
   name can be kept while the numbers change (that is what `spread_table_sha`
   is for; compare it too).
3. Insert **without `id`** so the VPS autoincrement assigns fresh ones. Local
   ids are meaningless there and would collide.
4. **Idempotent**: skip a row whose natural key already exists —
   `(strategy_name, symbol, timeframe, params_json, run_at)` for
   `backtest_results`, plus `run_type` and `cache_file` for `walkforward_runs`.
   The microsecond timestamps make these effectively unique. Re-running the
   import must be a no-op, not a duplicate.
5. `Connection.backup()` the VPS DB first, never `cp` (open WAL → torn copy),
   and record the backup in the Database Backups table in the same change.
6. Read back and report counts after inserting. Do not infer success from the
   absence of an exception — see Unverified Controls.

**Verification, before trusting the first import:** an insert → read-back →
delete write test against the VPS, exactly as was done for `walkforward_runs` on
2026-08-22. That test found `spread_table_sha` was NULL on every row ever
written, which code-reading had missed.

---

<!-- moved from CLAUDE.md 2026-09-04 — the 2026-08-23 index-source survey — superseded, Dukascopy now serves all three indices at 15MIN -->

### Index data — where this leaves it

**IG serves all three indices at correct index scale** (verified live 2026-08-23
via market snapshots, which cost no historical allowance): US500 bid 7671.16,
US100 29289.2, DAX 26108.4 — against ETF caches of 729 / 706 / 40.59.

But nothing serves them at **15MIN over a walk-forward span** today:

| source | 15MIN indices | why not |
|---|---|---|
| Twelve Data free tier | ❌ | `SPX`/`NDX` → *"available starting with the Grow or Venture plan"*; `IXIC`/`GDAXI` invalid; **`DAX` resolves to a $47 NASDAQ ETF**. The SPY/QQQ/EWG map was what the free tier permits — fixing `SYMBOL_MAP` alone fixes nothing |
| yfinance | ❌ | Yahoo: *"The requested range must be within the last 60 days"* at 15m. ~1,560 bars vs the ~10 months `WF_TRAIN_MONTHS=6` + `WF_MIN_WINDOWS=4` needs |
| IG REST | ⏳ | correct scale, but allowance at zero and depth unmeasured |
| stream persistence | ⏳ | free and correct, but **forward-only** (~400 index bars/week ≈ 43 weeks to 10 months) |

✅ **yfinance 1h reaches 730 days, so US500/US100/DAX HOUR are correctly scaled
and backtestable TODAY** (`US500_HOUR_5000_yf.json` is `^GSPC`, verified). Only
15MIN is broken.

**Do not mix sources inside one cache file.** Twelve Data before date X and IG
after is two instruments in one file — the DAX/ETF defect with a subtler
signature. One source per symbol, recorded in the `cache_file` provenance
columns (`d6f1c8c`).

---

<!-- moved from CLAUDE.md 2026-09-04 — the 2026-09-02 allowance meter reading and the two zero-cost probe failures -->

### ✅ STATE AS OF 2026-09-02 — allowance RESET, 5,790 remaining, resets 2026-09-08T07:18 UTC

Measured with **one** request (EURUSD `MINUTE_15`, `numpoints=10`, 10 bars
returned), 2026-09-02 01:2x UTC:

| | |
|---|---|
| remaining | **5,790** of 10,000 (42.1% used) |
| reset time | **2026-09-08T07:18:53+00:00** (`expiry=539812s`) |
| window start | ~**2026-09-01T07:18 UTC** — the anchor MOVED from 04:02, exactly as the window shape predicts. Do not carry a remembered anchor forward; re-read `resets_at`. |
| spent this window | **4,210 in ~18 hours, with NO container restart** — ~21 gap-backfills at 200 points each. Finding 37 leaking in ordinary operation. |

⚠️ **Two probe attempts before this one cost ZERO** — both died client-side, no
HTTP left the box: `return_dataframe` is a **constructor** argument to
`IGService`, not a call argument to
`fetch_historical_prices_by_epic_and_num_points`, and without it `trading_ig`
runs `conv_resol()` and chokes parsing `MINUTE_15` as a pandas frequency
string. Third time this has bitten a probe. Mirror `_rest_fetch`'s construction
(`IGService(..., acc_type=..., return_dataframe=False)`), always.

⚠️ Creating a session in a probe **invalidates the `positions_poller` token**.
Known, accepted, still real — probe sparingly.

*(The exhausted-allowance block below is retained as the state it describes,
which is what the 2026-09-01 reset ended.)*

*(The 2026-08-25 exhausted-allowance state block → `docs/INCIDENT_HISTORY.md`.
It is what the 2026-09-01 reset ended, and it records that the allowance was
destroyed by a probe rather than by use — see finding 38.)*

---

<!-- moved from CLAUDE.md 2026-09-04 — the row-vs-unique recompute tables for the Dukascopy/Twelve Data source comparison -->

### 🔴 RECOMPUTED ON UNIQUE OBSERVATIONS 2026-09-04 — the row-based table was biased AGAINST Dukascopy

**The earlier three-way table was ROW-based.** Established from the data, not
assumed: it iterated `candle_source_compare` rows and looked each one up in
Dukascopy, so a bar observed N times contributed N deltas.

**The correct unit is one observation per `(symbol, stream_time)`** — the
comparison is bar-vs-bar, so the bar is the observation, not the row.

| symbol | rows | distinct `stream_time` | factor |
|---|---|---|---|
| EURUSD | 5,062 | 3,892 | 1.30× |
| GBPUSD | 5,123 | 3,947 | 1.30× |
| AUDUSD | 4,371 | 3,236 | 1.35× |
| USDCAD | 3,447 | 2,672 | 1.29× |

**The adoption decision does not merely survive — it strengthens.** On unique
observations Dukascopy wins **every metric on every symbol**, including stdev,
which was the one column Twelve Data won on the row basis:

| symbol | metric | ROWS duka / TD | **UNIQUE duka / TD** |
|---|---|---|---|
| EURUSD | mean | −0.274 / +3.210 | **−0.062 / +3.311** |
| EURUSD | **stdev** | 1.283 / **1.018** ← TD won | **0.624 / 0.857** ← duka wins |
| GBPUSD | **stdev** | 1.088 / **1.035** ← TD won | **0.712 / 1.048** ← duka wins |
| AUDUSD | **stdev** | 1.232 / **0.749** ← TD won | **0.501 / 0.749** ← duka wins |
| USDCAD | **stdev** | 1.835 / **1.444** ← TD won | **0.730 / 1.418** ← duka wins |

**Dukascopy's stdev roughly HALVES on dedup; Twelve Data's barely moves.** That
asymmetry is the whole story: the repeatedly-observed bars were precisely the
divergent ones, and they were divergent on the *Dukascopy-vs-IG* leg. Twelve
Data is *uniformly* displaced, so removing duplicates changes it hardly at all.

All four Dukascopy means are now within **±0.08 pips of zero**
(−0.062, −0.063, −0.047, −0.076).

---

<!-- moved from CLAUDE.md 2026-09-04 — the williams_r demotion record and its superseded-claim corrections -->

### The four williams_r instances moved live → paper (2026-08-21)

ids **22 EURUSD**, **32 GBPUSD**, **34 AUDUSD**, **36 USDCAD**, all 15MIN, all
`status='paper'` since `2026-08-21T18:41:31Z`.

**Reasons are in `active_strategy_history` rows 43, 44, 45 and 46 — one per
instance, each carrying its own live record, the parity-v2 comparison and the
paper-not-inactive rationale. Read those rather than a summary here.** This
file has been wrong about the roster before (US100 HOUR supertrend ran live and
undocumented for ~8 weeks); pointing at the history table instead of restating
it is deliberate.

One-line headline only: no profitable month pooled in three, best-ever bucket
PF 0.86, and `parity-v2` independently predicts PF < 1.0 on all four.

**Why `paper` and not `inactive`** — the one thing worth stating here because
it is a live operational fact, not history: the signal loop iterates
`get_active_strategies(symbol)`, which is `status IN ('active','paper')`
(`database/models.py:597`). A symbol with **no runnable row never reaches
`_check_symbol`**, and the spread sample is taken at the top of that function
(`live_signal_loop.py:369`) before any block check. **AUDUSD and USDCAD have no
other runnable row**, so `inactive` would have taken their spread sampling and
`candle_source_compare` to zero. EURUSD and GBPUSD carry other paper strategies
and were never at risk.

Verified post-change by positive signal, not silence: the 18:45 cycle logged
`Checked this cycle (11)` including all four williams_r keys, with AUDUSD
(`6e-05`) and USDCAD (`0.00013`) both still writing `signal_log.spread`.

**Params, still authoritative, still divergent from the docs.** GBPUSD id 32
runs `period=21`, not the `%R(14)` described further down this file, and not
the `period=14/-85/-15` of the 2026-07-09 FX expansion batch. 4th occurrence of
the params-divergence class — always pull params from `active_strategy`
(see Critical Rules).

| id | Symbol | Rostered params |
|----|--------|-----------------|
| 22 | EURUSD | `period=10, oversold=-90, overbought=-20` |
| 32 | GBPUSD | `period=21, oversold=-90, overbought=-20` |
| 34 | AUDUSD | `period=14, oversold=-85, overbought=-20` |
| 36 | USDCAD | `period=14, oversold=-85, overbought=-15` |

**Corrections to claims this table used to make** (retained — the claims
outlived the rows, and the AUDUSD ones are still cited elsewhere):
- AUDUSD "stability-map plateau (23 contiguous cells at PF>=1.1, not a spike)"
  — the contour is real (25 of 84 cells clear PF ≥ 1.1), but of those 84 cells
  the verdicts are FRAGILE 38, MARGINAL 34, REJECT 11, **ROBUST 1**. It is one
  robust point in a mostly-fragile field, not a robust plateau.
- AUDUSD "walk-forward ROBUST, 83.3% windows, 6 windows" — **there is no
  `walk_forward` row for `williams_r` on any symbol, VPS or local.** The
  headline verdict survives only inside a permutation row's `extra_json`; the
  per-window breakdown is unrecoverable. `walkforward_runs` was created
  2026-07-22, a week after the 2026-07-15 promotion.
- The MC figures (p5=$707, p95=$2621) do reproduce exactly from stored rows.

*(A duplicated fragment of an older three-row version of this table sat here
until 2026-08-21, restating the EURUSD/USDCAD/AUDUSD notes in a stale column
format. Removed, not edited — it was a second copy, and the reasons now live in
`active_strategy_history`.)*

---

<!-- moved from CLAUDE.md 2026-09-04 — the .db-shm/.db-wal sibling investigation -->

#### ℹ️ The `.db-shm` / `.db-wal` siblings are EXPECTED — do not treat them as litter

There are **12** of them in this directory, paired to 6 backups. They were
initially assumed to be leftovers from one `docker cp`. **That was wrong, and
the correct explanation matters because it means deleting them is futile:**
`Connection.backup()` reproduces the source's journal mode, the source is
`journal_mode=wal`, so **every backup is a WAL database and ANY read — even
`mode=ro` — recreates its `-shm` and `-wal` siblings.** Demonstrated
2026-09-04: they were moved aside, the `.db` verified self-contained
(`integrity_check ok`, 996 / 268,119 / 182 — matching its table row exactly),
and they **reappeared on the next read**.

**Decision: LISTED, not removed.** They are 32 KB and 0 bytes respectively —
~200 KB across all twelve, against a 3.5 GB directory. Removing them would be
undone by the next integrity check anyone runs, and a rule that silently
reverses itself is worse than a documented exception. **The backup `.db` files
do not depend on them** and never have; a 0-byte `-wal` holds no committed
frames.

**They are NOT backups and must never be counted as one.** This note exists so
that the next reader auditing this directory against the table above does not
find twelve unlisted files and conclude the table is incomplete.

⚠️ **A THIRD backup, `trades.bak-20260904T022739Z.db` (325,763,072 bytes), was
taken by the idempotency re-run and DELETED rather than kept.** It is a
post-import snapshot, identical in content to the live DB at that moment, and
keeping a 325 MB file that duplicates current state is not a record of
anything. Noted here so its absence is deliberate rather than unexplained.

---

<!-- moved from CLAUDE.md 2026-09-04 — the Stage-1 parity-v2 head — its SPREAD_COSTS paragraph was made false by parity-v3, which deleted the constant -->

Four commits: `e0f51f8` marking → `14c3c17` sizing → `0fdbe7e` contract →
`36fac3b` spread capture. The backtest was modelling a different strategy from
the one running live.

**What `parity-v2` does, the entanglement finding, the convergence table and
the four still-unmodelled mechanics → `docs/OPERATIONS_LOG.md`.**

One result from there is worth keeping in front of anyone reading this file:
**TP and reversal-exit MASK EACH OTHER.** Neither change alone explains the
result, so neither would have shown up in isolation — TP alone barely moves PF,
reversal-off alone is degenerate. Only together do they resemble live. AUDUSD
`parity-v2` PF **1.085** against live demo actual **0.71**: converging, still
flattering, spread the known residual. **Still not promotion evidence.**

The flat `SPREAD_COSTS` constant is deliberately LEFT IN PLACE and named
(`spread_model = flat-roundtrip-dollars-UNCALIBRATED`) — removing it would make
every backtest look better while being no more correct.

---

<!-- moved from CLAUDE.md 2026-09-04 — a profit_factor-on-VPS claim that a later same-day observation contradicts -->

⛔ **THE MIGRATION HAS NOT REACHED THE VPS.** It runs from `init_db()` at
container start and nothing has been deployed. The VPS `backtest_results`
still has no `profit_factor` column — verified 2026-09-04 by `PRAGMA
table_info`. **The Stage 4 import will need it there first**, since
`backtest_trades` does not cross (gotcha 5) and an imported row would land
with no PF and nothing to derive one from.

---

<!-- moved from CLAUDE.md 2026-09-04 — the completed-control roll-up, CHECK 3 and CHECK 1 heads — all passed, consolidated into one table in CLAUDE.md -->

## ✅ CONTROLS AWAITING FIRST REAL FIRE — THE LIST IS EMPTY

Every control that was waiting on a first production fire has been observed
firing, each by positive signal rather than inferred from silence: FX weekend
block (Sat 2026-08-22), 21:00 rollover gate (Sun 08-23, weekday Mon 08-24),
collector disable → IG warm-up (Mon 08-25), shadow spread gate (Mon 08-25).
Dated evidence table → `docs/OPERATIONS_LOG.md`.

**The shadow gate's standing rule, kept here because it governs live reads:**
`risk/spread_gate.py` runs with `ENFORCE=False`, so the string
`SHADOW spread gate: ratio ...` must **never** be the sole explanation for a
*missing* trade. Its first fire was on a **paper** signal that still logged as
`PAPER_BUY` — gate reported, trade taken. If a trade is ever missing and this
string is the only explanation, the shadow gate has been promoted by accident.

**Add a row to the archive table BEFORE deploying the next dated control, not
after** — the value of that table is that it was written while the control was
still unobserved.

## ✅ CHECK 3 — PASSED 2026-08-25. `CANDLE_SOURCE=ig_stream` is true end to end.

Both claims have evidence: the collector no longer runs (marker test,
2026-08-23 14:31 UTC), and `candle_stream` warm-up now reaches IG instead of
yfinance — **7/7 pairs `source=IG REST`, zero fallback, zero quota errors**
(2026-08-25 04:02 UTC). Full result block → `docs/OPERATIONS_LOG.md`.

**Why it is not merely a tidy-up record:** the collector was taking
100,800 points/week of a 10,000/week budget, so `_warm_up` and `_backfill_gap`
fell through to yfinance on every pair for the rest of the week.
`CANDLE_SOURCE=ig_stream` was half true — IG ticks, **yfinance seed data** —
which is the off-session index staleness the 2026-07-15 flip existed to fix.
Stopping the drain fixed it on the first attempt. That is the causal claim
tested rather than argued.

**The reset time is now read from `resets_at` on every successful response** —
see IG Historical Allowance for the current value. It had been arriving on
every response for the life of the system and was discarded by both consumers.

## ✅ CHECK 1 — FX market-hours block (deployed 2026-08-17) — VERIFIED IN FULL 2026-08-22/23

`_is_blocked` never blocked FX: `MARKET_CLOSE` holds only US500/US100/DAX/BTC,
so every FX symbol hit `.get(symbol) is None → return False` before reaching any
weekend rule. **21 weekend trades were placed as a result.** Fixed by
`market_hours.py` (`is_market_open` = venue fact, `is_entry_allowed` = our
policy). Findings doc finding 23.

**PASSED Sat 2026-08-22** (block itself) **and Sun 2026-08-23** (criterion 4,
re-scoped). Full result blocks → `docs/OPERATIONS_LOG.md`.

**Two things in that record are load-bearing and are the reason it was archived
rather than dropped:**
1. **Criterion 4 was MIS-SPECIFIED, not failed.** It asked for a non-null
   `signal_log.spread` on a Saturday, when the venue is shut and there is
   nothing to sample. It reported a false failure against a working control.
   This is the first instance of CRITERIA AGE AGAINST THE SYSTEM THEY MEASURE.
2. **The spread-sampling ordering is load-bearing**: the sample is taken before
   the block check and the blocked branch still calls `log_signal_check`. That
   is what keeps the thin reopen — the most expensive window we have — from
   going blind. Verified 111/111 FX rows non-null on the Sunday reopen.

The reopen spread measurements themselves are retained in the GATE section
below, where the spread table will read them.

---

<!-- moved from CLAUDE.md 2026-09-04 — the two cleared-drift deploy records and the Stage 4 dress-rehearsal head -->

## ✅ DEPLOY 2026-08-25 — queue SHIPPED, drift CLEARED

16 commits, `591dc3a..715bc18`, image `sha256:9da8a7927a09`. Full post-deploy
verification (six positive observations, none inferred from silence) →
`docs/OPERATIONS_LOG.md`.

**The one item worth repeating here:** the collector disable existed in the
container only as a `docker cp`, which Unverified Controls instance 3 says is
lost on rebuild. **This rebuild is what made it permanent.** The crontab md5
anchor below is how you check that a future rebuild has not silently reverted
it.

**The deploy queue must be resolved from `git log` against the running image's
commit, never from an enumerated list** — a list written here went stale within
one commit, and the queue had grown 5→16 between the note and the deploy.

## ✅ DEPLOY 2026-08-22 — earlier drift CLEARED

Image `sha256:42f5585b3e34` at `591dc3a`. Record → `docs/OPERATIONS_LOG.md`.
Kept as a pointer because "the image matches the repo" is an assumption every
verify-the-deploy step in this file makes, and the date it became true again is
worth knowing.

**Two costs recorded there that recur on every weekday rebuild:** the restart
burns IG historical allowance re-warming every buffer (prefer weekends), and
`python3 -c "import webhook.receiver"` **creates a fresh IG session on import** —
three such probes produced three session recreations. Probe imports sparingly.

## Stage 4 DRESS REHEARSAL — one strategy, 2026-08-23

AUDUSD 15MIN `williams_r` against a VPS roster snapshot. Run so that anything
surprising surprised us on one strategy rather than thirteen. It did.

**Headlines that govern Stage 4 planning** (full account → `docs/OPERATIONS_LOG.md`):
- **1m48s per strategy, not 27 minutes.** Thirteen strategies is under an hour.
  No case for parallelising, none for a reduced gauntlet on time grounds.
- **Two defects found and FIXED** (`40d716b`): the stability map persisted in a
  batch at the end (a crash at cell 80 of 84 lost everything), and
  `windows_json` was NULL on all 84 cells. Both now verified by reconstruction.
- **`parity-v2` makes AUDUSD materially worse**: REJECT 11→**50** of 84 cells,
  the single ROBUST cell **gone**. Risk of ruin 67.3–84.3% at $10/$500.
- **Round trip to the VPS is idempotent** — re-import inserted 0, skipped 92.

The operational sequence (export on the host, import in the container, the
root-owned-DB constraint) is in the Stage 4 re-validation section above, not in
the archive — it is a runbook, not a record.

---

<!-- moved from CLAUDE.md 2026-09-04 — the Monitoring Gaps entries in full, including the two struck-through corrections and the divergence-watchdog design record -->

- ~~**`candle_stream` staleness is unmonitored.**~~ **FALSE — corrected
  2026-08-20.** `scripts/watchdog.py::main` has called
  `check_heartbeat(..., "candle_stream", "stale_candle_stream")` since commit
  `1abcdf5` (**2026-07-08**), and `check_heartbeat` early-returns outside
  Sun 22:00 – Fri 21:00 UTC, so it is already the market-hours-aware rule this
  entry asked someone to build. The 2026-08-15 weekend observation
  (last beat 05:04 UTC, silent after) is that gate working, not a gap. This
  bullet was wrong for six weeks — a monitoring gap recorded as outstanding
  while the monitor existed is the mirror image of a control believed present
  that never fired (see Unverified Controls); both come from reading the doc
  instead of the code.
- **`/app/logs/daily_run.log` no longer exists**, so the dashboard's
  cron-status panel (page 01) parses a missing file. Expected consequence of
  disabling `run_daily`, cosmetic, but the panel now reads permanently stale.
- **`candle_source_compare` now HAS a reader** (2026-08-20, commit `17c45f2`)
  — `watchdog.py::check_candle_divergence`, per-(symbol,timeframe) threshold at
  5× a **baked** p99 measured once over all 21,051 rows, plus a worst-of-24h
  line in `daily_summary.py` so the normal range is visible daily. Baked, not
  rolling: a rolling baseline widens around the anomaly it exists to catch.
  Verified by marker test, not by silence — synthetic row id 21120
  (`delta_pips=99999.99`) injected 2026-08-20 02:16 UTC, alert fired and sent,
  row deleted, state cleared on the next run. `logs/watchdog_alerts.jsonl`
  carries both the alert and an appended `marker_test` annotation naming it
  synthetic; the log stays append-only.
  **Do not retune to silence US100** — its ~100-pip mean divergence on both
  timeframes is off-session yfinance staleness (the condition the 2026-07-15
  flip fixed), and a global threshold accommodating it goes blind to FX at
  1–2 pips. `US100 HOUR` has logged nothing since 2026-08-13T00:56 UTC, when
  its last active strategy was deactivated — the baseline is retained for if it
  returns. `DAX`/`BTC` have never logged a row and are named in
  `DIVERGENCE_NO_BASELINE`; anything else unbanded alerts as UNCHECKED.
- ~~🔴 **WEBHOOK ARRIVAL FRESHNESS IS UNMONITORED**~~ — **VOID BY
  RETIREMENT, 2026-09-04.** Recorded as an open gap earlier the same day,
  with a `watchdog.py` recency check proposed as the fix. **That fix must NOT
  be built.** The source is retired, so a liveness check on it would either
  alert forever or be tuned until it can never fire — **and both are worse
  than nothing**, the second especially, because a control that cannot fire
  reads as a control that is passing. Corrected rather than deleted, same as
  the 12-of-13 correction: a deleted entry stops contradicting the reasoning
  that produced it.

  🔴 **KEEP THIS HALF — it outlives the source that produced it.**
  **Monitoring was built where the WORK was happening, not where the RISK
  was.** The one signal source that was rostered `active` had **zero**
  liveness checks, while the two paper-only loops had **two each**
  (`signal_loop` and `candle_stream` heartbeats, watchdog-gated on market
  hours). Nobody decided that; it accreted, because the loops were what was
  being actively developed. The daily summary compounded it by reporting
  *trades opened*, so a dead source reads as a quiet day — absence again.

  > **STANDING RULE: a live signal source gets a liveness check as PART of
  > wiring it up, not afterwards.** Not a follow-up ticket, not "once it's
  > proven" — in the same change that makes it live. Retro-fitting a monitor
  > requires someone to first notice the thing is unmonitored, which is
  > exactly the observation nobody makes about a system that appears to be
  > working. The next source starts with one.
- **`correlation_events` is still write-only** — 3,824 rows, but they are
  per-cycle re-logs of a *standing state*, not distinct events (~130 episodes).
  Consumer proposed, not built.
- **26 dangling Docker images on the VPS** as of 2026-08-22 (was recorded as 51
  on 2026-08-15; the count is lower now, and nothing in this repo records a
  prune between those dates — so either one happened undocumented or the
  earlier figure was miscounted. Do not treat the trend as reassuring). Not
  pruned. Precedent exists (Jun 27 prune). With `/home/ubuntu/backups` at
  1.7 GB and 29 GB free, disk is not pressing — check before the next rebuild.

---

<!-- moved from CLAUDE.md 2026-09-04 — the post-flip maintenance record, the three 2026-07-20 production bugs and the correlation-cluster design note — all already pointing at archives -->

### Post-flip Tier 1 maintenance (2026-07-16)
Quota-fallback Telegram dedup (once/6h per condition-type, state file
`/tmp/candle_stream_fallback_state.json`; logs stay unconditional, only
`send_telegram` gates), and the `_normalize_yf_time` timezone fix. Full account
→ `docs/INCIDENT_HISTORY.md`.

**The SL DRIFT investigation's conclusion is the part that matters and it was a
NEGATIVE result:** post-flip drift looked 2–3x worse and **was not a
regression**. Two structural, pre-existing causes — (a) 25–55 min
decision-to-execution lag from `candles[-2]` dedup plus `_is_due` cadence, and
(b) a **measurement artifact**: stream candle close is mid, live execution
fills at offer/bid, so every reanchor comparison injects ~half-spread of
phantom drift. Do not re-open this as a stream bug.

**One item still DEFERRED:** the mid-vs-dealing-price comparison fix. Cosmetic
— affects the drift metric's apparent size, not real SL/TP math. Batch it with
the next reanchor-logic review.

### Three production bugs found + fixed (2026-07-20)
Diagnosed by read-only VPS audit, fixed and deployed same day. Full accounts,
including the ledger re-audit → `docs/INCIDENT_HISTORY.md`.

1. **Webhook "EXECUTED" ghost rows** — logged unconditionally whenever
   `place_trade_from_alert()` returned without raising, but that returns `False`
   on many non-exception branches. Now gated on
   `result.get("status") == "OPEN"`.
2. **USDCAD never traded for 7 days** — `candle_stream` had a second,
   independently-hardcoded symbol list. **Killed the class**: both lists now
   import the shared `symbols.py`.
3. **Cross-symbol close_price/pnl contamination** — the poller's fallback
   matcher searched IG's entire multi-instrument history with **no symbol
   filter**. 8 rows corrected; the pre-correction ledger survives only as
   `trades.bak-20260720T012352Z.db` (see Database Backups).

⚠️ **This file's own earlier assumption that `pnl` was unaffected was WRONG** —
`_fetch_close_data()` returns `close_price` and `realised_pnl` from the same
matched row, so a wrong-symbol match corrupts both. It read as "sane" only
because every trade risks ~$10 with similar R:R.

`scripts/reaudit_close_prices.py` is idempotent and read-only against IG —
re-run it after any poller or `ig_scale` change.

### Correlation cluster logging + per-instance daily loss limit (2026-07-22)
`_check_correlation_cluster()` flags 3+ OPEN williams_r positions, same
direction, across {EURUSD, GBPUSD, AUDUSD, USDCAD} → `correlation_events` +
INFO Telegram. **Report-only, NOT a trading gate** — measuring frequency before
deciding whether to build blocking logic. Trigger incident and design notes →
`docs/INCIDENT_HISTORY.md`.

⚠️ **Direction is the raw per-symbol BUY/SELL, not USD-exposure normalized.**
USDCAD is USD-as-base while the other three are USD-as-quote, so a USDCAD SELL
is not the same underlying bet. Fine for counting; **any future blocking logic
built on this table MUST normalize to net USD exposure direction first.**

---

<!-- moved from CLAUDE.md 2026-09-04 — the REDUCED_GAUNTLET expectation derivation and the 12-of-13 correction narrative -->

**8, because `williams_r` holds FIVE of the thirteen paper rows** — ids 6
US500 HOUR, 22 EURUSD, 32 GBPUSD, 34 AUDUSD, 36 USDCAD. Those five get real
84-cell maps; the remaining eight get markers. Verified against `roster.db`:
31 rows total, 13 `status='paper'`, 5 of them `williams_r`. With ids 29/30
held on the ETF blocker it reads **6 of 11**, which is exactly what the
2026-09-04 batch produced (6 markers, 5 × 84 = 426 stability rows).

> 🔴 **THIS HEADING READ "12 OF 13" UNTIL 2026-09-04, AND THAT IS WORSE THAN
> HAVING NO NUMBER AT ALL.** The whole purpose of this entry is to separate
> "exactly as planned" from "something is badly wrong". With 12 in it, a
> **correct** run returning 6 markers would have been flagged as anomalous —
> the check would have manufactured the alarm it exists to prevent.
>
> **The reason generalises and is worth carrying:** `STABILITY_GRIDS` is keyed
> by strategy **NAME**, while the roster is counted in **ROWS**, and one
> strategy name can hold several rows. Counting names where the system counts
> rows is an off-by-N that scales with the roster, not a slip. Any future
> figure of this shape must be derived from the roster
> (`SELECT COUNT(*) ... WHERE status='paper' AND strategy_name NOT IN
> STABILITY_GRIDS`), never from counting distinct strategies by hand.

**A second marker verdict now exists — `NOT_RUNNABLE`.** The no-grid branch
used to write its marker **before any backtest ran**, so a strategy that
cannot be backtested at all still produced a row reading as
`REDUCED_GAUNTLET` (= "ran, no grid available"). It now proves runnability
first and records `NOT_RUNNABLE` with the exception in `extra_json` when the
strategy raises. Safe to add: **nothing reads `walkforward_runs.verdict`** —
there is no `get_walkforward*` in `models.py`, the selector and
`score_strategies()` read `backtest_results`, and no dashboard page touches
the table. Enumerated before the value was chosen, not after.

The standing plan was **build 2 grids, mark 4**. Against the current roster that
now reads: **build one more — `stoch_rsi` and `supertrend` — and accept the rest
as reduced.** Those two are the ones with live or recently-live history worth a
stability contour; the remainder are paper-only and a marker is an honest record
of what was not run.

**Write this down before the run, not after.** A batch that returns 12 reduced
verdicts is either "exactly as planned" or "something is badly wrong", and those
two look identical in the output. This entry is what makes it the first one.

---

<!-- moved from CLAUDE.md 2026-09-04 — the pre-registration pointer stub — folded into the Stage 4 re-run section where the conclusion is read -->

### 🔒 The two Dukascopy pre-registrations — ARCHIVED, the batch has run

Both were written 2026-09-04 **before** the batch and are now history →
`docs/OPERATIONS_LOG.md`. They mattered as pre-registrations: they are what
makes the re-run's outcome a test rather than a story, and they record a
prediction that was **right on direction and wrong on attribution** (offset
magnitude predicted almost nothing; sample size predicted everything).

**The one standing conclusion, which outlives the batch:**

> **NO PROMOTION DECISION FOLLOWS FROM STAGE 4, whatever the ordering looks
> like.** Thirteen rows near 1.0 read as a ranking and are not one — the error
> bars overlap. This is the same shape as the pre-parity scores that promoted
> `US100 HOUR supertrend` unreviewed, where an ordering was treated as evidence
> because it was the only thing on the screen.

The interpretation bar it set — **an edge smaller than ~0.5–0.6 pips per bar
cannot be distinguished from corpus error** — is retained with the noise-floor
measurement in the Dukascopy corpus section, which is where a future decision
reads it.

---

<!-- moved from CLAUDE.md 2026-09-04 — the tail-resolution evidence summary — verdict retained in CLAUDE.md, the four evidence lines archived -->

### ✅ THE TAIL IS RESOLVED — non-traded hours plus single-bar artifacts

**Verdict: CONFINED TO NON-TRADED HOURS, remainder single-bar artifacts. Not
real market divergence, not a Dukascopy defect. No cleaning step is justified —
EVERY BAR IS KEPT.**

🔴 **The ">3 pips on 5–7% of bars" figure was RAW-ROW based and is wrong.**
Deduplicated to one observation per (symbol, minute) the true tail rate is
**0.4–0.8%**. The tail bars specifically were duplicated **13.3x** against
1.30x for the data as a whole — rule 9's worked instance.

Four lines of evidence, all → `docs/OPERATIONS_LOG.md`:
- **hour-of-day is decisive** — hour 21 (rollover, `is_entry_allowed=False`
  every day) carries a **9.9%** tail rate against ≤0.8% everywhere else;
- **cross-symbol coincidence** — 84.8% of tail timestamps appear on ONE symbol
  only, so it is per-symbol scatter, not a feed-level fault;
- **persistence** — 93–100% single-bar runs, longest 3. Bad ticks, not
  repricing;
- **our own capture's reconnect gaps** contribute a real 0–24%, not dominant.

**GBPUSD's caveat is answered and it REVERSES.** It was the one symbol where
Twelve Data had the thinner tail; **84% of its tail bars fall in hours the bot
cannot enter.** Restricted to `is_entry_allowed` hours: **stdev 0.419 vs Twelve
Data's 1.035 — Dukascopy ~2.5x tighter on the hours that matter.**

**Why no cleaning:** the comparison is symmetric and cannot say which feed is
wrong, so removing spikes would be editing raw market data on a guess. And
`is_entry_allowed` governs ENTRIES, not candle availability — a backtest needs
continuous bars to evaluate holds across excluded hours.

---

<!-- moved from CLAUDE.md 2026-09-04 — the index level-check narrative and the depth/gap table — both restated compactly in the corpus table below -->

### It clears the index blocker — verified by PRICE LEVEL, not by name

**US500, US100 and DAX all classify to index scale** against the IG 2026-08-23
snapshots: 7674.60 vs 7671 (1.000x), 29354.15 vs 29289 (1.002x), 26226.65 vs
26108 (1.005x). **These are indices, not ETF proxies** — the SPY/QQQ/EWG defect
is absent. Depth 45,485–45,700 M15 bars / 23.9 months on all three, against a
requirement of ~10.

⚠️ Checked **by level**, exactly as the blocker demands. The name never proved
anything and still doesn't.

⛔ **The first execution-match table was ROW-based and is SUPERSEDED** by the
unique-observation recompute immediately below — it was biased *against*
Dukascopy. **Both tables → `docs/OPERATIONS_LOG.md`**; they are kept because
the difference between them is the worked instance behind duplicate-observation
bias (rule 9).

### Depth and gaps — 24 months, clean

| symbol | bars | first | last | months | weekend gaps | other >1h |
|---|---|---|---|---|---|---|
| EURUSD | 49,803 | 2024-09-04 | 2026-09-04 | 24.0 | 104 | 4 |
| GBPUSD | 49,795 | 2024-09-04 | 2026-09-04 | 24.0 | 104 | 5 |
| AUDUSD | 49,794 | 2024-09-04 | 2026-09-04 | 24.0 | 104 | 6 |
| USDCAD | 49,793 | 2024-09-04 | 2026-09-04 | 24.0 | 104 | 6 |

**104 weekend gaps over 2 years is exactly 52/year** — the series is complete,
not thinned. Every remaining gap is a Christmas or New Year holiday
(24.2h at 12-31 in both years, ~14–15h at 12-25). No unexplained holes.

---

<!-- moved from CLAUDE.md 2026-09-04 — the pre-September backup inventory rows — dated records; the rollback-relevant recent rows stay in CLAUDE.md -->

| `trades.bak-20260720T012352Z.db` | Before `scripts/reaudit_close_prices.py` corrected the 8 cross-symbol-contaminated rows | 565 trades, 179,413 backtest_results — **sole surviving pre-correction ledger state** |
| `trades.bak-20260816T042148Z.db` | Before the `engine_version` migration | 906 trades, 268,117 backtest_results |
| `trades.bak-20260817T164123Z.db` | Undocumented until 2026-08-21 — taken around the `market_hours` / finding-23 FX weekend-block work | 918 trades, 268,117 backtest_results, `integrity_check ok` |
| `trades.bak-20260821T184131Z.db` | Before moving all four live `williams_r` instances to `paper` | 996 trades, 268,117 backtest_results, `integrity_check ok` |
| `trades.bak-20260821T190857Z.db` | **Undocumented until 2026-08-22** — taken minutes after the williams_r demotion, purpose unrecorded | 996 trades, 268,117 backtest_results, `integrity_check ok` |
| `trades.bak-20260822T180436Z.db` | Taken by `scripts/import_stage4.py` before the Stage 4 import write test (rule 5) | 996 trades, 268,117 backtest_results, `integrity_check ok` |
| `trades.bak-20260823T040057Z.db` | Before the Stage 4 dress-rehearsal import (rule 5) | 996 trades, 268,117 backtest_results, `integrity_check ok` |
| `trades.bak-20260823T041942Z.db` | Before the post-fix dress-rehearsal re-import (rule 5) | 996 trades, 268,118 backtest_results, `integrity_check ok` |

---

<!-- moved from CLAUDE.md 2026-09-04 — the collector's dated failure diagnostic table -->

|---|---|
| `/app/logs/candles.log` | **222 lines, 222 quota errors, ZERO successes**, whole life of the 2026-08-22 image |
| `/app/scripts/candle_cache/` | **did not exist in the container** — never created, so there was no output to lose |
| its budget | 3 symbols x `FETCH_COUNT` 50 x 96 runs/day = **14,400/day = 100,800/week** = **10.08x** the allowance |
| exhaustion | **~16.7 hours**, then zero for the rest of the week |
| waste | 50 candles requested every 15 min to gain 1 — **~98%** |

---

<!-- moved from CLAUDE.md 2026-09-04 — the Sunday-reopen spread measurement detail — the headline numbers and the exclusion rule stay in CLAUDE.md -->

### 📏 MEASURED — the Sunday reopen, 2026-08-23 20:00–22:59 UTC

**First hard numbers for the window the entry policy declines.** Until now the
Sunday 23:00 rule rested on ~10 trades and an argument. First reopen sample per
symbol, from `signal_log.spread`:

| symbol | first reopen sample | max in window | normal (`NORMAL_SPREADS`-era estimate) | ratio |
|---|---|---|---|---|
| **GBPUSD** | **0.0026 = 26 pips** | 0.0026 | ~1.5 pips | **~17x** |
| AUDUSD | 0.0013 = 13 pips | 0.0013 | ~0.6 pips | ~22x |
| USDCAD | 0.00031 | 0.00133 = 13.3 pips | ~0.9 pips | ~15x |
| EURUSD | 0.00019 | 0.0009 = 9 pips | ~1.0 pips | ~9x |

**GBPUSD's 26 pips is wider than the 10–17 pip range quoted elsewhere in this
file, and wider than its own 21:00 rollover hour.** Raise that upper bound
where it appears. This is the cost of the declined window measured rather than
argued — and it is now the primary evidence for the Sunday 23:00 entry policy.

⛔ **THESE SAMPLES MUST NOT ENTER THE SPREAD TABLE.** Same exclusion as the
shut-book values, and for the same reason: `get_spread_samples(market_open_only=True)`
filters on `market_hours.is_entry_allowed`, and every row above was taken while
that predicate was **False**. They are pre-open-filtered by construction. A
median built including them is biased **high** — the mirror of the 2026-08-17
bias-low failure, and just as invisible, because a wider number looks
conservative rather than wrong.

They are evidence **for the policy**, not inputs **to the cost model**. Two
different uses of one column, and the filter is what separates them.

*(They do, however, quantify the exit-side exposure described immediately
below: a position held through the weekend gap exits into exactly these
spreads.)*

---

<!-- moved from CLAUDE.md 2026-09-04 — orphaned table header from the collector diagnostic table moved above -->

| | |

---

<!-- moved from CLAUDE.md 2026-09-04 — CHECK 2's rollover-hour spread table — now consolidated with the Sunday-reopen measurement in the spread cost model section -->

**Retained here because it is a MEASUREMENT and the spread table has no other
source for this hour:**

#### 📏 Rollover-hour spreads — measured, and the indices are the interesting part

| symbol | min | max | ~normal | ratio at max |
|---|---|---|---|---|
| **GBPUSD** | 0.00169 (16.9 pips) | 0.00169 | ~1.5 pips | ~11x |
| USDCAD | 0.00133 (13.3 pips) | 0.00133 | ~0.9 pips | ~15x |
| EURUSD | 0.00028 | 0.00116 (11.6 pips) | ~1.0 pips | ~12x |
| AUDUSD | 0.00061 | 0.00116 (11.6 pips) | ~0.6 pips | ~19x |
| **US500** | **1.5** | **1.5** | 1.5 | **~1x — flat** |
| **US100** | **5.0** | **5.0** | 5.0 | **~1x — flat** |

⛔ **THESE MUST NOT ENTER THE SPREAD TABLE.** Same exclusion as the shut-book
and Sunday-reopen samples, same reason: every row was taken while
`market_hours.is_entry_allowed` was **False**, and
`get_spread_samples(market_open_only=True)` filters on exactly that predicate.
Including them biases the median **high**. They are evidence **for** the policy,
never inputs **to** the cost model.

**The indices being flat is itself a finding, and only an all-symbols query
could show it.** FX widens 11–19x in the rollover hour; US500 and US100 do not
move at all. So **the rollover widening is an FX phenomenon**, and the gate —
which checks `ROLLOVER_BLOCK_HOUR` *before* the `_ALWAYS_OPEN` short-circuit,
deliberately covering 24/7 instruments — is **broader than the evidence base
that justifies it.**

**This is NOT a reason to narrow the gate.** Recorded because it is the kind of
thing that goes unnoticed until someone re-derives the rule from its rationale
and finds the rationale does not cover every instrument it applies to. Three
points in its favour as it stands: the index sample is small (11 rows across
one hour); an all-instruments rule has no per-symbol branch to drift; and
blocking entries in a low-liquidity hour costs little on instruments that are
not widening anyway. If the gate is ever revisited, **this measurement is the
starting point, and it needs more than one hour of index data first.**

Exactly the outcome ENUMERATE, DON'T ASSERT predicts: criterion 5 was written
to include symbols believed irrelevant, and the difference between them is
visible only because both were in the output.

---

*(The five criteria as originally written are kept below unchanged. They were
correct — including criterion 1's exact-string test, which is what would have
caught an ordering drift. It was the prediction table above them that was
wrong, and that correction is recorded in place rather than edited away.)*

---

<!-- moved from CLAUDE.md 2026-09-04 — the paper roster's per-row pre-parity backtest figures — every one superseded by the Stage 4 Dukascopy re-run -->

| Symbol | TF    | Strategy   | Mode  | Source | Notes                          |
|--------|-------|------------|-------|--------|---------------------------------|
| US500  | HOUR  | williams_r | Paper | loop   | Accumulating trades             |
| EURUSD | 15MIN | stoch_rsi  | Paper | loop   | 297 bt trades, PF 1.36          |
| EURUSD | 15MIN | bb_squeeze | Paper | loop   | 33 bt trades, PF 2.18. Walk-forward (2026-07-09): FRAGILE — median PF 1.08, 57.1% windows profitable, 149 trades across 7 windows. **Paper P&L corrected — see bb_squeeze correction below** |
| EURUSD | 15MIN | supertrend | Paper | loop   | 111 bt trades, PF 1.35          |
| US500  | HOUR  | stoch_rsi_confluence | Paper | loop | session filter only, shadow logging — see below |
| EURUSD | 15MIN | ny_session_momentum | Paper | loop | 37 bt trades, 75.7% WR, PF 1.64, follow mode |
| US500  | 15MIN | ema_pullback         | Paper | loop | ⛔ **PF 1.57 / 44 trades VOID — ETF-scaled cache, see finding 30.** 44 bt trades, 45.5% WR, PF 1.57, EMA8/50. Walk-forward (2026-07-09): FRAGILE — median PF 1.03, 53.8% windows profitable, 171 trades across 13 windows |
| US100  | 15MIN | ema_pullback         | Paper | loop | ⛔ **PF 3.17 / 86%-of-combos VOID — ETF-scaled cache, see finding 30.** 86% combos profitable, PF 3.17 best. Walk-forward (2026-07-09): FRAGILE — median PF 1.12, 69.2% windows profitable (one window short of ROBUST's 70% bar), 70 trades across 13 windows. The PF 3.17 sweep result did not survive — overfit |
| GBPUSD | 15MIN | ema_pullback         | Paper | loop | 25 bt trades, 64% WR, PF 2.00 |
| EURUSD | 15MIN | williams_r | Paper | loop | **Demoted from live 2026-08-21**, history row 43. id 22 |
| GBPUSD | 15MIN | williams_r | Paper | loop | **Demoted from live 2026-08-21**, history row 44. id 32 |
| AUDUSD | 15MIN | williams_r | Paper | loop | **Demoted from live 2026-08-21**, history row 45. id 34 |
| USDCAD | 15MIN | williams_r | Paper | loop | **Demoted from live 2026-08-21**, history row 46. id 36 |

**13 `status='paper'` rows total** (ids 6, 22, 23, 24, 25, 26, 28, 29, 30, 31,
32, 34, 36). Count verified on the VPS 2026-08-21.

### bb_squeeze EURUSD paper P&L — CORRECTED (2026-08-12)

---

<!-- moved from CLAUDE.md 2026-09-04 — the williams_r FX expansion walk-forward batch (2026-07-09) and the blocklist prose -->

STRATEGY_BLOCKLIST in scripts/select_strategy.py prevents daily cron from
re-promoting any of the above. To unblock: remove the tuple from the set
AND manually verify live performance warrants re-testing.

### williams_r FX expansion batch (walk-forward, 2026-07-09)
Tested williams_r (period=14, oversold=-85, overbought=-15 — same as
AUDUSD paper entry) against 3 untested pairs, ~30k 15MIN candles each
(Twelve Data via fetch_twelvedata.py), to see if AUDUSD's 100%-windows
result was a property of williams_r as a signal class or pair-specific:
- USDJPY: FRAGILE — median PF 1.13, 66.7% windows profitable (6
  windows, 1091 trades). Closest to ROBUST but one window short of the
  70% bar.
- EURGBP: REJECT — median PF 0.97, 33.3% windows profitable (6
  windows, 1004 trades).
- NZDUSD: REJECT — median PF 0.93, 50.0% windows profitable (6
  windows, 1181 trades).

Conclusion: williams_r's edge does NOT generalize across FX pairs —
AUDUSD's walk-forward result stands alone, not evidence of a portable
signal class. No roster changes from this batch. Correction note: an
initial follow-up claimed EURGBP scored ROBUST (median PF 1.42, 92.3%
windows) — that number did not come from any run and was a reporting
error, caught before any deploy. The REJECT figures above are the only
real, reproduced result.

US100 all strategies blocklisted 2026-06-12 — rsi_divergence was
auto-promoted live by cron without review. All US100 strategies blocked
until a specific US100 strategy is deliberately designed and validated.

---

<!-- moved from CLAUDE.md 2026-09-04 — the deactivated-strategy inventory — enforcement lives in STRATEGY_BLOCKLIST, not in this table -->

| Symbol | TF   | Strategy        | Reason                                   |
|--------|------|-----------------|------------------------------------------|
| US100  | HOUR | stoch_rsi       | 0% live win rate (6 trades)              |
| US100  | 5MIN | stoch_rsi       | 18.5% paper win rate (27 trades)         |
| US100  | HOUR | swiftalgo       | 43.5% WR, avg win ≈ avg loss             |
| DAX    | HOUR | macd_rsi        | 0% backtest win rate                     |
| DAX    | HOUR | rsi             | 9.1% win rate                            |
| BTC    | HOUR | rsi_divergence  | 0/5 since activation, noisy in range     |
| BTC    | HOUR | vwap_ema        | Already inactive (margin issues)         |
| US100  | HOUR | rsi             | Firing live trades incorrectly — deactivated 2026-06-04 |
| BTC    | HOUR | stoch_rsi       | BTC margin concerns — deactivated 2026-06-04             |
| DAX    | HOUR | williams_r      | Negative backtest P&L — deactivated 2026-06-12 |
| US500  | 15MIN| fvg             | 30.6% WR insufficient — deactivated 2026-06-12 |
| US500  | 15MIN| smc             | 24% WR, low frequency — deactivated 2026-06-12 |
| EURUSD | 15MIN| london_breakout | 35% WR, negative P&L — deactivated 2026-06-12  |

### Deactivated 2026-08-13 — invalid backtest evidence
Both set `status='inactive'` at 2026-08-13T01:38:04Z. `active_strategy_history`
rows **41** and **42** carry the full reasons; summarised:

| id | Symbol | TF | Strategy | history | Reason |
|----|--------|-----|----------|---------|--------|
| 33 | US100 | HOUR | supertrend | **41** | Promoted 2026-06-16 by the unconditional first-activation branch — no score threshold, **zero paper trades, zero human review**, and undocumented in this file for ~8 weeks. Its evidence (`backtest_id 73401`) is invalid: `supertrend` never emits `tp_price`, so the engine modelled it with no take-profit and sized at $15 vs live $10 |
| 2 | US500 | HOUR | stoch_rsi | **42** | Evidence (`backtest_id 1705`, score 0.867) invalid for the same reason — `stoch_rsi` never emits `tp_price`; the score that ranked it is not reproducible. Walk-forward was already FRAGILE (median PF 1.33, 57.1% windows, 3 of 28 windows PF 0.00). Live since 2026-04-29 |

**Neither is re-promotable** until the engine contract fix and a gauntlet
regeneration. `("US500","HOUR","stoch_rsi")` is now in `STRATEGY_BLOCKLIST`;
US100 is covered symbol-wide.

Verified live after deactivation: checked-cycle count dropped 13→11 and zero
new `signal_log` rows appeared for either key while the 11 siblings kept
logging.

BTC note: Two consecutive failed strategies. No BTC strategies until a
crypto-specific volatility approach is designed and backtested.

---

<!-- moved from CLAUDE.md 2026-09-04 — the concurrent-position cap's stacking-profitability rationale -->

### Max Concurrent Positions Per Symbol (2026-07-25)
`risk/concurrent_positions.py` — `MAX_CONCURRENT_PER_SYMBOL = 1`. Before a
signal_loop live trade, counts `trades.status='OPEN'` for that (symbol,
strategy_name); at/over limit, skips the signal and shadow-logs to
paper_trades (`notes: "SHADOW: skipped — concurrent position limit, would
be Nth stack"`), logs `BLOCKED_CONCURRENT_<signal>` to signal_log. Read
from DB state, not a live IG poll — same source `_check_correlation_cluster`
already uses. Race window: count is read before place_trade's own IG
round-trip; a different-timeframe signal on the same (symbol,
strategy_name) landing mid-`place_trade()` could still stack past the
limit — narrow, not fully closed. Webhook/swiftalgo path untouched (gate
lives only in `live_signal_loop.py::_check_symbol`, not `execute_trade.py`
or `webhook/receiver.py`).

Reason: 2026-07-24 stacking-profitability analysis (backtest-vs-live
reconciliation prep) found concurrent same-symbol williams_r stacking cost
**-$219.63** vs a first-entry-only counterfactual across 32 episodes/78
trades in the post-flip window — 21/32 episodes were ALL_SL together
(correlated drawdown, not diversification), and deeper price-averaging did
not correlate with better outcomes (mean-reversion "stronger snapback"
thesis unsupported). The backtest engine models one position at a time;
this aligns live execution to that model. **Reconciliation clean-singles
clock starts at this deploy** — AUDUSD reconciliation now counts only
single-position trades placed after this fix ships, not the pre-cap
history.

---

<!-- moved from CLAUDE.md 2026-09-04 — the watchdog's check-by-check description and the duplicate-process gotcha -->

### Layer 3 — heartbeat + watchdog
`heartbeat` table (name PK, last_beat, details) — signal_loop upserts
`name='signal_loop'` at the end of every cycle regardless of how many
strategies were due that cycle.

scripts/watchdog.py runs on the HOST (not in the container — the
whole point is surviving container death). Deliberately stdlib-only,
no project imports: parses .env directly (host cron env has no
TELEGRAM_* — those only reach the container via docker-compose's
env_file) and reads trades.db directly via sqlite3.

Checks:
- signal_loop heartbeat stale >20min during market hours
  (Sun 22:00 UTC – Fri 21:00 UTC) → 💀 SIGNAL LOOP STALE
- duplicate uvicorn process on host → 🔴 DUPLICATE PROCESS DETECTED
  Gotcha: Docker does NOT hide container processes from the host's
  process table (no PID namespace isolation by default) — a plain
  `pgrep -cf "uvicorn main:app"` always counts the container's own
  process too. The check cross-references matched PIDs against
  `docker top trading_bot-bot-1` and only flags a PID outside the
  container's own tree (e.g. a repeat of the Apr-12 stale-systemd
  incident). Caught this live: the first-ever run false-positived
  before this fix.
- trading_bot-bot-1 not running → 💀 BOT CONTAINER DOWN

Anti-spam: `/tmp/watchdog_state.json` tracks last-alert-time per
condition, re-alerts the same condition at most every 60min, and
clears on recovery so a fresh occurrence alerts immediately.

Every alert actually sent (not suppressed by the 60min window) is
also appended as one JSON line (`timestamp`, `condition`, `message`)
to `logs/watchdog_alerts.jsonl` — an append-only history alongside
the dedup state, not a replacement for it.

Host cron `/etc/cron.d/trading-watchdog`:
```
*/10 * * * * ubuntu python3 /home/ubuntu/trading_bot/scripts/watchdog.py >> /home/ubuntu/trading_bot/logs/watchdog.log 2>&1
0 23 * * * ubuntu python3 /home/ubuntu/trading_bot/scripts/daily_summary.py >> /home/ubuntu/trading_bot/logs/daily_summary.log 2>&1
```

---

<!-- moved from CLAUDE.md 2026-09-04 — the selector's armed-symbol analysis and the crontab md5 anchor history — one claim in it went stale when swiftalgo was retired -->

deactivations, **US100 HOUR had no active row** (armed). **US500 HOUR still
has one** — id 13 `swiftalgo`, `status='active'` — and `get_active_strategy`
filters `status='active'` (`database/models.py:430`), so US500 was **not**
armed via that branch. Both are blocklisted regardless. An earlier note in
this repo claimed US500 HOUR had no active row; that was wrong.

**STRATEGY_BLOCKLIST is an allowlist by omission.** It blocks enumerated
`(symbol, timeframe, strategy_name)` tuples only — any name not listed is
permitted. This file previously claimed "all US100 strategies blocklisted
since 2026-06-12"; that claim was false, `("US100","HOUR","supertrend")` was
never in the set, which is how the 2026-06-16 promotion succeeded. Only
`SYMBOL_BLOCKLIST` blocks a symbol. Also latent: 10 of the 22 US100 tuples are
unreachable — `_select_for_symbol` filters to `timeframe == "HOUR"` before the
blocklist check, so every 15MIN/5MIN tuple has never been evaluated.

**Verification anchors after any rebuild:**
- committed `scripts/crontab` md5 **`0f1cc206193f5d30341c3db530357b06`** as of
  2026-08-23 (was `aea93925651e8ee24ce7d52e70b3434d` from 2026-08-15 until the
  collector was disabled; blob `fe4ff2584c8dbfb4188bffdd6cf5b044316d135c`)
- in-container `/etc/cron.d/trading-bot` must match byte-for-byte —
  `Dockerfile:18` is a plain `cp`, no transformation
- the pre-fix Method A value was `d7565feade7ac71356579e686b887a1b`; seeing it
  again means a rebuild reverted the disable
- the 2026-08-23 collector disable was applied by **`docker cp`** into the
  running container, not by a rebuild (CHECK 1's Sunday reopen was hours away —
  see the prospective marker rule). Verified after the copy: in-container
  `/etc/cron.d/trading-bot` md5 is **`0f1cc206193f5d30341c3db530357b06`**,
  byte-identical to the committed file, so a rebuild restores exactly what is
  already running. Per Unverified Controls instance 3 the copy is lost on
  rebuild; the committed file is what makes it permanent.

---

<!-- moved from CLAUDE.md 2026-09-04 — a completed Phase-7 item that sat in the 'still to build' list for five weeks -->

- ~~Telegram alerts (trade placed, trade closed, risk limit hit)~~
  **DONE — shipped 2026-07-07/08.** This line contradicted the Alerting
  section for five weeks. All three named alerts exist as Layer 2 event hooks
  in `bot/notifier.py` (OPENED, CLOSED, REJECTED, SL DRIFT, DAILY LOSS LIMIT
  HIT, SIGNAL LOOP ERROR), plus heartbeat/watchdog (Layer 3) and the 23:00 UTC
  daily summary (Layer 4). There is no `utils/telegram_alert.py` and none is
  needed.

---

<!-- moved from CLAUDE.md 2026-09-04 — the engine_version prose, duplicated verbatim by the three-version table in the parity section -->

`backtest_results` and `walkforward_runs` carry
`engine_version TEXT NOT NULL DEFAULT 'pre-parity-v0'`. The constant lives in
`engine_version.py` (repo root, zero imports — same safe-import contract as
`symbols.py`). It versions the **trade model**, not the code: bump only when a
change would make two runs of the same strategy on the same candles produce
different trades or different P&L. **Never use commit SHAs** — a SHA changes on
commits that cannot move a number, and the field exists to answer "are these two
rows comparable?"

- `get_backtest_results()` filters to `CURRENT_ENGINE_VERSION` by default.
  `engine_version=None` reads everything and is for archive/inspection only
  (dashboard page 04 passes it deliberately, and says so in a comment). **Never
  pass `None` from anything feeding a promotion decision.**
- `score_strategies()` raises `MixedEngineVersionError` rather than ranking
  across models. With the filter in place this is defence in depth — it is
  reachable only if a caller defeats the filter, which is exactly the case worth
  catching.


---

<!-- moved from CLAUDE.md 2026-09-04 — a file-tree entry for a module that never existed, kept only to negate itself -->

utils/telegram_alert.py     ❌ DELETE THIS LINE'S PREMISE — Telegram
                            alerting is BUILT and deployed as
                            bot/notifier.py (4 layers, see Alerting).
                            No utils/telegram_alert.py exists or is
                            needed.

---

<!-- moved from CLAUDE.md 2026-09-04 — a dated test-script credential bug, fixed -->

Known bug fixed 2026-07-08: bot/test_ig.py and bot/test_trade.py were
hardcoded acc_type="DEMO" but pulled IG_API_KEY (the LIVE key) instead
of IG_DEMO_API_KEY — silently would have failed or hit the wrong
environment. Both now use the DEMO-specific vars.

---

<!-- moved from CLAUDE.md 2026-09-04 — the ig_allowance.py rollout narrative and the first reset-time read -->

### The allowance is now logged — `ig_allowance.py`

IG returns `allowance{remainingAllowance, totalAllowance, allowanceExpiry}` on
**every successful** `/prices` response. Both consumers did
`result.get("prices")` and dropped the rest, so the shared budget was
unmeasured and **the reset time was unknown**. Now parsed and printed at both
sites, tagged by source:

```
[ig_allowance] candle_stream REST US500/15MIN: remaining=9800 of 10000 (2.0% used), resets_at=...
```

Reports, does **not** throttle — a caller wanting to reserve budget reads
`remaining` and decides. A logging helper that can refuse is a logging helper
that can stop a warm-up. Never raises; stdlib-only, zero project imports (same
safe-import contract as `symbols.py` / `engine_version.py` /
`instrument_limits.py`, because `engine.py` imports it).

⚠️ **The reset time is only learnable from a request that SUCCEEDS.** A 403
carries no allowance block. Nothing will print until the budget resets.

✅ **It worked — the reset time is now known.** The first successful `/prices`
call after the 2026-08-25 deploy printed
`resets_at=2026-09-01T04:02:18+00:00 (expiry=604799s)`. That field had been
arriving on **every** successful response for the life of the system and was
discarded by both consumers; this is the first time it has ever been read. Every
plan that depended on the reset date before 2026-08-23 was a guess.

⛔ **Read the line about what a 403 can teach you as EXACTLY that.** It says the
reset time is absent from a 403. It does **not** say a failed request is free —
they are attempted and charged, which is how the allowance was destroyed on
2026-08-25. See finding 38 and the observation-cost rule in Unverified
Controls.

---

<!-- moved from CLAUDE.md 2026-09-04 — the per-file corpus inventory and the build-time additive proof — its closing claim that nothing consumes the files went stale the same day -->

### 📦 THE CORPUS — 12 files written 2026-09-04, additive only

`scripts/fetch_dukascopy.py` (local batch tool, **not** in `requirements.txt`,
same status as `fetch_twelvedata.py` — the container has no use for it and
`Dockerfile:11 COPY . .` would bake it into every layer).

Naming `{SYMBOL}_{TF}_DUKA.json` + a `.provenance.json` sidecar carrying
source, client version, **the exact instrument constant**, date range, bar
count, the mid construction, and the level-check result.

| symbol | TF | bars | range | size |
|---|---|---|---|---|
| EURUSD | 15MIN | 49,803 | 2024-09-04 → 2026-09-04 | 6.69 MB |
| GBPUSD | 15MIN | 49,795 | ″ | 6.51 MB |
| AUDUSD | 15MIN | 49,794 | ″ | 6.53 MB |
| USDCAD | 15MIN | 49,793 | ″ | 6.56 MB |
| **US500** | **15MIN** | **45,611** | ″ | 6.11 MB |
| **US100** | **15MIN** | **45,604** | ″ | 6.30 MB |
| EURUSD/GBPUSD/AUDUSD/USDCAD | HOUR | 12,448–12,450 | ″ | ~1.64 MB ea |
| US500 | HOUR | 11,783 | ″ | 1.58 MB |
| US100 | HOUR | 11,780 | ″ | 1.63 MB |

Scope taken from `roster.db`, not from memory: the 13 paper rows need exactly
`AUDUSD/EURUSD/GBPUSD/USDCAD 15MIN`, `US100 15MIN`, `US500 15MIN`,
`US500 HOUR`. HOUR was pulled for the rest because re-pulling is free and
walk-forward benefits.

**Level check re-run on the FILES AS WRITTEN**, not on what was pulled — the
script refuses to write on failure: **US500 7751.40 vs IG 7671 = 1.010×**,
**US100 29527.58 vs 29289 = 1.008×** (15MIN); 1.010× / 1.008× at HOUR.
**These are indices.**

⚠️ **DAX was NOT pulled** — no DAX row in the roster. Its instrument
(`INSTRUMENT_IDX_EUROPE_E_DAAX`) is in the script and measured good at 1.005×,
so it is one command away if a DAX strategy ever returns.

**Additive only, proven:** md5 of all **24** pre-existing cache files taken
before the run and re-verified after — **0 mismatches, 0 missing.** Nothing was
overwritten, renamed or deleted, so the `cache_file` provenance on Stage 4 rows
already imported to the VPS stays intact. The script refuses to overwrite
without `--force`.

⚠️ **Nothing consumes these files yet.** No `--source dukascopy` branch exists
in `run_backtest.py`, no default was changed, and Stage 4 was not re-run.
Wiring them in is a separate change.

---

<!-- moved from CLAUDE.md 2026-09-04 — the five Stage 4 operational gotchas and the where-it-runs / roster-snapshot rationale -->

### 🔧 FIVE OPERATIONAL GOTCHAS — all found by doing, none by reading

1. **`export_roster.py` must run on the VPS HOST, not in the container.** Inside
   the container it records `git_head = NULL` — `git` is not installed in the
   image and `/app` is not a work tree. A roster snapshot with no git HEAD is
   the no-provenance case the script exists to prevent.
2. **Backup on the host, import in the container.** Backing up works as
   `ubuntu` (the source is opened read-only); importing does not.
3. **The VPS `database/trades.db` is owned by `root`.** Any write as `ubuntu` on
   the host dies with `sqlite3.OperationalError: attempt to write a readonly
   database`. The container writes as root to the same file via the `./database`
   volume, so `docker exec` is the write path.
4. **`--since` is re-formatted per table, and must be.** `backtest_results.run_at`
   is `'YYYY-MM-DD HH:MM:SS'`; `walkforward_runs.created_at` is ISO with a `T`.
   `'T'` sorts above `' '`, so one raw string compared against both silently
   widens the window by a day and sweeps in rows from BEFORE the batch — wrong
   in the one direction nobody checks, because extra rows arriving looks like
   the import working.
5. **`backtest_trades` does NOT cross.** It is a child table keyed on
   `backtest_id` and the import inserts without ids, so carrying it would mean
   remapping every foreign key. An imported VPS `backtest_results` row has **no
   per-trade detail behind it** — the aggregate is auditable, the trade list
   stays local. Do not read absent trades on the VPS as a failed import.

### Where it runs: LOCALLY, not on the VPS

- The VPS has **no `scripts/candle_cache/` directory at all**. Seeding it means
  either putting ~36 MB of caches in the repo tree — where `Dockerfile:11`
  `COPY . .` bakes them into **every image layer**, the same problem that made
  the two DB backups cost 504 MB per build — or adding a bind mount, i.e. a
  `docker-compose.yml` change to run a batch job.
- The caches, the merged `fetch_twelvedata` incremental path and the
  `TWELVEDATA_API_KEY` all already live locally.
- Stage 4 is a batch job. It has no reason to run inside the trading container.

**Accepted cost, knowingly:** this deepens the local-vs-VPS corpus split
(finding 11). The import step below is what stops it becoming permanent.

### The roster comes from the VPS, via a small snapshot

The local `active_strategy` holds **3 phantom rows** matching no deployed
strategy, and `--from-roster` without `--roster-db` will happily resolve them —
demonstrated: `US100 HOUR stoch_rsi` resolves locally to phantom id=2 with
`period=14`. See finding 28.

```

# on the VPS
python3 scripts/export_roster.py --out /tmp/roster.db     # 20 KB, not 321 MB

# locally
scp ubuntu@<host>:/tmp/roster.db ./roster.db
python3 scripts/run_backtest.py … --from-roster --roster-db ./roster.db
```

`export_roster.py` writes `active_strategy` plus a `snapshot_provenance` table
recording source host, absolute source path, git HEAD and row count — a roster
file with no origin is indistinguishable from the phantom one it replaces.

---

<!-- moved from CLAUDE.md 2026-09-04 — the two-unknowns probe scoping — its deadline date and its index-backfill motivation both went stale -->

Both were untestable on 2026-08-23 (the allowance was at zero) and the
2026-08-25 attempt to measure them **exhausted the allowance without answering
either**. They are open until after 2026-09-01T04:02 UTC.

1. **Max `numpoints` per request** on `/prices/{epic}/{resolution}/{numpoints}`.
   Bracketed only as: `100000` and `50000` are *attempted* and return
   `error.price-history.io-error`. **No accepted value above 200 has ever been
   measured.**
2. **How far back `MINUTE_15` reaches per epic.** Entirely unknown. The whole
   index-backfill plan (~17,000 points per index symbol for a 10-month
   walk-forward span, ~51,000 for all three ≈ 5 weeks of full allowance) is a
   **guess** until this exists.

⚠️ **Probe design is now constrained by finding 38.** Do **not** bracket from
above on the theory that oversized requests are refused for free — they are
attempted and charged. Correct sequence:

- start with a **one-hour date-range window (four bars)** on one epic;
- read `allowance.remainingAllowance` off that response — the delta **is** the
  measured cost;
- step the look-back date, not the request size, to find the depth limit;
- escalate `numpoints` only afterwards, one step at a time, re-reading the
  meter each time.

Budget the whole session before starting: the allowance funds roughly three
container restarts, and a restart is not optional if the stream drops.

---

<!-- moved from CLAUDE.md 2026-09-04 — the Stage 4 where-it-runs preamble and the timing measurement — folded into the runbook section -->

**Decided 2026-08-22, before any run.** A run whose results have no defined path
home is how the `walkforward_runs` gap happened twice: the 2026-07-15 AUDUSD
promotion has no persisted walk-forward because the table did not exist yet, and
the EURUSD REJECT-vs-MARGINAL discrepancy is permanently unresolvable because no
run recorded its candles. **Define the import before the export.**

### ⏱️ HOW LONG IT TAKES — 2 minutes per strategy, NOT 27

**Measured 2026-08-23**, full four-stage gauntlet, AUDUSD 15MIN williams_r,
29,995 candles: **1 minute 48 seconds.** The 27-minute estimate that circulated
before the rehearsal was **~15x too high** and must not be used for planning.

| stage | duration |
|---|---|
| single backtest | ~1 s |
| walk-forward | ~2 s |
| permutation, 200 synthetic runs | 67 s ← the slow stage |
| stability map, 84 cells + MC top-5 | 37 s |

Plus ~1 minute for export → scp → import → read-back. **Thirteen strategies is
well under an hour, not an evening.** Consequences: there is no case for
parallelising, no case for a reduced gauntlet on time grounds, and no reason to
run it unattended overnight.

---

<!-- moved from CLAUDE.md 2026-09-04 — the annotated architecture tree — annotations duplicated the Alerting, Risk Management and Selector sections, and two entries had gone stale -->

main.py                     FastAPI entry point
webhook/receiver.py         POST /webhook — alert parser
                            ✅ Friday pre-weekend block
                            ✅ SwiftAlgo $75 daily loss limit
bot/execute_trade.py        Trade logic, session, execution
                            ⚠️ Requires permission to modify
                            Per-symbol cooldown (not global)
bot/live_signal_loop.py     ✅ Unified signal loop (HOUR + 5MIN)
                            Wakes every 5min, timeframe-aware
                            Paper trade mode via PAPER_TRADE_SYMBOLS
                            OR active_strategy.status='paper'
                            ATR-based SL/TP, candles[-2] dedup
                            Dedup key: (symbol, timeframe, strategy_name)
                            Weekend auto-close (Fri 20:40 UTC)
                            Market hours block per symbol
                            Daily loss limit $75 (signal_loop)
                            Paper trade resolver runs each cycle
                            ✅ Heartbeat upsert end of every cycle
bot/notifier.py             ✅ send_telegram() — see Alerting section
scripts/watchdog.py         ✅ Host cron, heartbeat/duplicate/container checks
scripts/daily_summary.py    ✅ Host cron 23:00 UTC, one summary message
risk_manager.py             Lot size ($10 USD fixed risk, see Risk Management)
risk/daily_loss.py          ✅ Per-(symbol,strategy_name) $75 daily loss limit
risk/concurrent_positions.py ✅ Max concurrent positions per symbol (cap=1),
                             signal_loop live path only, see Risk Management
ig_env.py                   ✅ get_ig_credentials() — DEMO/LIVE switch, see Broker section
filters/rule_filters.py     Trend filter (disabled)
filters/vix_filter.py       VIX filter — blocks swing entries >= 18
                            Fails open (API error → allow)
                            Called once per signal_loop cycle
filters/webhook_filters.py  Session / spread / macro filters
                            should_block_session() — UTC window per symbol
                            should_block_spread() — 2× normal spread
                            should_block_macro_event() — MACRO_EVENTS list
                            Update MACRO_EVENTS every Sunday
data/positions_poller.py    ✅ Polls IG every 30s, close detect
                            ✅ Column names fixed (dealId not position.dealId)
                            ✅ _verify_closed_on_ig() before any close
                            Deferred P&L checker (5min, 24h window)
database/db.py              ✅ SQLite connection/setup
                            ✅ paper_trades table added
database/models.py          ✅ All table schemas + queries
                            ✅ log_paper_trade (stamps paper_model +
                               spread_model), get_pending_paper_trades,
                               resolve_paper_trade
                            ❌ get_paper_trades / get_paper_trade_stats /
                               get_paper_stats_by_symbol DELETED 2026-08-16 —
                               zero callers, and dead code that looked like the
                               canonical read path. Paper reads go through raw
                               SQL composed with
                               database/paper_filters.py::paper_where(), which
                               is now the single definition of "a countable
                               paper row" (real vs shadow, resolver model).
dashboard/app.py            ✅ Streamlit entry point
dashboard/pages/            ✅ Pages 01-08 complete
  01_overview.py            Signal monitor: LIVE + PAPER sections
                            Alert banners, cron status, today P&L
  02_trade_log.py           Full history, sync from IG, manual entry
  03_calendar.py            Daily P&L heatmap
  04_backtest.py            Strategy results + equity curve inspect
  05_positions.py           Live open positions
  06_sync.py                IG sync page (standalone)
  07_performance.py         Analytics: by symbol, source, strategy
                            Paper vs Live comparison section
  08_paper.py               Paper trading log + simulated equity curve
backend/strategies/         ✅ 13 strategies built
  base.py, rsi.py, supertrend.py, vwap_ema.py,
  ema_ribbon.py, bb_squeeze.py, rsi_divergence.py,
  orb.py, ichimoku.py, keltner.py, stoch_rsi.py,
  ema_cross_volume.py, vwap_mean_reversion.py,
  connors_rsi2.py, williams_r.py, macd_rsi.py
backend/backtesting/        ⚠️ engine.py, metrics.py
                            engine.py violates its own signal contract —
                            see findings doc finding 1 + 12
scripts/run_backtest.py     ✅ CLI backtest runner
scripts/run_daily.py        ⛔ 06:00 UTC cron DISABLED 2026-08-15
scripts/score_strategies.py ✅ Score all backtest_results
scripts/select_strategy.py  ⛔ INERT since 2026-08-15 — see Selector
                               Disabled section
                            SYMBOL_BLOCKLIST = {"BTC","US100","US500"}
                            STRATEGY_BLOCKLIST — per (symbol,tf,strategy)
                               tuple; allowlist by omission, NOT a
                               symbol-wide block
scripts/resolve_webhook_outcomes.py
                            ✅ Stage E — own cron line, 06:10 UTC
scripts/sync_ig_trades.py   ✅ IG trade sync, self-contained session
                            ✅ Duplicate prevention via deal_reference
                            ✅ Price+symbol+date secondary check
scripts/backfill_pnl.py     ✅ Backfill missing P&L

---

<!-- moved from CLAUDE.md 2026-09-04 — the paused live-account rebuild scaling plan -->

### Account Rebuild Mode (2026-07-02) — PAUSED during DEMO validation
Live account rebuild scaling plan (resumes if/when reverted to LIVE):
  $100 → $200: $3/trade
  $200 → $500: $5/trade
  $500+:        $10/trade
Full $10 risk restored 2026-07-08 for the DEMO validation phase —
demo has no real capital to protect, so the rebuild-mode throttling
and GBPUSD's FRAGILE-verdict half-risk are both suspended, not
deleted. Re-apply the scaling plan above when reverting to LIVE.

### Per-Symbol Risk Overrides (risk_manager.py RISK_PER_TRADE_OVERRIDE)
| Symbol | Risk/Trade | Reason                        |
|--------|------------|-------------------------------|
| EURUSD | $10        | Demo validation phase (2026-07-08) |
| GBPUSD | $10        | Demo validation phase — FRAGILE-verdict half-risk suspended, not deleted |
| US500  | $10        | Demo validation phase (2026-07-08) |
| USDCAD | $10        | Data-collection instance (2026-07-14) |
| AUDUSD | $10        | Demo — no bankroll to protect. Phase-3 lead candidate (2026-07-15); real sizing per the ruin table below at Phase 5 |
| All    | $10        | Default                       |

---

<!-- moved from CLAUDE.md 2026-09-04 — the DAX cache blocker's original diagnosis and root cause — the fix now exists -->

> **✅ ROOT CAUSE FOUND 2026-08-22 — it is not DAX data. It is `EWG`.**
> `fetch_twelvedata.py`'s `SYMBOL_MAP` routes `"DAX" -> "EWG"`, the **iShares
> MSCI Germany ETF**: USD-denominated, ~$40/share, a different constituent set
> from the DAX index. Measured: last close **40.59**, median bar range
> **0.060** — an ordinary $40 ETF behaving normally. **No rescaling factor can
> repair it** (wrong instrument, wrong currency, wrong constituents). See
> findings doc finding 30, which audits all 10 `SYMBOL_MAP` entries. The
> original diagnosis below is retained as the observation that led here.

`scripts/candle_cache/DAX_15MIN_AV.json` has a **median 15-minute high-low range
of 0.055 index points** across 10,270 candles. That is not the DAX — a real DAX
15MIN range is tens of points. The cache is mis-scaled, or it is not DAX data.

Consequences: the `_MIN_SL_DIST` floor of 5.0 binds on **100%** of its candles,
and engine lot sizing hits the MAX clamp on **100%** of them. Any backtest run
on this file produces numbers that mean nothing.

**Do not run a gauntlet, sweep, or walk-forward on DAX until the cache is
re-fetched and its scale verified against IG.** Diagnosed 2026-08-16 while
measuring floor-bind frequency for the engine parity work; not investigated
beyond establishing that the data is unusable.

---

<!-- moved from CLAUDE.md 2026-09-04 — the import step's full rule text — condensed into the runbook -->

### The import step — BUILT, and it has run

`scripts/import_stage4.py`. **The "SCOPED, NOT BUILT — build before Stage 4
executes" scoping is obsolete** and archived → `docs/OPERATIONS_LOG.md`; it is
kept because the six refusal rules were designed before any code and the design
held.

**What crosses:** only rows from the run — `backtest_results` and
`walkforward_runs` at `engine_version = CURRENT_ENGINE_VERSION` and
`run_at`/`created_at >= <batch start>`. The local DB's 5,329 pre-parity
`backtest_results` and 276 `walkforward_runs` (1,166 and 82 ETF-contaminated)
**never cross**. Transport is a standalone `stage4_<UTCstamp>.db` with the same
two schemas — inspectable before it is trusted.

⛔ **NEVER copy the local `trades.db` over the VPS one.** It would destroy the
live `trades`, `paper_trades`, `signal_log` and `active_strategy`. The import is
additive row by row or it does not happen.

**The six rules are refusals, not warnings:** (1) refuse a foreign
`engine_version`; (2) refuse a foreign `spread_model` — and compare
`spread_table_sha` too, because a name can be kept while the numbers change;
(3) insert **without `id`**; (4) **idempotent** on the natural key
(`strategy_name, symbol, timeframe, params_json, run_at`, plus `run_type` and
`cache_file` for walkforward) — a re-run must be a no-op; (5) `Connection.backup()`
first and record it in the Database Backups table in the same change;
(6) read back and report counts — never infer success from the absence of an
exception.

⚠️ **`backtest_results` still has no `produced_on`/`imported_at`/cache-provenance
columns** (finding 31), so an imported row's off-host origin is not recorded on
the row itself. `walkforward_runs` carries it in `extra_json`.

---

<!-- moved from CLAUDE.md 2026-09-04 — the asymmetric-fallback note -->

### Related, recorded not fixed

`_rest_fetch`'s fallback is **asymmetric**: quota exhaustion raises
`_QuotaExceeded` and gets yfinance; empty prices or an unresolved `ig_scale`
return `None` and get **nothing**. On the 2026-08-22 restart that left US500
15MIN+HOUR, US100 15MIN and USDCAD 15MIN with empty buffers and no fallback
attempted (`warm-up got nothing ... source=IG REST`). Gap-backfill covered it
minutes later, by luck.

### Index data — RESOLVED by Dukascopy, 2026-09-04

---

<!-- moved from CLAUDE.md 2026-09-04 — the limit-unknown analysis and the 09-02 split's size table — the limit is now known to be 150,000 -->

## ⚠️ SIZE — this file is split, and the limit is NOT known

**Split 2026-09-02.** This file had reached **204,375 chars** because every
dated check, deploy, rehearsal and finding appended to it — roughly **+45,000
in three weeks**.

| | chars |
|---|---|
| before the split | 204,375 |
| **CLAUDE.md now** | **145,553** (incl. this section and the routing rule) |
| `docs/OPERATIONS_LOG.md` (dated records: CHECK results, deploys, rehearsals) | 58,572 |
| `docs/INCIDENT_HISTORY.md` (incident write-ups, superseded tables, strategy design notes) | 35,780 |

Routing for anything written from here on: see **ROUTING RULE** below.

Nothing was deleted. **Line-level audit: 2,635 substantive lines from the
pre-split file, 0 not conserved across the three files.** All 23 sole-copy
probe strings still resolve.

### What is actually known about the limit — say this, do not round it off

- ✅ **The file arrived INTACT at 195,382 chars on 2026-09-02.** Verified, not
  assumed: the final line of the file was present in context, as were landmarks
  at offsets 27 / 17k / 87k / 140k / 182k / 194k. No truncation from either end,
  no mid-file hole.
- ❌ **Where the cliff is remains UNKNOWN.** The ingestion limit cannot be read
  from inside a session. "Intact at 195k today" is not "safe at 250k tomorrow".
- **This needs checking outside a session.** Until it is, treat the headroom
  above as real but unmeasured — it is a smaller number than before, which is
  not the same as a number known to be under the limit.

---

<!-- moved from CLAUDE.md 2026-09-04 — a 'Live — 2 instances' heading and roster table that assert two active rows; there are now zero -->

### Live — 2 instances (verified against `active_strategy` 2026-08-21)

**As of 2026-08-21T18:41:31Z there are exactly TWO `status='active'` rows, and
both are webhook swiftalgo.** No `live_signal_loop` strategy is trading live.

| id | Symbol | TF | Strategy | Source | Rostered params |
|----|--------|-----|----------|--------|-----------------|
| 11 | EURUSD | HOUR | swiftalgo | webhook | n/a — Pine Script upstream |
| 13 | US500 | HOUR | swiftalgo | webhook | n/a — Pine Script upstream |

Both **demo** (account Z67Y2C). `backtest_id` NULL on both — no recorded
backtest provenance (findings doc finding 13).

---

<!-- moved from CLAUDE.md 2026-09-04 — the noise-floor reading guide — the bar itself stays in CLAUDE.md -->

Pooled: **0.547 pips of noise against 0.850 pips of modelled spread = 64%.**

**How to read it, precisely — the two effects behave differently:**
- **Per-bar trigger evaluation IS affected.** A 0.46–1.01 spread-width noise on
  a level check can flip whether a bar touched an SL or TP. This is the real
  constraint and it does not average away.
- **Aggregate P&L is NOT affected the same way.** The mean is ±0.06 pips, so
  over hundreds of trades the systematic component is negligible. **This is the
  material difference from Twelve Data**, whose +3.2 pip EURUSD mean was a
  *bias* that never averages down no matter how many trades you run.

> **THE BAR: an edge smaller than ~0.5–0.6 pips per bar cannot be
> distinguished from corpus error.** Carry this into the Stage 4
> pre-registration alongside the existing "no promotion decision follows"
> entry.

⚠️ **All four means land at −0.055 to −0.057 pips — identical to three decimal
places across four different instruments.** That is not a per-symbol vendor
offset; it looks like a constant sub-tick or rounding artifact in one of the
two pipelines. Small enough to ignore for now, too uniform to be coincidence,

---

<!-- moved from CLAUDE.md 2026-09-04 — the gap-backfill fix description -->

### ✅ FIXED — gap-backfill no longer duplicates warm-up (change 1, 2026-09-02)

`_backfill_gap` had an upper bound and no lower one: it ran for every pair on
every reconnect and always requested the `WARMUP_COUNT` ceiling, re-fetching
200 points per pair seconds after warm-up had filled the same buffers. **1,400
points off a 10,000/week allowance for zero candles, every restart.** Finding
37; full pre-fix measurement → `docs/INCIDENT_HISTORY.md`.

Fixed by `_bars_missing()` — skips when the buffer is current (`missing <= 1`)
or future-dated (`missing < 0`); unknown still fetches, because a redundant
backfill costs points while a wrongly-skipped one leaves the loop on stale
candles.

**NOT fixed: sizing a real backfill to the measured gap.** That needs the
minimum accepted `numpoints`, still unmeasured.

---

<!-- moved from CLAUDE.md 2026-09-04 — the Stage-1 head, already a pointer; its content is in the archive it points at -->

**Stage 1 (2026-08-16), four commits `e0f51f8..36fac3b`: the backtest was
modelling a different strategy from the one running live.** What `parity-v2`
did, the entanglement finding, the convergence table and the four unmodelled
mechanics → `docs/OPERATIONS_LOG.md`.

One result is worth keeping in front of every reader: **TP and reversal-exit
MASK EACH OTHER.** Neither change alone explains the result — TP alone barely
moves PF, reversal-off alone is degenerate. **Only together do they resemble
live**, so neither would have shown up in isolation.

⛔ **The Stage-1 note that `SPREAD_COSTS` is "deliberately LEFT IN PLACE" is
VOID** — parity-v3 deleted the constant. Archived with the block above rather
than edited away, because the reasoning for leaving it (removing it would make
every backtest look better while being no more correct) is what a future
"simplify the cost model" instinct needs to read.

---

<!-- moved from CLAUDE.md 2026-09-04 — the profit_factor migration record; the .get() lesson and the correction stay -->

### ⚠️ `backtest_results.profit_factor` did not EXIST until 2026-09-04

**Not "was NULL" — the column was absent.** Never in the `CREATE TABLE`, never
in any migration, never in `insert_backtest_result`'s INSERT. Meanwhile
`walkforward_runs` has carried `median_pf` since the day it was created. **The
table the selector actually reads had no profit factor; the one it does not
read did.** Same shape as finding 31 (cache provenance) and the
`spread_table_sha` NULLs — the gap was in the table that matters.

**Why it survived, and this is the reusable part:** every reader does
`dict(row).get("profit_factor")`, and **`.get()` returns `None` for an ABSENT
KEY exactly as it does for a NULL value.** A populated-but-empty column and a
non-existent one are indistinguishable through `.get()`. This file recorded it
as "NULL on every row" on 2026-09-03 for precisely that reason; that reading
was wrong and the correction is here rather than in the archive. **To ask
whether a column exists, use `PRAGMA table_info`, never `.get()`.**

Fixed forward-only: migration adds `profit_factor REAL`, and
`insert_backtest_result` binds `:profit_factor` with **no `.get()` fallback**,
so a caller that omits it raises rather than writing NULL (verified: it does).
`scripts/run_backtest.py` populates it from the **same** `calc_profit_factor`
the walk-forward path uses — one function, two callers.

**Pre-existing rows stay NULL and are NOT backfilled.** 5,332 local rows,
every one `pre-parity-v3`; they are history, not evidence.

✅ **CORRECTION — the migration HAS reached the VPS.** This section read *"THE
MIGRATION HAS NOT REACHED THE VPS … still has no `profit_factor` column —
verified 2026-09-04 by `PRAGMA table_info`"* (archived → `docs/OPERATIONS_LOG.md`).
That reading was taken **before** the Stage 4 import; the 09:34Z deploy
pre-flight re-read the VPS and found `backtest_results` at **28 columns with
`profit_factor`**, gained during that import. **The deploy's migration step is
a no-op.**

⚠️ **Two dated observations of the same table disagreed inside one file and
both were labelled 2026-09-04.** A timestamp to the day is not enough to order
two readings of a thing that changed that day.

---

<!-- moved from CLAUDE.md 2026-09-04 — the collector's live-path consequence and rebuild design note -->

### The collector is off. Do NOT re-enable it in its old form.

**222 log lines, 222 quota errors, ZERO successes** over the whole life of the
image; its output directory never existed in the container; its budget was
**100,800/week against a 10,000/week allowance — 10.08x**, exhausted in ~16.7
hours, ~98% waste. Diagnostic table → `docs/OPERATIONS_LOG.md`.

**Live-path consequence, which is why this was not housekeeping:** with the
allowance at zero, `candle_stream._warm_up` and `_backfill_gap` fall through to
yfinance on **every pair**. `CANDLE_SOURCE=ig_stream` was only half true — IG
ticks, **yfinance seed data**. The 2026-07-15 flip exists because off-session
yfinance is stale on indices, so the collector was quietly reintroducing the
exact failure the flip removed, while producing nothing. Findings doc finding 35.

A workable design, for whenever it is rebuilt: **hourly at `numpoints=6`
(~3,024/week)** or 4-hourly at `numpoints=20` (~2,520/week), writing to the
volume-mounted `./database` (a `candles` table with `UNIQUE(symbol,timeframe,
time)`) rather than an image layer, and self-throttling on `remainingAllowance`
so the live path keeps a reserve. `scripts/candle_cache/` is **not** a volume
(`docker-compose.yml` mounts only `./database`) — anything written there dies
with the image layer.

---

<!-- moved from CLAUDE.md 2026-09-04 — the mode-flag dispatch bug, now fixed to refuse -->

### 🔴 A GAUNTLET RUN WRITES NO `backtest_results` ROW — the flags do NOT combine

`--stability-map`, `--monte-carlo`, `--permutation` and `--walk-forward` are
checked in that order and **each branch `return`s**, so passing all four runs
only `--stability-map` and silently ignores the rest. All of them return before
the single-backtest save, so a gauntlet invocation writes **only**
`walkforward_runs`.

The first attempt at this batch did exactly that: ten runs "completed",
`walkforward_runs` grew by 307, and `backtest_results` did not move at all.
Caught by enumerating both counts, not by any error. **The gauntlet is FOUR
separate invocations per strategy**, and that is what the 2026-09-04 batch ran.

✅ **FIXED 2026-09-04 — it now REFUSES rather than silently dropping flags.**
Multiple mode flags exit 2 with a message naming every flag passed, which one
would have run, and the four-invocation sequence. Three genuine composites are
still allowed (`--stability-map --monte-carlo`, `--walk-forward --monte-carlo`,
`--walk-forward --sweep`) because those are real pairings inside one branch,
not dropped flags. They were **not** made to compose — composing would layer a
second dispatch model on a chain that already returns, and the gauntlet
genuinely is four invocations.

### 🔒 No promotion decision follows from Stage 4

---

<!-- moved from CLAUDE.md 2026-09-04 — the reduced-gauntlet expectation and its 12-of-13 correction -->

### 🟡 EXPECT 8 OF 13 ROWS TO BE REDUCED_GAUNTLET — that is the plan, not a fault

`STABILITY_GRIDS` in `scripts/run_backtest.py` contains **only `williams_r`**.
Every other rostered strategy hits the no-grid branch and persists a
`REDUCED_GAUNTLET` marker row instead of a stability map. Verified working:
forcing it with `bb_squeeze` writes one `stability_map` row, verdict
`REDUCED_GAUNTLET`, fully stamped and carrying
`extra_json.params_source = "roster:active_strategy.id=24"`.

**5 of the 13 paper rows are `williams_r`** (ids 6, 22, 32, 34, 36) and get real
84-cell maps; the rest get markers. **A second marker verdict exists —
`NOT_RUNNABLE`** — for a strategy that cannot be backtested at all; the no-grid
branch used to write `REDUCED_GAUNTLET` *before any backtest ran*, so
"ran, no grid" and "could not run" were indistinguishable. Safe to add because
**nothing reads `walkforward_runs.verdict`** (enumerated before the value was
chosen, not after).

> 🔴 **THIS HEADING READ "12 OF 13" AND THAT IS WORSE THAN HAVING NO NUMBER.**
> Its whole purpose is to separate "exactly as planned" from "something is badly
> wrong" — with 12 in it, a **correct** run returning 6 markers would have been
> flagged as anomalous. **The check would have manufactured the alarm it exists
> to prevent.**
>
> **The cause generalises:** `STABILITY_GRIDS` is keyed by strategy **NAME**,

---

<!-- moved from CLAUDE.md 2026-09-04 — the pre-registration pointer, duplicated by the Stage 4 re-run section -->

Both Dukascopy pre-registrations → `docs/OPERATIONS_LOG.md`. They are what make
the re-run a test rather than a story, and they record a prediction **right on
direction, wrong on attribution**: offset magnitude predicted almost nothing,
**sample size predicted everything**.

> **Thirteen rows near 1.0 read as a ranking and are not one — the error bars
> overlap.** Same shape as the pre-parity scores that promoted `US100 HOUR
> supertrend` unreviewed, where an ordering was treated as evidence because it
> was the only thing on the screen. **The bar: an edge smaller than ~0.5–0.6
> pips per bar cannot be distinguished from corpus error.**

---

<!-- moved from CLAUDE.md 2026-09-04 — Layer 1's full behaviour description -->

### Layer 1 — bot/notifier.py
`send_telegram(message, level="INFO"|"WARN"|"ERROR") -> bool`
POSTs to Telegram via urllib (no new deps). Never raises — wraps
everything, returns False on any failure, prints locally.
Level prefixes: 🟢 INFO, 🟡 WARN, 🔴 ERROR (red reserved exclusively
for system problems — CLOSED trade alerts always use level="INFO"
with the win/loss emoji embedded in the message text instead).
Rate limit: 20 msg/60s. Over cap: message dropped, drop-counter
incremented, count appended to the next message that does send
("...+3 alerts dropped"). 5s HTTP timeout — a slow Telegram API can
never block a trading cycle.

---

<!-- moved from CLAUDE.md 2026-09-04 — a 'nothing built, nothing wired in' preamble for a corpus that is now built and wired in -->

**Measurement only. Nothing built, nothing cached, nothing wired in.** The
numbers below decide whether to build; they are not themselves a change.

Client: **`dukascopy-python` 4.0.1**, pip-installed to a scratchpad `--target`
dir (WSL has no `python3-venv` and `ensurepip` is absent; no system package was
installed and `requirements.txt` is untouched).

---

<!-- moved from CLAUDE.md 2026-09-04 — the source-comparison detail; the adoption verdict stays -->

### 🔴 Source comparison — computed on UNIQUE OBSERVATIONS, not rows

**The correct unit is one observation per `(symbol, stream_time)`**, not one
per `candle_source_compare` row — that table logs once per strategy CHECK, so
rows over-count by 1.29–1.35x. **Both tables → `docs/OPERATIONS_LOG.md`.**

**The adoption decision does not merely survive the correction — it
strengthens.** On unique observations Dukascopy wins **every metric on every
symbol**, including stdev, which was the one column Twelve Data won on the row
basis (e.g. AUDUSD 0.501 vs 0.749; EURUSD 0.624 vs 0.857).

🔴 **Dukascopy's stdev roughly HALVES on dedup; Twelve Data's barely moves.**
That asymmetry is the whole story: the repeatedly-observed bars were precisely
the divergent ones. Twelve Data is *uniformly* displaced, so dedup changes it
hardly at all. **All four Dukascopy means land within ±0.08 pips of zero.**

⚠️ **All four means sit at −0.055 to −0.057 pips — identical to three decimals
across four instruments.** Not a per-symbol vendor offset; it looks like a
constant sub-tick or rounding artifact in one of the two pipelines. Too uniform
to be coincidence, small enough to ignore until someone chases the last tenth
of a pip.

---

<!-- moved from CLAUDE.md 2026-09-04 — the two gap-backfill verification summaries -->

#### ✅ VERIFIED TWICE — restart cost HALVED, and the ordinary-gap case closed

**Both verification records → `docs/OPERATIONS_LOG.md`**, each a per-pair
enumeration rather than an assertion (the shape ENUMERATE, DON'T ASSERT
prescribes: one `[ig_allowance]` line per pair that fetched, one skip line
naming its reason for every pair that did not, and **no pair silent in both
lists**).

Standing results:

| | before | after |
|---|---|---|
| restart cost | 2,800 points | **1,400** (7 pairs x 200, backfill contributed 0) |
| real 7-min reconnect | — | **1,200** — 6 pairs correctly fetched, 1 correctly skipped |

The weekly allowance now funds ~7 restarts instead of 3.

⚠️ **The STORM case is still UNTESTED.** 2026-08-28 was 511 backfills from
reconnects *seconds* apart against buffers a previous reconnect had just
filled. One seven-minute outage does not exercise that path. **Do not read the
above as closing it.**

⚠️ **The burn window was NON-DIAGNOSTIC and knowing why matters:** it held
**zero disconnects**, and `_backfill_gap` runs only from
`_reconnect_supervisor`, so a *pre-change* container would have burned zero in
that window too. A window in which both hypotheses predict the same
observation proves nothing (rule 6).

**⏸️ HOLD — the finding-38 probe is deliberately NOT run.** Budget it against
the observed post-change daily burn rate, not against the headline
`remaining`.

---

<!-- moved from CLAUDE.md 2026-09-04 — the ig_allowance.py description -->

### The allowance is logged — `ig_allowance.py`

IG returns `allowance{remainingAllowance, totalAllowance, allowanceExpiry}` on
**every successful** `/prices` response. **Both consumers did
`result.get("prices")` and dropped the rest**, so the shared budget was
unmeasured and the reset time unknown — for the life of the system. Now parsed
and printed at both sites, tagged by source. Rollout record →
`docs/OPERATIONS_LOG.md`.

**It reports, it does NOT throttle.** A caller wanting to reserve budget reads
`remaining` and decides. *A logging helper that can refuse is a logging helper
that can stop a warm-up.* Never raises; stdlib-only, zero project imports (same
safe-import contract as `symbols.py` / `engine_version.py`).

⚠️ **The reset time is only learnable from a request that SUCCEEDS** — a 403
carries no allowance block. ⛔ **Read that as EXACTLY what it says.** It is
about what a 403 can *teach* you; it does **not** say a failed request is free.
Refused requests are attempted and charged, which is how the allowance was
destroyed on 2026-08-25 — see rule 5.

---

<!-- moved from CLAUDE.md 2026-09-04 — the findings-doc warning as written 2026-08-12 — its 'nothing is fixed' claim and its live-row counts have both been overtaken -->

### ⚠️ Read this before trusting any performance figure in this file
`docs/SESSION_20260812_FINDINGS.md` is the authoritative record of 13 defects
found in the 2026-08-12 audit. **Nothing in it is fixed.** It covers, and this
file does NOT duplicate: engine parity (finding 1 — the backtest applies no
take-profit for 21 of 34 strategies and sizes at $15 vs live $10), the paper
resolver as a second inconsistent synthetic model (2), `status` fail-open
defaults (4), first-activation with no score threshold (5), backtest
provenance across the roster (13), and the local-vs-VPS corpus split (11).

Consequences that apply to this whole file:
- **Every backtest score, PF, and walk-forward verdict quoted below was
  produced by the pre-parity engine.** They are recorded as history, not as
  current evidence. Do not promote on them.
- 26 of 31 roster rows use a strategy that never emits `tp_price`; only 2 of
  8 live rows carry a `backtest_id` at all.
- Re-running the gauntlet after the engine fix is **regeneration, not
  reproduction** — for walk-forward there is no persisted artifact to diff
  against (finding 7).

---

<!-- moved from CLAUDE.md 2026-09-04 — Layer 4's coverage list -->

### Layer 4 — scripts/daily_summary.py
One Telegram message at 23:00 UTC (07:00 MYT), host cron (same reason
as watchdog — needs to read watchdog_alerts.jsonl, which lives on the
host filesystem). Stdlib-only, same .env/sqlite3 approach as
watchdog.py. Covers: trades opened/closed + net P&L + win/loss per
strategy (last 24h), current open positions, heartbeat status per
name, and watchdog alerts fired in the last 24h (read from
watchdog_alerts.jsonl — shows fired-and-cleared events, not just
conditions still unresolved at summary time).


---

<!-- moved from CLAUDE.md 2026-09-04 — the wrong-runbook-step narrative; the working checks stay -->

⚠️ **Step 6 was WRONG until 2026-08-21** and read
`curl localhost:8000 + curl localhost:8501`. **Neither port is published to
the host.** `docker-compose.yml` exposes them container-internally
(`8000/tcp`, `8501/tcp`, no host mapping) and only nginx maps
`0.0.0.0:80->80/tcp`. Both of those curls return **`000` — connection refused —
on a completely healthy stack**, so anyone following the old runbook got a
false failure and started debugging a working system. Confirmed by doing
exactly that on the 2026-08-21 deploy.

---

<!-- moved from CLAUDE.md 2026-09-04 — the spread table's provenance bullets and the zero-dispersion explanation -->

- **Frozen bounds:** `SINCE=2026-08-16T00:00` (incl) → `UNTIL=2026-08-29T00:00`
  (excl). Two complete Mon–Fri cycles. The bounds are what make the sha
  reproducible — the pool grows every five minutes, and it demonstrably grew
  *between* the verification runs.
- **`spread_table_sha = c0c905fc6c071dd4`**
- Lives in `spread_model.py` as `MEASURED_SPREADS_2026_09`, with
  `_PROVENANCE` (n, p90, max per symbol) and `_WINDOW` (bounds, filter,
  source) beside it. Rebuild with `scripts/build_spread_table.py`.

🔴 **US500 AND US100 HAVE ZERO DISPERSION — NO PERCENTILE OF THIS POOL CAN
EVER GIVE THE INDICES A TAIL.** median = p90 = max, on **all 1,074** US500
samples (0.6) and **all 906** US100 samples (2.0). Not one sample differs.
That is a broker-**posted tier**, not a distribution — and it matches CHECK 2's
rollover measurement, where the same two sat flat at 1.5 and 5.0 while FX
widened 11–19×. IG posts two fixed tiers and switches between them. So p99,
p999 and max on the indices are all 0.6 and 2.0 **by construction**; an index
tail needs a different data source (tick quotes, or the rollover/reopen tiers
treated *as* the tail), not a higher percentile of this one. FX is the opposite
shape — EURUSD's median equals its p90, with max/median 4.5–6.5× entirely in
the last decile.

🔴 **THE TAIL IS UNCALIBRATED. This is a median-only table. RISK-OF-RUIN AND
DRAWDOWN WORK MUST NOT USE IT.** Ruin lives in the tail. The pre-parity ruin
table was already wrong by more than an order of magnitude (5.58% against a
measured 67.3–84.3%); a median-only spread is how that happens a second time.
`p90`/`max` are recorded in `_PROVENANCE` as context and are deliberately not
in the table.

---

<!-- moved from CLAUDE.md 2026-09-04 — the daily-loss-limit rekeying rationale -->

Keyed per (symbol, strategy_name) as of 2026-07-22 — each instance gets its
own $75 budget, not one combined pool. Fixed because a FRAGILE strategy's
bad day (e.g. GBPUSD williams_r) was blocking an unrelated instance (e.g.
AUDUSD williams_r) even though they share a strategy_name — same-strategy
symbols still isolate from each other. `risk/daily_loss.py`
`is_daily_loss_limit_breached(symbol=..., strategy_name=...)`; call sites
`webhook/receiver.py` and `bot/live_signal_loop.py::_risk_check`. Telegram
alert dedup also moved from one global per-day flag to per (symbol,
strategy_name).

---

<!-- moved from CLAUDE.md 2026-09-04 — the watchdog anti-spam and cron detail -->

Anti-spam: `/tmp/watchdog_state.json`, re-alerts at most every 60 min per
condition, **clears on recovery** so a fresh occurrence alerts immediately.
Every alert actually sent is also appended to `logs/watchdog_alerts.jsonl`
(append-only history, not a replacement for the dedup state).

Host cron `/etc/cron.d/trading-watchdog`: watchdog every 10 min, daily summary
at 23:00 UTC. Full check list and cron lines → `docs/OPERATIONS_LOG.md`.

---

<!-- moved from CLAUDE.md 2026-09-04 — the two recurring post-flip lessons; the live guard stays -->

- **The REST `snapshotTime` bug**: IG returns it in the **account's** timezone
  (MYT+8 here), not UTC. Third instance of the class — *any timestamp from an
  external source may be localized regardless of what the field name implies;
  force-convert, never relabel*. Also hit `_normalize_yf_time` (yfinance
  intraday is exchange-local, BST in summer — a seasonal bug invisible in GMT
  months).
- **The comparison logger was only called from the yfinance-primary branch**,
  so flipping silently killed the exact dataset needed to verify the flip.

**Live guard still in force** (`_check_symbol`): if the stream's latest candle
is older than 3x the timeframe **or timestamped in the future**, FX falls back
to yfinance (WARN, once/6h/symbol); **indices skip the check with no fallback**

---

<!-- moved from CLAUDE.md 2026-09-04 — the dead-spread-filter evidence detail -->

   `data.get("spread")` from the inbound payload, and **0 of 382 stored
   TradingView payloads have ever carried a `spread` key**, so
   `should_block_spread` short-circuits on its `None` fail-open guard before
   the threshold is consulted. All-time `spread_filter` blocks: **0**, against
   session_filter 150, day_of_week 27, daily_loss_limit 15. Separately the
   threshold itself is ~5× too wide (EURUSD `NORMAL_SPREADS` 0.0008 = 8 pips,
   blocking at 16 pips, vs ~1.5 pips measured on a thin weekend book) — so
   fixing the constant alone would change nothing. See findings doc finding 15.
   Live trades are NOT protected against spread blowouts and never have been.

---

<!-- moved from CLAUDE.md 2026-09-04 — the shared-tell paragraph and the prospective-form note; both restated in the rule table -->

#### The tell they share

**Nine of the ten attach a conclusion to an ABSENCE** — no rows, no charge on
the meter, no grep hit, no alert. Absence is where this failure class lives.
When you notice your conclusion rests on something not being there, stop and
run the rule that matches.

⚠️ **Rules 1–4 are also PROSPECTIVE, not just ways to read a result.** The
practical form: **do not restart, rebuild or redeploy in the window before a
dated control check**, and before treating any criterion as failed, state what
would have to be true for it to PASS and confirm the current system permits
that state at all.

---

<!-- moved from CLAUDE.md 2026-09-04 — the collector's failure figures and rebuild design sketch -->

**222 log lines, 222 quota errors, ZERO successes**; its output directory never
existed in the container; **100,800 points/week against a 10,000 allowance =
10.08x**, exhausted in ~16.7 hours, ~98% waste.

🔴 **Live-path consequence — this was not housekeeping.** With the allowance at
zero, `_warm_up` and `_backfill_gap` fall through to yfinance on **every pair**,
so `CANDLE_SOURCE=ig_stream` was only half true: **IG ticks, yfinance seed
data.** The 2026-07-15 flip exists because off-session yfinance is stale on
indices — **the collector was quietly reintroducing the exact failure the flip
removed, while producing nothing.**

**If it is ever rebuilt:** hourly at `numpoints=6` (~3,024/week) or 4-hourly at
20 (~2,520/week), writing to the volume-mounted `./database` (a `candles` table
with `UNIQUE(symbol,timeframe,time)`), self-throttling on `remainingAllowance`

---

<!-- moved from CLAUDE.md 2026-09-04 — the probe-construction gotcha -->

⚠️ **Two probe attempts cost ZERO because they died client-side** —
`return_dataframe` is a **constructor** argument to `IGService`, not a call
argument. Third time this has bitten a probe: mirror `_rest_fetch`'s
construction (`IGService(..., acc_type=..., return_dataframe=False)`) always.

⚠️ **Creating a session in a probe invalidates the `positions_poller` token.**
Known, accepted, still real — probe sparingly.

---

<!-- moved from CLAUDE.md 2026-09-04 — the five Stage 4 gotchas in expanded form -->

**Full text → `docs/OPERATIONS_LOG.md`.** Condensed, because each one cost a
run:

1. **`export_roster.py` must run on the VPS HOST, not in the container.**
   Inside, it records `git_head = NULL` — `git` is not installed in the image
   and `/app` is not a work tree. A roster snapshot with no git HEAD is the
   no-provenance case the script exists to prevent.
2. **Back up on the host; import in the container.** Backing up works as
   `ubuntu` (source opened read-only); importing does not.
3. **The VPS `database/trades.db` is owned by `root`** — any write as `ubuntu`
   on the host dies with `attempt to write a readonly database`. `docker exec`
   is the write path.
4. **`--since` is re-formatted per table, and must be.**
   `backtest_results.run_at` is `'YYYY-MM-DD HH:MM:SS'`;
   `walkforward_runs.created_at` is ISO with a `T`. **`'T'` sorts above `' '`**,
   so one raw string compared against both **silently widens the window by a
   day** and sweeps in rows from before the batch — wrong in the one direction
   nobody checks, because extra rows arriving looks like the import working.
5. **`backtest_trades` does NOT cross.** It is keyed on `backtest_id` and the
   import inserts without ids. **An imported VPS row has no per-trade detail
   behind it** — the aggregate is auditable, the trade list stays local. **Do
   not read absent trades on the VPS as a failed import.**

---

<!-- moved from CLAUDE.md 2026-09-04 — the swiftalgo retirement rationale in full -->

#### ⛔ SWIFTALGO IS RETIRED — the silence is a DECISION, not an outage

**The TradingView source was retired by the operator. The silence since
2026-08-05/06 is EXPECTED. There is nothing to diagnose and nothing to
restore — DO NOT INVESTIGATE IT AS AN OUTAGE.** A future reader finding two
rows flipped on 2026-09-04 plus a month of silence will be tempted to; this
paragraph is the only thing that will stop them, because **`active_strategy`
has no notes column** and those rows carry a status and a bare `updated_at`.

- ids **11** and **13** set `status='inactive'` 2026-09-04T10:20:58Z. They read
  `active` until then, asserting something false.
- **There are now ZERO `status='active'` rows** — 18 `inactive`, 13 `paper`.
  Nothing in the system trades live.
- **`inactive` was used deliberately; a new value such as `retired` would have
  been UNSAFE.** `webhook/receiver.py:265` is
  `status = strategy_row.get("status", "active")` and the only branches are
  `inactive` (blocks) and `paper` — **anything unrecognised falls through to
  LIVE EXECUTION** (finding 4's fail-open default).
- **The receiver machinery is left DORMANT, deliberately.** Harmless, costs
  nothing, there if a source is ever wired up again. Removing it would mean
  touching the execution path.

---

<!-- moved from CLAUDE.md 2026-09-04 — the GBPUSD caveat reversal and the no-cleaning rationale -->

**GBPUSD's caveat is answered and REVERSES:** 84% of its tail bars fall in hours
the bot cannot enter; restricted to `is_entry_allowed` hours its stdev is
**0.419 vs Twelve Data's 1.035 — ~2.5x tighter on the hours that matter.**

**Why no cleaning:** the comparison is symmetric and cannot say which feed is
wrong, so removing spikes would be editing raw market data on a guess. And
`is_entry_allowed` governs ENTRIES, not candle availability — a backtest needs
continuous bars to evaluate holds across excluded hours.

---

<!-- moved from CLAUDE.md 2026-09-04 — the level-check and additive-proof detail -->

**Level check re-run on the FILES AS WRITTEN**, not on what was pulled — the
script refuses to write on failure. **US500 1.010x, US100 1.008x. These are
indices.**

**Additive only, proven:** md5 of all 24 pre-existing cache files taken before
the run and re-verified after — **0 mismatches, 0 missing**, so the `cache_file`
provenance on already-imported Stage 4 rows stays intact. The script refuses to
overwrite without `--force`.


---

<!-- moved from CLAUDE.md 2026-09-04 — a Market Close Times table duplicating the Market Hours table directly above it -->

## Market Close Times (UTC)
| Symbol | Weekday close | Friday last trade |
|--------|---------------|-------------------|
| US500  | 20:00         | 19:45             |
| US100  | 20:00         | 19:45             |
| DAX    | 15:30         | 15:30             |
| BTC    | 24/7          | 24/7              |

## Backtesting Rules (enforced in ALL phases)

---

<!-- moved from CLAUDE.md 2026-09-04 — the DEMO/LIVE credential and revert detail -->

Account: DEMO (Z67Y2C)  |  Was: LIVE (TW75S)
Switch controlled by IG_ACC_TYPE env var, read via ig_env.py
get_ig_credentials() — returns (username, password, api_key, acc_type).
Default LIVE if IG_ACC_TYPE unset.

DEMO credentials are separate from LIVE, NOT the same login:
  IG_USERNAME / IG_PASSWORD / IG_API_KEY           — LIVE
  IG_DEMO_USERNAME / IG_DEMO_PASSWORD / IG_DEMO_API_KEY — DEMO (falls
    back to the LIVE username/password if the DEMO-specific vars are
    absent, but not for this account — they're set and required)

Revert to LIVE:
  1. .env: set IG_ACC_TYPE=LIVE (or remove the var — same default)
  2. SSH VPS → docker-compose up -d   (NOT restart — restart reuses
     the existing container and does not reload .env)
  3. Verify: docker logs trading_bot-bot-1 | grep "Switched to TW75S"

execute_trade.py's hardcoded force-switch to TW75S only runs when
IG_ACC_TYPE=LIVE — in DEMO mode it logs whichever account the session
lands on instead (currently Z67Y2C), since a demo login has no TW75S

---

<!-- moved from CLAUDE.md 2026-09-04 — the reject-reason plumbing detail -->

- place_trade rejection reasons persist to signal_log.error (fixed
  2026-07-25) — previously only `print()`'d, lost on every container
  restart (lost real evidence twice, incl. the USDCAD UNKNOWN-reason
  investigation). `execute_trade.last_reject_reason: dict[symbol->str]`
  set at every `place_trade` failure return; `live_signal_loop.py`'s
  `_check_symbol` reads it right after the call instead of hardcoding
  "place_trade returned False". Module-level dict keyed by symbol, not
  thread-safe — acceptable because "williams_r" only ever runs from the
  single-threaded signal_loop and "swiftalgo" only from the webhook path,
  so no realistic same-symbol collision. Webhook path (`place_trade_from_alert`
  / `webhook_log`) untouched — it never consumed the old string either.

---

<!-- moved from CLAUDE.md 2026-09-04 — the gate-vs-evidence-base reasoning for the flat indices -->

🔴 **The indices being FLAT is itself a finding, and only an all-symbols query
could show it.** The rollover widening is an **FX phenomenon**, so the gate —
which deliberately covers 24/7 instruments — is **broader than the evidence base
that justifies it. This is NOT a reason to narrow it**: the index sample is 11
rows over one hour, an all-instruments rule has no per-symbol branch to drift,
and blocking a low-liquidity hour costs little where nothing is widening. If it
is ever revisited, **this is the starting point and it needs more than one hour
of index data first.**

*(These also quantify the exit-side exposure below: a position held through the
weekend gap exits into exactly these spreads.)*

---

<!-- moved from CLAUDE.md 2026-09-04 — the design-notes pointer's rationale -->

### Paper strategy design notes — MOVED
Entry rules, parameters, baseline backtests and per-strategy rationale for
`williams_r`, `macd_rsi`, `london_breakout`, `stoch_rsi_confluence`,
`ny_session_momentum`, `ema_pullback` and `fvg` → `docs/INCIDENT_HISTORY.md`.

Kept out of this file deliberately, and not only for size: **params recorded in
docs have diverged from the live roster four times** (see Critical Rules). The
archive copy is the design intent as written; `active_strategy` is what
actually runs, and it is the only source any analysis may use.

⚠️ Two of those write-ups quote figures now VOID — US500/US100 15MIN
`ema_pullback` (PF 1.57 / PF 3.17) was measured on **ETF-scaled candles**, see
the ETF cache blocker.

---

<!-- moved from CLAUDE.md 2026-09-04 — the parity-v2 vs parity-v3 comparison run -->

**Measured effect, AUDUSD 15MIN williams_r, identical candles/params/seed**
(before run from a clean `git archive HEAD` tree, not a remembered number):

| | parity-v2 | parity-v3 |
|---|---|---|
| trades | 221 | **234** |
| PF | **1.0849** | **1.0431** |
| net | $124.45 | **$66.03** |
| win rate | 37.1% | 34.2% |

Trade count **rose**, which is the tell that this is not just "same trades,
more cost": the fill shifts the SL/TP anchors so different bars trigger.

---

<!-- moved from CLAUDE.md 2026-09-04 — the contaminated-row counts and their identifying predicates -->

**Standing consequences:**
- **Marked, not deleted:** 1,166 of 5,329 local `backtest_results`
  (`symbol IN ('US500','US100','DAX') AND timeframe='15MIN' AND
  candles_total > 5000`) and 82 of 276 `walkforward_runs`
  (`cache_file LIKE '%_AV.json'`). Safe because all are `pre-parity-v0` and
  `get_backtest_results()` filters to the current version — reachable only via
  `engine_version=None`.
- `backtest_results` has **no cache-provenance column**, so its count is
  inferred from `candles_total` (finding 31).
- The `ema_pullback` figures produced on these files — US500 15MIN PF 1.57,
  US100 15MIN PF 3.17 — are **VOID**, not merely pre-parity.

---

<!-- moved from CLAUDE.md 2026-09-04 — the gap-backfill verification summary and the non-diagnostic-window note -->

#### ✅ VERIFIED TWICE — restart 2,800 → **1,400**; a real 7-min reconnect **1,200**

Both records → `docs/OPERATIONS_LOG.md`, each a per-pair enumeration (one
`[ig_allowance]` line per pair that fetched, one skip line naming its reason for
every pair that did not, **no pair silent in both lists**). The weekly allowance
now funds ~7 restarts instead of 3.

⚠️ **The STORM case is still UNTESTED** — 2026-08-28 was 511 backfills from
reconnects *seconds* apart. One seven-minute outage does not exercise it.

⚠️ **The burn window was NON-DIAGNOSTIC:** it held **zero disconnects**, and
`_backfill_gap` runs only from `_reconnect_supervisor` — so a *pre-change*
container would have burned zero there too (rule 6).

**⏸️ The finding-38 probe is deliberately NOT run.** Budget it against the
observed burn rate, not the headline `remaining`.

---

<!-- moved from CLAUDE.md 2026-09-04 — the divergence-watchdog tuning detail -->

**`candle_source_compare` HAS a reader** (`watchdog.py::check_candle_divergence`,
threshold 5x a **baked** p99 — baked, not rolling, because a rolling baseline
widens around the anomaly it exists to catch). ⚠️ **Do not retune to silence
US100**: its ~100-pip mean divergence is off-session yfinance staleness, and a
global threshold accommodating it goes blind to FX at 1–2 pips.
`DAX`/`BTC` are named in `DIVERGENCE_NO_BASELINE`; anything unbanded alerts as
UNCHECKED.

---

<!-- moved from CLAUDE.md 2026-09-04 — the demotion headline and the paper-not-inactive mechanism -->

**Reasons are in `active_strategy_history` rows 43–46 — one per instance. Read
those, not a summary.** This file has been wrong about the roster before
(US100 HOUR supertrend ran live undocumented for ~8 weeks), so pointing at the
history table is deliberate. Headline only: no profitable month pooled in
three, best-ever bucket PF 0.86, `parity-v2` independently predicts PF < 1.0 on
all four.

**Why `paper` and not `inactive` — a live operational fact, not history.** The
signal loop iterates `get_active_strategies(symbol)` = `status IN
('active','paper')` (`database/models.py:597`). A symbol with **no runnable
row never reaches `_check_symbol`**, and the spread sample is taken at the top
of that function (`live_signal_loop.py:369`) **before any block check**.
**AUDUSD and USDCAD have no other runnable row**, so `inactive` would have

---

<!-- moved from CLAUDE.md 2026-09-04 — the per-stage gauntlet timings -->

**Measured: 1m48s** for the full four-stage gauntlet on 29,995 candles
(permutation is the slow stage at 67 s; stability map 37 s). The 27-minute
estimate that circulated before the rehearsal was **~15x too high and must not
be used for planning.** **Thirteen strategies is well under an hour, not an
evening** — so there is no case for parallelising, none for a reduced gauntlet
on time grounds, and no reason to run it unattended overnight.

---

<!-- moved from CLAUDE.md 2026-09-04 — the noise-floor reading guide, second pass -->

**The two effects behave DIFFERENTLY and the distinction is the whole point:**
**per-bar trigger evaluation IS affected** — a 0.46–1.01 spread-width noise on a
level check can flip whether a bar touched an SL or TP, and it does not average
away. **Aggregate PF / net / win rate is NOT** — the mean is ±0.06 pips, so the
systematic component vanishes over hundreds of trades. **That is the material
difference from Twelve Data, whose +3.2 pip EURUSD mean was a BIAS that never
averaged down at any trade count.** Reading guide →
`docs/OPERATIONS_LOG.md`.


---

<!-- moved from CLAUDE.md 2026-09-04 — the Phase 7 completed-items list — a record of finished work -->

### Completed in Phase 7 so far
- Daily loss limit $75 for signal_loop (hard stop)
- Daily loss limit $75 for tradingview_webhook (blocks alerts)
- Trade count limits (bug catchers): 20/day, 6/symbol+TF
- Market hours block per symbol with minute-level accuracy
- Friday pre-weekend block at 19:45 UTC (both loop + webhook)
- Weekend auto-close (Fri 20:40 UTC) — fixed API signature
- Positions poller false-close bug fixed (column names)
- _verify_closed_on_ig() safety gate added to poller
- Per-symbol cooldown in execute_trade.py (was global)
- Paper trading system: paper_trades table, resolver,
  dashboard pages 07/08 updated
- Max concurrent positions per symbol — DONE 2026-07-25, but scoped
  differently than originally planned: cap is 1 (not 2) and per
  (symbol, strategy_name) on the signal_loop live path only, driven by
  the stacking-profitability finding (-$219.63 vs first-entry-only,
  see Risk Management). Not a global concurrent-position cap across all
  symbols — see `risk/concurrent_positions.py`.

---

<!-- moved from CLAUDE.md 2026-09-04 — the Test Scripts table — the six pipeline scripts in it are already in the Architecture tree -->

| Script                      | Purpose                     |
|-----------------------------|-----------------------------|
| bot/test_ig.py              | Verify IG session           |
| bot/test_trade.py           | Place test BUY XAUUSD       |
| bot/search_market.py        | Search IG epics             |
| scripts/seed_test_data.py   | Insert fake trades          |
| scripts/backfill_pnl.py     | Backfill missing P&L        |
| scripts/sync_ig_trades.py   | Sync/import IG trades to DB |
| scripts/run_backtest.py     | Run/sweep backtests         |
| scripts/score_strategies.py | Score all backtest results  |
| scripts/select_strategy.py  | Select + activate strategy  |
| scripts/run_daily.py        | Run full daily pipeline     |

---

<!-- moved from CLAUDE.md 2026-09-04 — four lines reworded in place during the cleanup; the originals are kept here so conservation is exact -->

Replaced by a pointer when the armed-symbol analysis above was archived:

**Precision on which symbols were actually armed:** after the 2026-08-13

Duplicate tail fragment from the noise-floor block, superseded by
"small enough to ignore until someone chases the last tenth of a pip.":

and worth a look if anyone ever chases the last tenth of a pip.

Folded into the 2026-08-15 bullet under Infrastructure Incidents:

⚠️ The 2026-08-15 record lists the open positions at that moment. **The roster
churns — never carry a hardcoded position list forward.**

---

<!-- moved from CLAUDE.md 2026-09-04 — the routing-rule preamble, trimmed so the rule section obeys its own 6,000 ceiling -->

**This is a ROUTING rule, not a size rule. Read that distinction before acting
on it.** A size rule says "this file is too long, remove something", and the
obvious way to satisfy it is to delete. This rule never says delete. It says
each line has ONE correct home, decided when the line is written, and the file
stays small as a *consequence* of routing rather than as a goal pursued by
cutting.

The 2026-09-02 split was a one-off fix for a recurring cause. A file that grows
by appending is not fixed by a periodic cleanup — the next three weeks add the
next 45,000 chars. Route at write time.

> **Operational sections carry a CURRENT-STATE head. Dated detail goes to the
> archive AT WRITE TIME, with its stub written in the SAME EDIT — never

---

<!-- moved from CLAUDE.md 2026-09-05 — gap-backfill verification detail and the weekend-restart working; the rule and the numbers stay in CLAUDE.md -->

#### ✅ VERIFIED TWICE — restart 2,800 -> 1,400; a real 7-min reconnect 1,200

Both records were per-pair enumerations with no pair silent in both the fetched
and skipped lists. The weekly allowance funds ~7 restarts instead of 3.

#### Weekend-restart working, 2026-09-05

`bot/candle_stream.py` was not in the deploy diff, so the behaviour is identical
to what cc9055d would have done. `_bars_missing()` measures complete bars behind
on bar-START boundaries against the wall clock; with the book shut since Friday's
close the newest bar is ~39 buckets old, so `missing >= 2` and it fetches — "on
uncertainty this fetches rather than skips", exactly as documented.

Prior verifications, both mid-week with the book open: 2026-09-02 (1,400, 7
skips) and the 2026-09-03 reconnect (1,200, 6 fetched + 1 skipped). The weekend
case had never been exercised since the fix shipped.

---

<!-- moved from CLAUDE.md 2026-09-05 — the 'Related, recorded not fixed' detail; standing rules kept in CLAUDE.md -->

### Related, recorded not fixed

**`_rest_fetch`'s fallback is ASYMMETRIC:** quota exhaustion raises
`_QuotaExceeded` and gets yfinance; **empty prices or an unresolved `ig_scale`
return `None` and get NOTHING.** On the 2026-08-22 restart that left US500
15MIN+HOUR, US100 15MIN and USDCAD 15MIN with **empty buffers and no fallback
attempted**. Gap-backfill covered it minutes later, **by luck**.

**The 2026-08-23 survey said nothing served indices at 15MIN over a
walk-forward span — no longer true**: `*_15MIN_DUKA.json` covers US500/US100 at
index scale over 24 months. Survey table → `docs/OPERATIONS_LOG.md`, kept as the
evidence that the Twelve Data free tier and yfinance genuinely cannot, so nobody
retries them. **yfinance 1h reaches 730 days** (`US500_HOUR_5000_yf.json` is
genuine `^GSPC`); 15m is capped at 60 days.

⛔ **Do not mix sources inside one cache file.** Twelve Data before date X and
IG after is two instruments in one file — the DAX/ETF defect with a subtler
signature. One source per symbol, recorded in the `cache_file` provenance.

---

<!-- moved from CLAUDE.md 2026-09-05 — superseded allowance-state block (pre-deploy reading) -->

### Allowance state — ALWAYS RE-READ, never carry a recorded number

Last read **2026-09-03T16:06:54Z: remaining 8,780 of 10,000, `resets_at`
2026-09-10T12:43:44Z.** **The window is ROLLING and its anchor MOVES** — it
re-anchors to the first request after a reset, and it has already moved once
(04:02 → 07:18 → 12:43). Derive the window from `resets_at` on a **successful**
response; never from a remembered anchor. Reading record →
`docs/OPERATIONS_LOG.md`.

**Baseline burn: ~4,210 points in ~18 hours with NO container restart** —
about 21 gap-backfills. That is finding 37 leaking in *ordinary* operation, and
it is the number to compare the post-change rate against.

⚠️ **`return_dataframe` is a CONSTRUCTOR argument to `IGService`, not a call
argument** — third time this has bitten a probe. Mirror `_rest_fetch`'s
construction always. ⚠️ **A probe session invalidates the `positions_poller`
token** — probe sparingly.

---
