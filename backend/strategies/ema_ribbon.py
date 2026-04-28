from backend.strategies.base import Strategy


class EMARibbonStrategy(Strategy):
    name = "ema_ribbon"

    def __init__(self, params: dict = None):
        defaults = {"fast": 8, "mid": 21, "slow": 55}
        super().__init__({**defaults, **(params or {})})

    def generate_signals(self, candles: list) -> list:
        fast_p = self.params["fast"]
        mid_p  = self.params["mid"]
        slow_p = self.params["slow"]

        closes = [c["close"] for c in candles]
        ema_fast = self._calc_ema(closes, fast_p)
        ema_mid  = self._calc_ema(closes, mid_p)
        ema_slow = self._calc_ema(closes, slow_p)

        signals = []
        for i in range(len(candles)):
            if (i == 0
                    or ema_fast[i] is None or ema_fast[i - 1] is None
                    or ema_mid[i]  is None or ema_mid[i - 1]  is None
                    or ema_slow[i] is None):
                signals.append({"index": i, "signal": "NONE"})
                continue

            bull_now  = ema_fast[i]     > ema_mid[i]     > ema_slow[i]
            bull_prev = ema_fast[i - 1] > ema_mid[i - 1]

            bear_now  = ema_fast[i]     < ema_mid[i]     < ema_slow[i]
            bear_prev = ema_fast[i - 1] < ema_mid[i - 1]

            if bull_now and not bull_prev:
                signals.append({"index": i, "signal": "BUY"})
            elif bear_now and not bear_prev:
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
