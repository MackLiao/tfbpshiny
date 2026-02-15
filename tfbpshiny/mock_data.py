"""
Mock datasets and generators for development without API calls.

This module now provides API-like helpers used by the Active Set selection flow:
- Dataset catalog with metadata configuration summaries.
- Per-dataset metadata + measurement rows.
- Filter-option discovery for dataset metadata tables.
- Intersection counts computed from filtered measurement rows.

"""

from __future__ import annotations

import copy
import hashlib
import math
import random
import re
from typing import Any

# ---------------------------------------------------------------------------
# Catalog and generated in-memory tables
# ---------------------------------------------------------------------------

_BINDING_PATTERN = re.compile(r"binding|chip|calling[_-]?cards|occupancy|chec|chip-exo")
_PERTURBATION_PATTERN = re.compile(
    r"perturb|expression|rna|knockout|deletion|overexpression|comparative|degron"
)

_DATASET_BLUEPRINTS: list[dict[str, Any]] = [
    {
        "id": "bd-001",
        "db_name": "harbison_chipchip",
        "repo_id": "yeast_tf_binding",
        "config_name": "harbison_chipchip",
        "name": "Harbison ChIP-chip",
        "is_active": True,
        "sample_count": 9,
        "type_hint": "binding",
        "source": "Harbison et al.",
    },
    {
        "id": "bd-002",
        "db_name": "hu_callingcards",
        "repo_id": "yeast_tf_binding",
        "config_name": "hu_callingcards",
        "name": "Hu Calling Cards",
        "is_active": False,
        "sample_count": 8,
        "type_hint": "binding",
        "source": "Hu et al.",
    },
    {
        "id": "bd-003",
        "db_name": "kemmeren_chipseq",
        "repo_id": "yeast_tf_binding",
        "config_name": "kemmeren_chipseq",
        "name": "Kemmeren ChIP-seq",
        "is_active": False,
        "sample_count": 10,
        "type_hint": "binding",
        "source": "Kemmeren et al.",
    },
    {
        "id": "bd-004",
        "db_name": "brent_chipexo",
        "repo_id": "yeast_tf_binding",
        "config_name": "brent_chipexo",
        "name": "Brent Lab ChIP-exo",
        "is_active": True,
        "sample_count": 11,
        "type_hint": "binding",
        "source": "Brent Lab",
    },
    {
        "id": "pr-001",
        "db_name": "kemmeren_tfko",
        "repo_id": "yeast_tf_perturb",
        "config_name": "kemmeren_tfko",
        "name": "Kemmeren Perturbation",
        "is_active": True,
        "sample_count": 12,
        "type_hint": "perturbation",
        "source": "Kemmeren et al.",
    },
    {
        "id": "pr-002",
        "db_name": "hu_reimann_tfko",
        "repo_id": "yeast_tf_perturb",
        "config_name": "hu_reimann_tfko",
        "name": "Hu Perturbation",
        "is_active": False,
        "sample_count": 11,
        "type_hint": "perturbation",
        "source": "Hu et al.",
    },
    {
        "id": "pr-003",
        "db_name": "mcisaac_zev",
        "repo_id": "yeast_tf_perturb",
        "config_name": "mcisaac_zev",
        "name": "McIsaac ZEV",
        "is_active": False,
        "sample_count": 10,
        "type_hint": "perturbation",
        "source": "McIsaac et al.",
    },
    {
        "id": "pr-004",
        "db_name": "brent_tfko",
        "repo_id": "yeast_tf_perturb",
        "config_name": "brent_tfko",
        "name": "Brent Lab TF Knockout",
        "is_active": True,
        "sample_count": 13,
        "type_hint": "perturbation",
        "source": "Brent Lab",
    },
    {
        "id": "pr-005",
        "db_name": "brent_overexpression",
        "repo_id": "yeast_tf_perturb",
        "config_name": "brent_overexpression",
        "name": "Brent Lab Overexpression",
        "is_active": False,
        "sample_count": 10,
        "type_hint": "perturbation",
        "source": "Brent Lab",
    },
    {
        "id": "pr-006",
        "db_name": "hackett_timeseries",
        "repo_id": "yeast_tf_perturb",
        "config_name": "hackett_timeseries",
        "name": "Hackett Time-series",
        "is_active": False,
        "sample_count": 9,
        "type_hint": "perturbation",
        "source": "Hackett et al.",
    },
]

_TF_SYMBOLS_BINDING = [
    "ABF1",
    "ACE2",
    "ADR1",
    "ARG80",
    "ARO80",
    "BAS1",
    "CAD1",
    "CBF1",
    "CIN5",
    "CRZ1",
    "DAL80",
    "DAL82",
    "ECM22",
    "FKH1",
    "FKH2",
    "GAL4",
    "GAT1",
    "GCN4",
    "GCR1",
    "GLN3",
    "HAC1",
    "HAP1",
    "HAP4",
    "HSF1",
]

_TF_SYMBOLS_PERTURB = [
    "ACE2",
    "ADR1",
    "ARG80",
    "BAS1",
    "CAD1",
    "CBF1",
    "CRZ1",
    "DAL80",
    "FKH1",
    "GAL4",
    "GAT1",
    "GCN4",
    "HAP1",
    "HAP4",
    "HSF1",
    "IFH1",
    "IME1",
    "INO2",
    "LEU3",
    "MBP1",
    "MET4",
    "RPN4",
    "SKN7",
    "YAP1",
]

_TARGET_SYMBOLS = [f"YGR{i:03d}W" for i in range(100, 320)]

_METADATA_CATEGORICAL_FIELDS = [
    "condition",
    "source_lab",
    "strain",
    "technology",
    "regulator_symbol",
    "regulator_locus_tag",
    "target_symbol",
    "target_locus_tag",
]

_METADATA_NUMERIC_FIELDS = ["time_min", "confidence", "score", "p_value"]


def _seed_for(raw: str) -> int:
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    return int(digest, 16)


def _to_locus(prefix: str, index: int) -> str:
    return f"{prefix}{index:04d}"


def _title_case(raw: str) -> str:
    parts = re.sub(r"[_-]+", " ", raw).strip()
    return re.sub(r"\b\w", lambda m: m.group(0).upper(), parts)


def infer_dataset_type(dataset: dict[str, Any]) -> str:
    """Infer dataset type using the same pattern logic as the React app."""
    haystack = (
        f"{dataset.get('db_name', '')} "
        f"{dataset.get('repo_id', '')} "
        f"{dataset.get('config_name', '')} "
        f"{dataset.get('name', '')}"
    ).lower()

    if _BINDING_PATTERN.search(haystack):
        return "Binding"
    if _PERTURBATION_PATTERN.search(haystack):
        return "Perturbation"
    return "Expression"


def _dataset_group_and_badge(dataset_type: str) -> tuple[str, str]:
    if dataset_type == "Binding":
        return ("binding", "BD")
    if dataset_type == "Perturbation":
        return ("perturbation", "PR")
    return ("expression", "EX")


def _generate_dataset_rows(
    blueprint: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Generate deterministic metadata and measurement rows for a dataset."""
    rng = random.Random(_seed_for(blueprint["db_name"]))

    tf_universe = (
        _TF_SYMBOLS_BINDING
        if blueprint.get("type_hint") == "binding"
        else _TF_SYMBOLS_PERTURB
    )
    tf_count = rng.randint(12, 18)
    tf_pool = sorted(rng.sample(tf_universe, k=tf_count))
    target_pool = sorted(rng.sample(_TARGET_SYMBOLS, k=rng.randint(70, 120)))

    tf_locus_map = {
        symbol: _to_locus("YTF", index)
        for index, symbol in enumerate(
            sorted(set(_TF_SYMBOLS_BINDING + _TF_SYMBOLS_PERTURB)), start=1
        )
    }
    target_locus_map = {
        symbol: _to_locus("YTG", index)
        for index, symbol in enumerate(_TARGET_SYMBOLS, start=1)
    }

    metadata_rows: list[dict[str, Any]] = []
    measurement_rows: list[dict[str, Any]] = []

    conditions = ["Control", "HeatShock", "NitrogenStarvation", "Rapamycin"]
    strains = ["BY4741", "W303", "S288C"]
    technologies = [
        "ChIP-chip" if blueprint.get("type_hint") == "binding" else "RNA-seq",
        "CallingCards" if blueprint.get("type_hint") == "binding" else "Microarray",
        "ChIP-exo" if blueprint.get("type_hint") == "binding" else "CRISPRi",
    ]

    sample_total = int(blueprint["sample_count"])
    for sample_index in range(sample_total):
        sample_id = f"{blueprint['id']}_S{sample_index + 1:02d}"
        meta_row = {
            "sample_id": sample_id,
            "condition": rng.choice(conditions),
            "source_lab": rng.choice(
                [blueprint.get("source", "Brent Lab"), "Public", "Curated"]
            ),
            "strain": rng.choice(strains),
            "technology": rng.choice(technologies),
            "time_min": rng.choice([0, 15, 30, 60, 120, 240]),
            "confidence": round(rng.uniform(0.5, 0.99), 3),
        }
        metadata_rows.append(meta_row)

        active_tf_count = rng.randint(max(4, tf_count // 2), tf_count)
        active_tfs = rng.sample(tf_pool, k=active_tf_count)
        for tf_symbol in active_tfs:
            num_targets = rng.randint(3, 7)
            chosen_targets = rng.sample(
                target_pool, k=min(len(target_pool), num_targets)
            )
            for target_symbol in chosen_targets:
                score = round(rng.uniform(5.0, 200.0), 3)
                p_value = round(rng.uniform(0.0001, 0.25), 6)
                effect_size = round(rng.gauss(0.2, 1.1), 4)
                measurement_rows.append(
                    {
                        "sample_id": sample_id,
                        "regulator_symbol": tf_symbol,
                        "regulator_locus_tag": tf_locus_map[tf_symbol],
                        "target_symbol": target_symbol,
                        "target_locus_tag": target_locus_map[target_symbol],
                        "condition": meta_row["condition"],
                        "source_lab": meta_row["source_lab"],
                        "strain": meta_row["strain"],
                        "technology": meta_row["technology"],
                        "time_min": meta_row["time_min"],
                        "confidence": meta_row["confidence"],
                        "score": score,
                        "p_value": p_value,
                        "effect_size": effect_size,
                    }
                )

    return metadata_rows, measurement_rows


def _build_mock_repository() -> tuple[
    list[dict[str, Any]],
    dict[str, list[dict[str, Any]]],
    dict[str, list[dict[str, Any]]],
]:
    catalog: list[dict[str, Any]] = []
    metadata_by_table: dict[str, list[dict[str, Any]]] = {}
    measurements_by_table: dict[str, list[dict[str, Any]]] = {}

    for blueprint in _DATASET_BLUEPRINTS:
        metadata_rows, measurement_rows = _generate_dataset_rows(blueprint)
        db_name = str(blueprint["db_name"])
        meta_db_name = f"{db_name}_meta"

        measurement_columns = [
            "sample_id",
            "regulator_symbol",
            "regulator_locus_tag",
            "target_symbol",
            "target_locus_tag",
            "condition",
            "source_lab",
            "strain",
            "technology",
            "time_min",
            "confidence",
            "score",
            "p_value",
            "effect_size",
        ]
        metadata_columns = [
            "sample_id",
            "condition",
            "source_lab",
            "strain",
            "technology",
            "time_min",
            "confidence",
        ]

        catalog.append(
            {
                "id": blueprint["id"],
                "db_name": db_name,
                "repo_id": blueprint["repo_id"],
                "config_name": blueprint["config_name"],
                "name": blueprint.get("name") or _title_case(blueprint["config_name"]),
                "selectable": True,
                "is_active": bool(blueprint.get("is_active", False)),
                "estimated_rows": len(measurement_rows),
                "num_columns": len(measurement_columns),
                "column_names": measurement_columns,
                "supplemental_configs": [
                    {
                        "config_name": f"{blueprint['config_name']}_meta",
                        "db_name": meta_db_name,
                        "sample_id_field": "sample_id",
                        "estimated_rows": len(metadata_rows),
                        "num_columns": len(metadata_columns),
                        "column_names": metadata_columns,
                    }
                ],
            }
        )

        metadata_by_table[meta_db_name] = metadata_rows
        measurements_by_table[db_name] = measurement_rows

    return catalog, metadata_by_table, measurements_by_table


(
    _MOCK_DATASET_CATALOG,
    _MOCK_METADATA_BY_TABLE,
    _MOCK_MEASUREMENTS_BY_TABLE,
) = _build_mock_repository()
_MOCK_DATASET_BY_DB_NAME: dict[str, dict[str, Any]] = {
    str(entry["db_name"]): entry for entry in _MOCK_DATASET_CATALOG
}

# ---------------------------------------------------------------------------
# Mock API-like helpers used by selection flow
# ---------------------------------------------------------------------------


def list_mock_dataset_catalog() -> list[dict[str, Any]]:
    """Return a deep copy of the mock `/dataset-catalog` response."""
    return copy.deepcopy(_MOCK_DATASET_CATALOG)


def sync_mock_active_set_config(dataset_ids: list[str]) -> dict[str, Any]:
    """Mock `/active-set/sync-config` endpoint."""
    available = {str(entry["id"]) for entry in _MOCK_DATASET_CATALOG}
    missing = [dataset_id for dataset_id in dataset_ids if dataset_id not in available]
    if missing:
        raise ValueError(f"Unknown dataset ids: {', '.join(missing)}")

    return {"ok": True, "dataset_ids": list(dataset_ids)}


def get_mock_filter_options(meta_table: str) -> list[dict[str, Any]]:
    """
    Mock `/active-set/filter-options/{metaTable}` endpoint.

    The UI expects filter fields that can target identifiers and metadata. We derive
    options from the generated measurement rows for the paired dataset.

    """
    db_name = meta_table[:-5] if meta_table.endswith("_meta") else meta_table
    rows = _MOCK_MEASUREMENTS_BY_TABLE.get(db_name, [])

    options: list[dict[str, Any]] = []

    for field in _METADATA_CATEGORICAL_FIELDS:
        values = sorted(
            {
                str(row[field])
                for row in rows
                if row.get(field) is not None and str(row.get(field)).strip() != ""
            }
        )
        if values:
            options.append(
                {
                    "field": field,
                    "kind": "categorical",
                    # Keep option lists readable in modal.
                    "values": values[:60],
                }
            )

    for field in _METADATA_NUMERIC_FIELDS:
        numeric_values = [
            float(row[field])
            for row in rows
            if isinstance(row.get(field), (int, float))
        ]
        if numeric_values:
            options.append(
                {
                    "field": field,
                    "kind": "numeric",
                    "min_value": min(numeric_values),
                    "max_value": max(numeric_values),
                }
            )

    return options


def get_mock_row_count(table: str) -> int:
    """Mock `/tables/{table}/count` endpoint."""
    rows = _MOCK_MEASUREMENTS_BY_TABLE.get(table)
    return len(rows) if rows is not None else 0


def _to_float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


def _normalize_categorical_filter_map(
    filters: dict[str, Any] | None,
) -> dict[str, list[str]]:
    cleaned: dict[str, list[str]] = {}
    if not filters:
        return cleaned

    for field, values in filters.items():
        if not isinstance(values, list):
            continue
        normalized_values = [
            str(value)
            for value in values
            if value is not None and str(value).strip() != ""
        ]
        if normalized_values:
            cleaned[str(field)] = normalized_values

    return cleaned


def _normalize_numeric_filter_map(
    filters: dict[str, Any] | None,
) -> dict[str, dict[str, float | None]]:
    cleaned: dict[str, dict[str, float | None]] = {}
    if not filters:
        return cleaned

    for field, bounds in filters.items():
        if not isinstance(bounds, dict):
            continue
        min_value = _to_float_or_none(bounds.get("min_value"))
        max_value = _to_float_or_none(bounds.get("max_value"))
        if min_value is None and max_value is None:
            continue
        cleaned[str(field)] = {
            "min_value": min_value,
            "max_value": max_value,
        }

    return cleaned


def _record_matches_filters(
    record: dict[str, Any],
    categorical_filters: dict[str, list[str]],
    numeric_filters: dict[str, dict[str, float | None]],
) -> bool:
    for field, accepted_values in categorical_filters.items():
        value = record.get(field)
        if value is None or str(value) not in accepted_values:
            return False

    for field, bounds in numeric_filters.items():
        value = _to_float_or_none(record.get(field))
        if value is None:
            return False

        min_value = bounds.get("min_value")
        max_value = bounds.get("max_value")
        if min_value is not None and value < min_value:
            return False
        if max_value is not None and value > max_value:
            return False

    return True


def _filtered_tf_set(
    db_name: str,
    categorical_filters: dict[str, list[str]] | None,
    numeric_filters: dict[str, dict[str, float | None]] | None,
) -> set[str]:
    rows = _MOCK_MEASUREMENTS_BY_TABLE.get(db_name, [])
    normalized_categorical = _normalize_categorical_filter_map(categorical_filters)
    normalized_numeric = _normalize_numeric_filter_map(numeric_filters)

    tf_set: set[str] = set()
    for row in rows:
        if _record_matches_filters(row, normalized_categorical, normalized_numeric):
            tf_set.add(str(row["regulator_symbol"]))
    return tf_set


def get_mock_intersection_cells(
    datasets: list[str],
    filters: dict[str, Any] | None = None,
    numeric_filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Mock `/active-set/intersection` endpoint using filtered TF sets."""
    filters = filters or {}
    numeric_filters = numeric_filters or {}

    tf_sets: dict[str, set[str]] = {}
    for db_name in datasets:
        tf_sets[db_name] = _filtered_tf_set(
            db_name,
            categorical_filters=filters.get(db_name, {}),
            numeric_filters=numeric_filters.get(db_name, {}),
        )

    cells: list[dict[str, Any]] = []
    for row_db in datasets:
        for col_db in datasets:
            row_tfs = tf_sets.get(row_db, set())
            col_tfs = tf_sets.get(col_db, set())
            if row_db == col_db:
                count = len(row_tfs)
            else:
                count = len(row_tfs.intersection(col_tfs))
            cells.append({"row": row_db, "col": col_db, "count": count})

    return cells


# ---------------------------------------------------------------------------
# Selection model helpers (Shiny app state)
# ---------------------------------------------------------------------------


def get_mock_datasets() -> list[dict[str, Any]]:
    """
    Return enriched datasets for Active Set UI state.

    Mirrors the React startup flow:
    1. Keep selectable datasets.
    2. Select active datasets, or fallback to first two selectable datasets.
    3. Populate UI-centric fields used by sidebar/matrix/modal modules.

    """
    selectable = [
        entry for entry in list_mock_dataset_catalog() if entry.get("selectable")
    ]

    active_ids = [str(entry["id"]) for entry in selectable if entry.get("is_active")]
    fallback_ids = [str(entry["id"]) for entry in selectable[:2]]
    selected_ids = set(active_ids if active_ids else fallback_ids)

    enriched: list[dict[str, Any]] = []
    for entry in selectable:
        dataset_type = infer_dataset_type(entry)
        group, type_badge = _dataset_group_and_badge(dataset_type)
        db_name = str(entry["db_name"])
        measurement_rows = _MOCK_MEASUREMENTS_BY_TABLE.get(db_name, [])
        unique_tf_count = len({row["regulator_symbol"] for row in measurement_rows})

        metadata_configs = []
        for supplemental in entry.get("supplemental_configs", []):
            metadata_configs.append(
                {
                    "configName": supplemental.get("config_name"),
                    "dbName": supplemental.get("db_name"),
                    "sampleIdField": supplemental.get("sample_id_field"),
                    "sampleCount": supplemental.get("estimated_rows") or 0,
                    "sampleCountKnown": supplemental.get("estimated_rows") is not None,
                    "columnCount": (
                        supplemental.get("num_columns")
                        if isinstance(supplemental.get("num_columns"), int)
                        else len(supplemental.get("column_names") or [])
                    ),
                    "columnNames": supplemental.get("column_names") or [],
                }
            )

        estimated_rows = entry.get("estimated_rows")
        column_names = entry.get("column_names") or []
        num_columns = entry.get("num_columns")

        enriched.append(
            {
                "id": str(entry["id"]),
                "db_name": db_name,
                "dbName": db_name,
                "repo_id": entry.get("repo_id"),
                "repoId": entry.get("repo_id"),
                "config_name": entry.get("config_name"),
                "configName": entry.get("config_name"),
                "name": entry.get("name")
                or _title_case(entry.get("config_name", db_name)),
                "type": dataset_type,
                "group": group,
                "type_badge": type_badge,
                "typeBadge": type_badge,
                "sample_count": (
                    estimated_rows if isinstance(estimated_rows, int) else 0
                ),
                "sampleCount": estimated_rows if isinstance(estimated_rows, int) else 0,
                "sample_count_known": isinstance(estimated_rows, int),
                "sampleCountKnown": isinstance(estimated_rows, int),
                "column_count": (
                    num_columns if isinstance(num_columns, int) else len(column_names)
                ),
                "columnCount": (
                    num_columns if isinstance(num_columns, int) else len(column_names)
                ),
                "column_names": column_names,
                "columnNames": column_names,
                # Legacy aliases retained for compatibility with existing modules.
                "gene_count": unique_tf_count,
                "col_count": (
                    num_columns if isinstance(num_columns, int) else len(column_names)
                ),
                # Intersection-derived counts start as unknown and get set on refresh.
                "tf_count": 0,
                "tfCount": 0,
                "tf_count_known": False,
                "tfCountKnown": False,
                "metadata_configs": metadata_configs,
                "metadataConfigs": metadata_configs,
                "metadata": {
                    "source": entry.get("repo_id", "mock"),
                    "meta_table": f"{db_name}_meta",
                },
                "selected": str(entry["id"]) in selected_ids,
            }
        )

    return enriched


def count_active_filters(filters: dict[str, Any] | None) -> int:
    """Count active categorical values and numeric ranges for a dataset."""
    if not filters or not isinstance(filters, dict):
        return 0

    categorical = _normalize_categorical_filter_map(
        filters.get("categorical") or filters
    )
    numeric = _normalize_numeric_filter_map(filters.get("numeric") or {})

    categorical_count = sum(len(values) for values in categorical.values())
    numeric_count = sum(
        1
        for bounds in numeric.values()
        if bounds.get("min_value") is not None or bounds.get("max_value") is not None
    )
    return categorical_count + numeric_count


# ---------------------------------------------------------------------------
# Analysis mock helpers (kept for existing analysis modules)
# ---------------------------------------------------------------------------


def get_mock_table_data(
    db_name: str,
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    """Return mock tabular analysis data for a dataset from real measurement rows."""
    rows = _MOCK_MEASUREMENTS_BY_TABLE.get(db_name, [])
    total = len(rows)

    safe_page = max(1, int(page))
    safe_page_size = max(1, int(page_size))
    start = (safe_page - 1) * safe_page_size
    end = start + safe_page_size

    slice_rows = rows[start:end]
    table_rows = [
        {
            "tf_name": row["regulator_symbol"],
            "target_gene": row["target_symbol"],
            "log2fc": row["effect_size"],
            "p_value": row["p_value"],
            "effect_size": row["score"],
            "source": db_name,
        }
        for row in slice_rows
    ]

    return {
        "rows": table_rows,
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
    }


def get_mock_summary(db_name: str) -> dict[str, Any]:
    """Return summary statistics derived from mock measurement rows."""
    rows = _MOCK_MEASUREMENTS_BY_TABLE.get(db_name, [])
    tf_set = {row["regulator_symbol"] for row in rows}
    target_set = {row["target_symbol"] for row in rows}

    total_tfs = len(tf_set)
    total_targets = len(target_set)
    total_interactions = len(rows)
    avg_targets_per_tf = round(total_targets / total_tfs, 1) if total_tfs else 0.0
    effect_sizes = sorted(float(row["effect_size"]) for row in rows)
    median_effect_size = (
        round(effect_sizes[len(effect_sizes) // 2], 3) if effect_sizes else 0.0
    )

    return {
        "db_name": db_name,
        "total_tfs": total_tfs,
        "total_targets": total_targets,
        "total_interactions": total_interactions,
        "avg_targets_per_tf": avg_targets_per_tf,
        "median_effect_size": median_effect_size,
        "sources": sorted({str(row["source_lab"]) for row in rows}),
    }


def get_mock_correlation(db_name: str) -> dict[str, Any]:
    """Return mock correlation matrix data."""
    rows = _MOCK_MEASUREMENTS_BY_TABLE.get(db_name, [])
    labels = sorted({str(row["regulator_symbol"]) for row in rows})[:8]
    if not labels:
        labels = ["ABF1", "ACE2", "ADR1", "ARG80", "BAS1", "CBF1", "CRZ1", "GAL4"]

    rng = random.Random(_seed_for(f"corr::{db_name}"))
    n = len(labels)
    matrix: list[list[float]] = []
    for i in range(n):
        row: list[float] = []
        for j in range(n):
            if i == j:
                row.append(1.0)
            elif j < i:
                row.append(matrix[j][i])
            else:
                row.append(round(rng.uniform(-0.6, 0.9), 3))
        matrix.append(row)
    return {"labels": labels, "matrix": matrix}


def get_mock_source_summary(db_name: str) -> dict[str, Any]:
    """Return source summary stats and metadata-field descriptors."""
    rows = _MOCK_MEASUREMENTS_BY_TABLE.get(db_name, [])
    catalog_entry = _MOCK_DATASET_BY_DB_NAME.get(db_name, {})

    fields: list[dict[str, Any]] = []
    if rows:
        sample = rows[0]
        for field, value in sample.items():
            if field == "sample_id":
                continue
            kind = "numeric" if isinstance(value, (int, float)) else "categorical"
            fields.append({"field": field, "kind": kind})

    dataset_type = infer_dataset_type(catalog_entry) if catalog_entry else "Expression"
    config_name = str(catalog_entry.get("config_name", db_name))
    repo_id = str(catalog_entry.get("repo_id", "mock"))

    return {
        "db_name": db_name,
        "repo_id": repo_id,
        "dataset_type": dataset_type,
        "config_name": config_name,
        "total_rows": len(rows),
        "regulator_count": len({str(row["regulator_symbol"]) for row in rows}),
        "target_count": len({str(row["target_symbol"]) for row in rows}),
        "sample_count": len({str(row["sample_id"]) for row in rows}),
        "column_count": len(rows[0]) if rows else 0,
        "metadata_fields": fields,
    }


def _group_field_from_group_by(group_by: str) -> str:
    normalized = (group_by or "regulator").strip().lower()
    if normalized == "target":
        return "target_symbol"
    if normalized == "sample":
        return "sample_id"
    return "regulator_symbol"


def _aggregate_values_by_entity(
    rows: list[dict[str, Any]],
    entity_field: str,
    value_column: str,
) -> dict[str, float]:
    bucket: dict[str, list[float]] = {}
    for row in rows:
        entity = str(row.get(entity_field, "")).strip()
        value = _to_float_or_none(row.get(value_column))
        if not entity or value is None:
            continue
        bucket.setdefault(entity, []).append(value)

    return {
        entity: (sum(values) / len(values))
        for entity, values in bucket.items()
        if values
    }


def _pearson_correlation(values_a: list[float], values_b: list[float]) -> float | None:
    if len(values_a) != len(values_b) or len(values_a) < 2:
        return None

    mean_a = sum(values_a) / len(values_a)
    mean_b = sum(values_b) / len(values_b)
    cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(values_a, values_b))
    var_a = sum((a - mean_a) ** 2 for a in values_a)
    var_b = sum((b - mean_b) ** 2 for b in values_b)

    denom = math.sqrt(var_a * var_b)
    if denom == 0:
        return None
    return cov / denom


def get_mock_pairwise_comparison(
    db_name_a: str,
    db_name_b: str,
    value_column: str = "effect_size",
    group_by: str = "regulator",
    max_points: int = 5000,
) -> dict[str, Any]:
    """Return pairwise comparison points between two datasets."""
    rows_a = _MOCK_MEASUREMENTS_BY_TABLE.get(db_name_a, [])
    rows_b = _MOCK_MEASUREMENTS_BY_TABLE.get(db_name_b, [])

    entity_field = _group_field_from_group_by(group_by)
    agg_a = _aggregate_values_by_entity(rows_a, entity_field, value_column)
    agg_b = _aggregate_values_by_entity(rows_b, entity_field, value_column)

    common_entities = sorted(set(agg_a).intersection(agg_b))
    points: list[dict[str, Any]] = []

    for entity in common_entities:
        value_a = agg_a[entity]
        value_b = agg_b[entity]
        delta = value_b - value_a
        points.append(
            {
                "entity": entity,
                "value_a": round(value_a, 6),
                "value_b": round(value_b, 6),
                "delta": round(delta, 6),
                "log2_fold_change": round(delta, 6),
            }
        )

    points.sort(key=lambda row: abs(float(row["delta"])), reverse=True)
    limited_points = points[: max(1, int(max_points))]

    corr = _pearson_correlation(
        [float(row["value_a"]) for row in limited_points],
        [float(row["value_b"]) for row in limited_points],
    )

    return {
        "db_name_a": db_name_a,
        "db_name_b": db_name_b,
        "group_by": entity_field,
        "value_column": value_column,
        "total_entities": len(common_entities),
        "points": limited_points,
        "correlation": (None if corr is None else round(corr, 5)),
    }


# ---------------------------------------------------------------------------
# Backward-compatible intersection helper
# ---------------------------------------------------------------------------


def compute_mock_intersection(
    datasets: list[dict[str, Any]],
    logic_mode: str = "intersect",
) -> dict[str, Any]:
    """
    Backward-compatible matrix helper based on selected datasets.

    `logic_mode` is accepted for compatibility with existing calls. The mock
    endpoint-style intersection computation itself does not depend on it.

    """
    _ = logic_mode
    selected = [entry for entry in datasets if entry.get("selected")]
    selected_db_names = [
        str(entry.get("db_name") or entry.get("dbName")) for entry in selected
    ]
    cells = get_mock_intersection_cells(selected_db_names)

    names = [str(entry.get("name", entry.get("db_name"))) for entry in selected]
    if not selected_db_names:
        return {"names": names, "matrix": []}

    matrix: list[list[int]] = []
    for row_db in selected_db_names:
        row_values: list[int] = []
        for col_db in selected_db_names:
            hit = next(
                (
                    cell
                    for cell in cells
                    if cell["row"] == row_db and cell["col"] == col_db
                ),
                None,
            )
            row_values.append(int(hit["count"]) if hit else 0)
        matrix.append(row_values)

    return {"names": names, "matrix": matrix}
