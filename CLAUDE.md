# Trading Bot — CLAUDE.md

## Project Overview
A webhook-driven algorithmic trading bot that receives 
TradingView alerts, applies trend filtering and risk 
management, and executes live trades via the IG Markets API.
Built in phases — current focus is VPS deployment of
database logging and monitoring dashboard.

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

## VPS Current Docker State
- Docker only — NO docker-compose installed
- Running container: bot
- Image name: trading_bot
- Start command: uvicorn main:app --host 0.0.0.0 --port 8000
- Port mapping: 0.0.0.0:80 → 8000
- No volumes mounted (null)
- No dashboard container yet
- No Nginx container yet
- VPS code is outdated — git pull required in Phase 1C

## Target Docker Architecture (after Phase 1C)
Three containers managed by docker-compose:

  bot:
    image: trading_bot
    command: uvicorn main:app --host 0.0.0.0 --port 8000
    ports: 80:8000
    env_file: .env
    restart: always
    volumes:
      - ./database:/app/database   ← shared SQLite

  dashboard:
    image: trading_dashboard
    command: streamlit run dashboard/app.py
             --server.port 8501 --server.headless true
    ports: 8501:8501
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

Note: Bot currently uses port 80 directly.
After Nginx is added, Nginx takes port 80 and
routes to bot (8000) and dashboard (8501) internally.

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

## Deployment Process (after Phase 1C)
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
- Bot currently on port 80 — Nginx will take over port 80
  after Phase 1C, bot moves to internal port 8000 only

## Test Scripts
| File                      | Purpose                        |
|---------------------------|--------------------------------|
| bot/test_ig.py            | Verify IG session (DEMO)       |
| bot/test_trade.py         | Place test BUY on XAUUSD       |
| bot/search_market.py      | Search IG market epics         |
| scripts/seed_test_data.py | Insert fake trades for testing |

---

## Completed ✅
- Webhook receiver (FastAPI)
- IG API execution engine
- Risk manager ($15 USD fixed)
- Trend filter
- Phase 1A: SQLite database + all table schemas
- Phase 1B: Streamlit dashboard (all 4 pages)
- GitHub SSH authentication (WSL)
- CSV trade logging (deprecated)

---

## Current Build Phase
PHASE 1C — Docker + VPS Deployment

### Goal
Migrate VPS from single Docker container to
docker-compose with bot + dashboard + nginx.
Both bot and dashboard share same SQLite database
via Docker volume.

### Files to build
- docker-compose.yml
- dashboard/Dockerfile
- nginx/trading.conf
- scripts/deploy.sh
- scripts/status.sh
- .env.example

### Step by step for Claude Code

Step 1 — Install docker-compose on VPS:
  ssh into VPS
  sudo apt-get update
  sudo apt-get install docker-compose-plugin
  docker compose version (verify)

Step 2 — Create docker-compose.yml locally
  Manages: bot + dashboard + nginx
  Shared volume: ./database:/app/database
  Bot moves from port 80 to internal 8000
  Nginx takes port 80, routes to both services

Step 3 — Create dashboard/Dockerfile
  Base: python:3.11-slim
  Install requirements
  Expose port 8501
  CMD: streamlit run dashboard/app.py

Step 4 — Create nginx/trading.conf
  Route /webhook → bot:8000
  Route / → dashboard:8501
  No SSL yet (IP only, no domain)

Step 5 — Create scripts/deploy.sh
  SSH into VPS
  git pull origin main
  docker-compose down
  docker-compose up -d --build
  docker-compose ps

Step 6 — Create .env.example
  VPS_HOST=
  VPS_USER=ubuntu
  VPS_SSH_KEY=~/.ssh/trading-bot-new.key
  DATABASE_URL=database/trades.db
  BOT_PORT=8000
  DASHBOARD_PORT=8501
  IG_USERNAME=
  IG_PASSWORD=
  IG_API_KEY=

Step 7 — Test locally first
  docker-compose up -d --build
  curl localhost:8000 (bot)
  open localhost:8501 (dashboard)
  verify both see same database

Step 8 — Deploy to VPS
  git push origin main
  ssh into VPS
  run deploy.sh
  verify docker-compose ps shows 3 containers

### Critical for this phase
- Do NOT stop the bot until new docker-compose
  is tested and ready to start immediately
- Database must be mounted as volume BEFORE
  stopping old container — data must not be lost
- Verify bot is still receiving webhooks after
  migration before marking phase complete

---

## Phase 1D — Nginx Access (after 1C confirmed working)
No domain — use IP directly:
- http://YOUR_VPS_IP → dashboard (port 80 via Nginx)
- http://YOUR_VPS_IP/webhook → bot webhook endpoint
- SSH tunnel for secure local access:
  ssh -i $VPS_SSH_KEY -L 8501:localhost:8501
  ubuntu@$VPS_HOST
  then open http://localhost:8501
- Add domain + SSL later if needed

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
- Results → backtest_results table
- Dashboard page 04 auto-populated

PHASE 4 — TradingView MCP + Pine Script
- Connect Claude Code to TradingView Desktop via MCP
  (tradesdontlie/tradingview-mcp — CDP based)
- Read top-rated Pine Script strategies
- Convert Pine Script → Python strategy classes
- Auto-run backtest on each converted strategy
- All results logged to backtest_results table

PHASE 5 — Strategy Selector
- Score formula:
  win_rate*0.4 + profit*0.3 +
  (1-drawdown)*0.2 + sharpe*0.1
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
- Database calls ONLY via database/models.py
- New dashboard pages ONLY in dashboard/pages/
- Docker only on VPS — no systemd services
- SQLite only — no PostgreSQL unless explicitly told
- SSH credentials always from .env — never hardcoded
- After every VPS deployment run docker-compose ps
  and verify all 3 containers are running