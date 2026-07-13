"""Reusable 3-bucket market regime classifier.

Deliberately flat: TREND / RANGE / NEUTRAL, no sub-slicing. Adding more
buckets or per-symbol thresholds would just be a new overfitting surface —
the whole point of this layer is a coarse, shared regime definition that
every strategy gets tagged against the same way.

Bucket rule (entry-time, from candles up to and including the entry candle):
  TREND   — ADX(14) > 25
  RANGE   — ADX(14) < 20 AND ATR(14) below its own 20-period average
  NEUTRAL — everything else, including the ADX/ATR warm-up period
"""

TREND, RANGE, NEUTRAL = "TREND", "RANGE", "NEUTRAL"


def _wilder_smooth(values: list, period: int) -> list:
    """Wilder's smoothing (the running-average form used by ADX/ATR).
    Returns a parallel list; entries are None until the seed window is full."""
    n = len(values)
    out = [None] * n
    seed_start = next((i for i, v in enumerate(values) if v is not None), None)
    if seed_start is None or n - seed_start < period:
        return out
    seed_end = seed_start + period  # exclusive
    running = sum(values[seed_start:seed_end])
    out[seed_end - 1] = running / period
    for i in range(seed_end, n):
        running = running - running / period + values[i]
        out[i] = running / period
    return out


def compute_adx_atr(candles: list, period: int = 14) -> tuple:
    """Wilder's ADX and ATR, both period 14 by default.
    Returns (adx, atr) — parallel lists, same length as candles. Entries are
    None until roughly 2*period candles of warm-up are available."""
    n = len(candles)
    tr = [None] * n
    plus_dm = [None] * n
    minus_dm = [None] * n

    for i in range(1, n):
        high, low = candles[i]["high"], candles[i]["low"]
        prev_high  = candles[i - 1]["high"]
        prev_low   = candles[i - 1]["low"]
        prev_close = candles[i - 1]["close"]
        tr[i] = max(high - low, abs(high - prev_close), abs(low - prev_close))
        up_move, down_move = high - prev_high, prev_low - low
        plus_dm[i]  = up_move   if (up_move > down_move and up_move > 0)   else 0.0
        minus_dm[i] = down_move if (down_move > up_move and down_move > 0) else 0.0

    atr        = _wilder_smooth(tr, period)
    plus_dm_s  = _wilder_smooth(plus_dm, period)
    minus_dm_s = _wilder_smooth(minus_dm, period)

    # +DI/-DI are ratios of smoothed-sum forms; since both num and denom here
    # are the smoothed *average* form (sum/period), the ratio is identical —
    # period cancels, no need to reconstruct the sum form.
    dx = [None] * n
    for i in range(n):
        if atr[i] is None or atr[i] == 0:
            continue
        plus_di  = 100 * plus_dm_s[i]  / atr[i]
        minus_di = 100 * minus_dm_s[i] / atr[i]
        denom = plus_di + minus_di
        dx[i] = 0.0 if denom == 0 else 100 * abs(plus_di - minus_di) / denom

    adx = _wilder_smooth(dx, period)
    return adx, atr


def classify_regimes(candles: list, adx_period: int = 14, atr_period: int = 14,
                     atr_avg_period: int = 20, trend_adx_thresh: float = 25,
                     range_adx_thresh: float = 20) -> list:
    """Per-candle regime bucket, parallel list same length as candles.
    Warm-up candles (insufficient history for ADX/ATR/20-period ATR avg)
    default to NEUTRAL rather than None, so every entry gets a definite tag."""
    adx, atr = compute_adx_atr(candles, period=adx_period)
    n = len(candles)

    atr_avg = [None] * n
    for i in range(n):
        if atr[i] is None:
            continue
        window = [a for a in atr[max(0, i - atr_avg_period + 1):i + 1] if a is not None]
        if len(window) < atr_avg_period:
            continue
        atr_avg[i] = sum(window) / len(window)

    regimes = [NEUTRAL] * n
    for i in range(n):
        if adx[i] is None or atr[i] is None or atr_avg[i] is None:
            continue  # warm-up — leave as NEUTRAL
        if adx[i] > trend_adx_thresh:
            regimes[i] = TREND
        elif adx[i] < range_adx_thresh and atr[i] < atr_avg[i]:
            regimes[i] = RANGE
    return regimes
