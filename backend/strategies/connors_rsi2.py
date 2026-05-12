from backend.strategies.base import Strategy


class ConnorsRSI2Strategy(Strategy):
    name = "connors_rsi2"

    def __init__(self, params: dict = None):
        defaults = {
            "rsi_period": 2,
            "sma_long":   200,
            "sma_exit":   5,
            "oversold":   10,
            "overbought": 90,
        }
        super().__init__({**defaults, **(params or {})})

    def generate_signals(self, candles: list) -> list:
        rsi_period = self.params["rsi_period"]
        sma_long   = self.params["sma_long"]
        oversold   = self.params["oversold"]
        overbought = self.params["overbought"]

        closes = [c["close"] for c in candles]
        rsi    = self._calc_rsi(closes, rsi_period)
        sma200 = self._calc_sma(closes, sma_long)

        signals = []
        for i in range(len(candles)):
            r  = rsi[i]
            s  = sma200[i]
            pr = rsi[i - 1] if i > 0 else None
            if r is None or s is None or pr is None:
                signals.append({"index": i, "signal": "NONE"})
                continue
            close = closes[i]
            if pr >= oversold and r < oversold and close > s:
                signals.append({"index": i, "signal": "BUY"})
            elif pr <= overbought and r > overbought and close < s:
                signals.append({"index": i, "signal": "SELL"})
            else:
                signals.append({"index": i, "signal": "NONE"})
        return signals

    def _calc_rsi(self, closes: list, period: int) -> list:
        n   = len(closes)
        rsi = [None] * n
        if n < period + 1:
            return rsi
        gains, losses = [], []
        for i in range(1, period + 1):
            d = closes[i] - closes[i - 1]
            gains.append(max(d, 0))
            losses.append(max(-d, 0))
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        for i in range(period, n):
            if i > period:
                d        = closes[i] - closes[i - 1]
                avg_gain = (avg_gain * (period - 1) + max(d, 0))  / period
                avg_loss = (avg_loss * (period - 1) + max(-d, 0)) / period
            rsi[i] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1 + avg_gain / avg_loss))
        return rsi

    def _calc_sma(self, closes: list, period: int) -> list:
        n   = len(closes)
        sma = [None] * n
        for i in range(period - 1, n):
            sma[i] = sum(closes[i - period + 1 : i + 1]) / period
        return sma
