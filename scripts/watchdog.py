#!/usr/bin/env python3
"""Host-level watchdog for the trading bot.

Runs via HOST cron (NOT inside the container) so it can detect and alert
even if the bot container itself has died. Deliberately stdlib-only --
no dependency on the project's Python environment being installed on
the host, and no import of bot.notifier (that reads TELEGRAM_* from
os.environ, which the host cron job's environment does not have; here
we parse .env directly instead).
"""
import json
import subprocess
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_DIR   = Path("/home/ubuntu/trading_bot")
DB_PATH    = REPO_DIR / "database" / "trades.db"
ENV_PATH   = REPO_DIR / ".env"
STATE_PATH = Path("/tmp/watchdog_state.json")
ALERT_LOG_PATH = REPO_DIR / "logs" / "watchdog_alerts.jsonl"

STALE_MINUTES        = 20
REALERT_MINUTES       = 60
MARKET_OPEN_WEEKDAY   = 6   # Sunday
MARKET_OPEN_HOUR       = 22
MARKET_CLOSE_WEEKDAY   = 4  # Friday
MARKET_CLOSE_HOUR      = 21


def _load_env(path: Path) -> dict:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _send_telegram(env: dict, message: str) -> bool:
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat  = env.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[watchdog] TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID missing from .env")
        return False
    try:
        data = urllib.parse.urlencode({"chat_id": chat, "text": message}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data)
        resp = json.loads(urllib.request.urlopen(req, timeout=5).read())
        return bool(resp.get("ok"))
    except Exception as e:
        print(f"[watchdog] telegram send failed: {e}")
        return False


def _is_market_hours(now: datetime) -> bool:
    """Sun 22:00 UTC - Fri 21:00 UTC."""
    wd, h = now.weekday(), now.hour
    if wd == 5:  # Saturday
        return False
    if wd == MARKET_OPEN_WEEKDAY:  # Sunday
        return h >= MARKET_OPEN_HOUR
    if wd == MARKET_CLOSE_WEEKDAY:  # Friday
        return h < MARKET_CLOSE_HOUR
    return True  # Mon-Thu


def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            return {}
    return {}


def _save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state))


def _append_alert_log(condition: str, message: str, now: datetime) -> None:
    try:
        ALERT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(ALERT_LOG_PATH, "a") as f:
            f.write(json.dumps({
                "timestamp": now.isoformat(),
                "condition": condition,
                "message":   message,
            }) + "\n")
    except Exception as e:
        print(f"[watchdog] alert log append failed: {e}")


def _should_alert(state: dict, key: str, now: datetime) -> bool:
    last = state.get(key)
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
    except Exception:
        return True
    return (now - last_dt).total_seconds() >= REALERT_MINUTES * 60


def check_heartbeat(env: dict, state: dict, now: datetime, name: str, key: str) -> None:
    if not _is_market_hours(now):
        print("[watchdog] outside market hours — skipping heartbeat check")
        return
    if not DB_PATH.exists():
        print(f"[watchdog] DB not found at {DB_PATH}")
        return
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute("SELECT last_beat FROM heartbeat WHERE name = ?", (name,))
        row = cur.fetchone()
        conn.close()
    except Exception as e:
        print(f"[watchdog] heartbeat query failed: {e}")
        return

    if not row or not row[0]:
        print(f"[watchdog] no {name} heartbeat row yet")
        return

    try:
        last_beat = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
        if last_beat.tzinfo is None:
            last_beat = last_beat.replace(tzinfo=timezone.utc)
    except Exception as e:
        print(f"[watchdog] heartbeat parse failed: {e}")
        return

    age_min = (now - last_beat).total_seconds() / 60
    print(f"[watchdog] {name} last beat {age_min:.1f} min ago")

    if age_min > STALE_MINUTES:
        if _should_alert(state, key, now):
            msg = f"💀 {name.upper()} STALE — last heartbeat {age_min:.0f} min ago"
            if _send_telegram(env, msg):
                state[key] = now.isoformat()
                _append_alert_log(key, msg, now)
    else:
        state.pop(key, None)


def check_duplicate_process(env: dict, state: dict, now: datetime) -> None:
    """Flags any 'uvicorn main:app' process NOT owned by trading_bot-bot-1.

    Docker does not hide container processes from the host's process table
    (no PID namespace isolation by default) -- the container's own uvicorn
    always shows up in a plain host-level `pgrep`. So "0 on host" is not
    the right healthy baseline; the container's PID must be excluded via
    `docker top`, and only a uvicorn PID *outside* that set (e.g. a stale
    host-level systemd/nohup process, like the Apr-12 incident) is a real
    duplicate.
    """
    key = "duplicate_process"
    try:
        pgrep_result = subprocess.run(
            ["pgrep", "-f", "uvicorn main:app"],
            capture_output=True, text=True,
        )
        matched_pids = {p.strip() for p in pgrep_result.stdout.splitlines() if p.strip()}

        top_result = subprocess.run(
            ["docker", "top", "trading_bot-bot-1"],
            capture_output=True, text=True,
        )
        container_pids = set()
        if top_result.returncode == 0:
            lines = top_result.stdout.splitlines()
            if lines:
                header = lines[0].split()
                pid_idx = header.index("PID") if "PID" in header else 1
                for line in lines[1:]:
                    parts = line.split(None, pid_idx + 1)
                    if len(parts) > pid_idx:
                        container_pids.add(parts[pid_idx])
    except Exception as e:
        print(f"[watchdog] pgrep/docker top failed: {e}")
        return

    rogue_pids = matched_pids - container_pids
    print(f"[watchdog] uvicorn PIDs on host: {matched_pids or '{}'} "
          f"| container-owned: {container_pids or '{}'} | rogue: {rogue_pids or '{}'}")

    if rogue_pids:
        if _should_alert(state, key, now):
            msg = (f"🔴 DUPLICATE PROCESS DETECTED — 'uvicorn main:app' running on HOST "
                   f"outside Docker (PIDs {sorted(rogue_pids)}) — bot should live in Docker only")
            if _send_telegram(env, msg):
                state[key] = now.isoformat()
                _append_alert_log(key, msg, now)
    else:
        state.pop(key, None)


def check_container(env: dict, state: dict, now: datetime) -> None:
    key = "container_down"
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", "trading_bot-bot-1"],
            capture_output=True, text=True,
        )
        running = result.returncode == 0 and result.stdout.strip() == "true"
    except Exception as e:
        print(f"[watchdog] docker inspect failed: {e}")
        running = False
    print(f"[watchdog] bot container running: {running}")

    if not running:
        if _should_alert(state, key, now):
            msg = "💀 BOT CONTAINER DOWN — trading_bot-bot-1 is not running"
            if _send_telegram(env, msg):
                state[key] = now.isoformat()
                _append_alert_log(key, msg, now)
    else:
        state.pop(key, None)


def main():
    now = datetime.now(timezone.utc)
    env = _load_env(ENV_PATH)
    state = _load_state()

    check_heartbeat(env, state, now, "signal_loop", "stale_heartbeat")
    check_heartbeat(env, state, now, "candle_stream", "stale_candle_stream")
    check_duplicate_process(env, state, now)
    check_container(env, state, now)

    _save_state(state)
    print("[watchdog] check complete")


if __name__ == "__main__":
    main()
