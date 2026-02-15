"""Selection matrix – Intersection Summary table."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any

from shiny import module, reactive, render, ui


@module.ui
def selection_matrix_ui() -> ui.Tag:
    """Render the intersection matrix workspace."""
    return ui.div(
        {"class": "main-workspace", "id": "selection-workspace"},
        ui.div(
            {"class": "workspace-header"},
            ui.h1("Intersection Summary"),
        ),
        ui.div(
            {"class": "workspace-body"},
            ui.output_ui("matrix_content"),
        ),
    )


@module.server
def selection_matrix_server(
    input: Any,
    output: Any,
    session: Any,
    datasets: reactive.Value[list[dict[str, Any]]],
    logic_mode: reactive.Value[str],
    intersection_cells: reactive.Value[list[dict[str, Any]]],
    has_loaded_intersection: reactive.Value[bool],
    intersection_loading: reactive.Value[bool],
    intersection_error: reactive.Value[str | None],
    on_cell_click: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    """Render matrix states and emit cell-click payloads."""

    cell_click_counts: reactive.Value[dict[str, int]] = reactive.value({})

    def _cell_key(row_db: str, col_db: str) -> str:
        return f"{row_db}::{col_db}"

    def _cell_button_id(row_id: str, col_id: str) -> str:
        raw = f"{row_id}::{col_id}"
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
        return f"matrix_cell_{digest}"

    @reactive.calc
    def _active_datasets() -> list[dict[str, Any]]:
        return [entry for entry in datasets() if entry.get("selected")]

    @reactive.calc
    def _cell_map() -> dict[str, int | None]:
        cells = intersection_cells()
        mapping: dict[str, int | None] = {}

        for cell in cells:
            row = str(cell.get("row"))
            col = str(cell.get("col"))
            count = cell.get("count")
            normalized_count = int(count) if isinstance(count, (int, float)) else None
            mapping[_cell_key(row, col)] = normalized_count
            mapping[_cell_key(col, row)] = normalized_count

        return mapping

    @reactive.calc
    def _diagonal_tf_map() -> dict[str, int]:
        diagonal: dict[str, int] = {}
        for cell in intersection_cells():
            row = str(cell.get("row"))
            col = str(cell.get("col"))
            count = cell.get("count")
            if row == col and isinstance(count, (int, float)):
                diagonal[row] = int(count)
        return diagonal

    @reactive.calc
    def _max_off_diagonal() -> int:
        active = _active_datasets()
        cell_map = _cell_map()

        values: list[int] = []
        for i, row_dataset in enumerate(active):
            row_db = str(row_dataset.get("db_name") or row_dataset.get("dbName"))
            for j, col_dataset in enumerate(active):
                if j <= i:
                    continue
                col_db = str(col_dataset.get("db_name") or col_dataset.get("dbName"))
                value = cell_map.get(_cell_key(row_db, col_db))
                if isinstance(value, int):
                    values.append(value)

        return max(values) if values else 1

    @reactive.effect
    def _watch_cell_clicks() -> None:
        active = _active_datasets()
        cell_map = _cell_map()
        current_counts = dict(cell_click_counts())

        for row_index, row_dataset in enumerate(active):
            row_id = str(row_dataset.get("id"))
            row_db = str(row_dataset.get("db_name") or row_dataset.get("dbName"))

            for col_index, col_dataset in enumerate(active):
                if col_index <= row_index:
                    continue

                col_id = str(col_dataset.get("id"))
                col_db = str(col_dataset.get("db_name") or col_dataset.get("dbName"))
                value = cell_map.get(_cell_key(row_db, col_db))
                if value is None:
                    continue

                button_id = _cell_button_id(row_id, col_id)
                try:
                    clicks = int(input[button_id]())
                except Exception:
                    continue

                prev_clicks = int(current_counts.get(button_id, 0))
                if clicks > prev_clicks:
                    current_counts[button_id] = clicks
                    cell_click_counts.set(current_counts)

                    if on_cell_click:
                        payload = {
                            "rowDataset": {
                                "id": row_id,
                                "dbName": row_db,
                                "type": row_dataset.get("type", "Expression"),
                                "name": row_dataset.get("name", row_db),
                                "tfCount": int(
                                    row_dataset.get("tf_count")
                                    or row_dataset.get("tfCount")
                                    or 0
                                ),
                                "tf_count": int(
                                    row_dataset.get("tf_count")
                                    or row_dataset.get("tfCount")
                                    or 0
                                ),
                            },
                            "colDataset": {
                                "id": col_id,
                                "dbName": col_db,
                                "type": col_dataset.get("type", "Expression"),
                                "name": col_dataset.get("name", col_db),
                                "tfCount": int(
                                    col_dataset.get("tf_count")
                                    or col_dataset.get("tfCount")
                                    or 0
                                ),
                                "tf_count": int(
                                    col_dataset.get("tf_count")
                                    or col_dataset.get("tfCount")
                                    or 0
                                ),
                            },
                            "intersectionCount": int(value),
                        }
                        on_cell_click(payload)
                    return

    @render.ui
    def matrix_content() -> ui.Tag:
        active = _active_datasets()

        if intersection_loading() and not has_loaded_intersection():
            return ui.div(
                {"class": "empty-state"},
                ui.h3("Downloading selected datasets..."),
            )

        if not active:
            return ui.div(
                {"class": "empty-state"},
                ui.h3("No datasets selected"),
                ui.p("Select datasets from the sidebar to view intersections."),
            )

        if intersection_error():
            return ui.div(
                {"class": "empty-state"},
                ui.h3("Failed to load selection data"),
                ui.p(str(intersection_error())),
            )

        if not has_loaded_intersection():
            return ui.div(
                {"class": "empty-state"},
                ui.h3("Dataset metadata is ready"),
                ui.p(
                    "Click Refresh Matrix to preload files and compute intersections."
                ),
            )

        cell_map = _cell_map()
        diagonal_tf_map = _diagonal_tf_map()
        max_value = _max_off_diagonal()

        def _bucket(value: int | None) -> int:
            if value is None:
                return 0
            if max_value <= 0:
                return 1
            scaled = int((value / max_value) * 5)
            return max(1, min(5, scaled))

        header_cells = [
            ui.tags.th(
                {"class": "matrix-row-header"},
                "Dataset Pair",
            )
        ]

        for dataset in active:
            db_name = str(dataset.get("db_name") or dataset.get("dbName"))
            tf_count = int(diagonal_tf_map.get(db_name, 0))
            header_cells.append(
                ui.tags.th(
                    {"class": "matrix-col-header"},
                    ui.div(
                        {"class": "matrix-header-name"},
                        str(dataset.get("name", db_name)),
                    ),
                    ui.div({"class": "matrix-header-meta"}, f"{tf_count:,} TFs"),
                )
            )

        body_rows: list[ui.Tag] = []
        for row_index, row_dataset in enumerate(active):
            row_name = str(row_dataset.get("name", "Dataset"))
            row_db = str(row_dataset.get("db_name") or row_dataset.get("dbName"))
            row_id = str(row_dataset.get("id"))

            cells: list[ui.Tag] = [
                ui.tags.td(
                    {"class": "matrix-row-label"},
                    row_name,
                )
            ]

            for col_index, col_dataset in enumerate(active):
                col_db = str(col_dataset.get("db_name") or col_dataset.get("dbName"))
                col_id = str(col_dataset.get("id"))

                if col_index < row_index:
                    cells.append(ui.tags.td({"class": "matrix-cell-empty"}, ""))
                    continue

                value = cell_map.get(_cell_key(row_db, col_db))
                is_diagonal = row_index == col_index

                if is_diagonal:
                    cells.append(
                        ui.tags.td(
                            {"class": "matrix-cell-diagonal"},
                            ("N/A" if value is None else f"{value:,}"),
                        )
                    )
                    continue

                if value is None:
                    cells.append(
                        ui.tags.td(
                            {"class": "matrix-cell-na"},
                            "N/A",
                        )
                    )
                    continue

                button_id = _cell_button_id(row_id, col_id)
                cells.append(
                    ui.tags.td(
                        {"class": "matrix-cell-interactive"},
                        ui.input_action_button(
                            button_id,
                            f"{value:,}",
                            class_=(
                                "matrix-cell-button"
                                f" matrix-intensity-{_bucket(value)}"
                            ),
                        ),
                    )
                )

            body_rows.append(ui.tags.tr(*cells))

        refresh_badge = (
            ui.div({"class": "matrix-refreshing-badge"}, "Refreshing...")
            if intersection_loading() and has_loaded_intersection()
            else ui.span()
        )

        return ui.div(
            {"class": "card intersection-summary-card"},
            ui.div(
                {"class": "intersection-summary-header"},
                ui.div(
                    ui.h2("Intersection Summary"),
                    ui.div(
                        {"class": "intersection-summary-subtitle"},
                        f"{len(active)} datasets · "
                        f"{'AND' if logic_mode() == 'intersect' else 'OR'} mode",
                    ),
                ),
                refresh_badge,
            ),
            ui.div(
                {"class": "matrix-table-wrap"},
                ui.tags.table(
                    {"class": "matrix-table matrix-summary-table"},
                    ui.tags.thead(ui.tags.tr(*header_cells)),
                    ui.tags.tbody(*body_rows),
                ),
            ),
        )
