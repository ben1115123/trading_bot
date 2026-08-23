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
from engine_version import CURRENT_ENGINE_VERSION

_TOTAL_ACCOUNT = 500.0
_RISK_PER_TRADE = 10.0
_RUIN_FRACTION = 0.5

# Sentinel distinguishing "the caller did not think about the seed" from "the
# caller deliberately chose an unseeded run". Those are NOT the same thing and
# a plain `seed=None` default cannot tell them apart — which is exactly how
# every permutation and Monte Carlo figure in this project came to be
# unreproducible while CLAUDE.md recorded `seed=42` for them.
_SEED_UNSET = object()


class UnseededRunError(RuntimeError):
    """A stochastic stage was called without an explicit seed decision.

    WHY THIS RAISES INSTEAD OF DEFAULTING. Measured 2026-08-23: two runs of the
    identical gauntlet, identical candles, identical params, 20 minutes apart,
    gave permutation percentile 98.5 vs 99.0 and moved all five Monte Carlo
    risk-of-ruin cells (66.8->68.6, 71.4->71.8, 74.9->77.5, 77.5->79.1,
    85.1->86.1). Every such figure ever quoted in this project is a number that
    cannot be produced a second time.

    That is worse than it sounds, because these rows ARE auditable from their
    own contents — the permutation row stores all 200 synthetic medians and
    recomputing the percentile from them reproduces the stored value exactly.
    So the defect is invisible to the obvious check: the row is internally
    consistent and externally unrepeatable.

    `seed=None` remains legal and means "deliberately nondeterministic". It is
    STORED as None, so a reader can see it, and the result carries
    `reproducible: False`. What is illegal is not deciding.
    """


def _resolve_seed(seed, fn: str):
    if seed is _SEED_UNSET:
        raise UnseededRunError(
            f"{fn} requires an explicit seed. Pass an int for a reproducible run, "
            f"or seed=None to declare the run deliberately nondeterministic "
            f"(which is stored as None and marks the result reproducible=False). "
            f"Refusing to pick one silently — an unrecorded seed is how every "
            f"permutation and Monte Carlo figure in this project became "
            f"unrepeatable while the docs claimed seed=42.")
    return seed


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


class UnstampedTradesError(RuntimeError):
    """bootstrap_mc was handed a trade list with no declared engine_version.

    This function is the ONE stage of the gauntlet that never calls the engine —
    it resamples a P&L list. So it will happily bootstrap trades produced by any
    model, and insert_walkforward_run then stamps the row with the CURRENT
    engine_version by default. A pre-parity trade list could therefore be
    resampled and persisted as parity-v2 evidence.

    Until 2026-08-22 that was prevented only by call-site convention: the CLI
    always happened to pass a freshly-computed walk-forward result. This project
    has been bitten four times by conventions that held until they didn't (see
    CLAUDE.md, Unverified Controls), so provenance is now REQUIRED rather than
    assumed. The caller must declare which model produced the trades, and the
    only honest source for that value is the engine result dict the trades came
    from (`wf["engine_version"]`).
    """


def bootstrap_mc(trades: list, n_iter: int = 1000, account: float = _TOTAL_ACCOUNT,
                 ruin_fraction: float = _RUIN_FRACTION, seed=_SEED_UNSET,
                 engine_version: str = None) -> dict:
    """Bootstrap resampling (with replacement) of the out-of-sample trade
    P&L list — the standard Monte Carlo technique for equity-path risk
    (Vince/van Tharp style). Each of n_iter synthetic paths draws len(trades)
    P&Ls with replacement, in random order, and walks a $account equity
    curve from that. Reports P&L and max-drawdown distributions, plus
    risk-of-ruin: % of paths whose max dollar drawdown exceeds
    ruin_fraction * account."""
    # Provenance gate. Deliberately raises rather than defaulting: a silent
    # default here is exactly the laundering path described in
    # UnstampedTradesError, and a default that is usually right is the kind of
    # thing that stays wrong for months.
    if not engine_version:
        raise UnstampedTradesError(
            "bootstrap_mc requires engine_version — pass the value from the engine "
            "result the trades came from, e.g. bootstrap_mc(wf['combined_trades'], "
            "engine_version=wf['engine_version']). Refusing to assume "
            f"{CURRENT_ENGINE_VERSION!r}.")
    if engine_version != CURRENT_ENGINE_VERSION:
        raise UnstampedTradesError(
            f"bootstrap_mc got trades produced under engine_version "
            f"{engine_version!r}, but the current model is "
            f"{CURRENT_ENGINE_VERSION!r}. Resampling across trade models produces "
            f"a distribution that describes neither. Regenerate the trades.")

    # Seed gate. Same reasoning as the provenance gate above: refusing beats a
    # default that is usually fine, because a default that is usually fine is
    # the kind of thing that stays wrong for months. See UnseededRunError.
    seed = _resolve_seed(seed, "bootstrap_mc")

    pnls = [t["pnl"] for t in trades]
    n = len(pnls)
    if n == 0:
        return {"error": "no trades to resample", "engine_version": engine_version,
                "seed": seed, "reproducible": seed is not None}

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
        "engine_version": engine_version,
        # The seed travels WITH the numbers it produced. A distribution whose
        # seed lives only in a shell-history line is not reproducible in any
        # sense that survives the session.
        "seed": seed, "reproducible": seed is not None,
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
                     session_filter: str = None, seed=_SEED_UNSET) -> dict:
    """Masters-method permutation test. Real result's median PF (from a real
    walk-forward on the real candles) is compared against n_iter walk-forward
    runs on log-return-shuffled synthetic candles (same params, same
    strategy). Edge is only considered real if the real result beats
    >95% of the synthetic (noise) distribution."""
    # Seed gate BEFORE any work — a run that will not be reproducible should
    # fail in the first millisecond, not after 200 walk-forwards. See
    # UnseededRunError.
    seed = _resolve_seed(seed, "permutation_test")

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
        # The seed that generated `synthetic_median_pfs`. Without it the row is
        # internally consistent (the percentile recomputes from the stored
        # medians exactly) and externally unrepeatable — the failure mode that
        # hid this for months.
        "seed":                 seed,
        "reproducible":         seed is not None,
        # Provenance rides with the result, same contract as bootstrap_mc.
        # Taken from the real run rather than the constant, so a stale engine
        # import cannot silently relabel it.
        "engine_version":       real_wf.get("engine_version"),
        "spread_model":         real_wf.get("spread_model"),
        "spread_table_sha":     real_wf.get("spread_table_sha"),
        # p-value resolution is 1/(n_iter+1); a percentile claim finer than that
        # is not expressible. At n_iter=200 the floor is p=0.005; at 50, p=0.020.
        "p_value_floor":        round(1.0 / (n_iter + 1), 5),
    }
