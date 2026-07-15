from trading_ig import IGService
from dotenv import load_dotenv
import os
import time
from datetime import datetime, timezone

from risk_manager import calculate_position_size, get_risk_per_trade
from database.models import log_trade, log_paper_trade
from ig_env import get_ig_credentials
import ig_scale

# -------------------------
# Load credentials
# -------------------------
load_dotenv()
username, password, api_key, IG_ACC_TYPE = get_ig_credentials()

# -------------------------
# Initialize IG
# -------------------------
ig_service = IGService(username, password, api_key, acc_type=IG_ACC_TYPE)

# -------------------------
# Asset configuration
# -------------------------
EPIC_CONFIG = {
    "US500":  {"epic": "IX.D.SPTRD.IFMM.IP",    "value_per_point": 1},
    "US100":  {"epic": "IX.D.NASDAQ.IFMM.IP",    "value_per_point": 1},
    "BTC":    {"epic": "CS.D.BITCOIN.CFBMU.IP",  "value_per_point": 0.1},
    "DAX":    {"epic": "IX.D.DAX.IFMS.IP",       "value_per_point": 1},
    "EURUSD": {"epic": "CS.D.EURUSD.MINI.IP",    "value_per_point": 10000},
    "GBPUSD": {"epic": "CS.D.GBPUSD.MINI.IP",    "value_per_point": 10000},
    "USDCAD": {"epic": "CS.D.USDCAD.MINI.IP",    "value_per_point": 10000},
    "AUDUSD": {"epic": "CS.D.AUDUSD.MINI.IP",    "value_per_point": 10000},
}

# -------------------------
# Session Manager
# -------------------------
last_login_time = 0


def recreate_session():
    global ig_service, last_login_time

    print("🔥 Recreating IG session completely...")

    ig_service = IGService(username, password, api_key, acc_type=IG_ACC_TYPE)
    ig_service.create_session()

    try:
        accounts = ig_service.fetch_accounts()

        current_account = accounts.loc[
            accounts["preferred"] == True, "accountId"
        ].values[0]

        if IG_ACC_TYPE == "LIVE":
            if current_account != "TW75S":
                ig_service.switch_account("TW75S", True)
                print("Switched to TW75S")
            else:
                print("Already using TW75S")
        else:
            print(f"[DEMO] Session landed on account {current_account}")

    except Exception as e:
        print("Account switch failed:", e)

    try:
        ig_scale.init_price_scales(
            ig_service,
            {s: c["epic"] for s, c in EPIC_CONFIG.items()},
            force=True,
        )
    except Exception as e:
        print(f"[ig_scale] init failed: {e}")

    last_login_time = time.time()


def ensure_session():
    global last_login_time

    try:
        # Refresh every 10 mins
        if time.time() - last_login_time > 600:
            print("Refreshing session proactively...")
            recreate_session()
        else:
            ig_service.fetch_accounts()

    except Exception as e:
        print("Session invalid:", e)
        recreate_session()


# Initialize session at start
recreate_session()

# Minimum SL distance from IG live entry price.
# yfinance candle close can lag the IG quote by several pips, making a
# valid signal SL appear dangerously close at execution time.
_MIN_SL_DIST: dict[str, float] = {
    "EURUSD": 0.00050,
    "GBPUSD": 0.00060,
    "USDCAD": 0.00050,
    "AUDUSD": 0.00050,
    "US500":  3.0,
    "US100":  4.0,
    "DAX":    5.0,
}

_SYMBOL_DECIMALS: dict[str, int] = {
    "EURUSD": 5, "GBPUSD": 5, "USDCAD": 5, "AUDUSD": 5,
    "US500": 2, "US100": 2, "DAX": 2,
}

# 1 pip per symbol — used only to gate [SL DRIFT] log/Telegram noise on the
# always-reanchor path (sub-pip corrections aren't worth alerting on).
_PIP_SIZE: dict[str, float] = {
    "EURUSD": 0.0001, "GBPUSD": 0.0001, "USDCAD": 0.0001, "AUDUSD": 0.0001,
    "US500": 1.0, "US100": 1.0, "DAX": 1.0,
}

# IG API rejection reason codes indicating a capacity/margin constraint.
# Shadow-log these: the signal was valid but the broker had no room.
# Other codes (e.g. ATTACHED_ORDER_LEVEL_ERROR) are bad-order errors —
# not missed trades — and are NOT shadow-logged.
_MARGIN_REASONS: frozenset = frozenset({
    "INSUFFICIENT_FUNDS",
    "MARGIN_LIMITED",
    "MARGIN_EXCEEDS_LIMIT",
    "EXCEEDED_ACCOUNT_LIMIT",
    "MARGIN_EXCEEDED",
    "CR_MARGIN",
    "EXCEEDS_RISK_LIMIT",
})

# -------------------------
# Global state
# -------------------------
last_signal = None
last_trade_time = {}  # keyed by symbol


# -------------------------
# Utils
# -------------------------
def parse_float(value):
    try:
        if value == "null":
            return None
        return float(value)
    except:
        return None


# -------------------------
# Main webhook handler
# -------------------------
def place_trade_from_alert(data):
    global last_signal, last_trade_time

    print("\n===================================")
    print("FULL WEBHOOK DATA:", data)

    try:
        symbol = data.get("symbol")

        if not symbol:
            print("Missing symbol — skipping")
            return False

        config = EPIC_CONFIG.get(symbol)

        if not config:
            print("Unsupported symbol:", symbol)
            return False

        strategy_name = "swiftalgo"

        buy_signal = data.get("buy_signal")
        sell_signal = data.get("sell_signal")
        trend = parse_float(data.get("trend"))

        print("Buy Signal:", buy_signal)
        print("Sell Signal:", sell_signal)
        print("Trend:", trend)

        if buy_signal not in ["0", "1"] or sell_signal not in ["0", "1"]:
            print("Invalid signal format — skipping")
            return False

        if buy_signal == "1" and sell_signal == "1":
            print("Conflict signal — skipping")
            return False

        # Cooldown
        current_time = time.time()
        if current_time - last_trade_time.get(symbol, 0) < 1:
            print(f"[cooldown] {symbol} — skipping, within 1s cooldown")
            return False

        # Determine action
        if buy_signal == "1":
            action = "buy"
            sl = parse_float(data.get("long_sl"))
            tp = parse_float(data.get("long_tp"))

        elif sell_signal == "1":
            action = "sell"
            sl = parse_float(data.get("short_sl"))
            tp = parse_float(data.get("short_tp"))

        else:
            print("No valid signal — skipping")
            return False

        print("Detected Action:", action)
        print("Parsed SL:", sl)
        print("Parsed TP:", tp)

        if sl is None or tp is None:
            print("Missing SL/TP — skipping trade")
            return False

        if trend is None:
            print("Missing trend — skipping trade")
            return False

        # Counter-trend filter
        if action == "buy" and trend == 3:
            print("Blocked BUY — Downtrend detected")
            return False

        if action == "sell" and trend == 1:
            print("Blocked SELL — Uptrend detected")
            return False

        print("Trend filter passed")

        result = place_trade(symbol, action, sl, tp, strategy_name=strategy_name,
                             source="tradingview_webhook")

        if result:
            last_signal = f"{symbol}_{action}"
            last_trade_time[symbol] = current_time

        return result

    except Exception as e:
        print("Error in place_trade_from_alert:", e)
        return False


# -------------------------
# Trade execution
# -------------------------
def place_trade(symbol, action, sl=None, tp=None, strategy_name="tradingview_webhook", source="tradingview_webhook", yf_entry=None, timeframe=None):
    print("===================================")
    print(f"Executing Trade: {symbol} | Action: {action} | SL: {sl} | TP: {tp}")

    config = EPIC_CONFIG.get(symbol)
    epic = config["epic"]
    value_per_point = config["value_per_point"]

    direction = "BUY" if action.lower() == "buy" else "SELL"

    if symbol in ig_scale.CHECKED_SYMBOLS and not ig_scale.is_resolved(symbol):
        print(f"[ig_scale] {symbol} price scale unresolved — refusing trade")
        from bot.notifier import send_telegram
        send_telegram(f"REFUSED {symbol} {direction} — price scale unresolved, "
                      f"trading blocked until resolved", level="ERROR")
        return False

    try:
        ensure_session()

        market = ig_service.fetch_market_by_epic(epic)
        bid = market["snapshot"]["bid"]
        offer = market["snapshot"]["offer"]
        entry_price = ig_scale.to_decimal(symbol, offer if direction == "BUY" else bid)

        print(f"Entry Price: {entry_price}")

        # yfinance candle close (yf_entry, signal-loop trades) always lags the
        # live IG quote by some amount — sub-floor drift used to pass through
        # uncorrected and silently degrade RR (e.g. trade 517: 1.44 vs
        # intended 2.0). Signal-loop trades now always reanchor sl/tp to the
        # live entry price, preserving the intended RR computed from
        # yf_entry/sl/tp. The floor remains a secondary guard on the
        # reanchored distance. Webhook trades (yf_entry=None) are unaffected —
        # swiftalgo sets its own sl/tp by design and keeps the old
        # floor-breach-only fallback.
        _min_dist = _MIN_SL_DIST.get(symbol)
        _pip = _PIP_SIZE.get(symbol, _min_dist or 0.0001)
        _log_threshold = 0.5 * _pip
        _prec = _SYMBOL_DECIMALS.get(symbol, 5)

        if yf_entry is not None and abs(yf_entry - sl) > 0:
            _orig_sl_dist = abs(yf_entry - sl)
            _orig_tp_dist = abs(tp - yf_entry)
            _rr = _orig_tp_dist / _orig_sl_dist
            _intended_sl_dist = max(_orig_sl_dist, _min_dist) if _min_dist is not None else _orig_sl_dist
            if direction == "BUY":
                sl = round(entry_price - _intended_sl_dist, _prec)
                tp = round(entry_price + _rr * _intended_sl_dist, _prec)
            else:
                sl = round(entry_price + _intended_sl_dist, _prec)
                tp = round(entry_price - _rr * _intended_sl_dist, _prec)
            _adjustment = abs(entry_price - yf_entry)
            if _adjustment > _log_threshold:
                print(
                    f"[SL DRIFT] {symbol} reanchored to live price "
                    f"(adj={_adjustment:.5f}). yf_entry={yf_entry} rr={_rr:.2f} "
                    f"new_sl={sl} new_tp={tp}"
                )
                from bot.notifier import send_telegram
                send_telegram(
                    f"SL DRIFT {symbol} — reanchored to live price (adj={_adjustment:.5f})",
                    level="WARN",
                )
        elif _min_dist is not None and abs(entry_price - sl) < _min_dist:
            _orig_sl_dist = abs(tp - sl) / 3  # fallback: assume 2:1
            _rr = 2.0
            _intended_sl_dist = max(_orig_sl_dist, _min_dist)
            if direction == "BUY":
                sl = round(entry_price - _intended_sl_dist, _prec)
                tp = round(entry_price + _rr * _intended_sl_dist, _prec)
            else:
                sl = round(entry_price + _intended_sl_dist, _prec)
                tp = round(entry_price - _rr * _intended_sl_dist, _prec)
            print(
                f"[SL DRIFT] {symbol} sl_dist was below min={_min_dist:.5f} — "
                f"reanchored to live price. rr={_rr:.2f} "
                f"new_sl={sl} new_tp={tp}"
            )
            from bot.notifier import send_telegram
            send_telegram(f"SL DRIFT {symbol} — reanchored to live price", level="WARN")

        size = calculate_position_size(entry_price, sl, value_per_point, symbol=symbol)

        if size is None:
            print("Position sizing failed — aborting")
            return False

        # Guard against IG's real minDealSize being above our calculated size —
        # this is a distinct floor from risk_manager's own hardcoded MIN_LOT_SIZE
        # (0.1), which can be BELOW what IG actually requires per instrument
        # (e.g. US100 minDealSize=0.2) and is exactly what produced the
        # MINIMUM_ORDER_SIZE_ERROR rejections: the bot clamped to its own
        # 0.1 floor, which IG then rejected as too small.
        _ig_min_deal_size = (
            market.get("dealingRules", {}).get("minDealSize", {}).get("value")
        )
        intended_risk = get_risk_per_trade(symbol)
        if _ig_min_deal_size is not None and size < _ig_min_deal_size:
            implied_risk = _ig_min_deal_size * abs(entry_price - sl) * value_per_point
            if implied_risk > 1.3 * intended_risk:
                print(
                    f"[MIN DEAL SIZE] {symbol} calculated size {size} is below IG's "
                    f"minDealSize={_ig_min_deal_size} — clamping would imply risk "
                    f"${implied_risk:.2f} vs ${intended_risk:.2f} intended (>1.3x) — skipping"
                )
                try:
                    _now = datetime.now(timezone.utc)
                    _h   = _now.hour
                    _session = (
                        "LONDON"    if 7  <= _h < 12 else
                        "NY_OPEN"   if 13 <= _h < 15 else
                        "NY_MID"    if 15 <= _h < 18 else
                        "OFF_HOURS"
                    )
                    log_paper_trade({
                        "checked_at":    _now.isoformat(),
                        "symbol":        symbol,
                        "strategy_name": strategy_name,
                        "timeframe":     timeframe,
                        "candle_time":   _now.isoformat(),
                        "signal":        f"SHADOW_{direction}",
                        "entry_price":   entry_price,
                        "sl":            sl,
                        "tp":            tp,
                        "outcome":       "PENDING",
                        "params_json":   "{}",
                        "session":       _session,
                        "notes":         (
                            f"SHADOW: skipped — min deal size would oversize risk to "
                            f"${implied_risk:.2f} vs ${intended_risk:.2f} intended"
                        ),
                    })
                    print(f"[MIN DEAL SIZE] {symbol} {direction} shadow-logged")
                except Exception as _shadow_err:
                    print(f"[MIN DEAL SIZE] shadow log failed: {_shadow_err}")
                from bot.notifier import send_telegram
                send_telegram(
                    f"MIN DEAL SIZE SKIP {symbol} {direction} — clamped risk "
                    f"${implied_risk:.2f} vs ${intended_risk:.2f} intended (>1.3x)",
                    level="WARN",
                )
                return False
            else:
                print(
                    f"[MIN DEAL SIZE] {symbol} size clamped {size} -> {_ig_min_deal_size} "
                    f"(IG minDealSize), implied risk ${implied_risk:.2f} vs "
                    f"${intended_risk:.2f} intended (within 1.3x) — proceeding"
                )
                size = _ig_min_deal_size

        expected_risk = size * abs(entry_price - sl) * value_per_point
        print(f"[TEST] Expected risk: ${expected_risk:.2f}")

        response = ig_service.create_open_position(
            currency_code="USD",
            direction=direction,
            epic=epic,
            expiry="-",
            force_open=True,
            guaranteed_stop=False,
            order_type="MARKET",
            size=size,
            level=None,
            limit_level=ig_scale.to_native(symbol, tp),
            stop_level=ig_scale.to_native(symbol, sl),
            limit_distance=None,
            stop_distance=None,
            trailing_stop=False,
            trailing_stop_increment=None,
            quote_id=None
        )

        print("IG Response:", response)

        if not response:
            return False

        if response.get("dealStatus") == "REJECTED":
            reason = response.get("reason", "UNKNOWN")
            print(f"Trade rejected: {reason}")
            from bot.notifier import send_telegram
            send_telegram(f"REJECTED {symbol} {direction} — {reason}", level="ERROR")
            if reason in _MARGIN_REASONS:
                try:
                    _now = datetime.now(timezone.utc)
                    _h   = _now.hour
                    _session = (
                        "LONDON"    if 7  <= _h < 12 else
                        "NY_OPEN"   if 13 <= _h < 15 else
                        "NY_MID"    if 15 <= _h < 18 else
                        "OFF_HOURS"
                    )
                    log_paper_trade({
                        "checked_at":    _now.isoformat(),
                        "symbol":        symbol,
                        "strategy_name": strategy_name,
                        "timeframe":     timeframe,
                        "candle_time":   _now.isoformat(),
                        "signal":        f"SHADOW_{direction}",
                        "entry_price":   entry_price,
                        "sl":            sl,
                        "tp":            tp,
                        "outcome":       "PENDING",
                        "params_json":   "{}",
                        "session":       _session,
                        "notes":         f"SHADOW: blocked by insufficient margin ({reason})",
                    })
                    print(f"[MARGIN BLOCK] {symbol} {direction} shadow-logged (reason={reason})")
                except Exception as _shadow_err:
                    print(f"[MARGIN BLOCK] shadow log failed: {_shadow_err}")
            return False

        if response.get("status") == "OPEN":
            print("Trade SUCCESSFULLY placed")
            from bot.notifier import send_telegram
            send_telegram(
                f"OPENED {strategy_name} {symbol} {direction} @ {entry_price} "
                f"SL {sl} TP {tp} (${expected_risk:.2f} risk)", level="INFO")
            try:
                log_trade({
                    "symbol": symbol,
                    "direction": direction,
                    "size": size,
                    "entry_price": entry_price,
                    "sl": sl,
                    "tp": tp,
                    "deal_id": response.get("dealId"),
                    "deal_reference": response.get("dealReference"),
                    "source": source,
                    "strategy_name": strategy_name,
                    "status": "OPEN",
                })
                print("Trade logged to database")
            except Exception as log_error:
                print("WARNING: Failed to log trade to database:", log_error)
            return response

        return response

    except Exception as e:
        print("Trade failed:", e)

        error_msg = str(e).lower()

        if "401" in error_msg or "client-token-invalid" in error_msg:
            print("⚠️ Session expired — FULL RESET and retry")

            try:
                recreate_session()

                return place_trade(symbol, action, sl, tp,
                                   strategy_name=strategy_name,
                                   source=source)

            except Exception as retry_error:
                print("Retry failed:", retry_error)

        return False