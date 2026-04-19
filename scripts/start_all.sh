#!/bin/bash
echo "Starting trading bot..."
sudo systemctl start trading_bot
echo "Starting dashboard..."
sudo systemctl start dashboard
echo "Done. Run scripts/status.sh to check."
