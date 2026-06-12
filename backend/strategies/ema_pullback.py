from datetime import datetime, timezone

from backend.strategies.base import Strategy


def _parse_utc(time_str: str):
    try:
        dt = datetime.fromisoformat(str(time_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _calc_ema(values: list, period: int) -> list:
    n = len(values)
    out = [None] * n
    if n < period:
        return out
    k = 2.0 / (period + 1)
    out[period - 1] = sum(values[:period]) / period
    for i in range(period, n):
        out[i] = values[i] * k + out[i - 1] * (1 - k)
    return out


def _calc_atr(candles: list, period: int) -> list:
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


class EMAPullbackStrategy(Strategy):
    """
    Trend-following pullback to fast EMA during active session.
    Entry on EMA touch + close back in trend direction, after a
    qualifying extension move (>= min_move_atr * ATR away from EMA).
    ATR-based SL/TP. Max 2 trades per day.
    """
    name = "ema_pullback"
    strategy_type = "daytrading"

    def __init__(self, params: dict = None):
        defaults = {
            "ema_fast":      8,
            "ema_slow":      21,
            "atr_period":    14,
            "min_move_atr":  1.5,
            "session_start": 7,
            "session_end":   17,
            "sl_atr_mult":   1.0,
            "tp_atr_mult":   2.0,
        }
        super().__init__({**defaults, **(params or {})})

    def generate_signals(self, candles: list) -> list:
        n = len(candles)
        signals = [{"index": i, "signal": "NONE", "sl_price": None, "tp_price": None} for i in range(n)]
        if n == 0:
            return signals

        p             = self.params
        ema_fast_p    = int(p["ema_fast"])
        ema_slow_p    = int(p["ema_slow"])
        atr_period    = int(p["atr_period"])
        min_move_atr  = float(p["min_move_atr"])
        session_start = int(p["session_start"])
        session_end   = int(p["session_end"])
        sl_mult       = float(p["sl_atr_mult"])
        tp_mult       = float(p["tp_atr_mult"])

        closes  = [c["close"] for c in candles]
        ema_f   = _calc_ema(closes, ema_fast_p)
        ema_s   = _calc_ema(closes, ema_slow_p)
        atrs    = _calc_atr(candles, atr_period)

        has_datetime = _parse_utc(candles[0]["time"]) is not None

        daily_count: dict = {}

        for i in range(3, n):
            if ema_f[i] is None or ema_s[i] is None or atrs[i] is None:
                continue

            if has_datetime:
                dt = _parse_utc(candles[i]["time"])
                if dt is None:
                    continue
                if not (session_start <= dt.hour < session_end):
                    continue
                day = dt.date()
            else:
                day = None

            if day is not None and daily_count.get(day, 0) >= 2:
                continue

            close   = candles[i]["close"]
            uptrend   = close > ema_s[i]
            downtrend = close < ema_s[i]

            # Recent extension away from EMA8 (look back 3 candles, excluding current)
            extended_up   = False
            extended_down = False
            for j in range(i - 3, i):
                if ema_f[j] is None or atrs[j] is None:
                    continue
                if candles[j]["close"] - ema_f[j] >= min_move_atr * atrs[j]:
                    extended_up = True
                if ema_f[j] - candles[j]["close"] >= min_move_atr * atrs[j]:
                    extended_down = True

            touched_ema = candles[i]["low"] <= ema_f[i] <= candles[i]["high"]

            signal_dir = None
            if uptrend and extended_up and touched_ema and close > ema_f[i]:
                signal_dir = "BUY"
            elif downtrend and extended_down and touched_ema and close < ema_f[i]:
                signal_dir = "SELL"

            if signal_dir is None:
                continue

            atr_now = atrs[i]
            if signal_dir == "BUY":
                sl_price = close - sl_mult * atr_now
                tp_price = close + tp_mult * atr_now
            else:
                sl_price = close + sl_mult * atr_now
                tp_price = close - tp_mult * atr_now

            signals[i] = {
                "index":    i,
                "signal":   signal_dir,
                "sl_price": round(sl_price, 6),
                "tp_price": round(tp_price, 6),
            }
            if day is not None:
                daily_count[day] = daily_count.get(day, 0) + 1

        return signals
