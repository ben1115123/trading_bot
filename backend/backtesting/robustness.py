"""Robustness-validation layer on top of run_walk_forward/run_stability_map.

Four techniques, each answering a different overfitting question:
  - plateau/spike analysis  — is the best cell surrounded by other good
    cells (real edge) or isolated (noise that happened to backtest well)?
  - cluster summary         — same question, region-shaped: find contiguous
    blocks of decent cells and recommend the center of the largest one
    over the single best cell (which is more likely to be a lucky outlier).
  - bootstrap Monte Carlo   — resample the trade sequence to see the range
    of equity paths this edge could have produced, not just the one path
    that happened to occur.
  - permutation test        — destroy the price series' serial structure
    (Masters method) and check whether the strategy's result is actually
    distinguishable from running it on structureless noise.
"""
import math
import random

from backend.backtesting.engine import run_walk_forward

_TOTAL_ACCOUNT = 500.0
_RISK_PER_TRADE = 10.0
_RUIN_FRACTION = 0.5


def _percentile(sorted_vals: list, p: float) -> float:
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    k = (n - 1) * p
    f = int(k)
    c = min(f + 1, n - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def _grid_coords(stability_result: dict) -> dict:
    """Map each cell's params to its (i, j, k, ...) index tuple in the grid,
    and back. Returns {"coord_to_cell": {...}, "cell_to_coord": {...}}."""
    keys = stability_result["keys"]
    grid = stability_result["grid"]
    value_to_idx = [{v: i for i, v in enumerate(grid[k])} for k in keys]
    coord_to_cell, cell_to_coord = {}, {}
    for cell in stability_result["cells"]:
        coord = tuple(value_to_idx[a][cell["params"][keys[a]]] for a in range(len(keys)))
        coord_to_cell[coord] = cell
        cell_to_coord[id(cell)] = coord
    return {"keys": keys, "coord_to_cell": coord_to_cell, "cell_to_coord": cell_to_coord}


def _neighbors(coord: tuple, n_axes: int):
    for axis in range(n_axes):
        for delta in (-1, 1):
            n = list(coord)
            n[axis] += delta
            yield tuple(n)


def compute_plateau_metrics(stability_result: dict) -> dict:
    """For each cell, average PF of its orthogonal grid-neighbors (Von Neumann
    adjacency — one axis step at a time, not diagonal). best_plateau is the
    cell with the highest neighbor-avg (not necessarily the highest own PF).
    spike_flag is True if the single best-PF cell's neighbor-avg < 1.0 —
    i.e. the top result is an isolated spike, not surrounded by other
    decent parameter combinations (the overfit signature)."""
    idx = _grid_coords(stability_result)
    coord_to_cell, keys = idx["coord_to_cell"], idx["keys"]
    n_axes = len(keys)

    for coord, cell in coord_to_cell.items():
        neighbor_pfs = [
            coord_to_cell[n]["median_pf"]
            for n in _neighbors(coord, n_axes)
            if n in coord_to_cell
        ]
        cell["neighbor_avg_pf"] = round(sum(neighbor_pfs) / len(neighbor_pfs), 4) if neighbor_pfs else None
        cell["coord"] = coord

    cells = stability_result["cells"]
    best_cell = max(cells, key=lambda c: c["median_pf"])
    plateau_candidates = [c for c in cells if c["neighbor_avg_pf"] is not None]
    best_plateau = max(plateau_candidates, key=lambda c: c["neighbor_avg_pf"]) if plateau_candidates else None
    spike_flag = best_cell["neighbor_avg_pf"] is not None and best_cell["neighbor_avg_pf"] < 1.0

    return {"best_cell": best_cell, "best_plateau": best_plateau, "spike_flag": spike_flag}


def find_clusters(stability_result: dict, threshold: float = 1.1) -> list:
    """Contiguous regions of cells with median_pf >= threshold (orthogonal
    adjacency, BFS flood-fill — no ML clustering). Each region reports size,
    center params (the qualifying cell closest to the region's index
    centroid), and the center cell itself (caller can MC it for
    risk-of-ruin). Sorted largest region first."""
    idx = _grid_coords(stability_result)
    coord_to_cell, keys = idx["coord_to_cell"], idx["keys"]
    n_axes = len(keys)

    qualifying = {c for c, cell in coord_to_cell.items() if cell["median_pf"] >= threshold}
    visited = set()
    clusters = []

    for start in qualifying:
        if start in visited:
            continue
        stack, region = [start], set()
        while stack:
            cur = stack.pop()
            if cur in visited:
                continue
            visited.add(cur)
            region.add(cur)
            for n in _neighbors(cur, n_axes):
                if n in qualifying and n not in visited:
                    stack.append(n)

        centroid = [sum(c[a] for c in region) / len(region) for a in range(n_axes)]
        center_coord = min(region, key=lambda c: sum((c[a] - centroid[a]) ** 2 for a in range(n_axes)))
        center_cell = coord_to_cell[center_coord]
        clusters.append({
            "size":          len(region),
            "center_params": center_cell["params"],
            "center_cell":   center_cell,
            "cells":         [coord_to_cell[c] for c in region],
        })

    clusters.sort(key=lambda r: -r["size"])
    return clusters


def bootstrap_mc(trades: list, n_iter: int = 1000, account: float = _TOTAL_ACCOUNT,
                 ruin_fraction: float = _RUIN_FRACTION, seed: int = None) -> dict:
    """Bootstrap resampling (with replacement) of the out-of-sample trade
    P&L list — the standard Monte Carlo technique for equity-path risk
    (Vince/van Tharp style). Each of n_iter synthetic paths draws len(trades)
    P&Ls with replacement, in random order, and walks a $account equity
    curve from that. Reports P&L and max-drawdown distributions, plus
    risk-of-ruin: % of paths whose max dollar drawdown exceeds
    ruin_fraction * account."""
    pnls = [t["pnl"] for t in trades]
    n = len(pnls)
    if n == 0:
        return {"error": "no trades to resample"}

    rng = random.Random(seed)
    ruin_threshold = account * ruin_fraction
    total_pnls, max_dds = [], []
    ruin_count = 0

    for _ in range(n_iter):
        sample = [rng.choice(pnls) for _ in range(n)]
        equity = account
        peak = account
        max_dd = 0.0
        for p in sample:
            equity += p
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd
        total_pnls.append(sum(sample))
        max_dds.append(max_dd)
        if max_dd > ruin_threshold:
            ruin_count += 1

    total_pnls.sort()
    max_dds.sort()

    return {
        "n_trades": n, "n_iter": n_iter, "account": account, "risk_per_trade": _RISK_PER_TRADE,
        "pnl_p5":  _percentile(total_pnls, 0.05), "pnl_p25": _percentile(total_pnls, 0.25),
        "pnl_median": _percentile(total_pnls, 0.50),
        "pnl_p75": _percentile(total_pnls, 0.75), "pnl_p95": _percentile(total_pnls, 0.95),
        "dd_p5":   _percentile(max_dds, 0.05),  "dd_p25":  _percentile(max_dds, 0.25),
        "dd_median": _percentile(max_dds, 0.50),
        "dd_p75":  _percentile(max_dds, 0.75),  "dd_p95":  _percentile(max_dds, 0.95),
        "risk_of_ruin_pct": round(100 * ruin_count / n_iter, 2),
        "ruin_threshold_dollars": ruin_threshold,
    }


def _shuffle_log_returns(candles: list, rng: random.Random) -> list:
    """Masters permutation: shuffle the bar-to-bar log returns (destroys
    serial/trend structure, preserves the marginal return distribution —
    same volatility profile, different sequence), then rebuild a synthetic
    close series by cumulative product from the original starting price.
    Synthetic O/H/L are reconstructed by applying each original bar's
    high/low/open-to-close ratio to the new synthetic close, so intrabar
    shape is preserved without needing separate permutation logic for
    each price field."""
    n = len(candles)
    closes = [c["close"] for c in candles]
    log_rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, n)]
    shuffled = log_rets[:]
    rng.shuffle(shuffled)

    synth_close = [0.0] * n
    synth_close[0] = closes[0]
    for i in range(1, n):
        synth_close[i] = synth_close[i - 1] * math.exp(shuffled[i - 1])

    synth_candles = []
    for i, c in enumerate(candles):
        orig_close = c["close"] or 1.0
        sc = synth_close[i]
        synth_candles.append({
            "time":  c["time"],
            "open":  sc * (c["open"]  / orig_close),
            "high":  sc * (c["high"]  / orig_close),
            "low":   sc * (c["low"]   / orig_close),
            "close": sc,
        })
    return synth_candles


def permutation_test(strategy_class, candles: list, symbol: str, params: dict,
                     n_iter: int = 200, max_hold_candles: int = None,
                     session_filter: str = None, seed: int = None) -> dict:
    """Masters-method permutation test. Real result's median PF (from a real
    walk-forward on the real candles) is compared against n_iter walk-forward
    runs on log-return-shuffled synthetic candles (same params, same
    strategy). Edge is only considered real if the real result beats
    >95% of the synthetic (noise) distribution."""
    real_wf = run_walk_forward(strategy_class, candles, symbol, params=params,
                               max_hold_candles=max_hold_candles, session_filter=session_filter)
    real_pf = real_wf["median_pf"]

    rng = random.Random(seed)
    synthetic_pfs = []
    for _ in range(n_iter):
        synth_candles = _shuffle_log_returns(candles, rng)
        wf = run_walk_forward(strategy_class, synth_candles, symbol, params=params,
                              max_hold_candles=max_hold_candles, session_filter=session_filter)
        synthetic_pfs.append(wf["median_pf"])

    synthetic_sorted = sorted(synthetic_pfs)
    rank = sum(1 for x in synthetic_sorted if x <= real_pf)
    percentile = round(100 * rank / len(synthetic_sorted), 2) if synthetic_sorted else 0.0

    return {
        "real_median_pf":       real_pf,
        "real_verdict":         real_wf["verdict"],
        "n_iter":               n_iter,
        "synthetic_median_pfs": synthetic_pfs,
        "synthetic_pf_median":  _percentile(synthetic_sorted, 0.50),
        "percentile":           percentile,
        "edge_confirmed":       percentile > 95,
    }
