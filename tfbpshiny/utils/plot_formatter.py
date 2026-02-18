"""Shared Plotly figure formatting for distribution plots."""

from __future__ import annotations

from plotly.graph_objects import Figure


def plot_formatter(
    fig: Figure,
    x_axis_title: str,
    y_axis_title: str,
    *,
    height: int = 500,
) -> Figure:
    """
    Apply consistent styling to a faceted box-plot figure.

    - Strips the ``facet_col=`` prefix from subplot titles.
    - Sets axis labels and layout dimensions.
    - Uses a clean white background with a shared legend.

    """
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))

    fig.update_layout(
        showlegend=True,
        legend_title_text="Binding Source",
        height=height,
        margin=dict(t=60, b=80, l=60, r=30),
        plot_bgcolor="white",
    )

    fig.update_xaxes(title_text=x_axis_title)
    fig.update_yaxes(title_text=y_axis_title, col=1)

    return fig
