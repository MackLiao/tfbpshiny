from __future__ import annotations

import itertools
from collections.abc import Callable
from logging import Logger
from typing import Any, Literal

import pandas as pd
import plotly.graph_objects as go
from labretriever import VirtualDB
from plotly.io import to_html
from shiny import module, reactive, render, ui

from tfbpshiny.modules.perturbation.queries import (
    corr_pair_sql,
    get_measurement_column,
    regulator_scatter_sql,
    regulator_symbols_query,
)


@module.server
def perturbation_workspace_server(
    input: Any,
    output: Any,
    session: Any,
    active_perturbation_datasets: reactive.Calc_[list[str]],
    corr_type: Callable[[], str],
    col_preference: Callable[[], str],
    dataset_filters: reactive.Value[dict[str, Any]],
    vdb: VirtualDB,
    logger: Logger,
) -> None:
    """
    Render the perturbation correlation rows: pairwise distributions
    and per-regulator plots.
    """

    display_names: dict[str, str] = {
        db_name: vdb.get_tags(db_name).get("display_name", db_name)
        for db_name in vdb.get_datasets()
    }

    @reactive.calc
    def _pairs() -> list[tuple[str, str]]:
        """
        All unique pairs of active perturbation datasets.

        :trigger active_perturbation_datasets: re-runs whenever the user toggles
            a perturbation dataset on or off in the Select Datasets sidebar.
        :returns: List of ``(db_a, db_b)`` tuples, length = n_active choose 2.

        """
        active = active_perturbation_datasets()
        return list(itertools.combinations(active, 2))

    @reactive.calc
    def _all_corr_data() -> dict[tuple[str, str], pd.DataFrame]:
        """
        Per-regulator correlation values for every active dataset pair.

        The heart of this function is a for loop over the dataset pairs. In each
        iteration, the user selected measurement column (effect or p-value),
        filters for that dataset, and the correlation method (pearson or spearman) are
        submitted along with the virtualDB instance to `corr_pair_sql()`
        (see queries.py), which uses the duckDB aggregate functions to compute
        correlations. The join is done on (regulator_locus_tag, target_locus_tag).
        NOTE: if there are multiple samples for a given regulator_locus_tag, then
        there will be multiple correlation values for that regulator in the output
        dataframe.

        :trigger _pairs: re-runs when the set of active pairs changes.
        :trigger col_preference: re-runs when the user switches between Effect
            and P-value columns.
        :trigger corr_type: re-runs when the user switches between Pearson and
            Spearman.
        :trigger dataset_filters: re-runs when filters are applied or reset for
            any dataset.
        :returns: a dict with keys ``(db_a, db_b)`` and values a dataframe
            with columns ``db_a``, ``db_a_id``, ``db_b``, ``db_b_id``,
            ``regulator_locus_tag`` and ``correlation``. Failed pairs are stored as
            empty DataFrames so downstream renders can handle them gracefully. The
            failure and error are logged at the ERROR level.

        """
        pairs = _pairs()
        # TODO: get rid of the type ignore
        preference: Literal["effect", "pvalue"] = col_preference()  # type: ignore[assignment] # noqa: E501
        method = corr_type()
        filters = dataset_filters()

        if not pairs:
            return {}

        result: dict[tuple[str, str], pd.DataFrame] = {}
        for i, (db_a, db_b) in enumerate(pairs):
            try:
                col_a = get_measurement_column(db_a, preference)
                col_b = get_measurement_column(db_b, preference)
                logger.debug(
                    f"Correlating {db_a}({col_a}) vs {db_b}({col_b}) ({method})"
                )
                result[(db_a, db_b)] = corr_pair_sql(
                    vdb,
                    db_a,
                    col_a,
                    filters.get(db_a),
                    db_b,
                    col_b,
                    filters.get(db_b),
                    method,
                    prefix=f"p{i}_",
                )
            except Exception as exc:
                logger.error(
                    f"Failed to correlate {db_a} vs {db_b}: {exc}", exc_info=True
                )
                result[(db_a, db_b)] = pd.DataFrame(
                    columns=[
                        "db_a",
                        "db_a_id",
                        "db_b",
                        "db_b_id",
                        "regulator_locus_tag",
                        "correlation",
                    ]
                )

        return result

    @render.ui
    def distributions_plot() -> ui.Tag:
        """
        Box-plot of per-regulator correlation values for every active pair.

        :trigger _pairs: re-renders when the set of active pairs changes. :trigger
        _all_corr_data: re-renders when correlation data is recomputed. :trigger
        corr_type: re-renders when the correlation method changes     (updates the
        axis/title label).

        """
        pairs = _pairs()
        corr_data = _all_corr_data()
        method = corr_type().capitalize()

        fig = go.Figure()

        if not pairs:
            fig.add_annotation(
                text="Select at least two perturbation datasets to see correlations.",
                xref="paper",
                yref="paper",
                x=0.5,
                y=0.5,
                showarrow=False,
            )
            return ui.HTML(to_html(fig, include_plotlyjs="cdn", full_html=False))

        for db_a, db_b in pairs:
            df = corr_data.get((db_a, db_b), pd.DataFrame())
            label_a = display_names.get(db_a, db_a)
            label_b = display_names.get(db_b, db_b)
            pair_label = f"{label_a}<br>vs<br>{label_b}"
            vals = (
                df["correlation"].dropna()
                if not df.empty
                else pd.Series([], dtype=float)
            )

            fig.add_trace(
                go.Box(
                    y=vals,
                    name=pair_label,
                    boxpoints="all",
                    jitter=0.4,
                    pointpos=0,
                    marker=dict(size=4, opacity=0.5),
                    line=dict(width=1.5),
                )
            )

        fig.update_layout(
            title=f"{method} correlation across regulators",
            yaxis_title=f"{method} r",
            showlegend=False,
            margin=dict(l=40, r=20, t=50, b=80),
        )
        return ui.HTML(to_html(fig, include_plotlyjs="cdn", full_html=False))

    @render.ui
    def regulator_selector() -> ui.Tag:
        """
        Dropdown of regulators present in at least one pair's correlation data.

        Choices are keyed by locus tag and labelled by gene symbol where available. The
        previously selected regulator is preserved across re-renders if it is still
        present in the new choice set.

        :trigger _all_corr_data: re-renders when correlation data changes (new
        datasets selected, filters applied, or column/method changed). :trigger
        active_perturbation_datasets: re-renders to refresh the symbol     map when the
        active dataset set changes.

        """
        corr_data = _all_corr_data()
        if not corr_data:
            return ui.span()

        active = active_perturbation_datasets()
        sym_map: dict[str, str] = {}
        for db in active:
            try:
                sym_df = vdb.query(regulator_symbols_query(db))
                sym_map.update(
                    zip(sym_df["regulator_locus_tag"], sym_df["regulator_symbol"])
                )
                break
            except Exception:
                pass

        all_regs: set[str] = set()
        for df in corr_data.values():
            if not df.empty:
                all_regs |= set(df["regulator_locus_tag"].dropna().unique())

        if not all_regs:
            return ui.span()
        choices = {
            r: f"{sym} ({r})" if (sym := sym_map.get(r) or "") else r
            for r in sorted(all_regs)
        }
        choices = dict(sorted(choices.items(), key=lambda kv: kv[1].lower()))

        try:
            current = str(input.selected_regulator())
        except Exception:
            current = ""
        default = current if current in choices else next(iter(choices))

        return ui.input_selectize(
            "selected_regulator",
            "Regulator",
            choices=choices,
            selected=default,
        )

    @render.ui
    def regulator_plots() -> ui.Tag:
        """
        Per-pair scatter plots for the selected regulator.

        Delegates to ``_build_regulator_plots``; catches and renders any
        unhandled exceptions as an annotated empty figure.

        :trigger input.selected_regulator: re-renders when the user picks a
            different regulator from the dropdown.
        :trigger _all_corr_data: re-renders when correlation data changes
            (new datasets, filters, column preference, or method).

        """
        try:
            return _build_regulator_plots()
        except Exception as exc:
            logger.exception("regulator_plots render failed")
            fig = go.Figure()
            fig.add_annotation(
                text=f"Error rendering plots: {exc}",
                xref="paper",
                yref="paper",
                x=0.5,
                y=0.5,
                showarrow=False,
            )
            return ui.HTML(to_html(fig, include_plotlyjs=False, full_html=False))

    def _build_regulator_plots() -> ui.Tag:
        try:
            reg = str(input.selected_regulator()) or None
        except Exception:
            reg = None
        pairs = list(_all_corr_data().keys())
        # TODO: get rid of the type ignore
        preference: Literal["effect", "pvalue"] = col_preference()  # type: ignore[assignment] # noqa: E501
        filters = dataset_filters()
        method = corr_type()

        if not reg or not pairs:
            fig = go.Figure()
            fig.add_annotation(
                text="Select a regulator above to see per-pair scatter plots.",
                xref="paper",
                yref="paper",
                x=0.5,
                y=0.5,
                showarrow=False,
            )
            return ui.HTML(to_html(fig, include_plotlyjs=False, full_html=False))

        # First pass: collect data and track which datasets are missing the regulator
        pair_data: list[tuple[str, str, str, str, object]] = []
        missing_datasets: set[str] = set()

        for idx, (db_a, db_b) in enumerate(pairs, start=1):
            try:
                col_a = get_measurement_column(db_a, preference)
                col_b = get_measurement_column(db_b, preference)
                scatter_sql, scatter_params = regulator_scatter_sql(
                    db_a,
                    col_a,
                    filters.get(db_a),
                    db_b,
                    col_b,
                    filters.get(db_b),
                    method,
                    reg,
                    idx,
                )
                merged = vdb.query(scatter_sql, **scatter_params)
            except Exception:
                logger.exception(f"Regulator plot fetch failed for {db_a}/{db_b}")
                continue

            if merged.empty:
                missing_datasets.add(display_names.get(db_a, db_a))
                missing_datasets.add(display_names.get(db_b, db_b))
                continue

            pair_data.append((db_a, db_b, col_a, col_b, merged))

        # Build one figure per valid pair
        plot_divs: list[ui.Tag] = []
        for db_a, db_b, col_a, col_b, merged in pair_data:
            la = display_names.get(db_a, db_a)
            lb = display_names.get(db_b, db_b)
            r = merged["_val_a"].corr(merged["_val_b"])

            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=merged["_val_a"],
                    y=merged["_val_b"],
                    mode="markers",
                    marker=dict(size=4, opacity=0.6, color="#4A90D9"),
                    text=merged["target_locus_tag"],
                    hovertemplate=(
                        "%{text}<br>"
                        + f"{la}: %{{x:.3f}}<br>"
                        + f"{lb}: %{{y:.3f}}<extra></extra>"
                    ),
                    showlegend=False,
                )
            )
            fig.add_annotation(
                text=f"r={r:.3f}",
                xref="paper",
                yref="paper",
                x=0.98,
                y=0.98,
                xanchor="right",
                yanchor="top",
                showarrow=False,
                font=dict(size=12),
            )
            fig.update_layout(
                title=dict(
                    text=f"{la}<br>vs<br>{lb}",
                    x=0.5,
                    xanchor="center",
                ),
                xaxis_title=f"{la}: {col_a}",
                yaxis_title=f"{lb}: {col_b}",
                margin=dict(l=50, r=20, t=100, b=50),
                width=400,
                height=400,
            )
            plot_divs.append(
                ui.div(
                    ui.HTML(to_html(fig, include_plotlyjs=False, full_html=False)),
                    style="flex: 0 0 auto;",
                )
            )

        missing_note: list[ui.Tag] = []
        if missing_datasets:
            names = ", ".join(sorted(missing_datasets))
            missing_note.append(
                ui.p(
                    f"{reg} was not found in: {names}. "
                    "Pairs involving these datasets are omitted.",
                    style="color: gray; font-style: italic; margin: 0.5rem 0;",
                )
            )

        return ui.div(
            *missing_note,
            ui.div(
                *plot_divs,
                style="display: flex; flex-wrap: wrap; gap: 1rem; align-items: flex-start;",  # noqa: E501
            ),
        )


__all__ = ["perturbation_workspace_server"]
