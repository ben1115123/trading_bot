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
