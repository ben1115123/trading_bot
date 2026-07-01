# risk_manager.py

RISK_PER_TRADE = 3  # USD per trade default

RISK_PER_TRADE_OVERRIDE = {
    "US500": 3.0,    # reduced while rebuilding account from $100
    "EURUSD": 3.0,   # reduced while rebuilding account from $100
    "GBPUSD": 3.0,   # reduced while rebuilding account from $100
}


def get_risk_per_trade(symbol: str, is_paper: bool = False) -> float:
    if is_paper:
        return float(RISK_PER_TRADE)
    return RISK_PER_TRADE_OVERRIDE.get(symbol.upper(), float(RISK_PER_TRADE))


MIN_LOT_SIZE = 0.1
MAX_LOT_SIZE = 10

def calculate_position_size(entry_price, sl_price, value_per_point, symbol: str = "", is_paper: bool = False):
    """
    Calculate lot size based on entry price, stop loss, and value per point
    """
    try:
        sl_distance = abs(entry_price - sl_price)

        if sl_distance == 0:
            print("[Risk Manager] Invalid SL distance (0)")
            return None

        # Lot size formula
        size = get_risk_per_trade(symbol, is_paper=is_paper) / (sl_distance * value_per_point)
        size = round(size, 2)

        # Enforce minimum/maximum lot size
        if size < MIN_LOT_SIZE:
            print("[Risk Manager] Lot below minimum, using minimum")
            size = MIN_LOT_SIZE
        if size > MAX_LOT_SIZE:
            print("[Risk Manager] Lot above maximum, capping")
            size = MAX_LOT_SIZE

        print(f"[Risk Manager] Calculated lot size: {size}, SL Distance: {sl_distance}, Value/Point: {value_per_point}")
        return size

    except Exception as e:
        print("[Risk Manager] Error:", e)
        return None