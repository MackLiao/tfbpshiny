"""Sidebar server for the Binding analysis page."""

from __future__ import annotations

from collections.abc import Callable
from logging import Logger
from typing import Any

from labretriever import VirtualDB
from shiny import module, reactive, render, ui

from tfbpshiny.components import sidebar_section


@module.server
def binding_sidebar_server(
    input: Any,
    output: Any,
    session: Any,
    active_binding_datasets: reactive.Calc_[list[str]],
    dataset_filters: reactive.Value[dict[str, Any]],
    vdb: VirtualDB,
    logger: Logger,
) -> tuple[
    Callable[[], str],  # corr_type: "pearson" | "spearman"
    Callable[[], str],  # col_preference: "effect" | "pvalue"
]:
    """
    Render binding analysis sidebar controls; return reactive selections.

    :return: Tuple of (corr_type, col_preference).

    """

    @reactive.calc
    def corr_type() -> str:
        """
        Currently selected correlation method.

        :trigger input.corr_type: fires when the user changes the Correlation
            radio button in the sidebar.
        :returns: ``"pearson"`` or ``"spearman"``; defaults to ``"pearson"``
            before the input is rendered.

        """
        try:
            return str(input.corr_type())
        except Exception:
            return "pearson"

    @reactive.calc
    def col_preference() -> str:
        """
        Currently selected measurement column preference.

        :trigger input.col_preference: fires when the user changes the Column
            radio button in the sidebar.
        :returns: ``"effect"`` or ``"pvalue"``; defaults to ``"effect"``
            before the input is rendered.

        """
        try:
            return str(input.col_preference())
        except Exception:
            return "effect"

    @render.ui
    def sidebar_controls() -> ui.Tag:
        active = active_binding_datasets()

        if not active:
            return ui.div(
                {"class": "empty-state compact"},
                ui.p("Select binding datasets from the Select Datasets page."),
            )

        return ui.div(
            sidebar_section(
                "Column",
                ui.input_radio_buttons(
                    "col_preference",
                    label=None,
                    choices={"effect": "Effect", "pvalue": "P-value"},
                    selected=col_preference(),
                    inline=True,
                ),
            ),
            sidebar_section(
                "Correlation",
                ui.input_radio_buttons(
                    "corr_type",
                    label=None,
                    choices={"pearson": "Pearson", "spearman": "Spearman"},
                    selected=corr_type(),
                    inline=True,
                ),
            ),
        )

    return corr_type, col_preference


__all__ = ["binding_sidebar_server"]
