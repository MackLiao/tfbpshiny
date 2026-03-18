"""UI functions for the Perturbation analysis page."""

from __future__ import annotations

from shiny import module, ui

from tfbpshiny.components import (
    sidebar_heading,
    sidebar_shell,
    workspace_heading,
    workspace_shell,
)


@module.ui
def perturbation_sidebar_ui() -> ui.Tag:
    return sidebar_shell(
        "perturbation-sidebar",
        header=sidebar_heading("Perturbation"),
        body=ui.output_ui("sidebar_controls"),
    )


@module.ui
def perturbation_workspace_ui() -> ui.Tag:
    return workspace_shell(
        "perturbation-workspace",
        header=workspace_heading("Perturbation Analysis"),
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


__all__ = ["perturbation_sidebar_ui", "perturbation_workspace_ui"]
