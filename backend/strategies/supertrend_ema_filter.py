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


def _calc_ema(closes: list, period: int) -> list:
    n = len(closes)
    ema = [None] * n
    if n < period:
        return ema
    ema[period - 1] = sum(closes[:period]) / period
    k = 2.0 / (period + 1)
    for i in range(period, n):
        ema[i] = closes[i] * k + ema[i - 1] * (1 - k)
    return ema


def _calc_rsi(closes: list, period: int) -> list:
    n = len(closes)
    rsi = [None] * n
    if n < period + 1:
        return rsi
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    for i in range(period, n):
        if i > period:
            diff = closes[i] - closes[i - 1]
            avg_gain = (avg_gain * (period - 1) + max(diff, 0)) / period
            avg_loss = (avg_loss * (period - 1) + max(-diff, 0)) / period
        rsi[i] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1 + avg_gain / avg_loss))
    return rsi


def _calc_supertrend(candles: list, period: int, multiplier: float):
    """Returns (upper, lower, direction). direction: 1=bullish, -1=bearish."""
    n    = len(candles)
    atrs = _calc_atr(candles, period)
    upper = [None] * n
    lower = [None] * n
    direc = [None] * n

    for i in range(period, n):
        if atrs[i] is None:
            continue
        hl2         = (candles[i]["high"] + candles[i]["low"]) / 2
        basic_upper = hl2 + multiplier * atrs[i]
        basic_lower = hl2 - multiplier * atrs[i]

        if i == period:
            upper[i] = basic_upper
            lower[i] = basic_lower
            direc[i] = 1
        else:
            pu = upper[i - 1] or basic_upper
            pl = lower[i - 1] or basic_lower
            upper[i] = basic_upper if (basic_upper < pu
                                       or candles[i - 1]["close"] > pu) else pu
            lower[i] = basic_lower if (basic_lower > pl
                                       or candles[i - 1]["close"] < pl) else pl

            pd = direc[i - 1] or 1
            if pd == 1:
                direc[i] = -1 if candles[i]["close"] < lower[i] else 1
            else:
                direc[i] = 1 if candles[i]["close"] > upper[i] else -1

    return upper, lower, direc


# LONDON (07-11), NY_OPEN (13-14), NY_MID (15-17)
_ACTIVE_HOURS = set(range(7, 12)) | set(range(13, 18))


class SupertrendEMAFilterStrategy(Strategy):
    """
    Supertrend flip entry gated by EMA50 trend direction, EMA50 slope,
    RSI momentum zone, and ATR expansion (volatility expanding into trend).
    SL at supertrend band. TP = tp_rr × SL distance.
    """
    name = "supertrend_ema_filter"
    strategy_type = "daytrading"

    def __init__(self, params: dict = None):
        defaults = {
            "st_period":      10,
            "st_multiplier":  3.0,
            "ema_slow":       50,
            "rsi_period":     14,
            "atr_period":     14,
            "atr_avg_period": 20,
            "tp_rr":          2.0,
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

        p           = self.params
        st_period   = int(p["st_period"])
        st_mult     = float(p["st_multiplier"])
        ema_slow_p  = int(p["ema_slow"])
        rsi_p       = int(p["rsi_period"])
        atr_p       = int(p["atr_period"])
        atr_avg_p   = int(p["atr_avg_period"])
        tp_rr       = float(p["tp_rr"])
        atr_min     = float(p["atr_min_filter"])
        min_sl      = float(p["min_sl_dist"])

        closes              = [c["close"] for c in candles]
        upper, lower, direc = _calc_supertrend(candles, st_period, st_mult)
        ema_slow            = _calc_ema(closes, ema_slow_p)
        rsi                 = _calc_rsi(closes, rsi_p)
        atrs                = _calc_atr(candles, atr_p)

        # SMA of ATR for expanding-volatility check
        atr_avg = [None] * n
        for i in range(atr_avg_p - 1, n):
            window = [atrs[j] for j in range(i - atr_avg_p + 1, i + 1)
                      if atrs[j] is not None]
            if len(window) == atr_avg_p:
                atr_avg[i] = sum(window) / atr_avg_p

        has_datetime = _parse_utc(candles[0]["time"]) is not None
        min_i = max(st_period, ema_slow_p, rsi_p, atr_p + atr_avg_p) + 6

        for i in range(min_i, n):
            if (direc[i] is None or direc[i - 1] is None
                    or upper[i] is None or lower[i] is None
                    or ema_slow[i] is None or ema_slow[i - 5] is None
                    or rsi[i] is None or atrs[i] is None or atr_avg[i] is None):
                continue

            # Only fire on supertrend direction flip
            if direc[i] == direc[i - 1]:
                continue

            if has_datetime:
                dt = _parse_utc(candles[i]["time"])
                if dt is None or dt.weekday() > 4:
                    continue
                if dt.hour not in _ACTIVE_HOURS:
                    continue

            if atrs[i] < atr_min:
                continue

            # ATR must be expanding (current > 20-period average)
            if atrs[i] <= atr_avg[i]:
                continue

            close_cur = closes[i]

            if direc[i] == 1:  # flip to bullish
                if close_cur <= ema_slow[i]:        # price above EMA50
                    continue
                if ema_slow[i] <= ema_slow[i - 5]:  # EMA50 sloping up
                    continue
                if not (45 <= rsi[i] <= 75):         # RSI momentum
                    continue
                sl_dist  = max(close_cur - lower[i], min_sl)
                sl_price = close_cur - sl_dist
                tp_price = close_cur + tp_rr * sl_dist
                signals[i] = {"index": i, "signal": "BUY",
                              "sl_price": sl_price, "tp_price": tp_price}

            else:  # direc[i] == -1, flip to bearish
                if close_cur >= ema_slow[i]:         # price below EMA50
                    continue
                if ema_slow[i] >= ema_slow[i - 5]:  # EMA50 sloping down
                    continue
                if not (25 <= rsi[i] <= 55):         # RSI momentum
                    continue
                sl_dist  = max(upper[i] - close_cur, min_sl)
                sl_price = close_cur + sl_dist
                tp_price = close_cur - tp_rr * sl_dist
                signals[i] = {"index": i, "signal": "SELL",
                              "sl_price": sl_price, "tp_price": tp_price}

        return signals
