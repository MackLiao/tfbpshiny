"""TF Binding and Perturbation – Shiny app shell and module orchestration."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Literal, cast

from dotenv import load_dotenv
from shiny import App, reactive, render, ui
from tfbpapi import VirtualDB

from configure_logger import configure_logger
from tfbpshiny.data_service import (
    get_column_count,
    get_datasets,
    get_filter_options,
    get_intersection_cells,
    get_or_create_vdb,
    get_row_count,
    get_sample_count,
)
from tfbpshiny.modules.analysis_sidebar import (
    analysis_sidebar_server,
    analysis_sidebar_ui,
)
from tfbpshiny.modules.analysis_workspace import (
    analysis_workspace_server,
    analysis_workspace_ui,
)
from tfbpshiny.modules.modals import (
    categorical_input_id,
    count_active_filters,
    enforce_identifier_groups,
    identifier_mode_input_id,
    normalize_dataset_filters,
    numeric_max_input_id,
    numeric_min_input_id,
    render_dataset_config_modal,
    render_intersection_detail_modal,
    resolve_analysis_module,
    resolve_identifier_groups,
)
from tfbpshiny.modules.nav import nav_server, nav_ui
from tfbpshiny.modules.selection_matrix import (
    selection_matrix_server,
    selection_matrix_ui,
)
from tfbpshiny.modules.selection_sidebar import (
    selection_sidebar_server,
    selection_sidebar_ui,
)

# ---------------------------------------------------------------------------
# Environment / logging
# ---------------------------------------------------------------------------

if not os.getenv("DOCKER_ENV"):
    load_dotenv(dotenv_path=Path(".env"))

logger = logging.getLogger("shiny")

log_file = f"tfbpshiny_{time.strftime('%Y%m%d-%H%M%S')}.log"
log_level = int(os.getenv("TFBPSHINY_LOG_LEVEL", "10"))
handler_type = cast(
    Literal["console", "file"], os.getenv("TFBPSHINY_LOG_HANDLER", "console")
)
configure_logger(
    "shiny",
    level=log_level,
    handler_type=handler_type,
    log_file=log_file,
)

# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

app_ui = ui.page_fillable(
    ui.include_css((Path(__file__).parent / "styles" / "app.css").resolve()),
    ui.div(
        {"class": "app-container"},
        # Region A: Nav rail
        nav_ui("nav"),
        # Region B: Sidebar
        ui.output_ui("sidebar_region"),
        # Region C: Workspace
        ui.output_ui("workspace_region"),
    ),
    ui.output_ui("modal_layer"),
    padding=0,
    gap=0,
)

# ---------------------------------------------------------------------------
# Initialize VirtualDB
# ---------------------------------------------------------------------------

# note that for testing purposes in development, or quick updates in production,
# you can use the .env to direct tfbpshiny to an alternate YAML config
# with env var `VDB_CONFIG_PATH=/path/to/alternate.yaml`
_default_config = Path(__file__).parent / "brentlab_yeast_collection.yaml"
config = os.getenv("VDB_CONFIG_PATH", str(_default_config))
logger.info("VDB config path: %s", config)
vdb = VirtualDB(config)
# this will create the default views
logger.info("VDB initialized with tables: %s", vdb.tables())

# datasets has the structure {data_type:
#                               {
#                                 assay1: [db_name1, db_name2, ...],
#                                 assay2: [db_name3, ...]
#                               }
#                             }
# eg {'Binding': {"Calling Cards": ['2026 Calling cards'],
#                 "ChIP-chip": ['2004 Harbison']},
#     'Perturbation': {"Overexpression": ['2020 Hackett'], "TFKO": ['2014 Kemmeren']}}
datasets: dict[str, dict[str, list]] = {}
for db_name in vdb.get_datasets():
    datatype = vdb.get_tags(db_name).get("data_type", "Unknown")
    assay = vdb.get_tags(db_name).get("assay", "Unknown")
    datasets.setdefault(datatype, {}).setdefault(assay, []).append(db_name)

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------


def app_server(
    input: Any,
    output: Any,
    session: Any,
) -> None:
    """Create shared reactive state and call all module servers."""

    # -- Shared reactive values --
    # values: "selection", "binding", "perturbation", "composite"
    # read by: nav_server, sidebar_region, workspace_region
    # updated in: nav_server (on nav click), _emit_navigation_intent_from_modal
    active_module: reactive.Value[str] = reactive.value("selection")

    # values: list of dataset dicts with id, db_name, type, selected, tf_count, sample_count, etc.
    # read by: selection_sidebar_server, selection_matrix_server, analysis_sidebar_server, analysis_workspace_server
    # updated in: initialization, _set_dataset_selected, _handle_refresh_intersection
    datasets: reactive.Value[list[dict[str, Any]]] = reactive.value([])
    # values: bool
    # read by: selection_sidebar_server
    # updated in: initialization
    datasets_loading: reactive.Value[bool] = reactive.value(True)

    # values: "intersect", "union"
    # read by: selection_sidebar_server, selection_matrix_server
    # updated in: selection_sidebar_server (logic mode toggle)
    logic_mode: reactive.Value[str] = reactive.value("intersect")
    # values: {dataset_id: {categorical: {field: [str]}, numeric: {field: {min, max}}}}
    # read by: selection_sidebar_server, modal_layer, _selection_signature
    # updated in: _apply_config_modal_filters, _handle_clear_all_filters
    dataset_filters: reactive.Value[dict[str, Any]] = reactive.value({})
    # values: {dataset_id: list of filter option dicts}
    # read by: modal_layer, _ensure_dataset_filter_options
    # updated in: _ensure_dataset_filter_options
    filter_options_by_dataset: reactive.Value[dict[str, list[dict[str, Any]]]] = (
        reactive.value({})
    )
    # values: {dataset_id: bool}
    # read by: modal_layer
    # updated in: _ensure_dataset_filter_options
    filter_options_loading_by_dataset: reactive.Value[dict[str, bool]] = reactive.value(
        {}
    )

    # values: list of pairwise cell dicts {row, col, count}
    # read by: selection_matrix_server
    # updated in: _handle_refresh_intersection, _reset_intersection_on_signature_change
    intersection_cells: reactive.Value[list[dict[str, Any]]] = reactive.value([])
    # values: bool
    # read by: selection_matrix_server
    # updated in: _handle_refresh_intersection, _reset_intersection_on_signature_change
    has_loaded_intersection: reactive.Value[bool] = reactive.value(False)
    # values: bool
    # read by: selection_sidebar_server, selection_matrix_server
    # updated in: _handle_refresh_intersection
    intersection_loading: reactive.Value[bool] = reactive.value(False)
    # values: error string, or None
    # read by: selection_matrix_server
    # updated in: _handle_refresh_intersection, _reset_intersection_on_signature_change
    intersection_error: reactive.Value[str | None] = reactive.value(None)
    # values: JSON string (hash of selected ids + filters), or None
    # read by: _reset_intersection_on_signature_change
    # updated in: _reset_intersection_on_signature_change
    last_selection_signature: reactive.Value[str | None] = reactive.value(None)

    # values: dataset_id string when config modal is open, else None
    # read by: modal_layer, _sync_modal_include_toggle, _apply_config_modal_filters, _clear_config_modal_draft
    # updated in: _handle_open_config, _close_config_modal_from_header, _close_config_modal_from_cancel, _apply_config_modal_filters
    active_config_dataset_id: reactive.Value[str | None] = reactive.value(None)
    # values: intersection cell payload {rowDataset, colDataset, intersectionCount}, or None
    # read by: modal_layer, _emit_navigation_intent_from_modal
    # updated in: _handle_matrix_cell_click, _close_intersection_modal_from_header, _close_intersection_modal_from_footer, _emit_navigation_intent_from_modal
    intersection_detail: reactive.Value[dict[str, Any] | None] = reactive.value(None)
    # values: navigation payload {rowDataset, colDataset, intersectionCount}, or None
    # read by: (currently unused downstream)
    # updated in: _emit_navigation_intent_from_modal
    latest_navigation_intent: reactive.Value[dict[str, Any] | None] = reactive.value(
        None
    )

    # values: dict controlling analysis views; keys:
    #   view: "summary", "table", "correlation", "compare"
    #   selected_db_name, comparison_db_name: string (db names for dataset A/B)
    #   comparison_mode: bool
    #   correlation_value_column: string
    #   page: integer, page_size: integer
    #   composite_method: string, composite_filter_threshold: float, composite_filter_operator: string
    #   composite_binding_datasets, composite_perturbation_datasets: list of db name strings
    # read by: analysis_sidebar_server, analysis_workspace_server
    # updated in: analysis_sidebar_server (control inputs), _emit_navigation_intent_from_modal
    analysis_config: reactive.Value[dict[str, Any]] = reactive.value(
        {
            "view": "summary",
            "selected_db_name": "",
            "comparison_db_name": "",
            "comparison_mode": False,
            "correlation_value_column": "effect_size",
            "page": 1,
            "page_size": 25,
            "composite_method": "dto",
            "composite_filter_threshold": 1.0,
            "composite_filter_operator": "<=",
            "composite_binding_datasets": [],
            "composite_perturbation_datasets": [],
        }
    )

    # # -- Initialization --
    # try:
    #     datasets.set(get_datasets())
    #     datasets_error.set(None)
    # except Exception as error:
    #     datasets.set([])
    #     datasets_error.set(str(error))
    # finally:
    #     datasets_loading.set(False)

    # -- Internal helpers --
    def _dataset_by_id(dataset_id: str) -> dict[str, Any] | None:
        """
        Look up a dataset by its string ID from shared reactive state.

        :param dataset_id: the dataset's ``id`` field as a string
        :returns: matching dataset dict, or ``None`` if not found

        """
        return next(
            (entry for entry in datasets() if str(entry["id"]) == dataset_id), None
        )

    def _set_dataset_selected(dataset_id: str, selected: bool) -> None:
        """
        Toggle the ``selected`` flag on a single dataset and notify dependents.

        Mutates the dataset entry in-place then calls ``datasets.set()`` only
        when the flag actually changes, avoiding spurious reactive invalidations.

        :param dataset_id: the dataset's ``id`` field as a string
        :param selected: desired selection state

        """
        current = datasets()
        changed = False
        for entry in current:
            if str(entry["id"]) != dataset_id:
                continue
            if bool(entry.get("selected")) != bool(selected):
                entry["selected"] = bool(selected)
                changed = True
        if changed:
            datasets.set(list(current))

    # called in: _selected_filter_payloads, _selection_signature, _ensure_dataset_filter_options, _handle_refresh_intersection
    @reactive.calc
    def _selected_datasets() -> list[dict[str, Any]]:
        """
        Subset of ``datasets`` where ``selected`` is truthy.

        :returns: list of selected dataset dicts

        """
        return [entry for entry in datasets() if entry.get("selected")]

    # called in: _selection_signature, _handle_refresh_intersection
    @reactive.calc
    def _selected_filter_payloads() -> dict[str, dict[str, Any]]:
        """
        Build normalized filter payloads for all selected datasets.

        Reads ``dataset_filters`` and normalizes each entry into separate
        categorical and numeric sub-dicts keyed by ``db_name``, ready for the
        backend intersection API.

        :returns: dict with ``"categorical"`` and ``"numeric"`` keys, each
            mapping ``db_name`` to its filter values

        """
        selected = _selected_datasets()
        filters = dataset_filters()

        categorical_payload: dict[str, dict[str, Any]] = {}
        numeric_payload: dict[str, dict[str, Any]] = {}

        for entry in selected:
            dataset_id = str(entry["id"])
            db_name = str(entry.get("db_name"))
            normalized = normalize_dataset_filters(filters.get(dataset_id, {}))
            if normalized["categorical"]:
                categorical_payload[db_name] = normalized["categorical"]
            if normalized["numeric"]:
                numeric_payload[db_name] = normalized["numeric"]

        return {
            "categorical": categorical_payload,
            "numeric": numeric_payload,
        }

    # called in: _reset_intersection_on_signature_change
    @reactive.calc
    def _selection_signature() -> str:
        """
        Produce a stable JSON hash of the current selection and filter state.

        Used by ``_reset_intersection_on_signature_change`` to detect when the
        selection or filters have changed and the intersection matrix should be
        cleared.

        :returns: sorted JSON string encoding selected dataset IDs and active filters

        """
        selected_ids = [str(entry["id"]) for entry in _selected_datasets()]
        payloads = _selected_filter_payloads()
        return json.dumps(
            {
                "selected": selected_ids,
                "filters": payloads["categorical"],
                "numeric_filters": payloads["numeric"],
            },
            sort_keys=True,
        )

    # triggered by: _selection_signature change
    @reactive.effect
    def _reset_intersection_on_signature_change() -> None:
        """Clear intersection state whenever the selection or filter signature
        changes."""
        signature = _selection_signature()
        previous_signature = last_selection_signature()
        if previous_signature == signature:
            return

        last_selection_signature.set(signature)
        intersection_cells.set([])
        intersection_error.set(None)
        has_loaded_intersection.set(False)

    def _ensure_dataset_filter_options(dataset_id: str) -> None:
        """
        Fetch and cache filter options for a dataset if not already loaded.

        No-ops if the dataset is already present in ``filter_options_by_dataset``.
        Sets ``filter_options_loading_by_dataset`` around the fetch and falls
        back to an empty list on error.

        :param dataset_id: the dataset's ``id`` field as a string

        """
        cache = filter_options_by_dataset()
        if dataset_id in cache:
            return

        loading_map = dict(filter_options_loading_by_dataset())
        loading_map[dataset_id] = True
        filter_options_loading_by_dataset.set(loading_map)

        options: list[dict[str, Any]] = []
        try:
            dataset = _dataset_by_id(dataset_id)
            if not dataset:
                raise ValueError("Dataset no longer available")

            # Build a VirtualDB containing at least this dataset.
            selected = _selected_datasets()
            selected_db_names = [str(e.get("db_name")) for e in selected]
            ds_db_name = str(dataset.get("db_name"))
            all_db_names = sorted(set(selected_db_names + [ds_db_name]))
            vdb = get_or_create_vdb(all_db_names)

            metadata_configs = dataset.get("metadata_configs") or []
            if metadata_configs:
                meta_table = str(metadata_configs[0].get("db_name"))
            else:
                meta_table = f"{ds_db_name}_meta"

            options = get_filter_options(meta_table, vdb)
        except Exception as error:
            logger.warning(
                "Failed to load filter options for %s: %s", dataset_id, error
            )
            options = []
        finally:
            next_cache = dict(filter_options_by_dataset())
            next_cache[dataset_id] = options
            filter_options_by_dataset.set(next_cache)

            next_loading = dict(filter_options_loading_by_dataset())
            next_loading[dataset_id] = False
            filter_options_loading_by_dataset.set(next_loading)

    def _handle_open_config(dataset_id: str) -> None:
        """
        Open the filter config modal for a dataset and ensure its options are loaded.

        :param dataset_id: the dataset's ``id`` field as a string

        """
        active_config_dataset_id.set(dataset_id)
        _ensure_dataset_filter_options(dataset_id)

    def _handle_clear_all_filters() -> None:
        """Clear all active filters across all datasets."""
        dataset_filters.set({})

    def _handle_refresh_intersection() -> None:
        """
        Query the backend for intersection counts and update shared reactive state.

        Creates or reuses a VirtualDB from the selected datasets, fetches
        sample/column counts per dataset, queries pairwise intersection cells,
        and stamps ``tf_count`` back onto each dataset entry. Updates
        ``intersection_cells``, ``has_loaded_intersection``, and ``datasets``.
        Sets ``intersection_error`` on failure.

        """
        selected = _selected_datasets()
        selected_db_names = [str(entry.get("db_name")) for entry in selected]

        if not selected_db_names:
            intersection_cells.set([])
            intersection_error.set(None)
            has_loaded_intersection.set(False)
            return

        intersection_loading.set(True)
        intersection_error.set(None)

        try:
            vdb = get_or_create_vdb(selected_db_names)

            sample_counts: dict[str, int | None] = {}
            column_counts: dict[str, int | None] = {}
            for entry in selected:
                dataset_id = str(entry["id"])
                db_name = str(entry.get("db_name"))
                dataset_type = str(entry.get("type", ""))
                try:
                    # For binding datasets, count distinct samples.
                    # For perturbation datasets, each row is a sample.
                    if dataset_type == "Binding":
                        sample_counts[dataset_id] = int(get_sample_count(db_name, vdb))
                    else:
                        sample_counts[dataset_id] = int(get_row_count(db_name, vdb))
                    column_counts[dataset_id] = int(get_column_count(db_name, vdb))
                except Exception:
                    sample_counts[dataset_id] = None
                    column_counts[dataset_id] = None

            updated_datasets = []
            for entry in datasets():
                dataset_id = str(entry["id"])
                sample_count = sample_counts.get(dataset_id)
                column_count = column_counts.get(dataset_id)
                if sample_count is None:
                    updated_datasets.append(entry)
                    continue

                next_entry = dict(entry)
                next_entry["sample_count"] = sample_count
                next_entry["sample_count_known"] = True
                if column_count is not None:
                    next_entry["column_count"] = column_count
                updated_datasets.append(next_entry)

            payloads = _selected_filter_payloads()
            cells = get_intersection_cells(
                selected_db_names,
                vdb,
                filters=payloads["categorical"],
                numeric_filters=payloads["numeric"],
            )

            tf_count_by_db_name = {
                str(cell["row"]): int(cell["count"])
                for cell in cells
                if str(cell.get("row")) == str(cell.get("col"))
                and isinstance(cell.get("count"), (int, float))
            }

            final_datasets = []
            for entry in updated_datasets:
                db_name = str(entry.get("db_name"))
                if db_name not in tf_count_by_db_name:
                    final_datasets.append(entry)
                    continue

                next_entry = dict(entry)
                tf_count = int(tf_count_by_db_name[db_name])
                next_entry["tf_count"] = tf_count
                next_entry["tf_count_known"] = True
                next_entry["gene_count"] = tf_count
                final_datasets.append(next_entry)

            datasets.set(final_datasets)
            intersection_cells.set(cells)
            has_loaded_intersection.set(True)
        except Exception as error:
            intersection_cells.set([])
            intersection_error.set(str(error) or "Failed to refresh intersections")
            has_loaded_intersection.set(False)
        finally:
            intersection_loading.set(False)

    def _handle_matrix_cell_click(payload: dict[str, Any]) -> None:
        """
        Store the clicked intersection cell payload to open the detail modal.

        :param payload: dict with ``rowDataset``, ``colDataset``, and ``intersectionCount``

        """
        intersection_detail.set(payload)

    @render.ui
    def sidebar_region() -> ui.Tag:
        """Render the selection or analysis sidebar depending on the active module."""
        if active_module() == "selection":
            return selection_sidebar_ui("sel_sidebar")
        return analysis_sidebar_ui("ana_sidebar")

    @render.ui
    def workspace_region() -> ui.Tag:
        """Render the selection matrix or analysis workspace depending on the active
        module."""
        if active_module() == "selection":
            return selection_matrix_ui("sel_matrix")
        return analysis_workspace_ui("ana_workspace")

    # -- Modal rendering --
    @render.ui
    def modal_layer() -> ui.Tag:
        """
        Render the active modal overlay, or an empty span when no modal is open.

        Priority: dataset config modal > intersection detail modal > nothing.

        """
        active_dataset_id = active_config_dataset_id()
        if active_dataset_id:
            dataset = _dataset_by_id(active_dataset_id)
            if not dataset:
                return ui.span()

            return render_dataset_config_modal(
                dataset=dataset,
                filters=dataset_filters().get(active_dataset_id, {}),
                filter_options=filter_options_by_dataset().get(active_dataset_id, []),
                loading_filters=bool(
                    filter_options_loading_by_dataset().get(active_dataset_id, False)
                ),
            )

        details = intersection_detail()
        if details:
            return render_intersection_detail_modal(details)

        return ui.span()

    # -- Dataset config modal interactions --
    # triggered by: input.modal_include_dataset change
    @reactive.effect
    def _sync_modal_include_toggle() -> None:
        """Sync the dataset selection state when the include toggle in the config modal
        changes."""
        dataset_id = active_config_dataset_id()
        if not dataset_id:
            return

        try:
            include = bool(input.modal_include_dataset())
        except Exception:
            return

        _set_dataset_selected(dataset_id, include)

    # triggered by: input.modal_close_config click
    @reactive.effect
    @reactive.event(input.modal_close_config)
    def _close_config_modal_from_header() -> None:
        """Close the dataset config modal when the header close button is clicked."""
        active_config_dataset_id.set(None)

    # triggered by: input.modal_cancel_filters click
    @reactive.effect
    @reactive.event(input.modal_cancel_filters)
    def _close_config_modal_from_cancel() -> None:
        """Close the dataset config modal when the cancel button is clicked."""
        active_config_dataset_id.set(None)

    # triggered by: input.modal_clear_filters click
    @reactive.effect
    @reactive.event(input.modal_clear_filters)
    def _clear_config_modal_draft() -> None:
        """Reset all filter inputs in the config modal to their empty state."""
        dataset_id = active_config_dataset_id()
        if not dataset_id:
            return

        options = filter_options_by_dataset().get(dataset_id, [])
        for option in options:
            field = str(option.get("field"))
            kind = str(option.get("kind", "categorical"))
            if kind == "numeric":
                ui.update_text(numeric_min_input_id(field), value="")
                ui.update_text(numeric_max_input_id(field), value="")
            else:
                ui.update_selectize(categorical_input_id(field), selected=[])

        for group in resolve_identifier_groups(options):
            if group.get("has_toggle"):
                ui.update_radio_buttons(
                    identifier_mode_input_id(str(group["key"])),
                    selected="symbol",
                )

    # triggered by: input.modal_apply_filters click
    @reactive.effect
    @reactive.event(input.modal_apply_filters)
    def _apply_config_modal_filters() -> None:
        """Read filter inputs from the config modal and write them to
        ``dataset_filters``."""
        dataset_id = active_config_dataset_id()
        if not dataset_id:
            return

        options = filter_options_by_dataset().get(dataset_id, [])

        draft_categorical: dict[str, list[str]] = {}
        draft_numeric: dict[str, dict[str, Any]] = {}

        for option in options:
            field = str(option.get("field"))
            kind = str(option.get("kind", "categorical"))

            if kind == "numeric":
                min_value = None
                max_value = None
                try:
                    min_value = input[numeric_min_input_id(field)]()
                except Exception:
                    pass
                try:
                    max_value = input[numeric_max_input_id(field)]()
                except Exception:
                    pass

                draft_numeric[field] = {
                    "min_value": min_value,
                    "max_value": max_value,
                }
            else:
                try:
                    values = input[categorical_input_id(field)]()
                except Exception:
                    values = []

                if isinstance(values, (list, tuple)):
                    draft_categorical[field] = [str(value) for value in values]

        mode_map: dict[str, str] = {}
        groups = resolve_identifier_groups(options)
        for group in groups:
            if not group.get("has_toggle"):
                continue

            try:
                mode = str(input[identifier_mode_input_id(str(group["key"]))]())
            except Exception:
                mode = "symbol"
            if mode in {"symbol", "locus"}:
                mode_map[str(group["key"])] = mode

        normalized = normalize_dataset_filters(
            {
                "categorical": draft_categorical,
                "numeric": draft_numeric,
            }
        )
        enforced = enforce_identifier_groups(normalized, groups, mode_map)

        next_filters = dict(dataset_filters())
        if count_active_filters(enforced) > 0:
            next_filters[dataset_id] = enforced
        else:
            next_filters.pop(dataset_id, None)

        dataset_filters.set(next_filters)
        active_config_dataset_id.set(None)

    # -- Intersection detail modal interactions --
    # triggered by: input.modal_close_intersection click
    @reactive.effect
    @reactive.event(input.modal_close_intersection)
    def _close_intersection_modal_from_header() -> None:
        """Close the intersection detail modal when the header close button is
        clicked."""
        intersection_detail.set(None)

    # triggered by: input.modal_close_intersection_secondary click
    @reactive.effect
    @reactive.event(input.modal_close_intersection_secondary)
    def _close_intersection_modal_from_footer() -> None:
        """Close the intersection detail modal when the footer close button is
        clicked."""
        intersection_detail.set(None)

    # triggered by: input.modal_open_analysis click
    @reactive.effect
    @reactive.event(input.modal_open_analysis)
    def _emit_navigation_intent_from_modal() -> None:
        """
        Navigate to the appropriate analysis module from the intersection detail modal.

        Reads the current ``intersection_detail`` payload, resolves the target
        analysis module from the dataset types, updates ``analysis_config`` with
        the selected dataset pair in comparison mode, and sets ``active_module``.
        Also records the intent in ``latest_navigation_intent`` for debugging.

        """
        details = intersection_detail()
        if not details:
            return

        row_dataset = details.get("rowDataset", {})
        col_dataset = details.get("colDataset", {})
        intersection_count = int(details.get("intersectionCount") or 0)
        row_type = str(row_dataset.get("type", "Expression"))
        col_type = str(col_dataset.get("type", "Expression"))
        row_db_name = str(row_dataset.get("db_name", ""))
        col_db_name = str(col_dataset.get("db_name", ""))

        payload: dict[str, Any] = {
            "rowDataset": {
                "id": str(row_dataset.get("id", "")),
                "db_name": row_db_name,
                "type": row_type,
            },
            "colDataset": {
                "id": str(col_dataset.get("id", "")),
                "db_name": col_db_name,
                "type": col_type,
            },
            "intersectionCount": intersection_count,
        }

        latest_navigation_intent.set(payload)
        logger.info("Intersection navigation intent: %s", payload)

        target_module = resolve_analysis_module(row_type, col_type)

        next_analysis_config = dict(analysis_config())
        next_analysis_config.update(
            {
                # Preserve the exact modal pair as default A/B in pairwise mode.
                "selected_db_name": row_db_name,
                "comparison_db_name": col_db_name,
                "comparison_mode": True,
                "view": "summary",
                "page": 1,
            }
        )
        analysis_config.set(next_analysis_config)

        if target_module:
            active_module.set(target_module)

        ui.notification_show("Navigation intent emitted from intersection detail.")
        intersection_detail.set(None)

    # -- Module servers --
    nav_server("nav", active_module=active_module)

    selection_sidebar_server(
        "sel_sidebar",
        datasets=datasets,
        logic_mode=logic_mode,
        dataset_filters=dataset_filters,
        datasets_loading=datasets_loading,
        intersection_loading=intersection_loading,
        on_configure=_handle_open_config,
        on_refresh=_handle_refresh_intersection,
        on_clear_all_filters=_handle_clear_all_filters,
    )

    selection_matrix_server(
        "sel_matrix",
        datasets=datasets,
        logic_mode=logic_mode,
        intersection_cells=intersection_cells,
        has_loaded_intersection=has_loaded_intersection,
        intersection_loading=intersection_loading,
        intersection_error=intersection_error,
        on_cell_click=_handle_matrix_cell_click,
    )

    analysis_sidebar_server(
        "ana_sidebar",
        active_module=active_module,
        datasets=datasets,
        analysis_config=analysis_config,
    )

    analysis_workspace_server(
        "ana_workspace",
        active_module=active_module,
        datasets=datasets,
        analysis_config=analysis_config,
    )


# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------

app = App(ui=app_ui, server=app_server)
