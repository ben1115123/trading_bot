#!/usr/bin/env python3
"""Export a Stage 4 batch's result rows to a standalone sqlite file for import to the VPS.

WHY THIS EXISTS
---------------
Stage 4 re-validation runs LOCALLY (the VPS has no scripts/candle_cache/ at all,
and seeding one means either baking ~36 MB into every image layer via
Dockerfile's `COPY . .` or adding a bind mount to run a batch job). That
deepens the local-vs-VPS corpus split, finding 11. This script plus
import_stage4.py is what stops the split becoming permanent.

A run whose results have no defined path home is how the walkforward_runs gap
happened twice: the 2026-07-15 AUDUSD promotion has no persisted walk-forward
because the table did not exist yet, and the EURUSD REJECT-vs-MARGINAL
discrepancy is permanently unresolvable because no run recorded its candles.
Define the import before the export.

WHAT CROSSES
------------
ONLY rows produced by the batch:
    backtest_results  WHERE engine_version = CURRENT AND run_at    >= --since
    walkforward_runs  WHERE engine_version = CURRENT AND created_at >= --since

Nothing else. The local DB also holds 5,329 pre-parity backtest_results and 276
walkforward_runs, 1,166 and 82 of which are ETF-contaminated (finding 30). None
of that crosses.

WHAT DELIBERATELY DOES NOT CROSS
--------------------------------
`backtest_trades`. It is a CHILD table keyed on backtest_id, and the import
inserts without ids so the VPS autoincrement assigns fresh ones — carrying the
children means remapping every foreign key, which is a different and larger
piece of work than the two tables this was scoped to. Consequence, stated here
rather than discovered later: an imported backtest_results row on the VPS has
NO per-trade detail behind it. The aggregate is auditable, the trade list is
not, and it stays local. Do not read a VPS row's absent trades as a failed
import.

FORM
----
A standalone sqlite file `stage4_<UTCstamp>.db` with the SAME table schemas,
column names and column order as production, so a reader can diff it against
either DB with the identical SELECT. Same shape as export_roster.py, and for
the same reason: a file that can be inspected before it is trusted.

Stdlib only (same safe contract as export_roster.py / watchdog.py) EXCEPT for
reading the current stamps, which come from the repo's engine_version.py and
spread_model.py — both zero-import modules by design.

USAGE
  python3 scripts/export_stage4.py --since '2026-08-23 00:00:00' \
      --roster-db ./roster.db --out-dir .
"""
import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine_version import CURRENT_ENGINE_VERSION          # noqa: E402
from spread_model import CURRENT_SPREAD_MODEL              # noqa: E402

# table -> (timestamp column, strftime format that column is STORED in)
#
# The two columns are stored in DIFFERENT formats and both are compared as
# TEXT by sqlite. backtest_results.run_at is 'YYYY-MM-DD HH:MM:SS';
# walkforward_runs.created_at is ISO with a 'T' separator. Since 'T' (0x54)
# sorts ABOVE ' ' (0x20), passing one format against the other silently widens
# the window by a whole day and sweeps in rows from BEFORE the batch — an
# import that is wrong in the one direction nobody would check, because extra
# rows arriving looks like the import working. --since is therefore parsed
# once and re-formatted per table.
TABLES = {
    "backtest_results": ("run_at",     "%Y-%m-%d %H:%M:%S"),
    "walkforward_runs": ("created_at", "%Y-%m-%dT%H:%M:%S"),
}


def _parse_since(raw: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:19], fmt)
        except ValueError:
            continue
    raise SystemExit(f"REFUSED: cannot parse --since {raw!r}. "
                     f"Use 'YYYY-MM-DD HH:MM:SS' or ISO.")


def _git_head(repo_dir: str):
    try:
        return subprocess.check_output(["git", "-C", repo_dir, "rev-parse", "--short", "HEAD"],
                                       stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return None


def _roster_head(roster_db: str):
    """git HEAD recorded inside the roster snapshot the params came from.

    An imported row must be able to answer "which roster produced these
    params". The roster file carries its own provenance (export_roster.py);
    this reads it rather than re-deriving it, because re-deriving it locally
    would record the LOCAL head, which is not the question.
    """
    if not roster_db or not os.path.exists(roster_db):
        return None
    try:
        c = sqlite3.connect(f"file:{roster_db}?mode=ro", uri=True)
        row = c.execute("SELECT git_head, source_host, taken_at FROM snapshot_provenance "
                        "ORDER BY rowid DESC LIMIT 1").fetchone()
        c.close()
        return {"git_head": row[0], "source_host": row[1], "taken_at": row[2]} if row else None
    except Exception:
        return None


def _ddl(src: sqlite3.Connection, table: str) -> str:
    r = src.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                    (table,)).fetchone()
    if not r:
        raise SystemExit(f"REFUSED: source has no table {table}")
    return r[0]


def export(src_path: str, since: str, out_path: str, roster_db: str = None,
           margin_minutes: int = 10) -> dict:
    """margin_minutes: how far BEFORE --since to actually start the window.

    THIS IS NOT SLOP, IT IS A CORRECTION FOR A MEASURED DEFECT. This WSL host's
    `datetime.now(timezone.utc)` sporadically jumps **+5:09** and snaps back:
    8 of 181 consecutive `walkforward_runs` rows written on 2026-08-23 carry a
    created_at LATER than the row inserted after them, every one by exactly
    5 min 9 s (finding 34). Rows are therefore stamped out of order relative to
    their own AUTOINCREMENT ids, and a timestamp bound taken from the same clock
    can land on the wrong side of rows that belong to the batch.

    The two errors are not symmetric, which is what decides the default:
      - OVER-including is harmless. The engine_version filter blocks anything
        from another trade model, and the import is idempotent on a natural key,
        so an already-imported row is skipped rather than duplicated.
      - UNDER-including is SILENT. Missing rows look exactly like a batch that
        produced fewer results, and nothing downstream can tell the difference.

    So the window is widened by default. Pass margin_minutes=0 for an exact
    bound only when the run is known to be clean.
    """
    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row

    if os.path.exists(out_path):
        raise SystemExit(f"REFUSED: {out_path} already exists. "
                         f"An export is a record of one batch; never overwrite one.")
    dst = sqlite3.connect(out_path)

    since_dt = _parse_since(since) - timedelta(minutes=margin_minutes)
    if margin_minutes:
        print(f"[bound] --since widened by {margin_minutes} min -> {since_dt} "
              f"(local clock is not monotonic, see finding 34)")
    counts = {}
    with dst:
        for table, (ts_col, ts_fmt) in TABLES.items():
            bound = since_dt.strftime(ts_fmt)
            # Same DDL as production verbatim -> same column names, same order.
            dst.execute(_ddl(src, table))
            rows = [dict(r) for r in src.execute(
                f"SELECT * FROM {table} WHERE engine_version = ? AND {ts_col} >= ? "
                f"ORDER BY id", (CURRENT_ENGINE_VERSION, bound))]
            if rows:
                cols = list(rows[0].keys())
                dst.executemany(
                    f"INSERT INTO {table} ({', '.join(cols)}) "
                    f"VALUES ({', '.join('?' * len(cols))})",
                    [tuple(r[c] for c in cols) for r in rows])
            counts[table] = len(rows)

            # A row that claims the current engine but a stale spread model is
            # a mixed batch. Catch it at export, not at import: the operator
            # who can still fix it is the one running this.
            bad = [r for r in rows if r.get("spread_model") != CURRENT_SPREAD_MODEL]
            if bad:
                raise SystemExit(
                    f"REFUSED: {len(bad)} {table} rows carry spread_model "
                    f"{sorted({r.get('spread_model') for r in bad})} != {CURRENT_SPREAD_MODEL!r}. "
                    f"Spread is a PARAMETER, not part of engine_version — mixing them "
                    f"silently blurs measured and unmeasured rows.")

        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dst.execute("CREATE TABLE export_provenance ("
                    "exported_at TEXT, produced_on TEXT, source_path TEXT, "
                    "git_head TEXT, engine_version TEXT, spread_model TEXT, "
                    "batch_since TEXT, roster_snapshot TEXT, counts_json TEXT)")
        dst.execute("INSERT INTO export_provenance VALUES (?,?,?,?,?,?,?,?,?)",
                    (datetime.now(timezone.utc).isoformat(),
                     os.uname().nodename,
                     os.path.abspath(src_path),
                     _git_head(repo),
                     CURRENT_ENGINE_VERSION,
                     CURRENT_SPREAD_MODEL,
                     since,
                     json.dumps(_roster_head(roster_db)),
                     json.dumps(counts)))
    dst.close()
    src.close()

    sha = hashlib.sha256(open(out_path, "rb").read()).hexdigest()[:16]
    print(f"exported -> {out_path} ({os.path.getsize(out_path):,} bytes, sha256:{sha})")
    for t, n in counts.items():
        ts_col, ts_fmt = TABLES[t]
        print(f"  {t}: {n} rows  (engine_version={CURRENT_ENGINE_VERSION}, "
              f"{ts_col} >= {since_dt.strftime(ts_fmt)})")
    if not any(counts.values()):
        print("  ⚠️  ZERO rows exported. That is not necessarily an error, but it is "
              "indistinguishable from a batch that never ran — check --since against "
              "the batch's actual start before importing this file.")
    return counts


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database", "trades.db"))
    ap.add_argument("--since", required=True,
                    help="batch start, UTC ('YYYY-MM-DD HH:MM:SS' or ISO). Re-formatted "
                         "per table to match how each column is actually stored.")
    ap.add_argument("--roster-db", help="roster snapshot the params came from (for provenance)")
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--out", help="explicit output path (overrides --out-dir naming)")
    ap.add_argument("--since-margin-minutes", type=int, default=10,
                    help="widen the --since window backwards by this many minutes "
                         "(default 10). Corrects for the non-monotonic local clock, "
                         "finding 34. Over-including is caught by the engine_version "
                         "filter and by idempotent import; under-including is silent.")
    a = ap.parse_args()
    out = a.out or os.path.join(
        a.out_dir, f"stage4_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.db")
    export(a.src, a.since, out, a.roster_db, margin_minutes=a.since_margin_minutes)
