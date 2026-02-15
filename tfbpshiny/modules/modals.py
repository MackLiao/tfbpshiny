"""Modal builders and filter helpers for Active Set selection."""

from __future__ import annotations

import re
from typing import Any, TypedDict

from shiny import ui


class IdentifierFieldMap(TypedDict):
    symbol: list[str]
    locus: list[str]


class IdentifierGroupSpec(TypedDict):
    key: str
    label: str
    field_map: IdentifierFieldMap


_IDENTIFIER_GROUPS: list[IdentifierGroupSpec] = [
    {
        "key": "tf",
        "label": "TF Identifier",
        "field_map": {
            "symbol": ["regulator_symbol", "gene_symbol", "tf_symbol"],
            "locus": ["regulator_locus_tag", "regulator"],
        },
    },
    {
        "key": "target",
        "label": "Target Identifier",
        "field_map": {
            "symbol": ["target_symbol"],
            "locus": ["target_locus_tag"],
        },
    },
]


def normalize_categorical_filters(
    filters: dict[str, Any] | None,
) -> dict[str, list[str]]:
    """Normalize categorical filters by removing empty values."""
    cleaned: dict[str, list[str]] = {}
    if not filters or not isinstance(filters, dict):
        return cleaned

    for field, values in filters.items():
        if not isinstance(values, list):
            continue
        filtered_values = [
            str(value)
            for value in values
            if value is not None and str(value).strip() != ""
        ]
        if filtered_values:
            cleaned[str(field)] = filtered_values

    return cleaned


def _to_finite_number(value: Any) -> float | None:
    if value in ("", None):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


def normalize_numeric_filters(
    filters: dict[str, Any] | None,
) -> dict[str, dict[str, float | None]]:
    """Normalize numeric bounds and drop fields with no active range."""
    cleaned: dict[str, dict[str, float | None]] = {}
    if not filters or not isinstance(filters, dict):
        return cleaned

    for field, bounds in filters.items():
        if not isinstance(bounds, dict):
            continue
        min_value = _to_finite_number(bounds.get("min_value"))
        max_value = _to_finite_number(bounds.get("max_value"))
        if min_value is None and max_value is None:
            continue
        cleaned[str(field)] = {
            "min_value": min_value,
            "max_value": max_value,
        }

    return cleaned


def normalize_dataset_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize per-dataset filter payload into categorical and numeric maps."""
    if not filters or not isinstance(filters, dict):
        return {"categorical": {}, "numeric": {}}

    return {
        "categorical": normalize_categorical_filters(
            filters.get("categorical") or filters
        ),
        "numeric": normalize_numeric_filters(filters.get("numeric") or {}),
    }


def count_active_filters(filters: dict[str, Any] | None) -> int:
    """Count active categorical selections and numeric ranges."""
    normalized = normalize_dataset_filters(filters)
    categorical_count = sum(
        len(values) for values in normalized["categorical"].values()
    )
    numeric_count = sum(
        1
        for bounds in normalized["numeric"].values()
        if bounds.get("min_value") is not None or bounds.get("max_value") is not None
    )
    return categorical_count + numeric_count


def resolve_identifier_groups(
    filter_options: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve identifier groups based on available filter fields."""
    fields = {str(option.get("field")) for option in filter_options}

    groups: list[dict[str, Any]] = []
    for group in _IDENTIFIER_GROUPS:
        symbol_field = next(
            (field for field in group["field_map"]["symbol"] if field in fields), None
        )
        locus_field = next(
            (field for field in group["field_map"]["locus"] if field in fields), None
        )

        if not symbol_field and not locus_field:
            continue

        groups.append(
            {
                "key": group["key"],
                "label": group["label"],
                "symbol_field": symbol_field,
                "locus_field": locus_field,
                "has_toggle": bool(symbol_field and locus_field),
            }
        )

    return groups


def resolve_identifier_mode(
    filters: dict[str, Any],
    group: dict[str, Any],
    modes: dict[str, str] | None = None,
) -> str:
    """Resolve identifier mode from explicit mode map or active filters."""
    modes = modes or {}
    key = str(group["key"])
    if modes.get(key) in {"symbol", "locus"}:
        return modes[key]

    categorical = normalize_dataset_filters(filters)["categorical"]
    locus_field = group.get("locus_field")
    if locus_field and categorical.get(str(locus_field)):
        return "locus"

    return "symbol"


def enforce_identifier_groups(
    filters: dict[str, Any],
    groups: list[dict[str, Any]],
    modes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Drop inactive identifier field selections for TF/target groups."""
    modes = modes or {}
    normalized = normalize_dataset_filters(filters)
    next_categorical = dict(normalized["categorical"])

    for group in groups:
        if not group.get("has_toggle"):
            continue

        mode = resolve_identifier_mode(normalized, group, modes)
        inactive_field = (
            group.get("locus_field") if mode == "symbol" else group.get("symbol_field")
        )
        if inactive_field:
            next_categorical.pop(str(inactive_field), None)

    return {
        "categorical": normalize_categorical_filters(next_categorical),
        "numeric": normalize_numeric_filters(normalized["numeric"]),
    }


def field_key(field: str) -> str:
    """Return a Shiny-safe key for dynamic filter field IDs."""
    safe = re.sub(r"[^0-9A-Za-z_]+", "_", str(field)).strip("_").lower()
    return safe or "field"


def categorical_input_id(field: str) -> str:
    return f"modal_cat_{field_key(field)}"


def numeric_min_input_id(field: str) -> str:
    return f"modal_num_{field_key(field)}_min"


def numeric_max_input_id(field: str) -> str:
    return f"modal_num_{field_key(field)}_max"


def identifier_mode_input_id(group_key: str) -> str:
    return f"modal_identifier_{field_key(group_key)}"


def _dataset_type_badge(dataset_type: str) -> tuple[str, str]:
    if dataset_type == "Binding":
        return ("BD", "badge-bd")
    if dataset_type == "Perturbation":
        return ("PR", "badge-pr")
    return ("EX", "badge-ex")


def render_dataset_config_modal(
    dataset: dict[str, Any],
    filters: dict[str, Any],
    filter_options: list[dict[str, Any]],
    loading_filters: bool,
) -> ui.Tag:
    """Render DatasetConfigModal-like UI as an overlay panel."""
    normalized_filters = normalize_dataset_filters(filters)
    active_filter_count = count_active_filters(normalized_filters)
    groups = resolve_identifier_groups(filter_options)

    badge_text, badge_class = _dataset_type_badge(
        str(dataset.get("type", "Expression"))
    )
    sample_count = int(dataset.get("sample_count") or dataset.get("sampleCount") or 0)
    sample_count_known = bool(
        dataset.get("sample_count_known") or dataset.get("sampleCountKnown")
    )
    column_count = int(dataset.get("column_count") or dataset.get("columnCount") or 0)

    option_sections: list[ui.Tag] = []

    for group in groups:
        if not group.get("has_toggle"):
            continue

        default_mode = resolve_identifier_mode(normalized_filters, group)
        option_sections.append(
            ui.div(
                {"class": "filter-option-card"},
                ui.div(
                    {"class": "filter-option-title"},
                    str(group["label"]),
                ),
                ui.input_radio_buttons(
                    identifier_mode_input_id(str(group["key"])),
                    label=None,
                    choices={"symbol": "Symbol", "locus": "Locus Tag"},
                    selected=default_mode,
                    inline=True,
                ),
                ui.p(
                    {"class": "filter-option-help"},
                    "Inactive identifier field selections are "
                    "dropped when filters are applied.",
                ),
            )
        )

    if loading_filters:
        option_sections.append(
            ui.div(
                {"class": "filter-loading-state"},
                "Loading metadata fields...",
            )
        )
    elif not filter_options:
        option_sections.append(
            ui.div(
                {"class": "filter-empty-state"},
                "No filterable metadata fields were returned for this dataset.",
            )
        )
    else:
        for option in filter_options:
            field = str(option.get("field"))
            kind = str(option.get("kind", "categorical"))

            if kind == "numeric":
                selected_bounds = normalized_filters["numeric"].get(field, {})
                option_sections.append(
                    ui.div(
                        {"class": "filter-option-card"},
                        ui.div(
                            {"class": "filter-option-header"},
                            ui.span({"class": "filter-option-title"}, field),
                            ui.span(
                                {"class": "badge badge-count"},
                                (
                                    "range set"
                                    if selected_bounds.get("min_value") is not None
                                    or selected_bounds.get("max_value") is not None
                                    else "no range"
                                ),
                            ),
                        ),
                        ui.div(
                            {"class": "filter-option-help"},
                            f"Min: {option.get('min_value', 'N/A')}"
                            f" · Max: {option.get('max_value', 'N/A')}",
                        ),
                        ui.div(
                            {"class": "numeric-filter-grid"},
                            ui.input_text(
                                numeric_min_input_id(field),
                                "Min",
                                value=(
                                    ""
                                    if selected_bounds.get("min_value") is None
                                    else str(selected_bounds.get("min_value"))
                                ),
                            ),
                            ui.input_text(
                                numeric_max_input_id(field),
                                "Max",
                                value=(
                                    ""
                                    if selected_bounds.get("max_value") is None
                                    else str(selected_bounds.get("max_value"))
                                ),
                            ),
                        ),
                    )
                )
            else:
                selected_values = normalized_filters["categorical"].get(field, [])
                choices = [str(value) for value in option.get("values", [])]
                option_sections.append(
                    ui.div(
                        {"class": "filter-option-card"},
                        ui.div(
                            {"class": "filter-option-header"},
                            ui.span({"class": "filter-option-title"}, field),
                            ui.span(
                                {"class": "badge badge-count"},
                                f"{len(selected_values)} selected",
                            ),
                        ),
                        ui.input_selectize(
                            categorical_input_id(field),
                            label=None,
                            choices=choices,
                            selected=selected_values,
                            multiple=True,
                            options={"plugins": ["remove_button"]},
                        ),
                    )
                )

    return ui.div(
        {"class": "modal-overlay"},
        ui.div(
            {"class": "modal-card modal-large"},
            ui.div(
                {"class": "modal-panel-header"},
                ui.div(
                    ui.div(
                        {"class": "modal-title-row"},
                        ui.span({"class": f"badge {badge_class}"}, badge_text),
                        ui.h3(str(dataset.get("name", "Dataset"))),
                        ui.span({"class": "badge"}, f"{active_filter_count} filters"),
                    ),
                    ui.div(
                        {"class": "modal-subtitle-row"},
                        (
                            f"{sample_count:,} rows"
                            if sample_count_known
                            else "rows pending"
                        ),
                        " · ",
                        f"{column_count:,} cols",
                    ),
                ),
                ui.input_action_button(
                    "modal_close_config",
                    "\u00d7",
                    class_="modal-close-btn",
                ),
            ),
            ui.div(
                {"class": "modal-panel-body"},
                ui.div(
                    {"class": "include-toggle-row"},
                    ui.div(
                        ui.strong("Include in Analysis"),
                        ui.p(
                            {"class": "hint"},
                            "Enable this dataset for the current workspace.",
                        ),
                    ),
                    ui.input_switch(
                        "modal_include_dataset",
                        label=None,
                        value=bool(dataset.get("selected")),
                    ),
                ),
                ui.div(
                    {"class": "modal-section"},
                    ui.div({"class": "group-header"}, "Dataset Metadata Filters"),
                    *option_sections,
                ),
            ),
            ui.div(
                {"class": "modal-panel-footer"},
                ui.input_action_button(
                    "modal_clear_filters",
                    "Clear",
                    class_="btn btn-sm btn-outline-secondary",
                ),
                ui.input_action_button(
                    "modal_cancel_filters",
                    "Cancel",
                    class_="btn btn-sm btn-secondary",
                ),
                ui.input_action_button(
                    "modal_apply_filters",
                    "Apply Filters",
                    class_="btn btn-sm btn-primary",
                ),
            ),
        ),
    )


def resolve_analysis_module(type_a: str, type_b: str) -> str | None:
    """Match React modal routing logic for intersection detail."""
    if type_a == "Binding" and type_b == "Binding":
        return "binding"
    if type_a == "Perturbation" and type_b == "Perturbation":
        return "perturbation"

    if (type_a == "Binding" and type_b == "Perturbation") or (
        type_a == "Perturbation" and type_b == "Binding"
    ):
        return "composite"

    if type_a == "Expression" and type_b == "Binding":
        return "binding"
    if type_a == "Binding" and type_b == "Expression":
        return "binding"
    if type_a == "Expression" and type_b == "Perturbation":
        return "perturbation"
    if type_a == "Perturbation" and type_b == "Expression":
        return "perturbation"

    return None


def render_intersection_detail_modal(details: dict[str, Any]) -> ui.Tag:
    """Render IntersectionDetailModal-like UI as an overlay panel."""
    row_dataset = details["rowDataset"]
    col_dataset = details["colDataset"]
    count = int(details.get("intersectionCount") or 0)

    row_tf_count = int(row_dataset.get("tfCount") or row_dataset.get("tf_count") or 0)
    col_tf_count = int(col_dataset.get("tfCount") or col_dataset.get("tf_count") or 0)

    row_pct = "N/A" if row_tf_count <= 0 else f"{(count / row_tf_count) * 100:.1f}%"
    col_pct = "N/A" if col_tf_count <= 0 else f"{(count / col_tf_count) * 100:.1f}%"

    target_module = resolve_analysis_module(
        str(row_dataset.get("type", "Expression")),
        str(col_dataset.get("type", "Expression")),
    )

    target_labels = {
        "binding": "Binding Analysis",
        "perturbation": "Perturbation Analysis",
        "composite": "Binding & Perturbation",
    }
    if target_module is None:
        target_label = "Analysis"
    else:
        target_label = target_labels.get(target_module, "Analysis")

    return ui.div(
        {"class": "modal-overlay"},
        ui.div(
            {"class": "modal-card modal-medium"},
            ui.div(
                {"class": "modal-panel-header"},
                ui.h3("Intersection Analysis"),
                ui.input_action_button(
                    "modal_close_intersection",
                    "\u00d7",
                    class_="modal-close-btn",
                ),
            ),
            ui.div(
                {"class": "modal-panel-body"},
                ui.div(
                    {"class": "intersection-dataset-row"},
                    ui.div(
                        {"class": "intersection-dataset-card"},
                        ui.div(
                            {"class": "intersection-dataset-value"},
                            f"{row_tf_count:,}",
                        ),
                        ui.div(str(row_dataset.get("name", "Dataset A"))),
                    ),
                    ui.div({"class": "intersection-vs"}, "VS"),
                    ui.div(
                        {"class": "intersection-dataset-card"},
                        ui.div(
                            {"class": "intersection-dataset-value"},
                            f"{col_tf_count:,}",
                        ),
                        ui.div(str(col_dataset.get("name", "Dataset B"))),
                    ),
                ),
                ui.div(
                    {"class": "intersection-result-card"},
                    ui.div({"class": "intersection-result-label"}, "Common TFs"),
                    ui.div({"class": "intersection-result-value"}, f"{count:,}"),
                    ui.div(
                        {"class": "intersection-result-meta"},
                        f"{row_pct} of A · {col_pct} of B",
                    ),
                ),
            ),
            ui.div(
                {"class": "modal-panel-footer"},
                ui.input_action_button(
                    "modal_close_intersection_secondary",
                    "Close",
                    class_="btn btn-sm btn-secondary",
                ),
                (
                    ui.input_action_button(
                        "modal_open_analysis",
                        f"Open in {target_label}",
                        class_="btn btn-sm btn-primary",
                    )
                    if target_module
                    else ui.span()
                ),
            ),
        ),
    )
