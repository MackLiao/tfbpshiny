"""SQL query helpers for the Select Datasets module."""

from __future__ import annotations

from typing import Any

# TODO: open a tfbpapi issue to expose datacard field types (e.g. factor vs numeric)
# via VirtualDB so this hard-coding is no longer necessary.
# The datacard for hackett_2020 marks `time` as a factor, but the _meta view
# exposes it as a numeric column (DOUBLE). Override it here so the filter modal
# renders a sorted selectize instead of a slider.
# if the first element in the tuple key is an empty string, then the override
# will apply to all datasets that have that key
# Values are ("categorical", level_dtype) where level_dtype is "numeric" or "string".
# "numeric" means the category labels are numeric strings and should be sorted
# numerically; "string" means they should be sorted lexicographically.
FIELD_TYPE_OVERRIDES: dict[tuple[str, str], tuple[str, str]] = {
    ("hackett", "time"): ("categorical", "numeric"),
    ("", "temperature_celsius"): ("categorical", "string"),
}


def _build_where(
    filters: dict[str, Any] | None,
    params: dict[str, Any],
    prefix: str = "",
) -> str:
    """
    Build a WHERE clause string and populate ``params`` in-place.

    :param filters: Filter spec — ``{field: {"type": ..., "value": ...}}``.
    :param params: Dict to populate with bound parameter values.
    :param prefix: String prepended to every param name to avoid collisions
        when two datasets share the same field names in one query.
    :return: WHERE clause string (empty string if no filters).

    """
    clauses: list[str] = []

    for field, spec in (filters or {}).items():
        kind = spec["type"]
        val = spec["value"]
        p = f"{prefix}{field}" if prefix else field

        if kind == "categorical":
            placeholders = ", ".join(f"$cat_{p}_{i}" for i in range(len(val)))
            clauses.append(f"{field} IN ({placeholders})")
            for i, v in enumerate(val):
                params[f"cat_{p}_{i}"] = v
        elif kind == "numeric":
            lo, hi = val
            clauses.append(
                f"TRY_CAST({field} AS DOUBLE)" f" BETWEEN $num_{p}_lo AND $num_{p}_hi"
            )
            params[f"num_{p}_lo"] = lo
            params[f"num_{p}_hi"] = hi
        elif kind == "bool":
            clauses.append(f"{field} = $bool_{p}")
            params[f"bool_{p}"] = bool(val)

    return f" WHERE {' AND '.join(clauses)}" if clauses else ""


def metadata_query(
    db_name: str, filters: dict[str, Any] | None = None
) -> tuple[str, dict[str, Any]]:
    """
    Return ``(sql, params)`` for querying the dataset's meta view with optional filters.

    :param db_name: Dataset name (e.g. ``'harbison'``).
    :param filters: Active filters for this dataset — the ``filter_dict[db_name]``
        value. Structure:
        ``{field: {"type": "categorical"|"numeric"|"bool", "value": ...}}``.
    :return: ``(sql_string, params_dict)`` ready for ``vdb.query(sql, **params)``.

    """
    params: dict[str, Any] = {}
    where = _build_where(filters, params)
    return f"SELECT * FROM {db_name}_meta{where}", params


def sample_count_query(
    db_name: str,
    filters: dict[str, Any] | None = None,
    restrict_to_regulators: list[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Return ``(sql, params)`` for counting samples in a dataset's meta view.

    :param db_name: Dataset name.
    :param filters: Active filters for this dataset.
    :param restrict_to_regulators: If provided, only count rows whose
        ``regulator_locus_tag`` is in this list.
    :return: ``(sql_string, params_dict)`` — query returns one row with column ``n``.

    """
    params: dict[str, Any] = {}
    where = _build_where(filters, params)

    if restrict_to_regulators:
        placeholders = ", ".join(
            f"$reg_{db_name}_{i}" for i in range(len(restrict_to_regulators))
        )
        reg_clause = f"regulator_locus_tag IN ({placeholders})"
        for i, v in enumerate(restrict_to_regulators):
            params[f"reg_{db_name}_{i}"] = v
        where = f"{where} AND {reg_clause}" if where else f" WHERE {reg_clause}"

    return f"SELECT COUNT(sample_id) AS n FROM {db_name}_meta{where}", params


def regulator_locus_tags_query(
    db_name: str,
    filters: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Return ``(sql, params)`` for fetching distinct regulator locus tags.

    :param db_name: Dataset name.
    :param filters: Active filters for this dataset.
    :return: ``(sql_string, params_dict)`` — query returns rows with column
        ``regulator_locus_tag``.

    """
    params: dict[str, Any] = {}
    where = _build_where(filters, params)
    return (
        f"SELECT DISTINCT regulator_locus_tag FROM {db_name}_meta{where}",
        params,
    )


__all__ = [
    "FIELD_TYPE_OVERRIDES",
    "metadata_query",
    "sample_count_query",
    "regulator_locus_tags_query",
]
