#!/usr/bin/env python3
"""Fetch Dukascopy M15/H1 candles into scripts/candle_cache/ as *_DUKA.json.

LOCAL BATCH TOOL — same status as scripts/fetch_twelvedata.py. The dependency
is deliberately NOT in requirements.txt: the container has no use for it and
Dockerfile:11 `COPY . .` would bake it into every image layer.

    pip3 install --target <somewhere> dukascopy-python   # 4.0.1 measured
    PYTHONPATH=<somewhere> python3 scripts/fetch_dukascopy.py

WHY DUKASCOPY (measured 2026-09-04, see CLAUDE.md):
  - Indices at TRUE INDEX SCALE — US500 7674.60 vs IG 7671, US100 29354.15 vs
    29289, DAX 26226.65 vs 26108. Twelve Data's free tier only served SPY/QQQ/
    EWG proxies, which is what voided active_strategy ids 29 and 30.
  - Sub-pip mean offset against IG mid on all four FX pairs (0.13-0.35 pips)
    against Twelve Data's +3.210 EURUSD / +2.434 AUDUSD.
  - ~24 months of M15, complete: 104 weekend gaps over 2 years is exactly
    52/year, and every other gap >1h is Christmas or New Year.

⚠️ INSTRUMENT NAMES ARE TRAPS. `INSTRUMENT_UK_SPX_GB_GBX` is a UK equity in
pence; `INSTRUMENT_ETF_CFD_DE_TECDAXE_DE_EUR` is a TecDAX ETF. Searching for
"SPX"/"NAS"/"DAX" returns those, not the indices. The index CFDs live in the
IDX group and are named below. ALWAYS re-verify the written file's price level
against a known IG snapshot — the name proves nothing. That check is built in
below and refuses to write on failure.

MID CONSTRUCTION: (bid + ask) / 2 applied to each of O/H/L/C independently,
identical to backend/backtesting/engine.py's IG path. Recorded per file in the
sidecar provenance so a later reader never has to infer it.

ONE SOURCE PER FILE. Never splice Dukascopy and Twelve Data into one cache —
that is the DAX/ETF defect with a subtler signature.

ADDITIVE ONLY. This script refuses to overwrite an existing file. Stage 4 rows
reference cache_file for provenance; destroying one orphans rows already
imported to the VPS.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import dukascopy_python as d
from dukascopy_python import instruments as I

CACHE_DIR = Path(__file__).resolve().parent / "candle_cache"

# symbol -> (dukascopy instrument constant, its literal name for provenance)
INSTRUMENTS = {
    "EURUSD": (I.INSTRUMENT_FX_MAJORS_EUR_USD,      "INSTRUMENT_FX_MAJORS_EUR_USD"),
    "GBPUSD": (I.INSTRUMENT_FX_MAJORS_GBP_USD,      "INSTRUMENT_FX_MAJORS_GBP_USD"),
    "AUDUSD": (I.INSTRUMENT_FX_MAJORS_AUD_USD,      "INSTRUMENT_FX_MAJORS_AUD_USD"),
    "USDCAD": (I.INSTRUMENT_FX_MAJORS_USD_CAD,      "INSTRUMENT_FX_MAJORS_USD_CAD"),
    "US500":  (I.INSTRUMENT_IDX_AMERICA_E_SANDP_500, "INSTRUMENT_IDX_AMERICA_E_SANDP_500"),
    "US100":  (I.INSTRUMENT_IDX_AMERICA_E_NQ_100,    "INSTRUMENT_IDX_AMERICA_E_NQ_100"),
    "DAX":    (I.INSTRUMENT_IDX_EUROPE_E_DAAX,       "INSTRUMENT_IDX_EUROPE_E_DAAX"),
}

INTERVALS = {"15MIN": d.INTERVAL_MIN_15, "HOUR": d.INTERVAL_HOUR_1}

# 2026-08-23 IG market snapshots. The level check is the ONLY thing that
# distinguishes an index from an ETF proxy; the instrument name does not.
IG_REFERENCE = {"US500": 7671.0, "US100": 29289.0, "DAX": 26108.0}
LEVEL_TOLERANCE = 0.10          # +/-10%


def cache_path(symbol: str, timeframe: str) -> Path:
    return CACHE_DIR / f"{symbol.upper()}_{timeframe.upper()}_DUKA.json"


def prov_path(symbol: str, timeframe: str) -> Path:
    return CACHE_DIR / f"{symbol.upper()}_{timeframe.upper()}_DUKA.provenance.json"


def build_mid(symbol: str, timeframe: str, start: datetime, end: datetime) -> tuple:
    """Returns (candles, meta). mid = (bid+ask)/2 per OHLC field."""
    inst, inst_name = INSTRUMENTS[symbol]
    interval = INTERVALS[timeframe]
    bid = d.fetch(inst, interval, d.OFFER_SIDE_BID, start, end)
    ask = d.fetch(inst, interval, d.OFFER_SIDE_ASK, start, end)
    if bid is None or ask is None or len(bid) == 0 or len(ask) == 0:
        raise RuntimeError(f"{symbol} {timeframe}: empty response")
    j = bid.join(ask, lsuffix="_bid", rsuffix="_ask", how="inner")
    candles = []
    for ts, row in j.iterrows():
        o = (row["open_bid"]  + row["open_ask"])  / 2
        h = (row["high_bid"]  + row["high_ask"])  / 2
        l = (row["low_bid"]   + row["low_ask"])   / 2
        c = (row["close_bid"] + row["close_ask"]) / 2
        if any(v != v for v in (o, h, l, c)):      # NaN guard, as engine.py does
            continue
        candles.append({
            "time":  ts.tz_convert("UTC").strftime("%Y-%m-%d %H:%M:%S"),
            "open":  float(o), "high": float(h), "low": float(l), "close": float(c),
            "volume": float(row.get("volume_bid", 0.0) or 0.0),
        })
    meta = {
        "source": "dukascopy",
        "client": "dukascopy-python 4.0.1",
        "instrument_constant": inst_name,
        "instrument_value": str(inst),
        "mid_construction": "(bid+ask)/2 applied to each of open/high/low/close "
                            "independently — identical to backend/backtesting/engine.py",
        "offer_sides_fetched": ["BID", "ASK"],
        "join": "inner on timestamp",
        "symbol": symbol, "timeframe": timeframe,
        "bars": len(candles),
        "date_start": candles[0]["time"] if candles else None,
        "date_end":   candles[-1]["time"] if candles else None,
        "requested_start": start.isoformat(), "requested_end": end.isoformat(),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "one_source_per_file": True,
        "notes": "Raw market data. NOT filtered by is_entry_allowed — that governs "
                 "ENTRIES, not candle availability; a backtest needs continuous bars "
                 "to evaluate holds across excluded hours.",
    }
    return candles, meta


def check_level(symbol: str, candles: list) -> str:
    ref = IG_REFERENCE.get(symbol)
    if ref is None:
        return "n/a (no IG reference for this symbol)"
    last = candles[-1]["close"]
    ratio = last / ref
    if not (1 - LEVEL_TOLERANCE) <= ratio <= (1 + LEVEL_TOLERANCE):
        raise RuntimeError(
            f"{symbol}: LEVEL CHECK FAILED — last close {last:.2f} vs IG reference "
            f"{ref} = {ratio:.3f}x. This is the SPY/QQQ/EWG proxy signature that "
            f"voided ids 29/30. REFUSING to write the file."
        )
    return f"OK {last:.2f} vs IG {ref} = {ratio:.3f}x"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=float, default=2.0)
    ap.add_argument("--pairs", default="EURUSD:15MIN,GBPUSD:15MIN,AUDUSD:15MIN,"
                                       "USDCAD:15MIN,US500:15MIN,US100:15MIN,"
                                       "EURUSD:HOUR,GBPUSD:HOUR,AUDUSD:HOUR,"
                                       "USDCAD:HOUR,US500:HOUR,US100:HOUR")
    ap.add_argument("--force", action="store_true",
                    help="allow overwrite (default REFUSES — additive only)")
    a = ap.parse_args()

    CACHE_DIR.mkdir(exist_ok=True)
    end = datetime.now(timezone.utc).replace(tzinfo=None)
    start = end - timedelta(days=int(a.years * 365))
    written = []
    for spec in a.pairs.split(","):
        sym, tf = spec.strip().split(":")
        out, pout = cache_path(sym, tf), prov_path(sym, tf)
        if out.exists() and not a.force:
            print(f"SKIP {out.name} — already exists (additive only; --force to override)")
            continue
        try:
            candles, meta = build_mid(sym, tf, start, end)
            meta["level_check"] = check_level(sym, candles)
        except Exception as e:
            print(f"FAIL {sym} {tf}: {type(e).__name__}: {e}")
            continue
        out.write_text(json.dumps(candles))
        pout.write_text(json.dumps(meta, indent=2))
        size = out.stat().st_size
        written.append((sym, tf, len(candles), meta["date_start"], meta["date_end"],
                        meta["instrument_constant"], size, meta["level_check"]))
        print(f"WROTE {out.name}: {len(candles)} bars {meta['date_start']} .. "
              f"{meta['date_end']}  {size:,}B  level={meta['level_check']}")
    print(f"\n{len(written)} file(s) written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
