import math
from backend.strategies.base import Strategy


class VWAPMeanReversionStrategy(Strategy):
    name = "vwap_mean_reversion"

    def __init__(self, params: dict = None):
        defaults = {"std_dev_entry": 1.5, "std_dev_exit": 0.2, "lookback": 20}
        super().__init__({**defaults, **(params or {})})

    def generate_signals(self, candles: list) -> list:
        entry_th = self.params["std_dev_entry"]
        lb       = self.params["lookback"]

        n       = len(candles)
        signals = []
        vwap    = self._calc_daily_vwap(candles)

        for i in range(n):
            if i < lb or vwap[i] is None:
                signals.append({"index": i, "signal": "NONE"})
                continue

            window = [c["close"] for c in candles[i - lb : i]]
            mean   = sum(window) / lb
            std    = math.sqrt(sum((x - mean) ** 2 for x in window) / lb)

            if std == 0:
                signals.append({"index": i, "signal": "NONE"})
                continue

            price = candles[i]["close"]
            dev   = (price - vwap[i]) / std

            if dev <= -entry_th:
                signals.append({"index": i, "signal": "BUY"})
            elif dev >= entry_th:
                signals.append({"index": i, "signal": "SELL"})
            else:
                signals.append({"index": i, "signal": "NONE"})

        return signals

    def _calc_daily_vwap(self, candles: list) -> list:
        n       = len(candles)
        vwap    = [None] * n
        cum_tp  = 0.0
        count   = 0
        cur_day = None

        for i, c in enumerate(candles):
            try:
                day = str(c["time"])[:10]
            except Exception:
                day = cur_day

            if day != cur_day:
                cum_tp  = 0.0
                count   = 0
                cur_day = day

            tp      = (c["high"] + c["low"] + c["close"]) / 3
            cum_tp += tp
            count  += 1
            vwap[i] = cum_tp / count

        return vwap
