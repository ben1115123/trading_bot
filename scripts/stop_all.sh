#!/bin/bash
echo "Stopping trading bot..."
sudo systemctl stop trading_bot
echo "Stopping dashboard..."
sudo systemctl stop dashboard
echo "Both services stopped."
