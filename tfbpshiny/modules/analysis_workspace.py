"""Analysis workspace – polished module views with pairwise comparison."""

from __future__ import annotations

import logging
import operator as op
from typing import Any

import pandas as pd
from shiny import module, reactive, render, ui

from tfbpshiny.data_service import (
    get_dto_data,
    get_median_correlation_matrix,
    get_or_create_vdb,
)
from tfbpshiny.mock_data import get_mock_source_summary
from tfbpshiny.utils.create_distribution_plot import create_distribution_plot
from tfbpshiny.utils.source_name_lookup import get_source_name_dict
from tfbpshiny.utils.transforms import neglog10_with_pseudocount

logger = logging.getLogger("shiny")

_COMPOSITE_METHOD_LABELS: dict[str, str] = {
    "dto": "DTO",
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
    "composite": "Comparison",
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
        db_names = [str(dataset.get("db_name")) for dataset in relevant]

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

    @reactive.calc
    def _vdb_for_correlation() -> tuple[Any, dict[str, Any]] | None:
        """
        Cache VDB and correlation result for current correlation view.

        Memoized by the relevant datasets and value column. This prevents duplicate
        expensive VDB creation when switching views or modules.

        """
        config = analysis_config()
        view = str(config.get("view", ""))

        # Only create VDB when in correlation view.
        if view != "correlation":
            return None

        relevant = _relevant_datasets()
        db_names = [str(dataset.get("db_name")) for dataset in relevant]

        if len(db_names) < 2:
            return None

        value_column = str(config.get("correlation_value_column", ""))
        if not value_column:
            return None

        try:
            vdb = get_or_create_vdb(db_names)
            result = get_median_correlation_matrix(db_names, value_column, vdb)
            return (vdb, result)
        except Exception:
            return None

    @render.ui
    def workspace_title() -> ui.Tag:
        module_name = active_module()

        if module_name == "composite":
            config = analysis_config()
            method = str(config.get("composite_method", "dto"))
            method_label = _COMPOSITE_METHOD_LABELS.get(method, method)
            return ui.h1(f"Comparison - {method_label}")

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

        if view == "summary":
            if comparison_mode and comparison_db:
                return _render_summary_comparison(selected_db, comparison_db)
            return _render_summary(selected_db)

        if view == "correlation":
            # Use cached VDB and correlation result.
            cached = _vdb_for_correlation()
            if cached is None:
                return ui.div(
                    {"class": "empty-state"},
                    ui.h3("Correlation data unavailable"),
                    ui.p(
                        "Select a valid value column present in at least two datasets."
                    ),
                )
            _, result = cached
            value_column = str(config.get("correlation_value_column", ""))
            return _render_correlation_from_result(result, value_column)

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
    threshold = float(config.get("composite_filter_threshold", 1.3))
    operator_str = str(config.get("composite_filter_operator", ">="))
    compare_fn = _OPERATOR_MAP.get(operator_str, op.ge)
    method_label = _COMPOSITE_METHOD_LABELS.get(method, method)

    # Build source name mapping for display
    source_name_map = get_source_name_dict()
    name_map = {}
    for d in selected:
        source_key = str(d.get("source_key", ""))
        db_name = str(d.get("db_name", ""))
        name_map[db_name] = source_name_map.get(source_key, db_name)

    # Query DTO data from VirtualDB
    df = pd.DataFrame()
    try:
        all_db_names = bd_names + pr_names + ["dto"]
        vdb = get_or_create_vdb(all_db_names)
        raw = get_dto_data(bd_names, pr_names, vdb)

        if raw:
            df = pd.DataFrame(raw)
            df = df.rename(
                columns={
                    "binding_id": "binding_source",
                    "perturbation_id": "perturbation_source",
                }
            )
            if "dto_pvalue" in df.columns:
                df["dto"] = df["dto_pvalue"]
    except Exception as e:
        logger.warning("Failed to get DTO data: %s", e)

    if df.empty:
        return ui.div(
            {"class": "empty-state"},
            ui.h3("No data available"),
            ui.p("No data available for the selected datasets."),
        )

    # Transform DTO p-values to -log10 scale.
    if method == "dto":
        try:
            df[method] = neglog10_with_pseudocount(df[method])
            method_label = "-log10(DTO p-value)"
        except ValueError:
            return ui.div(
                {"class": "empty-state"},
                ui.h3("Cannot transform p-values"),
                ui.p(
                    "All DTO p-values are zero. "
                    "Check the underlying data for this combination "
                    "of binding and perturbation sources."
                ),
            )

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

    plot_layout = str(config.get("composite_plot_layout", "binding_color"))
    if plot_layout == "perturbation_color":
        filtered = filtered.rename(
            columns={
                "binding_source": "_tmp_binding",
                "perturbation_source": "binding_source",
            }
        )
        filtered = filtered.rename(columns={"_tmp_binding": "perturbation_source"})
        color_label = "Perturbation Source"
        facet_label = "Binding Source"
    else:
        color_label = "Binding Data Source"
        facet_label = "Perturbation Source"

    # Keep only regulators present in all color-axis sources per facet.
    # Skip for DTO data: rows represent dataset pairs, not per-TF data,
    # so regulator_symbol == binding_source and intersection is meaningless.
    if method != "dto":
        # Count all color-axis sources per facet (including those with no
        # passing rows) so the denominator isn't weakened by strict thresholds.
        sources_per_facet = filtered.groupby("perturbation_source")[
            "binding_source"
        ].nunique()

        if (sources_per_facet > 1).any():
            # For each (facet, regulator), count distinct color sources
            # that have at least one non-NA (passing) value.
            non_na = filtered.dropna(subset=[method])
            coverage = non_na.groupby(["perturbation_source", "regulator_symbol"])[
                "binding_source"
            ].nunique()
            # Keep regulators covering all sources *within their own facet*.
            shared = coverage.reset_index(name="n_sources")
            shared = shared.merge(
                sources_per_facet.rename("n_facet_sources"),
                on="perturbation_source",
            )
            shared = shared.loc[
                shared["n_sources"] == shared["n_facet_sources"],
                ["perturbation_source", "regulator_symbol"],
            ]
            filtered = filtered.merge(
                shared, on=["perturbation_source", "regulator_symbol"]
            )

    if filtered.empty:
        return ui.div(
            {"class": "empty-state"},
            ui.h3("No shared regulators"),
            ui.p(
                "No regulators are common to all "
                f"{color_label.lower().rstrip('s')} sources "
                "in any facet. Try selecting fewer sources."
            ),
        )

    try:
        fig = create_distribution_plot(
            filtered,
            y_column=method,
            y_axis_title=method_label,
            color_label=color_label,
            facet_label=facet_label,
            match_yaxes=True,
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


def _render_correlation_matrix(
    db_names: list[str],
    value_column: str,
) -> ui.Tag:
    """Render median-of-per-TF-correlations matrix across selected datasets."""
    if len(db_names) < 2:
        return ui.div(
            {"class": "empty-state"},
            ui.h3("Need at least 2 datasets"),
            ui.p("Select two or more datasets to compute a correlation matrix."),
        )

    try:
        vdb = get_or_create_vdb(db_names)
        result = get_median_correlation_matrix(db_names, value_column, vdb)
    except Exception as e:
        return ui.div(
            {"class": "empty-state"},
            ui.h3("Error computing correlation matrix"),
            ui.p(f"Error: {e}"),
        )

    return _render_correlation_from_result(result, value_column)


def _render_correlation_from_result(
    result: dict[str, Any],
    value_column: str,
) -> ui.Tag:
    """Render correlation matrix from pre-computed result dict."""
    labels = result.get("labels", [])
    matrix = result.get("matrix", [])

    # Reject results with fewer than 2 datasets - a 1x1 matrix (value 1.0) is not
    # a meaningful cross-dataset correlation.
    if not labels or not matrix or len(labels) < 2:
        return ui.div(
            {"class": "empty-state"},
            ui.h3("Correlation data unavailable"),
            ui.p(
                "The selected value column is not present in at least two datasets. "
                "Choose a different column or select datasets that share this measure."
            ),
        )

    # Build HTML table with formatted values.
    header_cells = [ui.tags.th("")] + [ui.tags.th(lbl) for lbl in labels]
    rows: list[ui.Tag] = []
    for i, row_label in enumerate(labels):
        cells = [ui.tags.td(ui.tags.strong(row_label))]
        for j in range(len(labels)):
            val = matrix[i][j]
            if val is None:
                cells.append(ui.tags.td("--"))
            else:
                cells.append(ui.tags.td(f"{val:.3f}"))
        rows.append(ui.tags.tr(*cells))

    return ui.div(
        {"class": "card"},
        ui.div(
            {"class": "card-header"},
            f"Median Correlation Matrix ({len(labels)} datasets, "
            f"value: {value_column})",
        ),
        ui.tags.table(
            {"class": "table table-sm table-striped"},
            ui.tags.thead(ui.tags.tr(*header_cells)),
            ui.tags.tbody(*rows),
        ),
    )
