# Trading Bot — CLAUDE.md

## Project Overview
Webhook-driven algorithmic trading bot. Pipeline:
TradingView alert → webhook → Python bot → IG Markets API.
Current focus: Phase 7 — Risk Management & Stability.
Forward development plan: see ROADMAP.md

### ⚠️ Read this before trusting any performance figure in this file

`docs/SESSION_20260812_FINDINGS.md` is the authoritative record of 13 defects
from the 2026-08-12 audit. Original text → `docs/OPERATIONS_LOG.md`.

**Status as of 2026-09-04 — the original said "nothing in it is fixed", which is
no longer true:**

| finding | state |
|---|---|
| 1 + 12 engine parity (no TP for 21 of 34 strategies, $15 vs live $10) | ✅ **FIXED** — `parity-v2` contract, `parity-v3` spread |
| 4 `status` fail-open default | ⚠️ **OPEN** — unrecognised status still falls through to LIVE |
| 2 paper resolver as a second synthetic model | ⚠️ OPEN |
| 5 first-activation with no score threshold | ⚠️ OPEN — selector inert at two layers, which is what makes it safe |
| 11 local-vs-VPS corpus split | ⚠️ OPEN — the Stage 4 import is what keeps it from becoming permanent |
| 13 backtest provenance across the roster | ⚠️ OPEN |

🔴 **Consequences that still apply to this whole file:**
- **Any score, PF or walk-forward verdict NOT stamped `parity-v3` is history,
  not evidence. Do not promote on one.**
- Re-running the gauntlet is **regeneration, not reproduction** — for
  walk-forward there is no persisted pre-fix artifact to diff against
  (finding 7).
- The roster's live-row counts in the original warning are void: **there are
  now ZERO live rows.**

## ⚠️ SIZE — the limit is 150,000 chars. KNOWN, not guessed.

**Observed 2026-09-04:** the tooling reports the CLAUDE.md ingestion limit as
**150,000 characters**. The previous version of this section said the cliff
"remains UNKNOWN" and "cannot be read from inside a session"; **that is
resolved** and the archived text → `docs/OPERATIONS_LOG.md`.

**This file has now been split TWICE, and the second split is the more
instructive one.**

| | 2026-09-02 split | **2026-09-04 cleanup** |
|---|---|---|
| CLAUDE.md before | 204,375 | **214,025** |
| **CLAUDE.md after** | 145,553 | **119,526** |
| headroom against 150,000 | 4,447 | **~30,400** |
| `docs/OPERATIONS_LOG.md` | 58,572 | 289,540 |
| `docs/INCIDENT_HISTORY.md` | 35,780 | 70,379 |
| back over the limit | **in two days** | — |

⚠️ **The archive is now larger than CLAUDE.md by more than 2:1, and that is the
design working, not a problem** — the archives are read on demand, CLAUDE.md is
read every session. But `docs/OPERATIONS_LOG.md` is approaching the size
CLAUDE.md was when it first became unmanageable. **When it needs splitting,
split it by YEAR or by KIND, and never back into CLAUDE.md.**

🔴 **THE 09-02 SPLIT LANDED AT 145,553 AND WAS OVER 150,000 AGAIN WITHIN TWO
DAYS.** It obeyed the routing rule perfectly — CLAUDE.md +1,211 lines and
`OPERATIONS_LOG.md` +1,103 lines over the same window, so lines *were* being
routed. **The archive doubled and the file still grew.** Two causes, and both
now have a rule in the ROUTING RULE section below:

1. **The routing rule routes by KIND, not SIZE.** A section can be entirely
   standing fact and still be 29,000 chars. Obeying it perfectly does not bound
   the file. → **rule (b), HEADS HAVE A SIZE CEILING.**
2. **There was a BIRTH POLICY AND NO DEATH POLICY.** The rule said where a line
   goes when written and nothing said what happens when a line stops being
   true. `## STAGE 4 (TWELVE DATA) — SUPERSEDED` sat in the current-state file
   at **18,847 chars, correctly labelled and never moved.** → **rule (a),
   SUPERSESSION IS A MOVE, NOT A LABEL.**

**Leaving no headroom is what produced the second split.** Target **120,000**,
not 149,000.

Nothing was deleted in either split. Conservation is checkable and was checked
both times.

## 🧭 ROUTING RULE — WHERE A LINE GOES WHEN IT IS WRITTEN

**This is a ROUTING rule, not a size rule.** A size rule says "this file is too
long, remove something", and the obvious way to satisfy it is to **delete**.
**This rule never says delete.** Each line has ONE correct home, decided when
the line is written; the file stays small as a *consequence*.
Longer statement → `docs/OPERATIONS_LOG.md`.

> **Operational sections carry a CURRENT-STATE head. Dated detail goes to the
> archive AT WRITE TIME, with its stub written in the SAME EDIT — never
> "later".** "Later" is what produced a 204,000-char file.
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

### 🔴 RULE (a) — SUPERSESSION IS A MOVE, NOT A LABEL

> **Writing "SUPERSEDED", "stale", "obsolete", "VOID" or "no longer true" on a
> section IS THE TRIGGER TO ARCHIVE IT — in the SAME EDIT that adds the label.**
> The label is not the work. It is the decision that the work is due.

**A section titled SUPERSEDED that still occupies the current-state file is
this rule's absence, and there is a worked example of exactly that in this
cleanup:** `## ✅ STAGE 4 (TWELVE DATA) — … — SUPERSEDED` sat here at **18,847
chars** — correctly labelled by a careful author, honestly warning the reader
not to trust it, and **never moved.** It was the single largest block in the
file after Unverified Controls.

**Why the label alone feels sufficient, and why it is not:** labelling
discharges the *honesty* obligation — no reader will be misled — so the job
feels done. **It does not discharge the SPACE obligation, and nothing was
tracking that.** Four more turned up the same way in this cleanup.

**The stub carries the STANDING conclusion** — what is true now, and what the
superseded thing is still good for. Retain the reasoning, not the results.

⚠️ **Category 5 is the exception and it does not bend.** A CORRECTION to a
claim that appears in CLAUDE.md stays next to the claim, forever, however dated
it reads. Superseding a *claim* archives the claim; it never archives the
correction.

### 🔴 RULE (b) — HEADS HAVE A SIZE CEILING: 7,000 CHARS

> **A current-state head may not exceed 7,000 characters. When it does, the
> WORKED DETAIL archives and the HEAD KEEPS THE CLAIM.**

**7,000 is MEASURED, not picked.** The first draft said 6,000 — and **four
sections were over it the moment it was written, including this one.** A
ceiling breached on day one is an unenforceable criterion (see CRITERIA AGE
AGAINST THE SYSTEM THEY MEASURE). 7,000 is what the file actually holds, so a
breach means something changed.

**Routing by kind alone does not bound a file. This is what does.** The
2026-09-02 split obeyed the routing rule perfectly and was back over the limit
in two days, because **a section can be 100% standing fact and still be 29,000
chars.**

**Measure the head, not the topic:**

```
awk '/^## /{if(h!="")printf "%6d  %s\n",c,h; h=$0; c=length($0)+1; next}
     {if(h!="")c+=length($0)+1} END{if(h!="")printf "%6d  %s\n",c,h}' CLAUDE.md |
  sort -rn | head
```

**The split is by *function*, not importance, and the valuable half stays:**

| stays in the head | goes to the archive |
|---|---|
| the rule, the verdict, the number a decision reads | the narrative of how it was learned |
| what to do, and what NOT to do | the run that produced it, per-symbol tables, enumerations |
| the correction to a claim stated here | the claim it corrected |
| a pointer naming the archive AND why it mattered | everything else |

**Unverified Controls is the worked example.** At 29,014 chars it was the most
valuable content in the file and 13.6% of it. Split by kind: **ten rules stayed
as a table; eleven dated instances moved.** The rule family table stayed intact
— **an index is standing by definition.**

⚠️ **A head at the ceiling is a prompt to RE-READ it, not only to cut it.**
Three of the stale sections in this cleanup were found *because* their size
forced a look. Size is a proxy for "nobody has audited this lately."

✅ **Zero sections over it as of 2026-09-04**; the largest are this one, IG
Historical Allowance and Unverified Controls. **Run the command above before
adding to any of them.**

## Architecture
```
main.py                      FastAPI entry point
webhook/receiver.py          POST /webhook — alert parser. Friday pre-weekend
                             block; $75 daily loss limit. DORMANT (swiftalgo retired)
bot/execute_trade.py         ⚠️ REQUIRES PERMISSION TO MODIFY. Trade logic,
                             session, execution. Cooldown is PER-SYMBOL
bot/live_signal_loop.py      Unified signal loop (HOUR + 5MIN). Wakes every 5min,
                             timeframe-aware. Paper via PAPER_TRADE_SYMBOLS OR
                             active_strategy.status='paper'. ATR SL/TP,
                             candles[-2] dedup, key (symbol,timeframe,strategy).
                             Weekend auto-close Fri 20:40 UTC. Heartbeat upsert
                             at the end of EVERY cycle
bot/notifier.py              send_telegram() — see Alerting
bot/candle_stream.py         Lightstreamer ticks + REST warm-up/gap backfill
scripts/watchdog.py          HOST cron — heartbeats, duplicate proc, container,
                             candle divergence
scripts/daily_summary.py     HOST cron 23:00 UTC
risk_manager.py              Lot size ($10 fixed risk) — see Risk Management
risk/daily_loss.py           $75 per (symbol, strategy_name)
risk/concurrent_positions.py cap=1, signal_loop live path only
risk/spread_gate.py          SHADOW ONLY (ENFORCE=False)
ig_env.py                    get_ig_credentials() — DEMO/LIVE switch
ig_scale.py                  Price scale + deal currency per epic — see Broker
ig_allowance.py              Parses IG's allowance block; reports, never throttles
engine_version.py            CURRENT_ENGINE_VERSION — zero imports
spread_model.py              MEASURED_SPREADS_2026_09 + sha — zero imports
symbols.py                   The ONE symbol list (a second hardcoded list once
                             cost USDCAD 7 days of no trades)
market_hours.py              is_market_open (venue fact) vs is_entry_allowed (our
                             policy) — the 21:00 rollover gate lives here
filters/rule_filters.py      Trend filter (DISABLED — Pine Script filters upstream)
filters/vix_filter.py        Blocks swing entries >= 18. FAILS OPEN. Once per cycle
filters/webhook_filters.py   Session / spread / macro. ⛔ the spread filter is
                             DEAD — see SwiftAlgo Webhook Filters
data/positions_poller.py     Polls IG every 30s. _verify_closed_on_ig() before ANY
                             close. Columns are dealId/epic/direction. Deferred
                             P&L checker (5min, 24h window)
database/db.py               SQLite connection/setup
database/models.py           ALL table schemas + queries — every DB call goes here
database/paper_filters.py    paper_where() — the SINGLE definition of "a countable
                             paper row" (real vs shadow, resolver model). The old
                             get_paper_trades/_stats helpers were DELETED
                             2026-08-16: zero callers, and dead code that looked
                             like the canonical read path
dashboard/app.py             Streamlit entry
dashboard/pages/01..08       overview / trade_log / calendar / backtest /
                             positions / sync / performance / paper
backend/strategies/          34 registered (base, rsi, supertrend, vwap_ema,
                             ema_ribbon, bb_squeeze, rsi_divergence, orb,
                             ichimoku, keltner, stoch_rsi, ema_cross_volume,
                             vwap_mean_reversion, connors_rsi2, williams_r,
                             macd_rsi, ema_pullback, ny_session_momentum, …)
backend/backtesting/         engine.py, metrics.py. Contract enforced since
                             parity-v2; spread applied at the crossed side
                             since parity-v3
scripts/run_backtest.py      CLI runner. Mode flags do NOT combine — it refuses
scripts/run_daily.py         ⛔ 06:00 cron DISABLED 2026-08-15
scripts/select_strategy.py   ⛔ INERT at two layers — see Selector Disabled
scripts/score_strategies.py  Raises MixedEngineVersionError across models
scripts/import_stage4.py     Off-host result import — six refusal rules
scripts/export_roster.py     Roster snapshot + provenance. RUN ON THE VPS HOST
scripts/fetch_dukascopy.py   Local corpus builder (not in requirements.txt)
scripts/resolve_webhook_outcomes.py   Stage E — the ONLY active cron line, 06:10
scripts/sync_ig_trades.py    IG trade sync, self-contained session
scripts/backfill_pnl.py      Backfill missing P&L
```

*(This tree carried a `utils/telegram_alert.py` entry whose only content was a
note saying the file does not exist, and an `engine.py violates its own signal
contract` warning that parity-v2 fixed. Both archived →
`docs/OPERATIONS_LOG.md`.)*

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

⚠️ **Ports 8000/8501 are NOT published to the host** — only nginx maps
`0.0.0.0:80->80`. Curling them returns `000` **on a completely healthy stack**,
which is what the runbook told people to do until 2026-08-21. Account →
`docs/OPERATIONS_LOG.md`.
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

### Layer 1 — `bot/notifier.py`

`send_telegram(message, level="INFO"|"WARN"|"ERROR") -> bool`. urllib, no new
deps. **Never raises** — returns False on any failure and prints locally. **5s
HTTP timeout, so a slow Telegram API can never block a trading cycle.** Rate
limit 20/60s; over cap the message is dropped and the count is appended to the
next one that sends. Detail → `docs/OPERATIONS_LOG.md`.

⚠️ **🔴 ERROR is reserved exclusively for SYSTEM problems.** A CLOSED trade
always uses `level="INFO"` with the win/loss emoji in the message text — a
losing trade is not an error.

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

`heartbeat` table (name PK) — signal_loop upserts `name='signal_loop'` at the
end of **every** cycle regardless of how many strategies were due.

`scripts/watchdog.py` runs on the **HOST, not in the container** — the whole
point is surviving container death. Deliberately **stdlib-only, no project
imports**: it parses `.env` directly (host cron has no `TELEGRAM_*`) and reads
`trades.db` via `sqlite3`. Checks: stale `signal_loop`/`candle_stream`
heartbeats during market hours, a duplicate uvicorn process, container down,
and candle divergence.

⚠️ **Docker does NOT hide container processes from the host's process table.**
A plain `pgrep -cf "uvicorn main:app"` always counts the container's own
process, so the duplicate check cross-references matched PIDs against
`docker top` and only flags a PID **outside** the container's tree. **This
false-positived on its very first run** before the fix.

Anti-spam: `/tmp/watchdog_state.json`, at most one alert per condition per
60 min, **cleared on recovery** so a fresh occurrence alerts immediately. Every
alert sent is appended to `logs/watchdog_alerts.jsonl` (append-only history, not
a replacement for the dedup state). Host cron: watchdog every 10 min, summary at
23:00 UTC. Detail → `docs/OPERATIONS_LOG.md`.

### Layer 4 — `scripts/daily_summary.py`

One message at 23:00 UTC, **host cron** (it reads `watchdog_alerts.jsonl`, which
lives on the host). Stdlib-only. Covers trades opened/closed + net P&L + win/loss
per strategy over 24h, open positions, heartbeat status per name, and **watchdog
alerts fired in the last 24h — fired-and-cleared included**, not just conditions
still unresolved at summary time. Detail → `docs/OPERATIONS_LOG.md`.

⚠️ **It reports trades OPENED, so a dead signal source reads as a quiet day.**
That is how the swiftalgo silence went unnoticed for 29 days.

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

**Which symbols were actually armed by the first-activation branch, as of the
2026-08-13 deactivations → `docs/OPERATIONS_LOG.md`.**
**STRATEGY_BLOCKLIST is an ALLOWLIST BY OMISSION.** It blocks enumerated
`(symbol, timeframe, strategy_name)` tuples only — **any name not listed is
permitted.** This file previously claimed "all US100 strategies blocklisted
since 2026-06-12"; **that was false** — `("US100","HOUR","supertrend")` was
never in the set, which is how the 2026-06-16 promotion succeeded. **Only
`SYMBOL_BLOCKLIST` blocks a symbol.** Also latent: **10 of the 22 US100 tuples
are unreachable**, because `_select_for_symbol` filters to `timeframe ==
"HOUR"` before the blocklist check.

⚠️ **The armed-symbol analysis archived with this block described US500 HOUR as
carrying an `active` row (id 13 swiftalgo). That is no longer true** — ids 11
and 13 went `inactive` on 2026-09-04 and there are now **zero `active` rows**.
Both symbols are blocklisted regardless.

**Verification anchor after any rebuild:** committed `scripts/crontab` md5
**`0f1cc206193f5d30341c3db530357b06`**; in-container
`/etc/cron.d/trading-bot` must match **byte-for-byte** (`Dockerfile:18` is a
plain `cp`). Seeing the pre-fix `d7565feade7ac71356579e686b887a1b` means **a
rebuild reverted the disable**. Full md5 history → `docs/OPERATIONS_LOG.md`.

## Claude Code SSH Permissions
✅ SSH, run docker, git pull, check logs, restart containers
❌ Never modify .env / expose credentials / git push from VPS
❌ Never stop bot container without permission

## Broker — IG Markets
Library: trading_ig (IGService)
Session: auto-refresh every 10min, full recreate on 401

### Current mode: DEMO (switched 2026-07-08)
Account **DEMO (Z67Y2C)**; was LIVE (TW75S). Switched by `IG_ACC_TYPE`, read via
`ig_env.get_ig_credentials()`. ⚠️ **Default is LIVE if `IG_ACC_TYPE` is unset.**

**DEMO credentials are a separate login, not the same one** —
`IG_DEMO_USERNAME/PASSWORD/API_KEY` (they fall back to the LIVE user/pass if
absent, but this account has its own and needs them).

**Revert to LIVE:** set `IG_ACC_TYPE=LIVE` in `.env` → `docker-compose up -d`
(**NOT `restart`** — restart reuses the container and does not reload `.env`) →
verify with `docker logs trading_bot-bot-1 | grep "Switched to TW75S"`. Detail →
`docs/OPERATIONS_LOG.md`.

`execute_trade.py`'s hardcoded force-switch to TW75S runs **only** when
`IG_ACC_TYPE=LIVE`; in DEMO it logs whichever account the session lands on.
to switch to.

### Price scale quirk — `ig_scale.py`

> **⚠️ CURRENTLY INERT.** Every checked symbol classifies to **`divisor = 1.0`**
> on this account (measured 2026-08-18), so `to_decimal`/`to_native` multiply by
> one. **The scale has flipped at least TWICE** — decimal on LIVE, points on
> DEMO after 2026-07-08, decimal on DEMO now — and the last flip happened with
> **no account change: the broker changed representation under a running
> system.** The 2026-07-08 diagnosis and the boundary-conversion site list →
> `docs/INCIDENT_HISTORY.md`.
>
> **Do NOT delete `ig_scale` as dead weight.** Its value is the classification
> and the raise-on-ambiguity, never the arithmetic — it is the only thing that
> compares a price against what that price ought to look like.
> `init_price_scales(force=True)` on session recreate is load-bearing for
> exactly this reason.

**Standing rules that survive the layer being inert:**
- **Do NOT trust IG's `scalingFactor` field.** GBPUSD/AUDUSD carry
  `scalingFactor=10000` despite already being decimal; EURUSD — the one epic
  that needed /10000 — carried `scalingFactor=1`. Empirically disproven.
- **Scale differs by ACCOUNT, not just by epic.** Re-run
  `init_price_scales(..., force=True)` after ANY session recreate or account
  switch. Never assume scale carries over.
- **Ambiguous readings never guess** — they raise, alert, and block that symbol
  from trading until a human resolves it.
- All IG price reads/writes route through `to_decimal()`/`to_native()` at the
  boundary; everything else stays decimal.
- ⚠️ **The paper-trade path has NO `ig_scale` conversion at all.** That is the
  structural root of the id=824 corruption.

### Deal currency quirk — `ig_scale.get_currency_code()` (fixed 2026-07-25)

**Third per-instrument-assumption bug** (after `scalingFactor` and the REST
`snapshotTime` timezone bug). **IG instrument properties are NOT uniform across
epics — always derive per-epic, never hardcode one value for "all FX pairs."**

`create_open_position` had `currency_code="USD"` hardcoded. **USDCAD is the one
roster pair where USD is the base, not the quote**, so its `currencies` list
holds only `CAD` — and IG rejects the invalid param with an unclassified
`reason: 'UNKNOWN'`, not a structured code. **That was the root cause of
10/10 USDCAD live-trade rejections since its 2026-07-14 activation: zero USDCAD
trades were ever placed.** Write-up → `docs/INCIDENT_HISTORY.md`.

Fixed by caching deal currency per-epic alongside the price-scale map (same
lock, same lifecycle, one `fetch_market_by_epic` call). It falls back to `'USD'`
only if the lookup never resolved, **logged loudly**, so a wrong-currency order
is never sent silently.

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

### Live — ZERO instances. Nothing in this system trades live.

**`active_strategy` holds 18 `inactive` + 13 `paper` and NO `status='active'`
row** since 2026-09-04T10:20:58Z. The last two (ids 11 EURUSD and 13 US500,
both webhook `swiftalgo`, both demo Z67Y2C, `backtest_id` NULL on both) were
retired that day.

*(This heading read "Live — 2 instances, verified 2026-08-21" until the rows
were retired. The archived table → `docs/OPERATIONS_LOG.md`.)*

#### ⛔ SWIFTALGO IS RETIRED — the silence is a DECISION, not an outage

**The operator retired the TradingView source. The silence since 2026-08-05/06
is EXPECTED. DO NOT INVESTIGATE IT AS AN OUTAGE.** A future reader finding two
rows flipped on 2026-09-04 plus a month of silence will be tempted to, and
**`active_strategy` has no notes column** — this paragraph is the only place the
reason exists. Measurement (whole `webhook_log`, unfiltered: ~5.5 arrivals/day →
zero overnight, 29 days) → `docs/OPERATIONS_LOG.md`. Its shape is reusable:
**"rostered active" and "receiving alerts" are two different claims, and only
the first was ever checked.**

⚠️ **`inactive` was used deliberately; a value such as `retired` would have been
UNSAFE.** `webhook/receiver.py:265` is
`status = strategy_row.get("status", "active")`, and the only branches are
`inactive` (blocks) and `paper` — **anything unrecognised falls through to LIVE
EXECUTION** (finding 4's fail-open default).

**The receiver machinery is left DORMANT, deliberately** — harmless, costs
nothing, there if a source is ever wired up again. Removing it would mean
touching the execution path.

**The measurement that converted the assumption into a fact → `docs/OPERATIONS_LOG.md`**
(whole `webhook_log` table, unfiltered: last arrival `2026-08-06T00:01:06Z`,
~5.5 arrivals/day → zero overnight, 29 days). Its shape is reusable: **"rostered
active" and "receiving alerts" are two different claims and only the first was
ever checked.**

### The four williams_r instances moved live → paper (2026-08-21)

ids **22 EURUSD**, **32 GBPUSD**, **34 AUDUSD**, **36 USDCAD**, all 15MIN, all
`status='paper'` since `2026-08-21T18:41:31Z`.

**Reasons are in `active_strategy_history` rows 43–46 — read those, not a
summary.** This file has been wrong about the roster before, so pointing at the
history table is deliberate. Headline: no profitable month pooled in three,
best bucket PF 0.86, `parity-v2` predicts PF < 1.0 on all four.

⚠️ **`paper`, not `inactive`, and the reason is operational:** the signal loop
iterates `status IN ('active','paper')`, and a symbol with **no runnable row
never reaches `_check_symbol`** — where the spread sample is taken, **before any
block check**. **AUDUSD and USDCAD have no other runnable row**, so `inactive`
would have taken their spread sampling and `candle_source_compare` to zero.
Detail → `docs/OPERATIONS_LOG.md`.
taken their spread sampling and `candle_source_compare` to zero.

**Params — authoritative, and divergent from the docs.** 4th occurrence of the
params-divergence class; **always pull params from `active_strategy`.**

| id | Symbol | Rostered params |
|----|--------|-----------------|
| 22 | EURUSD | `period=10, oversold=-90, overbought=-20` |
| 32 | GBPUSD | `period=21, oversold=-90, overbought=-20` |
| 34 | AUDUSD | `period=14, oversold=-85, overbought=-20` |
| 36 | USDCAD | `period=14, oversold=-85, overbought=-15` |

**Corrections to claims this table used to make → `docs/OPERATIONS_LOG.md`** —
they matter because the AUDUSD ones are still cited elsewhere: the "robust
plateau" was **1 ROBUST cell of 84**, and the "walk-forward ROBUST, 83.3%
windows" figure **has no `walk_forward` row on any symbol** and is
unrecoverable.

### Paper
**13 `status='paper'` rows** (ids 6, 22, 23, 24, 25, 26, 28, 29, 30, 31, 32,
34, 36), verified on the VPS.

| Symbol | TF | Strategy | ids |
|---|---|---|---|
| US500 | HOUR | williams_r, stoch_rsi_confluence | 6, 31 |
| EURUSD | 15MIN | stoch_rsi, bb_squeeze, supertrend, ny_session_momentum, williams_r | 23, 24, 25, 28, 22 |
| GBPUSD | 15MIN | ema_pullback, williams_r | 26, 32 |
| US500 / US100 | 15MIN | ema_pullback | 29, 30 |
| AUDUSD / USDCAD | 15MIN | williams_r | 34, 36 |

⛔ **The per-row backtest figures this table used to carry (PF 1.36, PF 2.18,
PF 2.00, PF 3.17 …) are ARCHIVED → `docs/OPERATIONS_LOG.md` and NONE of them
is current evidence.** They were pre-parity, several were measured on
ETF-scaled candles, and **all of them were superseded by the Stage 4 Dukascopy
re-run, whose rankings did not correlate with theirs (tau +0.067).** Read the
Stage 4 re-run table instead; it is the only set produced by the engine that
now runs.

⚠️ **id 28 `ny_session_momentum` cannot be backtested at all** — wrong-side
take-profit, `EngineContractError` on both corpora.
**The −$2,453.93 / 32-trade figure was wrong wherever it appeared — it is ONE
corrupted row carrying 31 clean ones.** `paper_trades` **id=824** logged native
points-scale prices unconverted, so a 2.5-point `sl_distance` sized a lot that
**clamped up to the 0.1 floor** and booked **−$2,500.00**. Arithmetic →
`docs/INCIDENT_HISTORY.md`.

**Excluding id=824 the other 31 trades sum to `+$46.07`**; expectancy moves from
−$76.69 to **+$1.49/trade**. The record is mildly positive, not catastrophic —
it still fails promotion on PF and expectancy, but one bad row was
misrepresenting 31 clean ones. **id=824 is unique** across `paper_trades`
(1,447 rows) and `trades` (894). **Quarantine it, do not delete it — it is the
evidence.**

🔴 **Root cause is STRUCTURAL: the paper-trade path has no `ig_scale`
conversion at all.** It is not in the boundary-conversion site list.

⚠️ **5 more paper rows hit the OPPOSITE clamp** (sub-pip stops → lot 11–49
clamped down to 10), which under-risks those trades and **inflates Sharpe** —
one of the four R:R-adjusted promotion criteria. **Any `sl_distance` sanity
bound must reject at BOTH ends.**

## Deactivated Strategies (2026-05-27)
**Full inventory (13 rows from 2026-05-27 → 2026-06-12, plus the two 2026-08-13
deactivations) → `docs/OPERATIONS_LOG.md`.** The table is a record; the
**enforcement is `STRATEGY_BLOCKLIST` in `scripts/select_strategy.py`**, and
that is what actually prevents re-promotion.

**The two that still govern decisions:**

| id | Symbol | TF | Strategy | history | why it matters |
|----|--------|-----|----------|---------|---|
| 33 | US100 | HOUR | supertrend | **41** | Promoted 2026-06-16 by the **unconditional first-activation branch** — no score threshold, **zero paper trades, zero human review**, undocumented here for ~8 weeks. Evidence invalid: `supertrend` never emits `tp_price` |
| 2 | US500 | HOUR | stoch_rsi | **42** | Same invalid-evidence class; walk-forward was already FRAGILE. Live since 2026-04-29 |

**Neither is re-promotable** until the engine fix and a gauntlet regeneration —
both now done, but **on Dukascopy neither has been re-validated**.
`("US500","HOUR","stoch_rsi")` is in `STRATEGY_BLOCKLIST`; US100 is covered
symbol-wide.

**BTC: two consecutive failed strategies. No BTC strategies until a
crypto-specific volatility approach is designed and backtested.**
**DAX: all strategies failed. USDJPY: all failed.** Do not trade either.

## Instrument Notes
GBPUSD: mean reversion AND ema_pullback work (similar to EURUSD)
USDJPY: all strategies failed in old single-split tests — do not trade.
        Re-examined 2026-07-09 specifically for williams_r under
        walk-forward (see below) — still not promoted, but closest of
        the expansion batch to ROBUST.
DAX:    all strategies failed — do not trade

`STRATEGY_BLOCKLIST` in `scripts/select_strategy.py` prevents the daily cron
from re-promoting any of the above. To unblock: remove the tuple **and**
manually verify live performance warrants re-testing.

**The williams_r FX expansion batch (2026-07-09) → `docs/OPERATIONS_LOG.md`.**
Its conclusion is standing and is the reason it is kept: **williams_r's edge
does NOT generalize across FX pairs** — USDJPY FRAGILE, EURGBP and NZDUSD
REJECT, so AUDUSD's result stood alone rather than evidencing a portable signal
class. No roster changes came from it.

⚠️ **It also carries a correction worth remembering:** a follow-up claimed
EURGBP scored ROBUST (median PF 1.42, 92.3% windows). **That number came from
no run at all** — a reporting error, caught before any deploy.

**US100: all strategies blocklisted 2026-06-12** after `rsi_divergence` was
auto-promoted live by cron without review.

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
   **0 of 382 stored TradingView payloads have ever carried a `spread` key**, so
   `should_block_spread` short-circuits on its `None` fail-open guard before the
   threshold is consulted. All-time `spread_filter` blocks: **0**, against
   session_filter 150, day_of_week 27, daily_loss_limit 15. The threshold is
   **also ~5x too wide**, so fixing the constant alone would change nothing.
   **Live trades are NOT protected against spread blowouts and never have
   been.** Evidence → `docs/OPERATIONS_LOG.md`.
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

### Account Rebuild Mode (2026-07-02) — PAUSED, not deleted

Live-account scaling plan, **resumes if/when reverted to LIVE**: $100→$200 =
$3/trade, $200→$500 = $5, $500+ = $10. **Full $10 restored 2026-07-08 for DEMO
validation** — demo has no real capital, so the throttling and GBPUSD's
FRAGILE-verdict half-risk are **suspended, not deleted**. Re-apply on any LIVE
revert. Plan detail → `docs/OPERATIONS_LOG.md`.

### Per-Symbol Risk Overrides (`risk_manager.py RISK_PER_TRADE_OVERRIDE`)

**Every symbol is $10 right now** (EURUSD, GBPUSD, US500, USDCAD, AUDUSD and
the `All` default) — demo validation phase. They are separate knobs that
currently hold the same value; do not read the uniformity as a single
setting.

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
**Keyed per (symbol, strategy_name)** — each instance gets its own $75 budget,
not one combined pool. `risk/daily_loss.py::is_daily_loss_limit_breached`; call
sites `webhook/receiver.py` and `live_signal_loop.py::_risk_check`. Telegram
dedup is per-instance too. **Fixed because one FRAGILE instance's bad day was
blocking an unrelated instance that merely shared a `strategy_name`.**
| Source              | Limit         | Behaviour when hit                    |
|---------------------|---------------|----------------------------------------|
| signal_loop          | $75/instance | Stops firing new trades for that (symbol, strategy_name) only |
| tradingview_webhook  | $75/instance | Blocks incoming webhooks for that (symbol, strategy_name) only |

### Max Concurrent Positions Per Symbol (2026-07-25)

`risk/concurrent_positions.py` — **`MAX_CONCURRENT_PER_SYMBOL = 1`**, per
(symbol, strategy_name), **signal_loop live path only**. At the limit it skips
the signal and shadow-logs to `paper_trades`, logging
`BLOCKED_CONCURRENT_<signal>` to `signal_log`. Read from DB state, not a live IG
poll. **Webhook/swiftalgo path untouched.**

⚠️ **Race window not fully closed:** the count is read before `place_trade`'s own
IG round-trip, so a different-timeframe signal on the same (symbol,
strategy_name) landing mid-`place_trade()` could still stack past the limit.

**Rationale → `docs/OPERATIONS_LOG.md`.** Headline: concurrent same-symbol
`williams_r` stacking cost **−$219.63** against a first-entry-only counterfactual
across 32 episodes / 78 trades. **21 of 32 episodes were ALL_SL together —
correlated drawdown, not diversification** — and deeper price-averaging did not
correlate with better outcomes, so the "stronger snapback" thesis is
unsupported. The backtest engine models one position at a time; this aligns
live execution to that model.

⚠️ **The reconciliation clean-singles clock starts at this deploy** — it counts
only single-position trades placed after the fix, not the pre-cap history.

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
  (MYT+8), not UTC. Third instance of the class — ***any timestamp from an
  external source may be localized regardless of what the field name implies;
  force-convert, never relabel.*** Also hit `_normalize_yf_time` (yfinance
  intraday is exchange-local — a seasonal bug invisible in GMT months).
- **The comparison logger was only called from the yfinance-primary branch**,
  so flipping silently killed the exact dataset needed to verify the flip.
— off-session yfinance staleness is the failure this flip existed to fix, so an
untrusted-stale source is worse than skipping.

### Post-flip maintenance and the three 2026-07-20 production bugs

**Full accounts → `docs/INCIDENT_HISTORY.md`.** Four standing items:

1. **The SL DRIFT investigation was a NEGATIVE result.** Post-flip drift looked
   2–3x worse and **was not a regression**. Two structural, pre-existing causes:
   25–55 min decision-to-execution lag (`candles[-2]` dedup plus `_is_due`
   cadence), and a **measurement artifact** — stream candle close is mid, live
   fills at offer/bid, so every reanchor comparison injects ~half-spread of
   phantom drift. **Do not re-open this as a stream bug.** One item still
   DEFERRED: the mid-vs-dealing-price comparison fix, cosmetic, batch it with the
   next reanchor-logic review.
2. **Killed a bug class:** `candle_stream` had a second, independently-hardcoded
   symbol list (USDCAD never traded for 7 days). Both lists now import the shared
   `symbols.py`.
3. **Cross-symbol `close_price`/`pnl` contamination** — the poller's fallback
   matcher searched IG's entire multi-instrument history with **no symbol
   filter**. 8 rows corrected. ⚠️ **This file's earlier assumption that `pnl` was
   unaffected was WRONG** — `_fetch_close_data()` returns both from the same
   matched row. It read as "sane" only because every trade risks ~$10 at similar
   R:R. `scripts/reaudit_close_prices.py` is idempotent and read-only against IG
   — re-run it after any poller or `ig_scale` change.
4. **`_check_correlation_cluster()` is REPORT-ONLY, not a trading gate.** ⚠️
   **Direction is raw per-symbol BUY/SELL, not USD-exposure normalized.** USDCAD
   is USD-as-base while the other three are USD-as-quote, so a USDCAD SELL is not
   the same underlying bet. Fine for counting; **any future blocking logic built
   on this table MUST normalize to net USD exposure direction first.**

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

### Paper strategy design notes → `docs/INCIDENT_HISTORY.md`

Entry rules, parameters and baseline backtests for `williams_r`, `macd_rsi`,
`london_breakout`, `stoch_rsi_confluence`, `ny_session_momentum`,
`ema_pullback` and `fvg`. **Kept out of this file deliberately: params recorded
in docs have diverged from the live roster FOUR times.** The archive is design
intent; **`active_strategy` is what actually runs and is the only source any
analysis may use.** ⚠️ Two of those write-ups quote figures now VOID
(`ema_pullback` PF 1.57 / 3.17, ETF-scaled candles).

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

### The rules — each guards one way an observation can lie to you

**Every rule below was learned from a specific dated instance, and each
instance is a worked narrative → `docs/INCIDENT_HISTORY.md` (search the rule's
name).** The rules are here because they are standing; the stories are there
because they are dated. **Read the instance before arguing with a rule** — all
eleven were written by someone who already knew the rule and broke it anyway.

| # | rule | asks | guards against | instance |
|---|---|---|---|---|
| 1 | **marker test** | do not infer success from absence | a disable that never took effect | cron sentinel, 2026-08-12 17:11 |
| 2 | **self-invalidating probe** | could the probe observe the passing state? | reading a false negative off a working system | sampled after its own teardown (08-12); `docker exec` reading a buffer owned by another process (08-21) |
| 3 | **prospective form** | did I create the passing observation myself? | a restart manufacturing the artifact the check looks for | CHECK 1 — a rebuild re-warmed the buffer from a closed book (08-22) |
| 4 | **enumerate over assert** | can the check see anything it did not predict? | a criterion that can only confirm or deny itself | `GROUP BY hour, error` found the CHECK 2 ordering error (08-24) |
| 5 | **observation cost** | what does the observation COST if it fails? | destroying the resource you were measuring | ~7,200 IG points burned bracketing from above, both unknowns still unmeasured (08-25) |
| 6 | **non-separating branches** | can the branches tell the hypotheses apart? | a decision rule whose outcomes are equally consistent with both answers | the allowance-window test — both events sat in an expired window (09-02) |
| 7 | **artifact placement** | does the ARTIFACT exist where it will be needed? | a backup/export that reports success into a place the reader will never look | `import_stage4.py` wrote 650 MB to the container overlay (09-04) |
| 8 | **criteria age** | can the passing state still OCCUR? | a criterion made unsatisfiable by a control added after it | CHECK 1 criterion 4; the spread-gate hour-21 criterion |
| 9 | **duplicate observations** | is one row one observation? | a bias that CORRELATES with what you are measuring | `candle_source_compare` — anomalies duplicated ~13x vs 1.3x overall (09-04) |
| 10 | **the date banner is not a clock** | did both times come from real clocks? | an incident invented by the measuring instrument | 19h of "silence" that was 13 minutes of real data (09-03) |

#### The four rules that need saying in full, because a table cannot carry them

- **Rule 5 — a request that FAILS is not a request that was FREE.** Before
  probing a metered resource, state what the probe costs **if it fails**, and
  say how you know. If that is an inference rather than a measurement, start
  from the smallest informative request and read the meter off the first
  response before escalating.

- **Rule 6 has a mechanical form, and it needs one.** The rule was written into
  this file on the morning of 2026-09-02 and the *same author* built the same
  error into a rigour check that afternoon. **Knowing a rule does not apply
  it.** So: **for any check whose conclusion rests on an EMPTY result, write
  down the other ways that result could be empty — before running it.** If the
  list has more than one entry, the check needs another branch. (The check that
  proved this: `grep -rlF` returning nothing means "sole copy" *or* "string
  typed wrong". 2 of 23 verdicts were the second.)

- **Rule 9 — duplication BIASES, it does not merely inflate.** A constant
  inflation cancels out of a mean; this one does not, because **the multiplier
  correlates with the quantity measured** — a stalled buffer is re-read every
  cycle, so **the anomalies are duplicated ten times more than the ordinary
  bars.** It reversed two published conclusions, **both in the same direction**,
  so a reviewer sanity-checking the direction would have found it plausible.
  **Before computing any statistic from `signal_log` or
  `candle_source_compare`, dedup to one observation per (symbol, bar) and say
  which key you used** — `checked_at` and `stream_time` give different
  answers.
- **Rule 10 has a cheap standing fix:** `ssh … 'date -u'` settles it outright.
  Never date-check data against the session's own idea of the date.

#### The tell they share

**Nine of the ten attach a conclusion to an ABSENCE** — no rows, no charge on
the meter, no grep hit, no alert. **Absence is where this failure class lives.**
When your conclusion rests on something not being there, stop and run the
matching rule.

⚠️ **Rules 1–4 are also PROSPECTIVE:** do not restart, rebuild or redeploy in
the window before a dated control check, and before treating any criterion as
failed, confirm the current system still permits it to pass.

## engine_version marking (2026-08-16)

**Both `backtest_results` and `walkforward_runs` carry `engine_version TEXT NOT
NULL`.** The constant lives in `engine_version.py` (repo root, zero imports).
**The three-version table and the bump rule live with the parity section** —
one copy, because it is the comparability key. Original prose →
`docs/OPERATIONS_LOG.md`.

- `get_backtest_results()` filters to `CURRENT_ENGINE_VERSION` by default.
  `engine_version=None` reads everything and is **archive/inspection only**
  (dashboard page 04 passes it deliberately). **Never pass `None` from anything
  feeding a promotion decision.**
- `score_strategies()` raises `MixedEngineVersionError` rather than ranking
  across models — defence in depth, reachable only if a caller defeats the
  filter, which is exactly the case worth catching.

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

## ✅ DUKASCOPY MEASURED 2026-09-04 — a corpus that fixes BOTH open data defects

Client: **`dukascopy-python` 4.0.1**, pip-installed to a scratchpad `--target`
dir; `requirements.txt` untouched. *(This head read "Measurement only — nothing
built, nothing cached, nothing wired in" for a few hours on 2026-09-04.)*

### It clears the index blocker, and the corpus is complete

**US500/US100/DAX all classify to INDEX scale** by price level against the IG
2026-08-23 snapshots (1.000x / 1.002x / 1.005x) — **indices, not ETF proxies**.
Checked by level, exactly as the blocker demands; **the name never proved
anything and still doesn't.**

**Depth: ~49,800 M15 bars per FX pair and ~45,600 per index, 24.0 months**,
against a walk-forward requirement of ~10. **104 weekend gaps over two years is
exactly 52/year** — the series is complete, not thinned; every other gap is
Christmas or New Year. Tables → `docs/OPERATIONS_LOG.md`.

### 🔴 Source comparison — on UNIQUE OBSERVATIONS, not rows

**The unit is one observation per `(symbol, stream_time)`.** `candle_source_compare`
logs once per strategy CHECK, so rows over-count by 1.29–1.35x. **Deduplicated,
Dukascopy wins every metric on every symbol**, including stdev — the one column
Twelve Data won on the row basis. **All four Dukascopy means land within ±0.08
pips of zero.** Tables → `docs/OPERATIONS_LOG.md`.

🔴 **Dukascopy's stdev HALVES on dedup; Twelve Data's barely moves.** The
repeatedly-observed bars were precisely the divergent ones; Twelve Data is
*uniformly* displaced, so dedup barely touches it.

⚠️ **All four means sit at −0.055 to −0.057 — identical to three decimals across
four instruments.** Not a vendor offset; a constant sub-tick or rounding artifact
in one pipeline. Too uniform to be coincidence, ignorable until someone chases
the last tenth of a pip.

### 📏 THE ENTRY-ALLOWED NOISE FLOOR — the interpretation bar for Stage 4

Unique observations, `market_hours.is_entry_allowed` hours only, Dukascopy mid
vs IG stream mid. **This is the number a Stage 4 pre-registration must carry.**

| symbol | n | mean | **stdev** | IQR | p90 abs | >1 pip | spread | **stdev/spread** |
|---|---|---|---|---|---|---|---|---|
| EURUSD | 3,689 | −0.057 | **0.607** | 0.40 | 0.35 | 1.1% | 0.60 | **1.01** |
| GBPUSD | 3,745 | −0.056 | **0.524** | 0.60 | 0.50 | 1.3% | 0.90 | **0.58** |
| AUDUSD | 3,081 | −0.056 | **0.459** | 0.40 | 0.35 | 0.9% | 0.60 | **0.77** |
| USDCAD | 2,556 | −0.055 | **0.596** | 0.90 | 0.80 | 4.0% | 1.30 | **0.46** |

Pooled: **0.547 pips of noise against 0.850 pips of modelled spread = 64%.**

**The two effects behave DIFFERENTLY:** **per-bar trigger evaluation IS
affected** and does not average away; **aggregate PF / net / win rate is NOT**,
because the mean is ±0.06 pips. **That is the material difference from Twelve
Data, whose +3.2 pip EURUSD mean was a BIAS that never averaged down at any
trade count.**

> **THE BAR: an edge smaller than ~0.5–0.6 pips per bar cannot be distinguished
> from corpus error.**

⚠️ **All four means land at −0.055 to −0.057 pips — identical to three decimals
across four instruments.** Not a per-symbol vendor offset; it looks like a
constant sub-tick or rounding artifact in one of the two pipelines. Too uniform
to be coincidence, small enough to ignore until someone chases the last tenth of
a pip.

### ✅ THE TAIL IS RESOLVED — non-traded hours plus single-bar artifacts

**Verdict: CONFINED TO NON-TRADED HOURS, remainder single-bar artifacts. Not a
Dukascopy defect. NO CLEANING STEP — every bar is kept.** Four lines of evidence
(hour-of-day, cross-symbol coincidence, persistence, our own reconnect gaps) →
`docs/OPERATIONS_LOG.md`.

🔴 **The ">3 pips on 5–7% of bars" figure was RAW-ROW based and is wrong — the
true rate is 0.4–0.8%.** The tail bars were duplicated **13.3x** against 1.30x
for the data as a whole. Rule 9's worked instance.

**GBPUSD's caveat is answered and REVERSES:** 84% of its tail bars fall in hours
the bot cannot enter; restricted to `is_entry_allowed` hours its stdev is
**0.419 vs Twelve Data's 1.035 — ~2.5x tighter on the hours that matter.**

**Why no cleaning:** the comparison is symmetric and **cannot say which feed is
wrong**, so removing spikes would be editing raw market data on a guess. And
`is_entry_allowed` governs ENTRIES, not candle availability — a backtest needs
continuous bars to evaluate holds across excluded hours.

### 📦 THE CORPUS — 12 `*_DUKA.json` caches, built 2026-09-04

`scripts/fetch_dukascopy.py` (local batch tool, **not** in `requirements.txt` —
same status as `fetch_twelvedata.py`; the container has no use for it and
`Dockerfile:11 COPY . .` would bake it into every layer).

**`{SYMBOL}_{TF}_DUKA.json` + a `.provenance.json` sidecar** carrying source,
client version, **the exact instrument constant**, date range, bar count, the
mid construction, and the level-check result. **~49,800 M15 bars per FX pair,
~45,600 per index, plus HOUR for all six; 24 months.** Per-file table →
`docs/OPERATIONS_LOG.md`.

**Level check re-run on the FILES AS WRITTEN** — the script refuses to write on
failure. **US500 1.010x, US100 1.008x. These are indices.** **Additive only,
proven:** md5 of all 24 pre-existing caches before and after — **0 mismatches,
0 missing**, so `cache_file` provenance on already-imported rows stays intact.
Refuses to overwrite without `--force`.

✅ **These files ARE consumed.** `run_backtest.py` has a `--source dukascopy`
choice and the Stage 4 batch ran on it. *(This section read "Nothing consumes
these files yet — no `--source dukascopy` branch exists" until 2026-09-04; it
was true for a few hours.)*

⚠️ **DAX was NOT pulled** — no DAX row in the roster. Its instrument is in the
script and measured good at 1.005x, so it is one command away.

## ⛔ Twelve Data `*_15MIN_AV.json` index caches are ETF prices — CONTAINED

`fetch_twelvedata.py`'s `SYMBOL_MAP` routes `US500->SPY`, `US100->QQQ`,
`DAX->EWG` — **ETFs, not indices**, because those are what the free tier
permits (`SPX`/`NDX` need a paid plan; `DAX` there is a $47 NASDAQ ETF).
**Do not "just fix the mapping" — it cannot be fixed at this tier.** All 7 FX
entries are correct; the defect is per-FILE, and every `*_yf.json` is
correctly index-scaled.

**Marked, NOT deleted: 1,166 of 5,329 local `backtest_results` and 82 of 276
`walkforward_runs` are ETF-contaminated.** Safe only because all are
`pre-parity-v0` and `get_backtest_results()` filters to the current version —
**reachable via `engine_version=None`.** Identifying predicates →
`docs/OPERATIONS_LOG.md`. `backtest_results` has **no cache-provenance column**,
so its count is inferred from `candles_total` (finding 31).

⛔ **The `ema_pullback` figures produced on these files — US500 15MIN PF 1.57,
US100 15MIN PF 3.17 — are VOID**, not merely pre-parity.

✅ **THE BLOCKER ON ids 29/30 IS LIFTED (2026-09-04).** Dukascopy serves both
at true index scale (`US500_15MIN_DUKA.json` 7751.40 vs IG 7671 = 1.010x;
`US100_15MIN_DUKA.json` 29527.58 vs 29289 = 1.008x, level-checked in each
`.provenance.json`). Both ran in the Dukascopy Stage 4 batch. **`_AV.json` for
these three symbols must still never be used.**

**Standing rule, third instance of the class** (after DAX/EWG and EURUSD
points-vs-decimal): **always check a cache's price level against the instrument
it claims to be before trusting a backtest built on it.** The name proves
nothing.

*(The full 2026-08-22/23 audit, the free-tier probe table and the original
blocker text → `docs/OPERATIONS_LOG.md`.)*

## ⛔ DAX candle cache — BLOCKER on any DAX work

**Root cause: `fetch_twelvedata.py` maps `"DAX" -> "EWG"`, the iShares MSCI
Germany ETF** — USD-denominated, ~$40/share, different constituents. **No
rescaling can repair it** (wrong instrument, wrong currency, wrong
constituents). The symptom that led there: `DAX_15MIN_AV.json` has a **median
15MIN range of 0.055 index points** across 10,270 candles, so the `_MIN_SL_DIST`
floor of 5.0 binds on **100%** of them. **Any backtest on that file is
meaningless.** Diagnosis → `docs/OPERATIONS_LOG.md`.

✅ **A fix now exists but has NOT been applied:** Dukascopy's
`INSTRUMENT_IDX_EUROPE_E_DAAX` measured **1.005x against IG** and is in
`scripts/fetch_dukascopy.py`. **DAX was not pulled** — there is no DAX row in
the roster. It is one command away if a DAX strategy ever returns.

⚠️ **`DAX_15MIN_AV.json` remains unusable and must never be backtested on.**

## Database Backups (VPS)

Live in **`/home/ubuntu/backups/`**, outside the repo tree. Deliberately not
under `database/` — `Dockerfile:11` is `COPY . .`, so anything in the tree is
baked into every image layer; the two backups alone were 504 MB per build.

| File | Taken for | Contents |
|---|---|---|
| **8 backups 2026-07-20 → 2026-08-23** | inventory → `docs/OPERATIONS_LOG.md` | includes `trades.bak-20260720T012352Z.db`, the **sole surviving pre-correction ledger state** (565 trades), and two that were found UNLISTED days later — one with a permanently unrecoverable purpose |
| `trades.bak-20260904T020447Z.db` | Before the Stage 4 `profit_factor` schema change + parity-v3 import — taken on the HOST | 996 trades, 268,119 backtest_results, 182 walkforward_runs, 324,042,752 bytes, `integrity_check ok` |
| `trades.bak-20260904T022720Z.db` | `import_stage4.py`'s own rule-5 backup, immediately before the parity-v3 write. **Was written to the CONTAINER's ephemeral layer and rescued to the host afterwards** — see the backup-dir defect below | 996 trades, 268,119 backtest_results, 182 walkforward_runs, 324,042,752 bytes, `integrity_check ok` |
| `trades.bak-20260904T024323Z.db` | Before annotating `walkforward_runs` id 379 `REDUCED_GAUNTLET` → `NOT_RUNNABLE`. Taken on the HOST — the new `st_dev` guard correctly refuses this path from inside the container | 996 trades, 268,129 backtest_results, 653 walkforward_runs, 325,763,072 bytes, `integrity_check ok` |
| `trades.bak-20260904T102031Z.db` | Before retiring the swiftalgo roster rows (ids 11, 13 → `inactive`). Host-side | 996 trades, 268,129 backtest_results, 653 walkforward_runs, 31 active_strategy, 325,836,800 bytes, `integrity_check ok` |
| `trades.bak-20260904T124236Z.db` | Before importing the Dukascopy Stage 4 batch. Host-side | 996 trades, 268,129 backtest_results, 653 walkforward_runs, 31 active_strategy, 325,861,376 bytes, `integrity_check ok` |
| `trades.bak-20260905T061117Z.db` | Before the parity-v3 deploy AND the superseded-batch annotation — one backup covers both. Taken on the HOST as `ubuntu` via `Connection.backup()` | 996 trades, 268,141 backtest_results, 1,130 walkforward_runs, 31 active_strategy, 2,461 paper_trades, 102,646 signal_log, 328,159,232 bytes, `integrity_check ok` |

#### ℹ️ The `.db-shm` / `.db-wal` siblings are EXPECTED — not litter, not backups

`Connection.backup()` reproduces the source's journal mode and the source is
`journal_mode=wal`, so **every backup is a WAL database and ANY read — even
`mode=ro` — recreates its siblings.** Demonstrated by moving them aside,
verifying the `.db` self-contained, and watching them reappear on the next
read. **Decision: LISTED, not removed** — ~200 KB against a 3.5 GB directory,
and a rule the next integrity check silently reverses is worse than a
documented exception. Investigation → `docs/OPERATIONS_LOG.md`.

**They are NOT backups and must never be counted as one.** This note exists so
the next reader auditing this directory does not find unlisted files and
conclude the table is incomplete.

#### ⛔ A backup written INSIDE the container is not a backup

`import_stage4.py`'s `DEFAULT_BACKUP_DIR` is a HOST path, but the root-owned
VPS DB forces the script to run in the container, where that path resolves to
the **ephemeral overlay**. 650 MB landed there, invisible from the host, and
**every run reported `integrity_check ok`**. Found by listing the host
directory, not by anything the run said.

✅ **Guarded, and the guard has been SEEN to fire:** `backup_target()` compares
`st_dev` against the target's directory (`/app/database` bind mount = 2049,
overlay = 50) and **refuses**. This is rule 7's worked instance →
`docs/INCIDENT_HISTORY.md`; the full write-up → `docs/OPERATIONS_LOG.md`.

**Standing discipline for this table:**
- ⚠️ **The VPS `database/trades.db` is owned by `root`.** A write as `ubuntu`
  on the host dies with `attempt to write a readonly database`. Back up on the
  host; import in the container.
- **Take backups with `Connection.backup()`, never `cp`** — `cp` on a live DB
  with an open WAL can produce a torn copy.
- **A backup goes into the table above in the SAME change.** Two files were
  found unlisted after the fact and one has a permanently unrecoverable
  purpose. `import_stage4.py` prints a warning naming this table; that is a
  prompt, not a guarantee.

## Backtest Engine Parity — Stage 1 (2026-08-16)

**Stage 1 (2026-08-16), `e0f51f8..36fac3b`: the backtest was modelling a
different strategy from the one running live.** Detail → `docs/OPERATIONS_LOG.md`.

**The one result to keep in front of every reader: TP and reversal-exit MASK
EACH OTHER.** TP alone barely moves PF; reversal-off alone is degenerate. **Only
together do they resemble live** — so neither would have shown up in isolation.
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

**Measured effect** (AUDUSD 15MIN `williams_r`, identical candles/params/seed,
before run from a clean `git archive HEAD` tree): **PF 1.0849 → 1.0431**, net
$124.45 → **$66.03**, and **trades 221 → 234**. Table →
`docs/OPERATIONS_LOG.md`.

**The trade count RISING is the tell** that this is not "same trades, more
cost" — the fill shifts the SL/TP anchors, so different bars trigger.
Walk-forward at parity-v3: median PF 1.0514, 66.7% windows, **MARGINAL**.

🔴 **THE SPREAD TABLE IS MEDIAN-ONLY AND ITS TAIL IS UNCALIBRATED.
RISK-OF-RUIN AND DRAWDOWN WORK MUST NOT USE IT.**

#### ⚠️ NAMED RESIDUAL — the price series identity is ASSUMED, not shown

Symmetric application of spread is correct only if the corpus carries a **mid**,
and the data cannot settle it: measured cache-vs-IG offsets ran +0.34 to +3.21
pips with **disagreeing signs**, so no bid/ask hypothesis fits — they are
symbol-specific **vendor price-level offsets**. Mid is assumed.

**On the Twelve Data corpus this residual was VARYING AND MATERIAL** — per-bar
stdev **1.1x–1.7x the entire spread parity-v3 models** — so the corpus carried
per-bar noise larger than the cost being modelled, landing directly on SL/TP
trigger evaluation. **Full measurement → `docs/OPERATIONS_LOG.md`.**

✅ **The corpus change is what addressed it.** Dukascopy's means are **±0.06
pips** against Twelve Data's +3.2 on EURUSD, and its entry-allowed-hours noise
floor is **0.46–1.01 of one spread width** rather than 1.1–1.7x. See the
noise-floor table in the Dukascopy corpus section — **that** is the live
interpretation bar.

**What this never did:** invalidate parity-v3. Modelling spread correctly is
still correct. It says any residual backtest-vs-live divergence should be
attributed to price-level parity before anywhere else — and **price-level
parity is still not done**. Still divergent at parity-v3: entry LAG (live fills
25–55 min later), weekend handling, session windows.

### ⚠️ `backtest_results.profit_factor` did not EXIST until 2026-09-04

**Not "was NULL" — the column was ABSENT**, while `walkforward_runs` had carried
`median_pf` since day one. **The table the selector reads had no profit factor;
the one it does not read did.**

🔴 **Why it survived, and this is the reusable part:** every reader does
`dict(row).get("profit_factor")`, and **`.get()` returns `None` for an ABSENT KEY
exactly as it does for a NULL value.** A populated-but-empty column and a
non-existent one are **indistinguishable through `.get()`** — which is why this
file recorded it as "NULL on every row". **To ask whether a column exists, use
`PRAGMA table_info`, never `.get()`.**

Fixed forward-only: `insert_backtest_result` binds `:profit_factor` with **no
`.get()` fallback**, so a caller that omits it raises rather than writing NULL.
`run_backtest.py` populates it from the **same** `calc_profit_factor` the
walk-forward path uses — one function, two callers. **Pre-existing rows stay
NULL and are NOT backfilled** (5,332 local, all pre-parity-v3: history, not
evidence). Migration record → `docs/OPERATIONS_LOG.md`.

✅ **The migration HAS reached the VPS** — `backtest_results` is at 28 columns
with `profit_factor`, gained during the Stage 4 import, so the deploy's
migration step is a **no-op**. ⚠️ **Two dated observations of this table
disagreed inside one file, both labelled 2026-09-04.** A timestamp to the day is
not enough to order two readings of something that changed that day.

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

## ✅ COMPLETED CONTROL VERIFICATIONS — every one observed by POSITIVE signal

**The list of controls awaiting a first production fire is EMPTY.** None of
these was inferred from silence. **Full result blocks → `docs/OPERATIONS_LOG.md`.**

| control | deployed | first real fire / verdict |
|---|---|---|
| FX weekend block (`market_hours.py`) | 2026-08-17 | Sat 2026-08-22 — PASSED |
| 21:00 rollover gate | 2026-08-21 | Sun 08-23, weekday Mon 08-24 — PASSED, 6/6 criteria |
| collector disable → IG warm-up | 2026-08-23 | Mon 08-25 — **7/7 pairs `source=IG REST`**, zero fallback |
| shadow spread gate | 2026-08-21 | Mon 08-25 |
| candle-divergence watchdog | 2026-08-20 | marker test, synthetic row injected then deleted |

**Add a row here BEFORE deploying the next dated control, not after** — the
value of the table is that it was written while the control was still
unobserved.

### The three standing rules these produced

1. **`risk/spread_gate.py` runs with `ENFORCE=False`.** The string
   `SHADOW spread gate: ratio ...` must **never** be the sole explanation for a
   *missing* trade. Its first fire was on a paper signal that still logged as
   `PAPER_BUY` — gate reported, trade taken. **If a trade is ever missing and
   this string is the only explanation, the shadow gate has been promoted by
   accident.**
2. **CHECK 1's spread-sampling ORDER is load-bearing.** The sample is taken
   *before* the block check and the blocked branch still calls
   `log_signal_check`. That is what keeps the thin reopen — the most expensive
   window we have — from going blind. 111/111 FX rows non-null on the Sunday
   reopen.
3. **`CANDLE_SOURCE=ig_stream` is now true END TO END.** It was half true for
   weeks — IG ticks, **yfinance seed data** — because the collector drained the
   allowance so `_warm_up`/`_backfill_gap` fell through on every pair.
   `_is_blocked` had never blocked FX at all (`MARKET_CLOSE` holds no FX
   symbol), which is how **21 weekend trades** were placed (finding 23).

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

**The rollover-hour spread measurement it produced is consolidated with the
Sunday-reopen numbers under the spread cost model** — one place, because both
are excluded from the table by the same predicate for the same reason.

## Stage 4 re-validation — WHERE IT RUNS AND HOW RESULTS COME HOME

**Define the import BEFORE the export.** A run whose results have no defined
path home is how the `walkforward_runs` gap happened twice: the 2026-07-15
AUDUSD promotion has no persisted walk-forward because the table did not exist
yet, and the EURUSD REJECT-vs-MARGINAL discrepancy is **permanently
unresolvable** because no run recorded its candles.

### ⏱️ HOW LONG IT TAKES — 2 minutes per strategy, NOT 27

**Measured: 1m48s** for the full four-stage gauntlet on 29,995 candles. The
27-minute estimate that circulated before the rehearsal was **~15x too high**.
**Thirteen strategies is well under an hour** — no case for parallelising, none
for a reduced gauntlet on time grounds. Per-stage → `docs/OPERATIONS_LOG.md`.

### 🟡 EXPECT MOST ROWS TO BE `REDUCED_GAUNTLET` — the plan, not a fault

`STABILITY_GRIDS` holds **only `williams_r`**, so every other rostered strategy
persists a marker row instead of a stability map. A second verdict,
**`NOT_RUNNABLE`**, covers a strategy that cannot be backtested at all — the
no-grid branch used to write its marker *before any backtest ran*, making
"ran, no grid" and "could not run" indistinguishable.

🔴 **DERIVE THE EXPECTED COUNTS AT RUN TIME, never by hand.** This heading read
"12 OF 13" and **that is worse than having no number**: its whole purpose is to
separate "as planned" from "badly wrong", and with 12 in it a **correct** run
returning 6 markers would have been flagged as anomalous — **the check would
have manufactured the alarm it exists to prevent.** The cause generalises:
`STABILITY_GRIDS` is keyed by strategy **NAME**, the roster is counted in
**ROWS**, and one name holds several rows — an off-by-N that **scales with the
roster**. Derivation → `docs/OPERATIONS_LOG.md`.
> the roster is counted in **ROWS**, and one name can hold several rows.
> Counting names where the system counts rows is an off-by-N that **scales with
> the roster**, not a slip. **Derive any figure of this shape at run time**
> (`SELECT COUNT(*) … WHERE status='paper' AND strategy_name NOT IN
> STABILITY_GRIDS`), never by counting strategies by hand.

**Write the expected counts down BEFORE the run.** A batch returning N reduced
verdicts is either "exactly as planned" or "something is badly wrong", and those
two look identical in the output. Derivation and the 2026-09-04 reconciliation
→ `docs/OPERATIONS_LOG.md`.

## 🔴 STAGE 4 RE-RUN ON DUKASCOPY — RANKINGS COLLAPSED, 2026-09-04

### ✅ THE 10 SUPERSEDED ROWS ARE ANNOTATED ON THE VPS — 2026-09-05

`get_backtest_results()` filters on **`engine_version` alone**, and both Stage 4
batches are `parity-v3`. So the deploy took the selector's own query path from
**2 rows → 22**: **12 Dukascopy + 10 pre-Dukascopy** (the latter on
`*_15MIN_AV.json` + `US500_HOUR_5000_yf.json`). The pre-Dukascopy ten are void —
tau +0.067, and that batch's best figure was **PF 2.2452 on 23 trades**, which
fell to 0.4837 on 85.

**Chosen: ANNOTATE, not filter.** ids **268122–268131** now carry
`superseded / superseded_by / superseded_at / corpus / annotation` merged into
**`import_json`** — same shape as the `walkforward_runs` id-379
`REDUCED_GAUNTLET → NOT_RUNNABLE` annotation, additive, idempotent (re-run:
0 updated / 10 skipped), and reversible from the row alone. Predicate:
`engine_version='parity-v3' AND cache_file NOT LIKE '%_DUKA.json'` — 10 matched,
**0 Dukascopy rows touched**.

🔴 **THIS IS A RECORD, NOT A CONTROL, AND THE DIFFERENCE MATTERS.** Nothing reads
`import_json` — grep confirms it is written only by `import_stage4.py`. **A
re-armed selector would still rank all 22.** Do not mistake the annotation for a
gate.

**The proper fix is (b): filter consumers on CORPUS as well as
`engine_version`** — `get_backtest_results()`, `score_strategies()` and
`select_strategy()`. Deliberately NOT done in a deploy: it touches three modules
in the promotion path, and a corpus filter needs a real provenance predicate
(`cache_file` is written but read by nothing today) rather than a `LIKE`.

**Why deferring it is safe, and this is load-bearing:** nothing on the VPS calls
`score_strategies()` at all. `run_daily.py`'s cron line is commented out, and
`select_strategy()` is inert — `SYMBOLS = ["BTC","US100","US500"]` against
`SYMBOL_BLOCKLIST = {"BTC","US100","US500"}`, so every symbol is skipped before
`_select_for_symbol`. **The 22 rows cannot influence a promotion decision until
someone re-arms the selector — at which point (b) becomes mandatory, and the
annotation is what will tell them why.**

**Same engine (`parity-v3`), same spread model, different corpus.** 12 of 13
ran (id 28 excluded, see below). Imported to the VPS, idempotent on re-import.

### The pre-registration was RIGHT on direction and WRONG on attribution

**Predicted: rankings change.** They did — **Kendall tau = +0.067** across the
10 strategies present in both runs. That is indistinguishable from a random
reordering. **The Twelve Data corpus was shaping which strategies looked good.
Everything ranked on it is VOID, not merely imprecise.**

**Predicted: EURUSD and AUDUSD move most (offsets 5.5x and 4.1x their spread),
GBPUSD and USDCAD least (0.4x, 0.8x). THAT WAS WRONG.** The biggest mover by
far was **GBPUSD `ema_pullback`, rank 1 → rank 10, PF 2.2452 → 0.4837**, on the
symbol predicted to move least. EURUSD's rows moved 2–4 places; USDCAD moved 1.

**The real predictor was SAMPLE SIZE, not offset magnitude.** GBPUSD
`ema_pullback` had **23 trades** on the old corpus. Its PF 2.2452 — the best
number in the entire previous batch — was noise. The strategies with hundreds
of trades moved a few places; the one with 23 moved nine. Offset magnitude
predicted almost nothing.

### The numbers — where they live

**Per-strategy old-vs-new table, the matched-candle-count span control, and the
8-of-8 derived count reconciliation → `docs/OPERATIONS_LOG.md`.** Three results
from it are standing:

- **Span was NOT the explanation.** Re-run at matched candle counts, every
  common strategy tracks the full-span Dukascopy column, not the Twelve Data
  one. **The corpus is the cause.**
- **Still ZERO promotable.** Best walk-forward verdict anywhere is FRAGILE. The
  only MARGINAL from the old run (AUDUSD `williams_r`) fell to REJECT. **US100
  15MIN `ema_pullback` is the highest-PF strategy in the batch (1.4573,
  FRAGILE)** and ran on real index data for the first time.
- **8 of 8 derived expectations matched exactly** — counts derived at run time
  from `roster.db` + `STABILITY_GRIDS`, never carried.

Import: 12 + 477 inserted, re-import **0 inserted / 489 skipped** (idempotent).
Backup `trades.bak-20260904T124236Z.db`.

## Stage 4 runbook — gauntlet invocation, gotchas, import

⛔ **The Twelve Data Stage 4 results (10 of 13 on parity-v3, 2026-09-04) are
SUPERSEDED and have been ARCHIVED → `docs/OPERATIONS_LOG.md`.** They mattered:
they were the batch the Dukascopy re-run was compared against, and the record
of what was believed before the corpus changed. **Their rankings did not
survive it (Kendall tau +0.067) — do not cite any number from them.** The
standing results are the Dukascopy re-run above.

Three standing facts survive that batch and are kept here:
- **id 28 EURUSD 15MIN `ny_session_momentum` cannot be backtested at all.** Its
  roster params emit a wrong-side take-profit; `EngineContractError` on **both**
  corpora. Not caused by parity-v3, not fixed.
- **ids 29/30 were HELD on the ETF blocker, which is now lifted** — see above.
- `walkforward_runs` id **379** was annotated `REDUCED_GAUNTLET` →
  **`NOT_RUNNABLE`** on the VPS (annotated, not deleted). All six VPS
  `REDUCED_GAUNTLET` rows were probed for runnability; exactly one failed.

### 🔴 A GAUNTLET RUN WRITES NO `backtest_results` ROW — four invocations, not one

`--stability-map`, `--monte-carlo`, `--permutation`, `--walk-forward` are checked
in that order and **each branch `return`s**, all of them before the
single-backtest save. **The first attempt at the Stage 4 batch lost ten
`backtest_results` rows to this** — `walkforward_runs` grew by 307 and
`backtest_results` did not move. Caught by enumerating both counts, not by any
error.

✅ **It now REFUSES rather than silently dropping flags** — exit 2, naming every
flag passed, which one would have run, and the four-invocation sequence. Three
genuine composites stay allowed (`--stability-map --monte-carlo`,
`--walk-forward --monte-carlo`, `--walk-forward --sweep`); they are real
pairings inside one branch, not dropped flags. Detail →
`docs/OPERATIONS_LOG.md`.
**Both Dukascopy pre-registrations → `docs/OPERATIONS_LOG.md`.** Their standing
conclusion — *no promotion decision follows from Stage 4; thirteen rows near 1.0
are not a ranking* — is stated with the re-run results above.

### 🔧 Running Stage 4 — the five gotchas, all found by DOING

**Each cost a run. Full text → `docs/OPERATIONS_LOG.md`.**

1. **`export_roster.py` runs on the VPS HOST, not the container** — inside it
   records `git_head = NULL`, which is the no-provenance case it exists to
   prevent.
2. **Back up on the host; import in the container.**
3. **The VPS `trades.db` is owned by `root`** — writes as `ubuntu` die with
   `attempt to write a readonly database`. `docker exec` is the write path.
4. **`--since` must be re-formatted PER TABLE.** `backtest_results.run_at` is
   `'YYYY-MM-DD HH:MM:SS'`; `walkforward_runs.created_at` is ISO with a `T`, and
   **`'T'` sorts above `' '`** — so one raw string compared against both
   **silently widens the window by a day** and sweeps in rows from before the
   batch. Wrong in the one direction nobody checks, because extra rows arriving
   looks like the import working.
5. **`backtest_trades` does NOT cross** — it is keyed on `backtest_id` and the
   import inserts without ids. **An imported VPS row has no per-trade detail
   behind it.** Do not read absent trades on the VPS as a failed import.

### Where it runs: LOCALLY, and the roster comes FROM the VPS

The VPS has **no `scripts/candle_cache/` at all**, and seeding it would either
bake ~36 MB into every image layer (`Dockerfile:11 COPY . .`) or need a
`docker-compose.yml` change to run a batch job. Stage 4 is a batch job with no
reason to run inside the trading container. **Accepted cost, knowingly:** this
deepens the local-vs-VPS corpus split (finding 11); the import step is what
stops it becoming permanent.

⚠️ **The local `active_strategy` holds 3 PHANTOM rows** matching no deployed
strategy, and `--from-roster` without `--roster-db` will resolve them —
demonstrated: `US100 HOUR stoch_rsi` resolves locally to phantom id=2. So:

```
python3 scripts/export_roster.py --out /tmp/roster.db   # on the VPS HOST, 20 KB
scp ubuntu@<host>:/tmp/roster.db ./roster.db            # locally
python3 scripts/run_backtest.py … --from-roster --roster-db ./roster.db
```

`export_roster.py` also writes a `snapshot_provenance` table (source host,
absolute path, git HEAD, row count) — **a roster file with no origin is
indistinguishable from the phantom one it replaces.**

### The import step — `scripts/import_stage4.py`, BUILT and run

**Only rows from the run cross:** `backtest_results` + `walkforward_runs` at
`engine_version = CURRENT_ENGINE_VERSION` and `run_at`/`created_at >= <batch
start>`. The local DB's 5,329 pre-parity rows (1,166 ETF-contaminated) **never
cross**. Transport is a standalone `stage4_<UTCstamp>.db` — inspectable before
it is trusted.

⛔ **NEVER copy the local `trades.db` over the VPS one.** It would destroy the
live `trades`, `paper_trades`, `signal_log` and `active_strategy`. **Additive
row by row, or it does not happen.**

**Six rules, all REFUSALS rather than warnings:** foreign `engine_version`
refused; foreign `spread_model` refused (**and compare `spread_table_sha` too —
a name can be kept while the numbers change**); insert **without `id`**;
**idempotent** on the natural key so a re-run is a no-op; `Connection.backup()`
first, recorded in the Database Backups table in the same change; read back and
report counts — **never infer success from the absence of an exception.**

⚠️ **`backtest_results` still has no `produced_on`/`imported_at`/cache-provenance
columns** (finding 31), so an imported row's off-host origin is not on the row.
`walkforward_runs` carries it in `extra_json`. Full text →
`docs/OPERATIONS_LOG.md`.

## ✅ DEPLOY 2026-09-05 — parity-v3 SHIPPED. 16 commits, `cc9055d..a59cb9b`

Image **`sha256:f38ff0aa1e6c`**, started **2026-09-05T06:14:04Z**, `RestartCount=0`.
**Rollback target `sha256:d936077b2424` @ `cc9055d` is retained** (now dangling,
resolvable by ID). Queue resolved from `git log cc9055d..HEAD` at deploy time,
**never from a list** — the previous note said 9 commits and was 16 within a day.

**The whole live path is untouched by the queue** — verified file-by-file:
`execute_trade.py`, `live_signal_loop.py`, `candle_stream.py`, `receiver.py`,
`positions_poller.py`, `risk/*`, `market_hours.py`, `ig_*.py`, `Dockerfile`,
`docker-compose.yml`, `scripts/crontab`. Only docs, the backtest engine, the two
DB modules, the two version constants and batch scripts changed.

**Migration was a NO-OP, verified BEFORE the deploy rather than discovered at
startup:** `PRAGMA table_info(backtest_results)` read **28 columns with
`profit_factor` present** both before and after. The DDL is a single additive
`ALTER TABLE … ADD COLUMN` in a `try/except pass`.

**Post-deploy, every item a positive observation:** stamps **`parity-v3` /
`measured-2026-09-median` / `c0c905fc6c071dd4`**; `half_spread('EURUSD')`=3e-05
and `half_spread('DAX')` raises `UnmeasuredSpreadError`; 24/24 modules import
clean in-container, 34 strategies registered; crontab md5
**`0f1cc206193f5d30341c3db530357b06`** matching three ways (derived from the
commit, in-container, VPS tree) with one active cron line; both heartbeats beat
**after** container start (`candle_stream` 06:14:14Z, `signal_loop` 06:15:18Z);
`:80` 200, `/health` 200, `/webhook` 405, all three containers up.

### ℹ️ THE RESTART GAP — recorded so nobody diagnoses it later

**Process down ~06:14:04Z → 06:15:18Z. NO capture rows were lost.** The
`signal_log` cycle interval spanning the restart is **14m12s**, *shorter* than
the 15m01s either side, so the restart landed between scheduled cycles and no
cycle was skipped (last before 06:01:05Z, first after 06:15:18Z).

⚠️ **`candle_source_compare` has a genuine ~10-hour hole ending 2026-09-04T20:31:34Z,
and the deploy did NOT cause it.** The venue has been shut since Friday's close,
so the stream has no ticks to compare. **Do not investigate that hole as a
stream fault.**

⚠️ **The market was SHUT for this deploy** — all six symbols
`is_market_open=False`, every `signal_log` row reading `market closed — weekend`
and `spread` NULL. That is correct, not a failure, and **`signal_log.spread`
being NULL right now must not be read as broken spread sampling** (the CHECK 1
criterion-4 mis-specification, second instance). What closes it: non-null spread
across all six symbols after the **Sunday ~23:00 UTC reopen**.

## ✅ PAST DEPLOYS — drift cleared twice. Records → `docs/OPERATIONS_LOG.md`

| date | image | at commit | note |
|---|---|---|---|
| 2026-08-22 | `sha256:42f5585b3e34` | `591dc3a` | the date "the image matches the repo" became true again |
| 2026-08-25 | `sha256:9da8a7927a09` | `715bc18` | 16 commits; **this rebuild is what made the collector disable permanent** — it existed only as a `docker cp`, which is lost on rebuild |

**Three costs that recur on every rebuild, recorded because they are easy to
forget and expensive to rediscover:**
- **The deploy queue must be resolved from `git log` against the running
  image's commit, never from an enumerated list.** A list written in this file
  went stale within one commit, and again within a day.
- **A weekday restart burns IG allowance** re-warming every buffer. Prefer
  weekends.
- **`python3 -c "import webhook.receiver"` creates a fresh IG session on
  import** — three such probes produced three session recreations, and a new
  session invalidates the `positions_poller` token. Probe sparingly.

### Stage 4 dress rehearsal — one strategy, 2026-08-23

Run so anything surprising surprised us on one strategy rather than thirteen.
It did. **Full account → `docs/OPERATIONS_LOG.md`.** Headlines that still
govern planning: **1m48s per strategy**; two defects found and fixed in
`40d716b` (the stability map persisted in one batch at the end, so a crash at
cell 80 of 84 lost everything; `windows_json` NULL on all 84 cells);
**`parity-v2` makes AUDUSD materially worse** (REJECT 11→50 of 84 cells, the
single ROBUST cell gone); and the **round trip to the VPS is idempotent**.

## 📏 Spread cost model — MEASURED, FROZEN, and APPLIED in parity-v3

The gate passed 2026-09-03 on all six symbols and **pass B shipped in
`4bfc248`**: `CURRENT_SPREAD_MODEL = "measured-2026-09-median"`, `SPREAD_COSTS`
deleted, and `engine.py::half_spread()` applies the table at the crossed side.
**Gate criteria, per-symbol enumeration and the pass-A/pass-B staging →
`docs/OPERATIONS_LOG.md`.**

Two findings from that record are load-bearing and are the reason it is kept:
US500 and US100 have **zero dispersion** in the window (median = p90 = max on
1,074 and 906 samples) — a broker-posted tier, not a distribution, so **no
percentile of this pool can ever give the indices a tail**; and hour 21 is
**excluded by construction**, not thin — the rollover gate sets
`is_entry_allowed=False`, which is the predicate the filter uses.

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

- **Frozen bounds** `2026-08-16T00:00` → `2026-08-29T00:00` (two Mon–Fri
  cycles). **The bounds are what make the sha reproducible** — the pool grows
  every five minutes.
- **`spread_table_sha = c0c905fc6c071dd4`**, in `spread_model.py` as
  `MEASURED_SPREADS_2026_09` with `_PROVENANCE` (n, p90, max) and `_WINDOW`
  beside it. Rebuild with `scripts/build_spread_table.py`.

🔴 **US500 AND US100 HAVE ZERO DISPERSION — median = p90 = max on all 1,074 and
906 samples. NO PERCENTILE OF THIS POOL CAN EVER GIVE THE INDICES A TAIL.** That
is a broker-**posted tier**, not a distribution (it matches the rollover
measurement, where both sat flat while FX widened 11–19x). **An index tail needs
a different data source** — tick quotes, or the rollover/reopen tiers treated
*as* the tail — not a higher percentile of this one. FX is the opposite shape:
median = p90, with max/median 4.5–6.5x entirely in the last decile.

🔴 **THE TAIL IS UNCALIBRATED. This is a MEDIAN-ONLY table. RISK-OF-RUIN AND
DRAWDOWN WORK MUST NOT USE IT.** Ruin lives in the tail, and the pre-parity ruin
table was already wrong by more than an order of magnitude (5.58% vs a measured
67.3–84.3%). `p90`/`max` are in `_PROVENANCE` as context and are **deliberately
not in the table.**

### 📏 MEASURED — the Sunday reopen and the 21:00 rollover hour

**The only hard numbers for the two windows the entry policy declines**, and the
primary evidence for both rules. Per-symbol tables → `docs/OPERATIONS_LOG.md`.

| window | FX widening | indices |
|---|---|---|
| Sunday reopen 20:00–22:59 | **9x–22x**; GBPUSD **26 pips** | — |
| 21:00 daily rollover | **11x–19x** | **US500 1.5, US100 5.0 — FLAT, ~1x** |

**GBPUSD's 26 pips is wider than the 10–17 pip range quoted elsewhere in this
file, and wider than its own rollover hour.** Raise that bound where it appears.

⛔ **NEITHER SET MAY ENTER THE SPREAD TABLE.** Every row was taken while
`market_hours.is_entry_allowed` was **False**, and
`get_spread_samples(market_open_only=True)` filters on exactly that predicate.
Including them biases the median **high** — the mirror of the 2026-08-17
bias-low failure, and just as invisible, because a wider number looks
conservative rather than wrong. **They are evidence FOR the policy, never inputs
TO the cost model.** Two different uses of one column; the filter separates them.

🔴 **The indices being FLAT is itself a finding, and only an all-symbols query
could show it.** The rollover widening is an **FX phenomenon**, so the gate —
which deliberately covers 24/7 instruments — is **broader than the evidence base
that justifies it. This is NOT a reason to narrow it** (11 index rows over one
hour; an all-instruments rule has no per-symbol branch to drift). Reasoning →
`docs/OPERATIONS_LOG.md`.

### Known limitation to carry into the table — model shape, not filter

`is_entry_allowed` governs **entries**. A position held through Friday 20:45 →
Sunday 23:00 can still be **exited** at reopen spreads (10–17 pips measured),
and that cost is excluded from anything calibrated this way. `SPREAD_COSTS` is
a single round-trip constant and **cannot express an asymmetric entry/exit
cost**, so this is not fixable by filtering differently — it needs a different
model shape. Recorded in `get_spread_samples`' docstring where whoever builds
the table will read it.

## IG Historical Allowance — 10,000 points/week, one shared budget

**10,000 price points per week, per account, rolling.** One budget shared by
three consumers: `candle_stream` warm-up/backfill (the live path),
`engine.fetch_candles` (backtests), and — until 2026-08-23 —
`scripts/collect_candles.py`.

### ✅ FIXED — gap-backfill no longer duplicates warm-up (finding 37, change 1)

`_backfill_gap` had an upper bound and **no lower one**: every pair, every
reconnect, always at the `WARMUP_COUNT` ceiling — re-fetching 200 points per pair
**seconds after warm-up had filled the same buffers**. Fixed by `_bars_missing()`:
skip when the buffer is current (`missing <= 1`) or future-dated; **unknown still
fetches**, because a redundant backfill costs points while a wrongly-skipped one
leaves the loop on stale candles. Pre-fix measurement →
`docs/INCIDENT_HISTORY.md`.

⚠️ **NOT fixed: sizing a real backfill to the measured gap** — needs the minimum
accepted `numpoints`, still unmeasured.

#### 🔴 RESTART COST DEPENDS ON MARKET STATE — the skip cannot fire on a weekend

| restart | pairs fetched | cost | when |
|---|---|---|---|
| market OPEN, buffers current | 7 warm-up, **0 backfill** | **1,400** | 2026-09-02 |
| a real 7-min reconnect | 6 fetched, 1 skipped | **1,200** | 2026-09-03 |
| **market SHUT (weekend)** | **7 warm-up + 7 backfill** | **2,800** | 2026-09-05 |

Per-pair enumerations → `docs/OPERATIONS_LOG.md`, each with **no pair silent in
both the fetched and skipped lists**. The weekend figure is exact: 14
`[ig_allowance]` lines, **zero** skip lines, meter 8,780 → 5,980 = 200 × 14.

**NOT a regression and NOT a defect** — `candle_stream.py` was not in the deploy
diff, and `_bars_missing()` measures bars behind against the **wall clock**, so
with the book shut the newest bar is ~39 buckets old: `missing >= 2`, fetch,
exactly as documented.

> **THE POINT: the guard cannot tell "stale because we missed data" from "stale
> because the market is closed."** **The finding-37 saving is
> MARKET-HOURS-ONLY — budget a weekend restart at 2,800.** Both prior
> verifications were mid-week, which is why nobody had seen it.

⚠️ **The STORM case is still UNTESTED** (2026-08-28: 511 backfills from
reconnects *seconds* apart), and the 2026-09-02 burn window was
**NON-DIAGNOSTIC** — zero disconnects, so a pre-change container would have
burned zero there too (rule 6). **⏸️ The finding-38 probe is NOT run.**

⚠️ **A rollback trigger written for this deploy said "burn > 1,400 → roll
back", and it fired.** It was **mis-specified, not violated**: it silently
assumed a market-open restart, and the only module that could have caused a
regression was excluded from the diff by construction. Rolling back would have
changed nothing and un-shipped a clean deploy. Same class as CHECK 1's criterion
4 — see CRITERIA AGE AGAINST THE SYSTEM THEY MEASURE. **A burn trigger must name
the market state it assumes.**

### The allowance is logged — `ig_allowance.py`

IG returns `allowance{remaining, total, expiry}` on **every successful**
`/prices` response. **Both consumers did `result.get("prices")` and dropped the
rest**, so the budget was unmeasured and the reset time unknown for the life of
the system. **It reports, it does NOT throttle** — *a logging helper that can
refuse is a logging helper that can stop a warm-up.* Never raises; stdlib-only.

⚠️ **The reset time is only learnable from a request that SUCCEEDS** — a 403
carries no allowance block. ⛔ **That is about what a 403 can TEACH you. It does
NOT say a failed request is free.** Refused requests are attempted and charged
(rule 5).

### Allowance state — ALWAYS RE-READ, never carry a recorded number

**Last read 2026-09-05T06:14:15Z (post-deploy): remaining 5,980 of 10,000,
`resets_at` 2026-09-10T12:43:44Z.** That leaves room for ~2 more weekend
restarts or ~4 weekday ones before the reset.

**The window is ROLLING and its anchor MOVES** — it re-anchors to the first
request after a reset and has already moved twice (04:02 → 07:18 → 12:43).
Derive the window from `resets_at` on a **successful** response; never from a
remembered anchor.

💡 **Read it from the container's own logs first — it costs nothing.**
`docker logs trading_bot-bot-1 | grep ig_allowance | tail -1` returns the last
real reading. A probe is only needed if no fetch has happened since the last
event you care about. That is how the pre-deploy figure was taken on 2026-09-05.

⚠️ **`return_dataframe` is a CONSTRUCTOR argument to `IGService`, not a call
argument** — third time this has bitten a probe. ⚠️ **A probe session
invalidates the `positions_poller` token** — probe sparingly.

### 🔭 TWO UNKNOWNS — STILL UNMEASURED. Probe from the SMALLEST request upward.

Still open, and the 2026-08-25 attempt to measure them **exhausted the
allowance without answering either**:

1. **Max `numpoints` per request.** Bracketed only as: `100000` and `50000` are
   *attempted* and return `error.price-history.io-error`. **No accepted value
   above 200 has ever been measured.**
2. **How far back `MINUTE_15` reaches per epic.** Entirely unknown.

⚠️ **Their original motivation — an IG index backfill — is largely MOOT**: the
Dukascopy corpus now serves US500/US100 at 15MIN over 24 months. They matter now
only for sizing a real gap-backfill (the unfixed half of finding 37).

⛔ **Do NOT bracket from above** — oversized requests are **attempted and
charged**, not refused for free (rule 5). Smallest-first: a one-hour date-range
window (four bars), read `remainingAllowance` off that response (**the delta IS
the measured cost**), step the look-back *date* rather than the request size,
escalate `numpoints` only afterwards. **Budget the session first.**

### Related, recorded not fixed

**`_rest_fetch`'s fallback is ASYMMETRIC:** quota exhaustion raises
`_QuotaExceeded` and gets yfinance; **empty prices or an unresolved `ig_scale`
return `None` and get NOTHING** — which on the 2026-08-22 restart left four
buffers empty with no fallback attempted. Gap-backfill covered it minutes later,
**by luck**.

⛔ **Do not mix sources inside one cache file** — Twelve Data before date X and
IG after is two instruments in one file, the DAX/ETF defect with a subtler
signature. One source per symbol, recorded in the `cache_file` provenance.

**Index sourcing is RESOLVED** (`*_15MIN_DUKA.json`, 24 months at index scale);
**yfinance 1h reaches 730 days** and 15m is capped at 60. Survey table →
`docs/OPERATIONS_LOG.md`, kept as the evidence that the Twelve Data free tier and
yfinance genuinely cannot serve 15MIN indices, so nobody retries them.

## The candle collector is DISABLED (2026-08-23) — do NOT re-enable it as it was

**222 log lines, 222 quota errors, ZERO successes**; **100,800 points/week
against a 10,000 allowance = 10.08x**, exhausted in ~16.7 hours, ~98% waste.

🔴 **Live-path consequence — this was not housekeeping.** With the allowance at
zero, `_warm_up` and `_backfill_gap` fall through to yfinance on **every pair**,
so `CANDLE_SOURCE=ig_stream` was only half true: **IG ticks, yfinance seed
data** — quietly reintroducing the exact off-session index staleness the
2026-07-15 flip existed to fix, while producing nothing.

**If ever rebuilt:** hourly at `numpoints=6` (~3,024/week), writing to the
volume-mounted `./database`, self-throttling on `remainingAllowance` so the live
path keeps a reserve. ⚠️ **`scripts/candle_cache/` is NOT a volume** — anything
written there dies with the image layer. Design → `docs/OPERATIONS_LOG.md`.
so the live path keeps a reserve. ⚠️ **`scripts/candle_cache/` is NOT a volume**
(`docker-compose.yml` mounts only `./database`) — anything written there dies
with the image layer.

## Monitoring Gaps (outstanding)

**Genuinely outstanding:**
- **`correlation_events` is write-only** — 3,824 rows, but they are per-cycle
  re-logs of a *standing state*, not distinct events (~130 episodes). Consumer
  proposed, not built.
- **`/app/logs/daily_run.log` no longer exists**, so the dashboard's cron-status
  panel (page 01) parses a missing file and reads permanently stale. Cosmetic,
  expected consequence of disabling `run_daily`.
- **Dangling Docker images on the VPS** — 26 at 2026-08-22, 30 at 2026-09-04.
  Not pruned; disk is not pressing. Check before the next rebuild.

**Two entries here were WRONG and are corrected, not deleted → full text in
`docs/OPERATIONS_LOG.md`:**
- ~~`candle_stream` staleness is unmonitored~~ — **FALSE.** `watchdog.py` has
  called `check_heartbeat(..., "candle_stream", ...)` since **2026-07-08**, and
  it already early-returns outside market hours. **This bullet was wrong for six
  weeks** — a gap recorded as outstanding while the monitor existed is the
  mirror of a control believed present that never fired. Both come from reading
  the doc instead of the code.
- ~~webhook arrival freshness is unmonitored~~ — **VOID BY RETIREMENT.** **The
  proposed watchdog recency check must NOT be built:** the source is retired, so
  it would either alert forever or be tuned until it can never fire — and the
  second is worse, because a control that cannot fire reads as one that is
  passing.

**`candle_source_compare` HAS a reader** — `watchdog.py::check_candle_divergence`,
threshold 5x a **baked** p99 (**baked, not rolling: a rolling baseline widens
around the anomaly it exists to catch**). ⚠️ **Do not retune to silence US100** —
its ~100-pip divergence is off-session yfinance staleness, and a global threshold
accommodating it goes blind to FX at 1–2 pips. Detail →
`docs/OPERATIONS_LOG.md`.

> 🔴 **STANDING RULE — the one thing here that outlives its source: A LIVE
> SIGNAL SOURCE GETS A LIVENESS CHECK AS PART OF WIRING IT UP.** Not a
> follow-up ticket, not "once it's proven" — in the same change that makes it
> live. **Monitoring was built where the WORK was happening, not where the RISK
> was:** the one source rostered `active` had **zero** liveness checks while the
> two paper-only loops had **two each**. Nobody decided that; it accreted.
> Retro-fitting a monitor requires someone to first notice the thing is
> unmonitored — exactly the observation nobody makes about a system that appears
> to be working.

## Infrastructure Incidents
Two recorded; full accounts → `docs/OPERATIONS_LOG.md`.

- **2026-08-15** selector-disable deploy (`9e5f21a`), verified by marker test.
  ⚠️ Its record lists open positions at that moment — **the roster churns;
  never carry a hardcoded position list forward.**
- **2026-07-02** a stale `tradingbot.service` had been running since Apr 12
  **alongside** the Docker container — same IG account, same DB — firing live
  trades on 3-month-old code, undetected. **This is why the policy is
  Docker-only, no systemd**, and why `watchdog.py` checks for a duplicate
  uvicorn process outside the container's own tree.

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
- place_trade rejection reasons persist to `signal_log.error` (2026-07-25) —
  previously only `print()`'d and **lost on every container restart**, which
  destroyed real evidence twice. `execute_trade.last_reject_reason` is a
  module-level dict keyed by symbol, **not thread-safe** — acceptable only
  because signal_loop is single-threaded and swiftalgo runs from the webhook
  path. Detail → `docs/OPERATIONS_LOG.md`.
- Overview alert banner triggers if signal_log silent 2h+
- Cron status parsed from /app/logs/daily_run.log
- Weekend close: _verify_closed_on_ig before marking CLOSED
- Friday webhook block: _is_blocked() called in receiver.py

## Test Scripts
**Ad-hoc only** (the pipeline scripts are in the Architecture tree):
`bot/test_ig.py` verify IG session · `bot/test_trade.py` place a test BUY
XAUUSD · `bot/search_market.py` search IG epics · `scripts/seed_test_data.py`
insert fake trades. Full table → `docs/OPERATIONS_LOG.md`.

---

## Current Build Phase
PHASE 7 — Risk Management & Stability

### Completed in Phase 7 → `docs/OPERATIONS_LOG.md`

Daily loss limits, trade-count bug-catchers, market-hours and Friday blocks,
weekend auto-close, the poller false-close fix, `_verify_closed_on_ig()`,
per-symbol cooldown, the paper trading system, and the concurrent-position cap.

⚠️ **The concurrent-position cap shipped SCOPED DIFFERENTLY than planned:**
cap is **1, not 2**, and per **(symbol, strategy_name)** on the **signal_loop
live path only** — **not** a global cap across symbols. See
`risk/concurrent_positions.py`.

### Still to build in Phase 7
- ~~Telegram alerts~~ **DONE 2026-07-07/08** — it sat in this list, contradicting
  the Alerting section, for five weeks.
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