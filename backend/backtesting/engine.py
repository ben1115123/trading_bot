import itertools
from datetime import datetime, timezone

from backend.backtesting.metrics import (
    calc_win_rate, calc_max_drawdown, calc_sharpe_ratio,
    calc_total_profit, calc_benchmark_return, calc_profit_factor,
)
from backend.backtesting.regime import classify_regimes

WF_TRAIN_MONTHS        = 6
WF_TEST_MONTHS         = 1
WF_STEP_MONTHS         = 1
WF_MIN_WINDOWS         = 4
WF_SHRUNK_TRAIN_MONTHS = 4

EPIC_CONFIG = {
    "US500":  {"epic": "IX.D.SPTRD.IFMM.IP",    "value_per_point": 1},
    "US100":  {"epic": "IX.D.NASDAQ.IFMM.IP",    "value_per_point": 1},
    "BTC":    {"epic": "CS.D.BITCOIN.CFBMU.IP",  "value_per_point": 0.1},
    "DAX":    {"epic": "IX.D.DAX.IFMS.IP",       "value_per_point": 1},
    "EURUSD": {"epic": "CS.D.EURUSD.MINI.IP",    "value_per_point": 10000},
    "GBPUSD": {"epic": "CS.D.GBPUSD.MINI.IP",    "value_per_point": 10000},
    "USDJPY": {"epic": "CS.D.USDJPY.MINI.IP",    "value_per_point": 100},
    "AUDUSD": {"epic": "CS.D.AUDUSD.MINI.IP",    "value_per_point": 10000},
    "USDCAD": {"epic": "CS.D.USDCAD.MINI.IP",    "value_per_point": 10000},
    "EURGBP": {"epic": "CS.D.EURGBP.MINI.IP",    "value_per_point": 10000},
    "NZDUSD": {"epic": "CS.D.NZDUSD.MINI.IP",    "value_per_point": 10000},
}

# Risk per trade comes from the SAME source the live path uses
# (risk_manager.get_risk_per_trade), per-symbol, so RISK_PER_TRADE_OVERRIDE
# applies here too. There used to be a literal `RISK_PER_TRADE = 15.0` here
# commented "# USD, matches live bot" — the comment was false for as long as it
# existed: live sizes at $10 (risk_manager.RISK_PER_TRADE = 10, and every
# override is also 10). Every backtest_results row written before parity-v1
# was sized 50% heavier than the bot it claimed to model.
#
# Accepted coupling: changing a live override now re-bases future backtests.
# That is what engine_version exists to make visible.
from risk_manager import get_risk_per_trade
from instrument_limits import MIN_SL_DIST

SPREAD_COSTS = {
    "EURUSD": 1.05,   # ~1 pip x $10/pip per round trip
    "US500":  0.75,   # ~0.6pt spread x $1/pt per round trip
    "DAX":    1.50,   # ~1pt spread x $1/pt per round trip
    "US100":  1.00,   # estimate
    "GBPUSD": 1.50,   # ~1.2 pips x $10/pip round trip
    "USDJPY": 0.70,   # 0.7 pips (pip=0.01 for JPY pairs) x ~$1/pip round trip — corrected 2026-07-09, was 1.20
    "AUDUSD": 0.60,   # ~0.6 pips x $10/pip round trip
    "USDCAD": 0.90,   # ~0.9 pips x $10/pip round trip
    "EURGBP": 1.00,   # 1.0 pip x ~$1/pip round trip
    "NZDUSD": 1.00,   # 1.0 pip x ~$1/pip round trip
    "XAUUSD": 20.00,  # gold — for future use
    "BTC":    0.00,   # not trading
}


_TIMEFRAME_MAP = {
    "MINUTE": "1Min", "MINUTE_2": "2Min", "MINUTE_3": "3Min",
    "MINUTE_5": "5Min", "MINUTE_10": "10Min", "MINUTE_15": "15Min",
    "MINUTE_30": "30Min", "5MIN": "5Min", "15MIN": "15Min",
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


def _lot_size(sl_distance: float, value_per_point: float, symbol: str) -> float | None:
    """Mirror of risk_manager.calculate_position_size — same order, same guards.

    Returns None when the trade cannot be sized, exactly as risk_manager does
    at :30-32. The old version returned 0.1 on a zero stop distance, which
    silently invented a position the live path would have refused to open.

    Clamp order matters and is deliberately round-THEN-clamp, matching
    risk_manager:36-44. The old version clamped then rounded; the two differ
    only exactly at the 0.1/10.0 boundaries, but "only at the boundary" is
    where a lot-limit bug lives.
    """
    if sl_distance <= 0:
        return None
    size = get_risk_per_trade(symbol) / (sl_distance * value_per_point)
    size = round(size, 2)                       # round first...
    return max(0.1, min(10.0, size))            # ...then clamp


def _parse_candle_time(t) -> datetime:
    return datetime.fromisoformat(str(t).replace("Z", "+00:00"))


def _add_months(dt: datetime, n: int) -> datetime:
    month = dt.month - 1 + n
    year  = dt.year + month // 12
    month = month % 12 + 1
    day_cap = [31, 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28,
               31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return dt.replace(year=year, month=month, day=min(dt.day, day_cap))


def run_backtest(strategy, candles: list, symbol: str,
                 max_hold_candles: int = None,
                 session_filter: str = None) -> dict:
    """80/20 split. session_filter: 'US'|'24_7'|None. max_hold_candles: force-close after N candles."""
    split = int(len(candles) * 0.8)
    test = candles[split:]

    all_signals = strategy.generate_signals(candles)
    test_signals = all_signals[split:]

    regimes = classify_regimes(candles)
    test_regimes = regimes[split:]

    trades = _simulate_trades(test, test_signals, symbol, max_hold_candles, session_filter, test_regimes)

    return {
        "trades":           trades,
        "benchmark_return": calc_benchmark_return(test),
        "candles_total":    len(candles),
        "candles_train":    split,
        "candles_test":     len(test),
    }


def _simulate_trades(test: list, test_signals: list, symbol: str,
                     max_hold_candles: int = None, session_filter: str = None,
                     regimes: list = None) -> list:
    vpp = EPIC_CONFIG[symbol.upper()]["value_per_point"]
    spread_cost = SPREAD_COSTS.get(symbol.upper(), 0.75)
    trades = []
    open_trade = None

    for i, sig in enumerate(test_signals):
        candle = test[i]
        last = i == len(test_signals) - 1

        if open_trade is not None:
            # TP check — takes priority over SL on same candle
            _tp = open_trade.get("tp_price")
            if _tp is not None:
                tp_hit = (
                    (open_trade["direction"] == "BUY"  and candle["high"] >= _tp) or
                    (open_trade["direction"] == "SELL" and candle["low"]  <= _tp)
                )
                if tp_hit:
                    ep  = open_trade["entry_price"]
                    d   = open_trade["direction"]
                    pnl = (((_tp - ep) if d == "BUY" else (ep - _tp))
                           * open_trade["size"] * vpp) - spread_cost
                    try:
                        dur = int((datetime.fromisoformat(candle["time"]) -
                                   datetime.fromisoformat(open_trade["entry_time"])
                                   ).total_seconds() / 60)
                    except Exception:
                        dur = 0
                    trades.append({
                        "entry_time":    open_trade["entry_time"],
                        "exit_time":     candle["time"],
                        "direction":     d,
                        "entry_price":   ep,
                        "exit_price":    _tp,
                        "pnl":           round(pnl, 2),
                        "duration_mins": max(0, dur),
                        "exit_reason":   "tp_hit",
                        "regime":        open_trade.get("regime"),
                    })
                    open_trade = None
                    continue

            # Dollar stop-loss: check intra-bar low/high against SL price
            sl_hit = (
                (open_trade["direction"] == "BUY"  and candle["low"]  <= open_trade["sl_price"]) or
                (open_trade["direction"] == "SELL" and candle["high"] >= open_trade["sl_price"])
            )
            if sl_hit:
                try:
                    dur = int((datetime.fromisoformat(candle["time"]) - datetime.fromisoformat(open_trade["entry_time"])).total_seconds() / 60)
                except Exception:
                    dur = 0
                # Book the loss from the ACTUAL stop price, like every other
                # exit path here and like the broker does live. The old version
                # booked a flat `-RISK_PER_TRADE - spread_cost` regardless of
                # size or stop price. That is self-consistent only while sizing
                # is unclamped: whenever the lot clamp bound (4.5-8.9% of
                # williams_r FX entries pre-floor) the real risk was smaller
                # than RISK_PER_TRADE, yet the engine still booked the full
                # amount and overstated those losses.
                _ep, _d = open_trade["entry_price"], open_trade["direction"]
                _slp    = open_trade["sl_price"]
                _pnl    = (((_slp - _ep) if _d == "BUY" else (_ep - _slp))
                           * open_trade["size"] * vpp) - spread_cost
                trades.append({
                    "entry_time":    open_trade["entry_time"],
                    "exit_time":     candle["time"],
                    "direction":     _d,
                    "entry_price":   _ep,
                    "exit_price":    _slp,
                    "pnl":           round(_pnl, 2),
                    "duration_mins": max(0, dur),
                    "exit_reason":   "sl_stop",
                    "regime":        open_trade.get("regime"),
                })
                open_trade = None
                continue  # don't re-open on same SL bar

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
                pnl = ((xp - ep) if d == "BUY" else (ep - xp)) * open_trade["size"] * vpp - spread_cost
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
                    "regime":        open_trade.get("regime"),
                })
                open_trade = None

        if session_filter == "US" and not _in_us_session(candle["time"]):
            continue

        if open_trade is None and sig["signal"] in ("BUY", "SELL"):
            entry     = candle["close"]
            custom_sl = sig.get("sl_price")
            if custom_sl is not None:
                sl_price = custom_sl
                sl_dist  = abs(entry - sl_price) or (candle["high"] - candle["low"])
            else:
                # _MIN_SL_DIST floor, mirroring live_signal_loop.py:566. The
                # engine had no floor at all, so it sized off raw candle ranges
                # the live path would never have traded: on williams_r FX
                # entries the floor binds on 45-55% of signals. Strategy-supplied
                # stops are left alone — that is the strategy's own design, and
                # rewriting it is commit 3's question, not this one's.
                sl_dist  = max(candle["high"] - candle["low"],
                               MIN_SL_DIST.get(symbol.upper(), 0.0))
                sl_price = (entry - sl_dist) if sig["signal"] == "BUY" else (entry + sl_dist)
            size = _lot_size(sl_dist, vpp, symbol.upper())
            if size is None:
                # Unsizeable (zero/negative stop distance). Live aborts here
                # (risk_manager:30-32 returns None -> place_trade returns False),
                # so the engine skips the signal rather than inventing a
                # minimum-lot position that would never have been placed.
                continue
            open_trade = {
                "direction":        sig["signal"],
                "entry_price":      entry,
                "entry_time":       candle["time"],
                "entry_candle_idx": i,
                "size":             size,
                "sl_price":         sl_price,
                "tp_price":         sig.get("tp_price"),
                "regime":           regimes[i] if regimes else None,
            }

    return trades


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


def _build_wf_windows(start, end, train_months, test_months, step_months):
    windows = []
    train_start = start
    while True:
        train_end = _add_months(train_start, train_months)
        test_end  = _add_months(train_end, test_months)
        if test_end > end:
            break
        windows.append((train_start, train_end, test_end))
        train_start = _add_months(train_start, step_months)
    return windows


def run_walk_forward(strategy_class, candles: list, symbol: str, params: dict = None,
                     max_hold_candles: int = None, session_filter: str = None) -> dict:
    """Rolling walk-forward validation. Additive mode — does not replace run_backtest's
    80/20 split. train=6mo/test=1mo/step=1mo by default; shrinks train to 4mo if that
    yields fewer than WF_MIN_WINDOWS windows.
    """
    parsed = sorted(((_parse_candle_time(c["time"]), c) for c in candles), key=lambda x: x[0])
    if not parsed:
        return {"windows": [], "shrunk_train": False, "train_months_used": WF_TRAIN_MONTHS,
                "median_pf": 0.0, "pct_profitable": 0.0, "worst_window": None,
                "combined_trades": [], "combined_pnl": 0.0,
                "verdict": "REJECT", "verdict_reason": "no candle data"}

    start, end = parsed[0][0], parsed[-1][0]
    windows = _build_wf_windows(start, end, WF_TRAIN_MONTHS, WF_TEST_MONTHS, WF_STEP_MONTHS)
    shrunk, train_months_used = False, WF_TRAIN_MONTHS
    if len(windows) < WF_MIN_WINDOWS:
        windows = _build_wf_windows(start, end, WF_SHRUNK_TRAIN_MONTHS, WF_TEST_MONTHS, WF_STEP_MONTHS)
        shrunk, train_months_used = True, WF_SHRUNK_TRAIN_MONTHS

    window_results, combined_trades = [], []
    for tr_start, tr_end, te_end in windows:
        train_candles = [c for t, c in parsed if tr_start <= t < tr_end]
        test_candles  = [c for t, c in parsed if tr_end  <= t < te_end]
        if not test_candles:
            continue

        strategy = strategy_class(params=params) if params else strategy_class()
        if hasattr(strategy, "fit"):
            strategy.fit(train_candles)  # no current strategy implements this — future-proofing only

        combined_candles = train_candles + test_candles
        all_signals  = strategy.generate_signals(combined_candles)
        test_signals = all_signals[len(train_candles):]

        combined_regimes = classify_regimes(combined_candles)
        test_regimes = combined_regimes[len(train_candles):]

        trades = _simulate_trades(test_candles, test_signals, symbol, max_hold_candles, session_filter, test_regimes)
        combined_trades.extend(trades)
        window_results.append({
            "train_start": tr_start, "train_end": tr_end, "test_end": te_end,
            "trades": len(trades),
            "win_rate": calc_win_rate(trades),
            "pnl": calc_total_profit(trades),
            "profit_factor": calc_profit_factor(trades),
            "has_trades": len(trades) > 0,
        })

    valid = [w for w in window_results if w["has_trades"]]
    pfs = sorted(w["profit_factor"] for w in valid)
    if pfs:
        n = len(pfs)
        median_pf = pfs[n // 2] if n % 2 else round((pfs[n // 2 - 1] + pfs[n // 2]) / 2, 4)
    else:
        median_pf = 0.0
    pct_profitable = round(100 * sum(1 for w in valid if w["profit_factor"] > 1.0) / len(valid), 1) if valid else 0.0
    worst_window = min(valid, key=lambda w: w["profit_factor"]) if valid else None
    combined_pnl = calc_total_profit(combined_trades)

    if not valid:
        verdict, verdict_reason = "REJECT", "no windows produced trades"
    elif median_pf < 1.0:
        verdict, verdict_reason = "REJECT", f"median PF {median_pf} < 1.0"
    elif median_pf >= 1.2 and pct_profitable >= 70:
        verdict, verdict_reason = "ROBUST", f"median PF {median_pf} >= 1.2 and {pct_profitable}% windows profitable"
    elif combined_pnl > 0 and pct_profitable < 70:
        verdict, verdict_reason = "FRAGILE", f"profitable overall (${combined_pnl}) but only {pct_profitable}% of windows profitable"
    else:
        verdict, verdict_reason = "MARGINAL", f"median PF {median_pf}, {pct_profitable}% windows profitable — doesn't clear ROBUST or fall to FRAGILE/REJECT"

    return {
        "windows": window_results, "shrunk_train": shrunk, "train_months_used": train_months_used,
        "median_pf": median_pf, "pct_profitable": pct_profitable, "worst_window": worst_window,
        "combined_trades": combined_trades, "combined_pnl": combined_pnl,
        "verdict": verdict, "verdict_reason": verdict_reason,
    }


def run_stability_map(strategy_class, candles: list, symbol: str, param_grid: dict,
                      max_hold_candles: int = None, session_filter: str = None) -> dict:
    """Full walk-forward (not single 80/20 split) across every cell of param_grid.
    One cell = one full run_walk_forward call. Returns the grid plus one result
    dict per cell — plateau/spike/cluster analysis happens in robustness.py,
    this function only runs the sweep and reports raw per-cell numbers."""
    keys = list(param_grid.keys())
    cells = []
    for combo in itertools.product(*param_grid.values()):
        params = dict(zip(keys, combo))
        wf = run_walk_forward(strategy_class, candles, symbol, params=params,
                              max_hold_candles=max_hold_candles, session_filter=session_filter)
        cells.append({
            "params":          params,
            "median_pf":       wf["median_pf"],
            "pct_profitable":  wf["pct_profitable"],
            "verdict":         wf["verdict"],
            "windows":         len(wf["windows"]),
            "combined_pnl":    wf["combined_pnl"],
            "combined_trades": wf["combined_trades"],
        })
    return {"keys": keys, "grid": param_grid, "cells": cells}
