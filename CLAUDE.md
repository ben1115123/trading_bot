# Trading Bot — CLAUDE.md

## Project Overview
Webhook-driven algorithmic trading bot. Pipeline:
TradingView alert → webhook → Python bot → IG Markets API.
Current focus: Phase 4 — TradingView MCP + Pine Script.

## Architecture
main.py                     FastAPI entry point
webhook/receiver.py         POST /webhook — alert parser
bot/execute_trade.py        Trade logic, session, execution
risk_manager.py             Lot size ($15 USD fixed risk)
filters/rule_filters.py     Trend filter (contra-trend block)
data/positions_poller.py    ✅ Polls IG every 30s, close detect
database/db.py              ✅ SQLite connection/setup
database/models.py          ✅ All table schemas + queries
dashboard/app.py            ✅ Streamlit entry point
dashboard/pages/            ✅ Pages 01-04 complete
backend/strategies/         ✅ base.py, rsi.py, supertrend.py
backend/backtesting/        ✅ engine.py, metrics.py
scripts/run_backtest.py     ✅ CLI backtest runner

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
| Symbol | Epic                   | Value/Point |
|--------|------------------------|-------------|
| US500  | IX.D.SPTRD.IFMM.IP     | 1           |
| US100  | IX.D.NASDAQ.IFMM.IP    | 1           |
| BTC    | CS.D.BITCOIN.CFBMU.IP  | 0.1         |

## Webhook Payload
{
  "symbol": "US500", "buy_signal": "1", "sell_signal": "0",
  "trend": "1", "long_sl": "5100.0", "long_tp": "5200.0",
  "short_sl": "5300.0", "short_tp": "5000.0"
}
trend "1" = up (blocks SELL) | trend "3" = down (blocks BUY)

## Risk Management
lot_size = 15 / (sl_distance × value_per_point)
Min: 0.1 | Max: 10.0 | Entry price fetched live from IG

## Backtesting Rules (enforced in ALL phases)
- ALWAYS split candles 80/20 (train/test)
- NEVER generate signals on training portion
- ALWAYS store every simulated trade in backtest_trades
- ALWAYS calculate benchmark (buy-and-hold) per run
- ALWAYS run parameter sweep on new strategies
- Default timeframe: HOUR (better signal density than 5MIN)
- Default candle count: 2000
- Minimum trades threshold: 10 trades in test window
  — any run with <10 trades is flagged, not scored
- Strategy focus: intraday, scalping, momentum only
  — no swing or daily strategies unless explicitly asked

## Data Sources
- Backtesting: yfinance (free, no API limit) — DEFAULT
  Use: --source yfinance --cache on all backtest runs
  Symbol map: US500→^GSPC, US100→^NDX, BTC→BTC-USD
- Live trading: IG Markets API only
  IG historical data API: 10,000 points/week — DO NOT
  use for backtesting sweeps, reserve for live execution
- Cache location: scripts/candle_cache/
  Naming: {SYMBOL}_{TF}_{COUNT}_yf.json (yfinance)
          {SYMBOL}_{TF}_{COUNT}.json (IG)

## Key Gotchas
- Session recreated on execute_trade.py import
- 1s cooldown between trades (last_trade_time global)
- place_trade auto-retries once on 401
- Poller failure must NOT affect trade execution
- logs/trade_log.csv deprecated — DB only
- Positions poller: 2 consecutive empty polls before
  marking trades closed (avoids false closes on API blip)
- Transaction history match: deal_reference (short code)
  primary, openDateUtc proximity fallback

## Test Scripts
| Script                    | Purpose                  |
|---------------------------|--------------------------|
| bot/test_ig.py            | Verify IG session        |
| bot/test_trade.py         | Place test BUY XAUUSD    |
| bot/search_market.py      | Search IG epics          |
| scripts/seed_test_data.py | Insert fake trades       |
| scripts/backfill_pnl.py   | Backfill missing P&L     |
| scripts/run_backtest.py   | Run/sweep backtests      |

---

## Current Build Phase
PHASE 4 — TradingView MCP + Pine Script Conversion

### Goal
Connect Claude Code to TradingView Desktop via MCP,
read published Pine Script strategies, convert them
to Python strategy classes, backtest each one using
the Phase 3 engine, log all results to database.

### MCP Setup
Tool: tradesdontlie/tradingview-mcp (CDP-based)
Requires: TradingView Desktop open on Windows
Claude Code connects via Chrome DevTools Protocol

### What gets built
  backend/strategies/{name}.py     One file per converted strategy
  scripts/convert_strategy.py      Pine Script → Python converter
  scripts/run_phase4.py            End-to-end: fetch → convert →
                                   backtest → score → log

### Rules inherited from Phase 3
- 80/20 out-of-sample split on every converted strategy
- Store every simulated trade in backtest_trades
- Run parameter sweep on each converted strategy
- Equity curve + trade drilldown on dashboard
- Benchmark return calculated for every run
- Best performer per symbol surfaced on dashboard

### Step by step for Claude Code

Step 1 — Install and verify TradingView MCP
  Check if tradesdontlie/tradingview-mcp is installed
  If not: npm install -g tradingview-mcp
  Verify connection to TradingView Desktop via CDP
  Confirm Claude Code can read TradingView page content

Step 2 — Fetch top Pine Script strategies
  Navigate to TradingView community scripts
  Filter: strategy scripts, sorted by popularity
  Focus on INTRADAY strategies only:
    - Scalping strategies
    - Intraday momentum strategies  
    - Opening range breakout
    - VWAP-based strategies
    - EMA cross on short timeframes
  Ignore: swing trading, daily/weekly strategies,
          buy-and-hold approaches
  Extract top 5 strategies: name, logic, params, signals
  Save raw Pine Script to scripts/pinescript_cache/
  Run all backtests at 5MIN timeframe, 1000 candles

Step 3 — Convert each strategy to Python
  Create backend/strategies/{name}.py for each
  Must extend base.py Strategy class
  Must implement generate_signals(candles)
  Must expose params dict with defaults

Step 4 — Backtest each converted strategy
  Run scripts/run_backtest.py for each new strategy
  Use --sweep to test param combinations
  All results → backtest_results + backtest_trades

Step 5 — Verify dashboard page 04
  Confirm new strategies appear in summary table
  Confirm equity curves render correctly
  Confirm parameter comparison panel works

---

## Completed ✅
- Phase 1A: SQLite database + table schemas
- Phase 1B: Streamlit dashboard (4 pages)
- Phase 1C: Docker Compose on VPS (3 containers)
- Phase 1D: Nginx remote access live
- Phase 2A: Live trade logging → database
- Phase 2B: Positions poller + close detection
            (consecutive empty counter, deal_reference
            match, timezone fix, 16 trades backfilled)
- Phase 3:  Backtesting engine — RSI sweep (27 runs) +
            SuperTrend verified, 29 results in DB,
            dashboard page 04 fully populated

---

## Upcoming Phases
PHASE 5 — Strategy Selector
  Score: win_rate*0.4 + profit*0.3 + (1-dd)*0.2 + sharpe*0.1
  Only strategies beating benchmark qualify
  Auto-select best → update active_strategy table
  Only switch if improvement > 10%

PHASE 6 — Daily Automation
  scripts/run_daily.py
  Cron: 0 6 * * * python scripts/run_daily.py
  Backtest → score → select → update → log

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
- Database calls ONLY via database/models.py
- New dashboard pages ONLY in dashboard/pages/
- Docker only on VPS — no systemd
- SQLite only unless explicitly told otherwise
- After every VPS deploy: docker-compose ps