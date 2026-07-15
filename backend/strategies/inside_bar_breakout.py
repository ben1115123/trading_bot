from backend.strategies.base import Strategy


class InsideBarBreakoutStrategy(Strategy):
    name = "inside_bar_breakout"

    def __init__(self, params: dict = None):
        defaults = {
            "min_range_pips": 3,
            "min_break_pips": 1,
            "atr_period":     14,
            "atr_avg_period": 20,
            "pip_size":       0.0001,
            "tp_multiplier":  2.0,
        }
        super().__init__({**defaults, **(params or {})})

    def generate_signals(self, candles: list) -> list:
        min_range  = self.params["min_range_pips"] * self.params["pip_size"]
        min_break  = self.params["min_break_pips"] * self.params["pip_size"]
        atr_period = self.params["atr_period"]
        atr_avg_p  = self.params["atr_avg_period"]
        tp_mult    = self.params["tp_multiplier"]

        n = len(candles)
        atr     = self._calc_atr(candles, atr_period)
        atr_avg = self._calc_sma(atr, atr_avg_p)

        signals = []
        for i in range(n):
            if i < 2 or atr[i] is None or atr_avg[i] is None:
                signals.append({"index": i, "signal": "NONE"})
                continue

            mother = candles[i - 2]
            inside = candles[i - 1]
            curr   = candles[i]

            is_inside_bar = inside["high"] < mother["high"] and inside["low"] > mother["low"]
            if not is_inside_bar:
                signals.append({"index": i, "signal": "NONE"})
                continue

            inside_range = inside["high"] - inside["low"]
            if inside_range < min_range:
                signals.append({"index": i, "signal": "NONE"})
                continue

            if atr[i] <= atr_avg[i]:
                signals.append({"index": i, "signal": "NONE"})
                continue

            entry = curr["close"]
            breakout_up   = entry > inside["high"] + min_break
            breakout_down = entry < inside["low"] - min_break

            if breakout_up:
                sl_price = inside["low"]
                sl_dist  = entry - sl_price
                tp_price = entry + tp_mult * sl_dist
                signals.append({"index": i, "signal": "BUY", "sl_price": sl_price, "tp_price": tp_price})
            elif breakout_down:
                sl_price = inside["high"]
                sl_dist  = sl_price - entry
                tp_price = entry - tp_mult * sl_dist
                signals.append({"index": i, "signal": "SELL", "sl_price": sl_price, "tp_price": tp_price})
            else:
                signals.append({"index": i, "signal": "NONE"})

        return signals

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
