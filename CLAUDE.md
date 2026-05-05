# Trading Bot — CLAUDE.md

## Project Overview
Webhook-driven algorithmic trading bot. Pipeline:
TradingView alert → webhook → Python bot → IG Markets API.
Current focus: Phase 6 — Daily Automation.

## Architecture
main.py                     FastAPI entry point
webhook/receiver.py         POST /webhook — alert parser
bot/execute_trade.py        Trade logic, session, execution
                            ⚠️ Trend filter disabled —
                            Pine Script handles filtering
risk_manager.py             Lot size ($15 USD fixed risk)
filters/rule_filters.py     Trend filter (disabled)
data/positions_poller.py    ✅ Polls IG every 30s, close detect
                            Deferred P&L checker (5min, 24h window)
database/db.py              ✅ SQLite connection/setup
database/models.py          ✅ All table schemas + queries
dashboard/app.py            ✅ Streamlit entry point
dashboard/pages/            ✅ Pages 01-04 complete
                            ⚠️ Not deployed to VPS since Phase 3
                            Deploy after Phase 5 is complete
backend/strategies/         ✅ 10 strategies built
  base.py, rsi.py, supertrend.py, vwap_ema.py,
  ema_ribbon.py, bb_squeeze.py, rsi_divergence.py,
  orb.py, ichimoku.py, keltner.py, stoch_rsi.py,
  ema_cross_volume.py, vwap_mean_reversion.py
backend/backtesting/        ✅ engine.py, metrics.py
                            Session filter + max_hold support
scripts/run_backtest.py     ✅ CLI backtest runner
                            --source yfinance --cache flags
scripts/backfill_pnl.py     ✅ Backfill missing P&L
scripts/sync_ig_trades.py   ✅ Sync manual IG trades to DB

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

## Deployment Process
1. git push origin main          (local WSL)
2. SSH VPS → git pull
3. docker-compose down
4. docker-compose up -d --build
5. docker-compose ps             (verify all 3 up)
6. curl localhost:8000 + curl localhost:8501

## Claude Code SSH Permissions
✅ SSH, run docker, git pull, check logs, restart containers
❌ Never modify .env / expose credentials / git push from VPS
❌ Never stop bot container without permission

## Broker — IG Markets
Library: trading_ig (IGService)  |  Account: LIVE (TW75S)
Credentials: IG_USERNAME, IG_PASSWORD, IG_API_KEY (from .env)
Session: auto-refresh every 10min, full recreate on 401

## Supported Assets
| Symbol | Epic                   | yfinance | Value/Point |
|--------|------------------------|----------|-------------|
| US500  | IX.D.SPTRD.IFMM.IP     | ^GSPC    | 1           |
| US100  | IX.D.NASDAQ.IFMM.IP    | ^NDX     | 1           |
| BTC    | CS.D.BITCOIN.CFBMU.IP  | BTC-USD  | 0.1         |

## Webhook Payload
{
  "symbol": "US500", "buy_signal": "1", "sell_signal": "0",
  "trend": "1", "long_sl": "5100.0", "long_tp": "5200.0",
  "short_sl": "5300.0", "short_tp": "5000.0"
}
trend value is received but no longer filtered
— Pine Script indicator handles filtering upstream

## Risk Management
lot_size = 15 / (sl_distance × value_per_point)
Min: 0.1 | Max: 10.0 | Entry price fetched live from IG

## Backtesting Rules (enforced in ALL phases)
- ALWAYS split candles 80/20 (train/test)
- NEVER generate signals on training portion
- ALWAYS store every simulated trade in backtest_trades
- ALWAYS calculate benchmark (buy-and-hold) per run
- ALWAYS run parameter sweep on new strategies
- ALWAYS use --source yfinance --cache on all runs
- Default timeframe: HOUR (better signal density)
- Default candle count: 2000
- Minimum trades threshold:
    swing: >= 10 trades in test window
    daytrading: >= 5 trades in test window
- Strategy types:
    swing: HOUR timeframe, no session filter, no hold cap
    daytrading: 5MIN, session-filter US or 24_7,
                max-hold 78 (US session) or 288 (BTC)

## Data Sources
- Backtesting: yfinance (free, no API limit) — DEFAULT
  Symbol map: US500→^GSPC, US100→^NDX, BTC→BTC-USD
  Cache: scripts/candle_cache/{SYMBOL}_{TF}_{COUNT}_yf.json
- Live trading: IG Markets API only
  IG historical API: 10,000 points/week — reserved for
  live execution only, never for backtesting

## Key Gotchas
- Session recreated on execute_trade.py import
- 1s cooldown between trades (last_trade_time global)
- place_trade auto-retries once on 401
- Poller failure must NOT affect trade execution
- logs/trade_log.csv deprecated — DB only
- Trend filter disabled in execute_trade.py —
  Pine Script handles filtering upstream
- Positions poller: 2 consecutive empty polls before
  marking trades closed (avoids false closes on API blip)
- Transaction history match: deal_reference primary,
  openDateUtc proximity fallback
- Deferred P&L checker: runs every 5min, gives up
  after 24 hours, logs warning if failed
- Dashboard not deployed to VPS since Phase 3 —
  deploy after Phase 5 complete in one clean push
- active_strategy holds 1 row per symbol (upsert on select)
- get_active_strategy(symbol) → dict | None
- get_active_strategy() → list of all active rows

## Test Scripts
| Script                      | Purpose                     |
|-----------------------------|-----------------------------|
| bot/test_ig.py              | Verify IG session           |
| bot/test_trade.py           | Place test BUY XAUUSD       |
| bot/search_market.py        | Search IG epics             |
| scripts/seed_test_data.py   | Insert fake trades          |
| scripts/backfill_pnl.py     | Backfill missing P&L        |
| scripts/sync_ig_trades.py   | Sync manual IG trades to DB |
| scripts/run_backtest.py     | Run/sweep backtests         |
| scripts/score_strategies.py | Score all backtest results  |
| scripts/select_strategy.py  | Select + activate strategy  |

---

## Current Build Phase
PHASE 6 — Daily Automation

### Goal
Remove TradingView dependency for signal execution.
Morning cron rescores + reselects strategy.
Live signal loop runs active strategy all day via yfinance candles.

### Architecture
  scripts/run_daily.py          Orchestrator (cron entry point)
  scripts/daily_backtest.py     Fresh candles → backtest all strategies
  scripts/score_strategies.py   ✅ Score all backtest_results
  scripts/select_strategy.py    ✅ Pick best + update active_strategy
  scripts/live_signal_loop.py   Every HOUR: fetch candles → generate signals → execute

### Morning cron (6am UTC)
  1. Fetch fresh candles (yfinance, 2000 HOUR candles per symbol)
  2. Run backtest for all strategies × all symbols
  3. Score results → select best per symbol
  4. Update active_strategy table
  Cron: 0 6 * * * python scripts/run_daily.py

### Live signal loop
  - Runs continuously after morning cron
  - Every HOUR:
      fetch latest candles from yfinance
      run active_strategy.generate_signals()
      if signal fires → call execute_trade.py
      respect risk manager (no change to lot sizing)
  - No TradingView webhook needed for execution
  - TradingView alerts may still trigger as backup/monitor

### New files to create
  scripts/run_daily.py          Morning orchestrator
  scripts/live_signal_loop.py   Hourly signal poller

### Database changes
  None — active_strategy table already live from Phase 5

### Step by step for Claude Code

Step 1 — Create scripts/run_daily.py
  Calls daily_backtest → score_strategies → select_strategy
  Logs each step with timestamp
  Sends summary to logs/daily_run.log
  Show file and wait for approval

Step 2 — Create scripts/live_signal_loop.py
  Loads active_strategy for each symbol
  Every HOUR: fetch candles → generate_signals()
  If BUY/SELL signal: call execute_trade logic
  Tracks last signal to avoid duplicate fires
  Respects 1s cooldown + market hours
  Show file and wait for approval

Step 3 — Wire loop into Docker
  Add live_signal_loop to docker-compose.yml
  as a 4th container (or as a thread in bot container)
  Show diff and wait for approval

Step 4 — Deploy to VPS
  git pull → docker-compose up -d --build
  Verify all containers up
  Tail logs to confirm first hourly cycle runs

### Phase 6 rules
- NEVER fetch candles from IG API (yfinance only)
- NEVER bypass active_strategy table
- ALWAYS log every signal check + outcome
- NEVER run live_signal_loop without active strategy seeded
- ALWAYS test with paper/dry-run mode first
- ⚠️ Requires permission before touching execute_trade.py

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
            (5min scan, 24h window)
- Phase 3:  Backtesting engine complete
            RSI + SuperTrend verified, 29 results in DB
            Dashboard page 04 fully populated
- Phase 4:  10 strategies built and backtested
            yfinance as default data source
            Session filter + max_hold for day trading
            Trend filter disabled (Pine Script handles it)
            Top: stoch_rsi US100 HOUR
            (24 trades, 70.8% win rate, score 0.893)
- Phase 5:  Strategy Selector complete
            Per-symbol active strategies seeded:
            US100 → stoch_rsi HOUR (0.893)
            US500 → rsi HOUR (0.689)
            BTC   → vwap_ema HOUR (0.654)
            3-panel dashboard, score/select scripts live

---

## Upcoming Phases

PHASE 7 — Risk Management & Stability
  Max trades/day, max daily loss, max exposure
  Strategy stability rules + alerting

PHASE 8 — Production Frontend (Next.js + Vercel)
  Vercel (Next.js) → API calls → VPS (FastAPI + SQLite)
  Build only after Streamlit features finalised

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
- Dashboard deploy: only after Phase 5 complete