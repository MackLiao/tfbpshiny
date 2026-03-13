"""
Standalone app for developing the Select Datasets page in isolation.

Run with:
    poetry run shiny run tfbpshiny/modules/select_datasets/page_test.py

"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from shiny import App, ui
from tfbpapi import VirtualDB

from tfbpshiny.modules.select_datasets.server import (
    select_datasets_sidebar_server,
    select_datasets_workspace_server,
)
from tfbpshiny.modules.select_datasets.ui import (
    selection_matrix_ui,
    selection_sidebar_ui,
)

logger = logging.getLogger("shiny")
vdb = VirtualDB(
    (Path(__file__).parents[3] / "brentlab_yeast_collection.yaml").resolve()
)

app_ui = ui.page_fillable(
    ui.div(
        {"class": "app-body", "style": "display:flex; height:100vh;"},
        selection_sidebar_ui("select_datasets_sidebar"),
        selection_matrix_ui("select_datasets_workspace"),
    ),
    padding=0,
    gap=0,
)


def server(input: Any, output: Any, session: Any) -> None:
    active_binding_datasets, active_perturbation_datasets, dataset_filters = (
        select_datasets_sidebar_server(
            "select_datasets_sidebar", vdb=vdb, logger=logger
        )
    )
    select_datasets_workspace_server(
        "select_datasets_workspace",
        active_binding_datasets=active_binding_datasets,
        active_perturbation_datasets=active_perturbation_datasets,
        dataset_filters=dataset_filters,
        vdb=vdb,
        logger=logger,
    )


app = App(ui=app_ui, server=server)
