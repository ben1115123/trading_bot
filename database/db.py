import sqlite3
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Get database path from environment or use default
DATABASE_PATH = os.getenv("DATABASE_PATH", "database/trades.db")


def get_connection():
    """
    Returns a sqlite3 connection to the database file.
    Creates the database directory if it doesn't exist.
    Uses check_same_thread=False to allow multi-threaded access.
    """
    # Ensure the database directory exists
    db_dir = os.path.dirname(DATABASE_PATH)
    if db_dir:
        Path(db_dir).mkdir(parents=True, exist_ok=True)

    # Connect with check_same_thread=False for multi-threaded access
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    return conn


def init_db():
    """
    Initialize the database by creating all required tables if they don't exist.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Create trades table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp     TEXT NOT NULL,
            symbol        TEXT NOT NULL,
            direction     TEXT NOT NULL,
            size          REAL NOT NULL,
            entry_price   REAL NOT NULL,
            sl            REAL,
            tp            REAL,
            deal_id       TEXT,
            pnl           REAL,
            source        TEXT DEFAULT 'indicator',
            strategy_name TEXT DEFAULT 'manual',
            status        TEXT DEFAULT 'OPEN'
        )
    """)

    # Create backtest_results table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS backtest_results (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_name TEXT NOT NULL,
            symbol        TEXT NOT NULL,
            timeframe     TEXT NOT NULL,
            total_trades  INTEGER,
            win_rate      REAL,
            profit        REAL,
            drawdown      REAL,
            sharpe_ratio  REAL,
            score         REAL,
            run_at        TEXT NOT NULL
        )
    """)

    # Create active_strategy table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS active_strategy (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_name TEXT NOT NULL,
            symbol        TEXT NOT NULL,
            updated_at    TEXT NOT NULL
        )
    """)

    # Commit changes and close connection
    conn.commit()
    conn.close()
