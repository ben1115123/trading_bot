# Incident History — engineering write-ups moved out of CLAUDE.md

Split out 2026-09-02, alongside `docs/OPERATIONS_LOG.md`.

**SOLE COPY.** Moved, never duplicated. Each block left a stub in CLAUDE.md
naming this file and stating why the content mattered.

Dated incident write-ups, superseded numeric tables, and per-strategy design
notes. Defect diagnoses live in `docs/SESSION_20260812_FINDINGS.md`; standing
rules stay in CLAUDE.md.

---

<!-- moved from CLAUDE.md 2026-09-02 -->

### Price scale quirk — ig_scale.py (fixed 2026-07-09)

> **⚠️ NOT CURRENTLY IN EFFECT — measured 2026-08-18 (findings doc finding 26).**
> Every checked symbol now classifies to **`divisor = 1.0`** on this account
> (EURUSD REST `snapshot.bid` = 1.1578, stream buffer = 1.15817), so
> `to_decimal`/`to_native` currently divide and multiply by one and the
> conversion layer is arithmetically inert. The scale has flipped **at least
> twice** — decimal on LIVE, points on DEMO after 2026-07-08, decimal on DEMO
> now — and the last flip happened with **no account change**: the broker
> changed representation under a running system.
>
> **Do NOT delete `ig_scale` as dead weight.** Its value is the
> classification and the raise-on-ambiguity, never the arithmetic — it is the
> only thing that compares a price against what that price ought to look like.
> `init_price_scales(force=True)` on session recreate is load-bearing for
> exactly this reason. The description below is the state as of 2026-07-08 and
> is retained as history.

CS.D.EURUSD.MINI.IP quoted in native **points scale** (e.g. bid=11423.3)
on the DEMO account (Z67Y2C), not decimal FX price (1.14233) like every
other FX epic and like this same epic on the LIVE account (TW75S).
Discovered via 3x ATTACHED_ORDER_LEVEL_ERROR rejections on EURUSD SELL
(2026-07-08): entry_price came back native-scale from IG while SL/TP
(webhook, always decimal) went out unconverted — stop_level ended up
~10000x off market. Same mismatch silently corrupted candle_stream.py's
yfinance-vs-stream comparison logging (~1e8 "pip" deltas) — and that
comparison table later caught a recurrence in real time
(`2026-07-21T19:20:32`, `delta_pips = -114,008,596`) that **nobody read for
28 days**, because `candle_source_compare` has no consumer. See findings doc
findings 25 and 27.

`ig_scale.py` is the fix: classifies each symbol's native scale
**empirically** — compares the live bid against a known decimal-price
band per symbol — and caches it. Do NOT trust IG's `scalingFactor`
snapshot field: GBPUSD/AUDUSD carry `scalingFactor=10000` despite
already being decimal, while EURUSD (the one epic that actually needed
/10000 on this account) carries `scalingFactor=1`. That field does not
reliably predict which epics need conversion — this was empirically
disproven while diagnosing the bug, not assumed.

Confirmed epic scale differs by ACCOUNT, not just by epic — EURUSD was
decimal on LIVE (TW75S) before the 2026-07-08 switch (every EURUSD
trade in `trades` table pre-dating the switch has decimal entry_price)
and became points-scale only after switching to DEMO (Z67Y2C). Re-run
`init_price_scales(ig_service, EPIC_CONFIG_map, force=True)` after ANY
session recreate or account switch — never assume scale carries over.

Ambiguous readings (fit neither the decimal nor the x10000 band for
that symbol) never guess — they raise, send a Telegram ERROR alert, and
block that symbol from trading (`ig_scale.is_resolved(symbol)` returns
False) until a human resolves it.

All IG price reads/writes route through `ig_scale.to_decimal()` /
`ig_scale.to_native()` at the boundary: `execute_trade.py` (entry_price,
stop_level/limit_level sent to `create_open_position`, risk sizing),
`positions_poller.py` (open_price/bid/offer/close_price, P&L calc),
`candle_stream.py` (REST warm-up OHLC, live stream mid-OHLC — internal
buffers are decimal so the compare-vs-yfinance logging is apples-to-
apples), `sync_ig_trades.py` (openLevel/closeLevel from transaction
history). Everything else in the codebase (SL/TP math, DB storage,
dashboards, webhooks) stays decimal, unchanged.


---

<!-- moved from CLAUDE.md 2026-09-02 -->

### Phase-5 Sizing Reference — Monte Carlo Risk-of-Ruin (2026-07-15)
Bootstrap MC (5000 paths, shared resampled paths across configs, ~~seed=42~~)
on williams_r AUDUSD 15MIN (period=14/oversold=-85/overbought=-20, the
promoted plateau-center params), $500 account:

> ⛔ **`seed=42` HERE IS FALSE AND WAS FALSE WHEN WRITTEN.** `run_backtest.py`
> never passed a seed to `bootstrap_mc` — the parameter defaulted to `None` and
> the run was seeded from OS entropy. This line described a parameter the code
> never received, for four weeks. **The numbers below are therefore not
> reproducible and never were**, independently of every other problem with them.
> Finding 32; sixth instance of documentation asserting a property the code does
> not implement. Struck through rather than deleted — the false claim is the
> finding.



| Risk/trade | Risk-of-ruin | Risk/trade | Risk-of-ruin |
|-----------|--------------|-----------|--------------|
| $2        | 0.00%        | $5        | 5.58%        |
| $3        | 0.18%        | $5.50     | 9.56%        |
| $4        | 1.52%        | $6        | 15.24%       |
| $4.75     | 4.54%        | $7.50     | 37.44%       |

**Headline: 1% risk-of-account ≈ 5.6% ruin probability** ($5/$500 or
equivalently $10/$1000 — confirmed identical by the model, since ruin
depends only on risk-as-fraction-of-account). Largest size under 10%
ruin: $5.50/$500 (9.56%). Largest under 5%: $4.75/$500 (4.54%). Full
sweep (16 configs incl. $10 risk on $1000/$2000/$5000 accounts) persisted
in `walkforward_runs` (run_type='monte_carlo') — **local DB only, zero rows
on the VPS.**

**⚠️ This table does not describe the account the bot is running on.** The
demo account Z67Y2C balance is **$19,542.89** (verified 2026-08-15), not $500.
At $10/trade that is 0.05% of account — off the bottom of the table, where
ruin is effectively nil. Two consequences:

1. The demo account **cannot produce a ruin event**, so demo survival is not
   evidence that any sizing is safe. Nothing about the ladder is being tested
   by current operation.
2. The `$100 → $200 → $500` rebuild ladder in Account Rebuild Mode refers to
   a **live** account that is not currently funded or trading. The ladder and
   this ruin table are both Phase-5 planning artifacts for a future live
   return — neither governs anything running today.

Also inherited: the ruin table was computed from `williams_r` AUDUSD trades
generated by the **pre-parity engine** (no take-profit modelled, $15 sizing).
Its distribution is the flawed model's, so the percentages must be regenerated
after the engine fix before they gate any live sizing decision.



### 🔴 REGENERATED 2026-08-23 — the old figures were optimistic by MORE THAN AN ORDER OF MAGNITUDE

The regeneration flagged above now has its first data point, from the Stage 4
dress rehearsal (same strategy, same symbol, roster params, `parity-v2`):

| | pre-parity table above | **parity-v2, measured 2026-08-23** |
|---|---|---|
| risk of ruin at $10 on $500 | **5.58%** | **67.3% – 84.3%** |

Range because the MC ran on the top-5 plateau cells, not one:

| params (williams_r AUDUSD 15MIN) | risk of ruin |
|---|---|
| `period=21, oversold=-85, overbought=-15` | 67.3% |
| `period=21, oversold=-85, overbought=-10` | 70.6% |
| `period=12, oversold=-95, overbought=-20` | 74.1% |
| `period=14, oversold=-95, overbought=-20` | 80.0% |
| `period=21, oversold=-80, overbought=-10` | 84.3% |

**Every value is more than 10x the number in the table above**, and the best of
them is worse than that table's worst listed configuration ($7.50 → 37.44%).

✅ **REPRODUCIBLE — `seed=42`, stored on every row** (`extra_json.seed`,
`reproducible: true`), regenerated 2026-08-23T04:42Z under the seed contract
from finding 32. Re-run `--stability-map --monte-carlo --seed 42` on
`AUDUSD_15MIN_AV.json` with roster params for these exact figures.

The **unseeded** originals (66.8 / 71.4 / 74.9 / 77.5 / 85.1) are retained in
`walkforward_runs` marked `superseded_by` + `unseeded: true` rather than
deleted — the drift between them and the seeded run is the measurement that
established finding 32.

**Consequence, stated plainly: every promotion decision that cited this table
cited a number an order of magnitude wrong.** The table said 1% risk-of-account
was a 5.6% ruin probability; the current engine says two thirds to five sixths.
The pre-parity rows above are retained as history — do NOT delete them, they are
what those decisions actually saw — but **nothing may size off them.**

This is one strategy on one symbol. The full sweep (16 configs across
$1000/$2000/$5000 accounts) has NOT been regenerated, and the local-only
`walkforward_runs` MC rows behind it are all `pre-parity-v0`.
---

<!-- moved from CLAUDE.md 2026-09-02 -->

### CANDLE_SOURCE flip: yfinance → ig_stream (2026-07-15)
Live signal-loop candle source flipped from yfinance to ig_stream in
.env (all symbols). Justified by candle_source_compare data (2,845
cycles, 2026-07-08→07-15):
- Indices (US500/US100, 15MIN+HOUR): yfinance genuinely stale
  off-session — median real lag 6.5–11.5h vs stream, HOUR timeframe
  0% timestamp agreement ever. Matches the mechanism behind a lost
  MINIMUM_ORDER_SIZE_ERROR incident (raw logs unrecoverable — container
  recreate wiped them before they could be pulled; see min-deal-size
  guard below, added independently of that incident's specific detail).
- FX (AUDUSD/EURUSD/GBPUSD, 15MIN): deltas real but small (median
  0.4–3.9 pips), disagreement direction ambiguous-to-opposite (stream
  sometimes the lagging side, median ≈ −900s in mismatches) — flipped
  anyway per explicit instruction (stream "strictly better"), holds
  the comparison-logger open one more week to confirm.

**Post-flip incidents caught same-day, all patched**:
1. Index buffers (US500/US100) appeared frozen 6+ hours while REST
   snapshot showed the market actively TRADEABLE and moving. ROOT CAUSE
   FOUND (2026-07-15, same day): IG's REST historical `snapshotTime` is
   in the account's configured timezone (confirmed via session
   `timezoneOffset`, = 8 for this account/MYT), NOT UTC —
   `_normalize_rest_time` was labeling it UTC without converting,
   producing candles stamped hours into the future. Live Lightstreamer
   ticks (`_update_hour_buffer`, `_feed_15min_aggregator`) were never
   affected — both already used proper epoch UTC math. HOUR buffers
   self-healed within minutes via live ticks overwriting the in-progress
   entry; 15MIN buffers only refresh once a full 3-bar aggregation
   completes (up to 15min), so the mislabeled REST value stayed visible
   far longer there — which is why HOUR looked fine and 15MIN didn't at
   the same moment, and plausibly why the original freeze read as
   "stuck in the past" rather than obviously wrong: REST-vs-live merge/
   sort interactions plus simultaneous IG quota exhaustion (forcing a
   yfinance fallback that was itself genuinely off-session-stale)
   compounded into what looked like one bug but was likely two
   overlapping ones. Fixed: capture `timezoneOffset` from the session
   response (initial warm-up + every reconnect), subtract it before
   labeling UTC. Verified via a new diagnostic-only endpoint
   (`GET /debug/candles/{symbol}/{timeframe}`, `bot/candle_stream.py`
   `debug_buffer_tail()`) — post-fix buffer dump for both US500 and
   US100, both timeframes, shows a fully contiguous, correctly-timestamped
   sequence up to the current moment. Lightstreamer subscription
   diagnosis (originally planned as the next step if the freeze
   persisted) was skipped — the freeze did not survive the timestamp fix.
2. Comparison logger (`_log_candle_comparison`) was only ever called
   from the yfinance-primary branch — flipping silently killed the
   exact dataset needed for post-flip verification. Now also called
   from the ig_stream branch (inverted: stream primary, yfinance
   reference), kept running for the one-week confirmation window.

**Mitigation deployed (defense in depth, kept even after the root-cause
fix)**: stream-staleness guard in `_check_symbol`
(`bot/live_signal_loop.py`) — if the stream's latest candle is older
than 3x the timeframe, or timestamped in the future (negative age,
hardened 2026-07-15 after the future-dated candle sailed through the
first version of this guard): FX falls back to yfinance for that fetch
(rate-limited Telegram WARN, once/6h/symbol); indices skip the check
entirely with no yfinance fallback (off-session yfinance staleness is
the exact failure this flip was meant to fix, so an untrusted-stale
source is worse than skipping).


---

<!-- moved from CLAUDE.md 2026-09-02 -->

### Post-flip Tier 1 maintenance (2026-07-16)

**Quota-fallback Telegram dedup (deployed)**: the "IG historical-data
quota exceeded — fell back to yfinance" WARN fired on every warm-up AND
every gap-backfill during an exhausted-quota window, several times/hour.
Now deduped to once/6h per condition-type (`warmup` vs `backfill`),
state file `/tmp/candle_stream_fallback_state.json` (same anti-spam
pattern as `scripts/watchdog.py`'s state file). Logs (`print`) stay
unconditional — only `send_telegram` gates on the cooldown, so analysis
still sees every occurrence. Verified live: a real quota exhaustion hit
5 pairs in one warm-up pass, all 5 logged, only 1 Telegram alert fired.

**yfinance-fallback timezone bug (found + fixed)** — third occurrence of
this bug class (Phase 2B positions_poller timezone fix → 2026-07-15 REST
`snapshotTime` account-local/MYT+8 fix → this one). Recurring pattern:
**any timestamp handed to us by an external data source may be
localized, not UTC, regardless of what it looks like or what the field
name implies — force-convert, never assume.** This time: `_normalize_yf_time`
only stamped `tzinfo=utc` when the source was naive, so it silently kept
yfinance's real offset when tz-aware — yfinance intraday data returns
exchange-local time (Europe/London, BST=+01:00 in summer), not UTC as
the old docstring assumed. Found live via mixed +00:00/+01:00 timestamps
in the GBPUSD buffer after a quota fallback (seasonal bug — invisible
in GMT months, live now in BST). Fixed: `_normalize_yf_time` now
converts tz-aware timestamps via `astimezone(timezone.utc)` instead of
relabeling, and rejects (drops, logs) any candle landing in the future
after conversion — same future-dated guard as the REST fix. Verified
post-deploy: GBPUSD buffer after a live fallback event showed uniform
`+00:00` offsets, correctly ordered, zero rejections needed.

**Drift investigation conclusion — NOT a regression, migration is
sound.** SL DRIFT reanchor adjustments looked ~2-3x larger post-flip
than the pre-flip baseline (GBPUSD mean 1.71→3.92 pips, EURUSD
1.16→3.35 pips), which read as the migration having made things worse.
Investigated per-event (11 post-flip reanchors, full log context) and
found two structural, pre-existing causes, not a stream bug:
  (a) **Decision-to-execution lag, 25-55min** — `candles[-2]` dedup +
      per-symbol `_is_due()` cadence means the candle price used for
      SL/TP math can be 25-55min stale by the time the trade actually
      executes. Confirmed on all 11 events (e.g. the GBPUSD 12.1-pip
      outlier: ~40min gap, ordinary London/NY-session movement, not a
      bad tick). This mechanism is unchanged by the candle-source flip.
  (b) **Mid-vs-dealing-price comparison artifact** — the stream candle
      close is `(BID_CLOSE+OFR_CLOSE)/2` (mid, `_mid_ohlc` in
      `bot/candle_stream.py`), but live execution fills at
      `offer`/`bid` (dealing price, `execute_trade.py`). Every reanchor
      comparison injects ~half-spread of phantom "drift" that isn't
      real slippage — matches EURUSD's numbers almost exactly
      (`NORMAL_SPREADS` 0.0008 → half-spread 4 pips ≈ observed mean
      3.35). Sign of the drift correlated with trade direction in 8/11
      events (spread-driven, as expected); the other 3 were real
      market movement over the lag window big enough to flip the sign
      — ordinary noise, not a bug. Does NOT explain index drift (US500
      half-spread is only 0.3pt vs 6.18pt observed mean) — that's (a).

**One item left OPEN, one DEPLOYED:**
- **Change 1 (SL DRIFT alert threshold, 3 pips FX / 1.5pt index) —
  DEPLOYED 2026-07-22.** Un-held: the drift investigation above concluded
  the post-flip increase was the mid-vs-dealing measurement artifact, not
  a regression — the reason to keep watching at 0.5-pip resolution had
  passed. Un-holding forced by a live incident the same day: 0.5-pip
  yellow-alert spam buried a real daily-loss-limit red alert for 8 hours.
  `_ALERT_THRESHOLD` in `bot/execute_trade.py`; console `[SL DRIFT]` log
  stays unconditional (still full-resolution for diagnostics), only the
  Telegram send gates on the new threshold. Floor-breach branch (webhook
  path) left unconditional — not the noise source, out of scope.
- **Mid-vs-dealing-price comparison fix — still DEFERRED.** Cosmetic/
  measurement-accuracy issue, not urgent (doesn't affect real SL/TP
  math or execution, only the drift-metric's apparent size). Batch
  with the next reanchor-logic review rather than a one-off patch.


---

<!-- moved from CLAUDE.md 2026-09-02 -->

### Three production bugs found + fixed (2026-07-20)

Diagnosed via read-only VPS audit (webhook_log/trades cross-check + real
IG transaction history), then fixed same day. All three deployed and
verified live.

**Bug 1 — webhook "EXECUTED" ghost log rows.** `webhook/receiver.py` wrote
`result="EXECUTED"` to `webhook_log` unconditionally whenever
`place_trade_from_alert()` returned without raising — but that function
returns `False` on many non-exception branches (cooldown, missing SL/TP,
counter-trend filter, IG `REJECTED`, sizing failure) that never place a
real order. Found 5 EXECUTED rows (4 EURUSD swiftalgo + 1 US500,
2026-07-15→17) with no matching `trades` row; confirmed against real IG
transaction history that no position was ever opened for any of them —
false logging, not an untracked ghost position. Fixed: EXECUTED now
gated strictly on `isinstance(result, dict) and result.get("status") ==
"OPEN"`; everything else logs `REJECTED`. Also fixed a dead
`deal_reference` column — the old code read `result.get("deal_reference")`
but IG/execute_trade.py use camelCase `dealReference`, so the column was
always `NULL` even on genuine fills (this also weakens Bug 3's primary
match, see below).

**Bug 2 — USDCAD 15MIN williams_r never traded.** Active in
`active_strategy` since 2026-07-13, but `bot/candle_stream.py`'s
`EPIC_MAP`/`SYMBOLS` (a second, independently-hardcoded copy of the
symbol list, despite a comment claiming it "mirrors
`live_signal_loop.SYMBOLS`") never got USDCAD added. Its `(USDCAD,
15MIN)` candle buffer was therefore never created — not stale, never
populated — producing "ig_stream buffer not warm yet" on every single
signal_loop cycle for 7 straight days. `scripts/run_backtest.py`'s
`YF_SYMBOLS` was missing USDCAD too (would have broken the FX
yfinance-fallback path as well). Fixed: added USDCAD to both maps, and
— to kill the class of bug, not just this instance — replaced both
`candle_stream.py`'s and `live_signal_loop.py`'s independent `SYMBOLS`
lists with a single shared import (`symbols.py`, project root). A direct
import between the two modules would be circular (`live_signal_loop`
already imports `candle_stream`), so `symbols.py` has zero imports/side
effects and both depend on it safely.

**Bug 3 — `positions_poller.py` cross-symbol close_price/pnl
contamination.** `_fetch_close_data()`'s fallback matcher (used whenever
the primary `deal_reference` lookup misses — which the dead
`deal_reference` column above made more likely to happen) searched IG's
*entire* multi-instrument transaction history for any row within 60s of
the trade's own entry_time, with **no symbol filter**. `live_signal_loop`
routinely opens EURUSD/GBPUSD/AUDUSD within single-digit seconds of each
other, so the fallback could — and did — return a sibling trade's
transaction row: right symbol's scale divisor applied to the *wrong*
symbol's `closeLevel`. Confirmed 3 instances this way (ids 583/596/604,
2026-07-16→17).

**Correction to this file's own earlier assumption:** the original
finding assumed `pnl` was unaffected ("corruption confined to the
close_price column"). That was wrong. `_fetch_close_data()` returns
`close_price` **and** `realised_pnl` from the same matched row, so a
wrong-symbol match contaminates both identically — confirmed by
diffing against the sibling trade's own stored pnl (exact matches, not
coincidental). It only read as "sane" because every trade here risks
~$10 with similar R:R, so a swapped pnl still landed in a plausible
dollar range for a win or a loss. Fixed: the fallback now requires the
candidate row's `instrumentName` (mapped via a confirmed
IG-instrument-name → symbol table, verified live via
`fetch_market_by_epic` per symbol) to match the trade's own symbol
before accepting it; no same-symbol candidate → returns `None`, leaving
the trade for the next poll rather than borrowing.

**Ledger re-audit** (`scripts/reaudit_close_prices.py`, dry-run by
default, `--confirm` to apply): cross-checked every CLOSED trade since
the 2026-07-08 demo switch against real IG transaction history. Found
**8** contaminated rows (ids 548, 566, 568, 581, 583, 596, 604, 619) —
deeper than the 3 originally spotted by the read-only audit that
triggered this investigation. DB backed up before correction —
**moved 2026-08-16 to `/home/ubuntu/backups/trades.bak-20260720T012352Z.db`
on the VPS** (was `database/trades.bak-…`; relocated out of the repo tree
so `COPY . .` stops baking it into every image, see Database Backups).
It is the **sole surviving pre-correction ledger state** — 565 trades,
179,413 backtest_results, `integrity_check ok`, sha256 verified across the
move. Do not delete it. Full before/after values for the 8 corrected rows
logged to `logs/ledger_reaudit_20260720T012352Z.jsonl`. One trade
(id=500, GBPUSD) has no matching IG transaction in history at all and
was left uncorrected — flagged, not explained. Re-run the script
periodically or after any future poller/ig_scale change; it's
read-only against IG and idempotent (dry-run reports zero once clean).


---

<!-- moved from CLAUDE.md 2026-09-02 -->

### Correlation cluster logging + per-instance daily loss limit (2026-07-22)

**Trigger incident:** all 3 williams_r USD-pair instances (GBPUSD, EURUSD,
AUDUSD) went SELL together same day and all lost — the multi-symbol
correlated-exposure scenario Tier 4's "Correlation/exposure limits" roadmap
item existed to anticipate, now observed live rather than hypothetical.

**Daily loss limit fix (see also Daily Loss Limits above):** was one
$75 pool summed across every symbol+strategy — the correlated williams_r
loss blew the combined limit and would have also halted unrelated,
uncorrelated instances (US500 stoch_rsi, EURUSD swiftalgo) for the rest
of the day, despite them having nothing to do with the loss. Now keyed
per (symbol, strategy_name): confirmed via simulated GBPUSD-breach test
that AUDUSD (same strategy_name, different symbol) is unaffected.

**Correlation cluster logging — report-only, added same day:**
`bot/live_signal_loop.py::_check_correlation_cluster()`, runs once per
signal_loop cycle (not per-symbol — needs the full open-position picture).
Flags 3+ OPEN williams_r positions, same direction, across
{EURUSD, GBPUSD, AUDUSD, USDCAD} — logs to new `correlation_events` table
(`database/models.py::log_correlation_event`/`get_correlation_events`) and
sends an INFO Telegram alert. NOT a trading gate — purely measuring
frequency before deciding whether to build blocking logic (Tier 4
prerequisite). Triggers on distinct-pair count, not raw open-position
count — found live on the very first post-deploy cycle that williams_r can
hold 2 concurrent positions on the same symbol (re-entry across signal
cycles isn't deduped), which would otherwise inflate the cluster size
without adding real cross-pair diversification risk.

Direction is the raw per-symbol BUY/SELL signal, not USD-exposure
normalized — USDCAD is USD-as-base while the other three are
USD-as-quote, so a USDCAD SELL is not the same underlying bet as a
EURUSD/GBPUSD/AUDUSD SELL. Fine for report-only counting; **any future
blocking logic built on this table must normalize to net USD exposure
direction first**, per explicit instruction when this was built.


---

<!-- moved from CLAUDE.md 2026-09-02 -->

### New Paper Strategies (added 2026-05-20)
| Symbol | TF   | Strategy   | Rationale                              |
|--------|------|------------|----------------------------------------|
| US500  | HOUR | williams_r | Mean reversion, uncorrelated to stoch_rsi |
| DAX    | HOUR | williams_r | Mean reversion forward test            |
| DAX    | HOUR | macd_rsi   | Trend-momentum with EMA50 confirmation |

williams_r entry rules:
- Long: %R(14) crosses below -85 (enters oversold)
- Short: %R(14) crosses above -15 (enters overbought)
- Exit: SL/TP from backtesting engine (ATR-based)

macd_rsi entry rules:
- Long: MACD(12,26,9) line crosses above signal AND RSI(14)<60 AND close>EMA(50)
- Short: MACD line crosses below signal AND RSI(14)>40 AND close<EMA(50)
- Exit: SL/TP from backtesting engine (ATR-based)

Baseline backtest (default params, 5000 HOUR candles, test window 1000):
- US500 HOUR williams_r: 47 trades, 74.5% win rate, $857 profit
- DAX   HOUR williams_r: 47 trades, 59.6% win rate, $419 profit
- DAX   HOUR macd_rsi:   10 trades, 10.0% win rate, -$865 loss
  ⚠️  macd_rsi DAX baseline weak — paper trading to observe live behaviour


---

<!-- moved from CLAUDE.md 2026-09-02 -->

### London Breakout (added 2026-06-04)
| Symbol | TF    | Strategy        | Source | Rationale                     |
|--------|-------|-----------------|--------|-------------------------------|
| EURUSD | 15MIN | london_breakout | loop   | London session range breakout |

Params: min_range_pips=8, breakout_buffer=0.3, tp_multiplier=2.0, use_ema_filter=false
Range window: 06:00-07:00 UTC
Entry window: 07:00-09:00 UTC
SL: range low - buffer (BUY) / range high + buffer (SELL) — range-based, not ATR
TP: entry ± (range_size × 2.0)
Max one trade per day
Backtest note: inconclusive — yfinance 15MIN limited to 60 days, test window only
8-10 trades. Best sweep params: min_pips=8, buffer=0.3, tp=2.0, ema=false.
Review after 30 resolved paper trades.


---

<!-- moved from CLAUDE.md 2026-09-02 -->

### stoch_rsi_confluence (added 2026-06-12)
| Symbol | TF   | Strategy             | Source | Rationale                          |
|--------|------|----------------------|--------|-------------------------------------|
| US500  | HOUR | stoch_rsi_confluence | loop   | stoch_rsi + session/ATR confluence  |

Base: stoch_rsi US500 HOUR (same signal generation as live stoch_rsi)
ATR filter disabled — hurts in backtest.
Session filter only. Shadow logging active.
Filters: session (London 07:00-08:59 UTC + NY 13:00-15:59 UTC)
Blocked signals logged as SHADOW_BUY/SHADOW_SELL with
notes="SHADOW: filtered by session" for A/B comparison.
Review after 30 paper trades + 30 shadow trades.
Promote if confluence WR > shadow WR by 10%+


---

<!-- moved from CLAUDE.md 2026-09-02 -->

### ny_session_momentum + ema_pullback (added 2026-06-12)
| Symbol | TF    | Strategy             | Source | Rationale                          |
|--------|-------|----------------------|--------|-------------------------------------|
| EURUSD | 15MIN | ny_session_momentum  | loop   | NY-open range breakout, follow mode |
| US500  | 15MIN | ema_pullback         | loop   | EMA8/EMA50 trend pullback           |
| US100  | 15MIN | ema_pullback         | loop   | EMA13/EMA50 trend pullback          |

ny_session_momentum EURUSD params: range_minutes=60, min_range_pips=3,
breakout_buffer=0.0, tp_multiplier=1.0, fade_mode=false, range_start=13, entry_window=3
Backtest: 37 trades, 75.7% WR, PF 1.64, ~15 trades/month.
Note: fade_mode=True won on US500 (double-break fade), fade_mode=False won on EURUSD —
direction edge is instrument-dependent.

ema_pullback US500 params: ema_fast=8, ema_slow=50, min_move_atr=1.0,
sl_atr_mult=1.5, tp_atr_mult=3.0, session 07:00-17:00 UTC
Backtest: 44 trades, 45.5% WR, PF 1.57, ~15 trades/month.

ema_pullback US100 params: ema_fast=13, ema_slow=50, min_move_atr=1.5,
sl_atr_mult=1.0, tp_atr_mult=3.0, session 07:00-17:00 UTC
US100 15MIN ema_pullback validation:
  86% of 72 param combos profitable (PF > 1.0)
  22 combos with PF > 1.5
  Consistent params: fast=13, slow=50, tp_mult=3.0
  Strong concept edge confirmed across params
Backtest: 16 trades, 56.2% WR, PF 3.17 — low sample, watch closely.

Review all 3 after 30 resolved paper trades.


---

<!-- moved from CLAUDE.md 2026-09-02 -->

### FVG Strategy (added 2026-05-29)
| Symbol | TF    | Strategy | Rationale                                         |
|--------|-------|----------|---------------------------------------------------|
| US500  | 15MIN | fvg      | SMC Fair Value Gap POC, London/NY sessions only   |

fvg params: atr_period=10, min_gap_atr=0.5, expiry_candles=15
Entry: close retraces into 3-candle gap zone (confirmation close)
Session filter: London 07:00-09:59 UTC, NY 13:00-15:59 UTC
FVG expiry: 15 candles without retracement
Min gap size: 0.5x ATR10


---

<!-- moved from CLAUDE.md 2026-09-02 -->

### 🔴 The live path pays TWICE per restart — gap-backfill duplicates warm-up

*(measured 2026-08-25 on the first restart with the meter live. **Finding 37.
Scoped there, deliberately NOT fixed** — kept separate from the post-reset
measurement work.)*

A restart costs **2,800 points, 28% of the weekly allowance** — not the ~1,400
this file predicted. Fourteen REST calls, not seven: warm-up fetches 200 per
pair, then gap-backfill immediately re-fetches 200 per pair and leaves the
buffer at the same 200 candles (`gap backfill AUDUSD/15MIN: buffer now 200`).
**Zero candles gained, 1,400 points spent, every reconnect.**

**Arguably worse than the collector it sits next to.** The collector wasted
~98% on a schedule that could be — and was — commented out. This wastes **100%**
on the **live path**, fires on **every stream reconnect** rather than a cron
line, and cannot be disabled without touching the candle path. At 2,800 points
per restart the weekly allowance funds **three**.

Fix options are scoped in finding 37 (prefer: skip the backfill when warm-up
just ran, *and* size backfills to the measured gap rather than `WARMUP_COUNT`).

**CHANGE 1 SHIPPED 2026-09-02 — the SKIP half only.** `_backfill_gap` now calls
`_bars_missing()` and returns without issuing a REST request when the buffer is
already current (`missing <= 1`) or future-dated (`missing < 0`). Unknown
(`None` — empty buffer, unmapped timeframe, unparseable timestamp) still
fetches: a redundant backfill costs points, a wrongly-skipped one leaves the
signal loop on stale candles.

**Sizing a real backfill to the measured gap is NOT in change 1** — that needs
the minimum accepted `numpoints`, still unmeasured. Skipping needs no such
measurement because it issues no request at all, which is why the halves
shipped separately.

**⚠️ The verification predicate as originally written was WRONG — it asserted a
fixed count.** "Seven lines, `remaining=8600`" bakes in an assumption about how
many pairs fetch, and a restart where one pair legitimately needs a backfill
would read as a failure. Enumerate per pair instead:

1. **one `[ig_allowance]` line per pair that actually reached IG** — name them,
   do not count them;
2. **a skip line naming its reason for every pair that did NOT fetch** —
   `skipped, no REST request — buffer current ...`. A pair that is silent in
   both lists is the interesting case: it means neither branch ran.
3. **remaining delta == 200 x (number of pairs that fetched)**, computed from
   the enumeration in (1), *not* compared against a constant.

Expected on a clean restart: ~**1,400** for warm-up, ~**0** for backfill,
against 2,800 before.

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

**⏸️ HOLD — the finding-38 probe is deliberately NOT run.** Observe the
post-change daily burn first. Pre-change it was ~4,210 per 18 hours with no
restart; if change 1 works that should fall sharply, and the size of the drop
is what says how much of the ~2,790 spare is genuinely free rather than
reserved against reconnects. Budget the probe against the observed rate, not
against the headline remaining.


---

<!-- moved from CLAUDE.md 2026-09-02 -->

### ⛔ STATE AS OF 2026-08-25 — allowance EXHAUSTED, resets 2026-09-01T04:02 UTC (SUPERSEDED)

| | |
|---|---|
| reset time | **2026-09-01T04:02:18+00:00** — read from `resets_at`, first time ever known |
| window shape | **rolling 7 days from the first request after a reset** (`expiry=604799s`), not a fixed weekly boundary — it MOVES, re-read it |
| spent on the deploy warm-up | **2,800** of 10,000 (28%) — see finding 37, half of it wasted |
| spent on the unknowns probe | the remaining **~7,200** — see finding 38, and it measured nothing |
| remaining | **0** |


---
