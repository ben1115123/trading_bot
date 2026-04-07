from trading_ig import IGService
from dotenv import load_dotenv
import os
import time

from risk_manager import calculate_position_size

# -------------------------
# Load credentials
# -------------------------
load_dotenv()
username = os.getenv("IG_USERNAME")
password = os.getenv("IG_PASSWORD")
api_key = os.getenv("IG_API_KEY")

# -------------------------
# Initialize IG
# -------------------------
ig_service = IGService(username, password, api_key, acc_type="LIVE")

# -------------------------
# Session Manager
# -------------------------
last_login_time = 0


def recreate_session():
    global ig_service, last_login_time

    print("🔥 Recreating IG session completely...")

    ig_service = IGService(username, password, api_key, acc_type="LIVE")
    ig_service.create_session()

    try:
        accounts = ig_service.fetch_accounts()

        current_account = accounts.loc[
            accounts["preferred"] == True, "accountId"
        ].values[0]

        if current_account != "TW75S":
            ig_service.switch_account("TW75S", True)
            print("Switched to TW75S")
        else:
            print("Already using TW75S")

    except Exception as e:
        print("Account switch failed:", e)

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

# -------------------------
# Asset configuration
# -------------------------
EPIC_CONFIG = {
    "US500": {"epic": "IX.D.SPTRD.IFMM.IP", "value_per_point": 1},
    "US100": {"epic": "IX.D.NASDAQ.IFMM.IP", "value_per_point": 1},
    "BTC": {"epic": "CS.D.BITCOIN.CFBMU.IP", "value_per_point": 0.1}
}

# -------------------------
# Global state
# -------------------------
last_signal = None
last_trade_time = 0


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
        if current_time - last_trade_time < 10:
            print("Cooldown active — skipping trade")
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

        # Trend filter
        if action == "buy" and trend == 3:
            print("Blocked BUY — Downtrend detected")
            return False

        if action == "sell" and trend == 1:
            print("Blocked SELL — Uptrend detected")
            return False

        print("Trend filter passed")

        result = place_trade(symbol, action, sl, tp)

        if result:
            last_signal = f"{symbol}_{action}"
            last_trade_time = current_time

        return result

    except Exception as e:
        print("Error in place_trade_from_alert:", e)
        return False


# -------------------------
# Trade execution
# -------------------------
def place_trade(symbol, action, sl=None, tp=None):
    print("===================================")
    print(f"Executing Trade: {symbol} | Action: {action} | SL: {sl} | TP: {tp}")

    config = EPIC_CONFIG.get(symbol)
    epic = config["epic"]
    value_per_point = config["value_per_point"]

    direction = "BUY" if action.lower() == "buy" else "SELL"

    try:
        ensure_session()

        market = ig_service.fetch_market_by_epic(epic)
        bid = market["snapshot"]["bid"]
        offer = market["snapshot"]["offer"]
        entry_price = offer if direction == "BUY" else bid

        print(f"Entry Price: {entry_price}")

        size = calculate_position_size(entry_price, sl, value_per_point)

        if size is None:
            print("Position sizing failed — aborting")
            return False

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
            limit_level=tp,
            stop_level=sl,
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
            print("Trade rejected:", response.get("reason"))
            return False

        if response.get("status") == "OPEN":
            print("Trade SUCCESSFULLY placed")
            return response

        return response

    except Exception as e:
        print("Trade failed:", e)

        error_msg = str(e).lower()

        if "401" in error_msg or "client-token-invalid" in error_msg:
            print("⚠️ Session expired — FULL RESET and retry")

            try:
                recreate_session()

                return place_trade(symbol, action, sl, tp)

            except Exception as retry_error:
                print("Retry failed:", retry_error)

        return False