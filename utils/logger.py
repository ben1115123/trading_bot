import csv
from datetime import datetime

def log_trade(symbol, signal):
    with open("logs/trade_log.csv", "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([datetime.now(), symbol, signal])