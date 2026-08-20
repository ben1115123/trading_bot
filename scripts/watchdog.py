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
from datetime import datetime, timedelta, timezone
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

# --- Candle-source divergence -------------------------------------------
# Per-(symbol, timeframe) p99 of abs(delta_pips), computed ONCE from all
# 21,051 candle_source_compare rows spanning 2026-07-08 -> 2026-08-20.
#
# BAKED AS A CONSTANT, DELIBERATELY -- a rolling p99 recomputed each run
# would absorb the very anomaly this check exists to flag. The 2026-07-21
# EURUSD event (delta_pips = -114,008,596) sat in this table unread for 28
# days (findings doc finding 27); a self-updating baseline would have
# quietly widened around it. Recompute these numbers only deliberately, and
# only after confirming the window contains no known-bad rows.
#
# CALIBRATION: at 5x p99, exactly ONE row in 21,051 fires -- that anomaly.
# 10x fires on the same single row (no noise saved, only a higher floor);
# 3x also fires once but leaves EURUSD only 1.26x above its worst real
# observation, too tight for a news day. 5x keeps >= 2.1x headroom on every
# key with zero historical false positives.
#
# ⚠️ US100's ~100-pip mean divergence on BOTH timeframes is off-session
# yfinance staleness -- the exact condition the 2026-07-15 ig_stream flip
# was made to fix -- NOT a stream fault. That is why this table is
# per-symbol: a single global threshold tuned to keep US100 quiet would sit
# above 400 pips and go completely blind to FX, where real divergence is
# 1-2 pips and the failure mode is a 4-order-of-magnitude scale error.
DIVERGENCE_P99 = {
    ("AUDUSD", "15MIN"):   9.22,
    ("EURUSD", "15MIN"):  12.94,
    ("GBPUSD", "15MIN"):   9.93,
    ("USDCAD", "15MIN"):   6.95,
    ("US100",  "15MIN"): 436.60,
    ("US100",  "HOUR"):  476.27,
    ("US500",  "15MIN"):  70.25,
    ("US500",  "HOUR"):   77.71,
}
DIVERGENCE_MULTIPLIER  = 5.0
DIVERGENCE_WINDOW_MIN  = 60

# Symbols with NO baseline and no possibility of one: they have never logged a
# single candle_source_compare row in 21,051. DAX is in candle_stream.EPIC_MAP
# but no active strategy checks it, so the signal loop never runs a comparison
# for it; BTC is not in EPIC_MAP at all (no IG epic, paper only). Listed
# EXPLICITLY rather than left absent so that adding a symbol to the stream
# forces a decision here -- a test fails if a symbol is in neither set. If
# either ever starts logging, it lands in the UNCHECKED branch and says so,
# which is the correct outcome: a baseline must be measured, never guessed.
DIVERGENCE_NO_BASELINE = frozenset({"DAX", "BTC"})


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


def check_candle_divergence(env: dict, state: dict, now: datetime) -> None:
    """Alerts when yfinance-vs-stream disagreement exceeds this symbol's own
    historical ceiling -- i.e. one of the two candle sources has gone wrong.

    This gives candle_source_compare a READER. The table has recorded every
    comparison since 2026-07-08 and nothing ever consumed it: the 2026-07-21
    scale anomaly was written to it in real time (delta_pips = -114,008,596)
    and sat unread for 28 days until it was found by hand. The band check
    (ig_scale.in_expected_band) now catches that class at ingest, but only for
    values outside a plausible band; this catches the complementary case --
    both sources individually plausible, disagreeing with each other -- and
    it catches a stalled/frozen source, which no band can see.

    Deliberately a threshold rather than a dashboard panel: a panel is
    something a human must choose to open, which is precisely how this table
    went unread. The watchdog already runs every 10 minutes and already has
    the alert path.

    Missing baseline -> UNCHECKED, reported, never silently passed. Same
    tri-state discipline as ig_scale.in_expected_band: a (symbol, timeframe)
    absent from DIVERGENCE_P99 is a build-time omission (adding a symbol to
    one list and not the other is Bug 2's exact shape), so it must be noisy,
    not treated as healthy.
    """
    if not DB_PATH.exists():
        print(f"[watchdog] DB not found at {DB_PATH}")
        return

    since = (now - timedelta(minutes=DIVERGENCE_WINDOW_MIN)).isoformat()
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute("""
            SELECT symbol, timeframe, MAX(ABS(delta_pips)) AS worst
            FROM candle_source_compare
            WHERE checked_at >= ? AND delta_pips IS NOT NULL
            GROUP BY symbol, timeframe
        """, (since,))
        rows = cur.fetchall()
        conn.close()
    except Exception as e:
        print(f"[watchdog] candle divergence query failed: {e}")
        return

    if not rows:
        print(f"[watchdog] no candle comparisons in last {DIVERGENCE_WINDOW_MIN}min")
        return

    for symbol, timeframe, worst in rows:
        p99 = DIVERGENCE_P99.get((symbol, timeframe))
        if p99 is None:
            key = f"divergence_unchecked:{symbol}:{timeframe}"
            print(f"[watchdog] {symbol} {timeframe} has no divergence baseline — "
                  f"UNCHECKED (add it to DIVERGENCE_P99)")
            if _should_alert(state, key, now):
                msg = (f"🟡 CANDLE DIVERGENCE UNCHECKED — {symbol} {timeframe} has no "
                       f"baseline in watchdog DIVERGENCE_P99; worst {worst:.2f} pips "
                       f"in last {DIVERGENCE_WINDOW_MIN}min is unvalidated")
                if _send_telegram(env, msg):
                    state[key] = now.isoformat()
                    _append_alert_log(key, msg, now)
            continue

        threshold = p99 * DIVERGENCE_MULTIPLIER
        key = f"candle_divergence:{symbol}:{timeframe}"
        print(f"[watchdog] {symbol} {timeframe} worst divergence "
              f"{worst:.2f} pips (threshold {threshold:.2f})")

        if worst > threshold:
            if _should_alert(state, key, now):
                msg = (f"🟡 CANDLE SOURCE DIVERGENCE — {symbol} {timeframe} "
                       f"{worst:.2f} pips in last {DIVERGENCE_WINDOW_MIN}min, "
                       f"threshold {threshold:.2f} ({DIVERGENCE_MULTIPLIER:.0f}x p99 "
                       f"{p99:.2f}). yfinance and ig_stream disagree beyond anything "
                       f"seen in 21k historical comparisons — check ig_scale "
                       f"classification and stream freshness.")
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
    check_candle_divergence(env, state, now)
    check_duplicate_process(env, state, now)
    check_container(env, state, now)

    _save_state(state)
    print("[watchdog] check complete")


if __name__ == "__main__":
    main()
