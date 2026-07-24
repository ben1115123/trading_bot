"""IG price-unit normalization — the single boundary between IG-native
price scale and the decimal scale used everywhere else in this codebase
(SL/TP, risk sizing, DB storage, webhooks, dashboards).

Some epics on some IG accounts (confirmed: CS.D.EURUSD.MINI.IP on demo
account Z67Y2C) return snapshot bid/offer in points scale (e.g. 11407.2)
rather than decimal FX price (1.14072) — the same epic was decimal on
the live account (TW75S). IG's own `scalingFactor` snapshot field does
NOT reliably indicate this: GBPUSD/AUDUSD carry scalingFactor=10000
despite already being decimal, while EURUSD (the one epic that actually
needs /10000 on this account) carries scalingFactor=1. Classification
here is empirical — compare the live bid against a known-good decimal
range per symbol — never derived from IG's metadata.

Scale is classified once per symbol per session and cached module-wide
(shared across every process that imports this module — execute_trade,
candle_stream, positions_poller, sync_ig_trades all run in the same
container). Ambiguous readings (fit neither the decimal nor the x10000
band) are never guessed — they block that symbol from trading until a
human resolves it.
"""
import threading

from bot.notifier import send_telegram

# (low, high) bounds on the DECIMAL price for each symbol — wide enough
# to tolerate real market movement, narrow enough that a x10000 scale
# error can never land inside the same band as the correct one.
_EXPECTED_DECIMAL_RANGE: dict[str, tuple[float, float]] = {
    "EURUSD": (0.5, 2.0),
    "GBPUSD": (0.5, 2.5),
    "AUDUSD": (0.3, 1.5),
    "USDCAD": (0.5, 2.0),
    "US500":  (500.0, 20000.0),
    "US100":  (2000.0, 100000.0),
    "DAX":    (2000.0, 100000.0),
}

CHECKED_SYMBOLS = frozenset(_EXPECTED_DECIMAL_RANGE)

_CANDIDATE_DIVISORS = (1.0, 10000.0)

_lock = threading.Lock()
_scale: dict[str, float] = {}  # symbol -> divisor; native / divisor = decimal
_currency: dict[str, str] = {}  # symbol -> IG deal currency code (e.g. 'USD', 'CAD')
_DEFAULT_CURRENCY = "USD"


class PriceScaleAmbiguous(Exception):
    pass


def _classify(symbol: str, bid: float) -> float:
    lo, hi = _EXPECTED_DECIMAL_RANGE[symbol]
    for divisor in _CANDIDATE_DIVISORS:
        if lo <= bid / divisor <= hi:
            return divisor
    raise PriceScaleAmbiguous(
        f"{symbol}: live bid={bid} fits neither decimal ({lo}-{hi}) "
        f"nor x10000-scaled ({lo * 10000}-{hi * 10000}) band"
    )


def init_price_scales(ig_service, epic_map: dict[str, str], force: bool = False) -> None:
    """Classify each symbol's native price scale once and cache it.

    force=True always re-fetches and re-classifies — call this after
    session recreate / 401 retry / account switch, since scale is
    account-dependent (confirmed to differ between the demo and live
    account for EURUSD). force=False only fetches symbols missing from
    the cache, so repeat calls from independent sessions (candle_stream,
    sync_ig_trades) sharing this process converge on one cache without
    redundant API calls.

    Only symbols in CHECKED_SYMBOLS are classified — unlisted symbols
    (e.g. BTC) are left unmanaged and pass through to_decimal/to_native
    unchanged, matching pre-existing behaviour.
    """
    with _lock:
        targets = [
            (s, e) for s, e in epic_map.items()
            if s in CHECKED_SYMBOLS and (force or s not in _scale)
        ]
    for symbol, epic in targets:
        try:
            market = ig_service.fetch_market_by_epic(epic)
        except Exception as e:
            # Transient fetch failure -- do not cache and do not block trading
            # outright the way a genuine ambiguous-price reading does. Next
            # call (10min refresh / next reconnect) retries naturally.
            print(f"[ig_scale] market fetch failed for {symbol}: {e}")
            continue

        try:
            bid = float(market["snapshot"]["bid"])
            divisor = _classify(symbol, bid)
            with _lock:
                _scale[symbol] = divisor
            print(f"[ig_scale] {symbol} ({epic}) bid={bid} -> divisor={divisor}")
        except PriceScaleAmbiguous as e:
            with _lock:
                _scale.pop(symbol, None)
            print(f"[ig_scale] AMBIGUOUS {e} — {symbol} blocked from trading")
            send_telegram(
                f"PRICE SCALE AMBIGUOUS {symbol} — {e} — trading blocked until resolved",
                level="ERROR",
            )
        except Exception as e:
            print(f"[ig_scale] classification failed for {symbol}: {e}")

        # Deal currency — same market object, no extra API call. IG instrument
        # properties are NOT uniform per-epic (3rd such bug, after
        # scalingFactor and snapshotTime timezone): USDCAD's only supported
        # currency is CAD, not USD, since USD is the base there rather than
        # the quote. Always derive per-epic, never assume.
        try:
            currencies = (market.get("instrument", {}) or {}).get("currencies") or []
            code = currencies[0]["code"] if currencies else None
            if code:
                with _lock:
                    _currency[symbol] = code
                print(f"[ig_scale] {symbol} ({epic}) currency_code -> {code}")
            else:
                print(f"[ig_scale] {symbol} ({epic}) no currencies in instrument "
                      f"metadata — falls back to {_DEFAULT_CURRENCY} if needed")
        except Exception as e:
            print(f"[ig_scale] currency_code lookup failed for {symbol}: {e} — "
                  f"falls back to {_DEFAULT_CURRENCY} if needed")


def is_resolved(symbol: str) -> bool:
    if symbol not in CHECKED_SYMBOLS:
        return True
    with _lock:
        return symbol in _scale


def get_currency_code(symbol: str) -> str:
    """Deal currency for create_open_position's currency_code param, derived
    per-epic (see init_price_scales) rather than assumed. Falls back to
    'USD' only on lookup failure — logged loudly so a wrong-currency
    order is never sent silently.
    """
    with _lock:
        code = _currency.get(symbol)
    if code is None:
        print(f"[ig_scale] currency_code fallback to {_DEFAULT_CURRENCY} for "
              f"{symbol} — no cached value, verify instrument metadata")
        return _DEFAULT_CURRENCY
    return code


def to_decimal(symbol: str, native_value):
    if native_value is None:
        return None
    if symbol not in CHECKED_SYMBOLS:
        return native_value
    with _lock:
        divisor = _scale.get(symbol)
    if divisor is None:
        raise RuntimeError(f"price scale unresolved for {symbol} — refusing to convert")
    return native_value / divisor


def to_native(symbol: str, decimal_value):
    if decimal_value is None:
        return None
    if symbol not in CHECKED_SYMBOLS:
        return decimal_value
    with _lock:
        divisor = _scale.get(symbol)
    if divisor is None:
        raise RuntimeError(f"price scale unresolved for {symbol} — refusing to convert")
    return decimal_value * divisor
