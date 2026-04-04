"""Sidebar server for the Select Datasets page."""

from __future__ import annotations

import asyncio
import hashlib
import io
from logging import Logger
from typing import Any

import faicons as fa
import pandas as pd
from labretriever import VirtualDB
from shiny import module, reactive, render, ui

from tfbpshiny import components
from tfbpshiny.components import export_download_button
from tfbpshiny.modules.select_datasets.export import (
    ExportDataset,
    build_export_tarball,
    get_dataset_description,
)
from tfbpshiny.modules.select_datasets.queries import (
    FIELD_TYPE_OVERRIDES,
    full_data_query,
    metadata_query,
    regulator_display_labels_query,
)
from tfbpshiny.modules.select_datasets.ui import _slugify, dataset_filter_modal_ui

# Metadata fields to suppress from the filter UI, keyed by db_name.
# Fields to suppress from the filter UI. Use "*" for fields hidden across all
# datasets; use the db_name key for dataset-specific exclusions. The effective
# hidden set for a given dataset is the union of "*" and its own entry.
HIDDEN_FILTER_FIELDS: dict[str, set[str]] = {
    "*": {
        "regulator_locus_tag",
        "regulator_symbol",
        "Regulator locus tag",
        "Regulator symbol",
    },
    "callingcards": {"background_total_hops", "experiment_total_hops"},
    "harbison": {"condition"},
    "chec_m2025": {"condition", "mahendrawada_symbol"},
    "degron": {"env_condition", "timepoint"},
    "rossi": {"antibody", "growth_media"},
    "hackett": {"date", "mechanism", "restriction", "strain"},
}


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
    active_module: reactive.Value[str] | None = None,
) -> tuple[
    reactive.Calc_[list[str]],
    reactive.Calc_[list[str]],
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

    # Build description lookup from DataCard configs (via VirtualDB internals).
    # TODO: replace with a public VirtualDB method when one is available.
    descriptions: dict[str, str] = {}
    for db_name in dataset_dict:
        try:
            repo_id, config_name = vdb._db_name_map[db_name]
            card = vdb._datacards.get(repo_id)
            if card:
                cfg = card.get_config(config_name)
                if cfg and cfg.description:
                    descriptions[db_name] = cfg.description
        except (AttributeError, KeyError):
            logger.warning(
                f"Failed to fetch description for {db_name} from VirtualDB "
                "datacard config"
            )
            descriptions[db_name] = "No description available."

    # list of (db_name, display_name, description) tuples
    binding_datasets: list[tuple[str, str, str]] = [
        (db_name, tags.get("display_name", db_name), descriptions.get(db_name, ""))
        for db_name, tags in dataset_dict.items()
        if tags.get("data_type") == "binding"
    ]
    perturbation_datasets: list[tuple[str, str, str]] = [
        (db_name, tags.get("display_name", db_name), descriptions.get(db_name, ""))
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

    # Per-dataset toggle state — persists so toggles restore correctly on re-render.
    # Keys are fixed at init time and match dataset_dict keys exactly.
    _toggle_state: dict[str, reactive.Value[bool]] = {
        db_name: reactive.value(False)
        for db_name, _, _ in binding_datasets + perturbation_datasets
    }

    # Active dataset lists derived from toggle state. Using @reactive.calc
    # instead of manually maintained reactive.Value eliminates redundant writes
    # and lets Shiny coalesce rapid toggle changes within a single flush cycle.
    @reactive.calc
    def _active_binding_datasets() -> list[str]:
        """
        Binding datasets currently toggled on.

        :trigger: ``_toggle_state[db]`` for each binding dataset — re-runs
            whenever any binding toggle changes.

        """
        return [db for db, _, _ in binding_datasets if _toggle_state[db]()]

    @reactive.calc
    def _active_perturbation_datasets() -> list[str]:
        """
        Perturbation datasets currently toggled on.

        :trigger: ``_toggle_state[db]`` for each perturbation dataset — re-runs
            whenever any perturbation toggle changes.

        """
        return [db for db, _, _ in perturbation_datasets if _toggle_state[db]()]

    @reactive.effect
    @reactive.event(input.toggle_sidebar)
    def _toggle_sidebar() -> None:
        """
        Toggle the sidebar between expanded and collapsed state.

        :trigger input.toggle_sidebar: fires when the user clicks the collapse/expand
        chevron button in the sidebar header.

        """
        collapsed.set(not collapsed())

    def _make_toggle_effect(db_name: str) -> None:
        @reactive.effect
        @reactive.event(input[_toggle_id(db_name)])
        def _on_toggle() -> None:
            """
            Update persistent toggle state when a dataset switch is changed.

            The active-dataset lists are derived via ``@reactive.calc`` from
            ``_toggle_state``, so only a single write is needed here.  The
            guard avoids redundant ``.set()`` calls (e.g. when
            ``ui.update_switch`` echoes back the same value).

            :trigger input[_toggle_id(db_name)]: fires when the user flips the switch
            for this specific dataset.

            """
            try:
                val = bool(input[_toggle_id(db_name)]())
            except (KeyError, AttributeError):
                return
            with reactive.isolate():
                if _toggle_state[db_name]() == val:
                    return
            _toggle_state[db_name].set(val)

    for db_name, _, _ in binding_datasets + perturbation_datasets:
        _make_toggle_effect(db_name)

    for _db_name, _, _ in binding_datasets + perturbation_datasets:

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

                # build {locus_tag: "SYMBOL (LOCUS_TAG)"} map for regulator selectize
                reg_display_labels: dict[str, str] = {}
                try:
                    reg_sql, reg_params = regulator_display_labels_query(db_name)
                    reg_df = vdb.query(reg_sql, **reg_params)
                    for _, row in reg_df.iterrows():
                        tag = str(row["regulator_locus_tag"])
                        sym = row.get("regulator_symbol")
                        label = f"{sym} ({tag})" if sym and str(sym) != "nan" else tag
                        reg_display_labels[tag] = label
                except Exception:
                    logger.exception(
                        f"Failed to fetch regulator display labels for {db_name}"
                    )

                ui.modal_show(
                    dataset_filter_modal_ui(
                        db_name,
                        df,
                        existing_filters,
                        common_fields,
                        display_name=display_name,
                        common_field_levels=common_field_levels,
                        hidden_fields=HIDDEN_FILTER_FIELDS.get("*", set())
                        | HIDDEN_FILTER_FIELDS.get(db_name, set()),
                        regulator_display_labels=reg_display_labels or None,
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
            all_db_names = [d for d, _, _ in binding_datasets + perturbation_datasets]
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
            logger.debug(
                "dataset_filters reset for %s: %d datasets with active filters",
                db_name,
                len(current),
            )
        ui.modal_remove()
        modal_open_for.set(None)
        modal_df.set(None)

    @reactive.effect
    @reactive.event(input.modal_clear_regulator_filter)
    def _clear_regulator_filter() -> None:
        """
        Remove ``regulator_locus_tag`` from all datasets and clear the selectize in the
        open modal in place via ``ui.update_selectize``.

        :trigger input.modal_clear_regulator_filter: fires when the user clicks the
        Clear button inside the Regulator card of a filter modal.

        """
        db_name = modal_open_for()
        if db_name is None:
            return
        all_db_names = [d for d, _, _ in binding_datasets + perturbation_datasets]
        current = dict(dataset_filters())
        for ds in all_db_names:
            ds_filters = dict(current.get(ds, {}))
            ds_filters.pop("regulator_locus_tag", None)
            if ds_filters:
                current[ds] = ds_filters
            else:
                current.pop(ds, None)
        dataset_filters.set(current)
        # clear the selectize in place — no modal teardown/re-show needed
        ui.update_selectize("filter_regulator_locus_tag", selected=[])

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
                value = input[f"filter_{_slugify(field)}"]()
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
                    apply_to_all = bool(input[f"apply_to_all_{_slugify(field)}"]())
                except Exception:
                    apply_to_all = False
                field_filters[field]["apply_to_all"] = apply_to_all

        # handle regulator_locus_tag explicitly (hidden from generic field loop)
        try:
            reg_selected = list(input["filter_regulator_locus_tag"]())
        except Exception:
            reg_selected = []
        try:
            reg_apply_to_all = bool(input["apply_to_all_regulator_locus_tag"]())
        except Exception:
            reg_apply_to_all = True
        if reg_selected:
            saved_reg = (
                dataset_filters().get(db_name, {}).get("regulator_locus_tag", {})
            )
            from_pair = saved_reg.get("from_pair") if saved_reg else None
            reg_spec: dict[str, Any] = {
                "type": "categorical",
                "value": reg_selected,
                "apply_to_all": reg_apply_to_all,
            }
            if from_pair:
                reg_spec["from_pair"] = from_pair
            field_filters["regulator_locus_tag"] = reg_spec

        # split into common-field filters and dataset-specific
        # regulator_locus_tag is treated as a common field for propagation purposes
        reg_filter = field_filters.pop("regulator_locus_tag", None)
        common_filters = {f: v for f, v in field_filters.items() if f in common_fields}
        specific_filters = {
            f: v for f, v in field_filters.items() if f not in common_fields
        }

        current = dict(dataset_filters())
        all_db_names = [d for d, _, _ in binding_datasets + perturbation_datasets]

        # apply regulator filter (or clear it if empty)
        if reg_filter:
            if reg_filter.get("apply_to_all", True):
                for ds in all_db_names:
                    ds_filters = dict(current.get(ds, {}))
                    ds_filters["regulator_locus_tag"] = reg_filter
                    current[ds] = ds_filters
            else:
                for ds in all_db_names:
                    ds_filters = dict(current.get(ds, {}))
                    if ds == db_name:
                        ds_filters["regulator_locus_tag"] = reg_filter
                    else:
                        ds_filters.pop("regulator_locus_tag", None)
                    if ds_filters:
                        current[ds] = ds_filters
                    else:
                        current.pop(ds, None)
        else:
            # regulator field was cleared — remove from all datasets
            for ds in all_db_names:
                ds_filters = dict(current.get(ds, {}))
                ds_filters.pop("regulator_locus_tag", None)
                if ds_filters:
                    current[ds] = ds_filters
                else:
                    current.pop(ds, None)

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
        logger.debug(
            "dataset_filters applied for %s: %d fields set",
            db_name,
            len(ds_filters),
        )

        # activate the dataset if it isn't already on — the @reactive.calc
        # will automatically include it in the active list.
        # _toggle_state is set first; ui.update_switch syncs the DOM.
        # _on_toggle will fire from the DOM update but the isolate() guard
        # prevents a redundant set() call.
        if not _toggle_state[db_name]():
            _toggle_state[db_name].set(True)
            ui.update_switch(_toggle_id(db_name), value=True)

        ui.modal_remove()
        modal_open_for.set(None)
        modal_df.set(None)

    @render.download(
        filename=lambda: "tfbpshiny_export.tar.gz",
        media_type="application/gzip",
    )
    async def export_datasets():
        """
        Build and stream a .tar.gz archive of all active datasets.

        The tarball is built in a worker thread via ``asyncio.to_thread`` so
        the Shiny event loop stays responsive.  A ``ui.Progress`` bar shows
        live per-dataset progress via an ``asyncio.Queue`` bridged from the
        worker thread with ``call_soon_threadsafe``.

        :trigger: ``input.export_datasets`` — fires when the user clicks the
            Export Selected Datasets download button.

        """
        all_active = _active_binding_datasets() + _active_perturbation_datasets()
        if not all_active:
            return

        filters = dataset_filters()
        n = len(all_active)

        # Build ExportDataset specs (SQL + params, not DataFrames)
        export_list: list[ExportDataset] = []
        for db_name in all_active:
            ds_filters = filters.get(db_name)
            display_name = dataset_dict[db_name].get("display_name", db_name)

            meta_sql, meta_params = metadata_query(db_name, ds_filters)
            data_sql, data_params = full_data_query(db_name, ds_filters)
            description = get_dataset_description(vdb, db_name)

            export_list.append(
                ExportDataset(
                    display_name=display_name,
                    metadata_sql=meta_sql,
                    metadata_params=meta_params,
                    data_sql=data_sql,
                    data_params=data_params,
                    description=description,
                )
            )

        # asyncio.Queue bridged from the worker thread for live progress.
        # A None sentinel signals that the build is complete.
        progress_q: asyncio.Queue[str | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _on_dataset_done(name: str) -> None:
            loop.call_soon_threadsafe(progress_q.put_nowait, name)

        def _build_and_signal() -> io.BytesIO:
            try:
                return build_export_tarball(export_list, vdb, _on_dataset_done)
            finally:
                loop.call_soon_threadsafe(progress_q.put_nowait, None)

        with ui.Progress(min=0, max=n, session=session) as progress:
            progress.set(0, message="Preparing export...")

            build_task = asyncio.create_task(asyncio.to_thread(_build_and_signal))

            # Consume progress items until the sentinel arrives
            done = 0
            while True:
                name = await progress_q.get()
                if name is None:
                    break
                done += 1
                progress.set(
                    done,
                    message=f"Packaged {name}",
                    detail=f"{done} of {n}",
                )

            try:
                buf = await build_task
            except Exception:
                logger.exception("Export tarball build failed")
                return

            progress.set(n, message="Download ready")

        # Yield chunks from the in-memory buffer
        while chunk := buf.read(65536):
            yield chunk

    @render.ui
    def sidebar_panel() -> ui.Tag:
        """
        Full sidebar panel: header with collapse button, then Binding and
        Perturbation dataset rows with per-row toggles and Filter buttons.

        Toggle values are restored from ``_toggle_state`` so that re-renders
        (e.g. on navigation back to this page) reflect the current selection.

        :trigger collapsed: re-renders when the sidebar is collapsed or expanded.
        :trigger input.search: re-renders when the search input changes.

        Toggle state is read with ``reactive.isolate()`` so that toggling a
        dataset does NOT trigger a full sidebar re-render.  The
        ``ui.input_switch`` widget manages its own client-side state after
        initial render; programmatic state changes are synced via
        ``ui.update_switch`` in a separate effect.

        :trigger active_module: re-renders on page navigation so that
            toggle values are refreshed from ``_toggle_state`` when the
            user returns to the Select Datasets page.
        """
        # Read active_module to invalidate on navigation; the sidebar only
        # renders when active_module == "selection", but we re-compute on
        # every navigation change so toggle values are always fresh when the
        # user returns to this page.  Re-renders while the output element is
        # absent are deferred by Shiny until the element reappears.
        if active_module is not None:
            active_module()
        is_collapsed = collapsed()

        search_term = ""
        if not is_collapsed:
            try:
                search_term = (input.search() or "").strip().lower()
            except Exception:
                pass

        def _dataset_row(db_name: str, label: str, description: str) -> ui.Tag:
            # isolate: read current value without creating a reactive dependency
            with reactive.isolate():
                current_val = _toggle_state[db_name]()
            if is_collapsed:
                return ui.div(
                    {"class": "dataset-row"},
                    ui.input_switch(_toggle_id(db_name), label=None, value=current_val),
                )
            label_span = ui.span({"class": "dataset-row-label sidebar-text"}, label)
            if description:
                label_span = components.tooltip(
                    label_span, description, placement="right"
                )
            return ui.div(
                {"class": "dataset-row"},
                ui.input_switch(
                    _toggle_id(db_name),
                    label=label_span,
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
            (db_name, label, desc)
            for db_name, label, desc in binding_datasets
            if not search_term or search_term in label.lower()
        ]
        if visible_binding:
            if not is_collapsed:
                section_tags.append(
                    ui.div({"class": "group-header sidebar-text"}, "Binding")
                )
            for db_name, label, desc in visible_binding:
                section_tags.append(_dataset_row(db_name, label, desc))

        visible_perturbation = [
            (db_name, label, desc)
            for db_name, label, desc in perturbation_datasets
            if not search_term or search_term in label.lower()
        ]
        if visible_perturbation:
            if not is_collapsed:
                section_tags.append(
                    ui.div({"class": "group-header sidebar-text"}, "Perturbation")
                )
            for db_name, label, desc in visible_perturbation:
                section_tags.append(_dataset_row(db_name, label, desc))

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
            ui.output_ui("sidebar_footer"),
        )

    @render.ui
    def sidebar_footer() -> ui.TagChild:
        """
        Export button footer — rendered independently so it can react to active-dataset
        changes without triggering a full sidebar re-render.

        :trigger: ``_active_binding_datasets``, ``_active_perturbation_datasets``,
            ``collapsed`` — re-renders when active datasets or collapse state change.

        """
        has_active = bool(_active_binding_datasets() or _active_perturbation_datasets())
        is_collapsed = collapsed()
        if has_active and not is_collapsed:
            return ui.div(
                {"class": "sidebar-footer"},
                export_download_button("export_datasets"),
            )
        return None

    return _active_binding_datasets, _active_perturbation_datasets, dataset_filters


__all__ = ["select_datasets_sidebar_server"]
