"""Analysis sidebar – module-aware selectors and pairwise comparison controls."""

from __future__ import annotations

from typing import Any

from shiny import module, reactive, render, ui

_MODULE_LABELS: dict[str, str] = {
    "binding": "Binding Analysis",
    "perturbation": "Perturbation Analysis",
    "composite": "Composite Analysis",
}


def _module_type_filter(active_module: str, dataset: dict[str, Any]) -> bool:
    if not dataset.get("selected"):
        return False
    if active_module == "binding":
        return str(dataset.get("type", "")) == "Binding"
    if active_module == "perturbation":
        return str(dataset.get("type", "")) == "Perturbation"
    if active_module == "composite":
        return True
    return False


@module.ui
def analysis_sidebar_ui() -> ui.Tag:
    """Render the analysis sidebar panel."""
    return ui.div(
        {"class": "context-sidebar", "id": "analysis-sidebar"},
        ui.div(
            {"class": "sidebar-header"},
            ui.output_ui("sidebar_title"),
            ui.output_ui("comparison_hint"),
        ),
        ui.div(
            {"class": "sidebar-body"},
            ui.div(
                {"class": "mb-md"},
                ui.div({"class": "group-header"}, "View Mode"),
                ui.input_radio_buttons(
                    "view_mode",
                    label=None,
                    choices={
                        "table": "Table",
                        "correlation": "Correlation",
                        "summary": "Summary",
                        "compare": "Compare",
                    },
                    selected="table",
                ),
            ),
            ui.div(
                {"class": "mb-md"},
                ui.div({"class": "group-header"}, "Dataset A"),
                ui.input_select(
                    "selected_dataset",
                    label=None,
                    choices={},
                    width="100%",
                ),
            ),
            ui.div(
                {"class": "mb-md"},
                ui.div({"class": "group-header"}, "Pairwise"),
                ui.input_switch(
                    "comparison_mode",
                    label="Comparison mode",
                    value=False,
                ),
                ui.input_select(
                    "comparison_dataset",
                    label="Dataset B",
                    choices={},
                    width="100%",
                ),
                ui.div(
                    {"style": "display:flex; gap:8px; margin-top:8px;"},
                    ui.input_action_button(
                        "swap_datasets",
                        "Swap",
                        class_="btn btn-sm btn-outline-secondary",
                    ),
                    ui.input_action_button(
                        "exit_comparison",
                        "Exit",
                        class_="btn btn-sm btn-outline-secondary",
                    ),
                ),
            ),
            ui.div(
                {"class": "mb-md"},
                ui.div({"class": "group-header"}, "Correlation Settings"),
                ui.input_select(
                    "correlation_value_column",
                    label="Value column",
                    choices={
                        "effect_size": "effect_size",
                        "score": "score",
                        "p_value": "p_value",
                        "confidence": "confidence",
                        "time_min": "time_min",
                    },
                    selected="effect_size",
                    width="100%",
                ),
                ui.input_select(
                    "correlation_group_by",
                    label="Group by",
                    choices={
                        "regulator": "Regulator",
                        "target": "Target",
                        "sample": "Sample",
                    },
                    selected="regulator",
                    width="100%",
                ),
            ),
            ui.div(
                {"class": "mb-md"},
                ui.div({"class": "group-header"}, "Filters"),
                ui.input_slider(
                    "p_value",
                    "Max p-value",
                    min=0.001,
                    max=1.0,
                    value=0.05,
                    step=0.001,
                ),
                ui.input_numeric(
                    "log2fc_threshold",
                    "Min |log2FC|",
                    value=1.0,
                    min=0,
                    max=10,
                    step=0.1,
                ),
            ),
        ),
        ui.div(
            {"class": "sidebar-footer"},
            ui.input_action_button(
                "update_view",
                "Update View",
                class_="btn btn-primary btn-sm w-100",
            ),
        ),
    )


@module.server
def analysis_sidebar_server(
    input: Any,
    output: Any,
    session: Any,
    active_module: reactive.Value[str],
    datasets: reactive.Value[list[dict[str, Any]]],
    analysis_config: reactive.Value[dict[str, Any]],
) -> None:
    """Sync sidebar controls to analysis_config reactive value."""

    def _relevant_datasets() -> list[dict[str, Any]]:
        current_module = active_module()
        return [
            dataset
            for dataset in datasets()
            if _module_type_filter(current_module, dataset)
        ]

    def _set_config_if_changed(next_config: dict[str, Any]) -> None:
        if next_config != analysis_config():
            analysis_config.set(next_config)

    @render.ui
    def sidebar_title() -> ui.Tag:
        mod = active_module()
        label = _MODULE_LABELS.get(mod, "Analysis")
        return ui.div(
            ui.h2(label),
            ui.div({"class": "subtitle"}, "Configure your analysis view"),
        )

    @render.ui
    def comparison_hint() -> ui.Tag:
        if active_module() == "selection":
            return ui.span()

        config = analysis_config()
        if not config.get("comparison_mode"):
            return ui.span()

        relevant = _relevant_datasets()
        names = {
            str(dataset.get("db_name")): str(dataset.get("name"))
            for dataset in relevant
        }
        db_a = str(config.get("selected_db_name", ""))
        db_b = str(config.get("comparison_db_name", ""))

        if not db_a or not db_b:
            return ui.div({"class": "subtitle"}, "Pairwise comparison mode enabled")

        label_a = names.get(db_a, db_a)
        label_b = names.get(db_b, db_b)
        return ui.div(
            {"class": "subtitle"},
            f"Pairwise: {label_a} vs {label_b}",
        )

    @reactive.effect
    def _sync_controls_from_config() -> None:
        if active_module() == "selection":
            return

        config = analysis_config()
        ui.update_radio_buttons("view_mode", selected=str(config.get("view", "table")))
        ui.update_switch(
            "comparison_mode", value=bool(config.get("comparison_mode", False))
        )

        ui.update_slider("p_value", value=float(config.get("p_value", 0.05)))
        ui.update_numeric(
            "log2fc_threshold",
            value=float(config.get("log2fc_threshold", 1.0)),
        )
        ui.update_select(
            "correlation_value_column",
            selected=str(config.get("correlation_value_column", "effect_size")),
        )
        ui.update_select(
            "correlation_group_by",
            selected=str(config.get("correlation_group_by", "regulator")),
        )

    @reactive.effect
    def _update_dataset_choices() -> None:
        if active_module() == "selection":
            return

        relevant = _relevant_datasets()
        choices = {
            str(dataset["db_name"]): str(dataset["name"]) for dataset in relevant
        }

        config = analysis_config()
        selected_db = str(config.get("selected_db_name", ""))
        comparison_db = str(config.get("comparison_db_name", ""))

        all_keys = list(choices.keys())
        if not selected_db and all_keys:
            selected_db = all_keys[0]

        if selected_db not in choices and all_keys:
            selected_db = all_keys[0]

        if not comparison_db and len(all_keys) >= 2:
            comparison_db = all_keys[1] if all_keys[1] != selected_db else all_keys[0]

        if comparison_db not in choices and all_keys:
            comparison_db = all_keys[0]

        ui.update_select(
            "selected_dataset", choices=choices, selected=selected_db or None
        )
        ui.update_select(
            "comparison_dataset", choices=choices, selected=comparison_db or None
        )

        next_config = dict(config)
        if next_config.get("selected_db_name") != selected_db:
            next_config["selected_db_name"] = selected_db

        if next_config.get("comparison_db_name") != comparison_db:
            next_config["comparison_db_name"] = comparison_db

        # Compare mode is only meaningful with two datasets.
        if len(all_keys) < 2 and next_config.get("comparison_mode"):
            next_config["comparison_mode"] = False
            if next_config.get("view") == "compare":
                next_config["view"] = "table"

        _set_config_if_changed(next_config)

    @reactive.effect
    def _sync_config() -> None:
        if active_module() == "selection":
            return

        current_config = dict(analysis_config())

        try:
            view_mode = str(input.view_mode())
            selected_input = input.selected_dataset()
            selected_dataset = str(
                selected_input or current_config.get("selected_db_name") or ""
            )
            comparison_mode = bool(input.comparison_mode())
            comparison_input = input.comparison_dataset()
            comparison_dataset = str(
                comparison_input or current_config.get("comparison_db_name") or ""
            )
            p_value = float(input.p_value())
            log2fc_threshold = float(input.log2fc_threshold())
            value_column = str(input.correlation_value_column() or "effect_size")
            group_by = str(input.correlation_group_by() or "regulator")
        except Exception:
            return

        relevant_db_names = {
            str(dataset.get("db_name")) for dataset in _relevant_datasets()
        }

        if selected_dataset not in relevant_db_names and relevant_db_names:
            selected_dataset = sorted(relevant_db_names)[0]

        if comparison_dataset not in relevant_db_names and relevant_db_names:
            comparison_dataset = sorted(relevant_db_names)[0]

        if (
            comparison_mode
            and selected_dataset
            and comparison_dataset
            and selected_dataset == comparison_dataset
        ):
            alternatives = [
                db_name
                for db_name in sorted(relevant_db_names)
                if db_name != selected_dataset
            ]
            if alternatives:
                comparison_dataset = alternatives[0]
            else:
                comparison_mode = False

        if not comparison_mode and view_mode == "compare":
            view_mode = "table"

        next_config = dict(current_config)
        next_config.update(
            {
                "view": view_mode,
                "selected_db_name": selected_dataset,
                "comparison_mode": comparison_mode,
                "comparison_db_name": comparison_dataset,
                "p_value": p_value,
                "log2fc_threshold": log2fc_threshold,
                "correlation_value_column": value_column,
                "correlation_group_by": group_by,
            }
        )
        _set_config_if_changed(next_config)

    @reactive.effect
    @reactive.event(input.swap_datasets, ignore_init=True)
    def _swap_datasets() -> None:
        if active_module() == "selection":
            return

        config = dict(analysis_config())
        db_a = str(config.get("selected_db_name", ""))
        db_b = str(config.get("comparison_db_name", ""))
        if not db_a or not db_b:
            return

        config["selected_db_name"] = db_b
        config["comparison_db_name"] = db_a
        config["comparison_mode"] = True
        _set_config_if_changed(config)

    @reactive.effect
    @reactive.event(input.exit_comparison, ignore_init=True)
    def _exit_comparison() -> None:
        if active_module() == "selection":
            return

        config = dict(analysis_config())
        config["comparison_mode"] = False
        config["comparison_db_name"] = ""
        if config.get("view") == "compare":
            config["view"] = "table"
        _set_config_if_changed(config)
