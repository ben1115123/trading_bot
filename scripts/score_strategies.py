#!/usr/bin/env python3
"""
Score all backtest results based on eligibility rules and scoring formula.

Eligibility rules:
  - total_trades >= 10 for 'swing' strategies (or NULL/missing type defaults to 'swing')
  - total_trades >= 5 for 'daytrading' strategies
  - total_profit > 0
  - win_rate > 0.5
  - strategy beat benchmark: total_profit / 1000 > benchmark_return

Scoring formula (exact weights):
  score = win_rate * 0.4 + (total_profit / 1000) * 0.3 +
          (1 - max_drawdown / 1000) * 0.2 + sharpe_ratio * 0.1
  Clamped to [0.0, 1.0]
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.models import get_backtest_results


INITIAL_CAPITAL = 1000.0


def score_strategies():
    """
    Read all backtest_results, apply eligibility rules, calculate scores.

    Returns:
        list: Dicts with all original backtest_result fields + 'score' key,
              sorted by score descending. Only eligible runs included.
    """
    results = get_backtest_results()

    if not results:
        return []

    eligible = []

    for row in results:
        # Default strategy_type to 'swing' if NULL or missing
        strategy_type = row.get('strategy_type') or 'swing'

        # Rule 1: min total_trades
        min_trades = 10 if strategy_type == 'swing' else 5
        total_trades = row.get('total_trades') or 0
        if total_trades < min_trades:
            continue

        # Rule 2: profit > 0
        total_profit = row.get('total_profit') or 0
        if total_profit <= 0:
            continue

        # Rule 3: win_rate > 0.5
        win_rate = row.get('win_rate') or 0
        if win_rate <= 0.5:
            continue

        # Rule 4: beat benchmark
        benchmark_return = row.get('benchmark_return')
        if benchmark_return is not None:
            profit_ratio = total_profit / INITIAL_CAPITAL
            if profit_ratio <= benchmark_return:
                continue

        # All checks passed, calculate score
        win_rate_score = win_rate or 0.0
        profit_score = (total_profit / 1000.0) if total_profit else 0.0
        max_drawdown = row.get('max_drawdown') or 0.0
        drawdown_score = 1.0 - (max_drawdown / 1000.0)
        sharpe_score = row.get('sharpe_ratio') or 0.0

        score = (
            win_rate_score * 0.4 +
            profit_score * 0.3 +
            drawdown_score * 0.2 +
            sharpe_score * 0.1
        )

        # Clamp score to [0.0, 1.0]
        score = max(0.0, min(1.0, score))

        # Add score to row and append
        row_with_score = dict(row)
        row_with_score['score'] = score
        eligible.append(row_with_score)

    # Sort by score descending
    eligible.sort(key=lambda x: x['score'], reverse=True)

    return eligible


def print_table(scored_results):
    """
    Print a ranked table with score results.
    Format: rank | id | strategy_name | symbol | timeframe | type | trades | win% | profit | score
    """
    if not scored_results:
        print("No eligible strategies found.")
        return

    print("\n" + "=" * 120)
    print("STRATEGY SCORES")
    print("=" * 120)
    print(f"{'Rank':<5} {'ID':<6} {'Strategy':<20} {'Symbol':<8} {'TF':<8} {'Type':<12} {'Trades':<8} {'Win%':<8} {'Profit':<10} {'Score':<8}")
    print("-" * 120)

    for rank, result in enumerate(scored_results, 1):
        strategy_name = str(result.get('strategy_name', 'N/A'))[:20]
        symbol = str(result.get('symbol', 'N/A'))[:8]
        timeframe = str(result.get('timeframe', 'N/A'))[:8]
        strategy_type = str(result.get('strategy_type') or 'swing')[:12]
        total_trades = result.get('total_trades') or 0
        win_rate = result.get('win_rate') or 0.0
        total_profit = result.get('total_profit') or 0.0
        score = result.get('score', 0.0)
        row_id = result.get('id', 'N/A')

        win_pct = f"{win_rate * 100:.1f}%"

        print(f"{rank:<5} {row_id:<6} {strategy_name:<20} {symbol:<8} {timeframe:<8} {strategy_type:<12} {total_trades:<8} {win_pct:<8} {total_profit:<10.2f} {score:<8.4f}")

    print("=" * 120)


def print_top_per_symbol(scored_results):
    """
    Print the top 3 strategies per symbol.
    """
    if not scored_results:
        return

    # Group by symbol
    by_symbol = {}
    for result in scored_results:
        symbol = result.get('symbol', 'UNKNOWN')
        if symbol not in by_symbol:
            by_symbol[symbol] = []
        by_symbol[symbol].append(result)

    print("\n" + "=" * 120)
    print("TOP 3 PER SYMBOL")
    print("=" * 120)

    for symbol in sorted(by_symbol.keys()):
        results = by_symbol[symbol]
        print(f"\n{symbol}:")
        print(f"  {'Rank':<6} {'Strategy':<20} {'TF':<8} {'Type':<12} {'Trades':<8} {'Win%':<8} {'Profit':<10} {'Score':<8}")
        print(f"  {'-' * 100}")

        for rank, result in enumerate(results[:3], 1):
            strategy_name = str(result.get('strategy_name', 'N/A'))[:20]
            timeframe = str(result.get('timeframe', 'N/A'))[:8]
            strategy_type = str(result.get('strategy_type') or 'swing')[:12]
            total_trades = result.get('total_trades') or 0
            win_rate = result.get('win_rate') or 0.0
            total_profit = result.get('total_profit') or 0.0
            score = result.get('score', 0.0)

            win_pct = f"{win_rate * 100:.1f}%"

            print(f"  {rank:<6} {strategy_name:<20} {timeframe:<8} {strategy_type:<12} {total_trades:<8} {win_pct:<8} {total_profit:<10.2f} {score:<8.4f}")

    print("\n" + "=" * 120)


if __name__ == "__main__":
    scored_results = score_strategies()

    if scored_results:
        print_table(scored_results)
        print_top_per_symbol(scored_results)
        print(f"\nTotal eligible strategies: {len(scored_results)}")
    else:
        print("No eligible strategies found.")
