import itertools
from datetime import datetime

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


def fetch_candles(ig_service, symbol: str, timeframe: str, count: int) -> list:
    config = EPIC_CONFIG.get(symbol.upper())
    if not config:
        raise ValueError(f"Unknown symbol: {symbol}")

    result = ig_service.fetch_historical_prices_by_epic_and_num_points(
        epic=config["epic"],
        resolution=timeframe.upper(),
        numpoints=count,
    )

    prices_raw = result.get("prices")
    if not prices_raw:
        raise RuntimeError(f"No price data returned for {symbol}")

    candles = []
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


def _lot_size(sl_distance: float, value_per_point: float) -> float:
    if sl_distance <= 0:
        return 0.1
    return round(max(0.1, min(10.0, RISK_PER_TRADE / (sl_distance * value_per_point))), 2)


def run_backtest(strategy, candles: list, symbol: str) -> dict:
    """80/20 split — signals generated on full set for warmup, trades only on test portion."""
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
            should_close = (
                last or
                (open_trade["direction"] == "BUY"  and sig["signal"] == "SELL") or
                (open_trade["direction"] == "SELL" and sig["signal"] == "BUY")
            )
            if should_close:
                ep = open_trade["entry_price"]
                xp = candle["close"]
                d  = open_trade["direction"]
                pnl = ((xp - ep) if d == "BUY" else (ep - xp)) * open_trade["size"] * vpp
                try:
                    dur = int((datetime.fromisoformat(candle["time"]) - datetime.fromisoformat(open_trade["entry_time"])).total_seconds() / 60)
                except Exception:
                    dur = 0
                trades.append({
                    "entry_time":    open_trade["entry_time"],
                    "exit_time":     candle["time"],
                    "direction":     d,
                    "entry_price":   ep,
                    "exit_price":    xp,
                    "pnl":           round(pnl, 2),
                    "duration_mins": max(0, dur),
                })
                open_trade = None

        if open_trade is None and sig["signal"] in ("BUY", "SELL"):
            sl_dist = candle["high"] - candle["low"]
            open_trade = {
                "direction":   sig["signal"],
                "entry_price": candle["close"],
                "entry_time":  candle["time"],
                "size":        _lot_size(sl_dist, vpp),
            }

    return {
        "trades":           trades,
        "benchmark_return": calc_benchmark_return(test),
        "candles_total":    len(candles),
        "candles_train":    split,
        "candles_test":     len(test),
    }


def run_parameter_sweep(strategy_class, candles: list, symbol: str, param_grid: dict) -> list:
    keys = list(param_grid.keys())
    results = []
    for combo in itertools.product(*param_grid.values()):
        params = dict(zip(keys, combo))
        result = run_backtest(strategy_class(params=params), candles, symbol)
        result["params"] = params
        results.append(result)
    return results
