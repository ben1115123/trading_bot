#!/usr/bin/env python3
"""Sends one Telegram message summarizing the last 24h of trading activity,
current open positions, heartbeat status, and watchdog alerts.

Runs via HOST cron at 23:00 UTC (07:00 MYT) -- host-based rather than
in-container so it can read the watchdog's state file, which lives on
the host filesystem (the watchdog itself must run on the host to survive
container death, so its state file isn't visible from inside the
container). Deliberately stdlib-only, same reasoning as watchdog.py: no
dependency on the project's Python environment being set up on the host.
"""
import json
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_DIR   = Path("/home/ubuntu/trading_bot")
DB_PATH    = REPO_DIR / "database" / "trades.db"
ENV_PATH   = REPO_DIR / ".env"


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
        print("[daily_summary] TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID missing from .env")
        return False
    try:
        data = urllib.parse.urlencode({"chat_id": chat, "text": message}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data)
        resp = json.loads(urllib.request.urlopen(req, timeout=5).read())
        return bool(resp.get("ok"))
    except Exception as e:
        print(f"[daily_summary] telegram send failed: {e}")
        return False


def build_summary() -> str:
    now = datetime.now(timezone.utc)
    since = (now - timedelta(hours=24)).isoformat()
    lines = [f"📊 Daily Summary — {now.strftime('%Y-%m-%d %H:%M')} UTC"]

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS n FROM trades WHERE timestamp >= ?", (since,))
    opened = cur.fetchone()["n"]

    cur.execute("""
        SELECT strategy_name, pnl FROM trades
        WHERE close_time >= ? AND pnl IS NOT NULL
    """, (since,))
    closed_rows = cur.fetchall()
    closed = len(closed_rows)
    net_pnl = sum(r["pnl"] for r in closed_rows)

    per_strategy = defaultdict(lambda: {"wins": 0, "losses": 0})
    for r in closed_rows:
        name = r["strategy_name"] or "unknown"
        if r["pnl"] >= 0:
            per_strategy[name]["wins"] += 1
        else:
            per_strategy[name]["losses"] += 1

    lines.append(f"Trades: {opened} opened, {closed} closed, net P&L ${net_pnl:.2f}")
    if per_strategy:
        lines.append("By strategy:")
        for name, wl in sorted(per_strategy.items()):
            lines.append(f"  {name}: {wl['wins']}W/{wl['losses']}L")

    cur.execute("SELECT symbol, direction, unrealised_pnl FROM positions")
    open_pos = cur.fetchall()
    if open_pos:
        lines.append(f"Open positions ({len(open_pos)}):")
        for p in open_pos:
            upnl = p["unrealised_pnl"]
            if upnl is not None:
                lines.append(f"  {p['symbol']} {p['direction']} unrealised ${upnl:.2f}")
            else:
                lines.append(f"  {p['symbol']} {p['direction']}")
    else:
        lines.append("Open positions: none")

    cur.execute("SELECT name, last_beat, details FROM heartbeat")
    beats = cur.fetchall()
    if beats:
        lines.append("Heartbeat:")
        for b in beats:
            try:
                last = datetime.fromisoformat(str(b["last_beat"]).replace("Z", "+00:00"))
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                age_min = (now - last).total_seconds() / 60
                lines.append(f"  {b['name']}: {age_min:.0f}min ago ({b['details']})")
            except Exception:
                lines.append(f"  {b['name']}: {b['last_beat']}")
    else:
        lines.append("Heartbeat: no data")

    conn.close()

    # Reads the append-only alert log (one JSON line per alert actually
    # fired), not the dedup state file -- shows fired-and-cleared events
    # too, not just conditions still unresolved right now.
    alert_log_path = REPO_DIR / "logs" / "watchdog_alerts.jsonl"
    lines.append("Watchdog alerts (last 24h):")
    if alert_log_path.exists():
        recent = []
        for line in alert_log_path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                ts = datetime.fromisoformat(entry["timestamp"])
                if (now - ts).total_seconds() <= 86400:
                    recent.append(f"  {ts.strftime('%H:%M')} UTC {entry['condition']}: {entry['message']}")
            except Exception:
                continue
        lines.extend(recent if recent else ["  none"])
    else:
        lines.append("  none")

    return "\n".join(lines)


def main():
    env = _load_env(ENV_PATH)
    summary = build_summary()
    print(summary)
    ok = _send_telegram(env, summary)
    print("SENT OK" if ok else "SEND FAILED")


if __name__ == "__main__":
    main()
