from backend.strategies.base import Strategy


class RSIStrategy(Strategy):
    name = "rsi"

    def __init__(self, params: dict = None):
        defaults = {"period": 14, "overbought": 70, "oversold": 30}
        super().__init__({**defaults, **(params or {})})

    def generate_signals(self, candles: list) -> list:
        period = self.params["period"]
        overbought = self.params["overbought"]
        oversold = self.params["oversold"]

        closes = [c["close"] for c in candles]
        rsi = self._calc_rsi(closes, period)

        signals = []
        for i in range(len(candles)):
            if rsi[i] is None or i == 0 or rsi[i - 1] is None:
                signals.append({"index": i, "signal": "NONE"})
                continue
            prev, curr = rsi[i - 1], rsi[i]
            if prev <= oversold and curr > oversold:
                signals.append({"index": i, "signal": "BUY"})
            elif prev >= overbought and curr < overbought:
                signals.append({"index": i, "signal": "SELL"})
            else:
                signals.append({"index": i, "signal": "NONE"})

        return signals

    def _calc_rsi(self, closes: list, period: int) -> list:
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

            if avg_loss == 0:
                rsi[i] = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi[i] = 100.0 - (100.0 / (1 + rs))

        return rsi
