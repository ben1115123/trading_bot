from abc import ABC, abstractmethod


class Strategy(ABC):
    name: str = "base"

    def __init__(self, params: dict = None):
        self.params = params or {}

    @abstractmethod
    def generate_signals(self, candles: list) -> list:
        """
        Args:
            candles: list of dicts with keys: time, open, high, low, close
        Returns:
            list of dicts: { 'index': int, 'signal': 'BUY'|'SELL'|'NONE' }
            One entry per candle, same length as input.
        """
        pass
