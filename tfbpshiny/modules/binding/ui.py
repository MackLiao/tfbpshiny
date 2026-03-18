"""UI functions for the Binding analysis page."""

from __future__ import annotations

from shiny import module, ui

from tfbpshiny.components import (
    sidebar_heading,
    sidebar_shell,
    workspace_heading,
    workspace_shell,
)


@module.ui
def binding_sidebar_ui() -> ui.Tag:
    return sidebar_shell(
        "binding-sidebar",
        header=sidebar_heading("Binding"),
        body=ui.output_ui("sidebar_controls"),
    )


@module.ui
def binding_workspace_ui() -> ui.Tag:
    return workspace_shell(
        "binding-workspace",
        header=workspace_heading("Binding Correlation"),
        body=ui.div(
            ui.output_ui("distributions_plot"),
            ui.hr(),
            ui.output_ui("regulator_selector"),
            ui.div(
                {"style": "min-height: 400px;"},
                ui.output_ui("regulator_plots"),
            ),
        ),
    )


__all__ = ["binding_sidebar_ui", "binding_workspace_ui"]
