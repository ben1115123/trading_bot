import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

_LEVEL_PREFIX = {"INFO": "🟢", "WARN": "🟡", "ERROR": "🔴"}

_RATE_LIMIT      = 20    # max messages per rolling window
_WINDOW_SECONDS  = 60.0
_HTTP_TIMEOUT    = 5

_lock = threading.Lock()
_send_times: list[float] = []
_dropped_count = 0


def send_telegram(message: str, level: str = "INFO") -> bool:
    """POST a message to Telegram. Never raises — always returns bool.
    Rate-limited to _RATE_LIMIT messages per _WINDOW_SECONDS; drops beyond
    that are counted and the count is appended to the next message sent.
    """
    global _dropped_count
    try:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            print(f"[notifier] TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set — dropping: {message}")
            return False

        with _lock:
            now = time.time()
            while _send_times and now - _send_times[0] > _WINDOW_SECONDS:
                _send_times.pop(0)

            if len(_send_times) >= _RATE_LIMIT:
                _dropped_count += 1
                print(f"[notifier] rate limit hit ({_RATE_LIMIT}/{_WINDOW_SECONDS:.0f}s) "
                      f"— dropped (total dropped={_dropped_count}): {message}")
                return False

            prefix = _LEVEL_PREFIX.get(level.upper(), "")
            text = f"{prefix} {message}".strip()
            if _dropped_count > 0:
                text += f"\n...+{_dropped_count} alerts dropped"

        data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data)
        resp = json.loads(urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT).read())

        if not resp.get("ok"):
            print(f"[notifier] Telegram API returned not-ok: {resp}")
            return False

        with _lock:
            _send_times.append(now)
            _dropped_count = 0
        return True

    except Exception as e:
        print(f"[notifier] send_telegram failed: {e}")
        return False
