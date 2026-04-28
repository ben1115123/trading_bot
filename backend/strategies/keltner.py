from backend.strategies.base import Strategy


class KeltnerChannelStrategy(Strategy):
    name = "keltner"

    def __init__(self, params: dict = None):
        defaults = {"ema_period": 20, "atr_period": 10, "multiplier": 2.0}
        super().__init__({**defaults, **(params or {})})

    def generate_signals(self, candles: list) -> list:
        ema_p = self.params["ema_period"]
        atr_p = self.params["atr_period"]
        mult  = self.params["multiplier"]

        n       = len(candles)
        closes  = [c["close"] for c in candles]
        ema     = self._calc_ema(closes, ema_p)
        atr     = self._calc_atr(candles, atr_p)
        signals = []

        for i in range(n):
            if i == 0 or ema[i] is None or ema[i - 1] is None or atr[i] is None:
                signals.append({"index": i, "signal": "NONE"})
                continue

            upper = ema[i] + mult * atr[i]
            lower = ema[i] - mult * atr[i]
            price = closes[i]
            prev  = closes[i - 1]

            if prev <= upper and price > upper:
                signals.append({"index": i, "signal": "BUY"})
            elif prev >= lower and price < lower:
                signals.append({"index": i, "signal": "SELL"})
            else:
                signals.append({"index": i, "signal": "NONE"})

        return signals

    def _calc_ema(self, closes: list, period: int) -> list:
        n = len(closes)
        ema = [None] * n
        if n < period:
            return ema
        ema[period - 1] = sum(closes[:period]) / period
        k = 2 / (period + 1)
        for i in range(period, n):
            ema[i] = closes[i] * k + ema[i - 1] * (1 - k)
        return ema

    def _calc_atr(self, candles: list, period: int) -> list:
        n   = len(candles)
        tr  = [None] * n
        atr = [None] * n
        for i in range(1, n):
            h, l, pc = candles[i]["high"], candles[i]["low"], candles[i - 1]["close"]
            tr[i] = max(h - l, abs(h - pc), abs(l - pc))
        if n < period + 1:
            return atr
        atr[period] = sum(tr[1 : period + 1]) / period
        for i in range(period + 1, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
        return atr
