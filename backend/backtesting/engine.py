import itertools
from datetime import datetime, timezone

from backend.backtesting.metrics import (
    calc_win_rate, calc_max_drawdown, calc_sharpe_ratio,
    calc_total_profit, calc_benchmark_return,
)

EPIC_CONFIG = {
    "US500": {"epic": "IX.D.SPTRD.IFMM.IP",    "value_per_point": 1},
    "US100": {"epic": "IX.D.NASDAQ.IFMM.IP",    "value_per_point": 1},
    "BTC":   {"epic": "CS.D.BITCOIN.CFBMU.IP",  "value_per_point": 0.1},
}

RISK_PER_TRADE = 15.0  # USD, matches live bot


_TIMEFRAME_MAP = {
    "MINUTE": "1Min", "MINUTE_2": "2Min", "MINUTE_3": "3Min",
    "MINUTE_5": "5Min", "MINUTE_10": "10Min", "MINUTE_15": "15Min",
    "MINUTE_30": "30Min", "5MIN": "5Min",
    "HOUR": "1h", "HOUR_2": "2h", "HOUR_3": "3h", "HOUR_4": "4h",
    "DAY": "D", "WEEK": "W",
}


def fetch_candles(ig_service, symbol: str, timeframe: str, count: int) -> list:
    config = EPIC_CONFIG.get(symbol.upper())
    if not config:
        raise ValueError(f"Unknown symbol: {symbol}")

    resolution = _TIMEFRAME_MAP.get(timeframe.upper(), timeframe)

    result = ig_service.fetch_historical_prices_by_epic_and_num_points(
        epic=config["epic"],
        resolution=resolution,
        numpoints=count,
    )

    prices_raw = result.get("prices")
    if prices_raw is None:
        raise RuntimeError(f"No price data returned for {symbol}")

    candles = []

    try:
        import pandas as pd
        is_df = isinstance(prices_raw, pd.DataFrame)
    except ImportError:
        is_df = False

    if is_df:
        if prices_raw.empty:
            raise RuntimeError(f"No price data returned for {symbol}")
        for ts, row in prices_raw.iterrows():
            try:
                o = (row[("bid", "Open")]  + row[("ask", "Open")])  / 2
                h = (row[("bid", "High")]  + row[("ask", "High")])  / 2
                l = (row[("bid", "Low")]   + row[("ask", "Low")])   / 2
                c = (row[("bid", "Close")] + row[("ask", "Close")]) / 2
            except (KeyError, TypeError):
                continue
            if any(v != v for v in [o, h, l, c]):  # NaN check
                continue
            candles.append({"time": str(ts), "open": float(o), "high": float(h), "low": float(l), "close": float(c)})
    else:
        if not prices_raw:
            raise RuntimeError(f"No price data returned for {symbol}")
        for row in prices_raw:
            try:
                o = (row["openPrice"]["bid"]  + row["openPrice"]["ask"])  / 2
                h = (row["highPrice"]["bid"]  + row["highPrice"]["ask"])  / 2
                l = (row["lowPrice"]["bid"]   + row["lowPrice"]["ask"])   / 2
                c = (row["closePrice"]["bid"] + row["closePrice"]["ask"]) / 2
            except (KeyError, TypeError):
                continue
            if any(v != v for v in [o, h, l, c]):  # NaN check
                continue
            candles.append({"time": row["snapshotTime"], "open": float(o), "high": float(h), "low": float(l), "close": float(c)})

    return candles


def _in_us_session(time_str: str) -> bool:
    """True if timestamp is within US market hours (Mon-Fri, 13:30-21:00 UTC covers EDT+EST)."""
    try:
        dt = datetime.fromisoformat(str(time_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt.weekday() > 4:
            return False
        minutes = dt.hour * 60 + dt.minute
        return 810 <= minutes <= 1260  # 13:30=810, 21:00=1260
    except Exception:
        return True  # don't filter on parse failure


def _lot_size(sl_distance: float, value_per_point: float) -> float:
    if sl_distance <= 0:
        return 0.1
    return round(max(0.1, min(10.0, RISK_PER_TRADE / (sl_distance * value_per_point))), 2)


def run_backtest(strategy, candles: list, symbol: str,
                 max_hold_candles: int = None,
                 session_filter: str = None) -> dict:
    """80/20 split. session_filter: 'US'|'24_7'|None. max_hold_candles: force-close after N candles."""
    split = int(len(candles) * 0.8)
    test = candles[split:]

    all_signals = strategy.generate_signals(candles)
    test_signals = all_signals[split:]

    vpp = EPIC_CONFIG[symbol.upper()]["value_per_point"]
    trades = []
    open_trade = None

    for i, sig in enumerate(test_signals):
        candle = test[i]
        last = i == len(test_signals) - 1

        if open_trade is not None:
            candles_held = i - open_trade["entry_candle_idx"]
            force_close  = max_hold_candles is not None and candles_held >= max_hold_candles
            should_close = (
                last or
                force_close or
                (open_trade["direction"] == "BUY"  and sig["signal"] == "SELL") or
                (open_trade["direction"] == "SELL" and sig["signal"] == "BUY")
            )
            if should_close:
                ep  = open_trade["entry_price"]
                xp  = candle["close"]
                d   = open_trade["direction"]
                pnl = ((xp - ep) if d == "BUY" else (ep - xp)) * open_trade["size"] * vpp
                try:
                    dur = int((datetime.fromisoformat(candle["time"]) - datetime.fromisoformat(open_trade["entry_time"])).total_seconds() / 60)
                except Exception:
                    dur = 0
                exit_reason = "max_hold" if force_close else "signal"
                trades.append({
                    "entry_time":    open_trade["entry_time"],
                    "exit_time":     candle["time"],
                    "direction":     d,
                    "entry_price":   ep,
                    "exit_price":    xp,
                    "pnl":           round(pnl, 2),
                    "duration_mins": max(0, dur),
                    "exit_reason":   exit_reason,
                })
                open_trade = None

        if session_filter == "US" and not _in_us_session(candle["time"]):
            continue

        if open_trade is None and sig["signal"] in ("BUY", "SELL"):
            sl_dist = candle["high"] - candle["low"]
            open_trade = {
                "direction":        sig["signal"],
                "entry_price":      candle["close"],
                "entry_time":       candle["time"],
                "entry_candle_idx": i,
                "size":             _lot_size(sl_dist, vpp),
            }

    return {
        "trades":           trades,
        "benchmark_return": calc_benchmark_return(test),
        "candles_total":    len(candles),
        "candles_train":    split,
        "candles_test":     len(test),
    }


def run_parameter_sweep(strategy_class, candles: list, symbol: str, param_grid: dict,
                        max_hold_candles: int = None, session_filter: str = None) -> list:
    keys = list(param_grid.keys())
    results = []
    for combo in itertools.product(*param_grid.values()):
        params = dict(zip(keys, combo))
        result = run_backtest(strategy_class(params=params), candles, symbol,
                              max_hold_candles=max_hold_candles,
                              session_filter=session_filter)
        result["params"] = params
        results.append(result)
    return results
