from datetime import datetime, timezone

from backend.strategies.base import Strategy


def _parse_utc(time_str):
    try:
        dt = datetime.fromisoformat(str(time_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _calc_atr(candles, period):
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


class MarketStructureBreakStrategy(Strategy):
    """
    Close breaks above recent swing high → BUY (bullish structure break).
    Close breaks below recent swing low → SELL (bearish structure break).
    NY session only (15:00-21:00 UTC by default).
    """
    name = "market_structure_break"
    strategy_type = "daytrading"

    def __init__(self, params=None):
        defaults = {
            "swing_bars":    10,
            "atr_period":    14,
            "session_start": 15,
            "session_end":   21,
            "sl_atr_mult":   1.5,
            "tp_atr_mult":   2.5,
        }
        super().__init__({**defaults, **(params or {})})

    def generate_signals(self, candles):
        n = len(candles)
        signals = [{"index": i, "signal": "NONE", "sl_price": None, "tp_price": None} for i in range(n)]
        if n == 0:
            return signals

        p = self.params
        swing_bars    = int(p["swing_bars"])
        atr_period    = int(p["atr_period"])
        session_start = int(p["session_start"])
        session_end   = int(p["session_end"])
        sl_mult       = float(p["sl_atr_mult"])
        tp_mult       = float(p["tp_atr_mult"])

        atrs = _calc_atr(candles, atr_period)
        daily_count = {}

        for i in range(swing_bars + atr_period, n):
            if atrs[i] is None:
                continue

            dt = _parse_utc(candles[i]["time"])
            if dt is None:
                continue
            if not (session_start <= dt.hour < session_end):
                continue

            day = dt.date()
            if daily_count.get(day, 0) >= 2:
                continue

            window     = candles[i - swing_bars:i]
            swing_high = max(c["high"] for c in window)
            swing_low  = min(c["low"]  for c in window)

            close = candles[i]["close"]
            atr   = atrs[i]
            signal = "NONE"
            sl = tp = None

            if close > swing_high:
                signal = "BUY"
                sl = close - sl_mult * atr
                tp = close + tp_mult * atr
            elif close < swing_low:
                signal = "SELL"
                sl = close + sl_mult * atr
                tp = close - tp_mult * atr

            if signal != "NONE":
                signals[i] = {"index": i, "signal": signal, "sl_price": sl, "tp_price": tp}
                daily_count[day] = daily_count.get(day, 0) + 1

        return signals
