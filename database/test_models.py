import os
import sys
import tempfile
import pytest
import importlib


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    # Create a temporary file
    fd, temp_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    # Set the DATABASE_PATH environment variable BEFORE importing db module
    old_db_path = os.getenv('DATABASE_PATH')
    os.environ['DATABASE_PATH'] = temp_path

    # Reload the db module to pick up the new DATABASE_PATH
    if 'database.db' in sys.modules:
        importlib.reload(sys.modules['database.db'])

    from database.db import init_db
    from database.models import log_trade, get_recent_trades

    # Initialize the database
    init_db()

    yield temp_path

    # Cleanup
    if old_db_path is None:
        os.environ.pop('DATABASE_PATH', None)
    else:
        os.environ['DATABASE_PATH'] = old_db_path

    # Reload db module again to restore original DATABASE_PATH
    if 'database.db' in sys.modules:
        importlib.reload(sys.modules['database.db'])

    # Remove the temporary database file
    if os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except OSError:
            pass


from database.db import init_db
from database.models import log_trade, get_recent_trades


def test_log_trade(temp_db):
    """Test log_trade inserts a trade and returns a valid id."""
    trade_data = {
        'symbol': 'US500',
        'direction': 'BUY',
        'size': 0.5,
        'entry_price': 5150.0,
        'sl': 5100.0,
        'tp': 5200.0,
        'deal_id': 'deal123',
        'pnl': None,
    }

    trade_id = log_trade(trade_data)

    # Assert the returned id is an integer > 0
    assert isinstance(trade_id, int)
    assert trade_id > 0


def test_log_trade_with_defaults(temp_db):
    """Test log_trade sets defaults for optional fields."""
    trade_data = {
        'symbol': 'BTC',
        'direction': 'SELL',
        'size': 1.0,
        'entry_price': 45000.0,
    }

    trade_id = log_trade(trade_data)
    assert isinstance(trade_id, int)
    assert trade_id > 0

    # Retrieve the trade and verify defaults
    trades = get_recent_trades(limit=1)
    assert len(trades) == 1
    trade = trades[0]

    assert trade['source'] == 'indicator'
    assert trade['strategy_name'] == 'manual'
    assert trade['status'] == 'OPEN'
    assert trade['timestamp'] is not None


def test_get_recent_trades(temp_db):
    """Test get_recent_trades returns trades in correct order."""
    # Insert multiple trades
    trade1 = {
        'symbol': 'US500',
        'direction': 'BUY',
        'size': 0.5,
        'entry_price': 5150.0,
    }
    id1 = log_trade(trade1)

    trade2 = {
        'symbol': 'US100',
        'direction': 'SELL',
        'size': 1.0,
        'entry_price': 16000.0,
    }
    id2 = log_trade(trade2)

    trade3 = {
        'symbol': 'BTC',
        'direction': 'BUY',
        'size': 0.1,
        'entry_price': 45000.0,
    }
    id3 = log_trade(trade3)

    # Retrieve recent trades
    trades = get_recent_trades(limit=10)

    # Assert all trades are present
    assert len(trades) == 3

    # Assert they are ordered by id DESC (most recent first)
    assert trades[0]['id'] == id3
    assert trades[1]['id'] == id2
    assert trades[2]['id'] == id1

    # Assert values are correct
    assert trades[0]['symbol'] == 'BTC'
    assert trades[0]['direction'] == 'BUY'
    assert trades[0]['size'] == 0.1
    assert trades[0]['entry_price'] == 45000.0


def test_get_recent_trades_limit(temp_db):
    """Test get_recent_trades respects the limit parameter."""
    # Insert 5 trades
    for i in range(5):
        trade = {
            'symbol': f'SYM{i}',
            'direction': 'BUY',
            'size': 0.5,
            'entry_price': 5000.0 + i,
        }
        log_trade(trade)

    # Retrieve only 2 most recent
    trades = get_recent_trades(limit=2)
    assert len(trades) == 2

    # Retrieve all
    trades = get_recent_trades(limit=10)
    assert len(trades) == 5


def test_log_trade_full_data(temp_db):
    """Test log_trade with all fields provided."""
    from datetime import datetime, timezone

    timestamp = datetime.now(timezone.utc).isoformat()
    trade_data = {
        'timestamp': timestamp,
        'symbol': 'US500',
        'direction': 'BUY',
        'size': 0.5,
        'entry_price': 5150.0,
        'sl': 5100.0,
        'tp': 5200.0,
        'deal_id': 'deal_abc123',
        'pnl': None,
        'source': 'webhook',
        'strategy_name': 'rsi_trend',
        'status': 'OPEN',
    }

    trade_id = log_trade(trade_data)
    assert isinstance(trade_id, int)

    # Retrieve and verify all fields
    trades = get_recent_trades(limit=1)
    trade = trades[0]

    assert trade['timestamp'] == timestamp
    assert trade['symbol'] == 'US500'
    assert trade['direction'] == 'BUY'
    assert trade['size'] == 0.5
    assert trade['entry_price'] == 5150.0
    assert trade['sl'] == 5100.0
    assert trade['tp'] == 5200.0
    assert trade['deal_id'] == 'deal_abc123'
    assert trade['pnl'] is None
    assert trade['source'] == 'webhook'
    assert trade['strategy_name'] == 'rsi_trend'
    assert trade['status'] == 'OPEN'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
