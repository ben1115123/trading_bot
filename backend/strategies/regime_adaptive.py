from datetime import datetime, timezone

from backend.strategies.base import Strategy


def _parse_utc(time_str):
    try:
        dt = datetime.fromisoformat(str(time_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _calc_ema(values, period):
    n = len(values)
    out = [None] * n
    if n < period:
        return out
    k = 2.0 / (period + 1)
    out[period - 1] = sum(values[:period]) / period
    for i in range(period, n):
        out[i] = values[i] * k + out[i - 1] * (1 - k)
    return out


def _calc_atr(candles, period):
    n = len(candles)
    trs = [0.0] * n
    for i in range(n):
        c = candles[i]
        if i == 0:
            trs[i] = c["high"] - c["low"]
        else:
            pc = candles[i - 1]["close"]
            trs[i] = max(c["high"] - c["low"], abs(c["high"] - pc), abs(c["low"] - pc))
    atrs = [None] * n
    if n >= period:
        atrs[period - 1] = sum(trs[:period]) / period
        for i in range(period, n):
            atrs[i] = (atrs[i - 1] * (period - 1) + trs[i]) / period
    return atrs


def _calc_bb(closes, period, std_mult):
    n = len(closes)
    upper = [None] * n
    lower = [None] * n
    for i in range(period - 1, n):
        window = closes[i - period + 1:i + 1]
        m = sum(window) / period
        std = (sum((x - m) ** 2 for x in window) / period) ** 0.5
        upper[i] = m + std_mult * std
        lower[i] = m - std_mult * std
    return upper, lower


class RegimeAdaptiveStrategy(Strategy):
    """
    Detects trending vs ranging regime via ATR relative to recent average.
    Trending: EMA fast/slow crossover entry.
    Ranging: mean reversion at Bollinger Band extremes.
    LONDON session only (07:00-12:00 UTC by default).
    """
    name = "regime_adaptive"
    strategy_type = "daytrading"

    def __init__(self, params=None):
        defaults = {
            "ema_fast":        8,
            "ema_slow":        21,
            "atr_period":      14,
            "atr_regime_bars": 50,
            "atr_trend_mult":  1.2,
            "bb_period":       20,
            "bb_std":          2.0,
            "session_start":   7,
            "session_end":     12,
            "sl_atr_mult":     1.5,
            "tp_atr_mult":     2.5,
        }
        super().__init__({**defaults, **(params or {})})

    def generate_signals(self, candles):
        n = len(candles)
        signals = [{"index": i, "signal": "NONE", "sl_price": None, "tp_price": None} for i in range(n)]
        if n == 0:
            return signals

        p = self.params
        ema_fast_p    = int(p["ema_fast"])
        ema_slow_p    = int(p["ema_slow"])
        atr_period    = int(p["atr_period"])
        regime_bars   = int(p["atr_regime_bars"])
        trend_mult    = float(p["atr_trend_mult"])
        bb_period     = int(p["bb_period"])
        bb_std        = float(p["bb_std"])
        session_start = int(p["session_start"])
        session_end   = int(p["session_end"])
        sl_mult       = float(p["sl_atr_mult"])
        tp_mult       = float(p["tp_atr_mult"])

        closes = [c["close"] for c in candles]
        ema_f  = _calc_ema(closes, ema_fast_p)
        ema_s  = _calc_ema(closes, ema_slow_p)
        atrs   = _calc_atr(candles, atr_period)
        bb_up, bb_lo = _calc_bb(closes, bb_period, bb_std)

        daily_count = {}
        warmup = max(regime_bars, bb_period, ema_slow_p) + 1

        for i in range(warmup, n):
            if ema_f[i] is None or ema_s[i] is None or atrs[i] is None:
                continue
            if ema_f[i - 1] is None or ema_s[i - 1] is None:
                continue
            if bb_up[i] is None or bb_lo[i] is None:
                continue
            if bb_up[i - 1] is None or bb_lo[i - 1] is None:
                continue

            dt = _parse_utc(candles[i]["time"])
            if dt is None:
                continue
            if not (session_start <= dt.hour < session_end):
                continue

            day = dt.date()
            if daily_count.get(day, 0) >= 2:
                continue

            recent_atrs = [atrs[j] for j in range(i - regime_bars, i) if atrs[j] is not None]
            if not recent_atrs:
                continue
            avg_atr = sum(recent_atrs) / len(recent_atrs)
            trending = atrs[i] > trend_mult * avg_atr

            close = candles[i]["close"]
            atr   = atrs[i]
            signal = "NONE"
            sl = tp = None

            if trending:
                if ema_f[i - 1] < ema_s[i - 1] and ema_f[i] >= ema_s[i]:
                    signal = "BUY"
                    sl = close - sl_mult * atr
                    tp = close + tp_mult * atr
                elif ema_f[i - 1] > ema_s[i - 1] and ema_f[i] <= ema_s[i]:
                    signal = "SELL"
                    sl = close + sl_mult * atr
                    tp = close - tp_mult * atr
            else:
                prev_close = candles[i - 1]["close"]
                if close < bb_lo[i] and prev_close >= bb_lo[i - 1]:
                    signal = "BUY"
                    sl = close - sl_mult * atr
                    tp = close + tp_mult * atr
                elif close > bb_up[i] and prev_close <= bb_up[i - 1]:
                    signal = "SELL"
                    sl = close + sl_mult * atr
                    tp = close - tp_mult * atr

            if signal != "NONE":
                signals[i] = {"index": i, "signal": signal, "sl_price": sl, "tp_price": tp}
                daily_count[day] = daily_count.get(day, 0) + 1

        return signals
