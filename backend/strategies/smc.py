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


class SMCStrategy(Strategy):
    """
    SMC (Smart Money Concepts) strategy.
    Uses BOS/CHoCH to establish structural bias, then enters on
    bias-aligned FVGs when price retraces into the gap zone.
    No trades fire until a BOS establishes the first bias.
    """
    name = "smc"

    def __init__(self, params: dict = None):
        defaults = {
            "swing_lookback":    10,    # candles for swing high/low detection
            "min_gap_atr":       0.5,   # minimum FVG size as fraction of ATR
            "fvg_expiry":        15,    # candles before unmitigated FVG expires
            "atr_period":        10,    # ATR period
            "use_session_filter": False, # True = London/NY only; False = all hours
        }
        super().__init__({**defaults, **(params or {})})

    def generate_signals(self, candles: list) -> list:
        lookback          = int(self.params["swing_lookback"])
        min_gap           = float(self.params["min_gap_atr"])
        expiry            = int(self.params["fvg_expiry"])
        atr_period        = int(self.params["atr_period"])
        use_session_filter = bool(self.params.get("use_session_filter", False))

        n    = len(candles)
        atrs = _calc_atr(candles, atr_period)

        signals = [
            {"index": i, "signal": "NONE", "bias": None,
             "fvg_top": None, "fvg_bottom": None, "bos_level": None}
            for i in range(n)
        ]

        bias: str | None = None          # "BULLISH" | "BEARISH" | None
        open_fvgs: list  = []            # {direction, gap_low, gap_high, formed_at}

        for i in range(n):
            close_i = candles[i]["close"]

            # ── 1. Expire stale FVGs ──────────────────────────────────────
            open_fvgs = [f for f in open_fvgs if (i - f["formed_at"]) <= expiry]

            # ── 2. BOS / CHoCH ───────────────────────────────────────────
            # Lookback window is candles[i-lookback : i] — never includes candle i
            if i >= lookback:
                swing_high = max(candles[j]["high"] for j in range(i - lookback, i))
                swing_low  = min(candles[j]["low"]  for j in range(i - lookback, i))
                old_bias   = bias

                if close_i > swing_high:
                    bias = "BULLISH"
                    signals[i]["bos_level"] = swing_high
                elif close_i < swing_low:
                    bias = "BEARISH"
                    signals[i]["bos_level"] = swing_low

                # CHoCH — bias flipped: discard all misaligned FVGs
                if bias != old_bias and old_bias is not None:
                    open_fvgs = []

            signals[i]["bias"] = bias

            # ── 3. FVG detection ─────────────────────────────────────────
            # 3-candle pattern: [i-2], [i-1], [i]
            # Session filter uses middle candle [i-1]
            # Only store FVGs that align with current bias
            if i >= 2 and bias is not None and atrs[i] is not None:
                c0, c1, c2 = candles[i - 2], candles[i - 1], candles[i]
                atr_i = atrs[i]

                session_ok = (not use_session_filter) or _in_fvg_session(c1["time"])

                if bias == "BULLISH" and c0["high"] < c2["low"]:
                    gap_low  = c0["high"]
                    gap_high = c2["low"]
                    if (gap_high - gap_low) >= min_gap * atr_i and session_ok:
                        open_fvgs.append({
                            "direction": "BUY",
                            "gap_low":   gap_low,
                            "gap_high":  gap_high,
                            "formed_at": i,
                        })

                elif bias == "BEARISH" and c0["low"] > c2["high"]:
                    gap_low  = c2["high"]
                    gap_high = c0["low"]
                    if (gap_high - gap_low) >= min_gap * atr_i and session_ok:
                        open_fvgs.append({
                            "direction": "SELL",
                            "gap_low":   gap_low,
                            "gap_high":  gap_high,
                            "formed_at": i,
                        })

            # ── 4. Entry ─────────────────────────────────────────────────
            # Only enter on candles AFTER the FVG formed (i > formed_at)
            # If multiple qualify, use the most recent (highest formed_at)
            candidates = [
                f for f in open_fvgs
                if i > f["formed_at"] and f["gap_low"] <= close_i <= f["gap_high"]
            ]
            if candidates:
                best = max(candidates, key=lambda f: f["formed_at"])
                signals[i]["signal"]     = best["direction"]
                signals[i]["fvg_top"]    = best["gap_high"]
                signals[i]["fvg_bottom"] = best["gap_low"]
                open_fvgs = [f for f in open_fvgs if f is not best]

        return signals
