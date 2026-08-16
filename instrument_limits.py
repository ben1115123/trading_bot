"""Per-instrument execution limits shared by the live path and the backtest engine.

Zero imports, no side effects — same safe-import contract as symbols.py and
engine_version.py. That property is the whole point: `engine.py` cannot import
these from `bot/live_signal_loop.py`, because that module imports
`scripts.run_backtest`, which imports `backend.backtesting.engine` — a cycle —
and it also imports `bot.execute_trade`, which opens a live IG session at
import time. A backtest must never do either.

WHY A SHARED MODULE AND NOT A COPY: this codebase has already been bitten
twice by duplicated instrument tables drifting apart —
  - `EPIC_CONFIG`/`SYMBOLS` duplicated into `bot/candle_stream.py` behind a
    comment claiming it "mirrors live_signal_loop.SYMBOLS"; USDCAD was added
    to one and not the other, and its 15MIN buffer was never created for 7
    days (2026-07-20, bug 2). Fixed by `symbols.py`.
  - `_MIN_SL_DIST` itself existed only in the live path, so the backtest
    engine sized every trade off unfloored candle ranges. On AUDUSD 15MIN the
    floor binds on 55% of signal entries — see the parity work.
Add a symbol here, not in a second dict somewhere else.

MIN_SL_DIST: minimum stop distance in PRICE units for the symbol (not pips,
not points-scale). A candle-range stop narrower than this is widened to it.
Rationale is broker-side: IG rejects orders whose stop sits inside its
per-instrument minimum distance, and a sub-floor stop also sizes into an
implausibly large position.
"""

MIN_SL_DIST: dict[str, float] = {
    "EURUSD": 0.00050,
    "GBPUSD": 0.00060,
    "AUDUSD": 0.00050,
    "EURGBP": 0.00050,
    "USDCAD": 0.00050,
    "USDJPY": 0.050,
    "US500":  3.0,
    "US100":  4.0,
    "DAX":    5.0,
    "XAUUSD": 1.50,
}


# Contract value per 1.0 unit of price movement, in account currency (USD).
# lot_size = risk / (sl_distance * VALUE_PER_POINT[symbol])
#
# SINGLE SOURCE. Until 2026-08-16 this existed as THREE independent copies:
#   bot/execute_trade.py       EPIC_CONFIG[...]["value_per_point"]
#   backend/backtesting/engine.py  EPIC_CONFIG[...]["value_per_point"]
#   bot/live_signal_loop.py    _EPIC_VALUE_PER_POINT
# They never contradicted each other — reconciled cell by cell, zero conflicts —
# but they DIVERGED BY OMISSION, which was worse. USDCAD was missing from the
# resolver's copy, so `.get(symbol, 1.0)` silently returned 1.0 instead of
# 10000.0 and every USDCAD paper trade booked ~1/2000th of its intended value
# across 97 rows (findings doc finding 16). EURGBP, NZDUSD and USDJPY existed
# in one copy only.
#
# ACCESS BY [symbol], NEVER .get(symbol, default). A KeyError on an
# unregistered symbol is the CORRECT behaviour — it is loud, immediate, and
# would have caught finding 16 on USDCAD's very first paper trade in June
# instead of 97 rows later. A default is what turns a missing key into silently
# wrong arithmetic.
#
# USDJPY IS 100, NOT 10000. JPY pairs quote to 0.01 per pip, not 0.0001. This
# value existed only in the engine's copy; a careless "all FX is 10000"
# consolidation would have shipped a 100x error inside the fix for a 1,900x one.
VALUE_PER_POINT: dict[str, float] = {
    # indices — $1 per index point
    "US500":  1.0,
    "US100":  1.0,
    "DAX":    1.0,
    # FX minis — $1/pip, 0.0001 pip, 10k contract
    "EURUSD": 10000.0,
    "GBPUSD": 10000.0,
    "AUDUSD": 10000.0,
    "USDCAD": 10000.0,
    "EURGBP": 10000.0,
    "NZDUSD": 10000.0,
    # JPY pair — pip is 0.01, so a tenth of the others. NOT 10000.
    "USDJPY": 100.0,
    # crypto
    "BTC":    0.1,
}
