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


def _calc_kama(closes: list, period: int = 10, fast: int = 2, slow: int = 30) -> list:
    """Kaufman Adaptive Moving Average."""
    n = len(closes)
    kama = [None] * n
    fast_sc = 2.0 / (fast + 1)
    slow_sc = 2.0 / (slow + 1)
    if n < period:
        return kama
    # Seed with first eligible close
    kama[period - 1] = closes[period - 1]
    for i in range(period, n):
        direction  = abs(closes[i] - closes[i - period])
        volatility = sum(abs(closes[j] - closes[j - 1]) for j in range(i - period + 1, i + 1))
        er  = (direction / volatility) if volatility > 0 else 0.0
        sc  = (er * (fast_sc - slow_sc) + slow_sc) ** 2
        kama[i] = kama[i - 1] + sc * (closes[i] - kama[i - 1])
    return kama


# Active hours: LONDON (07-11), NY_OPEN (13-14), NY_MID (15-17)
_ACTIVE_HOURS = set(range(7, 12)) | set(range(13, 18))


class KAMACrossoverStrategy(Strategy):
    """
    KAMA crossover: price crosses KAMA with slope confirmation.
    ATR-based SL/TP. Active LONDON + NY sessions only.
    """
    name = "kama_crossover"
    strategy_type = "daytrading"

    def __init__(self, params: dict = None):
        defaults = {
            "period":         10,
            "slope_window":    3,
            "atr_period":     14,
            "sl_atr_mult":   1.5,
            "tp_atr_mult":   3.0,
            "atr_min_filter": 0.00030,
            "min_sl_dist":    0.00050,
        }
        super().__init__({**defaults, **(params or {})})

    def generate_signals(self, candles: list) -> list:
        n = len(candles)
        signals = [{"index": i, "signal": "NONE", "sl_price": None, "tp_price": None}
                   for i in range(n)]
        if n == 0:
            return signals

        p             = self.params
        period        = int(p["period"])
        slope_window  = int(p["slope_window"])
        atr_period    = int(p["atr_period"])
        sl_mult       = float(p["sl_atr_mult"])
        tp_mult       = float(p["tp_atr_mult"])
        atr_min       = float(p["atr_min_filter"])
        min_sl_dist   = float(p["min_sl_dist"])

        closes = [c["close"] for c in candles]
        kama   = _calc_kama(closes, period)
        atrs   = _calc_atr(candles, atr_period)

        has_datetime = _parse_utc(candles[0]["time"]) is not None
        min_i = max(period, slope_window + 1, atr_period)

        for i in range(min_i, n):
            if kama[i] is None or kama[i - 1] is None:
                continue
            if kama[i - slope_window] is None:
                continue
            if atrs[i] is None:
                continue

            if has_datetime:
                dt = _parse_utc(candles[i]["time"])
                if dt is None or dt.weekday() > 4:
                    continue
                if dt.hour not in _ACTIVE_HOURS:
                    continue

            if atrs[i] < atr_min:
                continue

            close_cur  = closes[i]
            close_prev = closes[i - 1]
            kama_cur   = kama[i]
            kama_prev  = kama[i - 1]
            slope_ref  = kama[i - slope_window]

            cross_above = close_prev <= kama_prev and close_cur > kama_cur
            cross_below = close_prev >= kama_prev and close_cur < kama_cur
            slope_up    = kama_cur > slope_ref
            slope_down  = kama_cur < slope_ref

            if cross_above and slope_up:
                atr      = atrs[i]
                sl_dist  = max(sl_mult * atr, min_sl_dist)
                sl_price = close_cur - sl_dist
                tp_price = close_cur + tp_mult * atr
                signals[i] = {"index": i, "signal": "BUY",
                              "sl_price": sl_price, "tp_price": tp_price}

            elif cross_below and slope_down:
                atr      = atrs[i]
                sl_dist  = max(sl_mult * atr, min_sl_dist)
                sl_price = close_cur + sl_dist
                tp_price = close_cur - tp_mult * atr
                signals[i] = {"index": i, "signal": "SELL",
                              "sl_price": sl_price, "tp_price": tp_price}

        return signals
