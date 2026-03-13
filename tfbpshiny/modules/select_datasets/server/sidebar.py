"""Sidebar server for the Select Datasets page."""

from __future__ import annotations

import hashlib
from logging import Logger
from typing import Any

import faicons as fa
import pandas as pd
from shiny import module, reactive, render, ui
from tfbpapi import VirtualDB

from tfbpshiny.modules.select_datasets.queries import (
    FIELD_TYPE_OVERRIDES,
    metadata_query,
)
from tfbpshiny.modules.select_datasets.ui import dataset_filter_modal_ui


def _toggle_id(db_name: str) -> str:
    digest = hashlib.sha1(db_name.encode()).hexdigest()[:10]
    return f"ds_toggle_{digest}"


def _filter_btn_id(db_name: str) -> str:
    digest = hashlib.sha1(db_name.encode()).hexdigest()[:10]
    return f"ds_filter_{digest}"


@module.server
def select_datasets_sidebar_server(
    input: Any,
    output: Any,
    session: Any,
    vdb: VirtualDB,
    logger: Logger,
) -> tuple[
    reactive.Value[list[str]],
    reactive.Value[list[str]],
    reactive.Value[dict[str, Any]],
]:
    """
    Render dataset selection sidebar; return (active_binding_datasets,
    active_perturbation_datasets, dataset_filters).

    The sidebar has two sections: "Binding" and "Perturbation".
    Datasets are sourced from VirtualDB tags (data_type, display_name).

    """

    # dataset dict is structure
    # {<db_name>: {"data_type": "binding" or "perturbation",
    #              "display_name": str,
    #              "assay": str}, ...}
    dataset_dict: dict[str, dict[str, str]] = {}
    for db_name in vdb.get_datasets():
        tags = vdb.get_tags(db_name)
        if tags.get("data_type") in ["binding", "perturbation"]:
            dataset_dict[db_name] = tags

    # list of (db_name, display_name) tuples for the binding and perturbation sections
    binding_datasets: list[tuple[str, str]] = [
        (db_name, tags.get("display_name", db_name))
        for db_name, tags in dataset_dict.items()
        if tags.get("data_type") == "binding"
    ]
    perturbation_datasets: list[tuple[str, str]] = [
        (db_name, tags.get("display_name", db_name))
        for db_name, tags in dataset_dict.items()
        if tags.get("data_type") == "perturbation"
    ]
    # there are some common fields across datasets. In the dataset filters,
    # these common fields are displayed in their own section of the modal, and when
    # they are set on any dataset, they are applied to all datasets.
    common_fields = set(vdb.get_common_fields()) - {"sample_id"}

    # reactives
    collapsed: reactive.Value[bool] = reactive.value(False)
    # {<db_name>: {<field_name>: {"type": "categorical" or "numeric" or "bool",
    #                              "value": list[str] | [lo, hi] | bool}}}
    dataset_filters: reactive.Value[dict[str, Any]] = reactive.value({})
    # tracks which db_name's filter modal is currently open
    modal_open_for: reactive.Value[str | None] = reactive.value(None)
    # stores the DataFrame fetched when a filter modal is opened
    modal_df: reactive.Value[pd.DataFrame | None] = reactive.value(None)

    # Persistent selection state — survives UI re-renders across navigation
    _active_binding_datasets: reactive.Value[list[str]] = reactive.value([])
    _active_perturbation_datasets: reactive.Value[list[str]] = reactive.value([])
    # Per-dataset toggle state — persists so toggles restore correctly on re-render
    _toggle_state: dict[str, reactive.Value[bool]] = {
        db_name: reactive.value(False)
        for db_name, _ in binding_datasets + perturbation_datasets
    }

    @reactive.effect
    @reactive.event(input.toggle_sidebar)
    def _toggle_sidebar() -> None:
        """
        Toggle the sidebar between expanded and collapsed state.

        :trigger input.toggle_sidebar: fires when the user clicks the collapse/expand
        chevron button in the sidebar header.

        """
        collapsed.set(not collapsed())

    def _make_toggle_effect(db_name: str, data_type: str) -> None:
        @reactive.effect
        @reactive.event(input[_toggle_id(db_name)])
        def _on_toggle() -> None:
            """
            Update persistent toggle state and active-dataset list when a dataset switch
            is changed.

            :trigger input[_toggle_id(db_name)]: fires when the user flips the switch
            for this specific dataset.

            """
            try:
                val = bool(input[_toggle_id(db_name)]())
            except Exception:
                return
            _toggle_state[db_name].set(val)
            if data_type == "binding":
                current = list(_active_binding_datasets())
                if val and db_name not in current:
                    current.append(db_name)
                elif not val and db_name in current:
                    current.remove(db_name)
                _active_binding_datasets.set(current)
            else:
                current = list(_active_perturbation_datasets())
                if val and db_name not in current:
                    current.append(db_name)
                elif not val and db_name in current:
                    current.remove(db_name)
                _active_perturbation_datasets.set(current)

    for db_name, tags in dataset_dict.items():
        _make_toggle_effect(db_name, tags.get("data_type", ""))

    for _db_name, _ in binding_datasets + perturbation_datasets:

        def _make_filter_effect(db_name: str) -> None:
            @reactive.effect
            @reactive.event(input[_filter_btn_id(db_name)])
            def _open_filter_modal() -> None:
                """
                Fetch metadata, compute common-field union levels, and show the filter
                modal for this dataset.

                :trigger input[_filter_btn_id(db_name)]: fires when the user     clicks
                the Filter button on this dataset's row.

                """
                existing_filters = dataset_filters().get(db_name)
                sql, params = metadata_query(db_name, existing_filters)
                df = vdb.query(sql, **params)
                modal_open_for.set(db_name)
                modal_df.set(df)
                display_name = dataset_dict[db_name].get("display_name", db_name)

                # build union of categorical levels for each common field
                # across all active datasets, so all valid values are selectable
                all_active = (
                    _active_binding_datasets() + _active_perturbation_datasets()
                )
                common_field_levels: dict[str, list[str]] = {}
                for cf_field in common_fields:
                    if cf_field not in df.columns:
                        continue
                    col_dtype = df[cf_field].dtype
                    type_override = FIELD_TYPE_OVERRIDES.get(
                        (db_name, cf_field)
                    ) or FIELD_TYPE_OVERRIDES.get(("", cf_field))
                    override_kind = type_override[0] if type_override else None
                    if override_kind != "categorical" and col_dtype.name not in (
                        "object",
                        "category",
                    ):
                        continue
                    levels: set[str] = {str(v) for v in df[cf_field].dropna().unique()}
                    for other_db in all_active:
                        if other_db == db_name:
                            continue
                        try:
                            other_sql, other_params = metadata_query(other_db)
                            other_df = vdb.query(other_sql, **other_params)
                            if cf_field in other_df.columns:
                                levels |= {
                                    str(v) for v in other_df[cf_field].dropna().unique()
                                }
                        except Exception:
                            pass
                    common_field_levels[cf_field] = list(levels)

                ui.modal_show(
                    dataset_filter_modal_ui(
                        db_name,
                        df,
                        existing_filters,
                        common_fields,
                        display_name=display_name,
                        common_field_levels=common_field_levels,
                    )
                )

        _make_filter_effect(_db_name)

    @reactive.effect
    @reactive.event(input.modal_reset_filters)
    def _reset_filter_modal() -> None:
        """
        Clear all filters for the open dataset (and common-field filters from every
        dataset), then close the modal.

        :trigger input.modal_reset_filters: fires when the user clicks the     Reset
        button inside the filter modal.

        """
        db_name = modal_open_for()
        if db_name is not None:
            current = dict(dataset_filters())
            all_db_names = [d for d, _ in binding_datasets + perturbation_datasets]
            # clear common-field filters from every dataset
            for ds in all_db_names:
                if ds in current:
                    ds_filters = {
                        f: v for f, v in current[ds].items() if f not in common_fields
                    }
                    if ds_filters:
                        current[ds] = ds_filters
                    else:
                        current.pop(ds)
            # clear dataset-specific filters for the open dataset
            current.pop(db_name, None)
            dataset_filters.set(current)
        logger.debug(f"dataset_filters reset for {db_name}: {current}")
        ui.modal_remove()
        modal_open_for.set(None)
        modal_df.set(None)

    @reactive.effect
    @reactive.event(input.modal_apply_filters)
    def _apply_filter_modal() -> None:
        """
        Read filter inputs from the modal, persist them to ``dataset_filters``, activate
        the dataset if it was off, then close the modal.

        Common-field filters are propagated to all datasets or just this one
        according to each field's ``apply_to_all`` toggle.

        :trigger input.modal_apply_filters: fires when the user clicks the
            Apply Filters button inside the filter modal.

        """
        db_name = modal_open_for()
        df = modal_df()
        if db_name is None or df is None:
            ui.modal_remove()
            return

        field_filters: dict[str, Any] = {}
        for field in df.columns:
            if field == "sample_id":
                continue

            col = df[field]
            try:
                value = input[f"filter_{field}"]()
            except Exception:
                continue

            type_override = FIELD_TYPE_OVERRIDES.get(
                (db_name, field)
            ) or FIELD_TYPE_OVERRIDES.get(("", field))
            override_kind = type_override[0] if type_override else None

            if override_kind == "categorical" or col.dtype.name in (
                "object",
                "category",
            ):
                selected = list(value) if value else []
                if selected:
                    field_filters[field] = {"type": "categorical", "value": selected}

            elif col.dtype == "bool":
                if bool(value):
                    field_filters[field] = {"type": "bool", "value": True}

            elif col.dtype.name in ("float64", "int64", "float32", "int32"):
                if isinstance(value, (list, tuple)) and len(value) == 2:
                    non_null = col.dropna()
                    if non_null.empty:
                        continue
                    data_min = float(non_null.min())
                    data_max = float(non_null.max())
                    # single-value column: slider was artificially bumped in UI,
                    # user cannot meaningfully filter it — skip
                    if data_min == data_max:
                        continue
                    s_min, s_max = float(value[0]), float(value[1])
                    if s_min != data_min or s_max != data_max:
                        field_filters[field] = {
                            "type": "numeric",
                            "value": [s_min, s_max],
                        }

            # read per-field apply_to_all toggle for common fields
            if field in common_fields and field in field_filters:
                try:
                    apply_to_all = bool(input[f"apply_to_all_{field}"]())
                except Exception:
                    apply_to_all = False
                field_filters[field]["apply_to_all"] = apply_to_all

        # split into common-field filters and dataset-specific
        common_filters = {f: v for f, v in field_filters.items() if f in common_fields}
        specific_filters = {
            f: v for f, v in field_filters.items() if f not in common_fields
        }

        current = dict(dataset_filters())
        all_db_names = [d for d, _ in binding_datasets + perturbation_datasets]

        # apply each common filter according to its own apply_to_all flag
        for f, spec in common_filters.items():
            apply_to_all = spec.get("apply_to_all", True)
            if apply_to_all:
                for ds in all_db_names:
                    ds_filters = dict(current.get(ds, {}))
                    ds_filters[f] = spec
                    current[ds] = ds_filters
            else:
                # apply only to this dataset; clear from others
                for ds in all_db_names:
                    ds_filters = dict(current.get(ds, {}))
                    if ds == db_name:
                        ds_filters[f] = spec
                    else:
                        ds_filters.pop(f, None)
                    if ds_filters:
                        current[ds] = ds_filters
                    else:
                        current.pop(ds, None)

        # clear common fields that were removed (not in common_filters)
        for f in common_fields:
            if f not in common_filters:
                # check how this field was previously stored to decide scope of removal
                prev_spec = current.get(db_name, {}).get(f)
                prev_apply_to_all = (
                    prev_spec.get("apply_to_all", False) if prev_spec else False
                )
                targets = all_db_names if prev_apply_to_all else [db_name]
                for ds in targets:
                    ds_filters = dict(current.get(ds, {}))
                    ds_filters.pop(f, None)
                    if ds_filters:
                        current[ds] = ds_filters
                    else:
                        current.pop(ds, None)

        # apply dataset-specific filters to just this dataset
        ds_filters = dict(current.get(db_name, {}))
        ds_filters.update(specific_filters)
        # remove any specific fields that are no longer set
        for f in list(ds_filters):
            if f not in common_fields and f not in specific_filters:
                ds_filters.pop(f)
        if ds_filters:
            current[db_name] = ds_filters
        else:
            current.pop(db_name, None)

        dataset_filters.set(current)
        logger.debug(f"dataset_filters applied for {db_name}: {current}")

        # activate the dataset if it isn't already on
        if not _toggle_state[db_name]():
            _toggle_state[db_name].set(True)
            current_b = list(_active_binding_datasets())
            current_p = list(_active_perturbation_datasets())
            if db_name in [d for d, _ in binding_datasets] and db_name not in current_b:
                _active_binding_datasets.set(current_b + [db_name])
            elif (
                db_name in [d for d, _ in perturbation_datasets]
                and db_name not in current_p
            ):
                _active_perturbation_datasets.set(current_p + [db_name])

        ui.modal_remove()
        modal_open_for.set(None)
        modal_df.set(None)

    @render.ui
    def sidebar_panel() -> ui.Tag:
        """
        Full sidebar panel: header with collapse button, then Binding and
        Perturbation dataset rows with per-row toggles and Filter buttons.

        Toggle values are restored from ``_toggle_state`` so that re-renders
        (e.g. on navigation back to this page) reflect the current selection.

        :trigger collapsed: re-renders when the sidebar is collapsed or expanded.
        :trigger _toggle_state[*]: re-renders when any dataset's persistent
            toggle state changes (i.e. after ``_on_toggle`` fires).
        """
        is_collapsed = collapsed()

        search_term = ""
        if not is_collapsed:
            try:
                search_term = (input.search() or "").strip().lower()
            except Exception:
                pass

        def _dataset_row(db_name: str, label: str) -> ui.Tag:
            current_val = _toggle_state[db_name]()
            if is_collapsed:
                return ui.div(
                    {"class": "dataset-row"},
                    ui.input_switch(_toggle_id(db_name), label=None, value=current_val),
                )
            return ui.div(
                {"class": "dataset-row"},
                ui.input_switch(
                    _toggle_id(db_name),
                    label=ui.span({"class": "dataset-row-label sidebar-text"}, label),
                    value=current_val,
                ),
                ui.input_action_button(
                    _filter_btn_id(db_name),
                    "Filter",
                    class_="btn-filter-dataset",
                ),
            )

        section_tags: list[ui.Tag] = []

        visible_binding = [
            (db_name, label)
            for db_name, label in binding_datasets
            if not search_term or search_term in label.lower()
        ]
        if visible_binding:
            if not is_collapsed:
                section_tags.append(
                    ui.div({"class": "group-header sidebar-text"}, "Binding")
                )
            for db_name, label in visible_binding:
                section_tags.append(_dataset_row(db_name, label))

        visible_perturbation = [
            (db_name, label)
            for db_name, label in perturbation_datasets
            if not search_term or search_term in label.lower()
        ]
        if visible_perturbation:
            if not is_collapsed:
                section_tags.append(
                    ui.div({"class": "group-header sidebar-text"}, "Perturbation")
                )
            for db_name, label in visible_perturbation:
                section_tags.append(_dataset_row(db_name, label))

        if not section_tags:
            section_tags.append(
                ui.div(
                    {"class": "empty-state compact"},
                    ui.p("No datasets match your search."),
                )
            )

        return ui.div(
            {
                "class": "context-sidebar selection-sidebar"
                + (" collapsed" if is_collapsed else ""),
                "id": "selection-sidebar",
            },
            ui.div(
                {"class": "sidebar-header"},
                ui.div(
                    {"class": "sidebar-header-row"},
                    (
                        ui.div(
                            ui.h2("Select datasets\nfor analysis"),
                        )
                        if not is_collapsed
                        else ui.div(ui.h2("SD"))
                    ),
                    ui.input_action_button(
                        "toggle_sidebar",
                        (
                            fa.icon_svg("angles-left", width="14px", height="14px")
                            if not is_collapsed
                            else fa.icon_svg(
                                "angles-right", width="14px", height="14px"
                            )
                        ),
                        class_="btn-collapse-sidebar",
                    ),
                ),
            ),
            ui.div(
                {"class": "sidebar-body"},
                ui.div({"class": "dataset-list"}, *section_tags),
            ),
        )

    return _active_binding_datasets, _active_perturbation_datasets, dataset_filters


__all__ = ["select_datasets_sidebar_server"]
