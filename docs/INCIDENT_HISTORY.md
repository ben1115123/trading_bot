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

<!-- moved from CLAUDE.md 2026-09-04 — the eleven worked instances behind the Unverified Controls rules — dated narratives; the rules themselves stay in CLAUDE.md -->

### The self-invalidating probe — a rule with a checkable step

**Two instances, both of which reported a clean negative about something that
was in fact working:**

1. **Sampled after its own teardown (2026-08-12).** A background check read a
   sentinel file 32 seconds *after* the cleanup step had deleted it, and
   reported `MARKER_ABSENT` for an event that had demonstrably occurred. The
   probe was measuring its own teardown.
2. **Ran in a process that could not hold the answer (2026-08-21).**
   `docker exec … python3 -c "from bot.candle_stream import get_spread; ..."`
   returned `None` for every symbol, which was read as "the stream is not warm
   after the rebuild". It was warm. `get_spread` reads a **module-level buffer
   populated by the Lightstreamer thread inside the long-running uvicorn
   process**; a one-shot `exec` starts a *fresh* interpreter whose buffer is
   empty by construction and can never be anything else. The probe could not
   have returned a non-`None` value no matter how healthy the system was.

**THE RULE — do this before trusting any probe result:**

> **State what the probe would show if the thing under test were WORKING, then
> confirm the probe is able to observe that state at all.**

If you cannot describe the passing observation, or the probe cannot reach it,
the result carries no information — a negative from such a probe is
indistinguishable from a broken system, and will usually be read as one.

Two failure modes to check for by name, because both have now happened here:

- **Wrong time.** The probe runs after the artifact is gone (instance 1), or
  before it is created. Read every probe result against the timestamps of the
  setup and cleanup around it.
- **Wrong process / wrong address space.** The probe looks somewhere the state
  provably does not live (instance 2). In-memory state — module globals, warm
  buffers, caches, thread-owned data — belongs to **one process**. A separate
  `exec`, a fresh interpreter, a different container, or a cron job cannot see
  it. Reach it through something that crosses the boundary: the DB, a log line,
  an HTTP endpoint the live process serves, or an artifact it writes.

Worked example of the fix, same session: the stream question was settled not by
re-running the `exec`, but by POSTing a webhook with **no** `spread` key and
watching the *live uvicorn process* log
`SHADOW spread gate: ratio 1.200 ... (spread=1.2)`. That observation is only
producible by a warm buffer, and it was made inside the process that owns one.

This rule is the mirror of the marker test below. The marker test says *do not
infer success from absence*; this one says *do not infer failure from absence
either*, until you have shown the probe could have seen success.

### The rule applied PROSPECTIVELY — do not rebuild before a dated control check

The self-invalidating-probe rule above is written as a way to read a result
after the fact. It has a forward-looking form, and it earned its place on
2026-08-22:

> **Do not restart, rebuild or redeploy in the window before a dated control
> check. A restart can manufacture exactly the artifact the check is looking
> for.**

**The proof is CHECK 1.** `signal_log.spread` was NULL on all six symbols all
Saturday — correct, the book was shut and there was nothing to sample. Then the
2026-08-22 18:07 UTC rebuild re-warmed the Lightstreamer buffer from a **closed
book**, and the very next cycle logged `spread` non-null on AUDUSD (0.00053) and
USDCAD (0.00061). Anyone reading that column afterwards, without knowing a
rebuild had happened minutes earlier, would have recorded criterion 4 as PASSED
on numbers no one could have traded on. (It aged back out to NULL within the
hour, which is its own tell.)

This is the mirror of the marker test and of the retrospective rule:

| rule | says |
|---|---|
| marker test | do not infer success from absence |
| self-invalidating probe | do not infer failure from absence either, until the probe could have seen success |
| **this one** | **do not create the passing observation yourself** |
| enumerate over assert | do not let the check see only what it already predicted |

Concretely: a deploy is cheap to postpone and a dated check is not repeatable —
CHECK 2's first genuine fire is a specific hour on a specific Monday. **The
deploy waits.** Applied 2026-08-23: `40d716b` was held rather than shipped,
with the reasoning recorded at the time rather than reconstructed after.

### The remedy — the marker test
When disabling something, prove the disable took effect with a **positive
signal**. Never infer it from absence of activity: absence is consistent with
both "disabled" and "would have fired but didn't happen to." Construct a probe
whose observation *differs* between the two states — a temporary artifact only
the new configuration can produce — observe it, then remove it.

Applied 2026-08-12: a one-shot cron line writing a timestamped sentinel,
scheduled 5 minutes out, `%` escaped as `\%` (an unescaped `%` is a newline
separator in crontab), with ≥2 minutes of lead for cron's per-minute mtime
poll. It fired at 17:11:01 — **that**, not the silence of the disabled job,
established the disable.

Applied again 2026-08-15 to verify this deploy: `/app/logs/daily_run.log`
stayed absent at 06:00 UTC while Stage E **wrote** `webhook_outcomes.log` at
06:10. Cron was demonstrably alive and reading that exact file in the same
window, so the 06:00 no-show is a real disable rather than a dead daemon.

**Corollary 1:** a test whose positive and negative branches produce the same
observation proves nothing. The first probe proposed on 2026-08-12 — watch the
`*/15` collector fire — was discarded because that line is identical in the old
and new crontabs, so it fires either way.

**Corollary 2:** a probe must be invalidated when its artifact is cleaned up,
or its result read against the cleanup timestamp.

**Corollary 3 (2026-08-15):** an SSH transport failure is not a command
result. The rebuild's wrapper exited 255 (`client_loop: send disconnect:
Broken pipe`) having shown zero build output; the build had in fact succeeded.
The conclusion rested on end-state evidence — new image ID, new `StartedAt`,
flipped crontab md5, cron executing — **not** on the exit code or the log.

### 🔴 WHAT AN OBSERVATION COSTS — a request that FAILS is not a request that was FREE

*(added 2026-08-25, from finding 38. This one was learned by destroying the
thing being measured.)*

The four rules around it all ask whether an observation carries **information**.
This one asks what taking it **spends** — the axis none of the others cover.

**The instance.** The IG historical allowance had just reset, and the two open
unknowns (max `numpoints`, `MINUTE_15` depth per epic) were to be measured
promptly. The probe was built on this reasoning:

> Every value I try is larger than the budget I have left, so a success is
> impossible. IG must answer either "numpoints too large" or "allowance
> exceeded". Both are failures, so neither costs anything.

**Sound except the last clause, which was never checked.** `numpoints=100000`
and `50000` returned `error.price-history.io-error` — **not** a quota error —
meaning IG attempted and charged them. By the third request a **four-bar**
window was refused. ~7,200 points gone, **both unknowns still unmeasured**, and
the allowance dead for a week.

**The misread, named exactly.** This file says *"the reset time is only
learnable from a request that SUCCEEDS. A 403 carries no allowance block."*
That is about what a 403 can **teach** you. It says nothing about what a failed
request **costs**. The inference was an addition to the line, not a reading of
it.

| rule | governs |
|---|---|
| marker test | do not infer success from absence |
| self-invalidating probe | do not infer failure from absence either |
| prospective form | do not create the passing observation yourself |
| enumerate over assert | do not let the check see only what it predicted |
| **this one** | **do not assume what the observation COSTS** |

> **THE RULE:** before probing a metered resource, state what the probe costs
> **if it fails**, and say how you know. If that answer is an inference rather
> than a measurement, start from the smallest informative request and read the
> meter off the first response before escalating.

**The correct shape, which was available the whole time:** smallest request
first (a one-hour date-range window is four bars) → read
`allowance.remainingAllowance` off that response → the delta **is** the cost,
measured → escalate only while the measured cost stays affordable. Bracketing
from above had no way to learn its own cost until after it had paid it.

A probe that exhausts the resource it was measuring has destroyed the
measurement — the same end state as a probe that could never have observed the
passing state, reached by a different route.

### 🔴 A TEST WHOSE BRANCHES CANNOT SEPARATE THE HYPOTHESES — corrected 2026-09-02

*(This one is a correction to a PLAN, recorded as such. The plan was agreed in
advance, in writing, with a decision table — and it still could not have worked.
That is what makes it worth a section: it did not look like a guess.)*

**The plan.** Read the IG allowance after the 2026-09-01 reset, and decide
finding 38's open question from the number:

> if `remaining` comes back at or near 10,000, refusals are not charged and the
> 102,200-point storm cost nothing. If it comes back low, they are.

**The read:** `remaining=5790`, `total=10000`,
`resets_at=2026-09-08T07:18:53Z`.

**Neither branch was diagnostic, and neither ever could have been.** The
allowance is a **rolling 7-day window anchored to the first request after a
reset** — `expiry=539812s` puts this window's start at ~**2026-09-01T07:18Z**,
not at the 04:02 the plan assumed. Both events the test was reasoning about —
the 2026-08-25 probe and the 2026-08-28 disconnect storm — sit in the
**previous, expired window**. Their charges cannot appear on this meter whether
refusals are billed or not. A high reading and a low reading are equally
consistent with both hypotheses.

**The error is specific and is NOT "the number surprised me".** It is that the
test reasoned about which accounting window *should* apply, instead of reading
`resets_at` **first** and deriving the window from it. `resets_at` was
available before the decision rule was written — it had been read on
2026-08-25 and is in this file. The window shape ("it MOVES, re-read it") is
recorded here too. The plan used the remembered 04:02 anchor rather than the
recorded rule about that anchor.

> **THE RULE:** before running a test that decides something, state what EACH
> branch would mean, then check that the branches are distinguishable **given
> the system's actual bookkeeping**. If two branches are consistent with the
> same hypotheses, the test is decorative regardless of how carefully its
> threshold was chosen.

Where it sits in the family — all five before it ask about a single
observation; this one asks about the **decision rule** built on top of one:

| rule | asks |
|---|---|
| marker test | do not infer success from absence |
| self-invalidating probe | could the probe observe the passing state? |
| prospective form | did I create the passing observation myself? |
| enumerate over assert | can the check see anything it did not predict? |
| observation cost | what does the observation COST if it fails? |
| **this one** | **can the branches TELL THE HYPOTHESES APART at all?** |

**Finding 38 stays OPEN.** It is answerable only within a single window: read
the meter, issue one request known to be refused, read the meter again. Zero
delta = refusals free; non-zero = charged. Deferred deliberately — see the
post-change-1 burn-rate hold below.

### 🔴 SECOND INSTANCE, SAME DAY — and the rule did NOT prevent it

*(2026-09-02, hours after the rule above was written into this file.)*

**The check.** A sole-copy audit, to establish which CLAUDE.md content existed
nowhere else before the split. Shape:

```
grep -rlF "<string>" --include='*.md' --include='*.py' . | grep -v CLAUDE.md
```

Empty output was read as **"sole copy"**.

**Empty output has TWO causes.** The string is in CLAUDE.md and nowhere else —
or **the string does not exist anywhere, because it was typed wrong.** Both
print nothing. Same defect as the allowance test: two branches, one
observation.

**It fired.** 2 of 23 verdicts were mis-transcribed strings, not sole copies —
`cannot separate the hypotheses` against a heading reading `CANNOT SEPARATE THE
HYPOTHESES`, and `export_roster.py must run…` against text carrying backticks.
Both sections existed and were intact. Caught only because the post-split
re-probe reported them as LOST, which forced a look; had the split actually
dropped them, the same two lines would have appeared and the *first* probe's
false verdicts would have been the reason nobody noticed.

**The fix is one extra branch:** assert **presence anywhere** before asserting
**exclusivity**. The corrected probe prints the hit list, and separately checks
each string against the pre-split file, so "absent" and "exclusive" can never
share an output. 23/23 resolved, 0 absent from the baseline.

> **THE PART WORTH KEEPING.** The rule against non-separating tests was written
> into this file **that morning**, and it did not stop the same error being
> built into a check **that afternoon** — by the same author, in a check whose
> whole purpose was rigour. **Knowing a rule does not apply it.** A rule about
> reasoning only fires if something forces the question at the moment the check
> is written.
>
> So it gets a mechanical form, not just a statement: **for any check whose
> conclusion rests on an EMPTY result, write down the other ways that result
> could be empty — before running it.** If the list has more than one entry,
> the check needs another branch. This is the marker test's "absence is not
> evidence" turned into a step you perform rather than a principle you hold.

Both instances share a tell worth recognising in the moment: the conclusion was
attached to the **absence** of something — no charge on the meter, no grep hit.
Absence is where this failure lives.

**What the read DID establish**, and it is worth more than the question it
failed to answer: **4,210 points spent in ~18 hours with no container restart**
— roughly 21 gap-backfills at 200 points each. That is finding 37 leaking in
**ordinary operation**, not under storm conditions. The 2026-08-28 number
(511 backfills) reads as exceptional and is easy to discount; this one is the
baseline burn and is not.

### 🔴 REPEATED-OBSERVATION DUPLICATION BIASES, IT DOES NOT MERELY INFLATE — 2026-09-04

**Surfaced twice now, under two different query paths, in two different tables
with two DIFFERENT mechanisms.** Do not assume one table's shape from another's
— measured, they disagree:

| table | duplication key | factor |
|---|---|---|
| `signal_log` | one row per **(symbol, timeframe, strategy_name)** check | EURUSD **4.2×**, GBPUSD 1.86×, AUDUSD/USDCAD **1.0×** |
| `candle_source_compare` | **1.0×** per `checked_at` minute — but **1.29–1.35×** per `stream_time`, because the 5-minute loop re-observes the same completed 15-minute bar across cycles | 1.30× average |

`get_spread_samples()` dedups the first internally — **but that protects that
accessor only.** Any analysis querying either table directly re-suffers it, and
the second mechanism has no accessor guarding it at all.

> **THE PART THAT MATTERS: the multiplier CORRELATES WITH THE QUANTITY BEING
> MEASURED.** A constant inflation is harmless to a mean — it cancels. This one
> does not. On `candle_source_compare` the average factor is 1.30×, but on the
> **divergent** bars it was **~13×** (213 rows over 16 distinct timestamps),
> because a stalled stream buffer gets re-read every cycle while it is stale.
> **The anomalies are duplicated ten times more than the ordinary bars.**

Consequences seen, both real:
1. The tail rate was reported as **5–7%** of bars; deduplicated it is
   **0.4–0.8%** — off by an order of magnitude, in the alarming direction.
2. Dukascopy's stdev was reported **worse than Twelve Data's on all four
   symbols**; deduplicated it is **better on all four**. The duplication was
   loading exactly the bars where Dukascopy and IG disagreed.

**Both errors pointed the same way — against the new source — because the
duplicated bars were the divergent ones.** A reviewer sanity-checking the
direction of the bias would have found it plausible.

> **THE RULE: before computing any statistic from `signal_log` or
> `candle_source_compare`, dedup to one observation per (symbol, bar) and state
> which key you used.** `checked_at` and `stream_time` are different keys and
> give different answers on the same table. If a figure was computed from rows,
> label it as row-based — it is not wrong, it answers a different question, and
> the two must never be compared to each other.

### 🔴 THE SESSION'S DATE BANNER IS NOT A CLOCK — 2026-09-03

*(Third member of the "conclusion resting on an absence" family, and the
cheapest to fall for, because the wrong number arrives unasked.)*

**What happened.** The session context asserted the date was 2026-09-04. The
spread pool's newest sample was `2026-09-03T18:00`. Against the banner that
reads as **~19 hours of weekday silence** — a dead signal loop on a live FX
day. An incident investigation was opened on that basis.

**There was no incident.** VPS and local WSL both read
`2026-09-03T18:13:30Z`; the VPS is NTP-synced with NTP active. The data was
**13 minutes old**. The banner was the only wrong clock in the room.

> **THE RULE:** freshness is a comparison between two times, and BOTH have to
> come from real clocks. Never date-check data against the session's own idea
> of the date — read the clock on the machine that owns the data, in the same
> command if possible.

Why it belongs beside the others: the conclusion rested on an **absence** (no
recent rows), and the absence was manufactured by the measuring instrument
rather than by the system — the same shape as a probe sampling after its own
teardown. It is also a live instance of the mechanical form recorded below:
*for any check whose conclusion rests on an empty result, write down the other
ways that result could be empty.* "My clock is wrong" was on that list and was
not consulted.

**This one has a cheap standing fix**, which is why it is worth a section:
`ssh … 'date -u'` costs nothing and settles it outright. The 2026-09-03 check
took four extra tool calls because the question was asked of the codebase
first and the clock second.

### 🔴 DID THE ARTIFACT ACTUALLY LAND WHERE IT WOULD BE NEEDED? — 2026-09-04

*(Seventh member of the family, and the first that is not about an
observation at all. The six before it ask whether a reading carries
information, whether the probe could see it, whether we manufactured it, and
what it cost. **This one asks whether the THING an operation claims to have
produced actually EXISTS at the address that would consume it.**)*

**The instance.** `import_stage4.py`'s rule-5 backup ran, returned, printed
`integrity_check ok`, and reported a filename and a byte count. All true. The
file was on the **container's ephemeral writable layer**, because
`DEFAULT_BACKUP_DIR` is a HOST path while gotcha 3 forces the script to run
INSIDE the container. 650 MB across two runs, invisible from the host,
missing from the Database Backups table, and destroyed by the next rebuild.
**The rollback path did not exist and reported healthy.** Found only by
listing the host directory afterwards — nothing in the run said otherwise.

Note what makes it nasty: **two individually-correct rules produced it, and
neither owned their intersection.**

| rule | correct on its own |
|---|---|
| gotcha 2 — "backup on the host, import in the container" | yes |
| gotcha 3 — "the VPS DB is root-owned, so writes must be in the container" | yes |

> **THE RULE:** when an operation's value is a **fallback you would only use
> later** — a backup, a snapshot, an export, a log you plan to read after an
> incident — **verify the artifact from the side that would CONSUME it**, not
> from the writer's return value. The writer's success is evidence the write
> happened *somewhere*. It is not evidence the artifact is where the reader
> will look.
>
> A backup whose only evidence of success is that the call returned is not a
> backup. Check it from the host, in the directory the runbook names.

Where it sits — the family now covers the whole life of an observation and
then one step past it:

| rule | asks |
|---|---|
| marker test | do not infer success from absence |
| self-invalidating probe | could the probe observe the passing state? |
| prospective form | did I create the passing observation myself? |
| enumerate over assert | can the check see anything it did not predict? |
| observation cost | what does the observation COST if it fails? |
| non-separating branches | can the branches tell the hypotheses apart? |
| **this one** | **does the ARTIFACT exist where it will be needed?** |

**Fixed, and the guard has been SEEN to fire** rather than merely added:
`backup_target()` compares `st_dev` of the backup directory against the
target's directory — `/app/database` is the bind mount (`st_dev=2049`), the
container overlay is `st_dev=50` — and refuses. Demonstrated 2026-09-04 by
pointing it at the exact path that failed silently before.

### 🔴 CRITERIA AGE AGAINST THE SYSTEM THEY MEASURE — two unsatisfiable criteria now

*(named 2026-08-31, on the second instance. The first was not recognised as an
instance of anything at the time.)*

**Both instances are the same defect: a criterion written before a control
existed, then made IMPOSSIBLE TO SATISFY by that control — while still reading
as a perfectly sensible test.**

| # | criterion | written | made impossible by | how it presented |
|---|---|---|---|---|
| 1 | CHECK 1 criterion 4 — FX `signal_log.spread` non-null in the blocked weekend window | before the first real FX weekend | the venue being **shut** on a Saturday: no quote exists to sample, so `get_spread()` correctly returns `None` | "criterion 4 FAILED" — read as the load-bearing sampling order being broken. It was not. Re-scoped to the Sunday reopen, where the venue is open and *we* decline; **passed 111/111** |
| 2 | Spread-table gate criterion 1 — every UTC hour 00–23 represented after market-open filtering | 2026-08-17, alongside the market-open filter itself | the **21:00 rollover gate** (deployed 2026-08-21, four days later) setting `is_entry_allowed=False` for the whole hour, which is the exact predicate the filter uses | "hour 21 empty on all six symbols" — reads as thin data, i.e. *wait longer*. Waiting can never fix it. Re-scoped to permitted hours only |

**Note the direction of the failure in both cases: the criterion reported a
problem with the SYSTEM when the problem was with the CRITERION.** Instance 1
nearly indicted a working control. Instance 2 would have deferred the spread
table indefinitely on a condition that no amount of accumulation can meet —
and "wait another two weeks" is a conclusion nobody re-examines, because it
costs nothing and sounds careful.

> **THE RULE:** a criterion is a claim about the system, written at a moment in
> time. **When the system changes, RE-READ every dated criterion that touches
> what changed — do not wait for one to fail.** In particular, when a new
> control narrows what the system will do, any criterion demanding an
> observation from inside the newly-excluded region has just become
> unsatisfiable, and it will not announce that. It will look like a shortfall.

**The practical check, before treating any criterion as failed:** state what
would have to be true for it to PASS, then confirm the current system permits
that state at all. This is the self-invalidating-probe rule (*could the probe
observe success?*) applied one level up, to the **specification** rather than
the measurement. Same question, different target:

| rule | asks of the... |
|---|---|
| self-invalidating probe | **probe** — could it have observed the passing state? |
| **this one** | **criterion** — can the passing state still occur at all? |

Both instances were caught only because the check enumerated the distribution
instead of asserting an expected value — the hour histogram showed *which* hour
was empty, and that it was exactly one, identically on all six symbols. An
all-hours-present assertion returns `False` and names nothing. See ENUMERATE,
DON'T ASSERT below; this is its fourth catch.

### ENUMERATE, DON'T ASSERT — how to write a check that can teach you something

The three rules above govern *whether an observation carries information*. This
one governs *whether the observation can carry information you do not already
have*.

> **A check that tests for its own prediction can only confirm or deny that
> prediction. A check that enumerates what actually happened can CORRECT it.**

Concretely, given a `signal_log` window:

| shape | what it can return | what it can never return |
|---|---|---|
| `WHERE error = 'entry window closed — thin reopen / pre-weekend policy'` | matched / didn't match | *which other reason fired instead, and when* |
| `GROUP BY substr(checked_at,12,2), error` | the full distribution | — |

**Both pass. Only one of them found anything.**

**The instance that named this rule (2026-08-24).** CHECK 1's criterion 4 was
written to confirm one string in the Sunday reopen window. It was run as a
`GROUP BY hour, error` instead — and the hour-21 bucket came back carrying
`entry window closed — daily rollover hour`, not the predicted string. That
single unexpected bucket:

- proved the 21:00 rollover gate had **already fired on a real clock**, a day
  before CHECK 2 said it was reachable;
- falsified this file's table asserting the Sunday reopen rule shadows that
  gate at 21:30;
- and revealed *how* the claim was wrong — not misread from the code, but never
  checked against it, since `is_entry_allowed` and `_block_reason` both test
  the rollover **first** and both carry a comment saying so.

An assertion-shaped criterion 4 would have returned "111/111 FX rows non-null,
PASS" — **completely true, and it would have taught nothing.** The CHECK 2
error would have survived until Monday or later.

**This is the fourth time a scheduled check has produced a finding outside its
own criteria** (CHECK 1 Saturday: the criterion itself was mis-specified;
CHECK 1 Sunday: the CHECK 2 ordering error; finding 33's two verification
queries wrong in the manufacturing direction; and 2026-08-31's spread-gate
hour histogram, which showed hour 21 empty on **all six symbols identically** —
a shape that says "structural exclusion", not "thin data". An
all-hours-present assertion would have returned `False` and named nothing).
Treat that as the norm, not luck.

**Practical form — when writing any dated check:**
- prefer `GROUP BY` over `WHERE =`. Ask what the column contained, not whether
  it contained what you expect.
- **include the cases you believe are irrelevant.** The gate is all-symbols;
  enumerate US500/US100 alongside FX even when the evidence base is FX-specific.
  A difference between them is only visible if both are in the output.
- report the distribution **before** stating the verdict, so an unexpected
  bucket is seen rather than filtered out on the way to a PASS.
- a criterion that cannot fail in an *interesting* way is a criterion that
  cannot inform. If every non-passing outcome is "the thing is broken", the
  check has no route to "the thing is fine and our belief about it was wrong."

---

<!-- moved from CLAUDE.md 2026-09-04 — the price-scale quirk description as of 2026-07-08 — the layer is currently arithmetically inert -->

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

**The 2026-07-08 diagnosis, the epic-by-epic evidence and the boundary
conversion site list → `docs/INCIDENT_HISTORY.md`.**

**Standing rules that survive the layer being inert:**
- **Do NOT trust IG's `scalingFactor` snapshot field.** GBPUSD/AUDUSD carry
  `scalingFactor=10000` despite already being decimal; EURUSD — the one epic
  that needed /10000 — carried `scalingFactor=1`. Empirically disproven, not
  assumed.
- **Scale differs by ACCOUNT, not just by epic.** Re-run
  `init_price_scales(..., force=True)` after ANY session recreate or account
  switch. Never assume scale carries over.
- **Ambiguous readings never guess** — they raise, alert, and block that symbol
  from trading until a human resolves it.
- All IG price reads/writes route through `to_decimal()`/`to_native()` at the
  boundary; everything else in the codebase stays decimal.
- ⚠️ **The paper-trade path has NO `ig_scale` conversion at all.** That is the
  structural root of the id=824 corruption — see the bb_squeeze correction.

---

<!-- moved from CLAUDE.md 2026-09-04 — the USDCAD deal-currency incident write-up -->

### Deal currency quirk — ig_scale.get_currency_code() (fixed 2026-07-25)
Third per-instrument-assumption bug (after `scalingFactor` above and the
REST `snapshotTime` account-timezone bug, see CANDLE_SOURCE section) — IG
instrument properties are NOT uniform across epics; always derive per-epic,
never hardcode one value for "all FX pairs." `create_open_position` had
`currency_code="USD"` hardcoded for every symbol. USDCAD is the one FX pair
in the roster where USD is the base, not the quote — its instrument's
`currencies` list only contains `CAD`, no `USD` entry (confirmed via
`fetch_market_by_epic`; EURUSD/GBPUSD/AUDUSD all list `USD`). Sending
`currency_code="USD"` on that epic is an invalid param IG rejects with an
unclassified `reason: 'UNKNOWN'` (not a structured margin/size code) — this
was the root cause of every USDCAD live-trade rejection since its
2026-07-14 activation (10/10 rejections, 100% failure rate, zero USDCAD
trades ever placed).

Fix: `ig_scale.get_currency_code(symbol)` — deal currency cached per-epic
alongside the price-scale map, same lock, same lifecycle (`init_price_scales`
fetches both from the one `fetch_market_by_epic` call, re-init on session
recreate / account switch). Falls back to `'USD'` only if the lookup never
resolved for that symbol, logged loudly (`[ig_scale] currency_code fallback
to USD for {symbol}`) so a wrong-currency order is never sent silently.

---

<!-- moved from CLAUDE.md 2026-09-04 — the id=824 corruption arithmetic -->

**The −$2,453.93 / 32-trade figure was wrong wherever it appeared.** It is one
corrupted row carrying 31 clean ones:

- `paper_trades` **id=824** (2026-07-21, EURUSD bb_squeeze PAPER_BUY) logged
  native points-scale prices unconverted — `entry=11403.2, sl=11400.7,
  tp=11408.2` — the documented EURUSD DEMO scale quirk. `sl_distance` computed
  as `2.5` in decimal terms → `lot_size = 15/(2.5×10000) = 0.0006`, **clamped
  up to the 0.1 floor** → `pnl = −2.5 × 0.1 × 10000 = −$2,500.00`.
- **Excluding id=824, the other 31 trades sum to `+$46.07`**; expectancy moves
  from −$76.69 to **+$1.49/trade**.

The strategy's paper record is mildly positive, not catastrophic. It still
fails promotion criteria on PF and expectancy — the point is that one bad row
was misrepresenting 31 clean ones. id=824 is **unique**, the only out-of-band
price in `paper_trades` (1,447 rows) or `trades` (894 rows). Quarantine it, do
not delete it — it is the evidence.

Root cause is structural, not a one-off: **the paper-trade path has no
`ig_scale` conversion at all.** The boundary-conversion sites listed under
Price scale quirk do not include it. Separately, 5 more paper rows hit the
**opposite** clamp (sub-pip stops → lot 11–49 clamped down to 10), which
under-risks those trades and **inflates Sharpe** — one of the four
R:R-adjusted promotion criteria. Any `sl_distance` sanity bound must reject at
**both** ends. See findings doc finding 3.

---

<!-- moved from CLAUDE.md 2026-09-04 — rule 9's worked reasoning; the operational instruction stays -->

- **Rule 9 — duplication BIASES, it does not merely inflate.** A constant
  inflation cancels out of a mean. This one does not, because the multiplier
  correlates with the quantity measured: a stalled buffer is re-read every
  cycle, so **the anomalies are duplicated ten times more than the ordinary
  bars.** It reversed two published conclusions, **both in the same direction**
  — a reviewer sanity-checking the direction would have found it plausible.
  **Before computing any statistic from `signal_log` or
  `candle_source_compare`, dedup to one observation per (symbol, bar) and state
  which key you used.** `checked_at` and `stream_time` are different keys and
  give different answers on the same table.

---
