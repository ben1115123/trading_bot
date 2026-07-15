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


# LONDON (07-11), NY_OPEN (13-14) only — trend setups work best in active opens
_ACTIVE_HOURS = set(range(7, 12)) | set(range(13, 15))


class EMARibbonPullbackStrategy(Strategy):
    """
    Three-EMA ribbon trend alignment + pullback-to-mid-EMA entry.
    SL anchored below/above EMA50. TP = tp_rr × SL distance.
    RSI gate ensures pullback is healthy, not exhausted.
    """
    name = "ema_ribbon_pullback"
    strategy_type = "daytrading"

    def __init__(self, params: dict = None):
        defaults = {
            "ema_fast":        9,
            "ema_mid":         21,
            "ema_slow":        50,
            "rsi_period":      14,
            "atr_period":      14,
            "rsi_lo":          35,   # BUY: RSI in [rsi_lo, rsi_hi]; SELL mirror: [100-rsi_hi, 100-rsi_lo]
            "rsi_hi":          60,
            "sl_atr_mult":     1.0,
            "tp_rr":           2.5,
            "touch_tolerance": 0.00050,
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
        fast_p     = int(p["ema_fast"])
        mid_p      = int(p["ema_mid"])
        slow_p     = int(p["ema_slow"])
        rsi_p      = int(p["rsi_period"])
        atr_p      = int(p["atr_period"])
        rsi_lo     = float(p["rsi_lo"])
        rsi_hi     = float(p["rsi_hi"])
        sl_mult    = float(p["sl_atr_mult"])
        tp_rr      = float(p["tp_rr"])
        touch_tol  = float(p["touch_tolerance"])
        atr_min    = float(p["atr_min_filter"])
        min_sl     = float(p["min_sl_dist"])

        closes = [c["close"] for c in candles]
        ema_f  = _calc_ema(closes, fast_p)
        ema_m  = _calc_ema(closes, mid_p)
        ema_s  = _calc_ema(closes, slow_p)
        rsi    = _calc_rsi(closes, rsi_p)
        atrs   = _calc_atr(candles, atr_p)

        has_datetime = _parse_utc(candles[0]["time"]) is not None
        min_i = max(fast_p, mid_p, slow_p, rsi_p, atr_p) + 6

        for i in range(min_i, n):
            if (ema_f[i] is None or ema_m[i] is None or ema_s[i] is None
                    or ema_f[i-1] is None or ema_m[i-1] is None
                    or ema_s[i-5] is None
                    or rsi[i-1] is None or atrs[i] is None):
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
            low_prev   = candles[i - 1]["low"]
            high_prev  = candles[i - 1]["high"]

            uptrend   = ema_f[i] > ema_m[i] > ema_s[i]
            downtrend = ema_f[i] < ema_m[i] < ema_s[i]
            ema50_up  = ema_s[i] > ema_s[i - 5]
            ema50_dn  = ema_s[i] < ema_s[i - 5]

            if uptrend and ema50_up:
                # Previous candle touched EMA21 (low dipped to within tolerance)
                touched = low_prev <= ema_m[i - 1] + touch_tol
                # Current candle closes back above EMA21
                back    = close_cur > ema_m[i]
                rsi_ok  = rsi_lo <= rsi[i - 1] <= rsi_hi
                if touched and back and rsi_ok:
                    atr      = atrs[i]
                    sl_raw   = ema_s[i] - sl_mult * atr
                    sl_dist  = max(close_cur - sl_raw, min_sl)
                    sl_price = close_cur - sl_dist
                    tp_price = close_cur + tp_rr * sl_dist
                    if sl_dist > 0:
                        signals[i] = {"index": i, "signal": "BUY",
                                      "sl_price": sl_price, "tp_price": tp_price}

            elif downtrend and ema50_dn:
                sell_rsi_lo = 100.0 - rsi_hi   # 40 when rsi_hi=60
                sell_rsi_hi = 100.0 - rsi_lo   # 65 when rsi_lo=35
                # Previous candle touched EMA21 from below (high bounced to within tolerance)
                touched = high_prev >= ema_m[i - 1] - touch_tol
                # Current candle closes back below EMA21
                back    = close_cur < ema_m[i]
                rsi_ok  = sell_rsi_lo <= rsi[i - 1] <= sell_rsi_hi
                if touched and back and rsi_ok:
                    atr      = atrs[i]
                    sl_raw   = ema_s[i] + sl_mult * atr
                    sl_dist  = max(sl_raw - close_cur, min_sl)
                    sl_price = close_cur + sl_dist
                    tp_price = close_cur - tp_rr * sl_dist
                    if sl_dist > 0:
                        signals[i] = {"index": i, "signal": "SELL",
                                      "sl_price": sl_price, "tp_price": tp_price}

        return signals
