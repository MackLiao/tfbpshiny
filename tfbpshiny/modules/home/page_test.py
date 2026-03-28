"""
Standalone app for developing the Home page in isolation.

Run with:
    poetry run shiny run tfbpshiny/home/page_test.py

"""

from __future__ import annotations

from typing import Any

from shiny import App, ui

from tfbpshiny.modules.home.ui import home_ui

app_ui = ui.page_fillable(
    home_ui(),
    padding=0,
    gap=0,
)


def server(input: Any, output: Any, session: Any) -> None:
    pass


app = App(ui=app_ui, server=server)
