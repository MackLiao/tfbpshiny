"""Selection sidebar – Active Set builder and metadata sieve."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from typing import Any

import faicons as fa
from shiny import module, reactive, render, ui

from tfbpshiny.modules.modals import count_active_filters


@module.ui
def selection_sidebar_ui() -> ui.Tag:
    """Render the Active Set sidebar shell."""
    return ui.output_ui("sidebar_panel")


@module.server
def selection_sidebar_server(
    input: Any,
    output: Any,
    session: Any,
    datasets: reactive.Value[list[dict[str, Any]]],
    logic_mode: reactive.Value[str],
    dataset_filters: reactive.Value[dict[str, Any]],
    datasets_loading: reactive.Value[bool],
    intersection_loading: reactive.Value[bool],
    on_configure: Callable[[str], None] | None = None,
    on_refresh: Callable[[], None] | None = None,
    on_clear_all_filters: Callable[[], None] | None = None,
) -> None:
    """Wire sidebar controls to shared Active Set state."""

    collapsed: reactive.Value[bool] = reactive.value(False)
    configure_clicks: reactive.Value[dict[str, int]] = reactive.value({})

    def _dataset_input_id(prefix: str, ds_id: Any) -> str:
        raw = str(ds_id)
        safe = re.sub(r"[^0-9A-Za-z_]", "_", raw).strip("_") or "dataset"
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
        return f"{prefix}_{safe}_{digest}"

    def _active_filter_counts() -> dict[str, int]:
        filters = dataset_filters()
        return {
            str(dataset["id"]): count_active_filters(
                filters.get(str(dataset["id"]), {})
            )
            for dataset in datasets()
        }

    def _selected_summary() -> dict[str, int]:
        selected = [dataset for dataset in datasets() if dataset.get("selected")]
        filter_counts = _active_filter_counts()

        selected_tf_total = sum(
            int(dataset.get("tf_count") or dataset.get("tfCount") or 0)
            for dataset in selected
            if dataset.get("tf_count_known") or dataset.get("tfCountKnown")
        )
        selected_filters_total = sum(
            filter_counts.get(str(dataset["id"]), 0) for dataset in selected
        )

        return {
            "selected_count": len(selected),
            "selected_tfs": selected_tf_total,
            "active_filters": selected_filters_total,
        }

    @reactive.effect
    @reactive.event(input.toggle_sidebar)
    def _toggle_sidebar() -> None:
        collapsed.set(not collapsed())

    @reactive.effect
    def _sync_logic_mode() -> None:
        try:
            mode = input.logic_mode()
        except Exception:
            return

        if mode in {"intersect", "union"} and logic_mode() != mode:
            logic_mode.set(mode)

    @reactive.effect
    def _sync_dataset_toggles() -> None:
        current = datasets()
        changed = False

        for dataset in current:
            toggle_id = _dataset_input_id("ds_toggle", dataset["id"])
            try:
                value = bool(input[toggle_id]())
            except Exception:
                continue
            if bool(dataset.get("selected")) != value:
                dataset["selected"] = value
                changed = True

        if changed:
            datasets.set(list(current))

    @reactive.effect
    def _watch_configure_buttons() -> None:
        current_counts = dict(configure_clicks())

        for dataset in datasets():
            configure_id = _dataset_input_id("configure", dataset["id"])
            try:
                clicks = int(input[configure_id]())
            except Exception:
                continue

            previous = int(current_counts.get(str(dataset["id"]), 0))
            if clicks > previous:
                current_counts[str(dataset["id"])] = clicks
                configure_clicks.set(current_counts)
                if on_configure:
                    on_configure(str(dataset["id"]))
                break

    @reactive.effect
    @reactive.event(input.clear_all_filters)
    def _clear_all_filters() -> None:
        if on_clear_all_filters:
            on_clear_all_filters()

    @reactive.effect
    @reactive.event(input.refresh)
    def _refresh_matrix() -> None:
        summary = _selected_summary()
        if (
            summary["selected_count"] <= 0
            or datasets_loading()
            or intersection_loading()
        ):
            return
        if on_refresh:
            on_refresh()

    @render.ui
    def sidebar_panel() -> ui.Tag:
        is_collapsed = collapsed()
        search_raw = ""
        if not is_collapsed:
            # `search` is dynamically mounted; guard against transient missing input.
            try:
                search_raw = input.search() or ""
            except Exception:
                search_raw = ""
        search_term = search_raw.strip().lower()

        all_datasets = datasets()
        filter_counts = _active_filter_counts()
        summary = _selected_summary()

        visible = (
            [
                dataset
                for dataset in all_datasets
                if search_term in str(dataset.get("name", "")).lower()
            ]
            if search_term
            else list(all_datasets)
        )

        binding = [dataset for dataset in visible if dataset.get("group") == "binding"]
        perturbation_or_other = [
            dataset for dataset in visible if dataset.get("group") != "binding"
        ]

        def _dataset_row(dataset: dict[str, Any]) -> ui.Tag:
            dataset_id = str(dataset["id"])
            toggle_id = _dataset_input_id("ds_toggle", dataset_id)
            configure_id = _dataset_input_id("configure", dataset_id)
            badge = str(dataset.get("type_badge") or dataset.get("typeBadge") or "EX")
            badge_cls = f"badge badge-{badge.lower()}"

            sample_count = int(
                dataset.get("sample_count") or dataset.get("sampleCount") or 0
            )
            column_count = int(
                dataset.get("column_count") or dataset.get("columnCount") or 0
            )
            sample_known = bool(
                dataset.get("sample_count_known") or dataset.get("sampleCountKnown")
            )
            summary_text = (
                f"{sample_count:,} rows · {column_count:,} cols"
                if sample_known
                else f"rows pending · {column_count:,} cols"
            )

            active_filters = filter_counts.get(dataset_id, 0)

            return ui.div(
                {
                    "class": "dataset-item" + (" compact" if is_collapsed else ""),
                    "title": str(dataset.get("name", "Dataset")),
                },
                ui.input_switch(
                    toggle_id,
                    label=None,
                    value=bool(dataset.get("selected")),
                ),
                ui.span({"class": badge_cls}, badge),
                (
                    ui.div(
                        {"class": "dataset-text"},
                        ui.span(
                            {"class": "dataset-name"},
                            str(dataset.get("name", "Dataset")),
                        ),
                        ui.span({"class": "dataset-meta"}, summary_text),
                    )
                    if not is_collapsed
                    else ui.span()
                ),
                (
                    ui.span({"class": "badge badge-count"}, str(active_filters))
                    if active_filters > 0 and not is_collapsed
                    else ui.span()
                ),
                ui.input_action_button(
                    configure_id,
                    fa.icon_svg("sliders", width="12px", height="12px"),
                    class_="btn-configure",
                ),
            )

        section_tags: list[ui.Tag] = []
        if binding:
            if not is_collapsed:
                section_tags.append(ui.div({"class": "group-header"}, "Binding"))
            section_tags.extend(_dataset_row(dataset) for dataset in binding)
        if perturbation_or_other:
            if not is_collapsed:
                section_tags.append(
                    ui.div({"class": "group-header"}, "Perturbation / Other")
                )
            section_tags.extend(
                _dataset_row(dataset) for dataset in perturbation_or_other
            )

        if not section_tags:
            section_tags.append(
                ui.div(
                    {"class": "empty-state compact"},
                    ui.p("No datasets match your search."),
                )
            )

        logic_help = (
            "AND mode prioritizes shared signal across datasets."
            if logic_mode() == "intersect"
            else "OR mode prioritizes broader discovery across datasets."
        )

        refresh_loading = bool(datasets_loading() or intersection_loading())
        refresh_label = "Refreshing..." if refresh_loading else "Refresh Matrix"

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
                            ui.h2("Active Set Builder"),
                            ui.div({"class": "subtitle"}, "Select datasets to compare"),
                        )
                        if not is_collapsed
                        else ui.div(ui.h2("AS"))
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
                (
                    ui.input_text(
                        "search",
                        label=None,
                        placeholder="Search datasets...",
                        width="100%",
                    )
                    if not is_collapsed
                    else ui.span()
                ),
            ),
            ui.div(
                {"class": "sidebar-body"},
                ui.div({"class": "dataset-list"}, *section_tags),
                (
                    ui.div(
                        {"class": "logic-sieve"},
                        ui.div(
                            {"class": "logic-sieve-header"},
                            ui.span({"class": "group-header"}, "Selection Logic"),
                            ui.input_radio_buttons(
                                "logic_mode",
                                label=None,
                                choices={"intersect": "AND", "union": "OR"},
                                selected=logic_mode(),
                                inline=True,
                            ),
                        ),
                        ui.div(
                            {
                                "class": "logic-explanation"
                                + (
                                    " logic-explanation-and"
                                    if logic_mode() == "intersect"
                                    else " logic-explanation-or"
                                ),
                            },
                            logic_help,
                        ),
                        ui.div(
                            {"class": "logic-footer"},
                            ui.span(
                                {"class": "logic-filter-count"},
                                f"Active Filters: {summary['active_filters']}",
                            ),
                            ui.input_action_button(
                                "clear_all_filters",
                                "Clear All",
                                class_="btn btn-sm btn-outline-secondary",
                            ),
                        ),
                    )
                    if not is_collapsed
                    else ui.span()
                ),
            ),
            ui.div(
                {"class": "sidebar-footer"},
                (
                    ui.div(
                        {"class": "sidebar-summary-cards"},
                        ui.div(
                            {"class": "summary-card"},
                            ui.span({"class": "summary-label"}, "TFs"),
                            ui.span(
                                {"class": "summary-value"},
                                f"{summary['selected_tfs']:,}",
                            ),
                        ),
                        ui.div(
                            {"class": "summary-card"},
                            ui.span({"class": "summary-label"}, "Filters"),
                            ui.span(
                                {"class": "summary-value"},
                                str(summary["active_filters"]),
                            ),
                        ),
                    )
                    if not is_collapsed
                    else ui.span()
                ),
                ui.input_action_button(
                    "refresh",
                    ui.span(
                        fa.icon_svg("arrows-rotate", width="14px", height="14px"),
                        ("" if is_collapsed else f" {refresh_label}"),
                    ),
                    class_=(
                        "btn btn-sm btn-primary w-100 refresh-btn"
                        + (" is-loading" if refresh_loading else "")
                        + (
                            " is-disabled"
                            if summary["selected_count"] <= 0 or refresh_loading
                            else ""
                        )
                    ),
                ),
            ),
        )
