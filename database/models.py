from datetime import datetime, timedelta, timezone
from database.db import get_connection
from engine_version import CURRENT_ENGINE_VERSION
from spread_model import CURRENT_SPREAD_MODEL, spread_table_sha
from paper_model import CURRENT_PAPER_MODEL
from database.paper_filters import TERMINAL_OUTCOMES, UNRESOLVABLE_OUTCOMES
from market_hours import is_entry_allowed


def log_trade(trade_data: dict) -> int:
    """
    Insert a trade record into the trades table.

    Args:
        trade_data (dict): Trade data with keys:
            - timestamp (optional): ISO format string, defaults to UTC now
            - symbol (required): Trading symbol
            - direction (required): 'BUY' or 'SELL'
            - size (required): Trade size/lot
            - entry_price (required): Entry price
            - sl (optional): Stop loss price
            - tp (optional): Take profit price
            - deal_id (optional): IG deal ID
            - pnl (optional): Profit/loss (NULL until closed)
            - source (optional): Source of signal, defaults to 'indicator'
            - strategy_name (optional): Strategy name, defaults to 'manual'
            - status (optional): Trade status, defaults to 'OPEN'

    Returns:
        int: The id (lastrowid) of the inserted trade
    """
    # Validate required fields at start (Fix C2)
    required = ('symbol', 'direction', 'size', 'entry_price')
    missing = [f for f in required if f not in trade_data]
    if missing:
        raise ValueError(f"log_trade missing required fields: {missing}")

    # Work on a copy to avoid mutating caller's dict (Fix I1)
    data = trade_data.copy()

    # Set defaults for optional fields
    if 'timestamp' not in data:
        data['timestamp'] = datetime.now(timezone.utc).isoformat()
    if 'source' not in data:
        data['source'] = 'indicator'
    if 'strategy_name' not in data:
        data['strategy_name'] = 'manual'
    if 'status' not in data:
        data['status'] = 'OPEN'

    # Set optional nullable fields to None if not provided
    if 'sl' not in data:
        data['sl'] = None
    if 'tp' not in data:
        data['tp'] = None
    if 'deal_id' not in data:
        data['deal_id'] = None
    if 'deal_reference' not in data:
        data['deal_reference'] = None
    if 'pnl' not in data:
        data['pnl'] = None

    for col in ('spread', 'vix_level', 'ema200_daily', 'price_vs_ema200',
                'atr_at_entry', 'day_of_week', 'session'):
        if col not in data:
            data[col] = None

    conn = get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO trades
            (timestamp, symbol, direction, size, entry_price, sl, tp,
             deal_id, deal_reference, pnl, source, strategy_name, status,
             spread, vix_level, ema200_daily, price_vs_ema200,
             atr_at_entry, day_of_week, session)
            VALUES
            (:timestamp, :symbol, :direction, :size, :entry_price, :sl, :tp,
             :deal_id, :deal_reference, :pnl, :source, :strategy_name, :status,
             :spread, :vix_level, :ema200_daily, :price_vs_ema200,
             :atr_at_entry, :day_of_week, :session)
        """, data)

        conn.commit()
        trade_id = cursor.lastrowid
    finally:
        conn.close()

    return trade_id


def upsert_position(pos: dict) -> None:
    required = ('deal_id', 'symbol', 'direction', 'size', 'open_price', 'updated_at')
    missing = [f for f in required if f not in pos]
    if missing:
        raise ValueError(f"upsert_position missing required fields: {missing}")

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO positions
                (deal_id, symbol, direction, size, open_price,
                 current_price, unrealised_pnl, updated_at)
            VALUES
                (:deal_id, :symbol, :direction, :size, :open_price,
                 :current_price, :unrealised_pnl, :updated_at)
            ON CONFLICT(deal_id) DO UPDATE SET
                current_price  = excluded.current_price,
                unrealised_pnl = excluded.unrealised_pnl,
                updated_at     = excluded.updated_at
        """, {
            "deal_id":       pos["deal_id"],
            "symbol":        pos["symbol"],
            "direction":     pos["direction"],
            "size":          pos["size"],
            "open_price":    pos["open_price"],
            "current_price": pos.get("current_price"),
            "unrealised_pnl": pos.get("unrealised_pnl"),
            "updated_at":    pos["updated_at"],
        })
        conn.commit()
    finally:
        conn.close()


def get_positions() -> list:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM positions ORDER BY updated_at DESC")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def clear_closed_positions(active_deal_ids: list) -> None:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        if active_deal_ids:
            placeholders = ",".join("?" * len(active_deal_ids))
            cursor.execute(
                f"DELETE FROM positions WHERE deal_id NOT IN ({placeholders})",
                active_deal_ids,
            )
        else:
            cursor.execute("DELETE FROM positions")
        conn.commit()
    finally:
        conn.close()


def upsert_heartbeat(name: str, details: str = "") -> None:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO heartbeat (name, last_beat, details)
            VALUES (:name, :last_beat, :details)
            ON CONFLICT(name) DO UPDATE SET
                last_beat = excluded.last_beat,
                details   = excluded.details
        """, {
            "name":      name,
            "last_beat": datetime.now(timezone.utc).isoformat(),
            "details":   details,
        })
        conn.commit()
    finally:
        conn.close()


def log_candle_source_compare(row: dict) -> None:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO candle_source_compare
                (checked_at, symbol, timeframe, yf_close, yf_time,
                 stream_close, stream_time, delta_pips)
            VALUES
                (:checked_at, :symbol, :timeframe, :yf_close, :yf_time,
                 :stream_close, :stream_time, :delta_pips)
        """, {
            "checked_at":   datetime.now(timezone.utc).isoformat(),
            "symbol":       row["symbol"],
            "timeframe":    row["timeframe"],
            "yf_close":     row.get("yf_close"),
            "yf_time":      row.get("yf_time"),
            "stream_close": row.get("stream_close"),
            "stream_time":  row.get("stream_time"),
            "delta_pips":   row.get("delta_pips"),
        })
        conn.commit()
    finally:
        conn.close()


def close_trade(deal_id: str, close_price=None, close_time=None, realised_pnl=None) -> int:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE trades
            SET close_price = ?,
                close_time  = ?,
                pnl         = ?,
                status      = 'CLOSED'
            WHERE deal_id = ?
              AND status   = 'OPEN'
        """, (close_price, close_time, realised_pnl, deal_id))
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def get_open_trade_deal_ids() -> list:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT deal_id FROM trades WHERE status = 'OPEN' AND deal_id IS NOT NULL")
        return [row["deal_id"] for row in cursor.fetchall()]
    finally:
        conn.close()


def get_trade_by_deal_id(deal_id: str) -> dict | None:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trades WHERE deal_id = ? LIMIT 1", (deal_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def insert_backtest_result(result: dict) -> int:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO backtest_results
                (strategy_name, symbol, timeframe, run_at,
                 candles_total, candles_train, candles_test,
                 total_trades, win_rate, total_profit, max_drawdown,
                 sharpe_ratio, benchmark_return, params_json, strategy_type,
                 engine_version, spread_model, spread_table_sha)
            VALUES
                (:strategy_name, :symbol, :timeframe, :run_at,
                 :candles_total, :candles_train, :candles_test,
                 :total_trades, :win_rate, :total_profit, :max_drawdown,
                 :sharpe_ratio, :benchmark_return, :params_json, :strategy_type,
                 :engine_version, :spread_model, :spread_table_sha)
        """, {
            **result,
            "engine_version":   result.get("engine_version", CURRENT_ENGINE_VERSION),
            "spread_model":     result.get("spread_model", CURRENT_SPREAD_MODEL),
            "spread_table_sha": result.get("spread_table_sha",
                                           spread_table_sha(result.get("spread_table"))),
        })
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def insert_backtest_trade(trade: dict) -> None:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO backtest_trades
                (backtest_id, entry_time, exit_time, direction,
                 entry_price, exit_price, pnl, duration_mins)
            VALUES
                (:backtest_id, :entry_time, :exit_time, :direction,
                 :entry_price, :exit_price, :pnl, :duration_mins)
        """, trade)
        conn.commit()
    finally:
        conn.close()


def insert_backtest_trades(trades: list) -> None:
    """Bulk insert — one connection, one transaction for the whole list."""
    if not trades:
        return
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.executemany("""
            INSERT INTO backtest_trades
                (backtest_id, entry_time, exit_time, direction,
                 entry_price, exit_price, pnl, duration_mins)
            VALUES
                (:backtest_id, :entry_time, :exit_time, :direction,
                 :entry_price, :exit_price, :pnl, :duration_mins)
        """, trades)
        conn.commit()
    finally:
        conn.close()


def get_spread_samples(symbol: str = None, since: str = None,
                       market_open_only: bool = True) -> list:
    """Captured spread observations, for calibrating a measured spread model.

    DEDUP CAVEAT — read before aggregating. signal_log holds one row per
    (symbol, timeframe, strategy_name) check, so a symbol watched by several
    strategies records the SAME market spread several times in the same minute.
    Measured 2026-08-16: 80,139 rows collapse to 45,733 distinct
    (symbol, minute) groups, i.e. ~1.75x duplication, and it is uneven —
    EURUSD logged 480 checks/day against AUDUSD's 96. Averaging the raw rows
    would silently weight whichever symbol has the most strategies attached.

    This collapses to one sample per (symbol, minute) before returning, so
    callers get market observations rather than check counts.

    MARKET-OPEN FILTER (default ON) — this is not a refinement, it is a
    prerequisite. The raw pool is contaminated with observations taken while
    the book was SHUT: the stream keeps delivering ticks with freshly stamped
    timestamps carrying a closed-market quote, so get_spread()'s 900s
    staleness guard does not catch them. Measured on the 2026-08-16/17 pool,
    every single observation above 3 pips came from a weekend, none from the
    Monday session:

        symbol   raw pool                          filtered
        EURUSD   med 0.60  p90  1.50  max 10.50    med 0.60  p90 0.60  max 0.90
        GBPUSD   med 0.90  p90 14.60  max 24.50    med 0.90  p90 0.90  max 1.50
        AUDUSD   med 0.60  p90  5.60  max 16.00    med 0.60  p90 0.90  max 0.90
        USDCAD   med 1.30  p90  6.70  max  8.60    med 1.30  p90 2.10  max 5.70
        US500    med 0.60  p90  0.60  max  1.50    med 0.60  p90 0.60  max 0.60
        US100    med 2.00  p90  2.00  max  5.00    med 2.00  p90 2.00  max 2.00

    Calibrating on the raw pool would produce a constant ~10x too wide —
    reproducing the NORMAL_SPREADS error (findings doc finding 15) that this
    measurement work exists to fix. Note that MEDIANS DO NOT MOVE on any
    symbol: the filter removes a fabricated tail without reshaping the data,
    which is the evidence that it is removing contamination rather than
    inconvenient observations.

    WHY is_entry_allowed AND NOT is_market_open. The constant feeds a cost
    model for trades the bot can actually place, and after the finding-23 fix
    it will never open a position in the Sunday 20:00-22:59 reopen. Measured
    on the same pool: is_market_open keeps 507 samples and leaves 26 wide
    survivors (the whole reopen ramp); is_entry_allowed keeps 458 and leaves
    exactly 1 — a real USDCAD quote at Sun 23:01.

    THIS ONLY BECAME THE CORRECT PREDICATE ONCE _is_blocked WAS FIXED. Before
    that, _is_blocked never fired for FX and the bot really did trade the
    reopen — 21 weekend trades at 10-17 pip spreads — so the window would have
    had to be INCLUDED to model live behaviour honestly. Filtering it out
    while the bot still traded there would have been the engine-flattery
    mistake in a new place.

    KNOWN LIMITATION OF THE MODEL SHAPE, not of this filter — read this before
    building a spread table. is_entry_allowed governs ENTRIES. A position held
    through Friday 20:45 to Sunday 23:00 can still be EXITED at reopen
    spreads, and that cost is excluded from anything calibrated here.
    SPREAD_COSTS is a single round-trip constant and cannot express an
    asymmetric entry/exit cost, so this cannot be fixed by filtering
    differently — it needs a different model shape. Recorded, not solved.

    Pass market_open_only=False for raw inspection only. Never for calibration.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        where, params = ["spread IS NOT NULL"], []
        if symbol:
            where.append("symbol = ?")
            params.append(symbol)
        if since:
            where.append("checked_at >= ?")
            params.append(since)
        cursor.execute(f"""
            SELECT symbol,
                   substr(checked_at, 1, 16) AS minute,
                   AVG(spread)               AS spread,
                   COUNT(*)                  AS checks_collapsed
            FROM signal_log
            WHERE {' AND '.join(where)}
            GROUP BY symbol, minute
            ORDER BY minute ASC
        """, params)
        rows = [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

    if not market_open_only:
        return rows

    # Applied in Python rather than SQL: the predicate is weekday-and-hour
    # logic that lives in market_hours.py, and duplicating it as a SQL
    # expression would create the fourth boundary definition this codebase
    # keeps producing (findings 20, 22, 23).
    kept = []
    for row in rows:
        try:
            when = datetime.fromisoformat(row["minute"])
        except ValueError:
            continue          # unparseable stamp: drop rather than assume open
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if is_entry_allowed(row["symbol"], when):
            kept.append(row)
    return kept


def get_backtest_results(engine_version: str | None = CURRENT_ENGINE_VERSION) -> list:
    """Backtest results, filtered to one engine trade-model version.

    Defaults to CURRENT_ENGINE_VERSION so that callers which rank, score or
    promote can never silently mix models — a pre-parity row and a post-parity
    row are not comparable numbers, and the whole point of the column is that
    nobody has to remember that.

    Pass engine_version=None to read every row regardless of version. That is
    for archive/inspection only (dashboards showing history, migration audits).
    Never pass None from anything that feeds a promotion decision.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        if engine_version is None:
            cursor.execute("SELECT * FROM backtest_results ORDER BY run_at DESC")
        else:
            cursor.execute(
                "SELECT * FROM backtest_results WHERE engine_version = ? "
                "ORDER BY run_at DESC",
                (engine_version,),
            )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_backtest_trades(backtest_id: int) -> list:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM backtest_trades WHERE backtest_id = ? ORDER BY entry_time ASC",
            (backtest_id,)
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_recent_trades(limit: int = 10) -> list:
    """
    Retrieve the most recent trades from the trades table.

    Args:
        limit (int): Number of trades to return, ordered by id DESC.
                    Defaults to 10.

    Returns:
        list: List of dicts, each representing a trade row
    """
    # Guard against limit <= 0 (Fix I2)
    if limit <= 0:
        raise ValueError(f"limit must be a positive integer, got {limit}")

    conn = get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT *
            FROM trades
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))

        rows = cursor.fetchall()
    finally:
        conn.close()

    # Convert sqlite3.Row objects to dicts
    trades = [dict(row) for row in rows]

    return trades


def insert_active_strategy(data: dict) -> int:
    required = ('strategy_name', 'symbol', 'timeframe', 'strategy_type', 'score', 'activated_at', 'params_json')
    missing = [f for f in required if f not in data]
    if missing:
        raise ValueError(f"insert_active_strategy missing required fields: {missing}")

    # Work on a copy to avoid mutating caller's dict (Fix 1)
    data = data.copy()

    conn = get_connection()
    try:
        cursor = conn.cursor()

        if 'status' not in data:
            data['status'] = 'active'
        if 'updated_at' not in data:
            data['updated_at'] = datetime.now(timezone.utc).isoformat()

        cursor.execute("""
            INSERT INTO active_strategy
                (strategy_name, symbol, timeframe, strategy_type, backtest_id,
                 score, activated_at, params_json, status, updated_at)
            VALUES
                (:strategy_name, :symbol, :timeframe, :strategy_type, :backtest_id,
                 :score, :activated_at, :params_json, :status, :updated_at)
            ON CONFLICT(symbol, timeframe, strategy_name) DO UPDATE SET
                strategy_name = excluded.strategy_name,
                timeframe = excluded.timeframe,
                strategy_type = excluded.strategy_type,
                backtest_id = excluded.backtest_id,
                score = excluded.score,
                activated_at = excluded.activated_at,
                params_json = excluded.params_json,
                status = excluded.status,
                updated_at = excluded.updated_at
        """, data)

        active_strategy_id = cursor.lastrowid

        reason = data.get('reason', 'manual')
        changed_at = data['updated_at']

        cursor.execute("""
            INSERT INTO active_strategy_history
                (strategy_name, symbol, timeframe, strategy_type, score,
                 activated_at, reason, changed_at)
            VALUES
                (:strategy_name, :symbol, :timeframe, :strategy_type, :score,
                 :activated_at, :reason, :changed_at)
        """, {
            'strategy_name': data['strategy_name'],
            'symbol': data['symbol'],
            'timeframe': data['timeframe'],
            'strategy_type': data['strategy_type'],
            'score': data['score'],
            'activated_at': data['activated_at'],
            'reason': reason,
            'changed_at': changed_at,
        })

        conn.commit()
    finally:
        conn.close()

    return active_strategy_id


def get_active_strategy(symbol: str = None, timeframe: str = None) -> dict | list | None:
    conn = get_connection()
    try:
        cursor = conn.cursor()

        if symbol:
            if timeframe:
                cursor.execute("""
                    SELECT * FROM active_strategy
                    WHERE symbol = ? AND timeframe = ? AND status = 'active'
                    LIMIT 1
                """, (symbol, timeframe))
            else:
                cursor.execute("""
                    SELECT * FROM active_strategy
                    WHERE symbol = ? AND status = 'active'
                    LIMIT 1
                """, (symbol,))
            row = cursor.fetchone()
            return dict(row) if row else None
        else:
            cursor.execute("""
                SELECT * FROM active_strategy
                WHERE status = 'active'
                ORDER BY symbol ASC
            """)
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
    finally:
        conn.close()


def get_active_strategies(symbol: str) -> list:
    """All runnable rows for a symbol — live (active) and paper."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM active_strategy
            WHERE symbol = ? AND status IN ('active', 'paper')
            ORDER BY timeframe ASC
        """, (symbol,))
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def get_active_strategy_history(limit: int = 10) -> list:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM active_strategy_history
            ORDER BY changed_at DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_webhook_strategy(symbol: str, strategy_name: str) -> dict | None:
    """Return active_strategy row for symbol+strategy_name regardless of status."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM active_strategy
            WHERE symbol = ? AND strategy_name = ?
            LIMIT 1
        """, (symbol, strategy_name))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def log_correlation_event(strategy_name: str, direction: str, symbols: list) -> None:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO correlation_events
                (checked_at, strategy_name, direction, symbols, count)
            VALUES (?, ?, ?, ?, ?)
        """, (
            datetime.now(timezone.utc).isoformat(),
            strategy_name, direction, ",".join(symbols), len(symbols),
        ))
        conn.commit()
    finally:
        conn.close()


def get_correlation_events(limit: int = 100) -> list:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM correlation_events ORDER BY checked_at DESC LIMIT ?",
            (limit,))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def log_signal_check(data: dict) -> None:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO signal_log
                (checked_at, symbol, strategy_name, timeframe,
                 candle_time, signal, trade_placed, error, spread)
            VALUES
                (:checked_at, :symbol, :strategy_name, :timeframe,
                 :candle_time, :signal, :trade_placed, :error, :spread)
        """, {
            "checked_at":    data.get("checked_at", datetime.now(timezone.utc).isoformat()),
            "symbol":        data["symbol"],
            "strategy_name": data.get("strategy_name"),
            "timeframe":     data.get("timeframe"),
            "candle_time":   data.get("candle_time"),
            "signal":        data.get("signal", "NONE"),
            "trade_placed":  int(data.get("trade_placed", 0)),
            "error":         data.get("error"),
            # Observed dealing spread at check time, decimal price units.
            # NULL when the stream has no fresh observation. See
            # get_spread_samples() for the dedup caveat before aggregating.
            "spread":        data.get("spread"),
        })
        conn.commit()
    finally:
        conn.close()


def get_recent_signal_checks(limit: int = 50) -> list:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM signal_log
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def log_paper_trade(data: dict) -> None:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO paper_trades
                (checked_at, symbol, strategy_name, timeframe,
                 candle_time, signal, entry_price, sl, tp,
                 simulated_pnl, outcome, params_json, notes, session, regime,
                 paper_model, spread_model, risk_per_trade)
            VALUES
                (:checked_at, :symbol, :strategy_name, :timeframe,
                 :candle_time, :signal, :entry_price, :sl, :tp,
                 :simulated_pnl, :outcome, :params_json, :notes, :session, :regime,
                 :paper_model, :spread_model, :risk_per_trade)
        """, {
            "checked_at":    data.get("checked_at", datetime.now(timezone.utc).isoformat()),
            "symbol":        data["symbol"],
            "strategy_name": data.get("strategy_name"),
            "timeframe":     data.get("timeframe"),
            "candle_time":   data.get("candle_time"),
            "signal":        data.get("signal"),
            "entry_price":   data.get("entry_price"),
            "sl":            data.get("sl"),
            "tp":            data.get("tp"),
            "simulated_pnl": data.get("simulated_pnl"),
            "outcome":       data.get("outcome", "PENDING"),
            "params_json":   data.get("params_json"),
            "notes":         data.get("notes"),
            "session":       data.get("session"),
            "regime":        data.get("regime"),
            # Provenance of the resolver model that will compute this row's
            # simulated_pnl. Stamped at WRITE time, not resolve time, so a row
            # written under one model and resolved after a bump is still
            # attributable — the resolver reads the stamp rather than assuming
            # the current one. risk_per_trade stays NULL until the re-baseline.
            "paper_model":    data.get("paper_model", CURRENT_PAPER_MODEL),
            "spread_model":   data.get("spread_model", CURRENT_SPREAD_MODEL),
            "risk_per_trade": data.get("risk_per_trade"),
        })
        conn.commit()
    finally:
        conn.close()


# DELETED 2026-08-16: get_paper_trades(), get_paper_trade_stats() and
# get_paper_stats_by_symbol().
#
# All three had ZERO callers — every dashboard page reads paper_trades through
# raw SQL via get_connection(). Dead code that LOOKS like the canonical read
# path is a trap: it implies a filtering contract that nothing actually goes
# through, and it is part of why twelve query sites independently forgot to
# exclude shadow rows (findings doc finding 17).
#
# The canonical thing is now the PREDICATE, not the query:
# database/paper_filters.py::paper_where(). Compose it into whatever SELECT
# you need. Do not resurrect these as a query layer — three of the twelve call
# sites (a dynamic UI filter bag, an equity-curve series, and a CTE joined
# against trades + active_strategy) cannot be expressed by any reasonable
# shared signature without it becoming a query builder.


def get_pending_paper_trades() -> list:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM paper_trades
            WHERE outcome = 'PENDING'
            AND entry_price IS NOT NULL
            AND sl IS NOT NULL
            AND tp IS NOT NULL
        """)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def resolve_paper_trade(trade_id: int, outcome: str, pnl: float | None,
                        reason: str | None = None) -> None:
    """Terminate a paper row.

    outcome must be one of paper_filters.TERMINAL_OUTCOMES. The three
    unresolvable ones (REFUSED / EXPIRED / NO_HISTORY) pass pnl=None: NULL,
    never 0.0, so a query that forgets to exclude them contributes nothing to a
    SUM instead of a phantom break-even trade.

    resolved_at is stamped here rather than by the caller — it is the one place
    every terminal transition passes through, and the column exists precisely
    because row-age-at-resolution was previously unrecoverable (finding 22).
    """
    if outcome not in TERMINAL_OUTCOMES:
        raise ValueError(
            f"resolve_paper_trade: {outcome!r} is not a terminal outcome "
            f"(expected one of {TERMINAL_OUTCOMES})"
        )
    if outcome in UNRESOLVABLE_OUTCOMES and pnl is not None:
        raise ValueError(
            f"resolve_paper_trade: {outcome} must carry pnl=None, got {pnl!r} "
            f"— an unresolvable row has no simulated P&L"
        )
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE paper_trades
               SET outcome = ?, simulated_pnl = ?,
                   resolved_at = ?, resolution_reason = ?
            WHERE id = ?
        """, (outcome, pnl, datetime.now(timezone.utc).isoformat(),
              reason, trade_id))
        conn.commit()
    finally:
        conn.close()


def log_webhook_alert(data: dict) -> None:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO webhook_log
                (timestamp, symbol, direction, strategy_name, raw_payload,
                 result, block_reason, deal_reference, notes)
            VALUES
                (:timestamp, :symbol, :direction, :strategy_name, :raw_payload,
                 :result, :block_reason, :deal_reference, :notes)
        """, {
            "timestamp":     data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "symbol":        data.get("symbol", "unknown"),
            "direction":     data.get("direction", "unknown"),
            "strategy_name": data.get("strategy_name"),
            "raw_payload":   data.get("raw_payload"),
            "result":        data.get("result", "BLOCKED"),
            "block_reason":  data.get("block_reason"),
            "deal_reference": data.get("deal_reference"),
            "notes":         data.get("notes"),
        })
        conn.commit()
    finally:
        conn.close()


def get_webhook_log(limit: int = 200) -> list:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM webhook_log ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def update_trade_context(symbol: str, source: str, context: dict) -> None:
    """Update context columns on the most recently inserted trade for symbol+source."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE trades SET
                spread          = :spread,
                vix_level       = :vix_level,
                ema200_daily    = :ema200_daily,
                price_vs_ema200 = :price_vs_ema200,
                atr_at_entry    = :atr_at_entry,
                day_of_week     = :day_of_week,
                session         = :session,
                regime          = :regime
            WHERE id = (
                SELECT id FROM trades
                WHERE symbol = :symbol AND source = :source AND status = 'OPEN'
                ORDER BY id DESC LIMIT 1
            )
        """, {
            "symbol":          symbol,
            "source":          source,
            "spread":          context.get("spread"),
            "vix_level":       context.get("vix_level"),
            "ema200_daily":    context.get("ema200_daily"),
            "price_vs_ema200": context.get("price_vs_ema200"),
            "atr_at_entry":    context.get("atr_at_entry"),
            "day_of_week":     context.get("day_of_week"),
            "session":         context.get("session"),
            "regime":          context.get("regime"),
        })
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def get_trade_context_stats(symbol: str = None, source: str = None, days: int = 90) -> dict:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    conds  = ["pnl IS NOT NULL", "status = 'CLOSED'", "timestamp >= ?"]
    params: list = [cutoff]
    if symbol:
        conds.append("symbol = ?")
        params.append(symbol)
    if source:
        if source == "live_signal_loop":
            conds.append("source IN ('signal_loop', 'live_signal_loop')")
        else:
            conds.append("source = ?")
            params.append(source)
    where = " AND ".join(conds)

    conn = get_connection()
    try:
        cur = conn.cursor()

        cur.execute(f"""
            SELECT session,
                   COUNT(*) as trades,
                   SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
                   ROUND(100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
                   ROUND(SUM(pnl), 2) as total_pnl,
                   ROUND(AVG(pnl), 2) as avg_pnl
            FROM trades WHERE {where} AND session IS NOT NULL
            GROUP BY session
        """, params)
        session_stats = [dict(r) for r in cur.fetchall()]

        cur.execute(f"""
            SELECT day_of_week,
                   COUNT(*) as trades,
                   SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
                   ROUND(100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
                   ROUND(SUM(pnl), 2) as total_pnl,
                   ROUND(AVG(pnl), 2) as avg_pnl
            FROM trades WHERE {where} AND day_of_week IS NOT NULL
            GROUP BY day_of_week ORDER BY day_of_week
        """, params)
        dow_stats = [dict(r) for r in cur.fetchall()]

        cur.execute(f"""
            SELECT price_vs_ema200, direction,
                   COUNT(*) as trades,
                   SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                   ROUND(100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
                   ROUND(SUM(pnl), 2) as total_pnl
            FROM trades WHERE {where} AND price_vs_ema200 IS NOT NULL
            GROUP BY price_vs_ema200, direction ORDER BY price_vs_ema200, direction
        """, params)
        ema200_stats = [dict(r) for r in cur.fetchall()]

        cur.execute(f"""
            SELECT
                CASE
                    WHEN vix_level < 15 THEN 'Low (<15)'
                    WHEN vix_level < 20 THEN 'Normal (15-20)'
                    WHEN vix_level < 25 THEN 'Elevated (20-25)'
                    ELSE 'High (>25)'
                END as vix_bucket,
                COUNT(*) as trades,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                ROUND(100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
                ROUND(SUM(pnl), 2) as total_pnl,
                ROUND(MIN(vix_level), 1) as vix_min
            FROM trades WHERE {where} AND vix_level IS NOT NULL
            GROUP BY vix_bucket ORDER BY vix_min
        """, params)
        vix_stats = [dict(r) for r in cur.fetchall()]

        cur.execute(f"""
            SELECT symbol, ROUND(AVG(spread), 5) as avg_spread, COUNT(*) as n
            FROM trades WHERE {where} AND spread IS NOT NULL
            GROUP BY symbol ORDER BY symbol
        """, params)
        spread_stats = [dict(r) for r in cur.fetchall()]

        cur.execute(f"""
            SELECT atr_at_entry, pnl
            FROM trades WHERE {where} AND atr_at_entry IS NOT NULL
            ORDER BY atr_at_entry
        """, params)
        atr_raw = [dict(r) for r in cur.fetchall()]

    finally:
        conn.close()

    return {
        "session_stats": session_stats,
        "dow_stats":     dow_stats,
        "ema200_stats":  ema200_stats,
        "vix_stats":     vix_stats,
        "spread_stats":  spread_stats,
        "atr_raw":       atr_raw,
    }


def get_unresolved_blocked_alerts(conn, limit: int = 100) -> list:
    """
    BLOCKED webhook_log rows from the last 7 days that have not yet been
    resolved into webhook_outcome_log, with SL/TP extracted from raw_payload.
    Rows where SL/TP cannot be extracted (missing/"null") are skipped.
    """
    import json as _json

    cursor = conn.cursor()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    cursor.execute("""
        SELECT * FROM webhook_log
        WHERE result = 'BLOCKED'
          AND timestamp >= ?
          AND id NOT IN (SELECT webhook_log_id FROM webhook_outcome_log)
        ORDER BY timestamp DESC
        LIMIT ?
    """, (cutoff, limit))

    alerts = []
    for row in cursor.fetchall():
        alert = dict(row)
        try:
            payload = _json.loads(alert.get("raw_payload") or "{}")
        except (ValueError, TypeError):
            continue

        direction = alert.get("direction")
        if direction == "BUY":
            sl, tp = payload.get("long_sl"), payload.get("long_tp")
        elif direction == "SELL":
            sl, tp = payload.get("short_sl"), payload.get("short_tp")
        else:
            continue

        if sl is None or tp is None or str(sl).strip().lower() == "null" or str(tp).strip().lower() == "null":
            continue

        try:
            alert["sl_price"] = float(sl)
            alert["tp_price"] = float(tp)
        except (ValueError, TypeError):
            continue

        alerts.append(alert)

    return alerts


def insert_webhook_outcome(conn, data: dict) -> int:
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO webhook_outcome_log
            (webhook_log_id, symbol, direction, block_reason, block_timestamp,
             sl_price, tp_price, outcome, outcome_at, candles_to_hit,
             price_at_outcome, estimated_pnl, resolved_at)
        VALUES
            (:webhook_log_id, :symbol, :direction, :block_reason, :block_timestamp,
             :sl_price, :tp_price, :outcome, :outcome_at, :candles_to_hit,
             :price_at_outcome, :estimated_pnl, :resolved_at)
    """, {
        "webhook_log_id":   data.get("webhook_log_id"),
        "symbol":           data.get("symbol"),
        "direction":        data.get("direction"),
        "block_reason":     data.get("block_reason"),
        "block_timestamp":  data.get("block_timestamp"),
        "sl_price":         data.get("sl_price"),
        "tp_price":         data.get("tp_price"),
        "outcome":          data.get("outcome"),
        "outcome_at":       data.get("outcome_at"),
        "candles_to_hit":   data.get("candles_to_hit"),
        "price_at_outcome": data.get("price_at_outcome"),
        "estimated_pnl":    data.get("estimated_pnl"),
        "resolved_at":      data.get("resolved_at"),
    })
    conn.commit()
    return cursor.lastrowid


def get_webhook_outcomes(conn, days: int = 30) -> list:
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT w.timestamp, w.symbol, w.direction,
               w.block_reason, o.outcome, o.estimated_pnl,
               o.candles_to_hit
        FROM webhook_log w
        JOIN webhook_outcome_log o ON o.webhook_log_id = w.id
        WHERE w.timestamp >= datetime('now', '-{int(days)} days')
        ORDER BY w.timestamp DESC
    """)
    return [dict(row) for row in cursor.fetchall()]


def get_outcome_summary(conn, days: int = 30) -> list:
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT w.block_reason,
               COUNT(*) as total_blocked,
               SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) as would_win,
               SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) as would_lose,
               SUM(CASE WHEN outcome='UNKNOWN' THEN 1 ELSE 0 END) as unknown,
               SUM(CASE WHEN outcome='WIN' THEN estimated_pnl ELSE 0 END) as pnl_missed,
               SUM(CASE WHEN outcome='LOSS' THEN estimated_pnl ELSE 0 END) as losses_saved
        FROM webhook_outcome_log o
        JOIN webhook_log w ON w.id = o.webhook_log_id
        WHERE w.timestamp >= datetime('now', '-{int(days)} days')
        GROUP BY w.block_reason
    """)
    return [dict(row) for row in cursor.fetchall()]


def get_webhook_filter_stats(days: int = 7) -> list:
    """Counts per outcome/block_reason for the last N days. EXECUTED and PAPER appear as their own reasons."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        cursor.execute("""
            SELECT
                COALESCE(
                    CASE WHEN result IN ('EXECUTED', 'PAPER') THEN result ELSE block_reason END,
                    result
                ) AS reason,
                COUNT(*) AS count
            FROM webhook_log
            WHERE timestamp >= ?
            GROUP BY reason
            ORDER BY count DESC
        """, (cutoff,))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def insert_walkforward_run(data: dict) -> int:
    """Persist one walk-forward/stability-map/monte-carlo/permutation run.
    cache_file/cache_candle_count/cache_date_start/cache_date_end are the
    fingerprint of the exact candle set used — the piece that was missing
    when the EURUSD REJECT-vs-MARGINAL discrepancy turned out unrecoverable."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO walkforward_runs
                (run_type, strategy_name, symbol, timeframe, params_json,
                 cache_file, cache_candle_count, cache_date_start, cache_date_end,
                 windows_json, verdict, median_pf, pct_profitable, extra_json, created_at,
                 engine_version, spread_model, spread_table_sha)
            VALUES
                (:run_type, :strategy_name, :symbol, :timeframe, :params_json,
                 :cache_file, :cache_candle_count, :cache_date_start, :cache_date_end,
                 :windows_json, :verdict, :median_pf, :pct_profitable, :extra_json, :created_at,
                 :engine_version, :spread_model, :spread_table_sha)
        """, {
            "run_type":           data["run_type"],
            "strategy_name":      data["strategy_name"],
            "symbol":             data["symbol"],
            "timeframe":          data.get("timeframe"),
            "params_json":        data.get("params_json"),
            "cache_file":         data.get("cache_file"),
            "cache_candle_count": data.get("cache_candle_count"),
            "cache_date_start":   data.get("cache_date_start"),
            "cache_date_end":     data.get("cache_date_end"),
            "windows_json":       data.get("windows_json"),
            "verdict":            data.get("verdict"),
            "median_pf":          data.get("median_pf"),
            "pct_profitable":     data.get("pct_profitable"),
            "extra_json":         data.get("extra_json"),
            "created_at":         data.get("created_at", datetime.now(timezone.utc).isoformat()),
            "engine_version":     data.get("engine_version", CURRENT_ENGINE_VERSION),
            "spread_model":       data.get("spread_model", CURRENT_SPREAD_MODEL),
            "spread_table_sha":   data.get("spread_table_sha",
                                           spread_table_sha(data.get("spread_table"))),
        })
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()
