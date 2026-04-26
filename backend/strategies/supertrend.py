from backend.strategies.base import Strategy


class SuperTrendStrategy(Strategy):
    name = "supertrend"

    def __init__(self, params: dict = None):
        defaults = {"period": 10, "multiplier": 3.0}
        super().__init__({**defaults, **(params or {})})

    def generate_signals(self, candles: list) -> list:
        period = self.params["period"]
        multiplier = self.params["multiplier"]

        n = len(candles)
        if n < period + 1:
            return [{"index": i, "signal": "NONE"} for i in range(n)]

        atr = self._calc_atr(candles, period)
        upper = [None] * n
        lower = [None] * n
        direction = [None] * n

        for i in range(period, n):
            if atr[i] is None:
                continue
            hl2 = (candles[i]["high"] + candles[i]["low"]) / 2
            basic_upper = hl2 + multiplier * atr[i]
            basic_lower = hl2 - multiplier * atr[i]

            if i == period:
                upper[i] = basic_upper
                lower[i] = basic_lower
                direction[i] = 1
            else:
                prev_upper = upper[i - 1] or basic_upper
                prev_lower = lower[i - 1] or basic_lower
                upper[i] = basic_upper if (basic_upper < prev_upper or candles[i - 1]["close"] > prev_upper) else prev_upper
                lower[i] = basic_lower if (basic_lower > prev_lower or candles[i - 1]["close"] < prev_lower) else prev_lower

                prev_dir = direction[i - 1] or 1
                if prev_dir == 1:
                    direction[i] = -1 if candles[i]["close"] < lower[i] else 1
                else:
                    direction[i] = 1 if candles[i]["close"] > upper[i] else -1

        signals = []
        for i in range(n):
            if direction[i] is None or i == 0 or direction[i - 1] is None:
                signals.append({"index": i, "signal": "NONE"})
            elif direction[i] == 1 and direction[i - 1] == -1:
                signals.append({"index": i, "signal": "BUY"})
            elif direction[i] == -1 and direction[i - 1] == 1:
                signals.append({"index": i, "signal": "SELL"})
            else:
                signals.append({"index": i, "signal": "NONE"})

        return signals

    def _calc_atr(self, candles: list, period: int) -> list:
        n = len(candles)
        tr = [None] * n
        atr = [None] * n

        for i in range(1, n):
            h, l, pc = candles[i]["high"], candles[i]["low"], candles[i - 1]["close"]
            tr[i] = max(h - l, abs(h - pc), abs(l - pc))

        if n < period + 1:
            return atr

        atr[period] = sum(tr[1:period + 1]) / period
        for i in range(period + 1, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

        return atr
