#!/usr/bin/env python3
"""Export the authoritative active_strategy roster to a small standalone sqlite file.

WHY THIS EXISTS
---------------
`run_backtest.py --from-roster --roster-db PATH` needs the roster from the VPS,
because the local dev DB carries phantom `active_strategy` rows that match no
deployed strategy (findings doc finding 28) — a local run can succeed and
silently validate a fiction.

The obvious way to get it was `Connection.backup()` of the whole production DB:
**321 MB copied to read 31 rows.** This exports just the one table, plus a
provenance row recording where and when it came from, so the snapshot can be
audited rather than trusted.

USAGE
  # on the VPS
  python3 scripts/export_roster.py --out /tmp/roster.db
  # then, locally
  scp ubuntu@<host>:/tmp/roster.db ./roster.db
  python3 scripts/run_backtest.py ... --from-roster --roster-db ./roster.db

Reads the source read-only. Stdlib only, so it runs on the VPS host without the
project's dependencies (same constraint as scripts/watchdog.py).
"""
import argparse
import os
import sqlite3
import subprocess
from datetime import datetime, timezone

def _default_src() -> str:
    """Repo-relative first, cwd-relative second.

    The script-relative path breaks when the file is copied somewhere else to
    run (e.g. /tmp on the VPS), which is exactly how it gets used. Falling back
    to cwd keeps `cd repo && python3 /tmp/export_roster.py` working.
    """
    repo = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "database", "trades.db")
    if os.path.exists(repo):
        return repo
    return os.path.join(os.getcwd(), "database", "trades.db")


DEFAULT_SRC = _default_src()


def _git_head(repo_dir: str) -> str | None:
    try:
        return subprocess.check_output(["git", "-C", repo_dir, "rev-parse", "--short", "HEAD"],
                                       stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return None


def export(src_path: str, out_path: str) -> int:
    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    rows = [dict(r) for r in src.execute("SELECT * FROM active_strategy ORDER BY id")]
    cols = [d[0] for d in src.execute("SELECT * FROM active_strategy LIMIT 1").description]
    src.close()

    if os.path.exists(out_path):
        os.remove(out_path)
    dst = sqlite3.connect(out_path)
    with dst:
        # Same column names and order as production, so --roster-db can issue
        # the identical SELECT against either file.
        dst.execute(f"CREATE TABLE active_strategy ({', '.join(c + ' TEXT' for c in cols)})")
        dst.executemany(
            f"INSERT INTO active_strategy ({', '.join(cols)}) "
            f"VALUES ({', '.join('?' * len(cols))})",
            [tuple(r[c] for c in cols) for r in rows])

        # Provenance travels WITH the snapshot. A roster file with no origin is
        # indistinguishable from the phantom local one it exists to replace.
        dst.execute("CREATE TABLE snapshot_provenance ("
                    "taken_at TEXT, source_path TEXT, source_host TEXT, "
                    "git_head TEXT, row_count INTEGER)")
        dst.execute("INSERT INTO snapshot_provenance VALUES (?,?,?,?,?)",
                    (datetime.now(timezone.utc).isoformat(),
                     os.path.abspath(src_path),
                     os.uname().nodename,
                     _git_head(os.path.dirname(os.path.dirname(os.path.abspath(src_path)))),
                     len(rows)))
    dst.close()

    size = os.path.getsize(out_path)
    print(f"exported {len(rows)} active_strategy rows -> {out_path} ({size:,} bytes)")
    runnable = [r for r in rows if r.get("status") in ("active", "paper")]
    print(f"  runnable (active|paper): {len(runnable)}")
    for r in runnable:
        print(f"    id={r['id']:<3} {r['symbol']:7} {r.get('timeframe') or '?':6} "
              f"{r['strategy_name']:22} {r['status']}")
    return len(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=DEFAULT_SRC, help="source trades.db (read-only)")
    ap.add_argument("--out", required=True, help="destination snapshot path")
    a = ap.parse_args()
    export(a.src, a.out)
