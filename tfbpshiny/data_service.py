"""
Data service backed by tfbpapi (VirtualDB + MetadataConfig).

Replaces mock_data helpers for the Active Set Selection page with real HuggingFace-
hosted DuckDB queries via tfbpapi.

"""

from __future__ import annotations

import logging
import math
import os
import re
import statistics
import tempfile
import threading
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from tfbpapi import DatasetConfig, MetadataConfig, VirtualDB

logger = logging.getLogger("shiny")

# ---------------------------------------------------------------------------
# Path to the bundled YAML collection config
# ---------------------------------------------------------------------------

_YAML_PATH = Path(__file__).parent / "brentlab_yeast_collection.yaml"

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_identifier(name: str) -> str:
    """Raise ValueError if *name* is not a safe SQL identifier."""
    if not _SAFE_IDENTIFIER.fullmatch(name):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return name


# ---------------------------------------------------------------------------
# Dataset type inference
# ---------------------------------------------------------------------------

_BINDING_KEYWORDS = re.compile(
    r"callingcards|harbison|rossi|m2025|chec|chipexo|chip",
    re.IGNORECASE,
)
_PERTURBATION_KEYWORDS = re.compile(
    r"hughes|kemmeren|hackett|overexpression|knockout|perturbation|tfko|zev|rnaseq",
    re.IGNORECASE,
)


def _infer_dataset_type(
    repo_id: str,
    config_name: str,
    ds_cfg: DatasetConfig,
) -> str:
    """Classify a dataset as Binding, Perturbation, or Comparative."""
    if getattr(ds_cfg, "links", None):
        return "Comparative"

    haystack = f"{repo_id} {config_name}"
    if _BINDING_KEYWORDS.search(haystack):
        return "Binding"
    if _PERTURBATION_KEYWORDS.search(haystack):
        return "Perturbation"
    return "Unknown"


def _dataset_group_and_badge(dataset_type: str) -> tuple[str, str]:
    if dataset_type == "Binding":
        return ("binding", "BD")
    if dataset_type == "Perturbation":
        return ("perturbation", "PR")
    if dataset_type == "Comparative":
        return ("comparative", "CO")
    return ("unknown", "UK")


def _title_case(raw: str) -> str:
    parts = re.sub(r"[_-]+", " ", raw).strip()
    return re.sub(r"\b\w", lambda m: m.group(0).upper(), parts)


# ---------------------------------------------------------------------------
# 1. get_datasets  (replaces get_mock_datasets)
# ---------------------------------------------------------------------------


def get_datasets(yaml_path: Path | str | None = None) -> list[dict[str, Any]]:
    """
    Build the dataset catalog from the YAML config (no network calls).

    Each entry matches the dict contract consumed by sidebar/matrix/modals.

    """
    path = Path(yaml_path) if yaml_path else _YAML_PATH
    config = MetadataConfig.from_yaml(path)

    enriched: list[dict[str, Any]] = []
    for repo_id, repo_cfg in config.repositories.items():
        if not repo_cfg.dataset:
            continue
        for config_name, ds_cfg in repo_cfg.dataset.items():
            db_name = ds_cfg.db_name or config_name
            display_name = (
                getattr(ds_cfg, "display_name", None)
                or ds_cfg.model_extra.get("display_name")
                or _title_case(db_name)
            )
            dataset_type = _infer_dataset_type(repo_id, config_name, ds_cfg)

            # Comparative datasets (e.g. DTO) are for composite analysis,
            # not active set selection.
            if dataset_type == "Comparative":
                continue

            group, type_badge = _dataset_group_and_badge(dataset_type)
            dataset_id = f"{repo_id}::{config_name}"

            meta_db_name = f"{db_name}_meta"
            metadata_configs = [
                {
                    "config_name": f"{config_name}_meta",
                    "db_name": meta_db_name,
                    "sample_id_field": "sample_id",
                    "sample_count": 0,
                    "sample_count_known": False,
                    "column_count": 0,
                    "column_names": [],
                }
            ]

            enriched.append(
                {
                    "id": dataset_id,
                    "db_name": db_name,
                    "repo_id": repo_id,
                    "config_name": config_name,
                    "name": display_name,
                    "type": dataset_type,
                    "group": group,
                    "type_badge": type_badge,
                    "sample_count": 0,
                    "sample_count_known": False,
                    "column_count": 0,
                    "column_names": [],
                    "gene_count": 0,
                    "tf_count": 0,
                    "tf_count_known": False,
                    "metadata_configs": metadata_configs,
                    "metadata": {
                        "source": repo_id,
                        "meta_table": meta_db_name,
                    },
                    "selected": False,
                    "selectable": True,
                }
            )

    # Pre-select first two selectable datasets as default.
    selectable = [d for d in enriched if d["selectable"]]
    for entry in selectable[:2]:
        entry["selected"] = True

    return enriched


# ---------------------------------------------------------------------------
# 2. get_or_create_vdb  (replaces sync_mock_active_set_config)
# ---------------------------------------------------------------------------

_vdb_cache: dict[str, VirtualDB] = {}
_vdb_cache_key: str | None = None
_vdb_lock = threading.Lock()


def _get_hf_token() -> str | None:
    return os.environ.get("HF_TOKEN")


def _build_subset_config(
    full_config: MetadataConfig,
    selected_db_names: set[str],
) -> Path:
    """Write a subset YAML config containing only the selected datasets."""
    raw = yaml.safe_load(_YAML_PATH.read_text())

    subset_repos: dict[str, Any] = {}
    for repo_id, repo_cfg in full_config.repositories.items():
        if not repo_cfg.dataset:
            continue

        matched_datasets: dict[str, Any] = {}
        for config_name, ds_cfg in repo_cfg.dataset.items():
            db_name = ds_cfg.db_name or config_name
            if db_name in selected_db_names:
                # Pull the original YAML dict for this dataset to avoid
                # needing to reverse-serialize pydantic models.
                orig_repo = raw.get("repositories", {}).get(repo_id, {})
                orig_ds = orig_repo.get("dataset", {}).get(config_name, {})
                if orig_ds:
                    matched_datasets[config_name] = orig_ds

        if matched_datasets:
            # Include repo-level properties (everything except 'dataset').
            orig_repo = raw.get("repositories", {}).get(repo_id, {})
            repo_entry: dict[str, Any] = {
                k: v for k, v in orig_repo.items() if k != "dataset"
            }
            repo_entry["dataset"] = matched_datasets
            subset_repos[repo_id] = repo_entry

    subset: dict[str, Any] = {"repositories": subset_repos}
    if "factor_aliases" in raw:
        subset["factor_aliases"] = raw["factor_aliases"]
    if "missing_value_labels" in raw:
        subset["missing_value_labels"] = raw["missing_value_labels"]
    if "description" in raw:
        subset["description"] = raw["description"]

    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        prefix="tfbpshiny_subset_",
        delete=False,
    )
    yaml.safe_dump(subset, tmp, default_flow_style=False)
    tmp.close()
    return Path(tmp.name)


def get_or_create_vdb(
    selected_db_names: list[str],
    token: str | None = None,
) -> VirtualDB:
    """Return a VirtualDB for the selected datasets, cached by selection set."""
    global _vdb_cache_key

    cache_key = ",".join(sorted(selected_db_names))
    with _vdb_lock:
        if cache_key == _vdb_cache_key and cache_key in _vdb_cache:
            return _vdb_cache[cache_key]

        full_config = MetadataConfig.from_yaml(_YAML_PATH)
        subset_path = _build_subset_config(full_config, set(selected_db_names))
        hf_token = token or _get_hf_token()

        try:
            vdb = VirtualDB(config_path=subset_path, token=hf_token, lazy=True)
        finally:
            subset_path.unlink(missing_ok=True)

        _vdb_cache.clear()
        _vdb_cache[cache_key] = vdb
        _vdb_cache_key = cache_key

        return vdb


# ---------------------------------------------------------------------------
# 3. get_filter_options  (replaces get_mock_filter_options)
# ---------------------------------------------------------------------------

_NUMERIC_TYPE_PATTERN = re.compile(
    r"DOUBLE|FLOAT|INTEGER|BIGINT|SMALLINT|TINYINT|DECIMAL|NUMERIC|REAL|HUGEINT",
    re.IGNORECASE,
)


def get_filter_options(
    meta_table: str,
    vdb: VirtualDB,
) -> list[dict[str, Any]]:
    """Discover filter fields from a metadata table via VirtualDB.describe()."""
    safe_table = _validate_identifier(meta_table)
    try:
        desc_df = vdb.describe(safe_table)
    except Exception:
        logger.warning("Cannot describe table %s", safe_table, exc_info=True)
        return []

    options: list[dict[str, Any]] = []
    for _, row in desc_df.iterrows():
        col_name = str(row["column_name"])
        col_type = str(row["column_type"])

        if col_name == "sample_id":
            continue

        try:
            safe_col = _validate_identifier(col_name)
        except ValueError:
            continue

        if _NUMERIC_TYPE_PATTERN.search(col_type):
            try:
                stats = vdb.query(
                    f"SELECT MIN({safe_col}) AS mn, MAX({safe_col}) AS mx "
                    f"FROM {safe_table}"
                )
                min_val = float(stats["mn"].iloc[0]) if len(stats) else 0.0
                max_val = float(stats["mx"].iloc[0]) if len(stats) else 0.0
            except Exception:
                logger.debug(
                    "Failed to get min/max for %s.%s",
                    safe_table,
                    safe_col,
                    exc_info=True,
                )
                continue
            options.append(
                {
                    "field": col_name,
                    "kind": "numeric",
                    "min_value": min_val,
                    "max_value": max_val,
                }
            )
        else:
            try:
                vals_df = vdb.query(
                    f"SELECT DISTINCT {safe_col} FROM {safe_table} "
                    f"WHERE {safe_col} IS NOT NULL "
                    f"ORDER BY {safe_col} LIMIT 200"
                )
                values = sorted(str(v) for v in vals_df[col_name].tolist())
            except Exception:
                logger.debug(
                    "Failed to get distinct values for %s.%s",
                    safe_table,
                    safe_col,
                    exc_info=True,
                )
                continue
            if values:
                options.append(
                    {
                        "field": col_name,
                        "kind": "categorical",
                        "values": values,
                    }
                )

    return options


# ---------------------------------------------------------------------------
# 4. get_row_count and get_sample_count  (replaces get_mock_row_count)
# ---------------------------------------------------------------------------


def get_row_count(db_name: str, vdb: VirtualDB) -> int:
    """Return the measurement count for a dataset's metadata table."""
    safe_table = _validate_identifier(f"{db_name}_meta")
    result = vdb.query(f"SELECT COUNT(*) AS cnt FROM {safe_table}")
    return int(result["cnt"].iloc[0]) if len(result) else 0


def get_sample_count(db_name: str, vdb: VirtualDB) -> int:
    """
    Return the sample count (distinct sample_id) for a dataset.

    For binding datasets where multiple measurements exist per sample, this returns the
    unique sample count instead of measurement count.

    """
    safe_table = _validate_identifier(f"{db_name}_meta")
    # Use the resolved sample_id column name from VirtualDB config
    sample_col = vdb._get_sample_id_col(db_name)
    result = vdb.query(f"SELECT COUNT(DISTINCT {sample_col}) AS cnt FROM {safe_table}")
    return int(result["cnt"].iloc[0]) if len(result) else 0


def get_column_count(db_name: str, vdb: VirtualDB) -> int:
    """Return the column count for a dataset's metadata table."""
    safe_table = _validate_identifier(f"{db_name}_meta")
    try:
        desc_df = vdb.describe(safe_table)
        return len(desc_df)
    except Exception:
        logger.warning("Cannot describe table %s", safe_table, exc_info=True)
        return 0


# ---------------------------------------------------------------------------
# 5. get_intersection_cells  (replaces get_mock_intersection_cells)
# ---------------------------------------------------------------------------


def _to_float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(parsed) else parsed


def _build_where_clause(
    categorical: dict[str, list[str]] | None,
    numeric: dict[str, dict[str, Any]] | None,
    valid_fields: set[str],
) -> tuple[str, dict[str, Any]]:
    """
    Build a parameterized WHERE clause.

    Field names are validated against *valid_fields* (an allowlist from the database
    schema) and then checked as safe SQL identifiers. Returns (clause_str, params_dict).
    clause_str is empty if no filters.

    """
    parts: list[str] = []
    params: dict[str, Any] = {}
    param_idx = 0

    if categorical:
        for field, values in categorical.items():
            if field not in valid_fields or not values:
                continue
            safe_field = _validate_identifier(field)
            placeholders = []
            for val in values:
                param_name = f"p{param_idx}"
                params[param_name] = str(val)
                placeholders.append(f"${param_name}")
                param_idx += 1
            parts.append(f"{safe_field} IN ({', '.join(placeholders)})")

    if numeric:
        for field, bounds in numeric.items():
            if field not in valid_fields:
                continue
            if not isinstance(bounds, dict):
                continue
            safe_field = _validate_identifier(field)
            min_val = _to_float_or_none(bounds.get("min_value"))
            max_val = _to_float_or_none(bounds.get("max_value"))
            if min_val is not None:
                param_name = f"p{param_idx}"
                params[param_name] = min_val
                parts.append(f"{safe_field} >= ${param_name}")
                param_idx += 1
            if max_val is not None:
                param_name = f"p{param_idx}"
                params[param_name] = max_val
                parts.append(f"{safe_field} <= ${param_name}")
                param_idx += 1

    clause = " AND ".join(parts) if parts else ""
    return clause, params


def get_intersection_cells(
    db_names: list[str],
    vdb: VirtualDB,
    filters: dict[str, Any] | None = None,
    numeric_filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Compute pairwise TF set intersections across selected datasets."""
    filters = filters or {}
    numeric_filters = numeric_filters or {}

    tf_sets: dict[str, set[str]] = {}
    for db_name in db_names:
        safe_table = _validate_identifier(f"{db_name}_meta")
        try:
            fields = set(vdb.get_fields(safe_table))
        except Exception:
            logger.warning("Cannot get fields for %s", safe_table)
            tf_sets[db_name] = set()
            continue

        # Prefer regulator_symbol, fall back to regulator_locus_tag.
        if "regulator_symbol" in fields:
            reg_col = "regulator_symbol"
        elif "regulator_locus_tag" in fields:
            reg_col = "regulator_locus_tag"
        else:
            tf_sets[db_name] = set()
            continue

        where_clause, params = _build_where_clause(
            categorical=filters.get(db_name),
            numeric=numeric_filters.get(db_name),
            valid_fields=fields,
        )

        sql = f"SELECT DISTINCT {reg_col} AS regulator FROM {safe_table}"
        if where_clause:
            sql += f" WHERE {where_clause}"

        try:
            df = vdb.query(sql, **params)
            tf_sets[db_name] = {str(v) for v in df["regulator"].tolist()}
        except Exception:
            logger.warning("Failed TF query for %s", db_name, exc_info=True)
            tf_sets[db_name] = set()

    # Build pairwise intersection matrix.
    cells: list[dict[str, Any]] = []
    for row_db in db_names:
        for col_db in db_names:
            row_tfs = tf_sets.get(row_db, set())
            col_tfs = tf_sets.get(col_db, set())
            count = len(row_tfs) if row_db == col_db else len(row_tfs & col_tfs)
            cells.append({"row": row_db, "col": col_db, "count": count})

    return cells


# ---------------------------------------------------------------------------
# 6. DTO (Dual Threshold Optimization) composite analysis
# ---------------------------------------------------------------------------


def get_dto_config(yaml_path: Path | str | None = None) -> dict[str, list[str]]:
    """
    Parse DTO links from the YAML config.

    Returns a dict with:
    - "binding": list of db_names linked as binding sources
    - "perturbation": list of db_names linked as perturbation sources

    """
    path = Path(yaml_path) if yaml_path else _YAML_PATH
    config = MetadataConfig.from_yaml(path)

    binding_dbs: list[str] = []
    perturbation_dbs: list[str] = []

    for repo_id, repo_cfg in config.repositories.items():
        if not repo_cfg.dataset:
            continue
        for config_name, ds_cfg in repo_cfg.dataset.items():
            if not getattr(ds_cfg, "links", None):
                continue

            # This is a comparative dataset (e.g., DTO)
            links = ds_cfg.links
            if hasattr(links, "binding_id"):
                for pair in links.binding_id:
                    _, cfg_name = pair[0], pair[1]
                    db_name = cfg_name  # Use config_name as db_name
                    if db_name not in binding_dbs:
                        binding_dbs.append(db_name)

            if hasattr(links, "perturbation_id"):
                for pair in links.perturbation_id:
                    _, cfg_name = pair[0], pair[1]
                    db_name = cfg_name
                    if db_name not in perturbation_dbs:
                        perturbation_dbs.append(db_name)

    return {
        "binding": binding_dbs,
        "perturbation": perturbation_dbs,
    }


def get_dto_data(
    binding_dbs: list[str],
    perturbation_dbs: list[str],
    vdb: VirtualDB,
) -> list[dict[str, Any]]:
    """
    Query DTO data for the selected binding and perturbation datasets.

    DTO is dataset-pair level data - each row represents a
    (binding_sample, perturbation_sample) pair with DTO metrics.
    There's no per-TF data.

    Args:
        binding_dbs: List of binding dataset db_names to filter
        perturbation_dbs: List of perturbation dataset db_names to filter
        vdb: VirtualDB instance with DTO dataset loaded

    Returns:
        List of dicts with binding_id, perturbation_id, dto_pvalue, and dto_fdr

    """
    # Check if dto_expanded view exists
    try:
        fields = set(vdb.get_fields("dto_expanded"))
    except Exception:
        logger.warning("DTO expanded view not found in VirtualDB")
        return []

    # Build WHERE clause for filtering using the partition columns
    # The expanded view has binding_id_source and perturbation_id_source
    conditions: list[str] = []
    params: dict[str, Any] = {}

    if binding_dbs:
        binding_placeholders = []
        for i, db in enumerate(binding_dbs):
            param_name = f"p{i}"
            params[param_name] = db
            binding_placeholders.append(f"${param_name}")
        conditions.append(f"binding_id_source IN ({', '.join(binding_placeholders)})")

    if perturbation_dbs:
        start_idx = len(params)
        pert_placeholders = []
        for i, db in enumerate(perturbation_dbs):
            param_name = f"p{start_idx + i}"
            params[param_name] = db
            pert_placeholders.append(f"${param_name}")
        conditions.append(f"perturbation_id_source IN ({', '.join(pert_placeholders)})")

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    # DTO doesn't have a regulator column - it's dataset-pair level data
    # Build select columns for the DTO metrics
    select_cols = ["binding_id_source", "perturbation_id_source"]

    # Check for dto_pvalue (mapped from dto_empirical_pvalue)
    if "dto_empirical_pvalue" in fields:
        select_cols.append("dto_empirical_pvalue")
    elif "dto_pvalue" in fields:
        select_cols.append("dto_pvalue")
    # Check for dto_fdr
    if "dto_fdr" in fields:
        select_cols.append("dto_fdr")

    col_sql = ", ".join(select_cols)

    sql = f"""
        SELECT {col_sql}
        FROM dto_expanded
        WHERE {where_clause}
    """

    try:
        df = vdb.query(sql, **params)
    except Exception:
        logger.warning("Failed to query DTO data", exc_info=True)
        return []

    # Build result list - DTO is dataset-pair level, not per-TF
    # We use binding_id_source as "regulator_symbol" for compatibility with the plot
    results: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        # Map dto_empirical_pvalue to dto_pvalue in output
        dto_pvalue = _to_float_or_none(row.get("dto_empirical_pvalue"))
        if dto_pvalue is None:
            dto_pvalue = _to_float_or_none(row.get("dto_pvalue"))

        # Use binding/perturbation source as the "regulator" for visualization
        results.append(
            {
                "regulator_symbol": str(row.get("binding_id_source", "")),
                "binding_id": str(row.get("binding_id_source", "")),
                "perturbation_id": str(row.get("perturbation_id_source", "")),
                "dto_pvalue": dto_pvalue,
                "dto_fdr": _to_float_or_none(row.get("dto_fdr")),
            }
        )

    return results


# ---------------------------------------------------------------------------
# 7. Median Correlation Matrix
# ---------------------------------------------------------------------------


def _pearson_correlation(x: list[float], y: list[float]) -> float | None:
    """Compute Pearson correlation between two equal-length float lists."""
    n = len(x)
    if n < 2 or n != len(y):
        return None

    mean_x = sum(x) / n
    mean_y = sum(y) / n
    dx = [xi - mean_x for xi in x]
    dy = [yi - mean_y for yi in y]

    num = sum(a * b for a, b in zip(dx, dy))
    denom_x = math.sqrt(sum(a * a for a in dx))
    denom_y = math.sqrt(sum(b * b for b in dy))

    if denom_x == 0 or denom_y == 0:
        return None
    return num / (denom_x * denom_y)


def get_median_correlation_matrix(
    db_names: list[str],
    value_column: str,
    vdb: VirtualDB,
) -> dict[str, Any]:
    """
    Compute a median-of-per-TF-correlations matrix across datasets.

    For each pair of datasets (A, B):
    1. Find common TFs (regulators).
    2. For each common TF, find shared targets, compute Pearson on *value_column*.
    3. The cell value is the median of the per-TF correlations.

    """
    safe_value_col = _validate_identifier(value_column)

    # --- gather per-dataset data: {db_name: {tf: {target: value}}} ---
    dataset_data: dict[str, dict[str, dict[str, float]]] = {}
    valid_db_names: list[str] = []

    for db_name in db_names:
        safe_table = _validate_identifier(f"{db_name}_meta")
        try:
            fields = set(vdb.get_fields(safe_table))
        except Exception:
            logger.warning("Cannot get fields for %s", safe_table)
            continue

        if safe_value_col not in fields:
            logger.debug("Dataset %s missing column %s", db_name, value_column)
            continue

        # Resolve regulator column
        if "regulator_symbol" in fields:
            reg_col = "regulator_symbol"
        elif "regulator_locus_tag" in fields:
            reg_col = "regulator_locus_tag"
        else:
            continue

        # Resolve target column
        if "target_locus_tag" in fields:
            tgt_col = "target_locus_tag"
        elif "target_symbol" in fields:
            tgt_col = "target_symbol"
        else:
            continue

        sql = (
            f"SELECT {reg_col} AS reg, {tgt_col} AS tgt, {safe_value_col} AS val "
            f"FROM {safe_table} WHERE {safe_value_col} IS NOT NULL"
        )
        try:
            df = vdb.query(sql)
        except Exception:
            logger.warning("Failed query for %s", db_name, exc_info=True)
            continue

        # Collect all values per (TF, target) pair, then aggregate with mean.
        # This handles duplicate rows from sample-level data correctly.
        tf_target_values: dict[str, dict[str, list[float]]] = {}
        for _, row in df.iterrows():
            parsed = _to_float_or_none(row["val"])
            if parsed is None:
                continue
            # Skip rows with null/missing regulator or target IDs.
            tf_raw = row["reg"]
            tgt_raw = row["tgt"]
            if tf_raw is None or tgt_raw is None:
                continue
            tf = str(tf_raw).strip()
            tgt = str(tgt_raw).strip()
            # Skip empty or placeholder strings.
            if not tf or not tgt or tf.lower() in ("nan", "none", "null", ""):
                continue
            if not tgt or tgt.lower() in ("nan", "none", "null", ""):
                continue
            tf_target_values.setdefault(tf, {}).setdefault(tgt, []).append(parsed)

        # Aggregate: compute mean of all values for each (TF, target) pair.
        tf_target_map: dict[str, dict[str, float]] = {}
        for tf, targets in tf_target_values.items():
            tf_target_map[tf] = {}
            for tgt, vals in targets.items():
                if len(vals) == 1:
                    tf_target_map[tf][tgt] = vals[0]
                else:
                    # Use mean: deterministic, appropriate for continuous values
                    tf_target_map[tf][tgt] = sum(vals) / len(vals)

        if not tf_target_map:
            logger.debug(
                "Dataset %s has no valid TF-target data after null filtering", db_name
            )
            continue

        dataset_data[db_name] = tf_target_map
        valid_db_names.append(db_name)

    n = len(valid_db_names)
    matrix: list[list[float | None]] = [[None] * n for _ in range(n)]

    for i in range(n):
        matrix[i][i] = 1.0

    for i in range(n):
        for j in range(i + 1, n):
            data_a = dataset_data[valid_db_names[i]]
            data_b = dataset_data[valid_db_names[j]]
            common_tfs = set(data_a.keys()) & set(data_b.keys())

            per_tf_corrs: list[float] = []
            for tf in common_tfs:
                targets_a = data_a[tf]
                targets_b = data_b[tf]
                shared_targets = set(targets_a.keys()) & set(targets_b.keys())
                if len(shared_targets) < 2:
                    continue
                sorted_targets = sorted(shared_targets)
                x = [targets_a[t] for t in sorted_targets]
                y = [targets_b[t] for t in sorted_targets]
                r = _pearson_correlation(x, y)
                if r is not None:
                    per_tf_corrs.append(r)

            if per_tf_corrs:
                median_val = statistics.median(per_tf_corrs)
                matrix[i][j] = median_val
                matrix[j][i] = median_val

    return {"labels": valid_db_names, "matrix": matrix}


# ---------------------------------------------------------------------------
# 8. Shared numeric columns across datasets
# ---------------------------------------------------------------------------

_STRUCTURAL_COLUMNS = frozenset(
    {
        "sample_id",
        "regulator_symbol",
        "regulator_locus_tag",
        "target_symbol",
        "target_locus_tag",
    }
)


def get_shared_numeric_columns(
    db_names: list[str],
    vdb: VirtualDB,
) -> list[str]:
    """
    Return sorted numeric columns available across datasets' meta tables.

    Returns the **union** of numeric columns found in any dataset, because each
    dataset may use different column names for its quantitative measures (e.g.
    ``enrichment`` for binding, ``M`` for perturbation).
    ``get_median_correlation_matrix`` already skips datasets that lack the
    selected column, so showing all available columns lets users pick whichever
    measure is relevant.

    Excludes structural columns (identifiers) that aren't analysis values.

    """
    if not db_names:
        return []

    all_cols: set[str] = set()
    for db_name in db_names:
        safe_table = _validate_identifier(f"{db_name}_meta")
        try:
            desc_df = vdb.describe(safe_table)
        except Exception:
            logger.warning("Cannot describe table %s", safe_table, exc_info=True)
            continue

        for _, row in desc_df.iterrows():
            col_name = str(row["column_name"])
            col_type = str(row["column_type"])
            if col_name in _STRUCTURAL_COLUMNS:
                continue
            if _NUMERIC_TYPE_PATTERN.search(col_type):
                all_cols.add(col_name)

    return sorted(all_cols)
