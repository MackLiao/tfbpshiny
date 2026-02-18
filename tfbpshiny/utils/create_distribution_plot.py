"""Create faceted box-plot distributions for composite analysis."""

from __future__ import annotations

import logging

import pandas as pd
import plotly.express as px
from plotly.graph_objects import Figure

from .plot_formatter import plot_formatter

logger = logging.getLogger("shiny")


def create_distribution_plot(
    df: pd.DataFrame,
    y_column: str,
    y_axis_title: str,
    *,
    height: int = 500,
) -> Figure:
    """
    Create a faceted box-plot of *y_column* by binding x perturbation source.

    Category orders and color assignments are derived from the actual unique
    values present in the DataFrame — not from hardcoded constants.

    :param df: Must contain ``binding_source``, ``expression_source``,
        and the *y_column*.  Values should already be display-ready strings.
    :param y_column: Numeric column to plot on the y-axis.
    :param y_axis_title: Display label for the y-axis.
    :param kwargs: Forwarded to :func:`plot_formatter`.
    :returns: A styled Plotly :class:`Figure`.

    """
    required = {y_column, "binding_source", "expression_source"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"DataFrame missing required columns: {missing}")

    if not pd.api.types.is_numeric_dtype(df[y_column]):
        raise TypeError(f"Column {y_column} must be numeric")

    # Derive levels from the data itself — no enum dependency.
    binding_levels = sorted(df["binding_source"].unique().tolist())
    perturbation_levels = sorted(df["expression_source"].unique().tolist())

    category_orders = {
        "binding_source": binding_levels,
        "expression_source": perturbation_levels,
    }

    color_palette = px.colors.qualitative.Vivid
    color_discrete_map = {
        name: color_palette[i % len(color_palette)]
        for i, name in enumerate(binding_levels)
    }

    fig = px.box(
        df,
        x="binding_source",
        y=y_column,
        color="binding_source",
        facet_col="expression_source",
        facet_col_spacing=0.04,
        points="outliers",
        category_orders=category_orders,
        color_discrete_map=color_discrete_map,
    )

    return plot_formatter(fig, "Binding Data Source", y_axis_title, height=height)
