# Trading Bot — CLAUDE.md

## Project Overview
Webhook-driven algorithmic trading bot. Pipeline:
TradingView alert → webhook → Python bot → IG Markets API.
Current focus: Phase 7 — Risk Management & Stability.

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
backend/backtesting/        ✅ engine.py, metrics.py
scripts/run_backtest.py     ✅ CLI backtest runner
scripts/run_daily.py        ✅ Morning orchestrator (6am UTC cron)
scripts/score_strategies.py ✅ Score all backtest_results
scripts/select_strategy.py  ✅ Select best per symbol+timeframe
                            ✅ STRATEGY_BLOCKLIST — cron cannot promote
                               blocklisted strategies to live/paper
scripts/sync_ig_trades.py   ✅ IG trade sync, self-contained session
                            ✅ Duplicate prevention via deal_reference
                            ✅ Price+symbol+date secondary check
scripts/backfill_pnl.py     ✅ Backfill missing P&L
utils/telegram_alert.py     ⬜ Planned — not yet built

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

## Supported Assets (Live)
| Symbol | Epic                   | yfinance | Value/Point |
|--------|------------------------|----------|-------------|
| US500  | IX.D.SPTRD.IFMM.IP     | ^GSPC    | 1           |
| US100  | IX.D.NASDAQ.IFMM.IP    | ^NDX     | 1           |
| DAX    | IX.D.DAX.IFMS.IP       | ^GDAXI   | 1           |
| EURUSD | CS.D.EURUSD.MINI.IP | EURUSD=X | 10000 | $1/pip, 10k contract |

## Paper Trade Symbols (.env)
PAPER_TRADE_SYMBOLS=DAX,BTC
(US100_5MIN removed — stoch_rsi deactivated)

## Active Strategies

### Live
| Symbol | TF   | Strategy   | Mode | Source  | Notes                          |
|--------|------|------------|------|---------|--------------------------------|
| US500  | HOUR | stoch_rsi  | Live | loop    | FRAGILE walk-forward verdict (2026-07-09): median PF 1.33, 57.1% windows profitable, 3 of 28 windows PF 0.00. Kept in demo roster at full size for reconciliation data — does NOT meet Phase 3 ROBUST bar for any future live-account return. Review alongside GBPUSD at the 2026-07-21 gate |
| EURUSD | HOUR | swiftalgo  | Live | webhook | Promoted 2026-05-27, $10 risk  |
| US500  | HOUR | swiftalgo  | Live | webhook | Confirmed live 2026-06-04, runs parallel with stoch_rsi via webhook |
| GBPUSD | 15MIN | williams_r | Live | loop   | Promoted 2026-06-22, $1.50 risk (halved 2026-07-07 — FRAGILE walk-forward verdict, review after 20 trades), no session blocks. Review at the 2026-07-21 gate alongside stoch_rsi US500 HOUR |
| EURUSD | 15MIN | williams_r | Live | loop   | Data-collection instance (2026-07-14) — promoted for regime-tagged execution data. Walk-forward status: original 2026-07-07 run REJECT (median PF 0.92, 42.9% windows), corrected 2026-07-14 rerun with rostered params (period=10, oversold=-90, overbought=-20) MARGINAL (median PF 1.08, 85.7% windows, 442 test trades) — verdict boundary-sensitive, NOT an edge promotion. Discrepancy investigated: same cache (predates the original run), same params (verified via active_strategy id=22 timestamp), same window count (7=7) ruling out a --count difference, no engine/strategy code changed since — root cause irreproducible because walk-forward runs were never persisted (no DB row, no saved output); likely a --session-filter or --max-hold CLI flag difference in the original invocation. $10 risk |
| USDCAD | 15MIN | williams_r | Live | loop   | Data-collection instance (2026-07-14) — never backtested before this batch. Walk-forward: REJECT (median PF 0.99, 50% windows, 410 test trades, default params period=14/oversold=-85/overbought=-15 — no prior rostered config existed). NOT an edge promotion — running live on demo purely for regime-tagged execution data. Epic CS.D.USDCAD.MINI.IP verified clean decimal scale (bid=1.41468, TRADEABLE) on demo (Z67Y2C) 2026-07-14; newly registered in ig_scale.py and execute_trade.py EPIC_CONFIG. $10 risk |
| AUDUSD | 15MIN | williams_r | Live | loop   | **Phase-3 lead candidate** (2026-07-15) — promoted paper→demo-live on full-stack validation, NOT a data-collection instance: walk-forward ROBUST (median PF 1.285, 83.3% windows profitable, 6 windows — corrected for the plateau-center params below; the original -15 config's 100%-windows/MARGINAL number was a different cell), stability-map plateau (23 contiguous cells at PF>=1.1, not a spike), permutation test 96th percentile vs synthetic noise, Monte Carlo positive at every percentile (p5=$707 to p95=$2621 on $500/$10-risk, 1000 paths). Params corrected period=14/oversold=-85/**overbought=-20** (was -15 — the rostered row predated the stability map; -20 is the plateau center). Epic CS.D.AUDUSD.MINI.IP verified clean decimal scale (bid=0.6987, TRADEABLE) on demo (Z67Y2C) 2026-07-15; newly registered in ig_scale.py/execute_trade.py EPIC_CONFIG (was paper-only). $10 risk (demo — no bankroll to protect; live sizing per the MC ruin table below comes at Phase 5) |

### Paper
| Symbol | TF    | Strategy   | Mode  | Source | Notes                          |
|--------|-------|------------|-------|--------|---------------------------------|
| US500  | HOUR  | williams_r | Paper | loop   | Accumulating trades             |
| EURUSD | 15MIN | stoch_rsi  | Paper | loop   | 297 bt trades, PF 1.36          |
| EURUSD | 15MIN | bb_squeeze | Paper | loop   | 33 bt trades, PF 2.18. Walk-forward (2026-07-09): FRAGILE — median PF 1.08, 57.1% windows profitable, 149 trades across 7 windows |
| EURUSD | 15MIN | supertrend | Paper | loop   | 111 bt trades, PF 1.35          |
| US500  | HOUR  | stoch_rsi_confluence | Paper | loop | session filter only, shadow logging — see below |
| EURUSD | 15MIN | ny_session_momentum | Paper | loop | 37 bt trades, 75.7% WR, PF 1.64, follow mode |
| US500  | 15MIN | ema_pullback         | Paper | loop | 44 bt trades, 45.5% WR, PF 1.57, EMA8/50. Walk-forward (2026-07-09): FRAGILE — median PF 1.03, 53.8% windows profitable, 171 trades across 13 windows |
| US100  | 15MIN | ema_pullback         | Paper | loop | 86% combos profitable, PF 3.17 best. Walk-forward (2026-07-09): FRAGILE — median PF 1.12, 69.2% windows profitable (one window short of ROBUST's 70% bar), 70 trades across 13 windows. The PF 3.17 sweep result did not survive — overfit |
| GBPUSD | 15MIN | ema_pullback         | Paper | loop | 25 bt trades, 64% WR, PF 2.00 |

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

## Supported Assets (Live)
| Symbol | Epic                   | yfinance | Value/Point |
|--------|------------------------|----------|-------------|
| US500  | IX.D.SPTRD.IFMM.IP     | ^GSPC    | 1           |
| US100  | IX.D.NASDAQ.IFMM.IP    | ^NDX     | 1           |
| DAX    | IX.D.DAX.IFMS.IP       | ^GDAXI   | 1           |

## Supported Assets (Paper only)
| Symbol | Epic                   | yfinance | Value/Point | Notes              |
|--------|------------------------|----------|-------------|--------------------|
| EURUSD | CS.D.EURUSD.MINI.IP    | EURUSD=X | 10000       | $1/pip, 10k contract|
| BTC    | —                      | BTC-USD  | 0.1         | Inactive           |

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
in `walkforward_runs` (run_type='monte_carlo'). This is a reference for
Phase 5 live-account sizing — demo currently runs flat $10 regardless
(no bankroll at risk).

### Paper Trade Risk Override (added 2026-06-12)
Paper trades always use $10 risk regardless of symbol (RISK_PER_TRADE
default). Live overrides above don't affect paper trade sizing —
they're the same value right now only because both are $10 during
demo validation.

### Dead Config
VPS .env has RISK_PER_TRADE=5 — NOT read by any code. risk_manager.py
hardcodes RISK_PER_TRADE=10 as default. Don't trust this env var.

### Daily Loss Limits
| Source              | Limit | Behaviour when hit        |
|---------------------|-------|---------------------------|
| signal_loop         | $75   | Stops firing new trades   |
| tradingview_webhook | $75   | Blocks incoming webhooks  |

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

## Infrastructure Incidents
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

### Still to build in Phase 7
- Telegram alerts (trade placed, trade closed, risk limit hit)
- Strategy stability rules:
    Don't switch if live win rate dropped < 40% last 7 days
- Max concurrent open positions (max 2 at once)
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