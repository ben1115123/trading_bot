from datetime import datetime, timezone

from backend.strategies.base import Strategy

SYMBOL_PIP_SIZE = {
    "EURUSD": 0.0001,
    "US500":  1.0,
    "DAX":    1.0,
    "US100":  1.0,
}
_DEFAULT_PIP_SIZE = 0.0001


def _parse_utc(time_str: str):
    try:
        dt = datetime.fromisoformat(str(time_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


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


def _calc_ema(values: list, period: int) -> list:
    n = len(values)
    out = [None] * n
    if n < period:
        return out
    k = 2.0 / (period + 1)
    out[period - 1] = sum(values[:period]) / period
    for i in range(period, n):
        out[i] = values[i] * k + out[i - 1] * (1 - k)
    return out


class SilverBulletStrategy(Strategy):
    """
    ICT Silver Bullet: FVG setups formed during the NY-open killzone,
    entered on retracement into the gap. SL at FVG edge, TP at nearest
    swing extreme (fallback ATR-based).
    """
    name = "silver_bullet"
    strategy_type = "daytrading"

    def __init__(self, params: dict = None):
        defaults = {
            "kill_start":     13,    # killzone start hour UTC
            "kill_end":       16,    # killzone end hour UTC
            "min_gap_atr":    0.3,   # minimum FVG size as fraction of ATR
            "fvg_expiry":     8,     # candles before FVG expires
            "atr_period":     10,    # ATR period
            "swing_lookback": 10,    # candles for swing high/low detection
            "tp_swing_bars":  20,    # look back N bars for nearest swing TP
            "use_htf_bias":   False, # optional daily EMA200 filter
        }
        super().__init__({**defaults, **(params or {})})

    def _daily_ema_bias(self, candles: list) -> dict:
        """Map each candle's date -> EMA200 of the PREVIOUS day's daily closes."""
        day_close: dict = {}
        for c in candles:
            dt = _parse_utc(c["time"])
            if dt is None:
                continue
            day_close[dt.date()] = c["close"]  # last write per day wins (candles assumed ordered)

        days = sorted(day_close.keys())
        closes = [day_close[d] for d in days]
        emas = _calc_ema(closes, 200)

        bias: dict = {}
        for idx, day in enumerate(days):
            # bias for `day` uses EMA up to and including the PRIOR day only
            bias[day] = emas[idx - 1] if idx > 0 else None
        return bias

    def generate_signals(self, candles: list) -> list:
        p              = self.params
        kill_start     = int(p["kill_start"])
        kill_end       = int(p["kill_end"])
        min_gap_atr    = float(p["min_gap_atr"])
        fvg_expiry     = int(p["fvg_expiry"])
        atr_period     = int(p["atr_period"])
        swing_lookback = int(p["swing_lookback"])
        tp_swing_bars  = int(p["tp_swing_bars"])
        use_htf_bias   = bool(p["use_htf_bias"])

        n = len(candles)

        def _blank(i):
            return {"index": i, "signal": "NONE", "sl_price": None, "tp_price": None,
                    "fvg_top": None, "fvg_bottom": None}

        signals = [_blank(i) for i in range(n)]
        if n == 0:
            return signals

        atrs = _calc_atr(candles, atr_period)

        has_datetime = _parse_utc(candles[0]["time"]) is not None

        htf_bias = self._daily_ema_bias(candles) if (use_htf_bias and has_datetime) else None

        # active_fvg: most recent unmitigated gap formed during the killzone
        active_fvg = None
        last_signal_date = None

        for i in range(2, n):
            # Expire stale FVG before evaluating anything at this bar
            if active_fvg is not None and (i - active_fvg["formed_at"]) > fvg_expiry:
                active_fvg = None

            atr_i = atrs[i]

            in_killzone = True
            if has_datetime:
                prev_dt = _parse_utc(candles[i - 1]["time"])
                in_killzone = prev_dt is not None and kill_start <= prev_dt.hour < kill_end

            if atr_i is not None and in_killzone:
                c0, c2 = candles[i - 2], candles[i]

                direction = None
                gap_low = gap_high = None

                # Bullish FVG: gap between c0.high and c2.low
                if c0["high"] < c2["low"]:
                    gap_low, gap_high = c0["high"], c2["low"]
                    if (gap_high - gap_low) >= min_gap_atr * atr_i:
                        direction = "BUY"

                # Bearish FVG: gap between c2.high and c0.low
                elif c0["low"] > c2["high"]:
                    gap_low, gap_high = c2["high"], c0["low"]
                    if (gap_high - gap_low) >= min_gap_atr * atr_i:
                        direction = "SELL"

                if direction is not None:
                    allow = True
                    if htf_bias is not None:
                        dt = _parse_utc(c2["time"])
                        ema = htf_bias.get(dt.date()) if dt else None
                        if ema is not None:
                            if direction == "BUY" and not (c2["close"] > ema):
                                allow = False
                            if direction == "SELL" and not (c2["close"] < ema):
                                allow = False

                    if allow:
                        active_fvg = {
                            "direction": direction,
                            "gap_low":   gap_low,
                            "gap_high":  gap_high,
                            "formed_at": i,
                        }

            # Entry: close retraces into the gap zone (must be after formation bar)
            if active_fvg is not None and i > active_fvg["formed_at"]:
                close = candles[i]["close"]
                if active_fvg["gap_low"] <= close <= active_fvg["gap_high"]:
                    dt = _parse_utc(candles[i]["time"])
                    day = dt.date() if dt else None

                    if day is None or last_signal_date != day:
                        fvg_top    = active_fvg["gap_high"]
                        fvg_bottom = active_fvg["gap_low"]
                        atr_now    = atr_i if atr_i is not None else (candles[i]["high"] - candles[i]["low"])
                        atr_buffer = 0.1 * atr_now

                        lo = max(0, i - tp_swing_bars)
                        window = candles[lo:i]
                        swing_high = max((c["high"] for c in window), default=None)
                        swing_low  = min((c["low"]  for c in window), default=None)

                        if active_fvg["direction"] == "BUY":
                            sl_price = fvg_bottom - atr_buffer
                            if swing_high is not None and swing_high > close:
                                tp_price = swing_high
                            else:
                                tp_price = close + 2.5 * atr_now
                        else:
                            sl_price = fvg_top + atr_buffer
                            if swing_low is not None and swing_low < close:
                                tp_price = swing_low
                            else:
                                tp_price = close - 2.5 * atr_now

                        signals[i] = {
                            "index":      i,
                            "signal":     active_fvg["direction"],
                            "sl_price":   round(sl_price, 6),
                            "tp_price":   round(tp_price, 6),
                            "fvg_top":    fvg_top,
                            "fvg_bottom": fvg_bottom,
                        }
                        last_signal_date = day

                    active_fvg = None  # gap mitigated — don't re-enter same gap

        return signals
