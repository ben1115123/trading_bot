# Trading Bot — CLAUDE.md

## Project Overview
A webhook-driven algorithmic trading bot that receives 
TradingView alerts, applies trend filtering and risk 
management, and executes live trades via the IG Markets API.

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
utils/logger.py             Appends trades to logs/trade_log.csv
database/db.py              TO BUILD — SQLite connection/setup
database/models.py          TO BUILD — table schemas + queries
dashboard/app.py            TO BUILD — Streamlit entry point

## Deployment Environment
- Bot runs on Oracle VPS (Ubuntu)
- Bot managed as systemd service on port 8000
- Dashboard will run as systemd service on port 8501
- Both services on same VPS, same machine
- Access dashboard remotely via Nginx reverse proxy
- SSL via Certbot (Let's Encrypt)
- Do NOT suggest Vercel, Railway, or external hosting
- SQLite is sufficient — do NOT suggest PostgreSQL
  unless multiple simultaneous writers are needed

## Broker Integration — IG Markets
- Library: trading_ig (IGService)
- Account type: LIVE (account ID: TW75S)
- Credentials from .env: IG_USERNAME, IG_PASSWORD, IG_API_KEY
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

## Running the Bot
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000

## Key Behaviours & Gotchas
- Session recreated at startup (called on execute_trade.py import)
- 1-second cooldown between trades (last_trade_time global)
- place_trade auto-retries once after 401/session expiry
- ai_filter.py is a stub — not wired into main flow
- strategy/parser.py and filters/rule_filters.py are stubs
- data/market_data.py returns empty dict
- logs/trade_log.csv exists but will be deprecated
  once Phase 1 database logging is complete

## Test Scripts
| File                   | Purpose                          |
|------------------------|----------------------------------|
| bot/test_ig.py         | Verify IG session (DEMO account) |
| bot/test_trade.py      | Place test BUY on XAUUSD (DEMO)  |
| bot/search_market.py   | Search IG market epics           |

---

## Current Build Phase
PHASE 1 — Database Logging + Basic Monitoring UI

### 1A — Database Layer
Files to build:
- database/db.py
- database/models.py

Schema:

trades:
  id            INTEGER PRIMARY KEY AUTOINCREMENT
  timestamp     TEXT NOT NULL
  symbol        TEXT NOT NULL
  direction     TEXT NOT NULL       -- BUY or SELL
  size          REAL NOT NULL
  entry_price   REAL NOT NULL
  sl            REAL
  tp            REAL
  deal_id       TEXT
  pnl           REAL                -- NULL until closed
  source        TEXT DEFAULT 'indicator'
  strategy_name TEXT DEFAULT 'manual'
  status        TEXT DEFAULT 'OPEN' -- OPEN | CLOSED | REJECTED

backtest_results:
  id            INTEGER PRIMARY KEY AUTOINCREMENT
  strategy_name TEXT NOT NULL
  symbol        TEXT NOT NULL
  timeframe     TEXT NOT NULL
  total_trades  INTEGER
  win_rate      REAL
  profit        REAL
  drawdown      REAL
  sharpe_ratio  REAL
  score         REAL
  run_at        TEXT NOT NULL

active_strategy:
  id            INTEGER PRIMARY KEY AUTOINCREMENT
  strategy_name TEXT NOT NULL
  symbol        TEXT NOT NULL
  updated_at    TEXT NOT NULL

Execution hook:
- ONLY touch bot/execute_trade.py at the logging point
- After response.get("status") == "OPEN" → call log_trade()
- log_trade() defined in database/models.py
- Touch nothing else in execute_trade.py

### 1B — Streamlit Dashboard
Files to build:
- dashboard/app.py
- dashboard/pages/01_overview.py
- dashboard/pages/02_trade_log.py
- dashboard/pages/03_calendar.py
- dashboard/pages/04_backtest.py (placeholder)

Pages:

Overview:
- Cards: total trades, win rate, total P&L
- Active strategy name + symbol
- Last 10 trades table
- Equity curve chart (Plotly)

Trade Log:
- Full trades table
- Filters: symbol, direction, date range, strategy
- Export to CSV button

Calendar:
- Monthly grid
- Green = profit day, Red = loss day, Grey = no trades
- Click day → show that day's trades

Backtest (placeholder):
- Message: "No backtest results yet"
- Table structure ready for Phase 3 data

Tech:
- Streamlit + Plotly
- Reads directly from database/trades.db

### 1C — VPS Deployment
Both services on Oracle VPS (Ubuntu):
- FastAPI bot:      port 8000 (existing)
- Streamlit:        port 8501 (new)
- Database:         database/trades.db (shared)

Systemd service for dashboard:
Path: /etc/systemd/system/dashboard.service
[Unit]
Description=Trading Dashboard
After=network.target
[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/trading_bot
ExecStart=streamlit run dashboard/app.py
  --server.port 8501 --server.headless true
Restart=always
[Install]
WantedBy=multi-user.target

Scripts to create:
- scripts/start_all.sh   → starts both bot + dashboard
- scripts/stop_all.sh    → stops both services
- scripts/status.sh      → shows status of both services

### 1D — Nginx + SSL Setup
Nginx reverse proxy config for VPS:
- yourdomain.com/dashboard → localhost:8501
- yourdomain.com/webhook   → localhost:8000

Template file to create:
- nginx/trading.conf

SSL: Certbot (Let's Encrypt) — free

Remote access:
- Dashboard viewable from any browser after Nginx setup
- If no domain yet, use SSH tunnel temporarily:
  ssh -L 8501:localhost:8501 ubuntu@YOUR_VPS_IP

### 1E — Scalability Rules
- All config (paths, ports, DB path) via .env
- Database calls ONLY through database/models.py
- New dashboard pages go in dashboard/pages/ only
- Never write raw SQL outside models.py
- Switching DB: change DATABASE_URL in .env only
- New assets: add to EPIC_CONFIG in execute_trade.py

---

## Completed ✅
- Webhook receiver (FastAPI)
- IG API execution engine
- Risk manager ($15 USD fixed)
- Trend filter
- CSV trade logging (deprecated in Phase 1)

---

## Upcoming Phases 📋

PHASE 2 — Enhanced Dashboard + Live P&L
- Pull open positions from IG API
- Show live unrealised P&L
- Strategy performance comparison charts
- Win rate breakdown by symbol
- Mobile responsive layout

PHASE 3 — Backtesting Engine
- backend/strategies/base.py
- backend/strategies/rsi.py
- backend/strategies/supertrend.py
- backend/backtesting/engine.py
- backend/backtesting/metrics.py
  (win rate, drawdown, Sharpe ratio)
- Results → backtest_results table
- Dashboard page 04 auto-populated

PHASE 4 — TradingView MCP + Pine Script
- Connect Claude Code to TradingView Desktop via MCP
- Read top-rated Pine Script strategies
- Convert Pine Script logic → Python strategy classes
- Auto-run backtest on each converted strategy
- All results logged for comparison

PHASE 5 — Strategy Selector
- Score formula:
  win_rate*0.4 + profit*0.3 +
  (1-drawdown)*0.2 + sharpe*0.1
- Auto-select best performer above threshold
- Update active_strategy table
- Log when strategy switches

PHASE 6 — Daily Automation
- scripts/run_daily.py:
  * Backtest all strategies
  * Score and select best
  * Update active_strategy
- Cron: 0 6 * * * python scripts/run_daily.py
- Only switch if improvement > 10%

---

## Critical Rules for Claude Code
- NEVER modify execute_trade.py without permission
- NEVER create a second execution engine
- NEVER hardcode credentials, IPs, or paths
- ALWAYS use .env for all config values
- ALWAYS log trades to database not just CSV
- ALWAYS tag trades with source + strategy_name
- ALWAYS ask before touching bot/ or webhook/
- Database calls ONLY via database/models.py
- New dashboard pages ONLY in dashboard/pages/
- Deployment ONLY on Oracle VPS — no external platforms
- SQLite only — no PostgreSQL unless explicitly told