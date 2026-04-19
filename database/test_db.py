import sqlite3
import os
import sys
from pathlib import Path

# Add database module to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import init_db, get_connection

# Test database initialization
def test_init_db():
    """Test that init_db creates all required tables."""
    # Use a test database path (absolute)
    test_db_path = os.path.abspath("test_trades.db")
    os.environ["DATABASE_PATH"] = test_db_path

    # Clean up any existing test database
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    # Re-import db module to pick up new DATABASE_PATH from environment
    import importlib
    import db as db_module
    importlib.reload(db_module)

    # Initialize database
    db_module.init_db()

    # Verify database was created
    assert os.path.exists(test_db_path), f"Database file was not created at {test_db_path}"

    # Connect and check for all tables
    conn = db_module.get_connection()
    cursor = conn.cursor()

    # Query sqlite_master to get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}

    # Verify all three tables exist
    required_tables = {"trades", "backtest_results", "active_strategy"}
    assert required_tables.issubset(tables), f"Missing tables. Found: {tables}, Expected: {required_tables}"

    # Verify trades table structure
    cursor.execute("PRAGMA table_info(trades)")
    trades_columns = {row[1] for row in cursor.fetchall()}
    trades_expected = {
        "id", "timestamp", "symbol", "direction", "size", "entry_price",
        "sl", "tp", "deal_id", "pnl", "source", "strategy_name", "status"
    }
    assert trades_expected.issubset(trades_columns), f"Missing columns in trades. Found: {trades_columns}"

    # Verify backtest_results table structure
    cursor.execute("PRAGMA table_info(backtest_results)")
    backtest_columns = {row[1] for row in cursor.fetchall()}
    backtest_expected = {
        "id", "strategy_name", "symbol", "timeframe", "total_trades", "win_rate",
        "profit", "drawdown", "sharpe_ratio", "score", "run_at"
    }
    assert backtest_expected.issubset(backtest_columns), f"Missing columns in backtest_results. Found: {backtest_columns}"

    # Verify active_strategy table structure
    cursor.execute("PRAGMA table_info(active_strategy)")
    strategy_columns = {row[1] for row in cursor.fetchall()}
    strategy_expected = {"id", "strategy_name", "symbol", "updated_at"}
    assert strategy_expected.issubset(strategy_columns), f"Missing columns in active_strategy. Found: {strategy_columns}"

    conn.close()

    # Clean up test database
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    print("[PASS] All tests passed!")
    print(f"[PASS] Found tables: {tables}")
    print(f"[PASS] Trades columns: {trades_columns}")
    print(f"[PASS] Backtest results columns: {backtest_columns}")
    print(f"[PASS] Active strategy columns: {strategy_columns}")


if __name__ == "__main__":
    test_init_db()
