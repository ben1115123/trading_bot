#!/bin/bash
set -e
printenv > /app/.env
chmod 600 /app/.env
service cron start
exec uvicorn main:app --host 0.0.0.0 --port 8000
