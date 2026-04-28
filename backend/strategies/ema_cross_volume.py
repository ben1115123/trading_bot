from backend.strategies.base import Strategy


class EMACrossVolumeStrategy(Strategy):
    name = "ema_cross_volume"

    def __init__(self, params: dict = None):
        defaults = {"fast": 8, "slow": 21, "vol_period": 20}
        super().__init__({**defaults, **(params or {})})

    def generate_signals(self, candles: list) -> list:
        fast_p = self.params["fast"]
        slow_p = self.params["slow"]
        vol_p  = self.params["vol_period"]

        closes  = [c["close"] for c in candles]
        volumes = [c.get("volume", 0) for c in candles]

        ema_fast = self._calc_ema(closes, fast_p)
        ema_slow = self._calc_ema(closes, slow_p)
        avg_vol  = self._sma(volumes, vol_p)

        signals = []
        for i in range(len(candles)):
            if (i == 0
                    or ema_fast[i] is None or ema_fast[i - 1] is None
                    or ema_slow[i] is None or ema_slow[i - 1] is None):
                signals.append({"index": i, "signal": "NONE"})
                continue

            cross_bull = ema_fast[i - 1] <= ema_slow[i - 1] and ema_fast[i] > ema_slow[i]
            cross_bear = ema_fast[i - 1] >= ema_slow[i - 1] and ema_fast[i] < ema_slow[i]

            vol_ok = True
            if avg_vol[i] is not None and avg_vol[i] > 0 and volumes[i] > 0:
                vol_ok = volumes[i] > avg_vol[i]

            if cross_bull and vol_ok:
                signals.append({"index": i, "signal": "BUY"})
            elif cross_bear and vol_ok:
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

    def _sma(self, values: list, period: int) -> list:
        n   = len(values)
        out = [None] * n
        for i in range(n):
            window = [v for v in values[max(0, i - period + 1) : i + 1]
                      if v is not None and v > 0]
            if len(window) == period:
                out[i] = sum(window) / period
        return out
