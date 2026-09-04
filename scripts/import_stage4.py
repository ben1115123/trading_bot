#!/usr/bin/env python3
"""Import a Stage 4 export into the VPS database. Additive, row by row, refusals not warnings.

⛔ THE THING THIS EXISTS TO PREVENT
-----------------------------------
NEVER copy the local trades.db over the VPS one. It would destroy the live
`trades`, `paper_trades`, `signal_log` and `active_strategy` tables. This
inserts rows; it never replaces a file, never drops a table, never updates an
existing row.

RUNS ON THE VPS. Dry-run by default (same contract as
scripts/reaudit_close_prices.py) — `--confirm` to write.

THE SIX RULES — every one a REFUSAL, not a warning
--------------------------------------------------
1. Refuse any row whose engine_version != current. Never mix trade models.
2. Refuse any row whose spread_model != current, and compare spread_table_sha
   as well: spread is a PARAMETER, and a NAME CAN BE KEPT WHILE THE NUMBERS
   CHANGE UNDERNEATH IT. That is the whole reason the hash column exists.
3. Insert WITHOUT `id`, so the VPS autoincrement assigns fresh ones. Local ids
   are meaningless here and would collide.
4. Idempotent: skip any row whose natural key already exists. Re-running the
   import must be a NO-OP, not a duplicate.
5. Connection.backup() the target first, never `cp` — cp on a live DB with an
   open WAL can produce a torn copy. Record it in CLAUDE.md's Database Backups
   table in the same change.
6. Read back and report counts after inserting. Do NOT infer success from the
   absence of an exception (CLAUDE.md, Unverified Controls).

OFF-HOST PROVENANCE
-------------------
Every imported row is stamped with where it was actually produced. Finding 31
gave backtest_results its candle-cache columns; it still has no free-form
provenance field, so this adds `import_json` (additive TEXT, no engine bump —
provenance cannot change what trades a run produces). walkforward_runs already
has `extra_json` and the stamp is merged in there, under key "import", which is
where _persist_wf_run already puts run provenance.

The stamp records: produced_on (the hostname that RAN the backtest, read from
the export's own provenance table — not this host), imported_at, the
roster_snapshot git HEAD the params came from, the source filename and its
sha256. A row that cannot say it was produced off-host is exactly the gap
finding 31 describes, one engine version further on.

SCHEMA
------
Ensures the additive columns exist before inserting, using the identical
ALTER statements committed in database/db.py. Idempotent, and it runs AFTER the
backup. An importer that assumes its target schema is an importer that fails
halfway through a batch.

USAGE
  python3 scripts/import_stage4.py --file stage4_20260823T....db            # dry run
  python3 scripts/import_stage4.py --file stage4_20260823T....db --confirm
"""
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine_version import CURRENT_ENGINE_VERSION          # noqa: E402
from spread_model import CURRENT_SPREAD_MODEL              # noqa: E402

DEFAULT_TARGET = "/home/ubuntu/trading_bot/database/trades.db"
DEFAULT_BACKUP_DIR = "/home/ubuntu/backups"

# Rule 4 — natural keys. The microsecond/second timestamps make these
# effectively unique; the point is that re-running the import is a no-op.
NATURAL_KEYS = {
    "backtest_results": ["strategy_name", "symbol", "timeframe", "params_json", "run_at"],
    "walkforward_runs": ["run_type", "strategy_name", "symbol", "timeframe",
                         "params_json", "cache_file", "created_at"],
}

# Columns this script may add to the target. Additive only.
#
# ⚠️ THE COMMENT HERE USED TO READ "Mirrors database/db.py exactly." It did
# not. dc34602 added `profit_factor` to db.py and never touched this file, so
# an export carrying that column would have built an INSERT naming a column the
# VPS table does not have — OperationalError at import, AFTER the whole batch
# had run. A comment claiming a mirror is a control believed present and never
# checked; that is the recurring failure class in this repo, so the mirror is
# now VERIFIED AT RUN TIME by check_mirror() below rather than asserted here.
#
# `import_json` is deliberately NOT in db.py: it is written only by this
# script, on the target. So the check is ONE-DIRECTIONAL — db.py must not
# contain anything this list cannot supply, but this list may carry extras.
ENSURE_COLUMNS = {
    "backtest_results": [
        ("cache_file",         "TEXT"),
        ("cache_candle_count", "INTEGER"),
        ("cache_date_start",   "TEXT"),
        ("cache_date_end",     "TEXT"),
        ("profit_factor",      "REAL"),
        ("import_json",        "TEXT"),
    ],
    "walkforward_runs": [],
}


def reference_schema() -> dict:
    """The columns database/db.py ACTUALLY creates, obtained by running it.

    Not by parsing db.py — its schema is spread across a CREATE TABLE plus a
    dozen try/except ALTER migrations, and a parser would be a second
    definition of the schema that can drift from the first. This builds a
    throwaway database, runs init_db() against it, and reads PRAGMA
    table_info. Executable definition, no parsing, cannot drift.

    DDL SAFETY: DATABASE_PATH is patched to a temp file BEFORE init_db() is
    called, so this can never touch a real database. get_connection() reads the
    module global at call time, which is what makes the patch effective.
    """
    import tempfile
    import database.db as _db
    original = _db.DATABASE_PATH
    tmpdir = tempfile.mkdtemp(prefix="stage4_refschema_")
    try:
        _db.DATABASE_PATH = os.path.join(tmpdir, "reference.db")
        _db.init_db()
        conn = sqlite3.connect(_db.DATABASE_PATH)
        try:
            return {t: {r[1]: (r[2] or "TEXT") for r in
                        conn.execute(f"PRAGMA table_info({t})")}
                    for t in ENSURE_COLUMNS}
        finally:
            conn.close()
    finally:
        _db.DATABASE_PATH = original
        shutil.rmtree(tmpdir, ignore_errors=True)


def check_mirror(conn) -> None:
    """Refuse if db.py declares a column the target lacks and this script
    cannot add.

    This is the guard that the stale comment was standing in for. It fires on
    exactly the case that would otherwise surface as an OperationalError after
    the batch: a new column in db.py, absent from the target, undeclared here.
    """
    try:
        reference = reference_schema()
    except Exception as e:
        _refuse(f"could not build the reference schema from database/db.py "
                f"({type(e).__name__}: {e}). The mirror between db.py and "
                f"ENSURE_COLUMNS cannot be verified, and an unverified mirror "
                f"is what this check exists to replace. Refusing rather than "
                f"proceeding on the assumption that it still holds.")
    drift = {}
    for table, refcols in reference.items():
        have      = set(_cols(conn, table))
        declared  = {c for c, _ in ENSURE_COLUMNS[table]}
        # Only columns that are genuinely missing from the target matter: on a
        # normal target everything else already exists.
        gap = [c for c in refcols if c not in have and c not in declared]
        if gap:
            drift[table] = gap
    if drift:
        _refuse(
            f"ENSURE_COLUMNS has DRIFTED from database/db.py. Missing from the "
            f"target and undeclared here: {drift}. db.py gained the column and "
            f"this script was not updated — the exact shape that made "
            f"`profit_factor` a post-batch OperationalError. Add it to "
            f"ENSURE_COLUMNS with its type, then re-run."
        )
    print(f"[schema] mirror verified against database/db.py — "
          f"{ {t: len(c) for t, c in reference.items()} } reference columns, no drift")


def _refuse(msg):
    raise SystemExit(f"REFUSED: {msg}")


def _sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]


def _cols(conn, table):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def backup_target(target: str, backup_dir: str) -> str:
    """Rule 5. SQLite online backup API. Never cp."""
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = os.path.join(backup_dir, f"trades.bak-{stamp}.db")
    if os.path.exists(out):
        _refuse(f"{out} already exists. A backup is a record of one moment; overwriting one "
                f"destroys the state it was taken to preserve. Wait a second and re-run.")
    src = sqlite3.connect(target)
    dst = sqlite3.connect(out)
    with dst:
        src.backup(dst)
    ok = dst.execute("PRAGMA integrity_check").fetchone()[0]
    dst.close()
    src.close()
    if ok != "ok":
        _refuse(f"backup integrity_check returned {ok!r} — refusing to import onto a DB "
                f"whose backup cannot be trusted")
    print(f"[backup] {out} ({os.path.getsize(out):,} bytes, integrity_check ok)")
    print(f"[backup] ⚠️  RECORD THIS IN CLAUDE.md's Database Backups TABLE IN THE SAME CHANGE. "
          f"An unlisted backup is how the next disk-pressure investigation starts from a "
          f"wrong baseline.")
    return out


def ensure_columns(conn, confirm: bool):
    check_mirror(conn)
    for table, cols in ENSURE_COLUMNS.items():
        have = _cols(conn, table)
        missing = [(c, d) for c, d in cols if c not in have]
        if not missing:
            continue
        print(f"[schema] {table}: adding {[c for c, _ in missing]}")
        if not confirm:
            continue
        for c, d in missing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {c} {d}")
        conn.commit()


def load_export(path: str) -> dict:
    if not os.path.exists(path):
        _refuse(f"{path} does not exist")
    src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    have = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    missing = ({"export_provenance"} | set(NATURAL_KEYS)) - have
    if missing:
        _refuse(f"{path} is missing table(s) {sorted(missing)} — it is not a "
                f"stage4 export. Refusing to guess at its shape.")
    prov = src.execute("SELECT * FROM export_provenance ORDER BY rowid DESC LIMIT 1").fetchone()
    if prov is None:
        _refuse("export carries no export_provenance row. A result file with no origin is "
                "indistinguishable from one produced by an unknown engine on unknown candles.")
    prov = dict(prov)
    data = {t: [dict(r) for r in src.execute(f"SELECT * FROM {t} ORDER BY id")]
            for t in NATURAL_KEYS}
    src.close()
    return {"provenance": prov, "data": data}


def validate(rows, table):
    """Rules 1 and 2. Refusals, evaluated before anything is written."""
    for r in rows:
        if r.get("engine_version") != CURRENT_ENGINE_VERSION:
            _refuse(f"{table} row (local id={r.get('id')}) carries engine_version "
                    f"{r.get('engine_version')!r} != {CURRENT_ENGINE_VERSION!r}. "
                    f"Never mix trade models.")
        if r.get("spread_model") != CURRENT_SPREAD_MODEL:
            _refuse(f"{table} row (local id={r.get('id')}) carries spread_model "
                    f"{r.get('spread_model')!r} != {CURRENT_SPREAD_MODEL!r}.")
    shas = {r.get("spread_table_sha") for r in rows}
    if len(shas) > 1:
        _refuse(f"{table} rows carry MORE THAN ONE spread_table_sha {sorted(map(str, shas))}. "
                f"The model name matched, so this batch changed its spread NUMBERS mid-run — "
                f"exactly the case spread_table_sha exists to catch.")
    return shas.pop() if shas else None


def _stamp(prov, file_path):
    return {
        "produced_on":     prov.get("produced_on"),
        "produced_git_head": prov.get("git_head"),
        "exported_at":     prov.get("exported_at"),
        "imported_at":     datetime.now(timezone.utc).isoformat(),
        "imported_on":     os.uname().nodename,
        "roster_snapshot": json.loads(prov.get("roster_snapshot") or "null"),
        "source_file":     os.path.basename(file_path),
        "source_sha256":   _sha(file_path),
        "batch_since":     prov.get("batch_since"),
    }


def import_rows(conn, table, rows, stamp, confirm):
    """Rules 3 and 4."""
    target_cols = _cols(conn, table)
    key = NATURAL_KEYS[table]
    inserted = skipped = 0
    for r in rows:
        where = " AND ".join(f"{k} IS ?" for k in key)
        if conn.execute(f"SELECT 1 FROM {table} WHERE {where} LIMIT 1",
                        tuple(r.get(k) for k in key)).fetchone():
            skipped += 1
            continue

        row = {k: v for k, v in r.items() if k != "id" and k in target_cols}  # rule 3
        if table == "walkforward_runs":
            extra = json.loads(row.get("extra_json") or "{}")
            if not isinstance(extra, dict):
                extra = {"_extra": extra}
            extra["import"] = stamp
            row["extra_json"] = json.dumps(extra, default=str)
        else:
            row["import_json"] = json.dumps(stamp, default=str)

        cols = list(row)
        if confirm:
            conn.execute(f"INSERT INTO {table} ({', '.join(cols)}) "
                         f"VALUES ({', '.join('?' * len(cols))})",
                         tuple(row[c] for c in cols))
        inserted += 1
    if confirm:
        conn.commit()
    return inserted, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="stage4_<UTCstamp>.db produced by export_stage4.py")
    ap.add_argument("--target", default=DEFAULT_TARGET)
    ap.add_argument("--backup-dir", default=DEFAULT_BACKUP_DIR)
    ap.add_argument("--confirm", action="store_true", help="actually write (default: dry run)")
    ap.add_argument("--no-backup", action="store_true",
                    help="skip the backup. ONLY for a throwaway target, never production.")
    a = ap.parse_args()

    payload = load_export(a.file)
    prov, data = payload["provenance"], payload["data"]
    print(f"[export] produced_on={prov.get('produced_on')} git_head={prov.get('git_head')} "
          f"exported_at={prov.get('exported_at')}")
    print(f"[export] engine_version={prov.get('engine_version')} "
          f"spread_model={prov.get('spread_model')} since={prov.get('batch_since')}")
    print(f"[export] roster_snapshot={prov.get('roster_snapshot')}")
    print(f"[export] sha256:{_sha(a.file)}  counts={prov.get('counts_json')}")

    for t, rows in data.items():                       # rules 1 + 2, before any write
        sha = validate(rows, t)
        print(f"[validate] {t}: {len(rows)} rows OK  spread_table_sha={sha}")

    if not any(data.values()):
        _refuse("export contains zero rows. Importing nothing is indistinguishable from a "
                "batch that never ran — re-check the export's --since.")

    if a.confirm and not a.no_backup:
        backup_target(a.target, a.backup_dir)          # rule 5, before any schema change

    conn = sqlite3.connect(a.target)
    try:
        ensure_columns(conn, a.confirm)
        stamp = _stamp(prov, a.file)
        before = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in data}
        results = {}
        for t, rows in data.items():
            results[t] = import_rows(conn, t, rows, stamp, a.confirm)

        # Rule 6 — read back. Never infer success from no exception being raised.
        print()
        for t, (ins, skip) in results.items():
            after = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            delta = after - before[t]
            print(f"{'[WROTE]' if a.confirm else '[DRY  ]'} {t}: "
                  f"inserted={ins} skipped_existing={skip}  "
                  f"count {before[t]} -> {after} (delta {delta})")
            if a.confirm and delta != ins:
                _refuse(f"{t}: read-back delta {delta} != inserted {ins}. "
                        f"Something else wrote to this table during the import.")
            if a.confirm and ins:
                stamped = conn.execute(
                    f"SELECT COUNT(*) FROM {t} WHERE "
                    + ("import_json IS NOT NULL" if t == "backtest_results"
                       else "extra_json LIKE '%\"import\"%'")).fetchone()[0]
                print(f"          off-host stamp present on {stamped} rows in {t}")
        if not a.confirm:
            print("\nDRY RUN — nothing written. Re-run with --confirm.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
