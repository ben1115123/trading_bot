# Trading Bot — CLAUDE.md

## Project Overview
A webhook-driven algorithmic trading bot that receives 
TradingView alerts, applies trend filtering and risk 
management, and executes live trades via the IG Markets API.
Built in phases — current focus is the backtesting engine
for RSI and SuperTrend strategies.

## Architecture
main.py                     FastAPI app entry point
webhook/receiver.py         POST /webhook — parses alert JSON
bot/execute_trade.py        Core trade logic: session mgmt,
                            signal parsing, trade execution
risk_manager.py             Lot size calculator ($15 USD risk)
strategy/parser.py          Stub — extracts symbol/signal/price
filters/rule_filters.py     Trend filter (blocks contra-trend)
ai/ai_filter.py             Stub — always returns "ACCEPT"
data/market_data.py         Stub — live data comes from IG
data/positions_poller.py    ✅ BUILT — polls IG every 30s,
                            detects closes, updates DB
utils/logger.py             Appends trades to logs/trade_log.csv
database/db.py              ✅ BUILT — SQLite connection/setup
database/models.py          ✅ BUILT — table schemas + queries
dashboard/app.py            ✅ BUILT — Streamlit entry point
dashboard/pages/            ✅ BUILT — all 4 pages complete

## Local Development Environment
- OS: Windows 11 with WSL2 (Ubuntu)
- Always work in WSL terminal — never Windows PowerShell
- WSL project path:
  /mnt/c/Users/tanbe/Downloads/trading_bot_skeleton
- Claude Code runs in WSL only
- Git SSH key: ~/.ssh/id_ed25519
- GitHub repo: git@github.com:ben1115123/trading_bot.git

## VPS Environment
- Provider: Oracle Cloud
- OS: Ubuntu
- Hostname: trading-bot
- Username: ubuntu
- Project path: /home/ubuntu/trading_bot
- SSH key: ~/.ssh/trading-bot-new.key
  (copy from Windows: 
   cp /mnt/c/Users/tanbe/Downloads/trading-bot-new.key 
   ~/.ssh/trading-bot-new.key
   chmod 600 ~/.ssh/trading-bot-new.key)
- All credentials in .env — never in CLAUDE.md

## VPS Current Docker State ✅ STABLE
- docker-compose managing all 3 containers
- All 3 containers up and healthy:
    bot         — uvicorn on internal port 8000
    dashboard   — streamlit on internal port 8501
    nginx       — port 80, routes to bot + dashboard
- Positions poller running: prints "Positions: none open"
  every 30 seconds as expected
- Session auto-refresh firing: "Recreating IG session..."
- Uptime confirmed: 16+ hours stable

## Docker Architecture
Three containers managed by docker-compose:

  bot:
    image: trading_bot
    command: uvicorn main:app --host 0.0.0.0 --port 8000
    ports: 8000:8000 (internal only — Nginx fronts it)
    env_file: .env
    restart: always
    volumes:
      - ./database:/app/database   ← shared SQLite

  dashboard:
    image: trading_dashboard
    command: streamlit run dashboard/app.py
             --server.port 8501 --server.headless true
    ports: 8501:8501 (internal only — Nginx fronts it)
    restart: always
    volumes:
      - ./database:/app/database   ← same SQLite file
    depends_on: bot

  nginx:
    image: nginx:alpine
    ports: 80:80
    volumes:
      - ./nginx/trading.conf:/etc/nginx/conf.d/default.conf
    depends_on: [bot, dashboard]
    restart: always

## Claude Code SSH Permissions
Credentials loaded from .env:
  VPS_HOST, VPS_USER, VPS_SSH_KEY

Claude Code is permitted to:
  ✅ SSH into VPS to run commands
  ✅ Install docker-compose on VPS
  ✅ Run docker commands on VPS
  ✅ Git pull on VPS
  ✅ Check container logs
  ✅ Restart containers
  ✅ Copy config files to VPS
  ❌ Never modify .env on VPS
  ❌ Never expose credentials in any output
  ❌ Never git push from VPS
  ❌ Never stop bot container without permission

## Deployment Process
1. git push origin main (local WSL)
2. Claude Code SSHs into VPS
3. cd /home/ubuntu/trading_bot
4. git pull origin main
5. docker-compose down
6. docker-compose up -d --build
7. docker-compose ps (verify all 3 running)
8. curl localhost:8000 (verify bot)
9. curl localhost:8501 (verify dashboard)

## Broker Integration — IG Markets
- Library: trading_ig (IGService)
- Account type: LIVE (account ID: TW75S)
- Credentials from .env:
  IG_USERNAME, IG_PASSWORD, IG_API_KEY
- Session auto-refreshes every 10 minutes
- Full session recreate on 401/token-invalid errors

## Supported Assets
| Symbol | Epic                   | Value Per Point |
|--------|------------------------|-----------------|
| US500  | IX.D.SPTRD.IFMM.IP     | 1               |
| US100  | IX.D.NASDAQ.IFMM.IP    | 1               |
| BTC    | CS.D.BITCOIN.CFBMU.IP  | 0.1             |

## Webhook Payload Format
{
  "symbol": "US500",
  "buy_signal": "1",
  "sell_signal": "0",
  "trend": "1",
  "long_sl": "5100.0",
  "long_tp": "5200.0",
  "short_sl": "5300.0",
  "short_tp": "5000.0"
}
- buy_signal / sell_signal: "0" or "1" (string)
- trend: "1" = uptrend, "3" = downtrend
- BUY blocked when trend == 3
- SELL blocked when trend == 1
- Conflicting signals (buy=1 and sell=1) are rejected

## Risk Management
lot_size = RISK_PER_TRADE / (sl_distance * value_per_point)
- RISK_PER_TRADE = $15 USD fixed — do not change
- Min lot: 0.1 | Max lot: 10.0
- Entry price fetched live from IG at trade time

## Running Locally (WSL)
cd /mnt/c/Users/tanbe/Downloads/trading_bot_skeleton
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
streamlit run dashboard/app.py --server.port 8501

## Key Behaviours & Gotchas
- Session recreated at startup (on execute_trade.py import)
- 1-second cooldown between trades (last_trade_time global)
- place_trade auto-retries once after 401/session expiry
- ai_filter.py stub — not wired into main flow
- strategy/parser.py and filters/rule_filters.py are stubs
- data/market_data.py returns empty dict
- logs/trade_log.csv deprecated — database only now
- Dashboard reads from database/trades.db directly
- Bot and dashboard share SQLite via Docker volume
- Positions poller runs as background thread in main.py
- Poller failure must NOT affect bot or trade execution

## Test Scripts
| File                      | Purpose                        |
|---------------------------|--------------------------------|
| bot/test_ig.py            | Verify IG session (DEMO)       |
| bot/test_trade.py         | Place test BUY on XAUUSD       |
| bot/search_market.py      | Search IG market epics         |
| scripts/seed_test_data.py | Insert fake trades for testing |

---

## Current Build Phase
PHASE 3 — Backtesting Engine

### Goal
Build a self-contained backtesting engine that:
1. Fetches historical OHLC candles from IG API
2. Runs RSI and SuperTrend strategies against that data
3. Simulates trades using out-of-sample validation
4. Stores every simulated trade (not just summary metrics)
5. Calculates performance metrics including benchmark comparison
6. Saves all results to backtest_results + backtest_trades tables
7. Populates dashboard/pages/04_backtest.py with full visibility

### New files to create
  backend/strategies/base.py        Strategy abstract base class
  backend/strategies/rsi.py         RSI strategy implementation
  backend/strategies/supertrend.py  SuperTrend strategy implementation
  backend/backtesting/engine.py     Candle iteration + trade simulation
  backend/backtesting/metrics.py    Win rate, drawdown, Sharpe, benchmark
  scripts/run_backtest.py           CLI entry point to trigger a backtest

### Database changes (database/models.py)
  Add backtest_results table:
    id             INTEGER PRIMARY KEY
    strategy_name  TEXT
    symbol         TEXT
    timeframe      TEXT
    run_at         TEXT
    candles_total  INTEGER   ← total candles fetched
    candles_train  INTEGER   ← first 80% used for context
    candles_test   INTEGER   ← last 20% used for simulation
    total_trades   INTEGER
    win_rate       REAL
    total_profit   REAL
    max_drawdown   REAL
    sharpe_ratio   REAL
    benchmark_return REAL    ← buy-and-hold return same period
    params_json    TEXT      ← JSON blob of strategy params used

  Add backtest_trades table:
    id             INTEGER PRIMARY KEY
    backtest_id    INTEGER   ← foreign key → backtest_results.id
    entry_time     TEXT
    exit_time      TEXT
    direction      TEXT      ← 'BUY' or 'SELL'
    entry_price    REAL
    exit_price     REAL
    pnl            REAL
    duration_mins  INTEGER

### Dashboard page (dashboard/pages/04_backtest.py)
  Summary table:
    - All backtest runs as rows
    - Columns: strategy, symbol, timeframe, trades, win rate,
      total profit, max drawdown, Sharpe, vs benchmark
    - Sortable by any column
    - Best performer per symbol highlighted in green

  Equity curve chart:
    - Click any row → see cumulative P&L over time
    - Shows smooth vs choppy performance visually
    - Reveals drawdown periods clearly

  Trade drilldown:
    - Expandable section per run showing every simulated trade
    - Entry/exit price, P&L, duration, direction
    - Helps identify patterns (e.g. only works certain hours)

  Parameter comparison panel:
    - Show multiple runs of same strategy side by side
    - e.g. RSI period=7 vs period=14 vs period=21
    - Makes optimal param selection visual

  Run Backtest button:
    - Trigger new backtest from dashboard UI
    - Select: symbol, timeframe, strategy, candle count, params
    - Results appear in table immediately after run

### Step by step for Claude Code

Step 1 — Add backtest_results and backtest_trades tables
  to database/models.py
  Add query functions:
    insert_backtest_result()
    insert_backtest_trade()
    get_backtest_results()
    get_backtest_trades(backtest_id)
  Show diff and wait for approval before continuing

Step 2 — Create backend/strategies/base.py
  Abstract base class: name, params, generate_signals(candles)
  generate_signals returns list of dicts:
    { index, signal: 'BUY'|'SELL'|'NONE' }

Step 3 — Create backend/strategies/rsi.py
  Params: period (default 14), overbought (70), oversold (30)
  BUY signal when RSI crosses above oversold
  SELL signal when RSI crosses below overbought

Step 4 — Create backend/strategies/supertrend.py
  Params: period (default 10), multiplier (default 3.0)
  Standard SuperTrend formula using ATR
  BUY when price crosses above SuperTrend line
  SELL when price crosses below SuperTrend line

Step 5 — Create backend/backtesting/engine.py
  fetch_candles(symbol, timeframe, count):
    Fetch from IG API using existing session/auth
    Return list of OHLC dicts
  
  run_backtest(strategy, candles, params):
    Split candles: first 80% = train, last 20% = test
    Run strategy signals on test portion only
    Entry on signal, exit on opposite signal
    Apply risk_manager lot sizing
    Calculate benchmark: buy-and-hold return on test period
    Return: list of trade results + benchmark return

  run_parameter_sweep(strategy_class, candles, param_grid):
    Iterate all param combinations in param_grid
    Call run_backtest for each
    Return all results for comparison

Step 6 — Create backend/backtesting/metrics.py
  calc_win_rate(trades) → float
  calc_max_drawdown(trades) → float
  calc_sharpe_ratio(trades) → float
  calc_total_profit(trades) → float
  calc_benchmark_return(candles) → float
    (close price of last candle / close price of first candle - 1)

Step 7 — Create scripts/run_backtest.py
  CLI usage:
    python scripts/run_backtest.py \
      --symbol US500 \
      --timeframe HOUR \
      --strategy rsi \
      --count 500 \
      --sweep   ← optional: run param sweep instead of single run
  Prints summary table to console
  Saves all results + trades to database

Step 8 — Update dashboard/pages/04_backtest.py
  Build full dashboard page as described above
  Run Backtest button calls scripts/run_backtest.py as subprocess

### Data source
  Historical candles from IG API — reuse existing session
  Endpoint: GET /prices/{epic}?resolution={res}&max={count}
  Resolution mapping:
    MINUTE → 1m candles
    HOUR   → 1h candles
    DAY    → daily candles

### Out-of-sample rule
  ALWAYS split candles 80/20 before backtesting
  NEVER run strategy signals on training portion
  Training portion is context only (e.g. for indicator warmup)
  Test portion is where simulated trades are generated
  This rule applies to ALL strategies including Phase 4 imports

---

## Completed ✅
- Phase 1A: SQLite database + all table schemas
- Phase 1B: Streamlit dashboard (all 4 pages)
- Phase 1C: Docker Compose on VPS (bot + dashboard + nginx)
- Phase 1D: Remote access via Nginx — dashboard live at VPS IP
- Phase 2A: Trade logging — live IG trades writing to database
- Phase 2B: Live positions poller + trade close detection
            Poller running every 30s, close detection wired,
            dashboard positions page live

---

## Upcoming Phases 📋

PHASE 4 — TradingView MCP + Pine Script Conversion
- Connect Claude Code to TradingView Desktop via MCP
  (tradesdontlie/tradingview-mcp — CDP based)
- Read top-rated Pine Script strategies from TradingView
- Convert Pine Script → Python strategy classes
- Feed converted strategies into Phase 3 backtest engine
- All results logged to backtest_results + backtest_trades

  ⚠️  Phase 4 must inherit ALL Phase 3 backtesting rules:
  - Out-of-sample 80/20 split on every converted strategy
  - Store every simulated trade in backtest_trades table
  - Run parameter sweep on each converted strategy
  - Show equity curve + trade drilldown on dashboard
  - Calculate benchmark return for every run
  - Surface best performer per symbol on dashboard

PHASE 5 — Strategy Selector
- Score formula:
  win_rate*0.4 + profit*0.3 +
  (1-drawdown)*0.2 + sharpe*0.1
- Only consider strategies that beat benchmark return
- Auto-select best performer above threshold
- Update active_strategy table
- Only switch if improvement > 10%
- Log all strategy switches

PHASE 6 — Daily Automation
- scripts/run_daily.py
- Cron: 0 6 * * * python scripts/run_daily.py
- Backtest → score → select → update → log

PHASE 7 — Risk Management & Stability
- Max trades per day per source
- Max daily loss limit
- Max total exposure
- Strategy stability rules
- Alerting on limit breach

PHASE 8 — Production Frontend (Next.js + Vercel)
- Rebuild dashboard in Next.js/React
- FastAPI on VPS serves as backend API
- Vercel hosts frontend (auto-deploy on git push)
- Oracle VPS keeps bot + database + FastAPI
- Architecture:
  Vercel (Next.js) → API calls → VPS (FastAPI + SQLite)
- Only build once Streamlit features are finalised
- Claude Code handles Vercel deployment via Vercel CLI

---

## Critical Rules for Claude Code
- NEVER modify execute_trade.py without permission
- NEVER create a second execution engine
- NEVER hardcode credentials, IPs, or paths
- NEVER expose credentials in any output or logs
- NEVER stop the bot container without permission
- ALWAYS use .env for all config values
- ALWAYS log trades to database not just CSV
- ALWAYS tag trades with source + strategy_name
- ALWAYS ask before touching bot/ or webhook/
- ALWAYS test locally before deploying to VPS
- ALWAYS verify bot still works after any deployment
- ALWAYS apply 80/20 out-of-sample split in backtests
- ALWAYS store individual trades in backtest_trades table
- ALWAYS calculate benchmark return in every backtest run
- Database calls ONLY via database/models.py
- New dashboard pages ONLY in dashboard/pages/
- Docker only on VPS — no systemd services
- SQLite only — no PostgreSQL unless explicitly told
- SSH credentials always from .env — never hardcoded
- After every VPS deployment run docker-compose ps
  and verify all 3 containers are running
- backend/ is new territory — safe to create freely
- Never touch bot/, webhook/, or execute_trade.py
  when working on backtesting code