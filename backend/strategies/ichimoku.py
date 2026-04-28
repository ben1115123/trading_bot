from backend.strategies.base import Strategy


class IchimokuStrategy(Strategy):
    name = "ichimoku"

    def __init__(self, params: dict = None):
        defaults = {"tenkan": 9, "kijun": 26, "senkou_b": 52, "displacement": 26}
        super().__init__({**defaults, **(params or {})})

    def generate_signals(self, candles: list) -> list:
        tenkan_p     = self.params["tenkan"]
        kijun_p      = self.params["kijun"]
        senkou_b_p   = self.params["senkou_b"]
        displacement = self.params["displacement"]

        n       = len(candles)
        signals = []

        def _mid(window):
            return (max(c["high"] for c in window) + min(c["low"] for c in window)) / 2

        for i in range(n):
            if i < max(senkou_b_p, kijun_p) + displacement or i == 0:
                signals.append({"index": i, "signal": "NONE"})
                continue

            cloud_i = i - displacement
            if cloud_i < senkou_b_p:
                signals.append({"index": i, "signal": "NONE"})
                continue

            tenkan      = _mid(candles[i - tenkan_p : i]) if i >= tenkan_p else None
            kijun       = _mid(candles[i - kijun_p  : i]) if i >= kijun_p  else None
            prev_i      = i - 1
            prev_tenkan = _mid(candles[prev_i - tenkan_p : prev_i]) if prev_i >= tenkan_p else None
            prev_kijun  = _mid(candles[prev_i - kijun_p  : prev_i]) if prev_i >= kijun_p  else None

            if any(v is None for v in [tenkan, kijun, prev_tenkan, prev_kijun]):
                signals.append({"index": i, "signal": "NONE"})
                continue

            senkou_a = (_mid(candles[cloud_i - tenkan_p  : cloud_i]) +
                        _mid(candles[cloud_i - kijun_p   : cloud_i])) / 2
            senkou_b = _mid(candles[cloud_i - senkou_b_p : cloud_i])

            cloud_top    = max(senkou_a, senkou_b)
            cloud_bottom = min(senkou_a, senkou_b)
            price        = candles[i]["close"]

            tk_cross_bull = prev_tenkan <= prev_kijun and tenkan > kijun
            tk_cross_bear = prev_tenkan >= prev_kijun and tenkan < kijun

            if tk_cross_bull and price > cloud_top:
                signals.append({"index": i, "signal": "BUY"})
            elif tk_cross_bear and price < cloud_bottom:
                signals.append({"index": i, "signal": "SELL"})
            else:
                signals.append({"index": i, "signal": "NONE"})

        return signals
