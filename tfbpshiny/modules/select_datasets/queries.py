"""SQL query helpers for the Select Datasets module."""

from __future__ import annotations

from typing import Any

# TODO: open a labretriever issue to expose datacard field types (e.g. factor vs numeric)
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
        p = (f"{prefix}{field}" if prefix else field).replace(" ", "_")

        if kind == "categorical":
            placeholders = ", ".join(f"$cat_{p}_{i}" for i in range(len(val)))
            clauses.append(f'"{field}" IN ({placeholders})')
            for i, v in enumerate(val):
                params[f"cat_{p}_{i}"] = v
        elif kind == "numeric":
            lo, hi = val
            clauses.append(
                f'TRY_CAST("{field}" AS DOUBLE)' f" BETWEEN $num_{p}_lo AND $num_{p}_hi"
            )
            params[f"num_{p}_lo"] = lo
            params[f"num_{p}_hi"] = hi
        elif kind == "bool":
            clauses.append(f'"{field}" = $bool_{p}')
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


def regulator_breakdown_query(
    db_name: str,
    candidate_cols: list[str],
    filters: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Return ``(sql, params)`` for a single query that counts multi-sample regulators and
    distinct values per candidate column in one pass.

    The result is a single row with:

    - ``n_multi`` — number of regulators that appear in more than one sample
    - One column per entry in ``candidate_cols`` — the number of distinct
      values for that column across multi-sample regulators only

    If ``n_multi`` is 0 every regulator maps to exactly one sample (uniform).
    Otherwise, candidate columns where the count is > 1 are the differentiating
    columns.

    :param db_name: Dataset name.
    :param candidate_cols: Columns to check, pre-filtered to exclude identity
        and hidden fields.
    :param filters: Active filters for this dataset.
    :return: ``(sql_string, params_dict)``.

    """
    params: dict[str, Any] = {}
    where = _build_where(filters, params)
    # per_reg: for each multi-sample regulator, count distinct values per column
    per_reg_exprs = ", ".join(f'COUNT(DISTINCT "{c}") AS "{c}"' for c in candidate_cols)
    # agg: count how many regulators show internal variation (per-regulator distinct > 1)
    agg_exprs = ", ".join(
        f'COUNT(*) FILTER (WHERE "{c}" > 1) AS "{c}"' for c in candidate_cols
    )
    sql = (
        f"WITH multi AS ("
        f"  SELECT regulator_locus_tag"
        f"  FROM {db_name}_meta{where}"
        f"  GROUP BY regulator_locus_tag"
        f"  HAVING COUNT(*) > 1"
        f"), per_reg AS ("
        f"  SELECT regulator_locus_tag"
        + (f", {per_reg_exprs}" if per_reg_exprs else "")
        + f"  FROM {db_name}_meta{where}"
        + (" AND" if where else " WHERE")
        + " regulator_locus_tag IN (SELECT regulator_locus_tag FROM multi)"
        "  GROUP BY regulator_locus_tag"
        ") "
        "SELECT COUNT(*) AS n_multi"
        + (f", {agg_exprs}" if agg_exprs else "")
        + " FROM per_reg"
    )
    return sql, params


def regulator_display_labels_query(db_name: str) -> tuple[str, dict]:
    """
    Return ``(sql, params)`` for fetching distinct regulator locus tags and symbols.

    Used to build the ``{locus_tag: "SYMBOL (LOCUS_TAG)"}`` display map for the
    Regulator selectize in the filter modal.

    :param db_name: Dataset name.
    :return: ``(sql_string, params_dict)`` — rows have columns
        ``regulator_locus_tag`` and ``regulator_symbol``.

    """
    return (
        f"SELECT DISTINCT regulator_locus_tag, regulator_symbol"
        f" FROM {db_name}_meta"
        f" ORDER BY regulator_locus_tag",
        {},
    )


def full_data_query(
    db_name: str, filters: dict[str, Any] | None = None
) -> tuple[str, dict[str, Any]]:
    """
    Return ``(sql, params)`` for querying the dataset's full data view with optional
    filters.

    The full data view (``{db_name}``) includes all genomic data columns joined with
    metadata columns.

    :param db_name: Dataset name (e.g. ``'harbison'``).
    :param filters: Active filters for this dataset — same structure as
        :func:`metadata_query`.
    :return: ``(sql_string, params_dict)`` ready for ``vdb.query(sql, **params)``.

    """
    params: dict[str, Any] = {}
    where = _build_where(filters, params)
    return f"SELECT * FROM {db_name}{where}", params


__all__ = [
    "FIELD_TYPE_OVERRIDES",
    "metadata_query",
    "full_data_query",
    "sample_count_query",
    "regulator_locus_tags_query",
    "regulator_breakdown_query",
    "regulator_display_labels_query",
]
