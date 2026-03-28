# flake8: noqa
"""SQL queries for the Comparison (DTO / Top-N by Binding) module."""

from __future__ import annotations

from typing import Any

import pandas as pd
from labretriever import VirtualDB

from tfbpshiny.modules.perturbation.queries import DATASET_COLUMNS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: callingcards target locus tags excluded from the top-N analysis (matching R)
CC_TARGET_BLACKLIST = ("YOR201C", "YOR202W", "YOR203W", "YCL018W", "YEL021W")

#: Hackett regulator symbols excluded from the analysis set
HACKETT_EXCLUDED_SYMBOLS = ("GCN4", "RDS2", "SWI1", "MAC1")

#: Pseudo-value added before -log10 to avoid log(0)
DTO_LOG_PSEUDO = 1e-3

#: Default top-N cutoff
DEFAULT_TOP_N = 25

#: Default effect size threshold (|effect| must exceed this to be "responsive")
DEFAULT_EFFECT_THRESHOLD = 0.0

#: Default p-value threshold (pvalue must be below this to be "responsive")
DEFAULT_PVALUE_THRESHOLD = 0.05

# ---------------------------------------------------------------------------
# Hackett analysis-set setup
# ---------------------------------------------------------------------------

_HACKETT_ANALYSIS_SET_SQL = """
CREATE OR REPLACE TABLE hackett_analysis_set AS
WITH regulator_tiers AS (
    SELECT
        regulator_locus_tag,
        CASE
            WHEN BOOL_OR(mechanism = 'ZEV' AND restriction = 'P') THEN 1
            WHEN BOOL_OR(mechanism = 'GEV' AND restriction = 'P') THEN 2
            ELSE 3
        END AS tier
    FROM hackett_meta
    GROUP BY regulator_locus_tag
),
tier_filtered AS (
    SELECT
        h.sample_id,
        h.regulator_locus_tag,
        h.regulator_symbol,
        h.mechanism,
        h.restriction,
        h.time,
        h.date,
        h.strain,
        t.tier
    FROM hackett_meta h
    JOIN regulator_tiers t USING (regulator_locus_tag)
    WHERE
        (t.tier = 1 AND h.mechanism = 'ZEV' AND h.restriction = 'P')
        OR (t.tier = 2 AND h.mechanism = 'GEV' AND h.restriction = 'P')
        OR (t.tier = 3 AND h.mechanism = 'GEV' AND h.restriction = 'M')
)
SELECT DISTINCT
    sample_id,
    regulator_locus_tag,
    regulator_symbol,
    mechanism,
    restriction,
    time,
    date,
    strain
FROM tier_filtered
WHERE regulator_symbol NOT IN ('GCN4', 'RDS2', 'SWI1', 'MAC1')
"""


def ensure_hackett_analysis_set(vdb: VirtualDB) -> None:
    """
    Register ``hackett_analysis_set`` as an in-memory DuckDB table if not present.

    Safe to call multiple times; uses ``CREATE OR REPLACE``.

    :param vdb: The application VirtualDB instance.

    """
    vdb._conn.execute(_HACKETT_ANALYSIS_SET_SQL)


# ---------------------------------------------------------------------------
# DTO query
# ---------------------------------------------------------------------------

_DTO_SQL = """
SELECT
    d.binding_id_source,
    d.perturbation_id_source,
    d.dto_empirical_pvalue,
    d.dto_fdr,
    d.binding_set_size,
    d.perturbation_set_size,
    CAST(d.binding_id_id   AS VARCHAR)    AS binding_sample_id,
    CAST(d.perturbation_id_id AS VARCHAR) AS pert_sample_id,
    COALESCE(CAST(h.time AS VARCHAR), 'standard') AS time
FROM dto_expanded d
LEFT JOIN hackett_analysis_set h
    ON  d.perturbation_id_source = 'hackett'
    AND CAST(d.perturbation_id_id AS VARCHAR) = CAST(h.sample_id AS VARCHAR)
LEFT JOIN (
    SELECT DISTINCT sample_id FROM callingcards
) cc
    ON  d.binding_id_source = 'callingcards'
    AND CAST(d.binding_id_id AS VARCHAR) = CAST(cc.sample_id AS VARCHAR)
LEFT JOIN (
    SELECT DISTINCT sample_id FROM harbison WHERE condition = 'YPD'
) harb
    ON  d.binding_id_source = 'harbison'
    AND CAST(d.binding_id_id AS VARCHAR) = CAST(harb.sample_id AS VARCHAR)
WHERE
    d.pr_ranking_column = 'log2fc'
    AND (d.perturbation_id_source != 'hackett'     OR h.sample_id IS NOT NULL)
    AND (d.binding_id_source      != 'callingcards' OR cc.sample_id IS NOT NULL)
    AND (d.binding_id_source      != 'harbison'     OR harb.sample_id IS NOT NULL)
"""


def fetch_dto_data(
    vdb: VirtualDB, sql_only: bool = False
) -> pd.DataFrame | tuple[str, dict]:
    """
    Fetch DTO empirical p-value data from ``dto_expanded``.

    Requires ``hackett_analysis_set`` to be registered first via
    :func:`ensure_hackett_analysis_set`.

    :param vdb: VirtualDB instance.
    :param sql_only: If ``True`` return ``(sql, {})`` instead of executing.
    :returns: DataFrame with columns ``binding_id_source``,
        ``perturbation_id_source``, ``dto_empirical_pvalue``, ``dto_fdr``,
        ``binding_set_size``, ``perturbation_set_size``, ``binding_sample_id``,
        ``pert_sample_id``, ``time``.

    """
    if sql_only:
        return _DTO_SQL, {}
    return vdb.query(_DTO_SQL)


# ---------------------------------------------------------------------------
# Top-N responsive ratio query
# ---------------------------------------------------------------------------

_HARBISON_DEDUP_CTE = """
    SELECT
        CAST(sample_id AS VARCHAR) AS binding_sample_id,
        regulator_locus_tag,
        target_locus_tag,
        MIN(pvalue) AS pvalue
    FROM harbison
    WHERE condition = 'YPD'
    GROUP BY sample_id, regulator_locus_tag, target_locus_tag
"""


def _build_where(clauses: list[str]) -> str:
    return ("WHERE " + " AND ".join(clauses)) if clauses else ""


def _build_filter_where(
    filters: dict[str, Any] | None,
    params: dict[str, Any],
    prefix: str,
) -> str:
    """Build a WHERE clause from a dataset_filters spec, populating params in-place."""
    if not filters:
        return ""
    clauses: list[str] = []
    for field, spec in filters.items():
        kind = spec["type"]
        val = spec["value"]
        p = f"{prefix}_{field}".replace(" ", "_")
        if kind == "categorical":
            placeholders = ", ".join(f"$cat_{p}_{i}" for i in range(len(val)))
            clauses.append(f'"{field}" IN ({placeholders})')
            for i, v in enumerate(val):
                params[f"cat_{p}_{i}"] = v
        elif kind == "numeric":
            clauses.append(
                f'TRY_CAST("{field}" AS DOUBLE) BETWEEN $num_{p}_lo AND $num_{p}_hi'
            )
            params[f"num_{p}_lo"] = val[0]
            params[f"num_{p}_hi"] = val[1]
        elif kind == "bool":
            clauses.append(f'"{field}" = $bool_{p}')
            params[f"bool_{p}"] = bool(val)
    return _build_where(clauses)


def _responsive_expr(
    perturbation_view: str,
    effect_threshold: float,
    pvalue_threshold: float,
    param_prefix: str,
    params: dict[str, Any],
) -> str:
    """
    Build a SQL expression that evaluates to 1 (responsive) or 0.

    Uses the effect and pvalue columns from ``DATASET_COLUMNS`` for the given
    perturbation view. If the dataset has no pvalue column only the effect
    threshold is applied.

    :param perturbation_view: Dataset name (key in ``DATASET_COLUMNS``).
    :param effect_threshold: Absolute effect magnitude must exceed this.
    :param pvalue_threshold: P-value must be below this (ignored if no pvalue
        column exists for the dataset).
    :param param_prefix: Namespace prefix for SQL parameter names.
    :param params: Dict populated in-place with threshold parameter values.
    :returns: SQL CASE expression string evaluating to 1 or 0.

    """
    effect_col, pvalue_col = DATASET_COLUMNS.get(perturbation_view, ("", ""))

    eff_key = f"{param_prefix}_eff_thresh"
    pval_key = f"{param_prefix}_pval_thresh"
    params[eff_key] = effect_threshold

    if effect_col and pvalue_col:
        params[pval_key] = pvalue_threshold
        return (
            f"CASE WHEN ABS(p.{effect_col}) > ${eff_key} "
            f"AND p.{pvalue_col} < ${pval_key} THEN 1 ELSE 0 END"
        )
    elif effect_col:
        return f"CASE WHEN ABS(p.{effect_col}) > ${eff_key} THEN 1 ELSE 0 END"
    else:
        # Fall back to pre-computed responsive column
        return "CAST(p.responsive AS INTEGER)"


def topn_responsive_ratio(
    vdb: VirtualDB,
    binding_view: str,
    perturbation_view: str,
    binding_sample_col: str,
    rank_col: str,
    top_n: int = DEFAULT_TOP_N,
    effect_threshold: float = DEFAULT_EFFECT_THRESHOLD,
    pvalue_threshold: float = DEFAULT_PVALUE_THRESHOLD,
    binding_filters: dict[str, Any] | None = None,
    perturbation_filters: dict[str, Any] | None = None,
    rank_asc: bool = True,
    target_blacklist: tuple[str, ...] = (),
    hackett_time_filter: bool = False,
    binding_dedup_cte: str = "",
    param_prefix: str = "p",
    sql_only: bool = False,
) -> pd.DataFrame | tuple[str, dict]:
    """
    Compute the top-N-by-binding responsive ratio for one (binding, perturbation) pair.

    Ranks binding targets per binding sample (PARTITION BY binding_sample_id),
    keeps the top ``top_n``, then joins to perturbation data and applies the
    effect/pvalue thresholds to determine responsiveness dynamically.

    :param vdb: VirtualDB instance.
    :param binding_view: View name for binding data.
    :param perturbation_view: View name for perturbation data.
    :param binding_sample_col: Column in binding view for the sample identifier.
    :param rank_col: Column used to rank binding hits.
    :param top_n: Number of top binding targets to keep per binding sample.
    :param effect_threshold: Minimum absolute effect size to count as responsive.
    :param pvalue_threshold: Maximum p-value to count as responsive (ignored if
        the dataset has no p-value column).
    :param binding_filters: dataset_filters spec for the binding dataset.
    :param perturbation_filters: dataset_filters spec for the perturbation dataset.
    :param rank_asc: If ``True``, lower values of ``rank_col`` rank better.
    :param target_blacklist: Locus tags to exclude from binding targets.
    :param hackett_time_filter: If ``True``, restrict hackett to time=45 via
        ``hackett_analysis_set``.
    :param binding_dedup_cte: Optional CTE body SQL to replace the default
        binding SELECT (used for Harbison dedup).
    :param param_prefix: Namespace prefix for SQL parameters to avoid collisions.
    :param sql_only: If ``True`` return ``(sql, params)`` instead of executing.

    """
    params: dict[str, Any] = {}
    rank_dir = "ASC" if rank_asc else "DESC"

    # binding CTE
    if binding_dedup_cte:
        binding_cte_body = binding_dedup_cte
    else:
        b_filter_where = _build_filter_where(
            binding_filters, params, prefix=f"{param_prefix}_b"
        )
        blacklist_clauses = []
        if b_filter_where:
            blacklist_clauses.append(b_filter_where.lstrip("WHERE "))
        if target_blacklist:
            ph = ", ".join(
                f"$bl_{param_prefix}_{i}" for i in range(len(target_blacklist))
            )
            blacklist_clauses.append(f"target_locus_tag NOT IN ({ph})")
            for i, tag in enumerate(target_blacklist):
                params[f"bl_{param_prefix}_{i}"] = tag
        binding_extra = _build_where(blacklist_clauses)
        binding_cte_body = f"""
        SELECT
            CAST({binding_sample_col} AS VARCHAR) AS binding_sample_id,
            regulator_locus_tag,
            target_locus_tag,
            {rank_col}
        FROM {binding_view}
        {binding_extra}
        """

    # perturbation responsive expression
    responsive_expr = _responsive_expr(
        perturbation_view,
        effect_threshold,
        pvalue_threshold,
        param_prefix,
        params,
    )

    # perturbation CTE
    pert_filter_where = _build_filter_where(
        perturbation_filters, params, prefix=f"{param_prefix}_p"
    )
    pert_join = ""
    if hackett_time_filter:
        pert_join = """
        JOIN hackett_analysis_set has
            ON CAST(p.sample_id AS VARCHAR) = CAST(has.sample_id AS VARCHAR)
            AND has.time = 45
        """

    top_n_key = f"{param_prefix}_top_n"
    params[top_n_key] = top_n

    sql = f"""
    WITH binding AS (
        {binding_cte_body}
    ),
    binding_ranked AS (
        SELECT
            binding_sample_id,
            regulator_locus_tag,
            target_locus_tag,
            {rank_col},
            RANK() OVER (
                PARTITION BY binding_sample_id
                ORDER BY {rank_col} {rank_dir}
            ) AS rnk
        FROM binding
        WHERE regulator_locus_tag != target_locus_tag
    ),
    top_n_binding AS (
        SELECT binding_sample_id, regulator_locus_tag, target_locus_tag
        FROM binding_ranked
        WHERE rnk <= ${top_n_key}
    ),
    perturbation AS (
        SELECT
            CAST(p.sample_id AS VARCHAR) AS perturbation_sample_id,
            p.regulator_locus_tag,
            p.target_locus_tag,
            {responsive_expr} AS is_responsive
        FROM {perturbation_view} p
        {pert_join}
        {pert_filter_where}
    )
    SELECT
        b.binding_sample_id,
        pert.perturbation_sample_id,
        COUNT(*)                                         AS n,
        SUM(pert.is_responsive)::DOUBLE / COUNT(*)       AS responsive_ratio
    FROM top_n_binding b
    JOIN perturbation pert
        ON  b.regulator_locus_tag = pert.regulator_locus_tag
        AND b.target_locus_tag    = pert.target_locus_tag
    GROUP BY b.binding_sample_id, pert.perturbation_sample_id
    """

    if sql_only:
        return sql, params
    return vdb.query(sql, **params)


# ---------------------------------------------------------------------------
# Source label maps (matching the R code)
# ---------------------------------------------------------------------------

BINDING_LABEL_MAP: dict[str, str] = {
    "callingcards": "2026 Calling Cards",
    "harbison": "2004 ChIP-chip",
    "chec_m2025": "2025 Chec-seq",
    "rossi": "2021 ChIPexo",
}

PERTURBATION_LABEL_MAP: dict[str, str] = {
    "hackett": "2020 Overexpression",
    "hughes_overexpression": "2006 Overexpression",
    "hughes_knockout": "2006 TFKO",
    "hu_reimand": "2007 TFKO",
    "kemmeren": "2014 TFKO",
    "degron": "2025 Degron",
}

# ---------------------------------------------------------------------------
# Per-source configuration for top-N analysis
# ---------------------------------------------------------------------------

#: Per-binding-source kwargs passed to topn_responsive_ratio (excluding filters).
BINDING_CONFIGS: dict[str, dict] = {
    "callingcards": dict(
        binding_sample_col="sample_id",
        rank_col="poisson_pval",
        rank_asc=True,
        target_blacklist=CC_TARGET_BLACKLIST,
    ),
    "harbison": dict(
        binding_sample_col="sample_id",
        rank_col="pvalue",
        rank_asc=True,
        binding_dedup_cte=_HARBISON_DEDUP_CTE,
    ),
    "chec_m2025": dict(
        binding_sample_col="sample_id",
        rank_col="score",
        rank_asc=False,
    ),
    "rossi": dict(
        binding_sample_col="sample_id",
        rank_col="score",
        rank_asc=False,
    ),
}

#: Per-perturbation-source kwargs passed to topn_responsive_ratio (excluding filters).
PERTURBATION_CONFIGS: dict[str, dict] = {
    "hackett": dict(hackett_time_filter=True),
    "hughes_overexpression": dict(hackett_time_filter=False),
    "hughes_knockout": dict(hackett_time_filter=False),
    "hu_reimand": dict(hackett_time_filter=False),
    "kemmeren": dict(hackett_time_filter=False),
    "degron": dict(hackett_time_filter=False),
}
