"""SQL query templates for the Perturbation analysis module."""

from __future__ import annotations

from typing import Any, Literal

import pandas as pd
from tfbpapi import VirtualDB

from tfbpshiny.modules.binding.queries import _corr_pair_sql_impl

# Map of db_name -> (effect_col, pvalue_col).
# pvalue_col is empty string for datasets that have no pvalue column.
# TODO: this information should be moved to virtualdb config.
DATASET_COLUMNS: dict[str, tuple[str, str]] = {
    "degron": ("log2FoldChange", "pvalue"),
    "hughes_overexpression": ("mean_norm_log2fc", ""),
    "hughes_knockout": ("mean_norm_log2fc", ""),
    "kemmeren": ("Madj", "pval"),
    "hackett": ("log2_shrunken_timecourses", ""),
    "hu_reimand": ("effect", "pval"),
}


def get_measurement_column(
    db_name: str, which_measurement_field: Literal["effect", "pvalue"]
) -> str:
    """
    Return the column to use for a dataset given the user's preference.

    If ``which_measurement_field`` is ``"pvalue"`` but the dataset has no pvalue
    column, falls back to the effect column.

    :param db_name: Dataset name (key in ``DATASET_COLUMNS``).
    :param which_measurement_field: ``"effect"`` or ``"pvalue"``.
    :return: Column name to use in queries.

    :raises ValueError: If ``which_measurement_field`` is invalid.
    :raises KeyError: If ``db_name`` is not in ``DATASET_COLUMNS``.

    """
    if which_measurement_field not in ("effect", "pvalue"):
        raise ValueError(f"Invalid measurement field: {which_measurement_field}")
    try:
        effect_col, pvalue_col = DATASET_COLUMNS[db_name]
    except KeyError as exc:
        raise KeyError(f"Unknown dataset name: {db_name}") from exc
    if which_measurement_field == "pvalue" and pvalue_col:
        return pvalue_col
    return effect_col


def perturbation_data_query(
    db_name: str,
    col: str,
    filters: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Build a SELECT query and parameter dict for a perturbation dataset.

    Column names and table name are interpolated directly (not parameterizable
    via DuckDB). Filter values are parameterized with ``$name`` syntax.

    :param db_name: Name of the dataset table to query.
    :param col: Data column to select (in addition to the ID columns).
    :param filters: Optional filter spec; each key is a column name, each value is
        a dict with keys ``type`` (``"categorical"``, ``"numeric"``, or ``"bool"``)
        and ``value``.
    :return: Tuple of (sql_string, params_dict) ready to pass to ``vdb.query()``.

    """
    params: dict[str, Any] = {}
    where_clause = _build_where(filters, params) if filters else ""
    sql = (
        f"SELECT regulator_locus_tag, target_locus_tag, sample_id, {col} "
        f"FROM {db_name}{where_clause}"
    )
    return sql, params


def _build_where(
    filters: dict[str, Any],
    params: dict[str, Any],
    prefix: str = "",
) -> str:
    """
    Build a WHERE clause string and populate ``params`` in-place.

    :param filters: Filter spec dict (column -> {type, value}).
    :param params: Dict to populate with parameterized values.
    :param prefix: Namespace prefix to avoid collisions across datasets.
    :return: WHERE clause string (empty string if no filters).

    """
    if not filters:
        return ""
    clauses: list[str] = []
    for field, spec in filters.items():
        kind = spec["type"]
        val = spec["value"]
        p = f"{prefix}_{field}" if prefix else field
        if kind == "categorical":
            placeholders = ", ".join(f"$cat_{p}_{i}" for i in range(len(val)))
            clauses.append(f"{field} IN ({placeholders})")
            for i, v in enumerate(val):
                params[f"cat_{p}_{i}"] = v
        elif kind == "numeric":
            clauses.append(
                f"TRY_CAST({field} AS DOUBLE) BETWEEN $num_{p}_lo AND $num_{p}_hi"
            )
            params[f"num_{p}_lo"] = val[0]
            params[f"num_{p}_hi"] = val[1]
        elif kind == "bool":
            clauses.append(f"{field} = $bool_{p}")
            params[f"bool_{p}"] = bool(val)
    return f" WHERE {' AND '.join(clauses)}" if clauses else ""


def corr_pair_sql(
    vdb: VirtualDB,
    db_a: str,
    col_a: str,
    filters_a: dict[str, Any] | None,
    db_b: str,
    col_b: str,
    filters_b: dict[str, Any] | None,
    method: str,
    prefix: str = "",
    sql_only: bool = False,
) -> pd.DataFrame | tuple[str, dict[str, Any]]:
    """
    Compute per-regulator correlation between two perturbation datasets.

    Delegates to :func:`~tfbpshiny.modules.binding.queries._corr_pair_sql_impl`
    using :func:`perturbation_data_query`.
    See that function for full parameter and return documentation.

    """
    return _corr_pair_sql_impl(
        vdb,
        perturbation_data_query,
        db_a,
        col_a,
        filters_a,
        db_b,
        col_b,
        filters_b,
        method,
        prefix,
        sql_only,
    )


def regulator_symbols_query(db_name: str) -> str:
    """
    Return SQL to fetch distinct regulator locus tags and symbols from a dataset's
    metadata table.

    :param db_name: Dataset name (metadata table is ``{db_name}_meta``).
    :return: SQL string with no parameters.

    """
    return (
        f"SELECT DISTINCT regulator_locus_tag, regulator_symbol "
        f"FROM {db_name}_meta WHERE regulator_locus_tag IS NOT NULL"
    )


def regulator_scatter_sql(
    db_a: str,
    col_a: str,
    filters_a: dict[str, Any] | None,
    db_b: str,
    col_b: str,
    filters_b: dict[str, Any] | None,
    method: str,
    regulator: str,
    idx: int,
) -> tuple[str, dict[str, Any]]:
    """
    Build a SELECT query returning per-target values for a single regulator, suitable
    for scatter plot rendering.

    For Pearson: returns raw column values as ``_val_a`` and ``_val_b``.
    For Spearman: returns ranks (effect ranked by ABS DESC, pvalue ranked ASC).

    :param db_a: First dataset name.
    :param col_a: Column to use from first dataset.
    :param filters_a: Optional filters for first dataset.
    :param db_b: Second dataset name.
    :param col_b: Column to use from second dataset.
    :param filters_b: Optional filters for second dataset.
    :param method: ``"pearson"`` or ``"spearman"``.
    :param regulator: Regulator locus tag to filter to.
    :param idx: Unique integer index to namespace parameters across multiple pairs.
    :return: Tuple of (sql_string, params_dict).

    """
    sql_a, params_a = perturbation_data_query(db_a, col_a, filters_a)
    sql_b, params_b = perturbation_data_query(db_b, col_b, filters_b)
    reg_key_a = f"rp{idx}a"
    reg_key_b = f"rp{idx}b"
    sql_a += (
        " AND " if "WHERE" in sql_a else " WHERE "
    ) + f"regulator_locus_tag = ${reg_key_a}"
    sql_b += (
        " AND " if "WHERE" in sql_b else " WHERE "
    ) + f"regulator_locus_tag = ${reg_key_b}"
    params_a[reg_key_a] = regulator
    params_b[reg_key_b] = regulator

    is_pvalue_a = "pval" in col_a.lower()
    is_pvalue_b = "pval" in col_b.lower()
    order_a = f"{col_a} ASC" if is_pvalue_a else f"ABS({col_a}) DESC"
    order_b = f"{col_b} ASC" if is_pvalue_b else f"ABS({col_b}) DESC"

    if method == "spearman":
        sql = f"""
            WITH a AS ({sql_a}), b AS ({sql_b})
            SELECT
              a.target_locus_tag,
              RANK() OVER (ORDER BY {order_a}) AS _val_a,
              RANK() OVER (ORDER BY {order_b}) AS _val_b
            FROM a JOIN b ON a.target_locus_tag = b.target_locus_tag
        """
    else:
        sql = f"""
            WITH a AS ({sql_a}), b AS ({sql_b})
            SELECT a.target_locus_tag, a.{col_a} AS _val_a, b.{col_b} AS _val_b
            FROM a JOIN b ON a.target_locus_tag = b.target_locus_tag
        """

    return sql, {**params_a, **params_b}


__all__ = [
    "DATASET_COLUMNS",
    "get_measurement_column",
    "perturbation_data_query",
    "corr_pair_sql",
    "regulator_symbols_query",
    "regulator_scatter_sql",
]
