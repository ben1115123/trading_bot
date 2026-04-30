import threading
import time
import json
from datetime import datetime, timezone

from database.models import get_active_strategy
from bot.execute_trade import place_trade

from backend.strategies.rsi import RSIStrategy
from backend.strategies.supertrend import SuperTrendStrategy
from backend.strategies.vwap_ema import VWAPEMAStrategy
from backend.strategies.ema_ribbon import EMARibbonStrategy
from backend.strategies.bb_squeeze import BBSqueezeStrategy
from backend.strategies.rsi_divergence import RSIDivergenceStrategy
from backend.strategies.orb import ORBStrategy
from backend.strategies.ichimoku import IchimokuStrategy
from backend.strategies.keltner import KeltnerChannelStrategy
from backend.strategies.stoch_rsi import StochRSIStrategy
from backend.strategies.ema_cross_volume import EMACrossVolumeStrategy
from backend.strategies.vwap_mean_reversion import VWAPMeanReversionStrategy

SYMBOLS        = ["US500", "US100", "BTC"]
CANDLE_COUNT   = 200
CHECK_INTERVAL = 3600   # seconds
SL_ATR_MULT    = 1.5
TP_ATR_MULT    = 3.0

YF_SYMBOLS   = {"US500": "^GSPC", "US100": "^NDX", "BTC": "BTC-USD"}
YF_INTERVALS = {"5MIN": "5m", "HOUR": "1h", "DAY": "1d"}
YF_PERIODS   = {"5m": "60d", "1h": "730d", "1d": "5y"}

STRATEGIES = {
    "rsi":                 RSIStrategy,
    "supertrend":          SuperTrendStrategy,
    "vwap_ema":            VWAPEMAStrategy,
    "ema_ribbon":          EMARibbonStrategy,
    "bb_squeeze":          BBSqueezeStrategy,
    "rsi_divergence":      RSIDivergenceStrategy,
    "orb":                 ORBStrategy,
    "ichimoku":            IchimokuStrategy,
    "keltner":             KeltnerChannelStrategy,
    "stoch_rsi":           StochRSIStrategy,
    "ema_cross_volume":    EMACrossVolumeStrategy,
    "vwap_mean_reversion": VWAPMeanReversionStrategy,
}


def _fetch_candles(symbol: str, timeframe: str) -> list:
    import yfinance as yf
    ticker   = YF_SYMBOLS.get(symbol.upper())
    interval = YF_INTERVALS.get(timeframe.upper(), "1h")
    period   = YF_PERIODS.get(interval, "730d")
    df = yf.download(ticker, period=period, interval=interval,
                     auto_adjust=True, progress=False)
    if df.empty:
        return []
    candles = []
    for ts, row in df.iterrows():
        try:
            def _get(col):
                val = row[col]
                return float(val.iloc[0]) if hasattr(val, "iloc") else float(val)
            o, h, l, c = _get("Open"), _get("High"), _get("Low"), _get("Close")
        except Exception:
            continue
        if any(v != v for v in [o, h, l, c]):
            continue
        candles.append({"time": str(ts), "open": o, "high": h, "low": l, "close": c})
    return candles[-CANDLE_COUNT:]


def _calc_atr(candles: list, period: int = 14) -> float | None:
    if len(candles) < period + 1:
        return None
    trs = []
    for i in range(1, len(candles)):
        h  = candles[i]["high"]
        l  = candles[i]["low"]
        pc = candles[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period


def _check_symbol(symbol: str, last_fired: dict) -> None:
    active = get_active_strategy(symbol=symbol)
    if not active:
        print(f"[signal_loop] [{symbol}] No active strategy — skipping")
        return

    strategy_name = active["strategy_name"]
    timeframe     = active["timeframe"] or "HOUR"

    strategy_cls = STRATEGIES.get(strategy_name)
    if not strategy_cls:
        print(f"[signal_loop] [{symbol}] Unknown strategy: {strategy_name} — skipping")
        return

    try:
        params = json.loads(active["params_json"] or "{}")
    except Exception:
        params = {}

    candles = _fetch_candles(symbol, timeframe)
    if len(candles) < 50:
        print(f"[signal_loop] [{symbol}] Only {len(candles)} candles — need 50+ — skipping")
        return

    signals = strategy_cls(params).generate_signals(candles)
    if not signals:
        return

    action         = signals[-1].get("signal", "NONE")
    last_candle_ts = candles[-1]["time"]

    print(f"[signal_loop] [{symbol}] {strategy_name} @ {last_candle_ts}: {action}")

    if action not in ("BUY", "SELL"):
        return

    if last_fired.get(symbol) == last_candle_ts:
        print(f"[signal_loop] [{symbol}] Already fired for this candle — skipping")
        return

    atr = _calc_atr(candles)
    if atr is None:
        print(f"[signal_loop] [{symbol}] ATR failed — skipping")
        return

    entry = candles[-1]["close"]
    if action == "BUY":
        sl = round(entry - SL_ATR_MULT * atr, 2)
        tp = round(entry + TP_ATR_MULT * atr, 2)
    else:
        sl = round(entry + SL_ATR_MULT * atr, 2)
        tp = round(entry - TP_ATR_MULT * atr, 2)

    print(f"[signal_loop] [{symbol}] FIRE {action} entry≈{entry:.2f} sl={sl} tp={tp} atr={atr:.4f}")

    try:
        result = place_trade(symbol, action.lower(), sl=sl, tp=tp,
                             strategy_name=strategy_name,
                             source="signal_loop")
        if result:
            last_fired[symbol] = last_candle_ts
            print(f"[signal_loop] [{symbol}] Trade placed ✓")
        else:
            print(f"[signal_loop] [{symbol}] Trade returned False")
    except Exception as e:
        print(f"[signal_loop] [{symbol}] Exception: {e}")


def _loop() -> None:
    last_fired: dict = {}
    print("[signal_loop] Started — checking every hour")
    while True:
        now = datetime.now(timezone.utc)
        print(f"\n[signal_loop] Cycle {now.strftime('%Y-%m-%d %H:%M UTC')}")
        for symbol in SYMBOLS:
            try:
                _check_symbol(symbol, last_fired)
            except Exception as e:
                print(f"[signal_loop] [{symbol}] Unhandled error: {e}")
        print(f"[signal_loop] Sleeping {CHECK_INTERVAL}s")
        time.sleep(CHECK_INTERVAL)


def start_signal_loop() -> None:
    threading.Thread(target=_loop, daemon=True, name="live_signal_loop").start()
    print("Live signal loop started (1h interval)")
