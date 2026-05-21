from backend.strategies.base import Strategy


class WilliamsRStrategy(Strategy):
    name = "williams_r"

    def __init__(self, params: dict = None):
        defaults = {"period": 14, "oversold": -85, "overbought": -15}
        super().__init__({**defaults, **(params or {})})

    def generate_signals(self, candles: list) -> list:
        period     = self.params["period"]
        oversold   = self.params["oversold"]
        overbought = self.params["overbought"]

        n  = len(candles)
        wr = [None] * n

        for i in range(period - 1, n):
            window  = candles[i - period + 1 : i + 1]
            highest = max(c["high"] for c in window)
            lowest  = min(c["low"]  for c in window)
            if highest == lowest:
                wr[i] = -50.0
            else:
                wr[i] = (highest - candles[i]["close"]) / (highest - lowest) * -100.0

        signals = []
        for i in range(n):
            if i == 0 or wr[i] is None or wr[i - 1] is None:
                signals.append({"index": i, "signal": "NONE"})
                continue

            cross_into_oversold   = wr[i - 1] > oversold   and wr[i] <= oversold
            cross_into_overbought = wr[i - 1] < overbought and wr[i] >= overbought

            if cross_into_oversold:
                signals.append({"index": i, "signal": "BUY"})
            elif cross_into_overbought:
                signals.append({"index": i, "signal": "SELL"})
            else:
                signals.append({"index": i, "signal": "NONE"})

        return signals
