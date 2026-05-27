import logging

import requests

logger = logging.getLogger(__name__)

VIX_BLOCK_THRESHOLD   = 22.0
VIX_CAUTION_THRESHOLD = 18.0


def get_current_vix() -> float | None:
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX"
        r = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        data = r.json()
        vix = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        logger.info(f"[VIX] Current level: {float(vix):.2f}")
        return float(vix)
    except Exception as e:
        logger.warning(f"[VIX] Fetch failed: {e} — defaulting to allow")
        return None


def should_block_swing_entry() -> bool:
    """
    True = skip live swing entry. False = allow.
    Fails OPEN — API error never blocks trading.
    Only call for swing strategies.
    """
    try:
        vix = get_current_vix()
        if vix is None:
            return False
        if vix >= VIX_BLOCK_THRESHOLD:
            logger.warning(
                f"[VIX] {vix:.2f} >= {VIX_BLOCK_THRESHOLD} — blocking swing entry"
            )
            return True
        if vix >= VIX_CAUTION_THRESHOLD:
            logger.info(
                f"[VIX] {vix:.2f} >= {VIX_CAUTION_THRESHOLD} — caution, blocking entry"
            )
            return True
        return False
    except Exception as e:
        logger.warning(f"[VIX] Unexpected error: {e} — allowing entry")
        return False
