#!/bin/bash
echo "=== Trading Bot (port 8000) ==="
sudo systemctl status trading_bot --no-pager -l

echo ""
echo "=== Dashboard (port 8501) ==="
sudo systemctl status dashboard --no-pager -l
