# Phase 1C — Docker Compose + VPS Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the VPS from a single `bot` Docker container to a three-container docker-compose stack (bot + dashboard + nginx) sharing a SQLite database via a volume, with a safe pause-before-cutover deploy flow.

**Architecture:** Nginx on port 80 proxies `/` to Streamlit dashboard (port 8501 internal) and `/webhook` to FastAPI bot (port 8000 internal). Both bot and dashboard mount `./database` as a Docker volume so they read/write the same `trades.db`. Cutover is atomic — `docker compose up -d` stops the old single container and starts all three.

**Tech Stack:** Docker, docker-compose-plugin (v2 CLI), nginx:alpine, python:3.10-slim (bot), python:3.11-slim (dashboard), Streamlit, FastAPI/uvicorn, SQLite WAL mode.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Rewrite | `nginx/trading.conf` | IP-only nginx, `/` → dashboard WebSocket, `/webhook` → bot |
| Create | `dashboard/Dockerfile` | python:3.11-slim image for Streamlit on 8501 |
| Create | `docker-compose.yml` | Declares bot, dashboard, nginx with shared volume |
| Update | `scripts/status.sh` | Replace systemd calls with `docker compose ps` + logs |
| Create | `scripts/deploy.sh` | Runs ON VPS: git pull → down → up --build → verify |
| Create | `.env.example` | Credential template (never committed with real values) |

---

## Task 1: Rewrite nginx/trading.conf

The existing file uses `127.0.0.1` (host IPs) and a `/dashboard/` prefix. Replace it entirely to use Docker service names and route `/` to the dashboard.

**Files:**
- Rewrite: `nginx/trading.conf`

- [ ] **Step 1: Write the new config**

Replace the entire contents of `nginx/trading.conf` with:

```nginx
server {
    listen 80;
    server_name _;

    # Bot webhook endpoint
    location /webhook {
        proxy_pass         http://bot:8000/webhook;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # Dashboard — root catches everything else
    # Streamlit requires WebSocket upgrade for /_stcore/stream
    location / {
        proxy_pass         http://dashboard:8501;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 86400;
    }
}
```

- [ ] **Step 2: Verify config syntax (dry-run)**

Run locally — Docker must be available, or skip to VPS verification in Task 8:
```bash
docker run --rm -v $(pwd)/nginx/trading.conf:/etc/nginx/conf.d/default.conf nginx:alpine nginx -t
```
Expected output: `nginx: configuration file /etc/nginx/nginx.conf test is successful`

If Docker not available locally, this step is verified in Task 8 when nginx starts on VPS.

- [ ] **Step 3: Commit**

```bash
git add nginx/trading.conf
git commit -m "feat: rewrite nginx conf for docker-compose service names and root routing"
```

---

## Task 2: Create dashboard/Dockerfile

**Files:**
- Create: `dashboard/Dockerfile`

- [ ] **Step 1: Create the Dockerfile**

Create `dashboard/Dockerfile` with these exact contents:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8501

CMD ["streamlit", "run", "dashboard/app.py", \
     "--server.port", "8501", \
     "--server.headless", "true", \
     "--server.address", "0.0.0.0"]
```

Note: `COPY . .` copies the full project root (context is `.` in docker-compose), so `dashboard/app.py`, `database/`, etc. are all available at `/app/`.

- [ ] **Step 2: Commit**

```bash
git add dashboard/Dockerfile
git commit -m "feat: add dashboard Dockerfile for Streamlit on port 8501"
```

---

## Task 3: Create docker-compose.yml

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Create docker-compose.yml at project root**

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

- [ ] **Step 2: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add docker-compose.yml for bot + dashboard + nginx stack"
```

---

## Task 4: Update scripts/status.sh

Replace systemd calls with docker compose equivalents.

**Files:**
- Modify: `scripts/status.sh`

- [ ] **Step 1: Rewrite the script**

Replace the entire contents of `scripts/status.sh` with:

```bash
#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

echo "=== Container Status ==="
docker compose ps

echo ""
echo "=== Bot logs (last 20 lines) ==="
docker compose logs --tail=20 bot

echo ""
echo "=== Dashboard logs (last 20 lines) ==="
docker compose logs --tail=20 dashboard

echo ""
echo "=== Nginx logs (last 20 lines) ==="
docker compose logs --tail=20 nginx
```

- [ ] **Step 2: Make executable and commit**

```bash
chmod +x scripts/status.sh
git add scripts/status.sh
git commit -m "feat: update status.sh to use docker compose instead of systemd"
```

---

## Task 5: Create scripts/deploy.sh

This script runs **on the VPS** (not locally). It assumes it is called from the project directory `/home/ubuntu/trading_bot`.

**Files:**
- Create: `scripts/deploy.sh`

- [ ] **Step 1: Create the script**

```bash
#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

echo "[deploy] Pulling latest code..."
git pull origin main

echo "[deploy] Building images..."
docker compose build

echo "[deploy] Starting all containers..."
docker compose up -d

echo "[deploy] Container status:"
docker compose ps

echo "[deploy] Verifying bot (port 8000)..."
sleep 3
curl -s localhost:8000 | grep -q "bot running" && echo "  bot OK" || echo "  bot FAILED"

echo "[deploy] Verifying dashboard via nginx (port 80)..."
HTTP=$(curl -s -o /dev/null -w "%{http_code}" localhost:80)
[ "$HTTP" = "200" ] && echo "  dashboard OK (HTTP $HTTP)" || echo "  dashboard check: HTTP $HTTP"

echo "[deploy] Verifying webhook endpoint..."
WH=$(curl -s -o /dev/null -w "%{http_code}" -X POST localhost:80/webhook \
  -H "Content-Type: application/json" -d '{}')
[ "$WH" = "422" ] && echo "  webhook OK (HTTP $WH — bot rejects empty payload as expected)" \
  || echo "  webhook check: HTTP $WH"

echo "[deploy] Done."
```

- [ ] **Step 2: Make executable and commit**

```bash
chmod +x scripts/deploy.sh
git add scripts/deploy.sh
git commit -m "feat: add deploy.sh for VPS docker compose deployment"
```

---

## Task 6: Create .env.example

**Files:**
- Create: `.env.example`

- [ ] **Step 1: Create the file**

```bash
# VPS SSH access (used by Claude Code to deploy)
VPS_HOST=
VPS_USER=ubuntu
VPS_SSH_KEY=~/.ssh/trading-bot-new.key

# Database
DATABASE_PATH=database/trades.db

# Internal ports (used by docker-compose)
BOT_PORT=8000
DASHBOARD_PORT=8501

# IG Markets broker credentials
IG_USERNAME=
IG_PASSWORD=
IG_API_KEY=
```

- [ ] **Step 2: Confirm .env.example is not in .gitignore (it should be committed)**

```bash
grep ".env.example" .gitignore && echo "PROBLEM: .env.example is gitignored" || echo "OK: .env.example will be committed"
```

- [ ] **Step 3: Commit**

```bash
git add .env.example
git commit -m "feat: add .env.example template for all required environment variables"
```

---

## Task 7: Push all changes to GitHub

- [ ] **Step 1: Verify all files are committed**

```bash
git status
```
Expected: `nothing to commit, working tree clean`

- [ ] **Step 2: Push to origin**

```bash
git push origin main
```
Expected: refs updated, no errors.

---

## Task 8: SSH into VPS + install docker-compose-plugin

Load VPS credentials from local `.env` before running SSH commands.

**Prerequisites:** SSH key must exist at `~/.ssh/trading-bot-new.key`. If not:
```bash
cp /mnt/c/Users/tanbe/Downloads/trading-bot-new.key ~/.ssh/trading-bot-new.key
chmod 600 ~/.ssh/trading-bot-new.key
```

- [ ] **Step 1: Load VPS vars from .env**

```bash
export $(grep -v '^#' .env | grep -E '^(VPS_HOST|VPS_USER|VPS_SSH_KEY)' | xargs)
```

- [ ] **Step 2: Test SSH connectivity**

```bash
ssh -i "$VPS_SSH_KEY" -o StrictHostKeyChecking=no "$VPS_USER@$VPS_HOST" "echo connected"
```
Expected: `connected`

- [ ] **Step 3: Check if docker-compose-plugin is already installed**

```bash
ssh -i "$VPS_SSH_KEY" "$VPS_USER@$VPS_HOST" "docker compose version 2>/dev/null || echo NOT_INSTALLED"
```
If output contains `Docker Compose version`, skip Step 4.

- [ ] **Step 4: Install docker-compose-plugin (only if Step 3 showed NOT_INSTALLED)**

```bash
ssh -i "$VPS_SSH_KEY" "$VPS_USER@$VPS_HOST" \
  "sudo apt-get update -qq && sudo apt-get install -y docker-compose-plugin"
```

- [ ] **Step 5: Verify install**

```bash
ssh -i "$VPS_SSH_KEY" "$VPS_USER@$VPS_HOST" "docker compose version"
```
Expected: `Docker Compose version v2.x.x`

---

## Task 9: Backup data from old container (Step 2.5 from spec)

**Do this before any code changes on VPS.**

- [ ] **Step 1: Confirm trades.db exists inside the running bot container**

```bash
ssh -i "$VPS_SSH_KEY" "$VPS_USER@$VPS_HOST" \
  "docker exec bot ls -lh /app/database/"
```
Expected: `trades.db` visible in output. If not present, check if the file is on the host at `/home/ubuntu/trading_bot/database/trades.db` instead.

- [ ] **Step 2: Create a timestamped backup inside the container**

```bash
ssh -i "$VPS_SSH_KEY" "$VPS_USER@$VPS_HOST" \
  "docker exec bot cp /app/database/trades.db /app/database/trades.db.bak_$(date +%Y%m%d_%H%M%S)"
```

- [ ] **Step 3: Record trade count (baseline for post-deploy verification)**

```bash
ssh -i "$VPS_SSH_KEY" "$VPS_USER@$VPS_HOST" \
  "docker exec bot sqlite3 /app/database/trades.db 'SELECT COUNT(*) FROM trades;'"
```
Note this number — verify it matches after cutover.

- [ ] **Step 4: Also copy backup to host filesystem (extra safety)**

```bash
ssh -i "$VPS_SSH_KEY" "$VPS_USER@$VPS_HOST" \
  "docker cp bot:/app/database/trades.db /home/ubuntu/trades.db.bak_$(date +%Y%m%d_%H%M%S)"
```
Expected: file appears at `/home/ubuntu/trades.db.bak_*` on host.

---

## Task 10: Git pull + verify .env on VPS

- [ ] **Step 1: Pull latest code on VPS**

```bash
ssh -i "$VPS_SSH_KEY" "$VPS_USER@$VPS_HOST" \
  "cd /home/ubuntu/trading_bot && git pull origin main"
```
Expected: shows new files (`docker-compose.yml`, `dashboard/Dockerfile`, etc.).

- [ ] **Step 2: Confirm new files are present**

```bash
ssh -i "$VPS_SSH_KEY" "$VPS_USER@$VPS_HOST" \
  "ls /home/ubuntu/trading_bot/docker-compose.yml /home/ubuntu/trading_bot/dashboard/Dockerfile /home/ubuntu/trading_bot/nginx/trading.conf"
```
Expected: all three paths printed without error.

- [ ] **Step 3: Verify .env exists on VPS**

```bash
ssh -i "$VPS_SSH_KEY" "$VPS_USER@$VPS_HOST" \
  "test -f /home/ubuntu/trading_bot/.env && echo EXISTS || echo MISSING"
```
Expected: `EXISTS`. If `MISSING` — **STOP**. The `.env` must be created on the VPS manually before proceeding. Never copy credentials over SSH in plaintext.

- [ ] **Step 4: Verify .env has real IG credentials (non-empty values)**

```bash
ssh -i "$VPS_SSH_KEY" "$VPS_USER@$VPS_HOST" \
  "cd /home/ubuntu/trading_bot && grep -c '^IG_USERNAME=.\+' .env"
```
Expected: `1`. If `0` — **STOP**. IG credentials are missing from `.env` on VPS. Add them before proceeding.

```bash
ssh -i "$VPS_SSH_KEY" "$VPS_USER@$VPS_HOST" \
  "cd /home/ubuntu/trading_bot && grep -c '^IG_PASSWORD=.\+' .env && grep -c '^IG_API_KEY=.\+' .env"
```
Expected: two lines each showing `1`.

---

## Task 11: Pre-build images on VPS

Building before cutover means downtime is minimised — images are ready before the old container stops.

- [ ] **Step 1: Build all images**

```bash
ssh -i "$VPS_SSH_KEY" "$VPS_USER@$VPS_HOST" \
  "cd /home/ubuntu/trading_bot && docker compose build 2>&1 | tail -20"
```
Expected: ends with lines like `=> exporting to image` and no `ERROR`. This takes 2-5 minutes first time (pip installs).

- [ ] **Step 2: Confirm images exist**

```bash
ssh -i "$VPS_SSH_KEY" "$VPS_USER@$VPS_HOST" \
  "docker images | grep -E 'trading_bot|REPOSITORY'"
```
Expected: `trading_bot-bot` and `trading_bot-dashboard` images present.

---

## Task 12: Pause — confirm cutover with user

**This is the hard stop before the old container is replaced.**

- [ ] **Step 1: Report pre-cutover state to user**

Run on VPS:
```bash
ssh -i "$VPS_SSH_KEY" "$VPS_USER@$VPS_HOST" \
  "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
```
Show output to user. Old `bot` container should be `Up X hours` on port 80.

- [ ] **Step 2: Ask user to confirm**

Present this message to the user:

> "Pre-build complete. The old `bot` container is still running on port 80 and accepting webhooks.
>
> Next step: `docker compose up -d` will stop the old container and start bot + dashboard + nginx simultaneously. Downtime will be ~10-30 seconds.
>
> **Type 'go' to proceed with cutover, or 'abort' to stop here.**"

- [ ] **Step 3: Wait for user confirmation before proceeding to Task 13.**

If user says abort — leave old container running, do not proceed.

---

## Task 13: Cutover — docker compose up -d

Only execute after user confirms in Task 12.

- [ ] **Step 1: Start all three containers**

```bash
ssh -i "$VPS_SSH_KEY" "$VPS_USER@$VPS_HOST" \
  "cd /home/ubuntu/trading_bot && docker compose up -d"
```
Expected output includes:
```
Container trading_bot-bot-1      Started
Container trading_bot-dashboard-1 Started
Container trading_bot-nginx-1    Started
```

- [ ] **Step 2: Wait 5 seconds for containers to initialise, then check status**

```bash
ssh -i "$VPS_SSH_KEY" "$VPS_USER@$VPS_HOST" \
  "cd /home/ubuntu/trading_bot && sleep 5 && docker compose ps"
```
Expected: all three services show `running` state. If any shows `Exit` or `Restarting`, run Task 14 Step 6 (debug) immediately.

---

## Task 14: Post-deploy verification

- [ ] **Step 1: Verify bot health (direct internal port)**

```bash
ssh -i "$VPS_SSH_KEY" "$VPS_USER@$VPS_HOST" \
  "curl -s localhost:8000"
```
Expected: `{"status":"bot running"}`

- [ ] **Step 2: Verify dashboard via nginx (port 80)**

```bash
ssh -i "$VPS_SSH_KEY" "$VPS_USER@$VPS_HOST" \
  "curl -s -o /dev/null -w 'HTTP %{http_code}\n' localhost:80"
```
Expected: `HTTP 200`

- [ ] **Step 3: Verify webhook endpoint through nginx**

```bash
ssh -i "$VPS_SSH_KEY" "$VPS_USER@$VPS_HOST" \
  "curl -s -o /dev/null -w 'HTTP %{http_code}\n' -X POST localhost:80/webhook \
   -H 'Content-Type: application/json' -d '{}'"
```
Expected: `HTTP 422` — bot is reachable and correctly rejecting an empty payload (FastAPI validation error).

- [ ] **Step 4: Verify database trade count unchanged**

```bash
ssh -i "$VPS_SSH_KEY" "$VPS_USER@$VPS_HOST" \
  "cd /home/ubuntu/trading_bot && docker compose exec bot sqlite3 /app/database/trades.db 'SELECT COUNT(*) FROM trades;'"
```
Expected: same number recorded in Task 9 Step 3. If lower — data loss has occurred; restore from `/home/ubuntu/trades.db.bak_*`.

- [ ] **Step 5: Confirm old standalone bot container is gone**

```bash
ssh -i "$VPS_SSH_KEY" "$VPS_USER@$VPS_HOST" \
  "docker ps -a --format '{{.Names}}' | grep '^bot$' && echo STILL_RUNNING || echo OK_REPLACED"
```
Expected: `OK_REPLACED`

- [ ] **Step 6: If any container is not running — check logs**

```bash
ssh -i "$VPS_SSH_KEY" "$VPS_USER@$VPS_HOST" \
  "cd /home/ubuntu/trading_bot && docker compose logs --tail=50"
```
Common failures:
- `dashboard` exits → check `requirements.txt` has streamlit; check `database/` volume path
- `nginx` exits → config syntax error; run `docker compose exec nginx nginx -t`
- `bot` exits → `.env` missing a required var; check `docker compose logs bot`

- [ ] **Step 7: Final status summary**

```bash
ssh -i "$VPS_SSH_KEY" "$VPS_USER@$VPS_HOST" \
  "cd /home/ubuntu/trading_bot && docker compose ps"
```
All three containers must show `running`. Phase 1C is complete when this passes.
