#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.models import insert_active_strategy, get_active_strategy, get_active_strategies
from scripts.score_strategies import score_strategies

SYMBOLS = ["BTC", "US100", "US500"]

STRATEGY_BLOCKLIST = {
    # US100 — no live edge demonstrated across any strategy
    ("US100", "HOUR", "stoch_rsi"),
    ("US100", "HOUR", "rsi"),
    ("US100", "HOUR", "williams_r"),
    ("US100", "HOUR", "macd_rsi"),
    ("US100", "HOUR", "rsi_divergence"),
    ("US100", "HOUR", "swiftalgo"),
    ("US100", "HOUR", "smc"),
    ("US100", "HOUR", "ema_pullback"),            # paper only, not for live
    ("US100", "HOUR", "ny_session_momentum"),
    ("US100", "HOUR", "silver_bullet"),
    ("US100", "HOUR", "london_breakout"),
    ("US100", "HOUR", "rsi_divergence_session"),
    ("US100", "15MIN", "smc"),
    ("US100", "15MIN", "stoch_rsi"),
    ("US100", "15MIN", "williams_r"),
    ("US100", "15MIN", "ny_session_momentum"),
    ("US100", "15MIN", "silver_bullet"),
    ("US100", "15MIN", "london_breakout"),
    ("US100", "15MIN", "rsi_divergence_session"),
    ("US100", "15MIN", "vwap_mean_reversion"),
    ("US100", "15MIN", "fvg"),
    ("US100", "5MIN", "stoch_rsi"),

    # BTC — two consecutive strategy failures; block all until redesign
    ("BTC",   "HOUR", "stoch_rsi"),
    ("BTC",   "HOUR", "rsi_divergence"),
    ("BTC",   "HOUR", "vwap_ema"),
    ("BTC",   "HOUR", "rsi"),
    ("BTC",   "HOUR", "williams_r"),
    ("BTC",   "HOUR", "macd_rsi"),

    # US500 HOUR — failed backtests / not validated
    ("US500", "HOUR", "stoch_rsi"),               # deactivated 2026-08-13 (id 2) — cron must not re-promote
    ("US500", "HOUR", "rsi"),
    ("US500", "HOUR", "macd_rsi"),
    ("US500", "HOUR", "vwap_ema"),
    ("US500", "HOUR", "ema_ribbon"),
    ("US500", "HOUR", "rsi_divergence"),
    ("US500", "HOUR", "orb"),
    ("US500", "HOUR", "ichimoku"),
    ("US500", "HOUR", "keltner"),
    ("US500", "HOUR", "ema_cross_volume"),
    ("US500", "HOUR", "vwap_mean_reversion"),
    ("US500", "HOUR", "connors_rsi2"),
    ("US500", "HOUR", "bb_squeeze"),
    ("US500", "HOUR", "supertrend"),
    ("US500", "HOUR", "london_breakout"),
    ("US500", "HOUR", "silver_bullet"),
    ("US500", "HOUR", "ny_session_momentum"),
    ("US500", "HOUR", "rsi_divergence_session"),
    # US500 15MIN — confirmed failures or manual deactivations
    ("US500", "15MIN", "fvg"),                    # 30.6% WR, deactivated
    ("US500", "15MIN", "smc"),                    # 24% WR, deactivated
    ("US500", "15MIN", "london_breakout"),        # negative P&L
    ("US500", "15MIN", "silver_bullet"),          # negative all combos
    ("US500", "15MIN", "vwap_mean_reversion"),    # PF 1.07
    ("US500", "15MIN", "rsi_divergence_session"), # PF 1.09
    ("US500", "15MIN", "ny_session_momentum"),    # PF 1.21 below bar

    # EURUSD HOUR — strategies that failed
    ("EURUSD", "HOUR", "stoch_rsi"),
    ("EURUSD", "HOUR", "williams_r"),
    ("EURUSD", "HOUR", "rsi"),
    ("EURUSD", "HOUR", "macd_rsi"),
    ("EURUSD", "HOUR", "rsi_divergence"),
    ("EURUSD", "HOUR", "vwap_ema"),
    ("EURUSD", "HOUR", "ema_ribbon"),
    ("EURUSD", "HOUR", "orb"),
    ("EURUSD", "HOUR", "ichimoku"),
    ("EURUSD", "HOUR", "keltner"),
    ("EURUSD", "HOUR", "ema_cross_volume"),
    ("EURUSD", "HOUR", "vwap_mean_reversion"),
    ("EURUSD", "HOUR", "connors_rsi2"),
    ("EURUSD", "HOUR", "bb_squeeze"),
    ("EURUSD", "HOUR", "supertrend"),
    ("EURUSD", "HOUR", "fvg"),
    ("EURUSD", "HOUR", "smc"),
    ("EURUSD", "HOUR", "silver_bullet"),
    # EURUSD 15MIN — failed / below promotion bar
    ("EURUSD", "15MIN", "london_breakout"),       # 35% WR, negative P&L, deactivated
    ("EURUSD", "15MIN", "silver_bullet"),         # 14 trades only
    ("EURUSD", "15MIN", "vwap_mean_reversion"),   # spread kills it
    ("EURUSD", "15MIN", "rsi_divergence_session"),# PF 1.10
    ("EURUSD", "15MIN", "smc"),
    ("EURUSD", "15MIN", "fvg"),

    # DAX HOUR — everything failed
    ("DAX", "HOUR", "williams_r"),       # deactivated
    ("DAX", "HOUR", "macd_rsi"),         # deactivated
    ("DAX", "HOUR", "rsi"),              # deactivated
    ("DAX", "HOUR", "stoch_rsi"),
    ("DAX", "HOUR", "rsi_divergence"),
    ("DAX", "HOUR", "vwap_ema"),
    ("DAX", "HOUR", "ema_ribbon"),
    ("DAX", "HOUR", "orb"),
    ("DAX", "HOUR", "ichimoku"),
    ("DAX", "HOUR", "keltner"),
    ("DAX", "HOUR", "ema_cross_volume"),
    ("DAX", "HOUR", "vwap_mean_reversion"),
    ("DAX", "HOUR", "connors_rsi2"),
    ("DAX", "HOUR", "bb_squeeze"),
    ("DAX", "HOUR", "supertrend"),
    ("DAX", "HOUR", "fvg"),
    ("DAX", "HOUR", "smc"),
    ("DAX", "HOUR", "silver_bullet"),
    ("DAX", "HOUR", "ny_session_momentum"),
    ("DAX", "HOUR", "london_breakout"),
    ("DAX", "HOUR", "ema_pullback"),
    ("DAX", "HOUR", "rsi_divergence_session"),
    # DAX 15MIN — everything failed
    ("DAX", "15MIN", "stoch_rsi"),
    ("DAX", "15MIN", "williams_r"),      # negative P&L
    ("DAX", "15MIN", "ema_pullback"),    # catastrophic
    ("DAX", "15MIN", "ny_session_momentum"), # catastrophic
    ("DAX", "15MIN", "smc"),
    ("DAX", "15MIN", "fvg"),
    ("DAX", "15MIN", "silver_bullet"),
    ("DAX", "15MIN", "london_breakout"),
    ("DAX", "15MIN", "rsi_divergence_session"),
    ("DAX", "15MIN", "vwap_mean_reversion"),

    # GBPUSD 15MIN — only ema_pullback/williams_r showed edge (2026-06-14 sweep)
    ("GBPUSD", "15MIN", "stoch_rsi"),
    ("GBPUSD", "15MIN", "supertrend"),
    ("GBPUSD", "15MIN", "ny_session_momentum"),
    ("GBPUSD", "HOUR", "stoch_rsi"),
    ("GBPUSD", "HOUR", "supertrend"),

    # USDJPY — all strategies failed 2026-06-14 sweep
    ("USDJPY", "15MIN", "stoch_rsi"),
    ("USDJPY", "15MIN", "supertrend"),
    ("USDJPY", "15MIN", "williams_r"),
    ("USDJPY", "15MIN", "ema_pullback"),
    ("USDJPY", "15MIN", "ny_session_momentum"),
    ("USDJPY", "HOUR", "stoch_rsi"),
    ("USDJPY", "HOUR", "williams_r"),
    ("USDJPY", "HOUR", "supertrend"),
}

# Symbols blocked entirely — cron will not promote any strategy
# US100 added 2026-08-15: STRATEGY_BLOCKLIST is an allowlist by omission —
#   ("US100","HOUR","supertrend") was never listed, so cron promoted it live
#   unreviewed on 2026-06-16 despite CLAUDE.md claiming all US100 strategies
#   were blocked since 2026-06-12. Symbol-wide block makes that claim true.
# US500 added 2026-08-15: US500 HOUR now has no active row (id 2 deactivated
#   2026-08-13), which arms select_strategy's first-activation branch — it has
#   no score threshold and would promote a paper strategy straight to live.
#   Five US500 HOUR names remain unblocked by tuple (williams_r,
#   stoch_rsi_confluence, ema_pullback, fvg, smc); enumerating them is the same
#   omission trap. See docs/SESSION_20260812_FINDINGS.md findings 5 and 6.
SYMBOL_BLOCKLIST = {"BTC", "US100", "US500"}

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
    # TODO: enable 5MIN when signal loop handles multiple timeframes
    sym_candidates = [c for c in candidates if c["symbol"] == symbol and c.get("timeframe") == "HOUR"]

    allowed = []
    for c in sym_candidates:
        key = (symbol, c.get("timeframe", "HOUR"), c["strategy_name"])
        if key in STRATEGY_BLOCKLIST:
            print(f"[select] {symbol} {c['strategy_name']} blocklisted — skipping promotion")
        else:
            allowed.append(c)
    sym_candidates = allowed

    if not sym_candidates:
        print(f"[{symbol}] No eligible strategies found.")
        return None

    best = sym_candidates[0]  # already sorted score DESC
    best_score = best["score"]
    current = get_active_strategy(symbol=symbol, timeframe="HOUR")

    if current is None:
        reason = f"No active strategy for {symbol} — first activation"
    elif (current["strategy_name"] == best["strategy_name"]
          and current["timeframe"] == best["timeframe"]):
        print(f"[{symbol}] Already active: {current['strategy_name']} "
              f"{current['timeframe']} (score {current['score']:.3f})")
        return best
    elif best_score <= (current["score"] or 0) + 0.05:
        print(f"[{symbol}] No switch — threshold not met: "
              f"{current['score']:.3f} → {best_score:.3f} "
              f"(need > {(current['score'] or 0) + 0.05:.3f})")
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
        if symbol in SYMBOL_BLOCKLIST:
            print(f"[SELECT] {symbol} is symbol-blocklisted — skipping all promotions")
            results[symbol] = None
            continue
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
