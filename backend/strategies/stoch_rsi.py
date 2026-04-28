from backend.strategies.base import Strategy


class StochRSIStrategy(Strategy):
    name = "stoch_rsi"

    def __init__(self, params: dict = None):
        defaults = {
            "rsi_period":   14,
            "stoch_period": 14,
            "k_smooth":     3,
            "d_smooth":     3,
            "oversold":     20,
            "overbought":   80,
        }
        super().__init__({**defaults, **(params or {})})

    def generate_signals(self, candles: list) -> list:
        rsi_p      = self.params["rsi_period"]
        stoch_p    = self.params["stoch_period"]
        k_sm       = self.params["k_smooth"]
        d_sm       = self.params["d_smooth"]
        oversold   = self.params["oversold"]
        overbought = self.params["overbought"]

        closes    = [c["close"] for c in candles]
        rsi       = self._calc_rsi(closes, rsi_p)
        n         = len(candles)

        stoch_raw = [None] * n
        for i in range(stoch_p - 1, n):
            window = [r for r in rsi[i - stoch_p + 1 : i + 1] if r is not None]
            if len(window) < stoch_p:
                continue
            lo, hi = min(window), max(window)
            stoch_raw[i] = 0.0 if hi == lo else (rsi[i] - lo) / (hi - lo) * 100

        k = self._sma(stoch_raw, k_sm)
        d = self._sma(k, d_sm)

        signals = []
        for i in range(n):
            if (i == 0
                    or k[i] is None or k[i - 1] is None
                    or d[i] is None or d[i - 1] is None):
                signals.append({"index": i, "signal": "NONE"})
                continue

            k_cross_up   = k[i - 1] < d[i - 1] and k[i] > d[i]
            k_cross_down = k[i - 1] > d[i - 1] and k[i] < d[i]

            if k_cross_up and k[i] < oversold:
                signals.append({"index": i, "signal": "BUY"})
            elif k_cross_down and k[i] > overbought:
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
            rsi[i] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1 + avg_gain / avg_loss))
        return rsi

    def _sma(self, values: list, period: int) -> list:
        n   = len(values)
        out = [None] * n
        for i in range(n):
            window = [v for v in values[max(0, i - period + 1) : i + 1] if v is not None]
            if len(window) == period:
                out[i] = sum(window) / period
        return out
