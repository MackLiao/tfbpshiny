"""Workspace server for the Select Datasets page."""

from __future__ import annotations

from logging import Logger
from typing import Any

from shiny import module, reactive, render, ui
from tfbpapi import VirtualDB

from tfbpshiny.modules.select_datasets.queries import (
    regulator_locus_tags_query,
    sample_count_query,
)
from tfbpshiny.modules.select_datasets.ui import (
    diagonal_cell_modal_ui,
    off_diagonal_cell_modal_ui,
)


@module.server
def select_datasets_workspace_server(
    input: Any,
    output: Any,
    session: Any,
    active_binding_datasets: reactive.calc,
    active_perturbation_datasets: reactive.calc,
    dataset_filters: reactive.Value[dict[str, Any]],
    vdb: VirtualDB,
    logger: Logger,
) -> None:
    """Render the sample-count matrix for all active datasets."""

    display_names: dict[str, str] = {
        db_name: vdb.get_tags(db_name).get("display_name", db_name)
        for db_name in vdb.get_datasets()
    }

    @reactive.calc
    def _active_datasets() -> list[str]:
        return active_binding_datasets() + active_perturbation_datasets()

    @reactive.calc
    def _matrix_data() -> dict[str, Any]:
        """
        Compute per-dataset regulator/sample counts and pairwise common-regulator counts
        with restricted sample counts.

        :return: Dict with keys: ``"diagonal"`` — ``{db_name: {"regulators": int,
            "samples": int}}`` ``"cross_dataset"`` — ``{(db_i, db_j):
            {"common_regulators": int, "samples_a": int, "samples_b": int}}``

        """
        active = _active_datasets()
        filters = dataset_filters()

        # --- diagonal pass: regulator sets + sample counts per dataset ---
        regulator_sets: dict[str, set[str]] = {}
        diagonal: dict[str, dict[str, int]] = {}

        for db_name in active:
            db_filters = filters.get(db_name)

            sql, params = regulator_locus_tags_query(db_name, db_filters)
            reg_df = vdb.query(sql, **params)
            regulators = set(reg_df["regulator_locus_tag"].dropna().astype(str))
            regulator_sets[db_name] = regulators

            sql, params = sample_count_query(db_name, db_filters)
            n_samples = int(vdb.query(sql, **params).iloc[0, 0])

            diagonal[db_name] = {"regulators": len(regulators), "samples": n_samples}

        # --- off-diagonal pass: common regulators + restricted sample counts ---
        cross_dataset: dict[tuple[str, str], dict[str, int]] = {}

        for i, db_a in enumerate(active):
            for db_b in active[i + 1 :]:
                common = regulator_sets[db_a] & regulator_sets[db_b]
                common_list = list(common)

                sql_a, params_a = sample_count_query(
                    db_a, filters.get(db_a), restrict_to_regulators=common_list
                )
                sql_b, params_b = sample_count_query(
                    db_b, filters.get(db_b), restrict_to_regulators=common_list
                )
                n_a = int(vdb.query(sql_a, **params_a).iloc[0, 0])
                n_b = int(vdb.query(sql_b, **params_b).iloc[0, 0])

                cross_dataset[(db_a, db_b)] = {
                    "common_regulators": len(common),
                    "samples_a": n_a,
                    "samples_b": n_b,
                }

        return {"diagonal": diagonal, "cross_dataset": cross_dataset}

    def _make_diagonal_effect(db_name: str) -> None:
        """Register a per-dataset click effect for a diagonal cell button."""
        btn_id = f"diag_{db_name}"

        @reactive.effect
        @reactive.event(input[btn_id])
        def _on_click() -> None:
            ui.modal_show(diagonal_cell_modal_ui())

    def _make_off_diagonal_effect(db_a: str, db_b: str) -> None:
        """Register per-pair click and modal-action effects for an off-diagonal cell."""
        btn_id = f"offdiag_{db_a}__{db_b}"
        apply_btn_id = "modal_select_common_regulators"

        @reactive.effect
        @reactive.event(input[btn_id])
        def _on_click() -> None:
            data = _matrix_data()
            info = data["cross_dataset"].get((db_a, db_b), {})
            n_common = info.get("common_regulators", 0)
            ui.modal_show(
                off_diagonal_cell_modal_ui(
                    display_names.get(db_a, db_a),
                    display_names.get(db_b, db_b),
                    n_common,
                )
            )

        @reactive.effect
        @reactive.event(input[apply_btn_id])
        def _on_apply_common_regulators() -> None:
            reg_sets = {}
            filters = dataset_filters()
            for db_name in (db_a, db_b):
                sql, params = regulator_locus_tags_query(db_name, filters.get(db_name))
                reg_df = vdb.query(sql, **params)
                reg_sets[db_name] = set(
                    reg_df["regulator_locus_tag"].dropna().astype(str)
                )
            common = sorted(reg_sets[db_a] & reg_sets[db_b])
            if not common:
                ui.modal_remove()
                return
            current = dict(dataset_filters())
            for db_name in (db_a, db_b):
                ds_filters = dict(current.get(db_name, {}))
                ds_filters["regulator_locus_tag"] = {
                    "type": "categorical",
                    "value": common,
                }
                current[db_name] = ds_filters
            dataset_filters.set(current)
            ui.modal_remove()

    # Track which cell effects have already been registered to avoid duplicates
    # when active_datasets changes but some datasets remain.
    _registered_effects: set[str] = set()

    @reactive.effect
    def _register_cell_effects() -> None:
        active = _active_datasets()
        for db_name in active:
            if db_name not in _registered_effects:
                _make_diagonal_effect(db_name)
                _registered_effects.add(db_name)
        for i, db_a in enumerate(active):
            for db_b in active[i + 1 :]:
                pair_id = f"{db_a}__{db_b}"
                if pair_id not in _registered_effects:
                    _make_off_diagonal_effect(db_a, db_b)
                    _registered_effects.add(pair_id)

    @render.ui
    def matrix_content() -> ui.Tag:
        active = _active_datasets()

        if not active:
            return ui.card(
                ui.card_body(
                    ui.p(
                        "Select datasets from the sidebar to view sample counts.",
                        class_="text-muted",
                    )
                )
            )

        data = _matrix_data()
        diagonal = data["diagonal"]
        cross_dataset = data["cross_dataset"]

        # --- header row ---
        header_cells = [ui.tags.th({"class": "matrix-row-header"}, "Dataset")]
        for db_name in active:
            label = display_names.get(db_name, db_name)
            header_cells.append(
                ui.tags.th(
                    {"class": "matrix-col-header"},
                    ui.div({"class": "matrix-header-name"}, label),
                )
            )

        # --- body rows ---
        body_rows: list[ui.Tag] = []
        for row_i, db_row in enumerate(active):
            cells: list[ui.Tag] = [
                ui.tags.td(
                    {"class": "matrix-row-label"}, display_names.get(db_row, db_row)
                )
            ]

            for col_i, db_col in enumerate(active):
                if col_i < row_i:
                    # lower triangle — empty
                    cells.append(ui.tags.td({"class": "matrix-cell-empty"}, ""))
                    continue

                if col_i == row_i:
                    # diagonal — regulator count + sample count
                    info = diagonal.get(db_row, {})
                    cells.append(
                        ui.tags.td(
                            {"class": "matrix-cell-diagonal"},
                            ui.input_action_button(
                                f"diag_{db_row}",
                                f"{info.get('regulators', 0):,} regulators / "
                                f"{info.get('samples', 0):,} samples",
                                class_="matrix-cell-button",
                            ),
                        )
                    )
                else:
                    # upper triangle — common regulators only
                    key = (db_row, db_col)
                    info = cross_dataset.get(key, {})
                    cells.append(
                        ui.tags.td(
                            {"class": "matrix-cell-interactive"},
                            ui.input_action_button(
                                f"offdiag_{db_row}__{db_col}",
                                f"{info.get('common_regulators', 0):,} "
                                "common regulators",
                                class_="matrix-cell-button",
                            ),
                        )
                    )

            body_rows.append(ui.tags.tr(*cells))

        return ui.tags.table(
            {"class": "matrix-summary-table"},
            ui.tags.thead(ui.tags.tr(*header_cells)),
            ui.tags.tbody(*body_rows),
        )


__all__ = ["select_datasets_workspace_server"]
