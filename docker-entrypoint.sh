#!/bin/bash
set -e
service cron start
exec uvicorn main:app --host 0.0.0.0 --port 8000
