#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.models import insert_active_strategy, get_active_strategy
from scripts.score_strategies import score_strategies


def select_strategy(dry_run: bool = False) -> dict | None:
    candidates = score_strategies()

    if not candidates:
        print("No eligible strategies found.")
        return None

    best = candidates[0]
    best_score = best['score']
    best_symbol = best['symbol']

    current = get_active_strategy(symbol=best_symbol)

    if current is None:
        reason = "No active strategy — first activation"
    elif (
        current['strategy_name'] == best['strategy_name']
        and current['symbol'] == best['symbol']
        and current['timeframe'] == best['timeframe']
    ):
        print(
            f"Already active: {current['strategy_name']} {current['symbol']} "
            f"{current['timeframe']} (score {current['score']:.3f})"
        )
        return best
    elif best_score <= current['score'] + 0.10:
        print(
            f"No switch — improvement threshold not met: "
            f"{current['score']:.3f} → {best_score:.3f} "
            f"(need > {current['score'] + 0.10:.3f})"
        )
        return None
    else:
        reason = f"Score improved {current['score']:.3f} → {best_score:.3f}"

    if dry_run:
        print(
            f"[dry-run] Would activate: {best['strategy_name']} {best_symbol} "
            f"{best['timeframe']} (score {best_score:.3f}) — {reason}"
        )
        return best

    insert_active_strategy({
        "strategy_name": best['strategy_name'],
        "symbol": best_symbol,
        "timeframe": best['timeframe'],
        "strategy_type": best.get('strategy_type') or 'swing',
        "score": best_score,
        "activated_at": datetime.now(timezone.utc).isoformat(),
        "params_json": best.get('params_json') or '{}',
        "backtest_id": best.get('id'),
        "reason": reason,
    })

    print(
        f"✓ Activated: {best['strategy_name']} {best_symbol} "
        f"{best['timeframe']} (score {best_score:.3f}) — {reason}"
    )
    return best


def seed_initial_strategy() -> None:
    if get_active_strategy() is not None:
        print("Active strategy already exists — skipping seed.")
        return

    insert_active_strategy({
        "strategy_name": "stoch_rsi",
        "symbol": "US100",
        "timeframe": "HOUR",
        "strategy_type": "swing",
        "score": 0.893,
        "activated_at": datetime.now(timezone.utc).isoformat(),
        "params_json": '{"k_period": 14, "d_period": 3, "overbought": 80, "oversold": 20}',
        "backtest_id": None,
        "reason": "Manual seed — Phase 5 initial deployment",
    })
    print("✓ Seeded initial strategy: stoch_rsi US100 HOUR")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--seed", action="store_true", help="Seed initial strategy if none exists")
    args = parser.parse_args()

    if args.seed:
        seed_initial_strategy()

    select_strategy(dry_run=args.dry_run)
