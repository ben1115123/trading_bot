"""Canonical symbol list for signal-loop-eligible trading pairs.

Single source of truth. Previously duplicated independently in
bot/live_signal_loop.py and bot/candle_stream.py -- they silently drifted
out of sync when USDCAD was onboarded 2026-07-13 (added only to
live_signal_loop.SYMBOLS), leaving candle_stream's (USDCAD, 15MIN) buffer
permanently empty ("ig_stream buffer not warm yet", every cycle, for 7
days straight) despite USDCAD being "active" in active_strategy the whole
time. candle_stream.py can't import bot.live_signal_loop directly (that
module already imports candle_stream, so the reverse import would be
circular) -- this module has zero imports and zero side effects, so both
can depend on it safely.
"""
SYMBOLS = ["US500", "US100", "DAX", "BTC", "EURUSD", "GBPUSD", "AUDUSD", "USDCAD"]
