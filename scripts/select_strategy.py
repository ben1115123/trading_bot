#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.models import insert_active_strategy, get_active_strategy
from scripts.score_strategies import score_strategies

SYMBOLS = ["BTC", "US100", "US500"]

SEED_STRATEGIES = {
    "US100": {
        "strategy_name": "stoch_rsi", "timeframe": "HOUR", "strategy_type": "swing",
        "score": 0.893, "params_json": '{"k_period": 14, "d_period": 3, "overbought": 80, "oversold": 20}',
        "reason": "Manual seed — Phase 5 initial deployment",
    },
    "US500": {
        "strategy_name": "rsi", "timeframe": "HOUR", "strategy_type": "swing",
        "score": 0.689, "params_json": '{"period": 14, "overbought": 70, "oversold": 30}',
        "reason": "Manual seed — Phase 5 initial deployment",
    },
    "BTC": {
        "strategy_name": "vwap_ema", "timeframe": "HOUR", "strategy_type": "swing",
        "score": 0.654, "params_json": '{"ema_period": 20}',
        "reason": "Manual seed — Phase 5 initial deployment",
    },
}


def _select_for_symbol(symbol: str, candidates: list, dry_run: bool) -> dict | None:
    sym_candidates = [c for c in candidates if c["symbol"] == symbol]
    if not sym_candidates:
        print(f"[{symbol}] No eligible strategies found.")
        return None

    best = sym_candidates[0]  # already sorted score DESC
    best_score = best["score"]
    current = get_active_strategy(symbol=symbol)

    if current is None:
        reason = f"No active strategy for {symbol} — first activation"
    elif (current["strategy_name"] == best["strategy_name"]
          and current["timeframe"] == best["timeframe"]):
        print(f"[{symbol}] Already active: {current['strategy_name']} "
              f"{current['timeframe']} (score {current['score']:.3f})")
        return best
    elif best_score <= (current["score"] or 0) + 0.10:
        print(f"[{symbol}] No switch — threshold not met: "
              f"{current['score']:.3f} → {best_score:.3f} "
              f"(need > {(current['score'] or 0) + 0.10:.3f})")
        return None
    else:
        reason = f"Score improved {(current['score'] or 0):.3f} → {best_score:.3f}"

    if dry_run:
        print(f"[{symbol}] [dry-run] Would activate: {best['strategy_name']} "
              f"{best['timeframe']} (score {best_score:.3f}) — {reason}")
        return best

    insert_active_strategy({
        "strategy_name": best["strategy_name"],
        "symbol": symbol,
        "timeframe": best["timeframe"],
        "strategy_type": best.get("strategy_type") or "swing",
        "score": best_score,
        "activated_at": datetime.now(timezone.utc).isoformat(),
        "params_json": best.get("params_json") or "{}",
        "backtest_id": best.get("id"),
        "reason": reason,
    })
    print(f"[{symbol}] ✓ Activated: {best['strategy_name']} {best['timeframe']} "
          f"(score {best_score:.3f}) — {reason}")
    return best


def select_strategy(dry_run: bool = False) -> dict:
    candidates = score_strategies()
    results = {}
    for symbol in SYMBOLS:
        results[symbol] = _select_for_symbol(symbol, candidates, dry_run)
    return results


def seed_initial_strategy() -> None:
    for symbol, seed in SEED_STRATEGIES.items():
        if get_active_strategy(symbol=symbol) is not None:
            print(f"[{symbol}] Active strategy already exists — skipping seed.")
            continue
        insert_active_strategy({
            **seed,
            "symbol": symbol,
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "backtest_id": None,
        })
        print(f"✓ Seeded: {seed['strategy_name']} {symbol} {seed['timeframe']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--seed", action="store_true", help="Seed initial strategies if none exist")
    args = parser.parse_args()

    if args.seed:
        seed_initial_strategy()

    select_strategy(dry_run=args.dry_run)
