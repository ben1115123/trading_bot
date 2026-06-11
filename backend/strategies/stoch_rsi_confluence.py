from datetime import datetime, timezone

from backend.strategies.stoch_rsi import StochRSIStrategy


def _parse_utc(time_str):
    try:
        dt = datetime.fromisoformat(str(time_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _calc_atr(candles: list, period: int) -> list:
    n  = len(candles)
    tr = [None] * n
    for i in range(n):
        high, low = candles[i]["high"], candles[i]["low"]
        if i == 0:
            tr[i] = high - low
            continue
        prev_close = candles[i - 1]["close"]
        tr[i] = max(high - low, abs(high - prev_close), abs(low - prev_close))

    atr = [None] * n
    for i in range(period - 1, n):
        window = tr[i - period + 1: i + 1]
        atr[i] = sum(window) / period
    return atr


def _percentile(values: list, pct: float):
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


class StochRSIConfluenceStrategy(StochRSIStrategy):
    """
    stoch_rsi base signals + session and ATR-regime confluence filters.

    Signals that pass all enabled filters are returned unchanged.
    Signals blocked by a filter are zeroed out (signal="NONE") but
    recorded via shadow_blocked/shadow_direction/shadow_reason so the
    signal loop can shadow-log them to paper_trades for A/B comparison.
    """
    name = "stoch_rsi_confluence"
    strategy_type = "swing"

    def __init__(self, params: dict = None):
        defaults = {
            "session_filter": True,
            "atr_filter":     True,
            "atr_period":     14,
            "atr_lookback":   50,
            "london_start":   7,
            "london_end":     9,
            "ny_start":       13,
            "ny_end":         16,
        }
        super().__init__({**defaults, **(params or {})})

    def generate_signals(self, candles: list) -> list:
        base_signals = super().generate_signals(candles)

        p              = self.params
        session_on     = bool(p["session_filter"])
        atr_on         = bool(p["atr_filter"])
        atr_period     = int(p["atr_period"])
        atr_lookback   = int(p["atr_lookback"])
        london_start   = int(p["london_start"])
        london_end     = int(p["london_end"])
        ny_start       = int(p["ny_start"])
        ny_end         = int(p["ny_end"])

        atr = _calc_atr(candles, atr_period) if atr_on else [None] * len(candles)

        out = []
        for i, sig in enumerate(base_signals):
            row = dict(sig)
            row["shadow_blocked"]   = False
            row["shadow_direction"] = None
            row["shadow_reason"]    = None

            signal = row.get("signal", "NONE")
            if signal not in ("BUY", "SELL"):
                out.append(row)
                continue

            reasons = []

            if session_on:
                dt = _parse_utc(candles[i]["time"])
                if dt is not None:
                    in_london = london_start <= dt.hour < london_end
                    in_ny     = ny_start <= dt.hour < ny_end
                    if not (in_london or in_ny):
                        reasons.append("session")
                # unparseable timestamp — fail open, no session reason

            if atr_on:
                current_atr = atr[i]
                window = [v for v in atr[max(0, i - atr_lookback + 1): i + 1] if v is not None]
                if current_atr is not None and len(window) >= 2:
                    low_th = _percentile(window, 33)
                    med_th = _percentile(window, 66)
                    if not (low_th <= current_atr <= med_th):
                        reasons.append("atr")
                # ATR not yet available — fail open, no atr reason

            if reasons:
                row["shadow_blocked"]   = True
                row["shadow_direction"] = 1 if signal == "BUY" else -1
                row["shadow_reason"]    = "+".join(reasons)
                row["signal"]           = "NONE"

            out.append(row)

        return out
