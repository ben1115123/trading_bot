"""Behaviour tests for the price-band value check (findings 25/26).

The regression being pinned: on 2026-07-21 a single Lightstreamer tick
arrived in points scale (11402.0) while ig_scale correctly held divisor=1.0,
so to_decimal was a no-op and the raw value was buffered. It surfaced 15
minutes later as paper_trades id=824 at -$2,500.

The value check is deliberately independent of the scale check, because
detection must not depend on which scale mode the account is in.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ig_scale


# --- the regression -------------------------------------------------------

def test_the_actual_bad_tick_is_rejected():
    """11402.0 under divisor=1.0 — exactly what was held on 2026-07-21."""
    assert ig_scale.in_expected_band("EURUSD", 11402.0 / 1.0) is False


def test_the_same_value_passes_under_points_scale():
    """Under divisor=10000 the identical raw value is a LEGITIMATE quote.

    This is the point of doing the check post-conversion rather than on the
    raw feed value: 11402.0 is only wrong relative to the scale in force.
    """
    assert ig_scale.in_expected_band("EURUSD", 11402.0 / 10000.0) is True


def test_healthy_neighbours_pass():
    """The ticks either side of the anomaly, from candle_source_compare."""
    for value in (1.14032, 1.14026, 1.140380859375):
        assert ig_scale.in_expected_band("EURUSD", value) is True


# --- the tri-state contract ----------------------------------------------

def test_unbanded_symbol_returns_None_not_True():
    """None means UNCHECKED and must be distinguishable from plausible.

    A default-True would make an unregistered symbol silently unvalidated —
    the fail-open shape that produced findings 16, 20, 22 and 23.
    """
    assert ig_scale.in_expected_band("BTC", 50000.0) is None
    assert ig_scale.in_expected_band("NOTASYMBOL", 1.0) is None


def test_none_value_is_unchecked_not_violation():
    assert ig_scale.in_expected_band("EURUSD", None) is None


def test_nan_is_a_violation():
    assert ig_scale.in_expected_band("EURUSD", float("nan")) is False


# --- coverage and margins ------------------------------------------------

def test_every_streamable_symbol_has_a_band():
    """EPIC_MAP == CHECKED_SYMBOLS today; the check is unreachable-by-design
    for unbanded symbols. If someone adds an epic without a band, this fails
    — which is the USDCAD Bug 2 shape caught at test time instead of in
    production after 7 silent days.
    """
    from bot.candle_stream import EPIC_MAP
    missing = {s for s in EPIC_MAP if ig_scale.expected_band(s) is None}
    assert not missing, f"streamable symbols with no price band: {missing}"


def test_bands_reject_a_x10000_scale_error_for_every_symbol():
    """The band's whole job: a points-scale value must never land inside the
    decimal band. Checked at both edges for every symbol.
    """
    for symbol, (lo, hi) in ig_scale._EXPECTED_DECIMAL_RANGE.items():
        for edge in (lo, hi):
            assert ig_scale.in_expected_band(symbol, edge * 10000) is False, \
                f"{symbol}: {edge} x10000 wrongly inside band"


def test_real_observed_extremes_pass_with_margin():
    """Widest real closes seen across 19,859 candle_source_compare rows.

    Tightest margin is USDCAD at 1.42x from the band edge — a false positive
    needs a 42% move, which is a redenomination, not a market move.
    """
    observed = {
        "EURUSD": (1.13566, 1.16143),
        "GBPUSD": (1.32761, 1.35710),
        "AUDUSD": (0.69078, 0.71290),
        "USDCAD": (1.38488, 1.41273),
        "US500":  (7295.47, 7815.43),
        "US100":  (27010.90, 30241.20),
    }
    for symbol, (low, high) in observed.items():
        assert ig_scale.in_expected_band(symbol, low) is True, symbol
        assert ig_scale.in_expected_band(symbol, high) is True, symbol
