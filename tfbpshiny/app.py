from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Literal, cast

from dotenv import load_dotenv
from labretriever import VirtualDB
from shiny import App, reactive, render, ui

from configure_logger import configure_logger
from tfbpshiny.components import github_badge, nav_button
from tfbpshiny.modules.binding.server import (
    binding_sidebar_server,
    binding_workspace_server,
)
from tfbpshiny.modules.binding.ui import binding_sidebar_ui, binding_workspace_ui
from tfbpshiny.modules.comparison.server import (
    comparison_sidebar_server,
    comparison_workspace_server,
)
from tfbpshiny.modules.comparison.ui import (
    comparison_sidebar_ui,
    comparison_workspace_ui,
)
from tfbpshiny.modules.home.ui import home_ui
from tfbpshiny.modules.perturbation.server import (
    perturbation_sidebar_server,
    perturbation_workspace_server,
)
from tfbpshiny.modules.perturbation.ui import (
    perturbation_sidebar_ui,
    perturbation_workspace_ui,
)
from tfbpshiny.modules.select_datasets.server import (
    select_datasets_sidebar_server,
    select_datasets_workspace_server,
)
from tfbpshiny.modules.select_datasets.ui import (
    selection_matrix_ui,
    selection_sidebar_ui,
)

if not os.getenv("DOCKER_ENV"):
    load_dotenv(dotenv_path=Path(".env"))

logger = logging.getLogger("shiny")

log_file = f"tfbpshiny_{time.strftime('%Y%m%d-%H%M%S')}.log"
log_level = int(os.getenv("TFBPSHINY_LOG_LEVEL", "10"))
handler_type = cast(
    Literal["console", "file"], os.getenv("TFBPSHINY_LOG_HANDLER", "console")
)
configure_logger(
    "shiny",
    level=log_level,
    handler_type=handler_type,
    log_file=log_file,
)

# instantiate the virtualDB

virtualdb_config = os.getenv(
    "VIRTUALDB_CONFIG", str(Path(__file__).parent / "brentlab_yeast_collection.yaml")
)
hf_token: str | None = os.getenv("HF_TOKEN")
logger.info(f"Loading VirtualDB with config: {virtualdb_config}")
vdb = VirtualDB(virtualdb_config, token=hf_token)

app_ui = ui.page_fillable(
    ui.include_css((Path(__file__).parent / "app.css").resolve()),
    ui.div(
        {"class": "app-container"},
        ui.div(
            {"class": "nav-bar"},
            ui.div({"class": "nav-logo"}, "TF\nBinding & Perturbation\nExplorer"),
            ui.div(
                {"class": "nav-tags"},
                nav_button("home", "Home"),
                nav_button("selection", "Dataset selection"),
                nav_button("binding", "Binding"),
                nav_button("perturbation", "Perturbation"),
                nav_button("comparison", "Comparison"),
            ),
            github_badge(),
        ),
        ui.div(
            {"class": "app-body"},
            ui.output_ui("sidebar_region"),
            ui.output_ui("workspace_region"),
        ),
    ),
    padding=0,
    gap=0,
)


def app_server(input: Any, output: Any, session: Any) -> None:
    """Create shared reactive state and call all module servers."""

    # this stores the name of the currently active module, ie
    # "home", "selection", "binding", "perturbation", or "comparison"
    active_module: reactive.Value[str] = reactive.value("home")

    # Dataset selection state — shared across all analysis modules
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

    corr_type, col_preference = binding_sidebar_server(
        "binding_sidebar",
        active_binding_datasets=active_binding_datasets,
        dataset_filters=dataset_filters,
        vdb=vdb,
        logger=logger,
    )
    binding_workspace_server(
        "binding_workspace",
        active_binding_datasets=active_binding_datasets,
        corr_type=corr_type,
        col_preference=col_preference,
        dataset_filters=dataset_filters,
        vdb=vdb,
        logger=logger,
    )

    corr_type_p, col_preference_p = perturbation_sidebar_server(
        "perturbation_sidebar",
        active_perturbation_datasets=active_perturbation_datasets,
        dataset_filters=dataset_filters,
        vdb=vdb,
        logger=logger,
    )
    perturbation_workspace_server(
        "perturbation_workspace",
        active_perturbation_datasets=active_perturbation_datasets,
        corr_type=corr_type_p,
        col_preference=col_preference_p,
        dataset_filters=dataset_filters,
        vdb=vdb,
        logger=logger,
    )

    top_n, effect_threshold, pvalue_threshold, facet_by = comparison_sidebar_server(
        "comparison_sidebar",
        active_binding_datasets=active_binding_datasets,
        active_perturbation_datasets=active_perturbation_datasets,
        vdb=vdb,
        logger=logger,
    )
    comparison_workspace_server(
        "comparison_workspace",
        active_binding_datasets=active_binding_datasets,
        active_perturbation_datasets=active_perturbation_datasets,
        dataset_filters=dataset_filters,
        top_n=top_n,
        effect_threshold=effect_threshold,
        pvalue_threshold=pvalue_threshold,
        facet_by=facet_by,
        vdb=vdb,
        logger=logger,
    )

    # set the active module when a nav button is clicked
    @reactive.effect
    @reactive.event(input.home, ignore_init=True)
    def _nav_home() -> None:
        """
        Switch the active module to the home page.

        :trigger: ``input.home`` — fires when the user clicks the HOME nav button.

        """
        active_module.set("home")

    @reactive.effect
    @reactive.event(input.selection, ignore_init=True)
    def _nav_selection() -> None:
        """
        Switch the active module to the dataset selection page.

        :trigger: ``input.selection`` — fires when the user clicks the SELECT
            DATASETS nav button.

        """
        active_module.set("selection")

    @reactive.effect
    @reactive.event(input.binding, ignore_init=True)
    def _nav_binding() -> None:
        """
        Switch the active module to the binding data page.

        :trigger: ``input.binding`` — fires when the user clicks the BINDING nav
            button.

        """
        active_module.set("binding")

    @reactive.effect
    @reactive.event(input.perturbation, ignore_init=True)
    def _nav_perturbation() -> None:
        """
        Switch the active module to the perturbation data page.

        :trigger: ``input.perturbation`` — fires when the user clicks the
            PERTURBATION nav button.

        """
        active_module.set("perturbation")

    @reactive.effect
    @reactive.event(input.comparison, ignore_init=True)
    def _nav_comparison() -> None:
        """
        Switch the active module to the comparison analysis page.

        :trigger: ``input.comparison`` — fires when the user clicks the COMPARISON
            nav button.

        """
        active_module.set("comparison")

    # The page is always divided into a sidebar region and workspace region
    # this renders the sidebar region according to the active module
    @render.ui
    def sidebar_region() -> ui.Tag:
        selected_module = active_module()
        logger.debug(f"Rendering sidebar for active module: {selected_module}")
        if selected_module == "home":
            # no sidebar for home module
            return ui.span()
        if selected_module == "selection":
            return selection_sidebar_ui("select_datasets_sidebar")
        if selected_module == "binding":
            return binding_sidebar_ui("binding_sidebar")
        if selected_module == "perturbation":
            return perturbation_sidebar_ui("perturbation_sidebar")
        if selected_module == "comparison":
            return comparison_sidebar_ui("comparison_sidebar")
        logger.error(f"No sidebar for active module: {selected_module}")
        return ui.span(ui.p("ERROR: No sidebar for: " + selected_module))

    # this renders the workspace region according to the active module
    @render.ui
    def workspace_region() -> ui.Tag:
        selected_module = active_module()
        logger.debug(f"Rendering workspace for active module: {selected_module}")
        if selected_module == "home":
            return home_ui()
        if selected_module == "selection":
            return selection_matrix_ui("select_datasets_workspace")
        if selected_module == "binding":
            return binding_workspace_ui("binding_workspace")
        if selected_module == "perturbation":
            return perturbation_workspace_ui("perturbation_workspace")
        if selected_module == "comparison":
            return comparison_workspace_ui("comparison_workspace")
        logger.error(f"No workspace for active module: {selected_module}")
        return ui.span(ui.p("ERROR: No workspace for: " + selected_module))


app = App(ui=app_ui, server=app_server)
