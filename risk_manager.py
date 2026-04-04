# risk_manager.py

RISK_PER_TRADE = 15  # USD per trade
MIN_LOT_SIZE = 0.1
MAX_LOT_SIZE = 10

def calculate_position_size(entry_price, sl_price, value_per_point):
    """
    Calculate lot size based on entry price, stop loss, and value per point
    """
    try:
        sl_distance = abs(entry_price - sl_price)

        if sl_distance == 0:
            print("[Risk Manager] Invalid SL distance (0)")
            return None

        # Lot size formula
        size = RISK_PER_TRADE / (sl_distance * value_per_point)
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