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
            params_json      TEXT,
            engine_version   TEXT NOT NULL DEFAULT 'pre-parity-v0',
            cache_file         TEXT,
            cache_candle_count INTEGER,
            cache_date_start   TEXT,
            cache_date_end     TEXT
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

    # Correlation cluster observations — report-only (2026-07-22), NOT a
    # trading gate. Logs when 3+ same-strategy positions open same-direction
    # across USD pairs simultaneously, to measure frequency before deciding
    # whether to gate it (ROADMAP.md Tier 4 correlation/exposure limits).
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS correlation_events (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            checked_at    TEXT NOT NULL,
            strategy_name TEXT NOT NULL,
            direction     TEXT NOT NULL,
            symbols       TEXT NOT NULL,
            count         INTEGER NOT NULL
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

    # Migrate trades table: add market context columns
    for stmt in [
        "ALTER TABLE trades ADD COLUMN spread REAL",
        "ALTER TABLE trades ADD COLUMN vix_level REAL",
        "ALTER TABLE trades ADD COLUMN ema200_daily REAL",
        "ALTER TABLE trades ADD COLUMN price_vs_ema200 TEXT",
        "ALTER TABLE trades ADD COLUMN atr_at_entry REAL",
        "ALTER TABLE trades ADD COLUMN day_of_week INTEGER",
        "ALTER TABLE trades ADD COLUMN session TEXT",
        "ALTER TABLE trades ADD COLUMN regime TEXT",
    ]:
        try:
            cursor.execute(stmt)
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

    # Migrate backtest_results: add engine_version. Existing rows inherit
    # 'pre-parity-v0' via the column default, which is exactly what they are —
    # produced by the engine described in docs/SESSION_20260812_FINDINGS.md
    # findings 1 and 12. See engine_version.py. NOT NULL + DEFAULT means an
    # INSERT that forgets the column still lands marked rather than NULL;
    # every write path sets it explicitly regardless.
    # (walkforward_runs gets the same treatment below, after its CREATE.)
    try:
        cursor.execute(
            "ALTER TABLE backtest_results ADD COLUMN "
            "engine_version TEXT NOT NULL DEFAULT 'pre-parity-v0'"
        )
    except Exception:
        pass

    # Migrate backtest_results: spread model provenance. engine_version alone
    # cannot answer "which spread numbers produced this row" — it versions the
    # model's STRUCTURE, while spread is a PARAMETER the structure is fed.
    # Swapping the table without a version bump would silently blur measured
    # and unmeasured rows, so the model name is stamped per row and the table
    # content is hashed alongside it (a name can be kept while numbers change,
    # a hash cannot). See spread_model.py.
    for col, defn in [
        ("spread_model",     "TEXT NOT NULL DEFAULT 'flat-roundtrip-dollars-UNCALIBRATED'"),
        ("spread_table_sha", "TEXT"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE backtest_results ADD COLUMN {col} {defn}")
        except Exception:
            pass

    # Migrate backtest_results: candle-cache provenance — the same four columns
    # walkforward_runs has carried since it was created. Finding 31: the table
    # the selector actually reads had LESS provenance than the one it does not,
    # which is why the ETF-cache contamination (finding 30) could be identified
    # EXACTLY in walkforward_runs (`cache_file LIKE '%_AV.json'`, 82 rows) but
    # only INFERRED in backtest_results (`candles_total > 5000`, 1,166 rows) —
    # reasoning about a fact that should have been recorded.
    #
    # Runs AFTER the CREATE above, per finding 18: on a fresh DB an ALTER that
    # precedes its CREATE is silently swallowed by the except and the column
    # never appears.
    #
    # ⛔ BACKFILL IS NULL, DELIBERATELY. This differs from the engine_version
    # migration directly above, which backfilled 'pre-parity-v0'. That value was
    # KNOWN — every pre-migration row was demonstrably produced by that engine.
    # Here the value is NOT known: existing rows never recorded which file they
    # used, and reconstructing it from candles_total + run_at would be a guess
    # wearing the costume of a record (same error as inventing P&L for the
    # NULL-pnl trades, finding 24, or backfilling resolved_at, finding 21).
    # NULL is the honest value and also the useful one — it distinguishes
    # "produced before provenance existed" from "produced with provenance",
    # which is the question a reader actually needs answered. Hence plain TEXT/
    # INTEGER with no DEFAULT, unlike the NOT NULL DEFAULT stamps above.
    #
    # NO engine_version BUMP. Provenance columns change nothing about how a
    # trade is entered, sized, exited or priced, so two runs over the same
    # candles still produce identical trades and P&L. Per the standing stamp
    # rule, that is not a bump.
    for col, defn in [
        ("cache_file",         "TEXT"),
        ("cache_candle_count", "INTEGER"),
        ("cache_date_start",   "TEXT"),
        ("cache_date_end",     "TEXT"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE backtest_results ADD COLUMN {col} {defn}")
        except Exception:
            pass

    # Migrate active_strategy: add Phase 5 columns
    for col, defn in [
        ("timeframe",     "TEXT"),
        ("strategy_type", "TEXT"),
        ("backtest_id",   "INTEGER"),
        ("score",         "REAL"),
        ("activated_at",  "TEXT"),
        ("params_json",   "TEXT"),
        ("status",        "TEXT DEFAULT 'active'"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE active_strategy ADD COLUMN {col} {defn}")
        except Exception:
            pass

    # Migrate active_strategy: UNIQUE(symbol) → UNIQUE(symbol, timeframe)
    try:
        cursor.execute("SELECT sql FROM sqlite_master WHERE name='active_strategy'")
        ddl = cursor.fetchone()
        if ddl and "UNIQUE(symbol)" in ddl[0] and "symbol, timeframe" not in ddl[0]:
            cursor.execute("ALTER TABLE active_strategy RENAME TO _active_strategy_old")
            cursor.execute("""
                CREATE TABLE active_strategy (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_name TEXT NOT NULL,
                    symbol        TEXT NOT NULL,
                    updated_at    TEXT NOT NULL,
                    timeframe     TEXT,
                    strategy_type TEXT,
                    backtest_id   INTEGER,
                    score         REAL,
                    activated_at  TEXT,
                    params_json   TEXT,
                    status        TEXT DEFAULT 'active',
                    UNIQUE(symbol, timeframe)
                )
            """)
            cursor.execute("""
                INSERT INTO active_strategy
                    (id, strategy_name, symbol, updated_at, timeframe, strategy_type,
                     backtest_id, score, activated_at, params_json, status)
                SELECT id, strategy_name, symbol, updated_at, timeframe, strategy_type,
                       backtest_id, score, activated_at, params_json, status
                FROM _active_strategy_old
            """)
            cursor.execute("DROP TABLE _active_strategy_old")
    except Exception:
        pass

    # Migrate active_strategy: UNIQUE(symbol, timeframe) → UNIQUE(symbol, timeframe, strategy_name)
    try:
        cursor.execute("SELECT sql FROM sqlite_master WHERE name='active_strategy'")
        ddl = cursor.fetchone()
        if ddl and "UNIQUE(symbol, timeframe)" in ddl[0] and "UNIQUE(symbol, timeframe, strategy_name)" not in ddl[0]:
            cursor.execute("ALTER TABLE active_strategy RENAME TO _active_strategy_old")
            cursor.execute("""
                CREATE TABLE active_strategy (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_name TEXT NOT NULL,
                    symbol        TEXT NOT NULL,
                    updated_at    TEXT NOT NULL,
                    timeframe     TEXT,
                    strategy_type TEXT,
                    backtest_id   INTEGER,
                    score         REAL,
                    activated_at  TEXT,
                    params_json   TEXT,
                    status        TEXT DEFAULT 'active',
                    UNIQUE(symbol, timeframe, strategy_name)
                )
            """)
            cursor.execute("""
                INSERT INTO active_strategy
                    (id, strategy_name, symbol, updated_at, timeframe, strategy_type,
                     backtest_id, score, activated_at, params_json, status)
                SELECT id, strategy_name, symbol, updated_at, timeframe, strategy_type,
                       backtest_id, score, activated_at, params_json, status
                FROM _active_strategy_old
            """)
            cursor.execute("DROP TABLE _active_strategy_old")
    except Exception:
        pass

    # Create active_strategy_history table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS active_strategy_history (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_name TEXT NOT NULL,
            symbol        TEXT NOT NULL,
            timeframe     TEXT,
            strategy_type TEXT,
            score         REAL,
            activated_at  TEXT,
            reason        TEXT,
            changed_at    TEXT NOT NULL
        )
    """)

    # Create signal_log table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signal_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            checked_at    TEXT NOT NULL,
            symbol        TEXT NOT NULL,
            strategy_name TEXT,
            timeframe     TEXT,
            candle_time   TEXT,
            signal        TEXT,
            trade_placed  INTEGER DEFAULT 0,
            error         TEXT,
            spread        REAL
        )
    """)

    # Migrate signal_log: per-check spread sample, for DBs created before the
    # column existed. MUST run AFTER the CREATE above.
    #
    # BUG FIX. 36fac3b placed this ALTER ~100 lines earlier, BEFORE signal_log
    # was created. On an existing database it worked; on a fresh one the table
    # did not yet exist, the exception was swallowed by the bare except, the
    # subsequent CREATE built signal_log without the column, and every
    # log_signal_check() raised OperationalError. The same commit contains a
    # comment on the walkforward_runs migration warning about exactly this
    # ordering trap — written, then not applied one table over.
    try:
        cursor.execute("ALTER TABLE signal_log ADD COLUMN spread REAL")
    except Exception:
        pass

    # Create paper_trades table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS paper_trades (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            checked_at    TEXT NOT NULL,
            symbol        TEXT NOT NULL,
            strategy_name TEXT,
            timeframe     TEXT,
            candle_time   TEXT,
            signal        TEXT,
            entry_price   REAL,
            sl            REAL,
            tp            REAL,
            simulated_pnl REAL,
            outcome       TEXT DEFAULT 'PENDING',
            params_json   TEXT,
            notes         TEXT,
            session       TEXT,
            paper_model    TEXT NOT NULL DEFAULT 'pre-parity-v0',
            spread_model   TEXT NOT NULL DEFAULT 'flat-roundtrip-dollars-UNCALIBRATED',
            risk_per_trade REAL,
            resolved_at       TEXT,
            resolution_reason TEXT
        )
    """)

    # Migrate paper_trades: add notes column for shadow-logging (existing DBs)
    try:
        cursor.execute("ALTER TABLE paper_trades ADD COLUMN notes TEXT")
    except Exception:
        pass

    # Migrate paper_trades: add regime column (entry-time ADX/ATR bucket tag)
    try:
        cursor.execute("ALTER TABLE paper_trades ADD COLUMN regime TEXT")
    except Exception:
        pass

    # Migrate paper_trades: add session column.
    # BUG FIX, not a new feature — models.py::log_paper_trade has been
    # INSERTing into `session` while db.py never created or migrated it
    # anywhere. The VPS database has the column by historical accident, so
    # live logging works there; any database built purely from init_db() does
    # NOT have it, and every paper-trade write raises OperationalError.
    try:
        cursor.execute("ALTER TABLE paper_trades ADD COLUMN session TEXT")
    except Exception:
        pass

    # Migrate paper_trades: resolver-model provenance. Same reasoning and same
    # sequencing as engine_version on backtest_results — the stamp lands BEFORE
    # any behaviour change, so no row can ever be written unmarked.
    #
    # paper_model is deliberately SEPARATE from engine_version: the paper
    # resolver and the backtest engine are independent models (findings doc
    # finding 2, "siblings, not subtask and parent") that change on different
    # schedules. spread_model is REUSED from 36fac3b rather than duplicated —
    # one spread model, stamped wherever it applies.
    #
    # risk_per_trade is NULL until the re-baseline populates it. Paper risk
    # varied across FOUR regimes inside pre-parity-v0 alone (per-symbol
    # overrides, then $15, then $3 from 2026-07-02, then $10 from 2026-07-08)
    # and is currently recoverable only by algebra on simulated_pnl — cheap to
    # store per row, expensive to re-derive forever. See paper_model.py.
    #
    # resolved_at / resolution_reason (paper-v2, 2026-08-17):
    #
    # resolved_at is FORWARD-ONLY and deliberately NOT backfilled. There is
    # nothing to backfill from — `checked_at` is the SIGNAL time, not the
    # resolution time, so no stored value can reconstruct how old a row was
    # when it resolved. That gap is exactly what makes finding 22's blast
    # radius unmeasurable across the 1,565 already-resolved rows. Writing an
    # inferred timestamp into the one column whose purpose is auditing
    # resolution timing would manufacture the false confidence the finding is
    # about. NULL means "resolved before resolution time was recorded" — the
    # true state.
    #
    # resolution_reason carries WHY a row terminated. The three unresolvable
    # outcomes are deliberately coarse (REFUSED / EXPIRED / NO_HISTORY) so they
    # stay countable; the specific defect goes here in prose.
    #
    # Placed AFTER the CREATE above, per finding 18.
    for col, defn in [
        ("paper_model",       "TEXT NOT NULL DEFAULT 'pre-parity-v0'"),
        ("spread_model",      "TEXT NOT NULL DEFAULT 'flat-roundtrip-dollars-UNCALIBRATED'"),
        ("risk_per_trade",    "REAL"),
        ("resolved_at",       "TEXT"),
        ("resolution_reason", "TEXT"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE paper_trades ADD COLUMN {col} {defn}")
        except Exception:
            pass

    # Create webhook_log table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS webhook_log (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp      TEXT NOT NULL,
            symbol         TEXT NOT NULL,
            direction      TEXT NOT NULL,
            strategy_name  TEXT,
            raw_payload    TEXT,
            result         TEXT NOT NULL,
            block_reason   TEXT,
            deal_reference TEXT,
            notes          TEXT
        )
    """)

    # Create webhook_outcome_log table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS webhook_outcome_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            webhook_log_id  INTEGER NOT NULL,
            symbol          TEXT NOT NULL,
            direction       TEXT NOT NULL,
            block_reason    TEXT NOT NULL,
            block_timestamp TEXT NOT NULL,
            sl_price        REAL,
            tp_price        REAL,
            outcome         TEXT,
            outcome_at      TEXT,
            candles_to_hit  INTEGER,
            price_at_outcome REAL,
            estimated_pnl   REAL,
            created_at      TEXT DEFAULT (datetime('now')),
            resolved_at     TEXT
        )
    """)

    # Migrate webhook_outcome_log: add any columns missing on existing DBs
    for col, defn in [
        ("webhook_log_id",   "INTEGER"),
        ("symbol",           "TEXT"),
        ("direction",        "TEXT"),
        ("block_reason",     "TEXT"),
        ("block_timestamp",  "TEXT"),
        ("sl_price",         "REAL"),
        ("tp_price",         "REAL"),
        ("outcome",          "TEXT"),
        ("outcome_at",       "TEXT"),
        ("candles_to_hit",   "INTEGER"),
        ("price_at_outcome", "REAL"),
        ("estimated_pnl",    "REAL"),
        ("resolved_at",      "TEXT"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE webhook_outcome_log ADD COLUMN {col} {defn}")
        except Exception:
            pass

    # Create heartbeat table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS heartbeat (
            name       TEXT PRIMARY KEY,
            last_beat  TEXT,
            details    TEXT
        )
    """)

    # Create candle_source_compare table — yfinance vs IG stream, one row per
    # symbol+timeframe per signal_loop cycle while CANDLE_SOURCE=yfinance
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS candle_source_compare (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            checked_at    TEXT NOT NULL,
            symbol        TEXT NOT NULL,
            timeframe     TEXT NOT NULL,
            yf_close      REAL,
            yf_time       TEXT,
            stream_close  REAL,
            stream_time   TEXT,
            delta_pips    REAL
        )
    """)

    # Create walkforward_runs table — persists every walk-forward/stability-map/
    # monte-carlo/permutation run so verdicts are auditable after the fact
    # (fixes the unrecoverable-verdict gap found in the EURUSD discrepancy —
    # walk-forward output used to be console-only, never stored anywhere).
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS walkforward_runs (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            run_type          TEXT NOT NULL,
            strategy_name     TEXT NOT NULL,
            symbol            TEXT NOT NULL,
            timeframe         TEXT,
            params_json       TEXT,
            cache_file        TEXT,
            cache_candle_count INTEGER,
            cache_date_start  TEXT,
            cache_date_end    TEXT,
            windows_json      TEXT,
            verdict           TEXT,
            median_pf         REAL,
            pct_profitable    REAL,
            extra_json        TEXT,
            created_at        TEXT NOT NULL,
            engine_version    TEXT NOT NULL DEFAULT 'pre-parity-v0'
        )
    """)

    # Migrate walkforward_runs: add engine_version for DBs created before this
    # column existed (the 276 local rows predate it). Must run AFTER the CREATE
    # above — on a fresh DB the table would not yet exist and the ALTER would
    # be silently swallowed by the except, leaving the column missing.
    try:
        cursor.execute(
            "ALTER TABLE walkforward_runs ADD COLUMN "
            "engine_version TEXT NOT NULL DEFAULT 'pre-parity-v0'"
        )
    except Exception:
        pass

    # Same spread provenance pair on walkforward_runs — see the backtest_results
    # migration above for why a version string alone is insufficient.
    for col, defn in [
        ("spread_model",     "TEXT NOT NULL DEFAULT 'flat-roundtrip-dollars-UNCALIBRATED'"),
        ("spread_table_sha", "TEXT"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE walkforward_runs ADD COLUMN {col} {defn}")
        except Exception:
            pass

    # Commit changes and close connection
    conn.commit()
    conn.close()
