"""Vertical icon-rail navigation module."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from shiny import module, reactive, render, ui

_MODULE_ITEMS: list[dict[str, str]] = [
    {"id": "selection", "label": "Selection", "tag": "Active Set"},
    {"id": "binding", "label": "Binding", "tag": "Binding"},
    {"id": "perturbation", "label": "Perturbation", "tag": "Perturb"},
    {"id": "composite", "label": "Composite", "tag": "Composite"},
]


@module.ui
def nav_ui() -> ui.Tag:
    """Render the vertical nav rail with labeled page tags."""
    return ui.div(
        {"class": "nav-rail"},
        ui.div({"class": "nav-logo"}, "TF"),
        ui.output_ui("nav_buttons"),
    )


@module.server
def nav_server(
    input: Any,
    output: Any,
    session: Any,
    active_module: reactive.Value[str],
    on_module_change: Callable[[str], None] | None = None,
) -> None:
    """Handle nav button clicks and update *active_module*."""

    @render.ui
    def nav_buttons() -> ui.Tag:
        current = active_module()
        buttons: list[ui.Tag] = []
        for item in _MODULE_ITEMS:
            is_active = item["id"] == current
            buttons.append(
                ui.input_action_button(
                    item["id"],
                    item["tag"],
                    class_=f"nav-btn{' active' if is_active else ''}",
                    title=item["label"],
                )
            )
        return ui.div({"class": "nav-tags"}, *buttons)

    @reactive.effect
    @reactive.event(input.selection, ignore_init=True)
    def _click_selection() -> None:
        active_module.set("selection")
        if on_module_change:
            on_module_change("selection")

    @reactive.effect
    @reactive.event(input.binding, ignore_init=True)
    def _click_binding() -> None:
        active_module.set("binding")
        if on_module_change:
            on_module_change("binding")

    @reactive.effect
    @reactive.event(input.perturbation, ignore_init=True)
    def _click_perturbation() -> None:
        active_module.set("perturbation")
        if on_module_change:
            on_module_change("perturbation")

    @reactive.effect
    @reactive.event(input.composite, ignore_init=True)
    def _click_composite() -> None:
        active_module.set("composite")
        if on_module_change:
            on_module_change("composite")
