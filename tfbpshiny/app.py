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

from configure_logger import configure_logger
from tfbpshiny.mock_data import (
    get_mock_datasets,
    get_mock_filter_options,
    get_mock_intersection_cells,
    get_mock_row_count,
    sync_mock_active_set_config,
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
# Server
# ---------------------------------------------------------------------------


def app_server(
    input: Any,
    output: Any,
    session: Any,
) -> None:
    """Create shared reactive state and call all module servers."""

    # -- Shared reactive values --
    active_module: reactive.Value[str] = reactive.value("selection")

    datasets: reactive.Value[list[dict[str, Any]]] = reactive.value([])
    datasets_loading: reactive.Value[bool] = reactive.value(True)
    datasets_error: reactive.Value[str | None] = reactive.value(None)

    logic_mode: reactive.Value[str] = reactive.value("intersect")
    dataset_filters: reactive.Value[dict[str, Any]] = reactive.value({})
    filter_options_by_dataset: reactive.Value[dict[str, list[dict[str, Any]]]] = (
        reactive.value({})
    )
    filter_options_loading_by_dataset: reactive.Value[dict[str, bool]] = reactive.value(
        {}
    )

    intersection_cells: reactive.Value[list[dict[str, Any]]] = reactive.value([])
    has_loaded_intersection: reactive.Value[bool] = reactive.value(False)
    intersection_loading: reactive.Value[bool] = reactive.value(False)
    intersection_error: reactive.Value[str | None] = reactive.value(None)
    last_selection_signature: reactive.Value[str | None] = reactive.value(None)

    active_config_dataset_id: reactive.Value[str | None] = reactive.value(None)
    intersection_detail: reactive.Value[dict[str, Any] | None] = reactive.value(None)
    latest_navigation_intent: reactive.Value[dict[str, Any] | None] = reactive.value(
        None
    )

    analysis_config: reactive.Value[dict[str, Any]] = reactive.value(
        {
            "view": "table",
            "selected_db_name": "",
            "comparison_db_name": "",
            "comparison_mode": False,
            "p_value": 0.05,
            "log2fc_threshold": 1.0,
            "correlation_value_column": "effect_size",
            "correlation_group_by": "regulator",
            "page": 1,
            "page_size": 25,
        }
    )

    # -- Initialization --
    try:
        datasets.set(get_mock_datasets())
        datasets_error.set(None)
    except Exception as error:
        datasets.set([])
        datasets_error.set(str(error))
    finally:
        datasets_loading.set(False)

    # -- Internal helpers --
    def _dataset_by_id(dataset_id: str) -> dict[str, Any] | None:
        return next(
            (entry for entry in datasets() if str(entry["id"]) == dataset_id), None
        )

    def _set_dataset_selected(dataset_id: str, selected: bool) -> None:
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

    @reactive.calc
    def _selected_datasets() -> list[dict[str, Any]]:
        return [entry for entry in datasets() if entry.get("selected")]

    @reactive.calc
    def _selected_filter_payloads() -> dict[str, dict[str, Any]]:
        selected = _selected_datasets()
        filters = dataset_filters()

        categorical_payload: dict[str, dict[str, Any]] = {}
        numeric_payload: dict[str, dict[str, Any]] = {}

        for entry in selected:
            dataset_id = str(entry["id"])
            db_name = str(entry.get("db_name") or entry.get("dbName"))
            normalized = normalize_dataset_filters(filters.get(dataset_id, {}))
            if normalized["categorical"]:
                categorical_payload[db_name] = normalized["categorical"]
            if normalized["numeric"]:
                numeric_payload[db_name] = normalized["numeric"]

        return {
            "categorical": categorical_payload,
            "numeric": numeric_payload,
        }

    @reactive.calc
    def _selection_signature() -> str:
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

    # Matrix reset behavior parity when selection/filter signature changes.
    @reactive.effect
    def _reset_intersection_on_signature_change() -> None:
        signature = _selection_signature()
        previous_signature = last_selection_signature()
        if previous_signature == signature:
            return

        last_selection_signature.set(signature)
        intersection_cells.set([])
        intersection_error.set(None)
        has_loaded_intersection.set(False)

    def _ensure_dataset_filter_options(dataset_id: str) -> None:
        cache = filter_options_by_dataset()
        if dataset_id in cache:
            return

        loading_map = dict(filter_options_loading_by_dataset())
        loading_map[dataset_id] = True
        filter_options_loading_by_dataset.set(loading_map)

        options: list[dict[str, Any]] = []
        try:
            selected_ids = [str(entry["id"]) for entry in _selected_datasets()]
            sync_ids = sorted(set(selected_ids + [dataset_id]))
            sync_mock_active_set_config(sync_ids)

            dataset = _dataset_by_id(dataset_id)
            if not dataset:
                raise ValueError("Dataset no longer available")

            metadata_configs = (
                dataset.get("metadata_configs") or dataset.get("metadataConfigs") or []
            )
            if metadata_configs:
                meta_table = str(
                    metadata_configs[0].get("dbName")
                    or metadata_configs[0].get("db_name")
                )
            else:
                meta_table = f"{dataset.get('db_name')}_meta"

            options = get_mock_filter_options(meta_table)
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
        active_config_dataset_id.set(dataset_id)
        _ensure_dataset_filter_options(dataset_id)

    def _handle_clear_all_filters() -> None:
        dataset_filters.set({})

    def _handle_refresh_intersection() -> None:
        selected = _selected_datasets()
        selected_ids = [str(entry["id"]) for entry in selected]
        selected_db_names = [
            str(entry.get("db_name") or entry.get("dbName")) for entry in selected
        ]

        if not selected_ids:
            intersection_cells.set([])
            intersection_error.set(None)
            has_loaded_intersection.set(False)
            return

        intersection_loading.set(True)
        intersection_error.set(None)

        try:
            sync_mock_active_set_config(selected_ids)

            row_counts: dict[str, int | None] = {}
            for entry in selected:
                dataset_id = str(entry["id"])
                db_name = str(entry.get("db_name") or entry.get("dbName"))
                try:
                    row_counts[dataset_id] = int(get_mock_row_count(db_name))
                except Exception:
                    row_counts[dataset_id] = None

            updated_datasets = []
            for entry in datasets():
                dataset_id = str(entry["id"])
                count = row_counts.get(dataset_id)
                if count is None:
                    updated_datasets.append(entry)
                    continue

                next_entry = dict(entry)
                next_entry["sample_count"] = count
                next_entry["sampleCount"] = count
                next_entry["sample_count_known"] = True
                next_entry["sampleCountKnown"] = True
                updated_datasets.append(next_entry)

            payloads = _selected_filter_payloads()
            cells = get_mock_intersection_cells(
                selected_db_names,
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
                db_name = str(entry.get("db_name") or entry.get("dbName"))
                if db_name not in tf_count_by_db_name:
                    final_datasets.append(entry)
                    continue

                next_entry = dict(entry)
                tf_count = int(tf_count_by_db_name[db_name])
                next_entry["tf_count"] = tf_count
                next_entry["tfCount"] = tf_count
                next_entry["tf_count_known"] = True
                next_entry["tfCountKnown"] = True
                # Keep legacy alias in sync for old summary uses.
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
        intersection_detail.set(payload)

    @reactive.calc
    def _combined_selection_error() -> str | None:
        return datasets_error() or intersection_error()

    @render.ui
    def sidebar_region() -> ui.Tag:
        if active_module() == "selection":
            return selection_sidebar_ui("sel_sidebar")
        return analysis_sidebar_ui("ana_sidebar")

    @render.ui
    def workspace_region() -> ui.Tag:
        if active_module() == "selection":
            return selection_matrix_ui("sel_matrix")
        return analysis_workspace_ui("ana_workspace")

    # -- Modal rendering --
    @render.ui
    def modal_layer() -> ui.Tag:
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
    @reactive.effect
    def _sync_modal_include_toggle() -> None:
        dataset_id = active_config_dataset_id()
        if not dataset_id:
            return

        try:
            include = bool(input.modal_include_dataset())
        except Exception:
            return

        _set_dataset_selected(dataset_id, include)

    @reactive.effect
    @reactive.event(input.modal_close_config)
    def _close_config_modal_from_header() -> None:
        active_config_dataset_id.set(None)

    @reactive.effect
    @reactive.event(input.modal_cancel_filters)
    def _close_config_modal_from_cancel() -> None:
        active_config_dataset_id.set(None)

    @reactive.effect
    @reactive.event(input.modal_clear_filters)
    def _clear_config_modal_draft() -> None:
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

    @reactive.effect
    @reactive.event(input.modal_apply_filters)
    def _apply_config_modal_filters() -> None:
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
    @reactive.effect
    @reactive.event(input.modal_close_intersection)
    def _close_intersection_modal_from_header() -> None:
        intersection_detail.set(None)

    @reactive.effect
    @reactive.event(input.modal_close_intersection_secondary)
    def _close_intersection_modal_from_footer() -> None:
        intersection_detail.set(None)

    @reactive.effect
    @reactive.event(input.modal_open_analysis)
    def _emit_navigation_intent_from_modal() -> None:
        details = intersection_detail()
        if not details:
            return

        row_dataset = details.get("rowDataset", {})
        col_dataset = details.get("colDataset", {})
        intersection_count = int(details.get("intersectionCount") or 0)
        row_type = str(row_dataset.get("type", "Expression"))
        col_type = str(col_dataset.get("type", "Expression"))
        row_db_name = str(row_dataset.get("dbName", ""))
        col_db_name = str(col_dataset.get("dbName", ""))

        payload: dict[str, Any] = {
            "rowDataset": {
                "id": str(row_dataset.get("id", "")),
                "dbName": row_db_name,
                "type": row_type,
            },
            "colDataset": {
                "id": str(col_dataset.get("id", "")),
                "dbName": col_db_name,
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
                "view": "compare",
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
        intersection_error=_combined_selection_error,
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
