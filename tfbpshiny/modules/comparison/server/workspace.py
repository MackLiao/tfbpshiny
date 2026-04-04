"""Workspace server for the Comparison module."""

from __future__ import annotations

from collections.abc import Callable
from logging import Logger
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from labretriever import VirtualDB
from plotly.io import to_html
from plotly.subplots import make_subplots
from shiny import module, reactive, render, ui

from tfbpshiny.modules.comparison.queries import (
    BINDING_CONFIGS,
    BINDING_LABEL_MAP,
    DTO_LOG_PSEUDO,
    PERTURBATION_CONFIGS,
    PERTURBATION_LABEL_MAP,
    ensure_hackett_analysis_set,
    fetch_dto_data,
    topn_responsive_ratio,
)

# color palettes
BINDING_COLORS: dict[str, str] = {
    "2004 ChIP-chip": "#E64B35",
    "2021 ChIPexo": "#F39B7F",
    "2025 Chec-seq": "#00A087",
    "2026 Calling Cards": "#3C5488",
}

PERTURBATION_COLORS: dict[str, str] = {
    "2006 Overexpression": "#4DBBD5",
    "2006 TFKO": "#00A087",
    "2007 TFKO": "#8491B4",
    "2014 TFKO": "#F39B7F",
    "2020 Overexpression": "#91D1C2",
    "2025 Degron": "#B09C85",
}

_PERT_ORDER = [
    "2006 Overexpression",
    "2006 TFKO",
    "2007 TFKO",
    "2014 TFKO",
    "2020 Overexpression",
    "2025 Degron",
]

_BINDING_ORDER = [
    "2004 ChIP-chip",
    "2021 ChIPexo",
    "2025 Chec-seq",
    "2026 Calling Cards",
]


@module.server
def comparison_workspace_server(
    input: Any,
    output: Any,
    session: Any,
    active_binding_datasets: reactive.Calc_[list[str]],
    active_perturbation_datasets: reactive.Calc_[list[str]],
    dataset_filters: reactive.Value[dict[str, Any]],
    top_n: Callable[[], int],
    effect_threshold: Callable[[], float],
    pvalue_threshold: Callable[[], float],
    facet_by: Callable[[], str],
    vdb: VirtualDB,
    logger: Logger,
) -> None:
    """Render two workspace rows: DTO ECDF (top) and Top-N boxplot (bottom)."""

    try:
        ensure_hackett_analysis_set(vdb)
    except Exception:
        logger.exception("Could not register hackett_analysis_set")

    @reactive.calc
    def _active_binding_labels() -> dict[str, str]:
        return {db: BINDING_LABEL_MAP.get(db, db) for db in active_binding_datasets()}

    @reactive.calc
    def _active_perturbation_labels() -> dict[str, str]:
        return {
            db: PERTURBATION_LABEL_MAP.get(db, db)
            for db in active_perturbation_datasets()
        }

    @reactive.calc
    def _dto_data() -> pd.DataFrame:
        """
        Fetch and label DTO empirical p-value data filtered to active datasets.

        :trigger _active_binding_labels: re-runs when binding selection changes.
        :trigger _active_perturbation_labels: re-runs when perturbation changes.

        """
        binding_labels = _active_binding_labels()
        pert_labels = _active_perturbation_labels()

        if not binding_labels or not pert_labels:
            return pd.DataFrame()
        try:
            df = fetch_dto_data(vdb)
        except Exception:
            logger.exception("DTO fetch failed")
            return pd.DataFrame()

        # TODO: get rid of the type ignores
        df["binding_source"] = df["binding_id_source"].map(BINDING_LABEL_MAP)  # type: ignore # noqa: E501
        df["perturbation_source"] = df["perturbation_id_source"].map(  # type: ignore # noqa: E501
            PERTURBATION_LABEL_MAP
        )
        df["mlog10_pval"] = -np.log10(df["dto_empirical_pvalue"] + DTO_LOG_PSEUDO)  # type: ignore # noqa: E501

        active_b = set(binding_labels.values())
        active_p = set(pert_labels.values())
        return df[
            df["binding_source"].isin(active_b)  # type: ignore
            & df["perturbation_source"].isin(active_p)  # type: ignore
        ]

    @reactive.calc
    def _topn_data() -> pd.DataFrame:
        """
        Compute top-N responsive ratio for all active (binding, perturbation) pairs.

        :trigger _active_binding_labels: re-runs when binding selection changes.
        :trigger _active_perturbation_labels: re-runs when perturbation changes.
        :trigger dataset_filters: re-runs when filters are applied or reset. :trigger
        top_n: re-runs when the top-N cutoff changes. :trigger effect_threshold: re-runs
        when the effect threshold changes. :trigger pvalue_threshold: re-runs when the
        p-value threshold changes.

        """
        binding_labels = _active_binding_labels()
        pert_labels = _active_perturbation_labels()
        filters = dataset_filters()
        n = top_n()
        eff = effect_threshold()
        pval = pvalue_threshold()

        if not binding_labels or not pert_labels:
            return pd.DataFrame()

        results: list[pd.DataFrame] = []
        for b_db, b_label in binding_labels.items():
            b_cfg = BINDING_CONFIGS.get(b_db)
            if b_cfg is None:
                logger.warning(f"No binding config for {b_db}, skipping")
                continue
            for p_db, p_label in pert_labels.items():
                p_cfg = PERTURBATION_CONFIGS.get(p_db)
                if p_cfg is None:
                    logger.warning(f"No perturbation config for {p_db}, skipping")
                    continue
                logger.debug(f"Top-{n}: {b_db} x {p_db}")
                try:
                    df = topn_responsive_ratio(
                        vdb=vdb,
                        binding_view=b_db,
                        perturbation_view=p_db,
                        top_n=n,
                        effect_threshold=eff,
                        pvalue_threshold=pval,
                        binding_filters=filters.get(b_db),
                        perturbation_filters=filters.get(p_db),
                        param_prefix=f"{b_db}_{p_db}",
                        **b_cfg,
                        **p_cfg,
                    )
                    # TODO: Get rid of the type ignores
                    df["binding_source"] = b_label  # type: ignore
                    df["perturbation_source"] = p_label  # type: ignore
                    results.append(df)
                except Exception as exc:
                    logger.error(
                        f"Top-N failed for {b_db} x {p_db}: {exc}", exc_info=True
                    )

        if not results:
            return pd.DataFrame()
        out = pd.concat(results, ignore_index=True)
        out["percent_responsive"] = out["responsive_ratio"] * 100
        return out

    @render.ui
    def dto_plot() -> ui.Tag:
        """
        ECDF of -log10(DTO empirical p-value) faceted by perturbation source.

        :trigger _dto_data: re-renders when DTO data changes.

        """
        df = _dto_data()

        if df.empty:
            return ui.div(
                {"class": "empty-state"},
                ui.p("No DTO data available for the selected datasets."),
            )

        pert_sources = [
            p for p in _PERT_ORDER if p in df["perturbation_source"].unique()
        ]
        if not pert_sources:
            return ui.div(
                {"class": "empty-state"}, ui.p("No perturbation sources to display.")
            )

        n = len(pert_sources)
        fig = make_subplots(
            rows=1, cols=n, subplot_titles=pert_sources, shared_yaxes=True
        )

        for col_idx, pert in enumerate(pert_sources, start=1):
            sub = df[df["perturbation_source"] == pert]
            for b_source in _BINDING_ORDER:
                color = BINDING_COLORS.get(b_source, "#888888")
                vals = sub.loc[
                    sub["binding_source"] == b_source, "mlog10_pval"
                ].dropna()
                if vals.empty:
                    continue
                sorted_vals = np.sort(vals.values)
                ecdf = np.arange(1, len(sorted_vals) + 1) / len(sorted_vals)
                fig.add_trace(
                    go.Scatter(
                        x=sorted_vals,
                        y=ecdf,
                        mode="lines",
                        line=dict(color=color, width=1.5),
                        name=b_source,
                        legendgroup=b_source,
                        showlegend=(col_idx == 1),
                    ),
                    row=1,
                    col=col_idx,
                )
            fig.update_xaxes(title_text="-log10(p + 0.001)", row=1, col=col_idx)

        fig.update_yaxes(title_text="ECDF", row=1, col=1)
        fig.update_layout(
            legend_title="Binding source",
            margin=dict(l=50, r=20, t=50, b=50),
        )
        return ui.HTML(to_html(fig, include_plotlyjs="cdn", full_html=False))

    @render.ui
    def topn_plot() -> ui.Tag:
        """
        Boxplot of percent-responsive for top-N binding targets.

        The facet orientation is controlled by ``facet_by``:
        - ``"binding"``: binding source = facet columns, perturbation = color
        - ``"perturbation"``: perturbation source = facet columns, binding = color

        :trigger _topn_data: re-renders when top-N data changes.
        :trigger facet_by: re-renders when facet orientation changes.
        :trigger top_n: title updates.

        """
        df = _topn_data()
        n = top_n()
        orientation = facet_by()

        if df.empty:
            return ui.div(
                {"class": "empty-state"},
                ui.p("No top-N data available for the selected datasets."),
            )

        if orientation == "binding":
            facet_col = "binding_source"
            x_col = "perturbation_source"
            facet_order = [
                b for b in _BINDING_ORDER if b in df["binding_source"].unique()
            ]
            x_order = [
                p for p in _PERT_ORDER if p in df["perturbation_source"].unique()
            ]
            palette = PERTURBATION_COLORS
            legend_title = "Perturbation source"
        else:
            facet_col = "perturbation_source"
            x_col = "binding_source"
            facet_order = [
                p for p in _PERT_ORDER if p in df["perturbation_source"].unique()
            ]
            x_order = [b for b in _BINDING_ORDER if b in df["binding_source"].unique()]
            palette = BINDING_COLORS
            legend_title = "Binding source"

        facets = [f for f in facet_order if f in df[facet_col].unique()]
        xs = [x for x in x_order if x in df[x_col].unique()]

        if not facets or not xs:
            return ui.div(
                {"class": "empty-state"}, ui.p("No data for selected combination.")
            )

        fig = make_subplots(
            rows=1, cols=len(facets), subplot_titles=facets, shared_yaxes=True
        )

        for col_idx, facet_val in enumerate(facets, start=1):
            sub = df[df[facet_col] == facet_val]
            for x_val in xs:
                color = palette.get(x_val, "#888888")
                vals = sub.loc[sub[x_col] == x_val, "percent_responsive"].dropna()
                fig.add_trace(
                    go.Box(
                        y=vals,
                        name=x_val,
                        marker_color=color,
                        boxpoints="all",
                        jitter=0.4,
                        pointpos=0,
                        marker=dict(size=3, opacity=0.45),
                        line=dict(width=1.2),
                        legendgroup=x_val,
                        showlegend=(col_idx == 1),
                    ),
                    row=1,
                    col=col_idx,
                )
            fig.update_xaxes(showticklabels=False, row=1, col=col_idx)

        fig.update_yaxes(
            title_text="% responsive in top N", range=[0, 100], row=1, col=1
        )
        fig.update_layout(
            title=f"Top {n} by binding — % responsive",
            legend_title=legend_title,
            margin=dict(l=50, r=20, t=60, b=30),
        )
        return ui.HTML(to_html(fig, include_plotlyjs="cdn", full_html=False))


__all__ = ["comparison_workspace_server"]
