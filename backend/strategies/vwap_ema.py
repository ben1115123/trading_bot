from backend.strategies.base import Strategy


class VWAPEMAStrategy(Strategy):
    name = "vwap_ema"

    def __init__(self, params: dict = None):
        defaults = {"ema_period": 20, "vwap_deviation": 0.002}
        super().__init__({**defaults, **(params or {})})

    def generate_signals(self, candles: list) -> list:
        period = self.params["ema_period"]
        deviation = self.params["vwap_deviation"]

        closes = [c["close"] for c in candles]
        typical = [(c["high"] + c["low"] + c["close"]) / 3 for c in candles]

        ema = self._calc_ema(closes, period)
        vwap = self._calc_rolling_vwap(typical, period)

        signals = []
        for i in range(len(candles)):
            if i == 0 or ema[i] is None or ema[i - 1] is None or vwap[i] is None:
                signals.append({"index": i, "signal": "NONE"})
                continue

            price = closes[i]
            prev_price = closes[i - 1]
            e = ema[i]
            v = vwap[i]
            vwap_upper = v * (1 + deviation)
            vwap_lower = v * (1 - deviation)

            crossed_above_ema = prev_price <= ema[i - 1] and price > e
            crossed_below_ema = prev_price >= ema[i - 1] and price < e

            if crossed_above_ema and price > vwap_upper:
                signals.append({"index": i, "signal": "BUY"})
            elif crossed_below_ema and price < vwap_lower:
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

    def _calc_rolling_vwap(self, typical: list, period: int) -> list:
        n = len(typical)
        vwap = [None] * n
        for i in range(period - 1, n):
            vwap[i] = sum(typical[i - period + 1 : i + 1]) / period
        return vwap
