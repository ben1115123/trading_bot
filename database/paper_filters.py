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
