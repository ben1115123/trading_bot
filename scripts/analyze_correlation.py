#!/usr/bin/env python3
"""Reads correlation_events and answers the Tier 4 question it was gathered for:
should concurrent same-direction exposure across FX pairs be BLOCKED, or only
counted?

READ-ONLY. Opens the DB in immutable mode and writes nothing.

=============================================================================
DECISION RULE -- FIXED BEFORE THIS SCRIPT WAS FIRST RUN, DELIBERATELY
=============================================================================
Build the blocking gate ONLY if BOTH hold:

  1. n >= 20 NORMALISED episodes (>= 3 legs on the SAME side of USD).
  2. Those episodes cost more than a first-symbol-only counterfactual --
     i.e. taking every leg was worse than taking only the first entry.

Below n = 20: extend collection and SAY SO. Do not decide on thin data.

This is written here rather than only in a chat message because the failure
mode it guards against is reading the output and then choosing the threshold
that agrees with it. The rule pre-dates the numbers.

Precedent: the 2026-07-24 stacking analysis measured -$219.63 versus a
first-entry-only counterfactual across 32 episodes, and that number is what
justified MAX_CONCURRENT_PER_SYMBOL = 1. This is the same shape of test
applied across symbols instead of within one.

=============================================================================
TWO CORRECTIONS THIS SCRIPT APPLIES TO THE RAW TABLE
=============================================================================
1. EPISODE COLLAPSE. correlation_events logs a STANDING STATE once per
   signal_loop cycle, not an event. A cluster open for four hours writes ~48
   rows. Raw row counts are therefore not frequencies and overstate by ~27x.
   Consecutive rows with the same (strategy, direction, symbols) within
   EPISODE_GAP_S are one episode.

2. USD NORMALISATION. Direction in the table is the raw per-symbol BUY/SELL
   signal. USDCAD is the one rostered pair with USD as BASE, so a USDCAD SELL
   is LONG USD while a EURUSD/GBPUSD/AUDUSD SELL is SHORT USD. An unnormalised
   3-symbol cluster containing USDCAD is really 2-vs-1 -- partially hedged,
   not correlated. Counting it as a 3-way correlated bet overstates cluster
   risk on exactly the combinations most likely to co-occur.

   CLAUDE.md already required this of any blocking logic built on this table.
   It is applied here, at the analysis, because the same error would otherwise
   reach the decision before it reached the code.
"""
import argparse
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime

EPISODE_GAP_S = 600          # 2 signal_loop cycles
MIN_EPISODES_TO_DECIDE = 20
USD_BASE = {"USDCAD"}        # USD is the BASE currency; every other pair quotes it


def usd_legs(symbols: list, direction: str) -> tuple:
    """(long_usd, short_usd) leg counts for a cluster.

    BUY on a USD-quote pair (EURUSD) sells USD. BUY on a USD-base pair
    (USDCAD) buys USD. The XOR flips the sense for USD-base pairs.
    """
    long_usd = short_usd = 0
    for s in symbols:
        if (direction == "BUY") ^ (s in USD_BASE):
            short_usd += 1
        else:
            long_usd += 1
    return long_usd, short_usd


def collapse_episodes(rows: list) -> list:
    """Consecutive same-(strategy,direction,symbols) rows within EPISODE_GAP_S
    are one episode. Returns dicts with start/end/row count."""
    episodes, cur = [], None
    for checked_at, strategy, direction, symbols, _count in rows:
        t = datetime.fromisoformat(checked_at)
        key = (strategy, direction, symbols)
        if cur and cur["key"] == key and (t - cur["end"]).total_seconds() <= EPISODE_GAP_S:
            cur["end"] = t
            cur["rows"] += 1
            continue
        if cur:
            episodes.append(cur)
        cur = {"key": key, "start": t, "end": t, "rows": 1}
    if cur:
        episodes.append(cur)

    for e in episodes:
        strategy, direction, symbols = e["key"]
        # DEDUPED: at least one stored row repeats a pair
        # ("EURUSD,GBPUSD,GBPUSD,AUDUSD,EURUSD"), so the writer does not always
        # store distinct pairs even though the trigger counts them. Dedupe here
        # or that episode reads as a 5-pair cluster.
        uniq = sorted(set(symbols.split(",")))
        e["strategy"], e["direction"], e["symbols"] = strategy, direction, uniq
        e["dup_in_source"] = len(uniq) != len(symbols.split(","))
        e["long_usd"], e["short_usd"] = usd_legs(uniq, direction)
        e["same_side"] = max(e["long_usd"], e["short_usd"])
        e["minutes"] = (e["end"] - e["start"]).total_seconds() / 60
    return episodes


def attach_trades(conn, episodes: list) -> None:
    """Attach the trades open during each episode, for the cluster's symbols."""
    for e in episodes:
        placeholders = ",".join("?" * len(e["symbols"]))
        rows = conn.execute(f"""
            SELECT id, symbol, direction, timestamp, close_time, pnl
            FROM trades
            WHERE strategy_name = ?
              AND symbol IN ({placeholders})
              AND pnl IS NOT NULL
              AND timestamp <= ?
              AND (close_time IS NULL OR close_time >= ?)
            ORDER BY timestamp
        """, (e["strategy"], *e["symbols"], e["end"].isoformat(), e["start"].isoformat())
        ).fetchall()
        e["trades"] = [dict(r) for r in rows]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/app/database/trades.db")
    args = ap.parse_args()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT checked_at, strategy_name, direction, symbols, count "
        "FROM correlation_events ORDER BY checked_at").fetchall()
    raw = [tuple(r) for r in rows]

    print(f"=== correlation_events — {len(raw)} raw rows ===")
    print(f"raw by direction: {dict(Counter(r[2] for r in raw))}")

    episodes = collapse_episodes(raw)
    attach_trades(conn, episodes)
    conn.close()

    print(f"\n=== EPISODE COLLAPSE (gap <= {EPISODE_GAP_S}s) ===")
    print(f"episodes: {len(episodes)}  (raw/episode {len(raw)/len(episodes):.1f}x)")
    per_dir = defaultdict(list)
    for e in episodes:
        per_dir[e["direction"]].append(e["rows"])
    for d, v in sorted(per_dir.items()):
        print(f"  {d}: {len(v)} episodes, mean {sum(v)/len(v):.1f} rows/ep, "
              f"median {sorted(v)[len(v)//2]}")
    durs = sorted(e["minutes"] for e in episodes)
    print(f"  duration min: median {durs[len(durs)//2]:.0f}  "
          f"p90 {durs[int(0.9*len(durs))]:.0f}  max {durs[-1]:.0f}")
    dups = sum(1 for e in episodes if e["dup_in_source"])
    if dups:
        print(f"  ⚠️  {dups} episode(s) had duplicate symbols in the stored "
              f"'symbols' string — deduped here")

    print("\n=== USD NORMALISATION ===")
    kept = [e for e in episodes if e["same_side"] >= 3]
    demoted = [e for e in episodes if e["same_side"] < 3]
    print(f"episodes with >= 3 legs on the same side of USD: "
          f"{len(kept)}/{len(episodes)} ({100*len(kept)/len(episodes):.0f}%)")
    print(f"demoted to 2-vs-1 (partially hedged, NOT a 3-way bet): {len(demoted)}")
    if demoted:
        print("  demoted sets:")
        for k, v in Counter(
                (",".join(e["symbols"]), e["direction"]) for e in demoted).most_common():
            print(f"    {k[0]} {k[1]}: {v}")

    print("\n=== COST vs FIRST-SYMBOL-ONLY COUNTERFACTUAL ===")
    print("(normalised episodes only; a trade in several episodes is counted "
          "once in the trade-level total)")
    ep_actual = ep_first = 0.0
    scored = 0
    seen, cluster_pnls = set(), []
    for e in kept:
        if not e["trades"]:
            continue
        scored += 1
        ep_actual += sum(t["pnl"] for t in e["trades"])
        ep_first += e["trades"][0]["pnl"]        # earliest entry
        for t in e["trades"]:
            if t["id"] not in seen:
                seen.add(t["id"])
                cluster_pnls.append(t["pnl"])

    print(f"normalised episodes with attached trades: {scored}/{len(kept)}")
    if scored:
        delta = ep_actual - ep_first
        print(f"  all legs taken:        ${ep_actual:8.2f}")
        print(f"  first entry only:      ${ep_first:8.2f}")
        print(f"  cost of the extra legs ${delta:8.2f}")
    if cluster_pnls:
        n = len(cluster_pnls)
        wins = sum(1 for p in cluster_pnls if p > 0)
        print(f"  distinct cluster trades: {n}, net ${sum(cluster_pnls):.2f}, "
              f"expectancy ${sum(cluster_pnls)/n:.2f}/trade, WR {100*wins/n:.1f}%")

    print("\n=== VERDICT (against the rule fixed in this file's docstring) ===")
    if len(kept) < MIN_EPISODES_TO_DECIDE:
        print(f"INSUFFICIENT DATA — {len(kept)} normalised episodes < "
              f"{MIN_EPISODES_TO_DECIDE}. Extend collection. Do not build the gate.")
        return 0
    if not scored:
        print(f"UNDECIDABLE — {len(kept)} normalised episodes, but none has "
              f"attached trades. The events and the ledger do not join; fix "
              f"that before deciding.")
        return 0
    if ep_actual < ep_first:
        print(f"BUILD THE GATE — taking every leg cost ${ep_first-ep_actual:.2f} "
              f"versus first-entry-only across {scored} normalised episodes.")
    else:
        print(f"DO NOT BUILD THE GATE — taking every leg was ${ep_actual-ep_first:.2f} "
              f"BETTER than first-entry-only across {scored} normalised episodes. "
              f"On this evidence the clusters are diversification, not "
              f"correlated drawdown. Keep counting.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
