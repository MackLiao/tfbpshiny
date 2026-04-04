"""Workspace server for the Select Datasets page."""

from __future__ import annotations

import time
from logging import Logger
from typing import Any

from labretriever import VirtualDB
from shiny import module, reactive, render, ui

from tfbpshiny.components import (
    matrix_cell,
    matrix_cell_button,
    matrix_header_cell,
    matrix_row_label,
    matrix_table,
)
from tfbpshiny.modules.select_datasets.queries import (
    regulator_breakdown_query,
    regulator_locus_tags_query,
    sample_count_query,
)
from tfbpshiny.modules.select_datasets.server.sidebar import HIDDEN_FILTER_FIELDS
from tfbpshiny.modules.select_datasets.ui import (
    diagonal_cell_modal_ui,
    off_diagonal_cell_modal_ui,
)


@module.server
def select_datasets_workspace_server(
    input: Any,
    output: Any,
    session: Any,
    active_binding_datasets: reactive.Calc_[list[str]],
    active_perturbation_datasets: reactive.Calc_[list[str]],
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
        """
        Combined list of all currently active binding and perturbation datasets.

        :trigger: ``active_binding_datasets``, ``active_perturbation_datasets`` —
            re-runs whenever either list changes.
        :returns: Concatenated list of active db_name strings, binding first.

        """
        return active_binding_datasets() + active_perturbation_datasets()

    # Debounced version of _active_datasets — waits for rapid toggle clicks to
    # settle before propagating to expensive downstream computations.
    # Uses Shiny-native reactive.invalidate_later() instead of asyncio tasks so
    # that all invalidation runs inside Shiny's reactive session context.
    _settled_datasets: reactive.Value[list[str]] = reactive.value([])
    _last_seen: list[str] = []
    _debounce_start: float | None = None
    _DEBOUNCE_SECONDS = 0.3
    _MAX_DEBOUNCE_SECONDS = 2.0

    @reactive.effect
    def _debounce_active_datasets() -> None:
        """
        Coalesce rapid active-dataset changes into a single update after a quiet period.

        How it works: when ``_active_datasets`` changes, the new value is
        captured in ``_last_seen`` and ``reactive.invalidate_later`` schedules
        this effect to re-run after ``_DEBOUNCE_SECONDS``.  If
        ``_active_datasets`` changes again before the timer fires, the effect
        re-runs immediately (resetting the timer).  When the timer fires and
        ``_active_datasets`` has not changed since, the value is propagated to
        ``_settled_datasets``.

        Special cases:
        - First activation (empty → non-empty): flushes immediately.
        - Starvation cap: if the user keeps toggling for longer than
          ``_MAX_DEBOUNCE_SECONDS``, the current value is flushed.

        :trigger: ``_active_datasets`` — re-runs on every toggle change.

        """
        nonlocal _last_seen, _debounce_start

        active = _active_datasets()
        now = time.monotonic()

        # isolate: read _settled_datasets without creating a reactive dependency
        with reactive.isolate():
            settled = _settled_datasets()

        # First activation: flush immediately to avoid empty-state flash.
        # Also fires when returning from a fully-deactivated state.
        if not _last_seen and active:
            _settled_datasets.set(active)
            _last_seen = list(active)
            _debounce_start = None
            return

        if active != _last_seen:
            # Source changed — record it and start/restart timer.
            _last_seen = list(active)

            # Starvation cap: flush if we've been debouncing too long.
            if _debounce_start is None:
                _debounce_start = now
            elif (now - _debounce_start) >= _MAX_DEBOUNCE_SECONDS:
                _debounce_start = None
                _settled_datasets.set(active)
                return

            # Schedule this effect to re-run after the debounce delay.
            # If _active_datasets changes again before then, the effect
            # re-runs immediately (dependency trigger), and the old timer
            # is discarded with the old reactive context.
            reactive.invalidate_later(_DEBOUNCE_SECONDS)
            return

        # Timer fired and source hasn't changed — propagate.
        if active != settled:
            _debounce_start = None
            _settled_datasets.set(active)

    @reactive.calc
    def _matrix_data() -> dict[str, Any]:
        """
        Compute per-dataset regulator/sample counts and pairwise common-regulator counts
        with restricted sample counts.

        :trigger: ``_settled_datasets`` — re-runs after rapid toggle changes
            settle (debounced).
            ``dataset_filters`` — re-runs when any filter changes, since filters
            affect regulator and sample counts.
        :returns: Dict with keys: ``"diagonal"`` — ``{db_name: {"regulators": int,
            "samples": int}}``; ``"cross_dataset"`` — ``{(db_i, db_j):
            {"common_regulators": int, "samples_a": int, "samples_b": int}}``.

        """
        active = _settled_datasets()
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
        """
        Create the modal and contents on click of a diagonal cell.

        The modal text will describe whether there is a 1-1 correspondence between
        regulators and samples. If there are not, then it will list the metadata columns
        that differentiate samples with the same regulator.

        """
        btn_id = f"diag_{db_name}"

        @reactive.effect
        @reactive.event(input[btn_id])
        def _on_click() -> None:
            """
            Compute regulator/sample multiplicity for this dataset and show the diagonal
            cell modal.

            :trigger: ``input[diag_{db_name}]`` — fires when the user clicks the
                diagonal matrix cell button for this dataset.

            """
            filters = dataset_filters().get(db_name)

            all_cols = vdb.get_fields(f"{db_name}_meta")
            # TODO: this is a good use case for the field `role` experimental
            # condition -- only use experimental condition fields and remove
            # any hidden filter fields
            remove_cols = (
                {"sample_id"}
                | {c for c in all_cols if c.lower().startswith("regulator")}
                | HIDDEN_FILTER_FIELDS.get("*", set())
                | HIDDEN_FILTER_FIELDS.get(db_name, set())
            )
            candidate_cols = [c for c in all_cols if c not in remove_cols]

            sql, params = regulator_breakdown_query(db_name, candidate_cols, filters)
            row = vdb.query(sql, **params).iloc[0]
            n_multi = int(row["n_multi"])

            if n_multi == 0:
                multi_regulator_sample_breakdown: dict = {"uniform": True}
            else:
                diff_cols = [c for c in candidate_cols if row[c] > 0]
                multi_regulator_sample_breakdown = {
                    "uniform": False,
                    "n_multi": n_multi,
                    "differentiating_columns": diff_cols,
                }

            display_name = display_names.get(db_name, db_name)
            ui.modal_show(
                diagonal_cell_modal_ui(display_name, multi_regulator_sample_breakdown)
            )

    def _make_off_diagonal_effect(db_a: str, db_b: str) -> None:
        """Register per-pair click and modal-action effects for an off-diagonal cell."""
        btn_id = f"offdiag_{db_a}__{db_b}"
        apply_btn_id = "modal_select_common_regulators"

        @reactive.effect
        @reactive.event(input[btn_id])
        def _on_click() -> None:
            """
            If this pair is the active regulator filter, clear the filter and
            unhighlight the cell. Otherwise, show the off-diagonal cell modal.

            :trigger: ``input[offdiag_{db_a}__{db_b}]`` — fires when the user
                clicks the off-diagonal matrix cell button for this pair.

            """
            if _active_regulator_pair() == (db_a, db_b):
                # Remove regulator_locus_tag from all datasets and clear highlight.
                current = dict(dataset_filters())
                for db_name in list(current):
                    ds_filters = dict(current[db_name])
                    ds_filters.pop("regulator_locus_tag", None)
                    if ds_filters:
                        current[db_name] = ds_filters
                    else:
                        current.pop(db_name)
                dataset_filters.set(current)
                _active_regulator_pair.set(None)
                return
            data = _matrix_data()
            info = data["cross_dataset"].get((db_a, db_b), {})
            n_common = info.get("common_regulators", 0)
            _open_modal_pair.set((db_a, db_b))
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
            """
            Compute the regulator intersection for this pair, write it as a
            ``regulator_locus_tag`` filter to all datasets, and highlight the cell.

            Only acts when this pair's modal is the one currently open, preventing
            all registered apply effects from firing on a single button click.

            :trigger: ``input[modal_select_common_regulators]`` — fires when the
                user clicks the "Select common regulators" button in the off-diagonal
                modal.

            """
            if _open_modal_pair() != (db_a, db_b):
                return
            reg_sets = {}
            filters = dataset_filters()
            for db_name in (db_a, db_b):
                # Exclude any existing regulator_locus_tag filter so the pairwise
                # intersection is computed from the full regulator set for each dataset
                # (subject to other filters only).
                db_filters = {
                    k: v
                    for k, v in (filters.get(db_name) or {}).items()
                    if k != "regulator_locus_tag"
                } or None
                sql, params = regulator_locus_tags_query(db_name, db_filters)
                reg_df = vdb.query(sql, **params)
                reg_sets[db_name] = set(
                    reg_df["regulator_locus_tag"].dropna().astype(str)
                )
            common = sorted(reg_sets[db_a] & reg_sets[db_b])
            if not common:
                ui.modal_remove()
                return
            current = dict(dataset_filters())
            pair_display = (
                display_names.get(db_a, db_a),
                display_names.get(db_b, db_b),
            )
            for db_name in vdb.get_datasets():
                ds_filters = dict(current.get(db_name, {}))
                ds_filters.pop("regulator_locus_tag", None)
                ds_filters["regulator_locus_tag"] = {
                    "type": "categorical",
                    "value": common,
                    "from_pair": pair_display,
                }
                current[db_name] = ds_filters
            dataset_filters.set(current)
            _active_regulator_pair.set((db_a, db_b))
            _open_modal_pair.set(None)
            ui.modal_remove()

    # Tracks the (db_a, db_b) pair whose intersection is the current regulator filter.
    # Used to highlight that cell in the matrix. None when no pairwise filter is active.
    _active_regulator_pair: reactive.Value[tuple[str, str] | None] = reactive.value(
        None
    )

    # Tracks which pair's off-diagonal modal is currently open.
    # All _on_apply_common_regulators effects share the same button ID, so this
    # guards against every registered effect firing on a single Apply click.
    _open_modal_pair: reactive.Value[tuple[str, str] | None] = reactive.value(None)

    # Track which cell effects have already been registered to avoid duplicates
    # when active_datasets changes but some datasets remain.
    _registered_effects: set[str] = set()

    @reactive.effect
    def _register_cell_effects() -> None:
        """
        Register click effects for any newly active dataset cells that have not yet been
        registered, avoiding duplicate effect registration.

        :trigger: ``_active_datasets`` — re-runs whenever the active dataset list
            changes so that new diagonal and off-diagonal cell effects are created
            for any newly added datasets.

        """
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

    @reactive.effect
    def _clear_pair_when_filter_removed() -> None:
        """
        Clear the highlighted cell pair when no ``regulator_locus_tag`` filter remains
        in ``dataset_filters``.

        :trigger: ``dataset_filters`` — re-runs on every filter change; clears
            ``_active_regulator_pair`` once the regulator filter has been removed.

        """
        filters = dataset_filters()
        has_reg_filter = any(
            "regulator_locus_tag" in (v or {}) for v in filters.values()
        )
        if not has_reg_filter:
            _active_regulator_pair.set(None)

    @render.ui
    def matrix_content() -> ui.Tag:
        active = _settled_datasets()

        if not active:
            return ui.card(
                ui.card_body(
                    ui.p(
                        "Select datasets from the sidebar to view sample counts.",
                        class_="text-muted",
                    )
                )
            )

        try:
            data = _matrix_data()
        except Exception:
            logger.exception("Failed to compute matrix data")
            return ui.card(
                ui.card_body(
                    ui.p(
                        "Failed to load dataset matrix. Check that filters are valid.",
                        class_="text-danger",
                    )
                )
            )
        diagonal = data["diagonal"]
        cross_dataset = data["cross_dataset"]

        # --- header row ---
        header_cells = [matrix_header_cell("Dataset", row=True)]
        for db_name in active:
            header_cells.append(matrix_header_cell(display_names.get(db_name, db_name)))

        # --- body rows ---
        body_rows: list[ui.Tag] = []
        for row_i, db_row in enumerate(active):
            cells: list[ui.Tag] = [matrix_row_label(display_names.get(db_row, db_row))]

            for col_i, db_col in enumerate(active):
                if col_i < row_i:
                    # lower triangle — empty
                    cells.append(matrix_cell("empty"))
                    continue

                if col_i == row_i:
                    # diagonal — regulator count + sample count
                    info = diagonal.get(db_row, {})
                    cells.append(
                        matrix_cell(
                            "diagonal",
                            matrix_cell_button(
                                f"diag_{db_row}",
                                f"{info.get('regulators', 0):,} regulators / "
                                f"{info.get('samples', 0):,} samples",
                            ),
                        )
                    )
                else:
                    # upper triangle — common regulators only
                    key = (db_row, db_col)
                    info = cross_dataset.get(key, {})
                    is_active = _active_regulator_pair() == (db_row, db_col)
                    cells.append(
                        matrix_cell(
                            "interactive",
                            matrix_cell_button(
                                f"offdiag_{db_row}__{db_col}",
                                f"{info.get('common_regulators', 0):,} "
                                "common regulators",
                                tooltip=(
                                    "Click to remove the regulator filter"
                                    if is_active
                                    else None
                                ),
                            ),
                            active=is_active,
                        )
                    )

            body_rows.append(ui.tags.tr(*cells))

        return matrix_table(ui.tags.tr(*header_cells), *body_rows)


__all__ = ["select_datasets_workspace_server"]
