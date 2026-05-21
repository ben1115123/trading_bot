from backend.strategies.base import Strategy


class MACDRSIStrategy(Strategy):
    name = "macd_rsi"

    def __init__(self, params: dict = None):
        defaults = {
            "fast":       12,
            "slow":       26,
            "signal":     9,
            "rsi_period": 14,
            "ema_period": 50,
        }
        super().__init__({**defaults, **(params or {})})

    def generate_signals(self, candles: list) -> list:
        fast_p    = self.params["fast"]
        slow_p    = self.params["slow"]
        signal_p  = self.params["signal"]
        rsi_p     = self.params["rsi_period"]
        ema_p     = self.params["ema_period"]

        closes = [c["close"] for c in candles]
        n      = len(closes)

        ema_fast  = self._calc_ema(closes, fast_p)
        ema_slow  = self._calc_ema(closes, slow_p)
        ema_trend = self._calc_ema(closes, ema_p)
        rsi       = self._calc_rsi(closes, rsi_p)

        macd_line = [None] * n
        for i in range(n):
            if ema_fast[i] is not None and ema_slow[i] is not None:
                macd_line[i] = ema_fast[i] - ema_slow[i]

        sig_line = self._calc_ema_of_list(macd_line, signal_p)

        signals = []
        for i in range(n):
            if (i == 0
                    or macd_line[i] is None or macd_line[i - 1] is None
                    or sig_line[i] is None  or sig_line[i - 1] is None
                    or rsi[i] is None
                    or ema_trend[i] is None):
                signals.append({"index": i, "signal": "NONE"})
                continue

            cross_up   = macd_line[i - 1] < sig_line[i - 1] and macd_line[i] > sig_line[i]
            cross_down = macd_line[i - 1] > sig_line[i - 1] and macd_line[i] < sig_line[i]
            close      = closes[i]

            if cross_up and rsi[i] < 60 and close > ema_trend[i]:
                signals.append({"index": i, "signal": "BUY"})
            elif cross_down and rsi[i] > 40 and close < ema_trend[i]:
                signals.append({"index": i, "signal": "SELL"})
            else:
                signals.append({"index": i, "signal": "NONE"})

        return signals

    def _calc_ema(self, closes: list, period: int) -> list:
        n = len(closes)
        out = [None] * n
        if n < period:
            return out
        out[period - 1] = sum(closes[:period]) / period
        k = 2.0 / (period + 1)
        for i in range(period, n):
            out[i] = closes[i] * k + out[i - 1] * (1 - k)
        return out

    def _calc_ema_of_list(self, values: list, period: int) -> list:
        n     = len(values)
        out   = [None] * n
        valid = [(i, v) for i, v in enumerate(values) if v is not None]
        if len(valid) < period:
            return out
        seed_i = valid[period - 1][0]
        out[seed_i] = sum(v for _, v in valid[:period]) / period
        k = 2.0 / (period + 1)
        prev_i = seed_i
        for idx, val in valid[period:]:
            out[idx] = val * k + out[prev_i] * (1 - k)
            prev_i = idx
        return out

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
