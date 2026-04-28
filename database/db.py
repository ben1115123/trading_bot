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
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp      TEXT NOT NULL,
            symbol         TEXT NOT NULL,
            direction      TEXT NOT NULL,
            size           REAL NOT NULL,
            entry_price    REAL NOT NULL,
            sl             REAL,
            tp             REAL,
            deal_id        TEXT,
            deal_reference TEXT,
            pnl            REAL,
            source         TEXT DEFAULT 'indicator',
            strategy_name  TEXT DEFAULT 'manual',
            status         TEXT DEFAULT 'OPEN'
        )
    """)

    # Create backtest_results table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS backtest_results (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_name    TEXT NOT NULL,
            symbol           TEXT NOT NULL,
            timeframe        TEXT NOT NULL,
            run_at           TEXT NOT NULL,
            candles_total    INTEGER,
            candles_train    INTEGER,
            candles_test     INTEGER,
            total_trades     INTEGER,
            win_rate         REAL,
            total_profit     REAL,
            max_drawdown     REAL,
            sharpe_ratio     REAL,
            benchmark_return REAL,
            params_json      TEXT
        )
    """)

    # Create backtest_trades table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS backtest_trades (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            backtest_id   INTEGER NOT NULL,
            entry_time    TEXT,
            exit_time     TEXT,
            direction     TEXT,
            entry_price   REAL,
            exit_price    REAL,
            pnl           REAL,
            duration_mins INTEGER,
            FOREIGN KEY (backtest_id) REFERENCES backtest_results(id)
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

    # Create positions table (live open positions, refreshed by poller)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            deal_id        TEXT PRIMARY KEY,
            symbol         TEXT NOT NULL,
            direction      TEXT NOT NULL,
            size           REAL NOT NULL,
            open_price     REAL NOT NULL,
            current_price  REAL,
            unrealised_pnl REAL,
            updated_at     TEXT NOT NULL
        )
    """)

    # Migrate trades table: add close + deal_reference columns for existing DBs
    for col, defn in [
        ("close_price",    "REAL"),
        ("close_time",     "TEXT"),
        ("deal_reference", "TEXT"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE trades ADD COLUMN {col} {defn}")
        except Exception:
            pass

    # Migrate backtest_results: add Phase 3 columns for existing DBs
    for col, defn in [
        ("candles_total",    "INTEGER"),
        ("candles_train",    "INTEGER"),
        ("candles_test",     "INTEGER"),
        ("total_profit",     "REAL"),
        ("max_drawdown",     "REAL"),
        ("benchmark_return", "REAL"),
        ("params_json",      "TEXT"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE backtest_results ADD COLUMN {col} {defn}")
        except Exception:
            pass

    # Migrate backtest_results: add strategy_type column
    try:
        cursor.execute("ALTER TABLE backtest_results ADD COLUMN strategy_type TEXT DEFAULT 'swing'")
    except Exception:
        pass

    # Commit changes and close connection
    conn.commit()
    conn.close()
