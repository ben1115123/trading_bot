def trend_filter(signal, trend):
    if signal == "BUY" and trend == "bearish":
        return False
    return True