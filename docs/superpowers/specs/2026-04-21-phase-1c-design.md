# Phase 1C Design — Docker Compose + VPS Deployment

**Date:** 2026-04-21  
**Status:** Approved

## Goal

Migrate VPS from a single Docker container (`bot`) to a full docker-compose stack with three containers: `bot`, `dashboard`, and `nginx`. Both bot and dashboard share a single SQLite database file via a Docker volume. Nginx takes over port 80 and proxies traffic to both services.

---

## Files to Create / Update

### New
| File | Purpose |
|------|---------|
| `docker-compose.yml` | Defines bot, dashboard, nginx services with shared volume |
| `dashboard/Dockerfile` | python:3.11-slim image running Streamlit on port 8501 |
| `.env.example` | Template listing all required environment variables |
| `scripts/deploy.sh` | SSH-free deploy script: git pull + docker compose down + up --build + verify |

### Updated
| File | Change |
|------|--------|
| `nginx/trading.conf` | Rewrite: Docker service names, `/` → dashboard, `/webhook` → bot, WebSocket support |
| `scripts/status.sh` | Replace systemd calls with `docker compose ps` + `docker compose logs --tail=20` |

---

## Architecture

```
Internet
   │
   ▼ :80
[nginx:alpine]
   ├── /          → dashboard:8501  (WebSocket upgrade for Streamlit)
   └── /webhook   → bot:8000
         │
    [bot]                        [dashboard]
    uvicorn main:app             streamlit run dashboard/app.py
    :8000 (internal)             :8501 (internal)
         │                              │
         └──────────────┬───────────────┘
                        ▼
              ./database:/app/database
              trades.db (WAL mode, shared)
```

- Bot moves off port 80 (internal only at 8000)
- Nginx takes port 80, routes by path
- Cutover is atomic: `docker compose up -d` stops old container and starts 3 new ones

---

## docker-compose.yml Service Definitions

```yaml
services:
  bot:
    build: .
    command: uvicorn main:app --host 0.0.0.0 --port 8000
    env_file: .env
    restart: always
    volumes:
      - ./database:/app/database

  dashboard:
    build:
      context: .
      dockerfile: dashboard/Dockerfile
    command: streamlit run dashboard/app.py --server.port 8501 --server.headless true --server.baseUrlPath ""
    restart: always
    volumes:
      - ./database:/app/database
    depends_on:
      - bot

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx/trading.conf:/etc/nginx/conf.d/default.conf
    depends_on:
      - bot
      - dashboard
    restart: always
```

---

## Nginx Config (nginx/trading.conf)

- `server_name _` — IP-only, no domain required
- `/` → `http://dashboard:8501` with WebSocket upgrade headers (required by Streamlit)
- `/webhook` → `http://bot:8000/webhook`
- No SSL (Phase 1D adds domain + Certbot)

---

## dashboard/Dockerfile

```
Base:    python:3.11-slim
WORKDIR: /app
COPY:    . .
RUN:     pip install --no-cache-dir -r requirements.txt
EXPOSE:  8501
CMD:     streamlit run dashboard/app.py --server.port 8501 --server.headless true
```

---

## Deploy Flow (Option C — pause before cutover)

1. All files committed and pushed to GitHub (local WSL)
2. Claude SSHes into VPS using `~/.ssh/trading-bot-new.key`
3. Claude installs `docker-compose-plugin` if not present
4. Claude runs `git pull origin main` on VPS
5. Claude runs `docker compose build` to pre-build images
6. **Claude pauses — asks user to confirm cutover**
7. User confirms → Claude runs `docker compose up -d`
   - Old single `bot` container stops automatically (port 80 freed)
   - Three new containers start
8. Claude verifies:
   - `docker compose ps` — all 3 running
   - `curl -s localhost:8000` → `{"status":"bot running"}`
   - `curl -s -o /dev/null -w "%{http_code}" localhost:80` → 200

---

## Environment Variables (.env.example)

```
VPS_HOST=
VPS_USER=ubuntu
VPS_SSH_KEY=~/.ssh/trading-bot-new.key
DATABASE_PATH=database/trades.db
BOT_PORT=8000
DASHBOARD_PORT=8501
IG_USERNAME=
IG_PASSWORD=
IG_API_KEY=
```

---

## Critical Constraints

- Do NOT stop the bot container until `docker compose up -d` is confirmed ready
- Database volume must be mounted before old container stops — no data loss
- Verify bot still receives webhooks after migration (curl `/webhook`)
- Never expose credentials in SSH output or logs
- SSH key path: `~/.ssh/trading-bot-new.key` (copied from Windows path in CLAUDE.md)
