from backend.strategies.base import Strategy


class ORBStrategy(Strategy):
    name = "orb"

    def __init__(self, params: dict = None):
        defaults = {"candles_in_range": 6, "breakout_buffer": 0.001}
        super().__init__({**defaults, **(params or {})})

    def generate_signals(self, candles: list) -> list:
        range_bars = self.params["candles_in_range"]
        buffer     = self.params["breakout_buffer"]

        n       = len(candles)
        signals = []

        for i in range(n):
            if i < range_bars:
                signals.append({"index": i, "signal": "NONE"})
                continue

            window_start = (i // range_bars) * range_bars
            range_end    = window_start + range_bars

            if i < range_end:
                signals.append({"index": i, "signal": "NONE"})
                continue

            prev_window_start = window_start - range_bars
            if prev_window_start < 0:
                signals.append({"index": i, "signal": "NONE"})
                continue

            range_high = max(c["high"] for c in candles[prev_window_start : window_start])
            range_low  = min(c["low"]  for c in candles[prev_window_start : window_start])
            price      = candles[i]["close"]

            if price > range_high * (1 + buffer):
                signals.append({"index": i, "signal": "BUY"})
            elif price < range_low * (1 - buffer):
                signals.append({"index": i, "signal": "SELL"})
            else:
                signals.append({"index": i, "signal": "NONE"})

        return signals
