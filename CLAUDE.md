# Trading Bot — CLAUDE.md

## Project Overview
Webhook-driven algorithmic trading bot. Pipeline:
TradingView alert → webhook → Python bot → IG Markets API.
Current focus: Phase 7 — Risk Management & Stability.
Forward development plan: see ROADMAP.md

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

## Architecture
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
                            ✅ log_paper_trade, get_paper_trades
                            ✅ get_paper_trade_stats, get_paper_stats_by_symbol
                            ✅ get_pending_paper_trades, resolve_paper_trade
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
utils/telegram_alert.py     ❌ DELETE THIS LINE'S PREMISE — Telegram
                            alerting is BUILT and deployed as
                            bot/notifier.py (4 layers, see Alerting).
                            No utils/telegram_alert.py exists or is
                            needed.

## Environments

### Local (WSL only — never PowerShell)
Path: /mnt/c/Users/tanbe/Downloads/trading_bot_skeleton
Git:  git@github.com:ben1115123/trading_bot.git
SSH:  ~/.ssh/id_ed25519

### VPS (Oracle Cloud) ✅ STABLE
Host: 149.118.143.112  User: ubuntu
Path: /home/ubuntu/trading_bot
SSH key: ~/.ssh/trading-bot-new.key
  cp /mnt/c/Users/tanbe/Downloads/trading-bot-new.key \
     ~/.ssh/trading-bot-new.key && chmod 600 ~/.ssh/trading-bot-new.key
Credentials: always from .env — never hardcoded

## Docker (VPS) ✅ 3 containers stable
  bot        uvicorn main:app        port 8000 (internal)
  dashboard  streamlit dashboard/    port 8501 (internal)
  nginx      port 80 → routes both

All share ./database volume (SQLite).
docker-compose.yml manages all three with restart: always.
Bot container uses /app/docker-entrypoint.sh (starts cron + uvicorn)

## Deployment Process
1. git push origin main          (local WSL)
2. SSH VPS → git pull
3. docker-compose down
4. docker-compose up -d --build
5. docker-compose ps             (verify all 3 up)
6. curl localhost:8000 + curl localhost:8501

Gotcha: `docker-compose restart <service>` reuses the existing
container — it does NOT re-read .env. Changing .env (e.g. new
credentials) requires `docker-compose up -d <service>` to recreate
the container, or the old env stays baked in.

## Alerting (Telegram)

Four layers, added 2026-07-07/08.

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

### Layer 2 — event hooks (additive lines only, no logic changes)
| File | Hook | Level |
|------|------|-------|
| bot/execute_trade.py | OPENED (successful placement) | INFO |
| bot/execute_trade.py | REJECTED (margin + non-margin, one hook) | ERROR |
| bot/execute_trade.py | SL DRIFT (reanchor branch) | WARN |
| bot/live_signal_loop.py | SIGNAL LOOP ERROR (get_active_strategies guard + per-symbol _check_symbol exception handler) | ERROR |
| bot/live_signal_loop.py | DAILY LOSS LIMIT HIT (deduped to first trigger per UTC day via `_last_daily_loss_alert_date`) | ERROR |
| data/positions_poller.py | CLOSED (🟢/🔴 by P&L sign in message text, level always INFO) | INFO |

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

### Layer 4 — scripts/daily_summary.py
One Telegram message at 23:00 UTC (07:00 MYT), host cron (same reason
as watchdog — needs to read watchdog_alerts.jsonl, which lives on the
host filesystem). Stdlib-only, same .env/sqlite3 approach as
watchdog.py. Covers: trades opened/closed + net P&L + win/loss per
strategy (last 24h), current open positions, heartbeat status per
name, and watchdog alerts fired in the last 24h (read from
watchdog_alerts.jsonl — shows fired-and-cleared events, not just
conditions still unresolved at summary time).

## Selector Disabled (2026-08-15, commit 9e5f21a)

The daily strategy selector is off at **two independent layers**. Re-arming it
requires undoing **both** — uncommenting the cron line AND reverting the code.

**Layer 1 — cron.** `scripts/crontab`: the `0 6 * * *` `run_daily.py` line is
commented out, carrying the DISABLED note from the 2026-08-12 in-container
edit. Cron file now has exactly two active lines:

```
10 6 * * * root ... scripts/resolve_webhook_outcomes.py >> /app/logs/webhook_outcomes.log
*/15 * * * * root ... scripts/collect_candles.py >> /app/logs/candles.log
```

**Layer 2 — code.** `scripts/select_strategy.py`:
`SYMBOL_BLOCKLIST = {"BTC", "US100", "US500"}`. `SYMBOLS` is exactly
`["BTC", "US100", "US500"]`, so **`select_strategy()` skips every symbol it
iterates before `_select_for_symbol` is ever called — the selector is a total
no-op, not merely gated.** Also added `("US500","HOUR","stoch_rsi")` to
`STRATEGY_BLOCKLIST`.

**Why.** The selector ranks on `backtest_results` scores produced by an engine
that applies no take-profit and sizes at $15 against live $10 (findings 1, 12).
Separately, `_select_for_symbol`'s first-activation branch has no score
threshold: when `get_active_strategy(symbol, "HOUR")` returns `None`, the
top-scoring candidate is promoted **unconditionally**. That is the exact
mechanism that put `US100 HOUR supertrend` live on 2026-06-16 with zero paper
trades and zero human review (finding 5).

**Precision on which symbols were actually armed:** after the 2026-08-13
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
- committed `scripts/crontab` md5 `aea93925651e8ee24ce7d52e70b3434d`
  (blob `fe4ff2584c8dbfb4188bffdd6cf5b044316d135c`)
- in-container `/etc/cron.d/trading-bot` must match byte-for-byte —
  `Dockerfile:18` is a plain `cp`, no transformation
- the pre-fix Method A value was `d7565feade7ac71356579e686b887a1b`; seeing it
  again means a rebuild reverted the disable

## Claude Code SSH Permissions
✅ SSH, run docker, git pull, check logs, restart containers
❌ Never modify .env / expose credentials / git push from VPS
❌ Never stop bot container without permission

## Broker — IG Markets
Library: trading_ig (IGService)
Session: auto-refresh every 10min, full recreate on 401

### Current mode: DEMO (switched 2026-07-08)
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
to switch to.

Known bug fixed 2026-07-08: bot/test_ig.py and bot/test_trade.py were
hardcoded acc_type="DEMO" but pulled IG_API_KEY (the LIVE key) instead
of IG_DEMO_API_KEY — silently would have failed or hit the wrong
environment. Both now use the DEMO-specific vars.

### Price scale quirk — ig_scale.py (fixed 2026-07-09)
CS.D.EURUSD.MINI.IP quotes in native **points scale** (e.g. bid=11423.3)
on the DEMO account (Z67Y2C), not decimal FX price (1.14233) like every
other FX epic and like this same epic on the LIVE account (TW75S).
Discovered via 3x ATTACHED_ORDER_LEVEL_ERROR rejections on EURUSD SELL
(2026-07-08): entry_price came back native-scale from IG while SL/TP
(webhook, always decimal) went out unconverted — stop_level ended up
~10000x off market. Same mismatch silently corrupted candle_stream.py's
yfinance-vs-stream comparison logging (~1e8 "pip" deltas).

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

## Supported Assets — CANONICAL TABLE
This is the single source of truth. A second, contradictory "Supported Assets"
pair of tables further down this file was **stale and has been removed**: it
listed EURUSD/BTC as "Paper only" and omitted GBPUSD, AUDUSD and USDCAD
entirely, while all three have been trading live on demo since 2026-06/07.

| Symbol | Epic                | yfinance | Value/Point | Trades live? |
|--------|---------------------|----------|-------------|--------------|
| US500  | IX.D.SPTRD.IFMM.IP  | ^GSPC    | 1           | Yes — swiftalgo webhook (id 13) |
| EURUSD | CS.D.EURUSD.MINI.IP | EURUSD=X | 10000       | Yes — williams_r loop (22) + swiftalgo webhook (11) |
| GBPUSD | CS.D.GBPUSD.MINI.IP | GBPUSD=X | 10000       | Yes — williams_r loop (32) |
| AUDUSD | CS.D.AUDUSD.MINI.IP | AUDUSD=X | 10000       | Yes — williams_r loop (34) |
| USDCAD | CS.D.USDCAD.MINI.IP | USDCAD=X | 10000       | Yes — williams_r loop (36) |
| US100  | IX.D.NASDAQ.IFMM.IP | ^NDX     | 1           | No — symbol-blocklisted |
| DAX    | IX.D.DAX.IFMS.IP    | ^GDAXI   | 1           | No — all strategies failed |
| BTC    | —                   | BTC-USD  | 0.1         | No — inactive, no crypto strategy |

FX minis: $1/pip, 10k contract. EURUSD carries the points-scale quirk on the
DEMO account — see Price scale quirk.

## Paper Trade Symbols (.env)
**Actual deployed value** (verified on VPS `.env` 2026-08-15):
```
PAPER_TRADE_SYMBOLS=DAX,US100_5MIN,BTC
```
This file previously documented `DAX,BTC` with the note "(US100_5MIN removed
— stoch_rsi deactivated)". **That removal never happened in `.env`.** The
value is inert in practice — US100 5MIN has no active row — but the doc and
the deployment disagreed, so trust `.env`.

Other `.env` values worth knowing: `IG_ACC_TYPE=DEMO`,
`CANDLE_SOURCE=ig_stream`, and `RISK_PER_TRADE=5` which **no code reads**
(see Dead Config).

## Active Strategies

### Live — 6 instances (verified against `active_strategy` 2026-08-15)

Every row below is **demo** (account Z67Y2C). `status='active'` in
`active_strategy`. **`backtest_id` is NULL on all six** — none of them has
recorded backtest provenance (findings doc finding 13).

| id | Symbol | TF | Strategy | Source | Rostered params |
|----|--------|-----|----------|--------|-----------------|
| 11 | EURUSD | HOUR | swiftalgo | webhook | n/a — Pine Script upstream |
| 13 | US500 | HOUR | swiftalgo | webhook | n/a — Pine Script upstream |
| 22 | EURUSD | 15MIN | williams_r | loop | `period=10, oversold=-90, overbought=-20` |
| 32 | GBPUSD | 15MIN | williams_r | loop | `period=21, oversold=-90, overbought=-20` |
| 34 | AUDUSD | 15MIN | williams_r | loop | `period=14, oversold=-85, overbought=-20` |
| 36 | USDCAD | 15MIN | williams_r | loop | `period=14, oversold=-85, overbought=-15` |

**GBPUSD id 32 runs `period=21`, not the documented 14.** The williams_r entry
rules below this file describe `%R(14)`, and the 2026-07-09 FX expansion batch
was run at `period=14/-85/-15` — neither matches what is actually rostered.
This is the 4th occurrence of the params-divergence class; always pull params
from `active_strategy` (see Critical Rules).

Detail on the four loop instances:

| Symbol | Notes |
|--------|-------|
| GBPUSD | Promoted 2026-06-22. FRAGILE walk-forward. $1.50 risk was halved 2026-07-07 then **restored to $10** for demo validation. No session blocks. The 2026-07-21 review gate never happened — still open |
| EURUSD | Data-collection instance (2026-07-14), not an edge promotion. Original 2026-07-07 run REJECT (median PF 0.92, 42.9% windows); 2026-07-14 rerun with rostered params MARGINAL (median PF 1.08, 85.7% windows, 442 test trades). Discrepancy root cause irreproducible — the runs were never persisted. $10 risk |
| USDCAD | Data-collection instance (2026-07-14), never backtested before that batch. Walk-forward REJECT (median PF 0.99, 50% windows, 410 test trades). Epic verified clean decimal scale on demo 2026-07-14. $10 risk |
| AUDUSD | Was the **Phase-3 lead candidate** (2026-07-15) — the only roster strategy to clear a full ROBUST gauntlet. **The hard gate resolved against it 2026-08-12: Branch B, DIVERGES.** 51 post-cap clean trades, PF 0.71 vs promotion basis 1.285, WR 26.0%, net −$109.07, expectancy −$2.18/trade — the *worst* live performer of the four williams_r instances. Diagnosis: engine flattery. See ROADMAP hard gate + findings doc |

**Corrections to claims previously made in this table:**
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
| EURUSD | 15MIN | williams_r | Live | loop   | Data-collection instance (2026-07-14) — promoted for regime-tagged execution data. Walk-forward status: original 2026-07-07 run REJECT (median PF 0.92, 42.9% windows), corrected 2026-07-14 rerun with rostered params (period=10, oversold=-90, overbought=-20) MARGINAL (median PF 1.08, 85.7% windows, 442 test trades) — verdict boundary-sensitive, NOT an edge promotion. Discrepancy investigated: same cache (predates the original run), same params (verified via active_strategy id=22 timestamp), same window count (7=7) ruling out a --count difference, no engine/strategy code changed since — root cause irreproducible because walk-forward runs were never persisted (no DB row, no saved output); likely a --session-filter or --max-hold CLI flag difference in the original invocation. $10 risk |
| USDCAD | 15MIN | williams_r | Live | loop   | Data-collection instance (2026-07-14) — never backtested before this batch. Walk-forward: REJECT (median PF 0.99, 50% windows, 410 test trades, default params period=14/oversold=-85/overbought=-15 — no prior rostered config existed). NOT an edge promotion — running live on demo purely for regime-tagged execution data. Epic CS.D.USDCAD.MINI.IP verified clean decimal scale (bid=1.41468, TRADEABLE) on demo (Z67Y2C) 2026-07-14; newly registered in ig_scale.py and execute_trade.py EPIC_CONFIG. $10 risk |
| AUDUSD | 15MIN | williams_r | Live | loop   | **Phase-3 lead candidate** (2026-07-15) — promoted paper→demo-live on full-stack validation, NOT a data-collection instance: walk-forward ROBUST (median PF 1.285, 83.3% windows profitable, 6 windows — corrected for the plateau-center params below; the original -15 config's 100%-windows/MARGINAL number was a different cell), stability-map plateau (23 contiguous cells at PF>=1.1, not a spike), permutation test 96th percentile vs synthetic noise, Monte Carlo positive at every percentile (p5=$707 to p95=$2621 on $500/$10-risk, 1000 paths). Params corrected period=14/oversold=-85/**overbought=-20** (was -15 — the rostered row predated the stability map; -20 is the plateau center). Epic CS.D.AUDUSD.MINI.IP verified clean decimal scale (bid=0.6987, TRADEABLE) on demo (Z67Y2C) 2026-07-15; newly registered in ig_scale.py/execute_trade.py EPIC_CONFIG (was paper-only). $10 risk (demo — no bankroll to protect; live sizing per the MC ruin table below comes at Phase 5) |

### Paper
| Symbol | TF    | Strategy   | Mode  | Source | Notes                          |
|--------|-------|------------|-------|--------|---------------------------------|
| US500  | HOUR  | williams_r | Paper | loop   | Accumulating trades             |
| EURUSD | 15MIN | stoch_rsi  | Paper | loop   | 297 bt trades, PF 1.36          |
| EURUSD | 15MIN | bb_squeeze | Paper | loop   | 33 bt trades, PF 2.18. Walk-forward (2026-07-09): FRAGILE — median PF 1.08, 57.1% windows profitable, 149 trades across 7 windows. **Paper P&L corrected — see bb_squeeze correction below** |
| EURUSD | 15MIN | supertrend | Paper | loop   | 111 bt trades, PF 1.35          |
| US500  | HOUR  | stoch_rsi_confluence | Paper | loop | session filter only, shadow logging — see below |
| EURUSD | 15MIN | ny_session_momentum | Paper | loop | 37 bt trades, 75.7% WR, PF 1.64, follow mode |
| US500  | 15MIN | ema_pullback         | Paper | loop | 44 bt trades, 45.5% WR, PF 1.57, EMA8/50. Walk-forward (2026-07-09): FRAGILE — median PF 1.03, 53.8% windows profitable, 171 trades across 13 windows |
| US100  | 15MIN | ema_pullback         | Paper | loop | 86% combos profitable, PF 3.17 best. Walk-forward (2026-07-09): FRAGILE — median PF 1.12, 69.2% windows profitable (one window short of ROBUST's 70% bar), 70 trades across 13 windows. The PF 3.17 sweep result did not survive — overfit |
| GBPUSD | 15MIN | ema_pullback         | Paper | loop | 25 bt trades, 64% WR, PF 2.00 |

### bb_squeeze EURUSD paper P&L — CORRECTED (2026-08-12)
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

## Deactivated Strategies (2026-05-27)
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

## Instrument Notes
GBPUSD: mean reversion AND ema_pullback work (similar to EURUSD)
USDJPY: all strategies failed in old single-split tests — do not trade.
        Re-examined 2026-07-09 specifically for williams_r under
        walk-forward (see below) — still not promoted, but closest of
        the expansion batch to ROBUST.
DAX:    all strategies failed — do not trade

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

## Paper Promotion Criteria

Standard promotion (WR-based, for 1.67 R:R strategies):
- 30+ resolved paper trades
- WR >= 52%
- Positive simulated P&L
- Losses not correlated with stoch_rsi US500

R:R-adjusted promotion (for high R:R strategies, PF >= 1.3):
- 50+ resolved paper trades (higher bar for lower WR)
- Profit Factor >= 1.3 after estimated spread
- Expectancy per trade > $2.00 after spread
- Sharpe >= 0.08
- Losses not correlated with stoch_rsi US500

## Signal Sources
| Source              | What it is                        |
|---------------------|-----------------------------------|
| tradingview_webhook | SwiftAlgo Pine Script via webhook |
| live_signal_loop    | Autonomous bot signal loop        |
| ig_import           | Manual trades synced from IG      |
| manual              | Manually entered via dashboard    |

## Webhook Payload
{
  "symbol": "US500", "buy_signal": "1", "sell_signal": "0",
  "trend": "1", "long_sl": "5100.0", "long_tp": "5200.0",
  "short_sl": "5300.0", "short_tp": "5000.0"
}
strategy_name hardcoded to "swiftalgo" in receiver.py
source hardcoded to "tradingview_webhook" in receiver.py

## VIX Filter (swing strategies, live only)
Threshold: VIX >= 20 → block | VIX >= 18 → caution, also block
Changed 2026-06-12 based on live data:
VIX 20-25 showed 16.7% WR across 6 trades
Fails open: API error or fetch failure → allow entry
Applied once per signal_loop cycle (not per symbol)
Paper trades always fire regardless of VIX — for filter evaluation
File: filters/vix_filter.py

## SwiftAlgo Webhook Filters (all symbols)
Applied in order before any trade execution:
1. Market close block (_is_blocked)
2. Daily loss limit
3. Session filter: symbol-specific UTC windows (webhook_filters.py SESSION_WINDOWS)
4. Macro event filter: MACRO_EVENTS list — update every Sunday
5. Spread filter: blocks if current_spread > 2× NORMAL_SPREADS[symbol]
6. Swiftalgo routing: checks active_strategy status for symbol+swiftalgo
   status=inactive → blocked | status=paper → logged to paper_trades
   No active_strategy row → falls through to place_trade_from_alert (live)
EURUSD paper entry_price: midpoint of SL+TP (approximation, P&L rough)

<!-- The two stale "Supported Assets" tables that stood here (Live: US500/
     US100/DAX only; Paper only: EURUSD/BTC) were removed 2026-08-15. They
     contradicted the canonical table above and were wrong in both directions:
     EURUSD was listed paper-only while trading live since 2026-05-27, and
     GBPUSD/AUDUSD/USDCAD were absent entirely despite trading live. Use the
     canonical Supported Assets table. -->

## Risk Management
lot_size = get_risk_per_trade(symbol) / (sl_distance × value_per_point)
Min: 0.1 | Max: 10.0 | Entry price fetched live from IG

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

### Phase-5 Sizing Reference — Monte Carlo Risk-of-Ruin (2026-07-15)
Bootstrap MC (5000 paths, shared resampled paths across configs, seed=42)
on williams_r AUDUSD 15MIN (period=14/oversold=-85/overbought=-20, the
promoted plateau-center params), $500 account:

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

### Paper Trade Risk Override (added 2026-06-12)
Paper trades always use $10 risk regardless of symbol (RISK_PER_TRADE
default). Live overrides above don't affect paper trade sizing —
they're the same value right now only because both are $10 during
demo validation.

### Dead Config
VPS .env has RISK_PER_TRADE=5 — NOT read by any code. risk_manager.py
hardcodes RISK_PER_TRADE=10 as default. Don't trust this env var.

### Daily Loss Limits
Keyed per (symbol, strategy_name) as of 2026-07-22 — each instance gets its
own $75 budget, not one combined pool. Fixed because a FRAGILE strategy's
bad day (e.g. GBPUSD williams_r) was blocking an unrelated instance (e.g.
AUDUSD williams_r) even though they share a strategy_name — same-strategy
symbols still isolate from each other. `risk/daily_loss.py`
`is_daily_loss_limit_breached(symbol=..., strategy_name=...)`; call sites
`webhook/receiver.py` and `bot/live_signal_loop.py::_risk_check`. Telegram
alert dedup also moved from one global per-day flag to per (symbol,
strategy_name).

| Source              | Limit         | Behaviour when hit                    |
|---------------------|---------------|----------------------------------------|
| signal_loop          | $75/instance | Stops firing new trades for that (symbol, strategy_name) only |
| tradingview_webhook  | $75/instance | Blocks incoming webhooks for that (symbol, strategy_name) only |

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

### Trade Count Limits (bug catchers only)
MAX_TRADES_PER_DAY       = 20  (across all symbols)
MAX_TRADES_PER_SYMBOL_TF = 6   (per symbol+timeframe)

### Market Hours (signal_loop blocks outside these)
| Symbol      | Opens      | Closes     | Notes              |
|-------------|------------|------------|--------------------|
| US500/US100 | 00:00 UTC  | 20:00 UTC  | Sun 22:00 UTC open |
| DAX         | 00:00 UTC  | 15:30 UTC  | 1h before 16:30    |
| BTC         | 24/7       | never      | Paper only         |

Friday block: no new trades after 19:45 UTC
Weekend close: auto-closes US500/US100/DAX at 20:40 UTC Friday

## Market Close Times (UTC)
| Symbol | Weekday close | Friday last trade |
|--------|---------------|-------------------|
| US500  | 20:00         | 19:45             |
| US100  | 20:00         | 19:45             |
| DAX    | 15:30         | 15:30             |
| BTC    | 24/7          | 24/7              |

## Backtesting Rules (enforced in ALL phases)
- ALWAYS split candles 80/20 (train/test)
- NEVER generate signals on training portion
- ALWAYS store every simulated trade in backtest_trades
- ALWAYS calculate benchmark (buy-and-hold) per run
- ALWAYS run parameter sweep on new strategies
- ALWAYS use --source yfinance --cache on all runs
- Default timeframe: HOUR (better signal density)
- Default candle count: 5000 (updated from 2000)
- Minimum trades threshold:
    swing: >= 10 trades in test window
    daytrading: >= 5 trades in test window
- Strategy types:
    swing: HOUR timeframe, no session filter, no hold cap
    daytrading: 5MIN, session-filter US or 24_7,
                max-hold 78 (US session) or 288 (BTC)

## Data Sources
- Backtesting: yfinance (free, no API limit) — DEFAULT
  Symbol map: US500→^GSPC, US100→^NDX, BTC→BTC-USD,
              DAX→^GDAXI
  Cache: scripts/candle_cache/{SYMBOL}_{TF}_{COUNT}_yf.json
- Live trading: IG Markets API only
  IG historical API: 10,000 points/week — reserved for
  live execution only, never for backtesting

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
triggered this investigation. DB backed up before correction
(`database/trades.bak-20260720T012352Z.db`); full before/after values
logged to `logs/ledger_reaudit_20260720T012352Z.jsonl`. One trade
(id=500, GBPUSD) has no matching IG transaction in history at all and
was left uncorrected — flagged, not explained. Re-run the script
periodically or after any future poller/ig_scale change; it's
read-only against IG and idempotent (dry-run reports zero once clean).

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

## Paper Trading System
- paper_trades table in DB — logs every paper signal
- outcome: PENDING → WIN/LOSS (resolved each loop cycle)
- _resolve_pending_paper_trades() runs at start of each cycle
- Checks subsequent candles: high >= tp = WIN, low <= sl = LOSS
- Simulated P&L tracked separately from live P&L
- Dashboard page 08 shows paper trading log
- Performance page 07 shows Paper vs Live comparison
- Paper routing: PAPER_TRADE_SYMBOLS env var (symbol-level)
  OR active_strategy.status='paper' (strategy-level)
- Multi-strategy: active_strategy UNIQUE(symbol,timeframe,strategy_name)
  allows multiple strategies on same symbol+TF

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

### FVG Strategy (added 2026-05-29)
| Symbol | TF    | Strategy | Rationale                                         |
|--------|-------|----------|---------------------------------------------------|
| US500  | 15MIN | fvg      | SMC Fair Value Gap POC, London/NY sessions only   |

fvg params: atr_period=10, min_gap_atr=0.5, expiry_candles=15
Entry: close retraces into 3-candle gap zone (confirmation close)
Session filter: London 07:00-09:59 UTC, NY 13:00-15:59 UTC
FVG expiry: 15 candles without retracement
Min gap size: 0.5x ATR10

## IG Sync (sync_ig_trades.py)
- Self-contained IG session (does not import execute_trade.py)
- Pulls transaction history by date range
- INSERT new trades not in DB (source=ig_import)
- UPDATE existing trades with P&L/close price
- Duplicate prevention:
    Primary: deal_reference match under any non-import source
    Secondary: price+symbol+direction+date match
- INSTRUMENT_TO_SYMBOL map:
    "US 500 Cash ($1)"      → US500
    "US Tech 100 Cash ($1)" → US100
    "Bitcoin ($0.1)"        → BTC
    "Spot Gold ($1)"        → XAUUSD
    "Germany 40 Cash (£1)"  → DAX

## Unverified Controls — the recurring failure class

**The class: a control believed to be in place that was never empirically
confirmed.** Four instances surfaced in the 2026-08-12 session alone.

1. **`service cron reload` is a no-op.** `/etc/init.d/cron` maps
   `reload|force-reload` to `log_daemon_msg` + `log_end_msg 0`, commented
   `# cron reloads automatically`. It signals nothing and **returns success**.
   Had it been used as the remedy, it would have reported clean and changed
   nothing.
2. **`collect_candles` cron recorded as disabled 2026-06-28** — still firing
   every 15 minutes ~7 weeks later. Almost certainly an in-container edit lost
   to a later rebuild, i.e. instance 3 realised historically.
3. **In-container cron edits do not survive a rebuild.** `/etc/cron.d/trading-bot`
   is baked from `scripts/crontab` at build time (`Dockerfile:18`). Editing the
   container file works until the next `up -d --build` silently restores the
   baked copy. This is why the 2026-08-15 deploy exists at all.
4. **A probe that invalidates its own precondition returns a false negative.**
   A background check sampled a sentinel file 32 seconds *after* the cleanup
   step had deleted it, and reported `MARKER_ABSENT` for an event that had
   demonstrably occurred. The probe was measuring its own teardown.

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

## Monitoring Gaps (outstanding)

- **`candle_stream` staleness is unmonitored.** `scripts/watchdog.py` alerts
  only on `signal_loop` heartbeat staleness. The `heartbeat` table also holds
  `name='candle_stream'`, and nothing checks it — a genuinely dead candle
  stream **would not page anyone**. Observed 2026-08-15: `candle_stream` last
  beat 05:04 UTC and silent thereafter, which is correct for a weekend
  (markets closed, no Lightstreamer ticks) and therefore indistinguishable
  from a real failure. Fix needs a market-hours-aware staleness rule, the same
  shape the signal_loop check already uses (Sun 22:00 – Fri 21:00 UTC).
- **`/app/logs/daily_run.log` no longer exists**, so the dashboard's
  cron-status panel (page 01) parses a missing file. Expected consequence of
  disabling `run_daily`, cosmetic, but the panel now reads permanently stale.
- **51 dangling Docker images on the VPS** as of 2026-08-15, accumulated
  across rebuilds. Not pruned — noted only. Precedent exists (Jun 27 prune).
  Disk fills quietly; check before the next rebuild.

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

## Key Gotchas
- VPS backtest_results table diverges from local —
  backtest sweeps run locally are NOT synced to VPS.
  active_strategy.backtest_id on VPS only valid for
  backtests run via run_daily.py cron on VPS itself.
  Local sweep results exist in local trades.db only.
- Session recreated on execute_trade.py import
- Cooldown is PER-SYMBOL (not global) — last_trade_time dict
- place_trade auto-retries once on 401 — retry preserves
  strategy_name and source
- Poller failure must NOT affect trade execution
- logs/trade_log.csv deprecated — DB only
- Trend filter disabled in execute_trade.py —
  Pine Script handles filtering upstream
- Positions poller: column names are dealId/epic/direction
  (NOT position.dealId/market.epic) — fixed May 2026
- _verify_closed_on_ig() prevents false closes —
  checks IG API before marking any trade CLOSED
- Transaction history match: deal_reference primary,
  openDateUtc proximity fallback
- Deferred P&L checker: runs every 5min, gives up
  after 24 hours, logs warning if failed
- active_strategy unique constraint on symbol+timeframe+strategy_name
  — multiple strategies can co-exist on same symbol+TF
  — HOUR and 5MIN both active per symbol, and multiple strategies per slot
- get_active_strategy(symbol, timeframe) → dict | None
- get_active_strategy() → list of all active rows
- get_active_strategies(symbol) → list per symbol
- signal_loop source = "live_signal_loop"
- swiftalgo source = "tradingview_webhook",
  strategy = "swiftalgo"
- manual trades source = "manual"
- ig_import source = "ig_import", strategy = "manual"
- live_signal_loop: dedup via last_fired[(symbol,timeframe)]
- live_signal_loop: per-symbol try/except — one bad symbol
  won't kill the loop
- SL/TP in signal loop: candle-range absolute prices
  (flat 1× SL, 2× TP from candle high-low range, floored
  per-symbol via _MIN_SL_DIST — NOT 1.5×/2.5×, corrected
  2026-07-13, second doc drift on this exact item)
- candles[-2] used (not [-1]) — avoids in-progress candle
- PAPER_TRADE_SYMBOLS env var controls paper mode
  format: "DAX,US100_5MIN,BTC"
- sync_ig_trades: duplicate prevention via deal_reference
  + price/symbol/date secondary check
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
- Overview alert banner triggers if signal_log silent 2h+
- Cron status parsed from /app/logs/daily_run.log
- Weekend close: _verify_closed_on_ig before marking CLOSED
- Friday webhook block: _is_blocked() called in receiver.py

## Test Scripts
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

## Current Build Phase
PHASE 7 — Risk Management & Stability

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

### Still to build in Phase 7
- ~~Telegram alerts (trade placed, trade closed, risk limit hit)~~
  **DONE — shipped 2026-07-07/08.** This line contradicted the Alerting
  section for five weeks. All three named alerts exist as Layer 2 event hooks
  in `bot/notifier.py` (OPENED, CLOSED, REJECTED, SL DRIFT, DAILY LOSS LIMIT
  HIT, SIGNAL LOOP ERROR), plus heartbeat/watchdog (Layer 3) and the 23:00 UTC
  daily summary (Layer 4). There is no `utils/telegram_alert.py` and none is
  needed.
- Strategy stability rules:
    Don't switch if live win rate dropped < 40% last 7 days
- Weekly performance report via Telegram
- Confluence strategy (multi-condition entry)
  Planned: EMA(200) + RSI(14) + MACD crossover

---

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

## Upcoming Phases

PHASE 8 — Production Frontend (Next.js + Vercel)
  Vercel (Next.js) → API calls → VPS (FastAPI + SQLite)
  Build only after Streamlit features finalised
  Build only after 6+ weeks of live data collected

PHASE 9 — Online Learning / Strategy Auto-Generation
  9A: Parameter optimisation — auto-trigger fresh backtest
      when live win rate drops 20% below backtest win rate
  9B: Strategy generation — test new indicator combinations
      automatically, promote winners to live

## Phase 9 Strategy Candidates

### FVG (Fair Value Gap) — SMC concept
- Most automatable SMC technique
- Bullish FVG: gap between candle[i-2].high and candle[i].low
- Bearish FVG: gap between candle[i-2].low and candle[i].high
- Entry on retracement back into the gap
- Genuinely uncorrelated to all existing strategies
- Target: paper trade on US500 HOUR
- Build when system stable after 2026-05-27 changes

---

## Critical Rules for Claude Code
- NEVER modify execute_trade.py without permission
- NEVER create a second execution engine
- NEVER hardcode credentials, IPs, or paths
- NEVER expose credentials in any output or logs
- NEVER stop bot container without permission
- ALWAYS use .env for all config values
- ALWAYS ask before touching bot/ or webhook/
- ALWAYS test locally before deploying to VPS
- ALWAYS verify bot works after any deployment
- ALWAYS apply 80/20 split + store trades + benchmark
- ALWAYS use --source yfinance --cache for backtests
- NEVER use IG API for historical candle fetches
- Database calls ONLY via database/models.py
- New dashboard pages ONLY in dashboard/pages/
- Docker only on VPS — no systemd
- SQLite only unless explicitly told otherwise
- After every VPS deploy: docker-compose ps
- NEVER deploy strategy with insufficient trades
- NEVER switch active strategy during market hours
- active_strategy table = single source of truth
- ALWAYS log strategy switches with reason
- Any analysis of a rostered strategy must pull its real params
  from active_strategy first — never assume file defaults
  (3rd occurrence of this divergence, 2026-07-14: williams_r
  EURUSD/GBPUSD live params differ from class defaults)
- NEVER run live trades on paper symbols
- Paper trade symbols controlled by PAPER_TRADE_SYMBOLS env
- connors_rsi2 NOT active — designed for daily bars only
- Sync deduplication: always check deal_reference before INSERT