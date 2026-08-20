"""Tests for watchdog.check_candle_divergence — the reader candle_source_compare
never had.

Values are not invented. Every threshold case below is pinned to a real number
measured from the 21,051 rows of candle_source_compare spanning 2026-07-08 ->
2026-08-20: the p99 baselines themselves, each symbol's worst genuine
observation, and the single 2026-07-21 EURUSD anomaly the check exists to
catch.
"""
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import watchdog as W  # noqa: E402

T0 = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
ANOMALY = -114008596.19   # the real 2026-07-21 EURUSD delta_pips
EURUSD_WORST_REAL = -30.87
US100_WORST_REAL = 619.01


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE candle_source_compare (id INTEGER PRIMARY KEY, checked_at TEXT,"
        " symbol TEXT, timeframe TEXT, delta_pips REAL)")
    conn.commit()
    monkeypatch.setattr(W, "DB_PATH", db)
    sent: list[str] = []
    monkeypatch.setattr(W, "_send_telegram", lambda e, m: (sent.append(m), True)[1])
    monkeypatch.setattr(W, "_append_alert_log", lambda *a, **k: None)

    def add(symbol, timeframe, delta, at):
        conn.execute(
            "INSERT INTO candle_source_compare (checked_at,symbol,timeframe,delta_pips)"
            " VALUES (?,?,?,?)",
            ((at - timedelta(minutes=5)).isoformat(), symbol, timeframe, delta))
        conn.commit()

    def run(state, at):
        sent.clear()
        W.check_candle_divergence({}, state, at)
        return list(sent)

    yield add, run
    conn.close()


def test_empty_window_is_silent(env):
    _, run = env
    assert run({}, T0) == []


def test_worst_real_observation_passes(env):
    """30.87 pips is the largest genuine EURUSD divergence in 4,020 rows."""
    add, run = env
    add("EURUSD", "15MIN", EURUSD_WORST_REAL, T0)
    assert run({}, T0) == []


def test_the_actual_anomaly_fires(env):
    add, run = env
    add("EURUSD", "15MIN", ANOMALY, T0)
    out = run({}, T0)
    assert len(out) == 1
    assert "CANDLE SOURCE DIVERGENCE" in out[0]
    assert "EURUSD 15MIN" in out[0]


def test_dedup_then_realert(env):
    add, run = env
    state = {}
    add("EURUSD", "15MIN", ANOMALY, T0)
    assert len(run(state, T0)) == 1

    t = T0 + timedelta(minutes=30)
    add("EURUSD", "15MIN", ANOMALY, t)
    assert run(state, t) == [], "must not re-alert inside REALERT_MINUTES"

    t = T0 + timedelta(minutes=61)
    add("EURUSD", "15MIN", ANOMALY, t)
    assert len(run(state, t)) == 1


def test_recovery_clears_state(env):
    add, run = env
    state = {}
    add("EURUSD", "15MIN", ANOMALY, T0)
    run(state, T0)
    t = T0 + timedelta(minutes=90)
    add("EURUSD", "15MIN", -12.0, t)
    assert run(state, t) == []
    assert not any(k.startswith("candle_divergence") for k in state)


def test_unbanded_symbol_is_reported_not_passed(env):
    """Tri-state discipline: a missing baseline is a build-time omission
    (Bug 2's shape), so it must be noisy rather than treated as healthy."""
    add, run = env
    add("XAUUSD", "15MIN", 3.0, T0)
    out = run({}, T0)
    assert len(out) == 1
    assert "UNCHECKED" in out[0] and "XAUUSD" in out[0]


def test_us100_off_session_staleness_is_not_flagged(env):
    """~100-pip mean divergence on US100 is yfinance being stale off-session,
    not a stream fault. Per-symbol thresholds exist so this stays quiet while
    FX stays sensitive at 1-2 pips."""
    add, run = env
    add("US100", "15MIN", US100_WORST_REAL, T0)
    assert run({}, T0) == []


def test_fx_midsize_corruption_fires(env):
    """50 pips is unremarkable for US100 and impossible for AUDUSD (p99 9.22).
    A global threshold would miss this; a per-symbol one catches it."""
    add, run = env
    add("AUDUSD", "15MIN", 50.0, T0)
    assert any("AUDUSD" in m for m in run({}, T0))


def test_every_streamed_symbol_has_a_baseline():
    """Fails if a symbol is added to the stream without a divergence baseline —
    the same guard the band check has, for the same Bug 2 reason."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import symbols  # noqa: E402

    streamed = set(getattr(symbols, "SYMBOLS", []))
    baselined = {s for s, _tf in W.DIVERGENCE_P99}
    undecided = streamed - baselined - set(W.DIVERGENCE_NO_BASELINE)
    assert not undecided, (
        f"{sorted(undecided)} is in symbols.SYMBOLS with neither a "
        f"DIVERGENCE_P99 baseline nor an explicit DIVERGENCE_NO_BASELINE entry")
    assert not (baselined & set(W.DIVERGENCE_NO_BASELINE)), \
        "a symbol cannot be both baselined and excluded"
