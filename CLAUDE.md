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
6. curl localhost:80 + curl localhost:80/health   (both expect 200)

⚠️ **Step 6 was WRONG until 2026-08-21** and read
`curl localhost:8000 + curl localhost:8501`. **Neither port is published to
the host.** `docker-compose.yml` exposes them container-internally
(`8000/tcp`, `8501/tcp`, no host mapping) and only nginx maps
`0.0.0.0:80->80/tcp`. Both of those curls return **`000` — connection refused —
on a completely healthy stack**, so anyone following the old runbook got a
false failure and started debugging a working system. Confirmed by doing
exactly that on the 2026-08-21 deploy.

Working checks, all verified on a healthy stack:
```
curl -s -o /dev/null -w '%{http_code}' localhost:80          # 200
curl -s -o /dev/null -w '%{http_code}' localhost:80/health   # 200
curl -s -o /dev/null -w '%{http_code}' localhost:80/webhook  # 405 = alive, POST-only
```
Also useful, and independent of nginx:
`docker exec trading_bot-nginx-1 wget -qS -O /dev/null http://bot:8000/`
— proves the bot app answers on the docker network. Note `curl` is **not
installed inside** the bot or dashboard images, so `docker exec … curl` fails
with `sh: 1: curl: not found` — that is a missing binary, not a dead service.

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
edit. **As of 2026-08-23 the cron file has exactly ONE active line** — the
`*/15` candle collector was disabled the same day (see IG Historical Allowance):

```
10 6 * * * root ... scripts/resolve_webhook_outcomes.py >> /app/logs/webhook_outcomes.log
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

### Live — 2 instances (verified against `active_strategy` 2026-08-21)

**As of 2026-08-21T18:41:31Z there are exactly TWO `status='active'` rows, and
both are webhook swiftalgo.** No `live_signal_loop` strategy is trading live.

| id | Symbol | TF | Strategy | Source | Rostered params |
|----|--------|-----|----------|--------|-----------------|
| 11 | EURUSD | HOUR | swiftalgo | webhook | n/a — Pine Script upstream |
| 13 | US500 | HOUR | swiftalgo | webhook | n/a — Pine Script upstream |

Both **demo** (account Z67Y2C). `backtest_id` NULL on both — no recorded
backtest provenance (findings doc finding 13).

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

### Paper
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
5. Spread filter: ⛔ **DEAD — has never blocked a single alert.** This line
   claimed an active protection that does not exist. `receiver.py:216` reads
   `data.get("spread")` from the inbound payload, and **0 of 382 stored
   TradingView payloads have ever carried a `spread` key**, so
   `should_block_spread` short-circuits on its `None` fail-open guard before
   the threshold is consulted. All-time `spread_filter` blocks: **0**, against
   session_filter 150, day_of_week 27, daily_loss_limit 15. Separately the
   threshold itself is ~5× too wide (EURUSD `NORMAL_SPREADS` 0.0008 = 8 pips,
   blocking at 16 pips, vs ~1.5 pips measured on a thin weekend book) — so
   fixing the constant alone would change nothing. See findings doc finding 15.
   Live trades are NOT protected against spread blowouts and never have been.
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
  ⚠️ **The reservation was not being honoured.** `collect_candles.py` was
  taking 100,800 points/week of a 10,000/week budget and returning nothing,
  which pushed `candle_stream`'s warm-up onto yfinance. Disabled 2026-08-23 —
  see IG Historical Allowance.

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
4. **A probe that cannot observe the working state returns a false negative.**
   Two instances so far — see "The self-invalidating probe" below, which is now
   its own rule rather than a footnote to this list.

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

## engine_version marking (2026-08-16)

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

### ⛔ Do NOT null `active_strategy.score` as tidying
It is tempting: every current score was produced by the pre-parity engine and is
therefore invalid, so nulling looks like hygiene. **It is not. It is dangerous,
and the reason is specific.**

`_select_for_symbol` reads `get_active_strategy(symbol, "HOUR")`, and the
`+0.05` improvement guard lives in the `else` branch — the one that only runs
when an incumbent exists with a comparable score. Nulling every score puts the
selector into the same state that produced the **2026-06-16 unreviewed promotion
of US100 HOUR supertrend**: no usable incumbent score, therefore no threshold,
therefore promote the top candidate unconditionally.

Nulling is correct **only after** re-validation has produced replacement scores
under the fixed engine. Sequence: engine fix → gauntlet regeneration → new
scores written → then null/replace. Not before, and never as cleanup.

The selector is inert at both layers right now (see Selector Disabled), which is
what makes the deferral safe. That inertness is load-bearing until this is done.

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

## ⛔ DAX candle cache — BLOCKER on any DAX work

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

## Database Backups (VPS)

Live in **`/home/ubuntu/backups/`**, outside the repo tree. Deliberately not
under `database/` — `Dockerfile:11` is `COPY . .`, so anything in the tree is
baked into every image layer; the two backups alone were 504 MB per build.

| File | Taken for | Contents |
|---|---|---|
| `trades.bak-20260720T012352Z.db` | Before `scripts/reaudit_close_prices.py` corrected the 8 cross-symbol-contaminated rows | 565 trades, 179,413 backtest_results — **sole surviving pre-correction ledger state** |
| `trades.bak-20260816T042148Z.db` | Before the `engine_version` migration | 906 trades, 268,117 backtest_results |
| `trades.bak-20260817T164123Z.db` | Undocumented until 2026-08-21 — taken around the `market_hours` / finding-23 FX weekend-block work | 918 trades, 268,117 backtest_results, `integrity_check ok` |
| `trades.bak-20260821T184131Z.db` | Before moving all four live `williams_r` instances to `paper` | 996 trades, 268,117 backtest_results, `integrity_check ok` |
| `trades.bak-20260821T190857Z.db` | **Undocumented until 2026-08-22** — taken minutes after the williams_r demotion, purpose unrecorded | 996 trades, 268,117 backtest_results, `integrity_check ok` |
| `trades.bak-20260822T180436Z.db` | Taken by `scripts/import_stage4.py` before the Stage 4 import write test (rule 5) | 996 trades, 268,117 backtest_results, `integrity_check ok` |
| `trades.bak-20260823T040057Z.db` | Before the Stage 4 dress-rehearsal import (rule 5) | 996 trades, 268,117 backtest_results, `integrity_check ok` |
| `trades.bak-20260823T041942Z.db` | Before the post-fix dress-rehearsal re-import (rule 5) | 996 trades, 268,118 backtest_results, `integrity_check ok` |

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

## ⏳ CONTROLS AWAITING FIRST REAL FIRE

Two gates are deployed and **verified only against constructed timestamps**.
Neither has ever fired in production. Per the marker-test rule, their silence
proves nothing until each has been observed once with a positive signal.

| control | deployed | first reachable | grep `signal_log.error` for |
|---|---|---|---|
| FX weekend block | 2026-08-17 | ✅ **VERIFIED Sat 2026-08-22** | `market closed — weekend` |
| 21:00 rollover gate | 2026-08-21 | **Mon 2026-08-24 21:00–21:59 UTC** | `entry window closed — daily rollover hour` |
| collector disable → IG warm-up | 2026-08-23 | **after the allowance resets** | see CHECK 3 below |

## ⚠️ CHECK 3 — does the warm-up reach IG once the collector stops burning?

**The collector disable is verified. What it was supposed to BUY is not.** Two
different claims, and only the first has evidence:

| claim | status | evidence |
|---|---|---|
| the collector no longer runs | ✅ **VERIFIED 2026-08-23 14:31 UTC** | marker test, below |
| `candle_stream` warm-up now reaches IG instead of yfinance | ⏳ **NOT OBSERVABLE YET** | — |

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

**Why the second claim cannot be checked today — and must not be faked.** The
allowance is a **rolling weekly budget that is currently at zero**; stopping
the drain does not refill it. Warm-up only runs on container start or stream
reconnect. So a restart right now would fall back to yfinance **no matter how
correct the fix is** — the probe cannot reach the passing state. That is the
self-invalidating-probe rule exactly, and a rebuild today is separately
forbidden (CHECK 1's Sunday reopen, CHECK 2 on Monday).

**What PASSING looks like, stated before the observation:** on the first
warm-up after the allowance resets, the bot log shows
`[candle_stream] warm-up US500/15MIN: 200 candles (source=IG REST)` —
`source=IG REST`, **not** `source=yfinance (quota fallback)` — and
`[ig_allowance] candle_stream REST ...` prints a non-zero `remaining` with a
`resets_at`. That log line is only producible by a successful IG fetch.

**Do not read a yfinance fallback before the reset as a failure of this
change.** And do not restart the container to force the check — take the next
warm-up that happens anyway.

CHECK 1 **passed on 2026-08-22 — the control is verified.** One of its four
criteria was found to be mis-specified and re-scoped to Sunday; that is a
defect in the checklist, not in the control. See the result block before
drawing any conclusion from it. CHECK 2 is still pending, plus
one follow-up on CHECK 1 (spread sampling through the **Sunday** reopen, which
is the window that actually tests it).

Tick these off below when observed. Delete neither section until both are
confirmed — a control recorded as verified when it never fired is the same
error as a monitoring gap recorded as outstanding while the monitor existed.

## ⚠️ CHECK 1 — FX market-hours block (deployed 2026-08-17, due Sat 2026-08-22)

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

## ⚠️ CHECK 2 — 21:00 UTC rollover gate (deployed 2026-08-21, due Mon 2026-08-24)

`market_hours.is_entry_allowed` refuses entries in the 21:00 UTC hour, **all
instruments**, checked before the `_ALWAYS_OPEN` short-circuit so BTC is
covered. Rationale, evidence table and the DAX/BTC-are-mechanism-not-evidence
caveat live in the `market_hours.py` comment; do not restate them here.

**Verified so far: 33 marker assertions, in the deployed image, ALL AGAINST
CONSTRUCTED `datetime` VALUES.**

> ⚠️ **SUPERSEDED IN PART — it HAS now fired on a real clock.** Sunday
> 2026-08-23 21:00–21:59 UTC logged **48 rows** carrying
> `entry window closed — daily rollover hour`, found while re-testing CHECK 1.
> The table below predicted the Sunday reopen rule would shadow this gate at
> 21:30; it does not. **Monday 2026-08-24 21:00 is still worth checking** — it
> is the documented weekday case, where `is_market_open` is True for a
> different reason — but it is no longer the gate's first exercise, and
> criterion 1's "first genuine exercise" framing below is now inaccurate.

**Why Monday and not this weekend** — the gate is genuinely unreachable before
then, so its silence until Monday is expected and means nothing:

| | `is_entry_allowed` | `is_market_open` | who blocks |
|---|---|---|---|
| Fri 2026-08-21 21:30 | False | **False** | venue already shut |
| Sat 2026-08-22 21:30 | False | False | venue shut |
| Sun 2026-08-23 21:30 | False | True | ❌ **WRONG — observed: THIS gate**, 48 rows logged `daily rollover hour` |
| **Mon 2026-08-24 21:30** | **False** | True | **this gate** ← first genuine exercise |

### On Mon 2026-08-24, after 22:00 UTC, confirm all four

1. `signal_log` rows exist in 21:00–21:59 UTC with
   `error = 'entry window closed — daily rollover hour'` — the **exact** string,
   distinct from `'entry window closed — thin reopen / pre-weekend policy'`.
   Getting the pre-weekend string instead means the rollover branch is being
   shadowed by an earlier rule and the ordering in `_block_reason` has drifted
   from `is_entry_allowed`.
2. **Zero** `trades` rows with `substr(timestamp,12,2) = '21'` on that date.
3. `signal_log.spread` **non-null** on FX rows inside the blocked window —
   sampling must continue through the block. Same load-bearing ordering as
   CHECK 1: the sample is taken before the block check and the blocked branch
   still calls `log_signal_check`. The rollover hour is the widest-spread hour
   of the day and the single most valuable hour to keep sampling.
4. `signal_loop` heartbeat kept beating through a fully-blocked cycle.

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

### Also awaiting first fire: the shadow ratio gate

`risk/spread_gate.py`, `ENFORCE=False`, k=0.25. It only evaluates on an actual
BUY/SELL, so it is unexercised until a signal lands. It sits before the
paper/live branch, so a **paper** signal exercises it. Look for
`SHADOW spread gate:` in the bot log or in `signal_log.error`. It must
**never** appear as the cause of a skipped trade while `ENFORCE` is False — if
a trade is ever missing and this string is the only explanation, the shadow
gate has been promoted by accident.

## Stage 4 re-validation — WHERE IT RUNS AND HOW RESULTS COME HOME

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

### 🟡 EXPECT 12 OF 13 ROWS TO BE REDUCED_GAUNTLET — that is the plan, not a fault

`STABILITY_GRIDS` in `scripts/run_backtest.py` contains **only `williams_r`**.
Every other rostered strategy hits the no-grid branch and persists a
`REDUCED_GAUNTLET` marker row instead of a stability map. Verified working:
forcing it with `bb_squeeze` writes one `stability_map` row, verdict
`REDUCED_GAUNTLET`, fully stamped and carrying
`extra_json.params_source = "roster:active_strategy.id=24"`.

The standing plan was **build 2 grids, mark 4**. Against the current roster that
now reads: **build one more — `stoch_rsi` and `supertrend` — and accept the rest
as reduced.** Those two are the ones with live or recently-live history worth a
stability contour; the remainder are paper-only and a marker is an honest record
of what was not run.

**Write this down before the run, not after.** A batch that returns 12 reduced
verdicts is either "exactly as planned" or "something is badly wrong", and those
two look identical in the output. This entry is what makes it the first one.

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

## ⚠️ DRIFT AGAIN — image behind by `40d716b` (2026-08-23)

Recorded immediately rather than discovered later, because this file cleared a
drift note yesterday and a silently re-opened one is worse than a never-closed
one.

| | |
|---|---|
| running image | `sha256:42f5585b3e34`, built 2026-08-22 18:07 UTC, contains `591dc3a` |
| `origin/main` | **`40d716b`** — the two stability-map fixes |
| undeployed | `40d716b` (engine `run_stability_map`, `models.update_walkforward_extra`, `run_backtest.py`) plus docs |

**Zero runtime impact, and that is checked rather than assumed.**
`bot/live_signal_loop.py` does not import `backend.backtesting.engine` at all,
so the changed function is unreachable from the signal loop, webhook, poller or
execution path. The only changed runtime-reachable file is `database/models.py`,
and the change is **purely additive** (one new function, plus `import json`).

**Not deployed on purpose** — the Sunday reopen check (CHECK 1 criterion 4) is
due within hours and the 21:00 rollover gate (CHECK 2) on Monday. A rebuild
resets the Lightstreamer buffers and burns IG historical-data quota re-warming
them, which is exactly the wrong thing to do in the hours before two controls
are supposed to be observed firing for the first time. Deploy after CHECK 2.

⚠️ While the drift stands: `database/models.py` and `scripts/import_stage4.py`
were `docker cp`'d into the running container on 2026-08-23 to mark the pre-fix
rehearsal rows superseded. **Those copies are lost on the next rebuild** (see
Unverified Controls instance 3) — the DB rows they wrote are not. Nothing
depends on them persisting.

**Clear this entry when the next deploy lands**, and re-verify the crontab md5
anchor at the same time.

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

## 🚦 GATE — do not build the spread table before these are all true

The market-open filter shipped 2026-08-17 (`get_spread_samples(market_open_only=True)`,
predicate `market_hours.is_entry_allowed`). **The table itself is deliberately
NOT built yet.** Friday 2026-08-21 is the earliest check, and it is a check,
not a judgement call — the criteria are fixed here while the reasoning is
fresh.

**Why not on 2026-08-17's pool:** n was fine (65–89/symbol, and the filtered
distribution has only 2 distinct values, so the median is statistically
solid). **Coverage was not.** Hours **18:00–22:00 UTC had ZERO samples on
every symbol** — including the ~21:00 UTC daily rollover, the most reliably
wide weekday period there is. A median built then would not be thin, it would
be **biased low**: the same error as calibrating on the shut book, opposite
sign, and harder to catch because the number looks plausible.

### Acceptance criteria — ALL must hold

1. **Every UTC hour 00–23 represented**, and **18:00–22:00 specifically
   present**. This is the criterion that failed on 2026-08-17.
2. **Every weekday Mon–Fri represented.**
3. **≥ ~480 samples/symbol** after filtering (~97/day × 5 trading days).
4. **If any hour is still empty: do NOT build.** Report which hours, and wait.

### Preference: two weeks, not one

One Mon–Fri cycle is the *minimum* — it gives ~20 observations per hour. Two
weeks gives **~40 per hour** and a realistic chance of catching a news day
(NFP/CPI/FOMC), which is where the tail actually lives. Build at one week only
if something downstream is blocked on it; otherwise prefer two.

### When it is built

- `spread_model` renamed to make **median-only** explicit and impossible to
  mistake for tail-calibrated later
- `spread_table_sha` populated
- provenance in code per symbol: n samples, date range, filter applied
- commit message and script comment must state that **the tail is
  uncalibrated and risk-of-ruin work must NOT use this table**

### Known limitation to carry into the table — model shape, not filter

`is_entry_allowed` governs **entries**. A position held through Friday 20:45 →
Sunday 23:00 can still be **exited** at reopen spreads (10–17 pips measured),
and that cost is excluded from anything calibrated this way. `SPREAD_COSTS` is
a single round-trip constant and **cannot express an asymmetric entry/exit
cost**, so this is not fixable by filtering differently — it needs a different
model shape. Recorded in `get_spread_samples`' docstring where whoever builds
the table will read it.

## IG Historical Allowance — the collector is DISABLED (2026-08-23)

**10,000 price points per week, per account, rolling.** One budget shared by
three consumers: `candle_stream` warm-up/backfill (the live path),
`engine.fetch_candles` (backtests), and — until 2026-08-23 —
`scripts/collect_candles.py`.

### The collector is off. Do NOT re-enable it in its old form.

| | |
|---|---|
| `/app/logs/candles.log` | **222 lines, 222 quota errors, ZERO successes**, whole life of the 2026-08-22 image |
| `/app/scripts/candle_cache/` | **did not exist in the container** — never created, so there was no output to lose |
| its budget | 3 symbols x `FETCH_COUNT` 50 x 96 runs/day = **14,400/day = 100,800/week** = **10.08x** the allowance |
| exhaustion | **~16.7 hours**, then zero for the rest of the week |
| waste | 50 candles requested every 15 min to gain 1 — **~98%** |

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

### 🔭 TWO UNKNOWNS — measure after the allowance resets, before planning backfill

Both were untestable on 2026-08-23: `numpoints=1` on three separate epics was
refused outright.

1. **Max `numpoints` per request** on `/prices/{epic}/{resolution}/{numpoints}`.
2. **How far back `MINUTE_15` reaches per epic.** The whole index-backfill plan
   (~17,000 points per index symbol for a 10-month walk-forward span, ~51,000
   for all three ≈ 5 weeks of full allowance) is a **guess** until this exists.

### Related, recorded not fixed

`_rest_fetch`'s fallback is **asymmetric**: quota exhaustion raises
`_QuotaExceeded` and gets yfinance; empty prices or an unresolved `ig_scale`
return `None` and get **nothing**. On the 2026-08-22 restart that left US500
15MIN+HOUR, US100 15MIN and USDCAD 15MIN with empty buffers and no fallback
attempted (`warm-up got nothing ... source=IG REST`). Gap-backfill covered it
minutes later, by luck.

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


## Monitoring Gaps (outstanding)

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
- **`correlation_events` is still write-only** — 3,824 rows, but they are
  per-cycle re-logs of a *standing state*, not distinct events (~130 episodes).
  Consumer proposed, not built.
- **26 dangling Docker images on the VPS** as of 2026-08-22 (was recorded as 51
  on 2026-08-15; the count is lower now, and nothing in this repo records a
  prune between those dates — so either one happened undocumented or the
  earlier figure was miscounted. Do not treat the trend as reassuring). Not
  pruned. Precedent exists (Jun 27 prune). With `/home/ubuntu/backups` at
  1.7 GB and 29 GB free, disk is not pressing — check before the next rebuild.

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