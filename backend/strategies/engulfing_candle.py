from backend.strategies.base import Strategy


class EngulfingCandleStrategy(Strategy):
    name = "engulfing_candle"

    def __init__(self, params: dict = None):
        defaults = {
            "min_body_pips":  4,
            "rsi_period":     14,
            "atr_period":     14,
            "atr_avg_period": 20,
            "pip_size":       0.0001,
            "tp_multiplier":  2.0,
        }
        super().__init__({**defaults, **(params or {})})

    def generate_signals(self, candles: list) -> list:
        min_body   = self.params["min_body_pips"] * self.params["pip_size"]
        rsi_period = self.params["rsi_period"]
        atr_period = self.params["atr_period"]
        atr_avg_p  = self.params["atr_avg_period"]
        tp_mult    = self.params["tp_multiplier"]

        closes = [c["close"] for c in candles]
        n = len(candles)

        rsi     = self._calc_rsi(closes, rsi_period)
        atr     = self._calc_atr(candles, atr_period)
        atr_avg = self._calc_sma(atr, atr_avg_p)

        signals = []
        for i in range(n):
            if i == 0 or rsi[i] is None or atr[i] is None or atr_avg[i] is None:
                signals.append({"index": i, "signal": "NONE"})
                continue

            prev = candles[i - 1]
            curr = candles[i]

            prev_body_low  = min(prev["open"], prev["close"])
            prev_body_high = max(prev["open"], prev["close"])
            curr_body_low  = min(curr["open"], curr["close"])
            curr_body_high = max(curr["open"], curr["close"])
            body_size      = curr_body_high - curr_body_low

            curr_green = curr["close"] > curr["open"]
            curr_red   = curr["close"] < curr["open"]
            prev_red   = prev["close"] < prev["open"]
            prev_green = prev["close"] > prev["open"]
            engulfs    = curr_body_low <= prev_body_low and curr_body_high >= prev_body_high

            bullish_engulf = curr_green and prev_red and engulfs
            bearish_engulf = curr_red and prev_green and engulfs

            if body_size < min_body or atr[i] <= atr_avg[i]:
                signals.append({"index": i, "signal": "NONE"})
                continue

            entry = curr["close"]

            if bullish_engulf and rsi[i] < 60:
                sl_price = curr["low"]
                sl_dist  = entry - sl_price
                tp_price = entry + tp_mult * sl_dist
                signals.append({"index": i, "signal": "BUY", "sl_price": sl_price, "tp_price": tp_price})
            elif bearish_engulf and rsi[i] > 40:
                sl_price = curr["high"]
                sl_dist  = sl_price - entry
                tp_price = entry - tp_mult * sl_dist
                signals.append({"index": i, "signal": "SELL", "sl_price": sl_price, "tp_price": tp_price})
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

    def _calc_atr(self, candles: list, period: int) -> list:
        n = len(candles)
        trs = [0.0] * n
        for i in range(n):
            c = candles[i]
            if i == 0:
                trs[i] = c["high"] - c["low"]
            else:
                pc = candles[i - 1]["close"]
                trs[i] = max(c["high"] - c["low"], abs(c["high"] - pc), abs(c["low"] - pc))
        atrs = [None] * n
        if n >= period:
            atrs[period - 1] = sum(trs[:period]) / period
            for i in range(period, n):
                atrs[i] = (atrs[i - 1] * (period - 1) + trs[i]) / period
        return atrs

    def _calc_sma(self, values: list, period: int) -> list:
        n = len(values)
        out = [None] * n
        for i in range(period - 1, n):
            window = values[i - period + 1:i + 1]
            if any(v is None for v in window):
                continue
            out[i] = sum(window) / period
        return out
