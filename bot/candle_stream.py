"""IG Lightstreamer candle stream — REST warm-up + live streaming.

Hybrid design (option c from the yfinance-lag investigation):
  1. REST warm-up: fetch a lookback buffer per needed symbol+timeframe
     before subscribing, so strategies have indicator history from the
     first cycle instead of waiting for the buffer to fill live.
  2. Subscribe via IGStreamService to CHART:{epic}:{scale} — IG pushes
     server-side-completed OHLC bars, closing the price-lag gap that
     motivated this (signal price == execution price universe).

IG's Lightstreamer CHART topic only supports scales SECOND/1MINUTE/
5MINUTE/HOUR — there is no native 15MINUTE. 15MIN candles are built
by aggregating three consecutive 5MINUTE bars client-side.

Runs independently of bot.execute_trade — its own IGService/session,
not the shared live-trading singleton (avoids import side effects and
a second create_session() call stomping on the live bot's session).
Read-only: this module never places orders.

Always started regardless of CANDLE_SOURCE (see live_signal_loop.py) —
parallel validation mode needs the stream running and comparison data
accumulating even while yfinance still drives real trades.
"""
import json
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from trading_ig import IGService
from trading_ig.stream import IGStreamService, Subscription, ClientListener

from ig_env import get_ig_credentials
import ig_scale
from database.models import get_active_strategies, upsert_heartbeat
from scripts.run_backtest import STRATEGIES, _fetch_yfinance_candles
from bot.notifier import send_telegram
from symbols import SYMBOLS

# -------------------------
# Config
# -------------------------
EPIC_MAP = {
    "US500":  "IX.D.SPTRD.IFMM.IP",
    "US100":  "IX.D.NASDAQ.IFMM.IP",
    "DAX":    "IX.D.DAX.IFMS.IP",
    "EURUSD": "CS.D.EURUSD.MINI.IP",
    "GBPUSD": "CS.D.GBPUSD.MINI.IP",
    "AUDUSD": "CS.D.AUDUSD.MINI.IP",
    "USDCAD": "CS.D.USDCAD.MINI.IP",
}
# SYMBOLS imported from symbols.py -- single source of truth shared with
# live_signal_loop.py (see symbols.py docstring for why USDCAD silently
# never traded for 7 days when this used to be a second hardcoded copy).

# IG's raw REST resolution enum values. conv_resol() (which translates
# pandas-offset strings like "15Min" -> "MINUTE_15") is only invoked by
# trading_ig when return_dataframe=True -- this module uses
# return_dataframe=False, so conv_resol never runs and the raw enum must
# be passed directly, or IG's API rejects the resolution param outright.
_REST_RESOLUTION = {"15MIN": "MINUTE_15", "HOUR": "HOUR"}

# CHART:{epic}:{scale} — only these 4 scales exist server-side
_LS_SCALE_FOR_TIMEFRAME = {"HOUR": "HOUR", "15MIN": "5MINUTE"}  # 15MIN is aggregated

WARMUP_COUNT = 200   # 4x the longest active lookback (ema_pullback ema_slow=50) —
                     # cheap since it's a one-shot REST call, cost only matters
                     # pre-dedup and this runs once at startup / per reconnect gap
MAX_BUFFER = 500

# Quota-fallback Telegram dedup: same anti-spam pattern as scripts/watchdog.py's
# state file, keyed per condition-type (warm-up vs gap-backfill) since they're
# raised from different call sites with different frequency characteristics.
_FALLBACK_STATE_PATH = Path("/tmp/candle_stream_fallback_state.json")
_FALLBACK_ALERT_COOLDOWN_SEC = 6 * 3600


def _should_alert_fallback(condition: str) -> bool:
    try:
        state = json.loads(_FALLBACK_STATE_PATH.read_text())
    except Exception:
        state = {}
    last = state.get(condition)
    if last:
        try:
            if (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() < _FALLBACK_ALERT_COOLDOWN_SEC:
                return False
        except Exception:
            pass
    state[condition] = datetime.now(timezone.utc).isoformat()
    try:
        _FALLBACK_STATE_PATH.write_text(json.dumps(state))
    except Exception as e:
        print(f"[candle_stream] fallback state write failed: {e}")
    return True

CHART_FIELDS = [
    "UTM",
    "BID_OPEN", "BID_HIGH", "BID_LOW", "BID_CLOSE",
    "OFR_OPEN", "OFR_HIGH", "OFR_LOW", "OFR_CLOSE",
    "CONS_END", "CONS_TICK_COUNT",
]

_BACKOFF_STEPS = [5, 10, 20, 40, 80, 160, 300]  # seconds, caps at 300

# -------------------------
# State
# -------------------------
_lock = threading.Lock()
_buffers: dict[tuple, list] = {}          # (symbol, timeframe) -> [candle, ...] sorted by time
_partial_15min: dict[str, dict] = {}      # symbol -> {"bucket_start": iso, "bars": [...], "count": int}
_disconnected = threading.Event()
_disconnected.set()  # starts "disconnected" until first successful connect

# IG's REST snapshotTime is in the ACCOUNT'S configured timezone, not UTC
# (confirmed via session creation's timezoneOffset field, e.g. 8 for this
# account/MYT) -- despite looking like a naive UTC string. Caught live
# 2026-07-15: a 15MIN REST-warmed candle stamped 8h into the future.
# Captured once at session creation (account timezone is a static setting,
# doesn't change mid-session) and reused by every _normalize_rest_time call.
_ACCOUNT_TZ_OFFSET_HOURS: int | None = None


def get_candles(symbol: str, timeframe: str) -> list | None:
    """Public read accessor for live_signal_loop.py. None = buffer not warm
    enough yet to trust (caller should skip that symbol's check, not crash)."""
    with _lock:
        buf = _buffers.get((symbol, timeframe))
        return list(buf) if buf and len(buf) >= 20 else None


def debug_buffer_tail(symbol: str, timeframe: str, n: int = 10) -> list:
    """Diagnostic accessor — bypasses get_candles' 20-candle warm threshold
    and returns the raw buffer tail regardless of trustworthiness. Never
    called from the trading path; exists so buffer contents can be
    inspected from outside the process (module state isn't visible to a
    separate `docker exec` python invocation)."""
    with _lock:
        buf = _buffers.get((symbol, timeframe), [])
        return list(buf[-n:])


# -------------------------
# REST (warm-up + gap backfill)
# -------------------------
def _rest_fetch(ig_service: IGService, symbol: str, timeframe: str, count: int) -> list | None:
    epic = EPIC_MAP.get(symbol)
    resolution = _REST_RESOLUTION.get(timeframe)
    if not epic or not resolution:
        return None
    try:
        result = ig_service.fetch_historical_prices_by_epic_and_num_points(
            epic=epic, resolution=resolution, numpoints=count,
        )
    except Exception as e:
        if "exceeded-account-historical-data-allowance" in str(e):
            raise _QuotaExceeded(str(e)) from e
        print(f"[candle_stream] REST fetch failed {symbol}/{timeframe}: {e}")
        return None

    prices_raw = result.get("prices")
    if not prices_raw:
        return None

    if not ig_scale.is_resolved(symbol):
        print(f"[candle_stream] {symbol} price scale unresolved — skipping REST fetch")
        return None

    candles = []
    for row in prices_raw:
        try:
            o = (row["openPrice"]["bid"] + row["openPrice"]["ask"]) / 2
            h = (row["highPrice"]["bid"] + row["highPrice"]["ask"]) / 2
            l = (row["lowPrice"]["bid"] + row["lowPrice"]["ask"]) / 2
            c = (row["closePrice"]["bid"] + row["closePrice"]["ask"]) / 2
        except (KeyError, TypeError):
            continue
        if any(v != v for v in [o, h, l, c]):  # NaN check
            continue
        candles.append({
            "time": _normalize_rest_time(row["snapshotTime"]),
            "open": ig_scale.to_decimal(symbol, float(o)),
            "high": ig_scale.to_decimal(symbol, float(h)),
            "low": ig_scale.to_decimal(symbol, float(l)),
            "close": ig_scale.to_decimal(symbol, float(c)),
        })
    return candles


def _normalize_rest_time(raw: str) -> str:
    """IG REST snapshotTime is 'yyyy/MM/dd HH:mm:ss' in the account's
    configured timezone (_ACCOUNT_TZ_OFFSET_HOURS), NOT UTC — subtract the
    offset before labeling UTC, or REST-sourced candles get mislabeled
    hours into the future/past. Falls back to offset=0 (old, wrong
    behavior) only if the offset was never captured — better than crashing,
    but every session creation should set it before this is ever called."""
    try:
        dt = datetime.strptime(str(raw), "%Y/%m/%d %H:%M:%S")
        offset_hours = _ACCOUNT_TZ_OFFSET_HOURS if _ACCOUNT_TZ_OFFSET_HOURS is not None else 0
        dt_utc = dt - timedelta(hours=offset_hours)
        return dt_utc.replace(tzinfo=timezone.utc).isoformat()
    except Exception:
        return str(raw)


class _QuotaExceeded(Exception):
    pass


def _normalize_yf_time(raw: str) -> str | None:
    """yfinance candle time is str(pandas.Timestamp). Despite the old
    assumption that it's always 'YYYY-MM-DD HH:MM:SS+00:00', yfinance
    intraday data can come back tz-aware in the EXCHANGE's local zone
    (e.g. Europe/London, BST=+01:00 in summer) -- found live 2026-07-16
    via mixed +00:00/+01:00 offsets in the same GBPUSD buffer. Convert to
    true UTC instead of blindly relabeling; only assume-UTC for genuinely
    naive timestamps. Same future-dated guard as the REST snapshotTime fix
    (2026-07-15): a bad conversion here would otherwise silently poison the
    buffer with a future candle. Returns None (caller drops it) if rejected
    or unparseable."""
    try:
        dt = datetime.fromisoformat(str(raw).replace(" ", "T", 1))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
    except Exception:
        print(f"[candle_stream] yfinance timestamp unparseable, dropping candle: {raw!r}")
        return None
    if dt > datetime.now(timezone.utc) + timedelta(minutes=1):
        print(f"[candle_stream] yfinance candle rejected -- future-dated after "
              f"UTC conversion: raw={raw!r} -> {dt.isoformat()}")
        return None
    return dt.isoformat()


def _yfinance_fallback(symbol: str, timeframe: str, count: int) -> list | None:
    """Warm-up/backfill fallback when IG's weekly historical-data REST quota
    is exhausted. yfinance candles are already decimal-scale (real ticker
    price) -- no ig_scale conversion needed, unlike the IG REST path."""
    try:
        raw = _fetch_yfinance_candles(symbol, timeframe, count)
    except Exception as e:
        print(f"[candle_stream] yfinance fallback failed {symbol}/{timeframe}: {e}")
        return None
    candles = []
    for c in raw:
        t = _normalize_yf_time(c["time"])
        if t is None:
            continue
        candles.append({
            "time": t,
            "open": c["open"], "high": c["high"], "low": c["low"], "close": c["close"],
        })
    return candles


def _needed_pairs() -> list:
    """Derived from active_strategy at warm-up/reconnect time, not hardcoded —
    only pairs with a real strategy class (STRATEGIES dict) and a known epic
    (EPIC_MAP) are included. swiftalgo-style rows and unsupported timeframes
    are skipped."""
    pairs = set()
    for symbol in SYMBOLS:
        if symbol not in EPIC_MAP:
            continue
        try:
            active_list = get_active_strategies(symbol=symbol)
        except Exception as e:
            print(f"[candle_stream] get_active_strategies failed for {symbol}: {e}")
            continue
        for active in active_list:
            timeframe = active.get("timeframe", "HOUR")
            strategy_name = active.get("strategy_name", "")
            if strategy_name not in STRATEGIES:
                continue
            if timeframe not in _LS_SCALE_FOR_TIMEFRAME:
                continue
            pairs.add((symbol, timeframe))
    return sorted(pairs)


def _warm_up(ig_service: IGService, pairs: list) -> None:
    print(f"[candle_stream] warm-up starting for {len(pairs)} pairs: {pairs}")
    fallback_used = False
    for symbol, timeframe in pairs:
        source = "IG REST"
        try:
            candles = _rest_fetch(ig_service, symbol, timeframe, WARMUP_COUNT)
        except _QuotaExceeded as e:
            print(f"[candle_stream] IG historical-data quota exceeded for "
                  f"{symbol}/{timeframe} -- falling back to yfinance: {e}")
            candles = _yfinance_fallback(symbol, timeframe, WARMUP_COUNT)
            source = "yfinance (quota fallback)"
            fallback_used = True
        if not candles:
            print(f"[candle_stream] warm-up got nothing for {symbol}/{timeframe} (source={source})")
            continue
        with _lock:
            _buffers[(symbol, timeframe)] = candles[-MAX_BUFFER:]
        print(f"[candle_stream] warm-up {symbol}/{timeframe}: {len(candles)} candles (source={source})")
    if fallback_used and _should_alert_fallback("warmup"):
        send_telegram(
            "candle_stream: IG historical-data quota exceeded -- warm-up "
            "fell back to yfinance for one or more pairs", level="WARN")


def _backfill_gap(ig_service: IGService, symbol: str, timeframe: str) -> bool:
    """After reconnect: REST already returns IG-server-aggregated 15MIN bars
    directly (MINUTE_15 is a real REST resolution even though it isn't a
    Lightstreamer scale), so gap backfill never touches the 3-bar aggregator
    — it fills the buffer with genuine complete candles regardless of
    timeframe. Bounded to WARMUP_COUNT so a long outage doesn't over-fetch.
    Returns True if the yfinance quota fallback engaged, for the caller to
    dedupe its Telegram alert to one per reconnect cycle."""
    source = "IG REST"
    fallback_used = False
    try:
        candles = _rest_fetch(ig_service, symbol, timeframe, WARMUP_COUNT)
    except _QuotaExceeded as e:
        print(f"[candle_stream] IG historical-data quota exceeded for "
              f"{symbol}/{timeframe} -- falling back to yfinance: {e}")
        candles = _yfinance_fallback(symbol, timeframe, WARMUP_COUNT)
        source = "yfinance (quota fallback)"
        fallback_used = True
    if not candles:
        print(f"[candle_stream] gap backfill got nothing for {symbol}/{timeframe} (source={source})")
        return fallback_used
    with _lock:
        existing = _buffers.get((symbol, timeframe), [])
        seen_times = {c["time"] for c in existing}
        merged = existing + [c for c in candles if c["time"] not in seen_times]
        merged.sort(key=lambda c: c["time"])
        _buffers[(symbol, timeframe)] = merged[-MAX_BUFFER:]
    print(f"[candle_stream] gap backfill {symbol}/{timeframe}: buffer now {len(merged)} (source={source})")
    return fallback_used


# -------------------------
# Streaming
# -------------------------
def _mid_ohlc(symbol: str, values: dict) -> tuple | None:
    """(BID_x + OFR_x) / 2 per field — matches the REST warm-up's mid-price
    convention so the two never disagree on price basis. Converted to
    decimal scale via ig_scale before being buffered, same as REST."""
    if not ig_scale.is_resolved(symbol):
        return None
    try:
        o = (float(values["BID_OPEN"]) + float(values["OFR_OPEN"])) / 2
        h = (float(values["BID_HIGH"]) + float(values["OFR_HIGH"])) / 2
        l = (float(values["BID_LOW"]) + float(values["OFR_LOW"])) / 2
        c = (float(values["BID_CLOSE"]) + float(values["OFR_CLOSE"])) / 2
        return (
            ig_scale.to_decimal(symbol, o), ig_scale.to_decimal(symbol, h),
            ig_scale.to_decimal(symbol, l), ig_scale.to_decimal(symbol, c),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _epic_for_item(item_name: str) -> str | None:
    # item_name format: "CHART:{epic}:{scale}"
    parts = item_name.split(":")
    return parts[1] if len(parts) >= 2 else None


def _symbol_for_epic(epic: str) -> str | None:
    for symbol, e in EPIC_MAP.items():
        if e == epic:
            return symbol
    return None


def _update_hour_buffer(symbol: str, utm_ms: int, mid: tuple, cons_end: bool) -> None:
    o, h, l, c = mid
    iso_time = datetime.fromtimestamp(utm_ms / 1000, tz=timezone.utc).isoformat()
    key = (symbol, "HOUR")
    with _lock:
        buf = _buffers.setdefault(key, [])
        if buf and buf[-1].get("_forming"):
            buf[-1].update({"open": buf[-1]["open"], "high": max(buf[-1]["high"], h),
                            "low": min(buf[-1]["low"], l), "close": c, "time": iso_time,
                            "_forming": not cons_end})
        else:
            buf.append({"open": o, "high": h, "low": l, "close": c, "time": iso_time,
                        "_forming": not cons_end})
        if cons_end and buf and buf[-1].get("_forming") is False:
            del buf[-1]["_forming"]
        _buffers[key] = buf[-MAX_BUFFER:]


def _reset_partial_15min(symbol: str, reason: str) -> None:
    """Aggregator integrity rule: a 15MIN candle must never be built from
    fewer than 3 constituent 5MIN bars. Any in-flight partial bucket is
    discarded outright (never emitted) rather than padded or guessed."""
    existing = _partial_15min.pop(symbol, None)
    if existing and existing.get("count", 0) > 0:
        print(f"[candle_stream] discarding incomplete 15MIN bucket for {symbol} "
              f"({existing['count']}/3 bars, reason={reason})")


def _feed_15min_aggregator(symbol: str, utm_ms: int, mid: tuple, cons_end: bool) -> None:
    if not cons_end:
        return  # only fold in fully-closed 5MIN bars
    bucket_start_ms = (utm_ms // 900_000) * 900_000

    with _lock:
        partial = _partial_15min.get(symbol)
        if partial is None or partial["bucket_start_ms"] != bucket_start_ms:
            if partial is not None and partial["count"] < 3:
                print(f"[candle_stream] discarding incomplete 15MIN bucket for {symbol} "
                      f"({partial['count']}/3 bars, reason=new bucket started)")
            partial = {"bucket_start_ms": bucket_start_ms, "bars": [], "count": 0}
            _partial_15min[symbol] = partial

        partial["bars"].append(mid)
        partial["count"] += 1

        if partial["count"] == 3:
            opens = partial["bars"][0][0]
            closes = partial["bars"][-1][3]
            highs = max(b[1] for b in partial["bars"])
            lows = min(b[2] for b in partial["bars"])
            iso_time = datetime.fromtimestamp(bucket_start_ms / 1000, tz=timezone.utc).isoformat()
            key = (symbol, "15MIN")
            buf = _buffers.setdefault(key, [])
            buf.append({"open": opens, "high": highs, "low": lows, "close": closes, "time": iso_time})
            _buffers[key] = buf[-MAX_BUFFER:]
            del _partial_15min[symbol]


def _on_update(item_name: str, values: dict) -> None:
    # Heartbeat on EVERY update (including in-progress ticks, not just
    # candle closes) — an HOUR-scale item only closes every 60min, so
    # gating heartbeat on CONS_END would let it drift stale under normal
    # operation and false-trip the watchdog's 20min bar.
    try:
        upsert_heartbeat("candle_stream", f"last update {item_name}")
    except Exception as e:
        print(f"[candle_stream] heartbeat upsert failed: {e}")

    epic = _epic_for_item(item_name)
    scale = item_name.split(":")[-1] if epic else None
    symbol = _symbol_for_epic(epic) if epic else None
    if not symbol or not scale:
        return

    mid = _mid_ohlc(symbol, values)
    if mid is None:
        return
    utm = values.get("UTM")
    if not utm:
        return
    try:
        utm_ms = int(utm)
    except (TypeError, ValueError):
        return
    cons_end = values.get("CONS_END") == "1"

    if scale == "HOUR":
        _update_hour_buffer(symbol, utm_ms, mid, cons_end)
    elif scale == "5MINUTE":
        _feed_15min_aggregator(symbol, utm_ms, mid, cons_end)


class _UpdateListener:
    def onItemUpdate(self, update) -> None:
        try:
            values = {f: update.getValue(f) for f in CHART_FIELDS}
            _on_update(update.getItemName(), values)
        except Exception as e:
            print(f"[candle_stream] onItemUpdate error: {e}")

    def onSubscription(self) -> None:
        print("[candle_stream] subscription confirmed")

    def onSubscriptionError(self, code, message) -> None:
        print(f"[candle_stream] subscription error {code}: {message}")

    def onUnsubscription(self) -> None:
        print("[candle_stream] unsubscribed")

    def onItemLostUpdates(self, item_name, lost) -> None:
        print(f"[candle_stream] lost {lost} updates for {item_name}")

    def onClearSnapshot(self, item_name, item_pos) -> None:
        pass

    def onEndOfSnapshot(self, item_name, item_pos) -> None:
        pass

    def onCommandSecondLevelItemLostUpdates(self, lost, key) -> None:
        pass

    def onCommandSecondLevelSubscriptionError(self, code, message, key) -> None:
        pass

    def onListenEnd(self) -> None:
        pass

    def onListenStart(self) -> None:
        pass

    def onRealMaxFrequency(self, frequency) -> None:
        pass


class _ConnectionListener(ClientListener):
    def onStatusChange(self, status: str) -> None:
        print(f"[candle_stream] connection status: {status}")
        if status.startswith("CONNECTED"):
            _disconnected.clear()
        else:
            _disconnected.set()

    def onServerError(self, code, message) -> None:
        print(f"[candle_stream] server error {code}: {message}")
        _disconnected.set()

    def onListenEnd(self) -> None:
        pass

    def onListenStart(self) -> None:
        pass

    def onPropertyChange(self, prop) -> None:
        pass


# -------------------------
# Connection supervisor
# -------------------------
def _connect_and_subscribe(pairs: list) -> tuple:
    username, password, api_key, acc_type = get_ig_credentials()
    ig_service = IGService(username, password, api_key, acc_type=acc_type,
                           return_dataframe=False)

    # IGStreamService.create_session() below calls ig_service.create_session()
    # internally but discards the response dict, so timezoneOffset would be
    # unreachable afterward — call it here first to capture it (this makes
    # IGStreamService.create_session() log in a second time; harmless at
    # reconnect frequency — 5-300s backoff, not a hot path — and each login
    # simply supersedes the last). Every reconnect refreshes the offset,
    # not just the initial connect, in case it's ever wrong or unset.
    global _ACCOUNT_TZ_OFFSET_HOURS
    try:
        _session_resp = ig_service.create_session()
        _ACCOUNT_TZ_OFFSET_HOURS = _session_resp.get("timezoneOffset", _ACCOUNT_TZ_OFFSET_HOURS)
    except Exception as e:
        print(f"[candle_stream] could not capture account timezoneOffset: {e}")

    stream_service = IGStreamService(ig_service)
    stream_service.create_session()  # raises or sys.exit(1) on failure — caller catches both
    stream_service.add_client_listener(_ConnectionListener())

    try:
        ig_scale.init_price_scales(ig_service, EPIC_MAP, force=False)
    except Exception as e:
        print(f"[candle_stream] init_price_scales failed: {e}")

    epics_needing = {EPIC_MAP[symbol] for symbol, _ in pairs if symbol in EPIC_MAP}
    scales_needed = {_LS_SCALE_FOR_TIMEFRAME[tf] for _, tf in pairs}

    listener = _UpdateListener()
    for scale in scales_needed:
        items = [f"CHART:{epic}:{scale}" for epic in epics_needing]
        sub = Subscription(mode="MERGE", items=items, fields=CHART_FIELDS)
        sub.addListener(listener)
        stream_service.subscribe(sub)
        print(f"[candle_stream] subscribed {scale}: {items}")

    return ig_service, stream_service


def _reconnect_supervisor() -> None:
    backoff_idx = 0
    while True:
        try:
            pairs = _needed_pairs()
            if not pairs:
                print("[candle_stream] no candle-consuming active strategies found — retrying in 60s")
                time.sleep(60)
                continue

            # Aggregator integrity: never resume with stale in-flight bucket
            # state from before the disconnect.
            with _lock:
                for symbol in list(_partial_15min.keys()):
                    _reset_partial_15min(symbol, "reconnect")

            ig_service, stream_service = _connect_and_subscribe(pairs)
            _disconnected.clear()
            backoff_idx = 0
            print("[candle_stream] connected")

            backfill_fallback = False
            for symbol, timeframe in pairs:
                if _backfill_gap(ig_service, symbol, timeframe):
                    backfill_fallback = True
            if backfill_fallback and _should_alert_fallback("backfill"):
                send_telegram(
                    "candle_stream: IG historical-data quota exceeded -- gap "
                    "backfill fell back to yfinance for one or more pairs", level="WARN")

            # Block here until the connection listener flags a disconnect.
            _disconnected.wait()
            print("[candle_stream] disconnected — will reconnect")
            try:
                stream_service.disconnect()
            except Exception:
                pass

        except (Exception, SystemExit) as e:
            # SystemExit does not subclass Exception -- IGStreamService.create_session()
            # calls sys.exit(1) on connect failure rather than raising, so it must be
            # caught explicitly here or it silently kills this daemon thread.
            print(f"[candle_stream] connection error: {e}")

        delay = _BACKOFF_STEPS[min(backoff_idx, len(_BACKOFF_STEPS) - 1)]
        backoff_idx += 1
        print(f"[candle_stream] reconnecting in {delay}s")
        time.sleep(delay)


def start_candle_stream() -> None:
    """Entry point — mirrors start_poller()/start_signal_loop()'s pattern.
    Always starts regardless of CANDLE_SOURCE (parallel validation needs
    the stream running even while yfinance still drives real trades)."""
    def _run():
        pairs = _needed_pairs()
        if pairs:
            username, password, api_key, acc_type = get_ig_credentials()
            warmup_service = IGService(username, password, api_key, acc_type=acc_type,
                                       return_dataframe=False)
            try:
                global _ACCOUNT_TZ_OFFSET_HOURS
                _session_resp = warmup_service.create_session()
                _ACCOUNT_TZ_OFFSET_HOURS = _session_resp.get("timezoneOffset", _ACCOUNT_TZ_OFFSET_HOURS)
                ig_scale.init_price_scales(warmup_service, EPIC_MAP, force=False)
                _warm_up(warmup_service, pairs)
            except (Exception, SystemExit) as e:
                print(f"[candle_stream] initial warm-up failed, stream will backfill on connect: {e}")
        _reconnect_supervisor()

    threading.Thread(target=_run, daemon=True, name="candle_stream").start()
    print("[candle_stream] thread started")
