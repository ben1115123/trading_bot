#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/../.env"

echo "Deploying to $VPS_USER@$VPS_HOST..."

ssh -i "$VPS_SSH_KEY" -o StrictHostKeyChecking=no "$VPS_USER@$VPS_HOST" bash << 'ENDSSH'
  set -e
  cd /home/ubuntu/trading_bot

  echo "--- git pull ---"
  git pull origin main

  echo "--- docker-compose down ---"
  docker-compose down

  echo "--- docker-compose up ---"
  docker-compose up -d --build

  echo "--- container status ---"
  docker-compose ps

  echo "--- verifying bot (port 8000) ---"
  sleep 5
  curl -sf http://localhost:8000/docs > /dev/null && echo "Bot OK" || echo "Bot check failed"

  echo "--- verifying dashboard (port 8501) ---"
  curl -sf http://localhost:8501 > /dev/null && echo "Dashboard OK" || echo "Dashboard check failed"
ENDSSH

echo "Deploy complete."
