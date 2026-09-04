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

