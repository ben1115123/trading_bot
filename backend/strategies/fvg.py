from datetime import datetime, timezone

from backend.strategies.base import Strategy


def _in_fvg_session(time_str: str) -> bool:
    """True if timestamp falls in London (07:00-09:59 UTC) or NY open (13:00-15:59 UTC)."""
    try:
        dt = datetime.fromisoformat(str(time_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        m = dt.hour * 60 + dt.minute
        return (420 <= m <= 599) or (780 <= m <= 959)
    except Exception:
        return False


def _calc_atr(candles: list, period: int) -> list:
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


class FVGStrategy(Strategy):
    """
    Fair Value Gap (SMC) strategy.
    Detects 3-candle imbalance gaps formed in London/NY session windows,
    then enters when price retraces back into the gap zone.
    """
    name = "fvg"

    def __init__(self, params: dict = None):
        defaults = {
            "atr_period":     14,
            "min_gap_atr":    0.3,  # gap must be >= this fraction of ATR14
            "expiry_candles": 10,   # FVG invalidated after N candles with no retracement
        }
        super().__init__({**defaults, **(params or {})})

    def generate_signals(self, candles: list) -> list:
        atr_period    = int(self.params["atr_period"])
        min_gap_atr   = float(self.params["min_gap_atr"])
        expiry        = int(self.params["expiry_candles"])

        n    = len(candles)
        atrs = _calc_atr(candles, atr_period)
        signals = [{"index": i, "signal": "NONE"} for i in range(n)]

        # active_fvg: most recent unmitigated gap
        # keys: direction, gap_low, gap_high, formed_at
        active_fvg = None

        for i in range(2, n):
            # Expire stale FVG before evaluating anything at this bar
            if active_fvg is not None and (i - active_fvg["formed_at"]) > expiry:
                active_fvg = None

            atr_i = atrs[i]
            if atr_i is not None:
                c0, c2 = candles[i - 2], candles[i]

                # Bullish FVG: gap between c0.high and c2.low
                if c0["high"] < c2["low"]:
                    gap_low  = c0["high"]
                    gap_high = c2["low"]
                    if (gap_high - gap_low) >= min_gap_atr * atr_i and _in_fvg_session(c2["time"]):
                        active_fvg = {
                            "direction": "BUY",
                            "gap_low":   gap_low,
                            "gap_high":  gap_high,
                            "formed_at": i,
                        }

                # Bearish FVG: gap between c2.high and c0.low
                elif c0["low"] > c2["high"]:
                    gap_low  = c2["high"]
                    gap_high = c0["low"]
                    if (gap_high - gap_low) >= min_gap_atr * atr_i and _in_fvg_session(c2["time"]):
                        active_fvg = {
                            "direction": "SELL",
                            "gap_low":   gap_low,
                            "gap_high":  gap_high,
                            "formed_at": i,
                        }

            # Entry: close retraces into the gap zone (must be after formation bar)
            if active_fvg is not None and i > active_fvg["formed_at"]:
                close = candles[i]["close"]
                if active_fvg["gap_low"] <= close <= active_fvg["gap_high"]:
                    signals[i] = {"index": i, "signal": active_fvg["direction"]}
                    active_fvg = None  # gap mitigated — don't re-enter same gap

        return signals
