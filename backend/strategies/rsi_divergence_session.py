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


class RSIDivergenceSessionStrategy(Strategy):
    """
    Session-filtered RSI divergence for 15MIN intraday use.
    Bullish: price makes a lower low vs `divergence_bars` ago while RSI makes
    a higher low (and the difference >= min_rsi_diff). Bearish: mirror.
    ATR-based SL/TP, London-NY session filter.
    """
    name = "rsi_divergence_session"
    strategy_type = "daytrading"

    def __init__(self, params: dict = None):
        defaults = {
            "rsi_period":      14,
            "divergence_bars": 10,
            "session_start":   7,
            "session_end":     17,
            "sl_atr_mult":     1.5,
            "tp_atr_mult":     2.5,
            "min_rsi_diff":    5,
            "atr_period":      14,
        }
        super().__init__({**defaults, **(params or {})})

    def generate_signals(self, candles: list) -> list:
        n = len(candles)
        signals = [{"index": i, "signal": "NONE", "sl_price": None, "tp_price": None} for i in range(n)]
        if n == 0:
            return signals

        p              = self.params
        rsi_period     = int(p["rsi_period"])
        div_bars       = int(p["divergence_bars"])
        session_start  = int(p["session_start"])
        session_end    = int(p["session_end"])
        sl_mult        = float(p["sl_atr_mult"])
        tp_mult        = float(p["tp_atr_mult"])
        min_rsi_diff   = float(p["min_rsi_diff"])
        atr_period     = int(p["atr_period"])

        closes = [c["close"] for c in candles]
        rsi    = _calc_rsi(closes, rsi_period)
        atrs   = _calc_atr(candles, atr_period)

        has_datetime = _parse_utc(candles[0]["time"]) is not None

        for i in range(div_bars, n):
            if rsi[i] is None or rsi[i - div_bars] is None or atrs[i] is None:
                continue

            if has_datetime:
                dt = _parse_utc(candles[i]["time"])
                if dt is None:
                    continue
                if not (session_start <= dt.hour < session_end):
                    continue

            low_now,  low_prev  = candles[i]["low"],  candles[i - div_bars]["low"]
            high_now, high_prev = candles[i]["high"], candles[i - div_bars]["high"]
            rsi_now,  rsi_prev  = rsi[i], rsi[i - div_bars]

            signal_dir = None

            # Bullish divergence: lower low in price, higher low in RSI
            if low_now < low_prev and rsi_now > rsi_prev and (rsi_now - rsi_prev) >= min_rsi_diff:
                signal_dir = "BUY"
            # Bearish divergence: higher high in price, lower high in RSI
            elif high_now > high_prev and rsi_now < rsi_prev and (rsi_prev - rsi_now) >= min_rsi_diff:
                signal_dir = "SELL"

            if signal_dir is None:
                continue

            close   = candles[i]["close"]
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

        return signals
