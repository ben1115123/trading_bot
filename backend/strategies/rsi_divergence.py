from backend.strategies.base import Strategy


class RSIDivergenceStrategy(Strategy):
    name = "rsi_divergence"

    def __init__(self, params: dict = None):
        defaults = {"rsi_period": 14, "lookback": 5, "overbought": 70, "oversold": 30}
        super().__init__({**defaults, **(params or {})})

    def generate_signals(self, candles: list) -> list:
        period     = self.params["rsi_period"]
        lookback   = self.params["lookback"]
        overbought = self.params["overbought"]
        oversold   = self.params["oversold"]

        closes  = [c["close"] for c in candles]
        rsi     = self._calc_rsi(closes, period)
        n       = len(candles)
        signals = []

        for i in range(n):
            if i < period + lookback or rsi[i] is None:
                signals.append({"index": i, "signal": "NONE"})
                continue

            price_now = closes[i]
            rsi_now   = rsi[i]
            signal    = "NONE"

            # Bullish divergence: lower low in price, higher low in RSI — oversold zone only
            if rsi_now < oversold:
                prior_low_price = min(closes[i - lookback : i])
                if price_now < prior_low_price:
                    try:
                        prior_low_idx = closes.index(prior_low_price, i - lookback, i)
                        prior_rsi     = rsi[prior_low_idx]
                        if prior_rsi is not None and rsi_now > prior_rsi:
                            signal = "BUY"
                    except ValueError:
                        pass

            # Bearish divergence: higher high in price, lower high in RSI — overbought zone only
            if signal == "NONE" and rsi_now > overbought:
                prior_high_price = max(closes[i - lookback : i])
                if price_now > prior_high_price:
                    try:
                        prior_high_idx = closes.index(prior_high_price, i - lookback, i)
                        prior_rsi      = rsi[prior_high_idx]
                        if prior_rsi is not None and rsi_now < prior_rsi:
                            signal = "SELL"
                    except ValueError:
                        pass

            signals.append({"index": i, "signal": signal})

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
