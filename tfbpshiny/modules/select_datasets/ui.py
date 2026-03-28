"""UI functions for the Select Datasets page."""

from __future__ import annotations

from typing import Any

import pandas as pd
from shiny import module, ui

from tfbpshiny.components import workspace_heading, workspace_shell
from tfbpshiny.modules.select_datasets.queries import FIELD_TYPE_OVERRIDES


def _slugify(s: str) -> str:
    """
    Convert a string to a slug suitable for use in HTML element IDs.

    This is primarily used to replace spaces, eg in aliased fields like
    `Regulator locus tag`, to `regulator_locus_tag` for the filter control IDs.

    """
    return s.lower().replace(" ", "_")


def _filter_control(
    field: str,
    col: pd.Series,
    saved_spec: dict[str, Any] | None,
    db_name: str = "",
    is_common: bool = False,
    union_levels: list[str] | None = None,
) -> ui.Tag | None:
    """
    Build a single filter-option card for ``field``.

    Returns ``None`` if the field type is not filterable or has no usable data.

    Note: this function uses the ``filter-option-card`` CSS classes directly
    rather than ``components.filter_option_card`` because it conditionally
    injects an "Apply to all datasets" toggle into the card header — a variant
    that the generic component does not support.

    :param is_common: When ``True``, appends an "Apply to all datasets" toggle
        inside the card. The toggle is pre-set from ``saved_spec["apply_to_all"]``
        if present, defaulting to ``True``.

    """
    dtype = col.dtype
    type_override = FIELD_TYPE_OVERRIDES.get(
        (db_name, field)
    ) or FIELD_TYPE_OVERRIDES.get(("", field))
    override_kind = type_override[0] if type_override else None
    override_level_dtype = type_override[1] if type_override else None

    def _apply_to_all_toggle() -> ui.Tag:
        saved_val = saved_spec.get("apply_to_all", False) if saved_spec else False
        return ui.input_switch(
            f"apply_to_all_{_slugify(field)}",
            "Apply to all datasets",
            value=saved_val,
        )

    if override_kind == "categorical" or dtype.name in ("object", "category"):
        raw = (
            union_levels
            if union_levels is not None
            else [str(v) for v in col.dropna().unique()]
        )
        choices = sorted(
            raw, key=lambda x: float(x) if override_level_dtype == "numeric" else x
        )
        selected = saved_spec["value"] if saved_spec else []
        return ui.div(
            {"class": "filter-option-card"},
            ui.div(
                {"class": "filter-option-header"},
                ui.span({"class": "filter-option-title"}, field),
                _apply_to_all_toggle() if is_common else ui.span(),
            ),
            ui.input_selectize(
                f"filter_{_slugify(field)}",
                label=None,
                choices=choices,
                selected=selected,
                multiple=True,
                options={"plugins": ["remove_button"]},
            ),
        )

    if dtype == "bool":
        saved_val = bool(saved_spec["value"]) if saved_spec else False
        return ui.div(
            {"class": "filter-option-card"},
            ui.div(
                {"class": "filter-option-header"},
                ui.span({"class": "filter-option-title"}, field),
                _apply_to_all_toggle() if is_common else ui.span(),
            ),
            ui.input_switch(f"filter_{_slugify(field)}", label=field, value=saved_val),
        )

    if dtype.name in ("float64", "int64", "float32", "int32"):
        non_null = col.dropna()
        if non_null.empty:
            return None
        data_min = float(non_null.min())
        data_max = float(non_null.max())
        if data_min == data_max:
            data_max = data_min + 1.0
        # TODO: fix typing issue and remove type: ignore
        saved_val = saved_spec["value"] if saved_spec else [data_min, data_max]  # type: ignore # noqa: E501
        return ui.div(
            {"class": "filter-option-card"},
            ui.div(
                {"class": "filter-option-header"},
                ui.span({"class": "filter-option-title"}, field),
                _apply_to_all_toggle() if is_common else ui.span(),
            ),
            ui.input_slider(
                f"filter_{_slugify(field)}",
                label=None,
                min=data_min,
                max=data_max,
                value=saved_val,
            ),
        )

    return None


def _section_heading(label: str) -> ui.Tag:
    return ui.div(
        {
            "style": "font-weight:bold; border-bottom: 1px solid #e0e0e0;"
            " padding-bottom:4px; margin-bottom:6px;"
        },
        label,
    )


def dataset_filter_modal_ui(
    db_name: str,
    df: pd.DataFrame,
    saved_filters: dict[str, Any] | None = None,
    common_fields: set[str] | None = None,
    display_name: str | None = None,
    common_field_levels: dict[str, list[str]] | None = None,
    hidden_fields: set[str] | None = None,
    regulator_display_labels: dict[str, str] | None = None,
) -> ui.Tag:
    """
    Build the filter modal for a given dataset from live metadata.

    Characteristics shared across all datasets (``common_fields``) are shown in the
    left column; dataset-specific characteristics are shown in the right column. An
    "Apply to all datasets" toggle controls whether common-characteristic changes
    propagate to every dataset or only to this one.

    :param db_name: Internal dataset key (used for filter IDs).
    :param df: Metadata DataFrame from ``vdb.query(metadata_query(db_name, ...))``.
    :param saved_filters: Previously applied filters for this dataset, used to
        pre-populate controls.
    :param common_fields: Characteristic names shared across all datasets. If
        ``None``, all characteristics are treated as dataset-specific.
    :param display_name: Human-readable dataset name used as the modal title.
        Falls back to ``db_name`` if not provided.
    :param common_field_levels: For common categorical fields, the union of factor
        levels across all active datasets. Used to populate the selectize choices
        so that valid values from other datasets remain selectable.
    :param regulator_display_labels: Maps ``locus_tag`` to ``"SYMBOL (LOCUS_TAG)"``
        display strings. When provided, a Regulator card is prepended to the Common
        Characteristics column with a combined searchable selectize.

    """
    saved = saved_filters or {}
    cf = (common_fields or set()) - {"sample_id"}
    cfl = common_field_levels or {}
    title = display_name or db_name

    common_cards: list[ui.Tag] = []
    specific_cards: list[ui.Tag] = []

    _hidden = hidden_fields or set()
    for field in df.columns:
        if field == "sample_id":
            continue
        if field in _hidden:
            continue
        is_common = field in cf
        card = _filter_control(
            field,
            df[field],
            saved.get(field),
            db_name,
            is_common=is_common,
            union_levels=cfl.get(field) if is_common else None,
        )
        if card is None:
            continue
        if is_common:
            common_cards.append(card)
        else:
            specific_cards.append(card)

    # --- regulator card (prepended to common column) ---
    regulator_card: list[ui.Tag] = []
    if regulator_display_labels is not None:
        saved_reg = saved.get("regulator_locus_tag", {})
        selected_reg = saved_reg.get("value", []) if saved_reg else []
        from_pair: tuple[str, str] | None = (
            saved_reg.get("from_pair") if saved_reg else None
        )
        apply_to_all_reg = saved_reg.get("apply_to_all", True) if saved_reg else True

        if from_pair:
            # Pairwise regulator filter is active: restrict choices to the intersection
            # of this dataset's regulators with the active filter values; show a note.
            # The selectize starts empty — the pairwise filter is implicit context,
            # not a pre-selection. The user may optionally narrow further by picking
            # from the available restricted choices.
            restricted_choices = {
                tag: label
                for tag, label in regulator_display_labels.items()
                if tag in selected_reg
            }
            regulator_card = [
                ui.div(
                    {"class": "filter-option-card"},
                    ui.div(
                        {"class": "filter-option-header"},
                        ui.span({"class": "filter-option-title"}, "Regulator"),
                    ),
                    ui.p(
                        {
                            "class": "text-muted",
                            "style": "font-size:0.8rem; margin-bottom:6px;",
                        },
                        f"Regulators are limited to the {len(selected_reg):,} common "
                        f"regulators between {from_pair[0]} and {from_pair[1]}. "
                        "To clear this, deselect the highlighted cell in the matrix.",
                    ),
                    ui.input_selectize(
                        "filter_regulator_locus_tag",
                        label=None,
                        choices=restricted_choices,
                        selected=[],
                        multiple=True,
                        options={"plugins": ["remove_button"]},
                    ),
                )
            ]
        else:
            regulator_card = [
                ui.div(
                    {"class": "filter-option-card"},
                    ui.div(
                        {"class": "filter-option-header"},
                        ui.span({"class": "filter-option-title"}, "Regulator"),
                        ui.div(
                            {"style": "display:flex; align-items:center; gap:0.5rem;"},
                            ui.input_action_button(
                                "modal_clear_regulator_filter",
                                "Clear",
                                class_="btn btn-sm btn-outline-secondary",
                            ),
                            ui.input_switch(
                                "apply_to_all_regulator_locus_tag",
                                "Apply to all datasets",
                                value=apply_to_all_reg,
                            ),
                        ),
                    ),
                    ui.input_selectize(
                        "filter_regulator_locus_tag",
                        label=None,
                        choices=regulator_display_labels,
                        selected=selected_reg,
                        multiple=True,
                        options={"plugins": ["remove_button"]},
                    ),
                )
            ]

    # --- common characteristics column ---
    if common_cards or regulator_card:
        common_col_children: list[ui.Tag] = [
            _section_heading("Common Characteristics"),
            ui.p(
                {
                    "class": "text-muted",
                    "style": "font-size:0.8rem; margin-bottom:8px;",
                },
                "These characteristics appear in every dataset.",
            ),
            *regulator_card,
            *common_cards,
        ]
    else:
        common_col_children = [
            _section_heading("Common Characteristics"),
            ui.p(
                {"class": "text-muted"},
                "No common characteristics available.",
            ),
        ]

    # --- dataset-specific characteristics column ---
    if specific_cards:
        specific_col_children: list[ui.Tag] = [
            _section_heading(f"{title} Characteristics"),
            ui.p(
                {
                    "class": "text-muted",
                    "style": "font-size:0.8rem; margin-bottom:8px;",
                },
                "These characteristics are specific to this dataset.",
            ),
            *specific_cards,
        ]
    else:
        specific_col_children = [
            _section_heading(f"{title} Characteristics"),
            ui.p(
                {"class": "text-muted"},
                "No dataset-specific characteristics available.",
            ),
        ]

    body = ui.row(
        ui.column(6, ui.div({"class": "modal-section"}, *common_col_children)),
        ui.column(6, ui.div({"class": "modal-section"}, *specific_col_children)),
    )

    return ui.modal(
        body,
        title=title,
        size="xl",
        easy_close=True,
        footer=ui.div(
            ui.input_action_button(
                "modal_reset_filters",
                "Reset",
                class_="btn btn-sm btn-outline-secondary",
            ),
            ui.input_action_button(
                "modal_apply_filters",
                "Apply Filters",
                class_="btn btn-sm btn-primary",
            ),
        ),
    )


@module.ui
def selection_sidebar_ui() -> ui.Tag:
    """Render the Active Set sidebar shell."""
    return ui.output_ui("sidebar_panel")


@module.ui
def selection_matrix_ui() -> ui.Tag:
    """Render the intersection matrix workspace."""
    return workspace_shell(
        "selection-workspace",
        header=workspace_heading("Sample Counts by Dataset"),
        body=ui.output_ui("matrix_content"),
    )


def diagonal_cell_modal_ui(display_name: str, breakdown: dict) -> ui.Tag:
    """
    Modal for diagonal matrix cells summarising sample/regulator multiplicity.

    This will either say that each sample interrogates a unique regulator,
    or provide information about which columns differentiate samples that share
    regulators.

    :param display_name: Human-readable dataset name for the modal title.
    :param breakdown: Dict produced by the multiplicity analysis in workspace.py.
        ``{"uniform": True}`` when each regulator maps to exactly one sample;
        ``{"uniform": False, "n_multi": int, "differentiating_columns": list[str]}``
        otherwise.

    """
    if breakdown.get("uniform"):
        body = ui.p("Each sample represents a unique interrogated regulator.")
    else:
        cols = breakdown.get("differentiating_columns", [])
        body = ui.div(
            ui.p(
                f"{breakdown['n_multi']:,} regulators appear in multiple samples. "
                f"Samples differ by:"
            ),
            (
                ui.tags.ul(*[ui.tags.li(c) for c in cols])
                if cols
                else ui.p(ui.tags.em("unknown columns"))
            ),
        )
    return ui.modal(
        body,
        title=display_name,
        easy_close=True,
        footer=ui.modal_button("Close"),
    )


def off_diagonal_cell_modal_ui(
    display_a: str,
    display_b: str,
    n_common: int,
) -> ui.Tag:
    """
    Modal for off-diagonal (cross-dataset) matrix cells.

    Shows the number of common regulators shared between two datasets and offers a
    button to restrict both datasets to only those regulators.

    :param display_a: Human-readable name of the first dataset.
    :param display_b: Human-readable name of the second dataset.
    :param n_common: Number of regulators shared between the two datasets.

    """
    return ui.modal(
        ui.p(
            f"{display_a} and {display_b} share ",
            ui.strong(f"{n_common:,}"),
            " regulators in common.",
        ),
        ui.p(
            {"class": "text-muted", "style": "font-size:0.85rem;"},
            "Applying the filter below will restrict both datasets to only samples "
            "whose regulator appears in both datasets.",
        ),
        easy_close=True,
        footer=ui.div(
            ui.modal_button("Close", class_="btn btn-sm btn-outline-secondary"),
            ui.input_action_button(
                "modal_select_common_regulators",
                f"Select {n_common:,} common regulators",
                class_="btn btn-sm btn-primary",
            ),
        ),
    )


__all__ = [
    "dataset_filter_modal_ui",
    "diagonal_cell_modal_ui",
    "off_diagonal_cell_modal_ui",
    "selection_sidebar_ui",
    "selection_matrix_ui",
]
