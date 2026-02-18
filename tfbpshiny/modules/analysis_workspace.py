"""Analysis workspace – polished module views with pairwise comparison."""

from __future__ import annotations

import operator as op
from typing import Any

import pandas as pd
from shiny import module, reactive, render, ui

from tfbpshiny.mock_data import (
    get_mock_composite_data,
    get_mock_correlation,
    get_mock_pairwise_comparison,
    get_mock_source_summary,
    get_mock_table_data,
)
from tfbpshiny.utils.create_distribution_plot import create_distribution_plot
from tfbpshiny.utils.source_name_lookup import get_source_name_dict

_COMPOSITE_METHOD_LABELS: dict[str, str] = {
    "dto": "DTO",
    "rank_response_pvalue": "Rank Response P-value",
    "univariate_pvalue": "Univariate P-value",
}

_OPERATOR_MAP: dict[str, Any] = {
    "<": op.lt,
    "<=": op.le,
    ">": op.gt,
    ">=": op.ge,
}

_MODULE_LABELS: dict[str, str] = {
    "binding": "Binding",
    "perturbation": "Perturbation",
    "composite": "Composite",
}


@module.ui
def analysis_workspace_ui() -> ui.Tag:
    """Render the analysis workspace."""
    return ui.div(
        {"class": "main-workspace", "id": "analysis-workspace"},
        ui.div(
            {"class": "workspace-header"},
            ui.output_ui("workspace_title"),
        ),
        ui.div(
            {"class": "workspace-body"},
            ui.output_ui("workspace_content"),
        ),
    )


@module.server
def analysis_workspace_server(
    input: Any,
    output: Any,
    session: Any,
    active_module: reactive.Value[str],
    datasets: reactive.Value[list[dict[str, Any]]],
    analysis_config: reactive.Value[dict[str, Any]],
) -> None:
    """Route analysis content with module-aware and pairwise-aware behavior."""

    def _relevant_datasets() -> list[dict[str, Any]]:
        module_name = active_module()
        selected = [dataset for dataset in datasets() if dataset.get("selected")]

        if module_name == "binding":
            return [dataset for dataset in selected if dataset.get("type") == "Binding"]
        if module_name == "perturbation":
            return [
                dataset for dataset in selected if dataset.get("type") == "Perturbation"
            ]
        if module_name == "composite":
            return selected
        return []

    def _resolve_dataset_pair() -> tuple[str, str, bool]:
        config = analysis_config()
        relevant = _relevant_datasets()
        db_names = [
            str(dataset.get("db_name") or dataset.get("dbName")) for dataset in relevant
        ]

        selected_db = str(config.get("selected_db_name", ""))
        if selected_db not in db_names:
            selected_db = db_names[0] if db_names else ""

        comparison_mode = bool(config.get("comparison_mode", False))
        comparison_db = str(config.get("comparison_db_name", ""))

        if comparison_db not in db_names:
            comparison_db = ""

        if comparison_mode:
            if not comparison_db and len(db_names) > 1:
                comparison_db = (
                    db_names[1] if db_names[1] != selected_db else db_names[0]
                )
            if comparison_db == selected_db:
                alternatives = [db for db in db_names if db != selected_db]
                comparison_db = alternatives[0] if alternatives else ""
                if not comparison_db:
                    comparison_mode = False

        return selected_db, comparison_db, comparison_mode

    @render.ui
    def workspace_title() -> ui.Tag:
        module_name = active_module()

        if module_name == "composite":
            config = analysis_config()
            method = str(config.get("composite_method", "dto"))
            method_label = _COMPOSITE_METHOD_LABELS.get(method, method)
            return ui.h1(f"Composite - {method_label}")

        module_label = _MODULE_LABELS.get(module_name, "Analysis")
        view = str(analysis_config().get("view", "table")).capitalize()

        _, _, comparison_mode = _resolve_dataset_pair()
        suffix = " (Pairwise)" if comparison_mode and view == "Compare" else ""
        return ui.h1(f"{module_label} - {view}{suffix}")

    @render.ui
    def workspace_content() -> ui.Tag:
        module_name = active_module()

        if module_name == "composite":
            return _render_composite(analysis_config(), datasets())

        config = analysis_config()
        view = str(config.get("view", "table"))

        selected_db, comparison_db, comparison_mode = _resolve_dataset_pair()

        if not selected_db:
            return ui.div(
                {"class": "empty-state"},
                ui.h3("No dataset selected"),
                ui.p(
                    "Select datasets in Active Set, then open "
                    "analysis from a matrix cell."
                ),
            )

        if view == "table":
            return _render_table(
                db_name=selected_db,
                p_value=float(config.get("p_value", 0.05)),
                log2fc_threshold=float(config.get("log2fc_threshold", 1.0)),
                comparison_db=(comparison_db if comparison_mode else ""),
            )

        if view == "correlation":
            return _render_correlation(selected_db)

        if view == "summary":
            if comparison_mode and comparison_db:
                return _render_summary_comparison(selected_db, comparison_db)
            return _render_summary(selected_db)

        if view == "compare":
            if not comparison_mode or not comparison_db:
                return ui.div(
                    {"class": "empty-state"},
                    ui.h3("Comparison Mode Required"),
                    ui.p(
                        "Select two datasets from Intersection "
                        "Summary and open analysis."
                    ),
                )

            return _render_pairwise_compare(
                db_name_a=selected_db,
                db_name_b=comparison_db,
                value_column=str(config.get("correlation_value_column", "effect_size")),
                group_by=str(config.get("correlation_group_by", "regulator")),
            )

        return ui.div({"class": "empty-state"}, ui.p("Unknown view mode."))


def _render_composite(
    config: dict[str, Any],
    all_datasets: list[dict[str, Any]],
) -> ui.Tag:
    """Render the composite analysis view with faceted boxplots."""
    # Resolve which datasets to use from sidebar checkboxes.
    bd_checked = config.get("composite_binding_datasets")
    pr_checked = config.get("composite_perturbation_datasets")

    selected = [d for d in all_datasets if d.get("selected")]

    if isinstance(bd_checked, list) and bd_checked:
        bd_names = [str(n) for n in bd_checked]
    else:
        bd_names = [str(d["db_name"]) for d in selected if d.get("type") == "Binding"]

    if isinstance(pr_checked, list) and pr_checked:
        pr_names = [str(n) for n in pr_checked]
    else:
        pr_names = [
            str(d["db_name"]) for d in selected if d.get("type") == "Perturbation"
        ]

    if not bd_names or not pr_names:
        return ui.div(
            {"class": "empty-state"},
            ui.h3("Select binding and perturbation datasets"),
            ui.p(
                "Check at least one binding and one perturbation "
                "dataset in the sidebar."
            ),
        )

    method = str(config.get("composite_method", "dto"))
    threshold = float(config.get("composite_filter_threshold", 0.5))
    operator_str = str(config.get("composite_filter_operator", "<"))
    compare_fn = _OPERATOR_MAP.get(operator_str, op.lt)
    method_label = _COMPOSITE_METHOD_LABELS.get(method, method)

    # Build source name mapping for display
    source_name_map = get_source_name_dict()
    name_map = {}
    for d in selected:
        source_key = str(d.get("source_key", ""))
        db_name = str(d.get("db_name", ""))
        name_map[db_name] = source_name_map.get(source_key, db_name)

    raw = get_mock_composite_data(bd_names, pr_names, name_map=name_map)
    if not raw:
        return ui.div(
            {"class": "empty-state"},
            ui.h3("No data available"),
            ui.p("No overlapping TFs found between the selected datasets."),
        )

    df = pd.DataFrame(raw)

    # Apply filter: identify TFs that pass in at least one perturbation.
    df["passes"] = df[method].apply(lambda v: compare_fn(v, threshold))

    passing_tfs = df.groupby("regulator_symbol")["passes"].any().loc[lambda s: s].index

    # Mask DTO values that don't pass the threshold (set to NA so they don't
    # appear in plot)
    df.loc[~df["passes"], method] = pd.NA

    filtered = df[df["regulator_symbol"].isin(passing_tfs)]

    if filtered.empty:
        return ui.div(
            {"class": "empty-state"},
            ui.h3("No TFs pass the current filter"),
            ui.p(
                f"No TFs have {method_label} {operator_str} {threshold}. "
                "Try relaxing the threshold."
            ),
        )

    try:
        fig = create_distribution_plot(
            filtered, y_column=method, y_axis_title=method_label
        )
        plot_html = fig.to_html(full_html=False, include_plotlyjs="cdn")
    except Exception as e:
        return ui.div(
            {"class": "empty-state"},
            ui.h3("Error rendering plot"),
            ui.p(f"Error: {str(e)}"),
        )

    status_text = (
        f"Showing {method_label} | "
        f"Filter: {operator_str} {threshold} | "
        f"{len(bd_names)} binding x {len(pr_names)} perturbation"
    )

    return ui.div(
        ui.div(
            {
                "style": "margin-bottom: 8px; font-size: 13px; "
                "color: var(--color-text-muted);"
            },
            ui.span(status_text),
        ),
        ui.HTML(plot_html),
    )


def _render_table(
    db_name: str,
    p_value: float,
    log2fc_threshold: float,
    comparison_db: str = "",
) -> ui.Tag:
    """Render filtered table analysis for one dataset."""
    data = get_mock_table_data(db_name, page=1, page_size=250)
    df = pd.DataFrame(data["rows"])

    if not df.empty:
        df = df[df["p_value"] <= float(p_value)]
        df = df[df["log2fc"].abs() >= float(log2fc_threshold)]

    preview = df.head(50)

    header_bits = [
        f"Showing {len(preview):,} of {len(df):,} filtered rows",
        f"(p <= {p_value:.3f}, |log2FC| >= {log2fc_threshold:.2f})",
    ]
    if comparison_db:
        header_bits.append(f"Pairwise context with {comparison_db}")

    if preview.empty:
        return ui.div(
            {"class": "card"},
            ui.div({"class": "card-header"}, " | ".join(header_bits)),
            ui.div(
                {"class": "empty-state compact"},
                ui.h3("No rows passed current filters"),
                ui.p("Relax p-value or |log2FC| threshold to include more rows."),
            ),
        )

    return ui.div(
        {"class": "card"},
        ui.div({"class": "card-header"}, " | ".join(header_bits)),
        ui.HTML(preview.to_html(index=False, classes="table table-sm table-striped")),
    )


def _render_summary(db_name: str) -> ui.Tag:
    """Render source summary for one dataset."""
    summary = get_mock_source_summary(db_name)

    stats = [
        ("Total Rows", f"{int(summary['total_rows']):,}"),
        ("Regulators", f"{int(summary['regulator_count']):,}"),
        ("Targets", f"{int(summary['target_count']):,}"),
        ("Samples", f"{int(summary['sample_count']):,}"),
        ("Columns", f"{int(summary['column_count']):,}"),
    ]

    stat_boxes = [
        ui.div(
            {"class": "stat-box"},
            ui.div({"class": "stat-value"}, value),
            ui.div({"class": "stat-label"}, label),
        )
        for label, value in stats
    ]

    metadata_rows = [
        ui.tags.tr(
            ui.tags.td(field["field"]),
            ui.tags.td(field["kind"]),
        )
        for field in summary.get("metadata_fields", [])
    ]

    return ui.div(
        {"style": "display:flex; flex-direction:column; gap:16px;"},
        ui.div(
            {"class": "card"},
            ui.div(
                {"class": "card-header"},
                f"{summary['db_name']} ({summary['dataset_type']})",
            ),
            ui.p(
                {"style": "margin:0; color:var(--color-text-muted); font-size:12px;"},
                f"Repo: {summary['repo_id']} | Config: {summary['config_name']}",
            ),
        ),
        ui.div({"class": "stat-grid"}, *stat_boxes),
        ui.div(
            {"class": "card"},
            ui.div({"class": "card-header"}, "Metadata Fields"),
            ui.tags.table(
                {"class": "table table-sm"},
                ui.tags.thead(ui.tags.tr(ui.tags.th("Field"), ui.tags.th("Type"))),
                ui.tags.tbody(*metadata_rows),
            ),
        ),
    )


def _render_summary_comparison(db_name_a: str, db_name_b: str) -> ui.Tag:
    """Render side-by-side source summary comparison."""
    summary_a = get_mock_source_summary(db_name_a)
    summary_b = get_mock_source_summary(db_name_b)

    metric_defs = [
        ("Total Rows", "total_rows"),
        ("Regulators", "regulator_count"),
        ("Targets", "target_count"),
        ("Samples", "sample_count"),
        ("Columns", "column_count"),
    ]

    rows: list[ui.Tag] = []
    for label, key in metric_defs:
        value_a = int(summary_a.get(key, 0))
        value_b = int(summary_b.get(key, 0))
        delta = value_b - value_a
        rows.append(
            ui.tags.tr(
                ui.tags.td(label),
                ui.tags.td(f"{value_a:,}"),
                ui.tags.td(f"{value_b:,}"),
                ui.tags.td(f"{delta:+,}"),
            )
        )

    fields_a = {field["field"] for field in summary_a.get("metadata_fields", [])}
    fields_b = {field["field"] for field in summary_b.get("metadata_fields", [])}

    return ui.div(
        {"style": "display:flex; flex-direction:column; gap:16px;"},
        ui.div(
            {"class": "card"},
            ui.div(
                {"class": "card-header"},
                f"Pairwise Summary: {summary_a['db_name']} vs {summary_b['db_name']}",
            ),
            ui.p(
                {"style": "margin:0; color:var(--color-text-muted); font-size:12px;"},
                "Delta is Dataset B minus Dataset A.",
            ),
        ),
        ui.div(
            {"class": "card"},
            ui.tags.table(
                {"class": "table table-sm table-striped"},
                ui.tags.thead(
                    ui.tags.tr(
                        ui.tags.th("Metric"),
                        ui.tags.th("Dataset A"),
                        ui.tags.th("Dataset B"),
                        ui.tags.th("Delta"),
                    )
                ),
                ui.tags.tbody(*rows),
            ),
        ),
        ui.div(
            {"class": "card"},
            ui.div({"class": "card-header"}, "Metadata Field Overlap"),
            ui.p(
                {"style": "margin:0; font-size:12px; color:var(--color-text-muted);"},
                f"Common fields: {len(fields_a & fields_b)} | "
                f"Only A: {len(fields_a - fields_b)} | "
                f"Only B: {len(fields_b - fields_a)}",
            ),
        ),
    )


def _render_pairwise_compare(
    db_name_a: str,
    db_name_b: str,
    value_column: str,
    group_by: str,
) -> ui.Tag:
    """Render pairwise comparison stats and ranked difference table."""
    result = get_mock_pairwise_comparison(
        db_name_a=db_name_a,
        db_name_b=db_name_b,
        value_column=value_column,
        group_by=group_by,
        max_points=4000,
    )

    points = result.get("points", [])
    if not points:
        return ui.div(
            {"class": "empty-state"},
            ui.h3("No overlapping entities found"),
            ui.p("Try a different value column or grouping mode."),
        )

    df = pd.DataFrame(points)
    mean_delta = float(df["delta"].mean()) if not df.empty else 0.0
    up_count = int((df["delta"] > 0).sum())
    down_count = int((df["delta"] < 0).sum())

    preview = df.head(50)

    return ui.div(
        {"style": "display:flex; flex-direction:column; gap:16px;"},
        ui.div(
            {"class": "card"},
            ui.div(
                {"class": "card-header"},
                f"Pairwise Comparison: {result['db_name_a']} vs {result['db_name_b']}",
            ),
            ui.p(
                {
                    "style": "margin:0;"
                    " color:var(--color-text-muted);"
                    " font-size:12px;"
                },
                f"Group by {result['group_by']}"
                f" | Value column: {result['value_column']}",
            ),
        ),
        ui.div(
            {"class": "stat-grid"},
            ui.div(
                {"class": "stat-box"},
                ui.div({"class": "stat-value"}, f"{int(result['total_entities']):,}"),
                ui.div({"class": "stat-label"}, "Common Entities"),
            ),
            ui.div(
                {"class": "stat-box"},
                ui.div(
                    {"class": "stat-value"},
                    (
                        "N/A"
                        if result.get("correlation") is None
                        else f"{float(result['correlation']):.3f}"
                    ),
                ),
                ui.div({"class": "stat-label"}, "Correlation"),
            ),
            ui.div(
                {"class": "stat-box"},
                ui.div({"class": "stat-value"}, f"{mean_delta:+.3f}"),
                ui.div({"class": "stat-label"}, "Mean Delta (B-A)"),
            ),
            ui.div(
                {"class": "stat-box"},
                ui.div({"class": "stat-value"}, f"{up_count:,} / {down_count:,}"),
                ui.div({"class": "stat-label"}, "Positive / Negative"),
            ),
        ),
        ui.div(
            {"class": "card"},
            ui.div({"class": "card-header"}, "Top Absolute Differences"),
            ui.HTML(
                preview.to_html(index=False, classes="table table-sm table-striped")
            ),
        ),
    )


def _render_correlation(db_name: str) -> ui.Tag:
    """Render correlation matrix table preview."""
    corr = get_mock_correlation(db_name)
    labels = corr.get("labels", [])
    matrix = corr.get("matrix", [])

    if not labels or not matrix:
        return ui.div(
            {"class": "empty-state"},
            ui.h3("Correlation data unavailable"),
            ui.p("No data returned for this dataset."),
        )

    df = pd.DataFrame(matrix, index=labels, columns=labels)

    return ui.div(
        {"class": "card"},
        ui.div(
            {"class": "card-header"}, f"Correlation Matrix ({len(labels)} entities)"
        ),
        ui.HTML(df.round(3).to_html(classes="table table-sm table-striped")),
    )
