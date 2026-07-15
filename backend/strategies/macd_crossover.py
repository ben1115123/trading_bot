from backend.strategies.base import Strategy


class MACDCrossoverStrategy(Strategy):
    name = "macd_crossover"

    def __init__(self, params: dict = None):
        defaults = {
            "fast":       12,
            "slow":       26,
            "signal":     9,
            "ema_period": 200,
        }
        super().__init__({**defaults, **(params or {})})

    def generate_signals(self, candles: list) -> list:
        fast_p   = self.params["fast"]
        slow_p   = self.params["slow"]
        signal_p = self.params["signal"]
        ema_p    = self.params["ema_period"]

        closes = [c["close"] for c in candles]
        n = len(closes)

        ema_fast  = self._calc_ema(closes, fast_p)
        ema_slow  = self._calc_ema(closes, slow_p)
        ema_trend = self._calc_ema(closes, ema_p)

        macd_line = [None] * n
        for i in range(n):
            if ema_fast[i] is not None and ema_slow[i] is not None:
                macd_line[i] = ema_fast[i] - ema_slow[i]

        sig_line = self._calc_ema_of_list(macd_line, signal_p)

        hist = [None] * n
        for i in range(n):
            if macd_line[i] is not None and sig_line[i] is not None:
                hist[i] = macd_line[i] - sig_line[i]

        signals = []
        for i in range(n):
            if (i == 0
                    or macd_line[i] is None or macd_line[i - 1] is None
                    or sig_line[i] is None  or sig_line[i - 1] is None
                    or hist[i] is None or hist[i - 1] is None
                    or ema_trend[i] is None):
                signals.append({"index": i, "signal": "NONE"})
                continue

            cross_up   = macd_line[i - 1] < sig_line[i - 1] and macd_line[i] > sig_line[i]
            cross_down = macd_line[i - 1] > sig_line[i - 1] and macd_line[i] < sig_line[i]
            close      = closes[i]

            hist_turned_positive = hist[i - 1] <= 0 and hist[i] > 0
            hist_turned_negative = hist[i - 1] >= 0 and hist[i] < 0

            if cross_up and hist_turned_positive and close > ema_trend[i]:
                signals.append({"index": i, "signal": "BUY"})
            elif cross_down and hist_turned_negative and close < ema_trend[i]:
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
        n = len(values)
        out = [None] * n
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
