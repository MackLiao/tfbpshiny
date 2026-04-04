"""Sidebar server for the Comparison module."""

from __future__ import annotations

from collections.abc import Callable
from logging import Logger
from typing import Any

from labretriever import VirtualDB
from shiny import module, reactive, render, ui

from tfbpshiny.components import sidebar_section
from tfbpshiny.modules.comparison.queries import (
    DEFAULT_EFFECT_THRESHOLD,
    DEFAULT_PVALUE_THRESHOLD,
    DEFAULT_TOP_N,
)


@module.server
def comparison_sidebar_server(
    input: Any,
    output: Any,
    session: Any,
    active_binding_datasets: reactive.Calc_[list[str]],
    active_perturbation_datasets: reactive.Calc_[list[str]],
    vdb: VirtualDB,
    logger: Logger,
) -> tuple[
    Callable[[], int],  # top_n
    Callable[[], float],  # effect_threshold
    Callable[[], float],  # pvalue_threshold
    Callable[[], str],  # facet_by: "binding" | "perturbation"
]:
    """
    Render comparison sidebar controls and return reactive selections.

    The sidebar has two sections matching the two workspace rows:
    - **Dual Threshold Optimization**: no user controls (DTO is pre-computed).
    - **Top N by Binding**: top_n, effect threshold, pvalue threshold,
        facet orientation.

    :returns: Tuple of (top_n, effect_threshold, pvalue_threshold, facet_by).

    """

    @reactive.calc
    def top_n() -> int:
        """
        Number of top binding targets to keep per sample.

        :trigger input.top_n: fires when the user changes the numeric input.
        :returns: Integer >= 1; defaults to ``DEFAULT_TOP_N``.

        """
        try:
            val = int(input.top_n())
            return max(1, val)
        except Exception:
            return DEFAULT_TOP_N

    @reactive.calc
    def effect_threshold() -> float:
        """
        Minimum absolute effect size for a perturbation target to be responsive.

        :trigger input.effect_threshold: fires when the slider changes.
        :returns: Float >= 0; defaults to ``DEFAULT_EFFECT_THRESHOLD``.

        """
        try:
            return float(input.effect_threshold())
        except Exception:
            return DEFAULT_EFFECT_THRESHOLD

    @reactive.calc
    def pvalue_threshold() -> float:
        """
        Maximum p-value for a perturbation target to be responsive.

        :trigger input.pvalue_threshold: fires when the slider changes.
        :returns: Float in (0, 1]; defaults to ``DEFAULT_PVALUE_THRESHOLD``.

        """
        try:
            return float(input.pvalue_threshold())
        except Exception:
            return DEFAULT_PVALUE_THRESHOLD

    @reactive.calc
    def facet_by() -> str:
        """
        Controls which dimension forms the facets vs the color grouping.

        :trigger input.facet_by: fires when the user changes the radio button.
        :returns:``"binding"`` (binding = facets, perturbation = color) or
            ``"perturbation"`` (perturbation = facets, binding = color).

        """
        try:
            return str(input.facet_by())
        except Exception:
            return "binding"

    @render.ui
    def sidebar_controls() -> ui.Tag:
        binding = active_binding_datasets()
        perturbation = active_perturbation_datasets()

        if not binding or not perturbation:
            return ui.div(
                {"class": "empty-state compact"},
                ui.p(
                    "Select at least one binding and one perturbation dataset "
                    "from the Select Datasets page."
                ),
            )

        return ui.div(
            # DTO section — no controls
            sidebar_section(
                "Dual Threshold Optimization",
                ui.p(
                    {"class": "text-muted", "style": "font-size:0.85em;"},
                    "DTO results are pre-computed; no parameters to set.",
                ),
            ),
            ui.hr(),
            # Top-N section
            sidebar_section(
                "Top N by Binding",
                ui.input_numeric(
                    "top_n",
                    "Top N",
                    value=top_n(),
                    min=1,
                    max=500,
                    step=5,
                ),
                ui.div({"class": "sidebar-section-title"}, "Responsive threshold"),
                ui.input_slider(
                    "effect_threshold",
                    "Min |effect|",
                    min=0.0,
                    max=5.0,
                    value=effect_threshold(),
                    step=0.1,
                ),
                ui.input_slider(
                    "pvalue_threshold",
                    "Max p-value",
                    min=0.001,
                    max=1.0,
                    value=pvalue_threshold(),
                    step=0.001,
                ),
                ui.div({"class": "sidebar-section-title"}, "Facet by"),
                ui.input_radio_buttons(
                    "facet_by",
                    label=None,
                    choices={
                        "binding": "Binding source",
                        "perturbation": "Perturbation source",
                    },
                    selected=facet_by(),
                ),
            ),
        )

    return top_n, effect_threshold, pvalue_threshold, facet_by


__all__ = ["comparison_sidebar_server"]
