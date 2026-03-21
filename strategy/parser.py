def parse_signal(data):
    symbol = data.get("symbol")
    signal = data.get("signal")
    price = data.get("price")

    return symbol, signal, price