import math
from backend.strategies.base import Strategy


class BBSqueezeStrategy(Strategy):
    name = "bb_squeeze"

    def __init__(self, params: dict = None):
        defaults = {"period": 20, "std_dev": 2.0, "squeeze_threshold": 0.002}
        super().__init__({**defaults, **(params or {})})

    def generate_signals(self, candles: list) -> list:
        period    = self.params["period"]
        std_mult  = self.params["std_dev"]
        threshold = self.params["squeeze_threshold"]

        closes = [c["close"] for c in candles]
        n = len(candles)
        signals = []

        for i in range(n):
            if i < period:
                signals.append({"index": i, "signal": "NONE"})
                continue

            window = closes[i - period : i]
            mean   = sum(window) / period
            std    = math.sqrt(sum((x - mean) ** 2 for x in window) / period)
            upper  = mean + std_mult * std
            lower  = mean - std_mult * std
            bw     = (upper - lower) / mean

            if i == period:
                signals.append({"index": i, "signal": "NONE"})
                continue

            prev_window = closes[i - period - 1 : i - 1]
            prev_mean   = sum(prev_window) / period
            prev_std    = math.sqrt(sum((x - prev_mean) ** 2 for x in prev_window) / period)
            prev_upper  = prev_mean + std_mult * prev_std
            prev_lower  = prev_mean - std_mult * prev_std
            prev_bw     = (prev_upper - prev_lower) / prev_mean

            was_squeeze = prev_bw < threshold
            in_squeeze  = bw < threshold
            price       = closes[i]

            if was_squeeze and not in_squeeze:
                if price > upper:
                    signals.append({"index": i, "signal": "BUY"})
                elif price < lower:
                    signals.append({"index": i, "signal": "SELL"})
                else:
                    signals.append({"index": i, "signal": "NONE"})
            else:
                signals.append({"index": i, "signal": "NONE"})

        return signals
