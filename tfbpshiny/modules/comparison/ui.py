"""UI functions for the Comparison module."""

from __future__ import annotations

from shiny import module, ui

from tfbpshiny.components import (
    sidebar_heading,
    sidebar_shell,
    workspace_heading,
    workspace_shell,
)


@module.ui
def comparison_sidebar_ui() -> ui.Tag:
    return sidebar_shell(
        "comparison-sidebar",
        header=sidebar_heading("Comparison"),
        body=ui.output_ui("sidebar_controls"),
    )


@module.ui
def comparison_workspace_ui() -> ui.Tag:
    return workspace_shell(
        "comparison-workspace",
        header=workspace_heading("Comparison"),
        body=ui.div(
            ui.div(
                {"class": "workspace-section"},
                ui.h3("Dual Threshold Optimization"),
                ui.output_ui("dto_plot"),
            ),
            ui.hr(),
            ui.div(
                {"class": "workspace-section"},
                ui.h3("Top N by Binding"),
                ui.output_ui("topn_plot"),
            ),
        ),
    )


__all__ = ["comparison_sidebar_ui", "comparison_workspace_ui"]
