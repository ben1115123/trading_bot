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

## 🧭 ROUTING RULE — WHERE A LINE GOES WHEN IT IS WRITTEN

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
> "later".** "Later" is what produced a 204,000-char file.

### The five categories

| what the block is | where it goes |
|---|---|
| 1. **Standing fact / current state** — true until something changes it | **CLAUDE.md** |
| 2. **Dated observation** — a check result, a deploy record, a rehearsal | **archive** + stub |
| 3. **Rule learned from an incident** — a lesson, not an event | **CLAUDE.md**, Unverified Controls |
| 4. **MEASUREMENT that a future decision reads** | **the NUMBER stays in CLAUDE.md; the RUN goes to the archive** |
| 5. **Correction to a claim that appears in CLAUDE.md** | **CLAUDE.md, next to the claim. Never the archive.** |

**Category 4 is the one most easily mis-routed**, because a measurement looks
exactly like a dated observation — it has a date, a run, a method. The test is
what reads it: if a future decision consumes the *number*, the number is
current state and belongs here; only the *run* is history. The rollover-hour
and Sunday-reopen spread tables are the live example — they are the sole
evidence base for the entry policy and the only inputs the spread table will
ever have for those windows. Routing them as "dated observations" would archive
the only copy of data a pending decision needs.

**Category 5 is NON-NEGOTIABLE and is the reason this is a routing rule.**
An archived correction stops contradicting the error it corrects. Move it and
the wrong claim walks back in, because nothing at the point of use disagrees
with it any more. This file has been wrong about its own roster, its own
blocklist semantics and its own monitoring coverage; each was fixed by a
correction sitting next to the claim. **Anyone applying this rule as a size
rule will archive those first — they read as pure history — and will silently
undo the fixes.**

### The visible trigger

The rule needs to fire without anyone remembering it, so it has a textual
signal: **when a section grows a `### ✅ VERIFIED <date>` block, the
verification is finished.** Collapse the section to its standing conclusion and
move the result block out **in that same edit**. Four of the five largest
sections before the split were exactly that shape — verified, complete, and
still carrying their full working.

### Stubs

**A stub must say where the content went AND why it mattered.** A stub that
reads as an empty section invites the next reader to conclude nothing was
there — which is how a deliberate archive becomes an accidental deletion one
reader later.

**MOVE, NEVER DELETE.** Every line goes to its destination file *before* the
source is touched, and the move is verified by grepping the destination for a
distinctive string from the moved block. Conservation is checkable: a
line-level diff of substantive lines across all destination files should come
back at 100%. It did on 2026-09-02 — 2,635 lines, 0 lost.

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

### Phase-5 Sizing Reference — Monte Carlo Risk-of-Ruin
**Both the 2026-07-15 pre-parity table and its 2026-08-23 regeneration →
`docs/INCIDENT_HISTORY.md`.** The old rows are retained there, not deleted —
they are what the promotion decisions actually saw.

**The headline, which is the only thing anyone should carry:**

| | pre-parity table (2026-07-15) | **parity-v2, measured 2026-08-23** |
|---|---|---|
| risk of ruin at $10 on $500 | **5.58%** | **67.3% – 84.3%** |

**Every promotion decision that cited that table cited a number more than an
order of magnitude wrong.** The best parity-v2 cell is worse than the old
table's worst listed configuration. **Nothing may size off the pre-parity
rows.** The regenerated figures are `seed=42`, reproducible, stored on the row.

⚠️ **Neither table describes the account the bot runs on.** Demo Z67Y2C holds
~$19,542, so $10/trade is 0.05% — off the bottom of the table, ruin effectively
nil. **The demo cannot produce a ruin event, so demo survival is not evidence
that any sizing is safe.** Both tables are Phase-5 artifacts for a future live
return; neither governs anything running today.

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
`.env` `CANDLE_SOURCE=ig_stream`, all symbols. Justified by 2,845 cycles of
`candle_source_compare`: **indices genuinely stale off-session** on yfinance
(median real lag 6.5–11.5h, HOUR timeframe 0% timestamp agreement ever); FX
deltas real but small and ambiguous in direction, flipped anyway per explicit
instruction.

**Full record — the two same-day post-flip incidents, their root causes, and
the staleness guard → `docs/INCIDENT_HISTORY.md`.** Two things from it recur
and are why the record is kept:

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
— off-session yfinance staleness is the failure this flip existed to fix, so an
untrusted-stale source is worse than skipping.

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
| `trades.bak-20260904T020447Z.db` | Before the Stage 4 `profit_factor` schema change + parity-v3 import — taken on the HOST | 996 trades, 268,119 backtest_results, 182 walkforward_runs, 324,042,752 bytes, `integrity_check ok` |
| `trades.bak-20260904T022720Z.db` | `import_stage4.py`'s own rule-5 backup, immediately before the parity-v3 write. **Was written to the CONTAINER's ephemeral layer and rescued to the host afterwards** — see the backup-dir defect below | 996 trades, 268,119 backtest_results, 182 walkforward_runs, 324,042,752 bytes, `integrity_check ok` |

⚠️ **A THIRD backup, `trades.bak-20260904T022739Z.db` (325,763,072 bytes), was
taken by the idempotency re-run and DELETED rather than kept.** It is a
post-import snapshot, identical in content to the live DB at that moment, and
keeping a 325 MB file that duplicates current state is not a record of
anything. Noted here so its absence is deliberate rather than unexplained.

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

## Backtest Engine Parity — Stage 1 (2026-08-16)

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

**Retained here because it is the comparability key, not history:**
### engine_version — three versions, what each means
`engine_version.py` (repo root, zero imports). Versions the trade model's
**structure**. Bump only if two runs of the same strategy over the same candles
would produce different trades or different P&L. **Never commit SHAs.**

| version | meaning |
|---|---|
| `pre-parity-v0` | Everything before 2026-08-16. No take-profit for 21 of 34 strategies, $15 risk vs live $10, no SL floor, SL exits booked at a flat `-RISK`. **History, never evidence.** All 268,117 VPS rows and 276 local `walkforward_runs` rows carry this. |
| `parity-v1` | Sizing only. Floor applied, risk via `get_risk_per_trade`, clamp order matched to live, unsizeable trades aborted, SL booked from the actual stop price. **Half-fixed — still no TP. Generate no evidence at v1.** |
| `parity-v2` | The `sl_price`/`tp_price` contract. Still no spread realism: a flat dollar deduction at exit. |
| `parity-v3` | **Current, 2026-09-04.** Measured spread applied to PRICES at the crossed side — see below. |

### ✅ parity-v3 — measured spread, applied at the crossed side (2026-09-04)

**COMMIT 5, pass B.** `SPREAD_COSTS` and its flat per-round-trip dollar
deduction at exit are **deleted**. Spread now moves the prices:

- **entry** — a BUY fills at `close + half`, a SELL at `close - half`. The
  **fill**, not the mid, anchors `sl_price`/`tp_price` and `sl_dist`, as live
  does. This collapses TWO of parity-v2's listed divergences into one change:
  applying spread at entry **is** the offer/bid entry-price fix.
- **exit** — a LONG is closed by selling and is evaluated against **bid**
  (`candle - half`); a SHORT against **ask** (`candle + half`). Applies to the
  intrabar sl/tp ladder *and* to `session_close`/`max_hold`/`signal`.
- **unmeasured symbols RAISE.** `UnmeasuredSpreadError` for DAX, USDJPY,
  EURGBP, NZDUSD, XAUUSD, BTC. No fallback to the old constant — that would
  put two cost models inside one `engine_version`. Costs nothing: all 13
  rostered paper strategies are on the six measured symbols.

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
Walk-forward at parity-v3: median PF 1.0514, 66.7% windows, **MARGINAL**.

🔴 **THE SPREAD TABLE IS MEDIAN-ONLY AND ITS TAIL IS UNCALIBRATED.
RISK-OF-RUIN AND DRAWDOWN WORK MUST NOT USE IT.**

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

⛔ **THE MIGRATION HAS NOT REACHED THE VPS.** It runs from `init_db()` at
container start and nothing has been deployed. The VPS `backtest_results`
still has no `profit_factor` column — verified 2026-09-04 by `PRAGMA
table_info`. **The Stage 4 import will need it there first**, since
`backtest_trades` does not cross (gotcha 5) and an imported row would land
with no PF and nothing to derive one from.


## Engine parity work — caveats to carry forward (2026-08-16)

Two caveats, both still live; full text → `docs/OPERATIONS_LOG.md`.

1. **The 36/36 contract result is NOT full coverage.** `orb` and
   `first_bar_breakout` produced ZERO signals on the test candles, so they are
   contract-**untested**, not contract-clean. The first run that makes them fire
   is the first test of their compliance.
2. **`score_strategies()` returning `[]` is AMBIGUOUS.** After a version bump
   there are zero rows at the current version until the gauntlet is
   regenerated, so "no candidates" and "selector working but idle" look
   identical — both are silence. **Before re-arming the selector, make the two
   states distinguishable by a positive signal.** Harmless today only because
   the selector is inert at both layers.

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

## ✅ CHECK 2 — 21:00 UTC rollover gate (deployed 2026-08-21) — VERIFIED IN FULL 2026-08-24

**PASSED, all six criteria, Mon 2026-08-24 21:00–21:59 UTC.** The gate refuses
entries in the 21:00 UTC hour on **all instruments**, checked before the
`_ALWAYS_OPEN` short-circuit so BTC is covered. Rationale and the
DAX/BTC-are-mechanism-not-evidence caveat live in the `market_hours.py`
comment.

**Full result block, all six criteria, the 2026-08-23 Sunday correction, and
the "what Monday still tests" scoping → `docs/OPERATIONS_LOG.md`.** That
material matters and is not filler: it contains the correction proving this
file's own prediction table was wrong — the rollover branch wins the ordering
in `_block_reason`, and the gate had **already fired on a real clock** a day
before this file said it was reachable. It also carries the criterion-1
exact-string test that would catch an ordering drift.

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

> 🔴 **THE "12 OF 13" FIGURE IN THIS SECTION'S HEADING WAS WRONG, and it was
> wrong in the direction that makes a correct run look anomalous.** The roster
> holds **five** `williams_r` paper rows (ids 6 US500 HOUR, 22 EURUSD, 32
> GBPUSD, 34 AUDUSD, 36 USDCAD), not one — so five get a real 84-cell
> stability map and the correct expectation is **8 of 13 reduced**, or **6 of
> 11** with ids 29/30 held on the ETF blocker. Measured 2026-09-04: exactly
> **6 REDUCED_GAUNTLET and 5 × 84-cell maps (426 stability rows)**.
> A pre-registered check is only as good as its arithmetic; this one counted
> strategies rather than roster rows.

The standing plan was **build 2 grids, mark 4**. Against the current roster that
now reads: **build one more — `stoch_rsi` and `supertrend` — and accept the rest
as reduced.** Those two are the ones with live or recently-live history worth a
stability contour; the remainder are paper-only and a marker is an honest record
of what was not run.

**Write this down before the run, not after.** A batch that returns 12 reduced
verdicts is either "exactly as planned" or "something is badly wrong", and those
two look identical in the output. This entry is what makes it the first one.

## ✅ STAGE 4 COMPLETE — 10 of 13 re-validated on parity-v3, 2026-09-04

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

**Thirteen rows near 1.0 will otherwise read as a ranking.** That is the
specific misreading this entry exists to pre-empt — it is the same shape as
the pre-parity scores that promoted `US100 HOUR supertrend` unreviewed, where
an ordering was treated as evidence because it was the only thing on the
screen.

What WOULD change this: a smaller residual (index-scale 15MIN candles from a
single source, or a cache-vs-IG level correction), or a strategy whose PF is
far enough from 1.0 that a ~1-pip-per-bar noise term cannot explain it. Neither
is in this batch.

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

### 📏 THE TABLE — measured, frozen, hashed. PRICE units.

⚠️ **PRICE units, not pips.** EURUSD `0.00006` is **0.6 pips**, not 6. Several
tables in this file quote pips for readability and the model being replaced is
wrong in units, so both are given. Do not carry one column into code meant for
the other.

| symbol | median (PRICE) | readable | n |
|---|---|---|---|
| EURUSD | **0.00006** | 0.60 pips | 917 |
| GBPUSD | **0.00009** | 0.90 pips | 908 |
| AUDUSD | **0.00006** | 0.60 pips | 907 |
| USDCAD | **0.00013** | 1.30 pips | 896 |
| US500 | **0.6** | 0.60 index points | 1074 |
| US100 | **2.0** | 2.00 index points | 906 |

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

### 🔭 TWO UNKNOWNS — STILL UNMEASURED. Probe from the SMALLEST request upward.

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
Two recorded; full accounts → `docs/OPERATIONS_LOG.md`.

- **2026-08-15** selector-disable deploy (`9e5f21a`), verified by marker test.
- **2026-07-02** a stale `tradingbot.service` had been running since Apr 12
  **alongside** the Docker container — same IG account, same DB — firing live
  trades on 3-month-old code, undetected. **This is why the policy is
  Docker-only, no systemd**, and why `watchdog.py` checks for a duplicate
  uvicorn process outside the container's own tree.

⚠️ The 2026-08-15 record lists the open positions at that moment. **The roster
churns — never carry a hardcoded position list forward.**

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
Phases 1A–6 complete (database, dashboard, Docker/nginx on VPS, trade logging,
positions poller, backtesting engine, 11 strategies, strategy selector, daily
automation). Per-phase detail → `docs/OPERATIONS_LOG.md`. Current phase and
what remains in it are below.

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