"""The canonical predicate for "which paper_trades rows count".

Zero imports beyond the two model-version constants — a leaf, like symbols.py,
engine_version.py, instrument_limits.py, spread_model.py and paper_model.py.

WHY A PREDICATE HELPER RATHER THAN A QUERY LAYER: the recurring defect in this
codebase is the PREDICATE, not the aggregation. Finding 17 (557 shadow rows
counted as real) and model-version mixing are both "wrong rows selected"; no
aggregation bug has ever been found in the dashboard pages. So the thing that
must live in exactly one place is the definition of a countable row, not the
SELECT around it.

Twelve query sites across four dashboard pages compose this fragment. They
stay as raw SQL deliberately — three of them (a dynamic UI filter bag, an
equity-curve series, and a CTE joined against trades + active_strategy) cannot
be expressed by any reasonable shared function signature without turning it
into a query builder with six optional parameters.

SHADOW ROWS ARE NOT NOISE. They are counterfactuals for signals a filter
DELIBERATELY BLOCKED — the only measurement of whether a blocking filter
actually helps. They must never be deleted or stopped, only kept separable.
Hence include_shadow is tri-state rather than a boolean: exclude (default),
include, or "only" for the counterfactual view.
"""

from paper_model import CURRENT_PAPER_MODEL

# signal values carry a PAPER_ or SHADOW_ prefix; see live_signal_loop.py:749
_SHADOW_PREFIX = "SHADOW%"

# ---------------------------------------------------------------------------
# Outcome vocabulary
#
# Until paper-v2 a row was WIN, LOSS or PENDING, and PENDING meant two
# different things that nothing could tell apart: "not resolved yet" and
# "will never resolve". paper-v2 splits the second case into three terminal
# outcomes, so `outcome != 'PENDING'` no longer means "has a P&L" and
# `total - wins - losses` no longer means "pending".
#
# The completeness assumption is the point. Twelve query sites forgot to
# exclude shadow rows (finding 17) because the predicate lived nowhere; the
# same shape applies here, so the vocabulary lives here too rather than as a
# literal in each SELECT.
# ---------------------------------------------------------------------------

# Carry a simulated_pnl. The only rows any statistic may count.
RESOLVED_OUTCOMES = ("WIN", "LOSS")

# Terminated without a P&L — the row is closed, and simulated_pnl stays NULL
# so a mistaken SUM contributes nothing rather than a phantom break-even.
#   REFUSED     the row itself is unusable: malformed bracket, NULL timeframe,
#               unparseable candle_time. No future data can fix it.
#   EXPIRED     aged past the resolution horizon. A relevance judgement.
#   NO_HISTORY  the data source provably cannot cover the signal's window —
#               its earliest available candle postdates the signal, and the
#               window only rolls forward.
UNRESOLVABLE_OUTCOMES = ("REFUSED", "EXPIRED", "NO_HISTORY")

PENDING_OUTCOME = "PENDING"

TERMINAL_OUTCOMES = RESOLVED_OUTCOMES + UNRESOLVABLE_OUTCOMES


def resolved_outcomes(alias: str = "") -> tuple:
    """Return (sql_fragment, params) restricting to rows that carry a P&L.

    Use this anywhere a query previously said `outcome != 'PENDING'`, or
    counted `COUNT(*)` on the assumption that every non-pending row resolved.
    Composes with paper_where():

        frag, params   = paper_where()
        rfrag, rparams = resolved_outcomes()
        cur.execute(f"SELECT ... WHERE 1=1 {frag} {rfrag}", (*params, *rparams))
    """
    p = f"{alias}." if alias else ""
    placeholders = ",".join("?" * len(RESOLVED_OUTCOMES))
    return f" AND {p}outcome IN ({placeholders})", list(RESOLVED_OUTCOMES)


def unresolvable_count_sql(alias: str = "") -> str:
    """SQL expression counting rows terminated without a P&L.

    Same contract as excluded_count_sql: a decision surface must SAY what it
    dropped. Nine rows silently vanishing from a total is indistinguishable
    from data loss — and per finding 22 those nine are the evidence for the
    defect that created this vocabulary, so they must stay visible.
    """
    p = f"{alias}." if alias else ""
    quoted = ",".join(f"'{o}'" for o in UNRESOLVABLE_OUTCOMES)
    return f"SUM(CASE WHEN {p}outcome IN ({quoted}) THEN 1 ELSE 0 END)"


def paper_where(include_shadow: bool | str = False,
                paper_model: str | None = CURRENT_PAPER_MODEL,
                alias: str = "") -> tuple:
    """Return (sql_fragment, params) for the canonical paper-row predicate.

    The fragment always begins with ' AND ' (or is empty), so callers append it
    to a query that already has a WHERE — use `WHERE 1=1` when there is no
    other condition:

        frag, params = paper_where()
        cur.execute(f"SELECT ... FROM paper_trades WHERE 1=1 {frag} GROUP BY ...", params)

    include_shadow:
        False  (default) real paper trades only — what every statistic means
        True             everything, real and counterfactual together
        "only"           counterfactuals only (10_context's shadow panel)

    paper_model:
        a version string  restrict to one resolver model (decision surfaces)
        None              every model (inspection surfaces — label the column,
                          because rows from different models are NOT comparable)

    alias: table alias when the query uses one, e.g. alias="p" -> "p.signal".
    """
    p = f"{alias}." if alias else ""
    frag, params = "", []

    if include_shadow is False:
        frag += f" AND {p}signal NOT LIKE ?"
        params.append(_SHADOW_PREFIX)
    elif include_shadow == "only":
        frag += f" AND {p}signal LIKE ?"
        params.append(_SHADOW_PREFIX)
    elif include_shadow is not True:
        raise ValueError(
            f"include_shadow must be False, True or 'only', got {include_shadow!r}"
        )

    if paper_model is not None:
        frag += f" AND {p}paper_model = ?"
        params.append(paper_model)

    return frag, params


def excluded_count_sql(alias: str = "") -> str:
    """SQL expression counting rows the default predicate would drop.

    For decision surfaces, which must SAY what they filtered rather than
    silently shrink — an unexplained smaller number is indistinguishable from
    a data loss.
    """
    p = f"{alias}." if alias else ""
    return (f"SUM(CASE WHEN {p}signal LIKE '{_SHADOW_PREFIX}' "
            f"OR {p}paper_model != '{CURRENT_PAPER_MODEL}' THEN 1 ELSE 0 END)")
