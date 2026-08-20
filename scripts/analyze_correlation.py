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
import random
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

    print("\n=== COST vs COUNTERFACTUAL ===")
    # DEDUPED AT TRADE LEVEL, deliberately. Summing per episode double-counts:
    # a position open across several episodes contributes once per episode, and
    # with 94 episodes over ~100 distinct trades the repeats dominate the
    # totals on BOTH arms. Every figure below is over DISTINCT trade ids.
    #
    # Arm A is the rule as fixed: first entry only.
    # Arm B is what a gate would actually do -- it can only block a leg that
    # OPENS while the cluster already exists; legs already open when the
    # cluster forms are untouched by any entry gate. Reported because A
    # flatters the gate by crediting it with blocking trades it could not
    # reach.
    by_id = {}
    first_ids, opened_during_ids = set(), set()
    for e in kept:
        if not e["trades"]:
            continue
        for t in e["trades"]:
            by_id[t["id"]] = t
        first_ids.add(e["trades"][0]["id"])
        for t in e["trades"]:
            if datetime.fromisoformat(t["timestamp"]) >= e["start"]:
                opened_during_ids.add(t["id"])
    # a trade that is some episode's first entry is never treated as blockable
    opened_during_ids -= first_ids

    # ARM C -- the leg that CREATED the cluster. An episode begins because a
    # third same-side leg opened, so that leg lands just BEFORE the first
    # logged row and escapes both arms above. It is precisely what an exposure
    # gate checked at entry would refuse, which makes it the only arm that
    # measures the gate's real surface.
    forming_ids = set()
    for e in kept:
        pre = [t for t in e["trades"]
               if datetime.fromisoformat(t["timestamp"]) <= e["start"]]
        if not pre:
            continue
        last = max(pre, key=lambda t: t["timestamp"])
        age = (e["start"] - datetime.fromisoformat(last["timestamp"])).total_seconds()
        if age <= EPISODE_GAP_S:
            forming_ids.add(last["id"])

    scored = sum(1 for e in kept if e["trades"])
    print(f"normalised episodes with attached trades: {scored}/{len(kept)}")
    if not by_id:
        actual = arm_a = arm_b = 0.0
    else:
        actual = sum(t["pnl"] for t in by_id.values())
        arm_a  = sum(by_id[i]["pnl"] for i in first_ids)
        arm_b  = actual - sum(by_id[i]["pnl"] for i in opened_during_ids)
        n = len(by_id)
        wins = sum(1 for t in by_id.values() if t["pnl"] > 0)
        print(f"  distinct cluster trades: {n}, net ${actual:.2f}, "
              f"expectancy ${actual/n:.2f}/trade, WR {100*wins/n:.1f}%")
        print(f"  ARM A  first entry only ({len(first_ids)} trades):      "
              f"${arm_a:8.2f}   -> extra legs {'cost' if actual < arm_a else 'gained'} "
              f"${abs(actual-arm_a):.2f}")
        print(f"  ARM B  block legs opening mid-cluster "
              f"({len(opened_during_ids)} blocked): ${arm_b:8.2f}   "
              f"-> those legs {'cost' if actual < arm_b else 'gained'} "
              f"${abs(actual-arm_b):.2f}")
        arm_c = actual - sum(by_id[i]["pnl"] for i in forming_ids)
        print(f"  ARM C  block the cluster-FORMING leg "
              f"({len(forming_ids)} blocked): ${arm_c:8.2f}   "
              f"-> those legs {'cost' if actual < arm_c else 'gained'} "
              f"${abs(actual-arm_c):.2f}")

    # ATTRIBUTION TEST -- the step that decides this.
    #
    # "Blocking these legs would have saved money" is NOT evidence that
    # clustering is the risk. If the strategy loses money generally, then
    # blocking ANY 45 of its trades saves money, and a correlation gate is
    # just an expensive proxy for "stop trading a losing strategy" -- it would
    # fire on the cluster and leave the actual loss untouched.
    #
    # So the cluster-forming legs are compared against random same-window
    # samples of the SAME strategy's trades. Only if they are materially worse
    # than that baseline is the clustering itself carrying the cost.
    print("\n=== ATTRIBUTION — are cluster legs worse than this strategy's average? ===")
    verdict_attributable = None
    if forming_ids:
        lo = min(t["timestamp"] for t in by_id.values())
        hi = max(t["timestamp"] for t in by_id.values())
        pool = [r["pnl"] for r in conn.execute(
            "SELECT pnl FROM trades WHERE strategy_name = ? AND pnl IS NOT NULL "
            "AND timestamp BETWEEN ? AND ?", (episodes[0]["strategy"], lo, hi))]
        n = len(forming_ids)
        obs = sum(by_id[i]["pnl"] for i in forming_ids)
        if len(pool) > n:
            pwr = 100 * sum(1 for p in pool if p > 0) / len(pool)
            fwr = 100 * sum(1 for i in forming_ids if by_id[i]["pnl"] > 0) / n
            print(f"  window {lo[:10]} -> {hi[:10]}")
            print(f"  baseline (all {episodes[0]['strategy']} trades): n={len(pool)}, "
                  f"net ${sum(pool):.2f}, expectancy ${sum(pool)/len(pool):.2f}, "
                  f"WR {pwr:.1f}%")
            print(f"  cluster-forming legs:            n={n}, "
                  f"net ${obs:.2f}, expectancy ${obs/n:.2f}, WR {fwr:.1f}%")
            random.seed(42)
            draws = [sum(random.sample(pool, n)) for _ in range(20000)]
            pct = sum(1 for d in draws if d <= obs) / len(draws)
            print(f"  bootstrap 20k draws of {n} random same-window trades:")
            print(f"    P(random <= observed) = {pct:.3f}  "
                  f"(median random sum ${sorted(draws)[len(draws)//2]:.2f})")
            verdict_attributable = pct < 0.05
            print(f"  -> clustering {'IS' if verdict_attributable else 'is NOT'} "
                  f"distinguishable from ordinary strategy performance")

    print("\n=== VERDICT (against the rule fixed in this file's docstring) ===")
    if verdict_attributable is False:
        print(f"DO NOT BUILD THE GATE — the cluster-forming legs are not "
              f"distinguishable from random trades of the same strategy in the "
              f"same window. Blocking them would have 'saved' money only because "
              f"the strategy loses money generally. A correlation gate here is a "
              f"proxy for a strategy problem and would leave that problem in "
              f"place. Keep counting; fix the strategy.")
        return 0
    if len(kept) < MIN_EPISODES_TO_DECIDE:
        print(f"INSUFFICIENT DATA — {len(kept)} normalised episodes < "
              f"{MIN_EPISODES_TO_DECIDE}. Extend collection. Do not build the gate.")
        return 0
    if not scored:
        print(f"UNDECIDABLE — {len(kept)} normalised episodes, but none has "
              f"attached trades. The events and the ledger do not join; fix "
              f"that before deciding.")
        return 0
    if actual < arm_a and actual < arm_b:
        print(f"BUILD THE GATE — taking every leg cost ${arm_a-actual:.2f} (arm A) / "
              f"${arm_b-actual:.2f} (arm B) across {scored} normalised episodes, "
              f"{len(by_id)} distinct trades.")
    elif actual >= arm_a and actual >= arm_b:
        print(f"DO NOT BUILD THE GATE — taking every leg was ${actual-arm_a:.2f} "
              f"(arm A) / ${actual-arm_b:.2f} (arm B) BETTER than blocking, across "
              f"{scored} normalised episodes, {len(by_id)} distinct trades. On this "
              f"evidence the clusters are not correlated drawdown. Keep counting.")
    else:
        print(f"SPLIT — arm A and arm B disagree (actual ${actual:.2f}, A ${arm_a:.2f}, "
              f"B ${arm_b:.2f}). Arm B is the faithful model of an entry gate; A "
              f"credits the gate with blocking trades it could not reach. Do not "
              f"build on a split result.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
