from datetime import datetime, timezone

from backend.strategies.base import Strategy

_DEFAULT_PIP_SIZE = 0.0001


def _parse_utc(time_str: str):
    try:
        dt = datetime.fromisoformat(str(time_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


class NYSessionMomentumStrategy(Strategy):
    """
    NY open range breakout with optional double-break fade.
    Range formed from the first `range_minutes` after `range_start` UTC.
    fade_mode=True: fade the first breakout (expect reversal to opposite range edge).
    fade_mode=False: follow the breakout direction.
    """
    name = "ny_session_momentum"
    strategy_type = "daytrading"

    def __init__(self, params: dict = None):
        defaults = {
            "range_start":     13,
            "range_minutes":   30,
            "entry_window":    3,
            "min_range_pips":  5,
            "breakout_buffer": 0.3,
            "tp_multiplier":   1.5,
            "fade_mode":       True,
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

        if _parse_utc(candles[0]["time"]) is None:
            return signals

        p               = self.params
        range_start     = int(p["range_start"])
        range_minutes   = int(p["range_minutes"])
        entry_window    = int(p["entry_window"])
        pip_size        = _DEFAULT_PIP_SIZE
        min_range_price = float(p["min_range_pips"]) * pip_size
        buffer_price    = float(p["breakout_buffer"]) * pip_size
        tp_mult         = float(p["tp_multiplier"])
        fade_mode       = bool(p["fade_mode"])

        range_start_min = range_start * 60
        range_end_min   = range_start_min + range_minutes
        entry_end_min   = range_start_min + entry_window * 60

        # Pass 1: build day range from candles within [range_start_min, range_end_min) UTC
        day_high: dict = {}
        day_low:  dict = {}
        for c in candles:
            dt = _parse_utc(c["time"])
            if dt is None:
                continue
            m = dt.hour * 60 + dt.minute
            if range_start_min <= m < range_end_min:
                day = dt.date()
                day_high[day] = max(day_high.get(day, c["high"]), c["high"])
                day_low[day]  = min(day_low.get(day,  c["low"]),  c["low"])

        # Pass 2: generate signals in entry window
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

            m = dt.hour * 60 + dt.minute
            if not (range_end_min <= m < entry_end_min):
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
            broke_up   = close > rh + buffer_price
            broke_down = close < rl - buffer_price

            if not (broke_up or broke_down):
                continue

            if fade_mode:
                # Fade the breakout: expect reversal to opposite range edge
                if broke_up:
                    signal_dir = "SELL"
                    sl_price   = round(close + range_size * 1.5, 6)
                    tp_price   = round(rl - range_size * tp_mult, 6)
                else:
                    signal_dir = "BUY"
                    sl_price   = round(close - range_size * 1.5, 6)
                    tp_price   = round(rh + range_size * tp_mult, 6)
            else:
                # Follow the breakout direction
                if broke_up:
                    signal_dir = "BUY"
                    sl_price   = round(close - range_size * 1.5, 6)
                    tp_price   = round(rh + range_size * tp_mult, 6)
                else:
                    signal_dir = "SELL"
                    sl_price   = round(close + range_size * 1.5, 6)
                    tp_price   = round(rl - range_size * tp_mult, 6)

            signals[i] = {
                "index":      i,
                "signal":     signal_dir,
                "sl_price":   sl_price,
                "tp_price":   tp_price,
                "range_high": rh,
                "range_low":  rl,
                "range_size": range_size,
            }
            last_signal_date = day

        return signals
