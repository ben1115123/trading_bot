from datetime import datetime, timezone

from backend.strategies.base import Strategy

SYMBOL_PIP_SIZE = {
    "EURUSD": 0.0001,
    "US500":  1.0,
    "DAX":    1.0,
    "US100":  1.0,
}
_DEFAULT_PIP_SIZE = 0.0001


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


class LondonBreakoutStrategy(Strategy):
    """
    London session breakout on EURUSD 15MIN.
    Range: 06:00-07:00 UTC. Entry window: 07:00-09:00 UTC.
    SL = opposite side of range. TP = entry ± range_size × tp_multiplier.
    One trade per calendar day.
    """
    name = "london_breakout"
    strategy_type = "daytrading"

    def __init__(self, params: dict = None):
        defaults = {
            "range_start_hour":  6,
            "range_end_hour":    7,
            "entry_window_end":  9,
            "min_range_pips":    5,
            "breakout_buffer":   0.3,
            "tp_multiplier":     1.5,
            "atr_period":        14,
            "use_ema_filter":    False,
            "ema_period":        200,
        }
        super().__init__({**defaults, **(params or {})})

    def generate_signals(self, candles: list) -> list:
        n = len(candles)

        def _blank(i):
            return {"index": i, "signal": "NONE", "sl_price": None, "tp_price": None,
                    "range_high": None, "range_low": None, "range_size": None}

        signals = [_blank(i) for i in range(n)]

        if n == 0:
            return signals

        # Degrade gracefully if timestamps are unparseable
        if _parse_utc(candles[0]["time"]) is None:
            return signals

        p               = self.params
        range_start     = int(p["range_start_hour"])
        range_end       = int(p["range_end_hour"])
        entry_end       = int(p["entry_window_end"])
        pip_size        = _DEFAULT_PIP_SIZE
        min_range_price = float(p["min_range_pips"]) * pip_size
        buffer_price    = float(p["breakout_buffer"]) * pip_size
        tp_mult         = float(p["tp_multiplier"])
        use_ema         = bool(p["use_ema_filter"])
        ema_period      = int(p["ema_period"])

        ema_vals = None
        if use_ema:
            closes   = [c["close"] for c in candles]
            ema_vals = _calc_ema(closes, ema_period)

        # Pass 1: build day range from candles within [range_start, range_end) UTC
        day_high: dict = {}
        day_low:  dict = {}
        for c in candles:
            dt = _parse_utc(c["time"])
            if dt is None:
                continue
            if range_start <= dt.hour < range_end:
                day = dt.date()
                day_high[day] = max(day_high.get(day, c["high"]), c["high"])
                day_low[day]  = min(day_low.get(day,  c["low"]),  c["low"])

        # Pass 2: generate signals in entry window [range_end, entry_end) UTC
        last_signal_date = None

        for i in range(n):
            c  = candles[i]
            dt = _parse_utc(c["time"])
            if dt is None:
                continue

            day = dt.date()
            rh  = day_high.get(day)
            rl  = day_low.get(day)

            if rh is not None and rl is not None:
                signals[i]["range_high"] = rh
                signals[i]["range_low"]  = rl
                signals[i]["range_size"] = rh - rl

            if not (range_end <= dt.hour < entry_end):
                continue
            if rh is None or rl is None:
                continue

            range_size = rh - rl
            if range_size < min_range_price:
                continue

            # One trade per calendar day
            if last_signal_date == day:
                continue

            close = c["close"]
            ema   = ema_vals[i] if ema_vals is not None else None

            buy_ok  = close > rh + buffer_price
            sell_ok = close < rl - buffer_price

            if use_ema and ema is not None:
                buy_ok  = buy_ok  and close > ema
                sell_ok = sell_ok and close < ema

            if buy_ok:
                signals[i] = {
                    "index":      i,
                    "signal":     "BUY",
                    "sl_price":   round(rl - buffer_price, 6),
                    "tp_price":   round(close + range_size * tp_mult, 6),
                    "range_high": rh,
                    "range_low":  rl,
                    "range_size": range_size,
                }
                last_signal_date = day
            elif sell_ok:
                signals[i] = {
                    "index":      i,
                    "signal":     "SELL",
                    "sl_price":   round(rh + buffer_price, 6),
                    "tp_price":   round(close - range_size * tp_mult, 6),
                    "range_high": rh,
                    "range_low":  rl,
                    "range_size": range_size,
                }
                last_signal_date = day

        return signals
