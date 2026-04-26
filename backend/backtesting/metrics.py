import math


def calc_total_profit(trades: list) -> float:
    return round(sum(t["pnl"] for t in trades), 2) if trades else 0.0


def calc_win_rate(trades: list) -> float:
    if not trades:
        return 0.0
    return round(sum(1 for t in trades if t["pnl"] > 0) / len(trades), 4)


def calc_max_drawdown(trades: list) -> float:
    if not trades:
        return 0.0
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        equity += t["pnl"]
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd
    return round(max_dd, 2)


def calc_sharpe_ratio(trades: list, risk_free_rate: float = 0.0) -> float:
    if len(trades) < 2:
        return 0.0
    pnls = [t["pnl"] for t in trades]
    mean = sum(pnls) / len(pnls)
    variance = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
    std = math.sqrt(variance) if variance > 0 else 0.0
    if std == 0:
        return 0.0
    return round((mean - risk_free_rate) / std, 4)


def calc_benchmark_return(candles: list) -> float:
    if len(candles) < 2:
        return 0.0
    first, last = candles[0]["close"], candles[-1]["close"]
    if first == 0:
        return 0.0
    return round(last / first - 1, 6)
