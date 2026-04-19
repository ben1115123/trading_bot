import sqlite3
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Anchor database path to project root
_BASE_DIR = Path(__file__).resolve().parent.parent  # project root
DATABASE_PATH = os.getenv("DATABASE_PATH", str(_BASE_DIR / "database" / "trades.db"))


def get_connection():
    """
    Returns a sqlite3 connection to the database file.
    Creates the database directory if it doesn't exist.
    Adds row_factory for dict-like row access in models.py.
    """
    # Ensure the database directory exists
    db_dir = os.path.dirname(DATABASE_PATH)
    if db_dir:
        Path(db_dir).mkdir(parents=True, exist_ok=True)

    # Connect to database
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    Initialize the database by creating all required tables if they don't exist.
    Enables WAL mode to prevent read/write contention.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Enable WAL mode for better concurrency
    cursor.execute("PRAGMA journal_mode=WAL")

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
            updated_at    TEXT NOT NULL,
            UNIQUE(symbol)
        )
    """)

    # Commit changes and close connection
    conn.commit()
    conn.close()
