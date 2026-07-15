import math
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


def _calc_wma(values: list, period: int) -> list:
    n = len(values)
    wma = [None] * n
    weights = list(range(1, period + 1))
    total_w = sum(weights)
    for i in range(period - 1, n):
        window = values[i - period + 1 : i + 1]
        if any(v is None for v in window):
            continue
        wma[i] = sum(w * v for w, v in zip(weights, window)) / total_w
    return wma


def _calc_hma(closes: list, period: int) -> list:
    """HMA(n) = WMA(2×WMA(n/2) - WMA(n), sqrt(n))"""
    half_p = max(1, period // 2)
    sqrt_p = max(2, int(math.sqrt(period)))
    wma_half = _calc_wma(closes, half_p)
    wma_full = _calc_wma(closes, period)
    n = len(closes)
    diff = [None] * n
    for i in range(n):
        if wma_half[i] is not None and wma_full[i] is not None:
            diff[i] = 2.0 * wma_half[i] - wma_full[i]
    return _calc_wma(diff, sqrt_p)


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


# LONDON (07-11), NY_OPEN (13-14), NY_MID (15-17)
_ACTIVE_HOURS = set(range(7, 12)) | set(range(13, 18))


class HullMomentumStrategy(Strategy):
    """
    Hull MA momentum: fresh HMA-side cross with RSI momentum confirmation.
    Requires price to have recently been on opposite side of HMA (avoids chasing).
    ATR-based SL/TP.
    """
    name = "hull_momentum"
    strategy_type = "daytrading"

    def __init__(self, params: dict = None):
        defaults = {
            "hma_period":      14,
            "rsi_period":      14,
            "atr_period":      14,
            "rsi_mid":         50,
            "sl_atr_mult":     1.5,
            "tp_atr_mult":     3.0,
            "hma_slope_min":   0.00010,
            "atr_min_filter":  0.00030,
            "min_sl_dist":     0.00050,
        }
        super().__init__({**defaults, **(params or {})})

    def generate_signals(self, candles: list) -> list:
        n = len(candles)
        signals = [{"index": i, "signal": "NONE", "sl_price": None, "tp_price": None}
                   for i in range(n)]
        if n == 0:
            return signals

        p          = self.params
        hma_p      = int(p["hma_period"])
        rsi_p      = int(p["rsi_period"])
        atr_p      = int(p["atr_period"])
        rsi_mid    = float(p["rsi_mid"])
        sl_mult    = float(p["sl_atr_mult"])
        tp_mult    = float(p["tp_atr_mult"])
        slope_min  = float(p["hma_slope_min"])
        atr_min    = float(p["atr_min_filter"])
        min_sl     = float(p["min_sl_dist"])

        closes = [c["close"] for c in candles]
        hma    = _calc_hma(closes, hma_p)
        rsi    = _calc_rsi(closes, rsi_p)
        atrs   = _calc_atr(candles, atr_p)

        has_datetime = _parse_utc(candles[0]["time"]) is not None
        # HMA needs ~period + sqrt(period) warmup; add 6 for slope lookback
        min_i = hma_p + int(math.sqrt(hma_p)) + max(rsi_p, atr_p) + 6

        for i in range(min_i, n):
            if (hma[i] is None or hma[i - 1] is None or hma[i - 3] is None
                    or rsi[i] is None or rsi[i - 1] is None
                    or atrs[i] is None):
                continue

            if has_datetime:
                dt = _parse_utc(candles[i]["time"])
                if dt is None or dt.weekday() > 4:
                    continue
                if dt.hour not in _ACTIVE_HOURS:
                    continue

            if atrs[i] < atr_min:
                continue

            close_cur = closes[i]
            hma_cur   = hma[i]
            hma_slope = hma_cur - hma[i - 3]

            if abs(hma_slope) < slope_min:
                continue

            slope_up = hma_slope > 0
            slope_dn = hma_slope < 0

            # RSI crossed rsi_mid on current candle or previous candle
            rsi_cross_up = (rsi[i - 1] < rsi_mid <= rsi[i]) or (
                i >= 2 and rsi[i - 2] is not None
                and rsi[i - 2] < rsi_mid <= rsi[i - 1])
            rsi_cross_dn = (rsi[i - 1] > rsi_mid >= rsi[i]) or (
                i >= 2 and rsi[i - 2] is not None
                and rsi[i - 2] > rsi_mid >= rsi[i - 1])

            # Ensure price was on opposite side of HMA in last 5 candles (not chasing)
            lookback   = range(max(0, i - 5), i)
            was_below  = any(closes[j] < hma[j]
                             for j in lookback if hma[j] is not None)
            was_above  = any(closes[j] > hma[j]
                             for j in lookback if hma[j] is not None)

            if slope_up and close_cur > hma_cur and rsi_cross_up and was_below:
                atr      = atrs[i]
                sl_dist  = max(sl_mult * atr, min_sl)
                sl_price = close_cur - sl_dist
                tp_price = close_cur + tp_mult * atr
                signals[i] = {"index": i, "signal": "BUY",
                              "sl_price": sl_price, "tp_price": tp_price}

            elif slope_dn and close_cur < hma_cur and rsi_cross_dn and was_above:
                atr      = atrs[i]
                sl_dist  = max(sl_mult * atr, min_sl)
                sl_price = close_cur + sl_dist
                tp_price = close_cur - tp_mult * atr
                signals[i] = {"index": i, "signal": "SELL",
                              "sl_price": sl_price, "tp_price": tp_price}

        return signals
