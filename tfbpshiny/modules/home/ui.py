"""Splash page shown on initial load."""

from shiny import ui


def _nav_link(label: str, target_id: str) -> ui.Tag:
    """
    Bold link that clicks a nav button to navigate to a page.

    :param label: Display text for the link.
    :param target_id: The Shiny input ID of the nav button to click.

    """
    return ui.a(
        label,
        href="#",
        onclick=f"document.getElementById('{target_id}').click(); return false;",
        style="font-weight: bold;",
    )


def home_ui() -> ui.Tag:
    return ui.div(
        {"class": "home-content p-4"},
        ui.div(
            {"class": "alert alert-warning", "role": "alert"},
            ui.strong("Under development: "),
            "excuse the mess. Projected release: April, 2026.",
        ),
        ui.h2("Welcome to the TF Binding and Perturbation Explorer"),
        ui.p(
            "Explore datasets of transcription factor (TF) binding and gene "
            "expression responses following TF perturbation. Compare growth "
            "conditions, experimental techniques, or analytic techniques. "
            "Currently, all datasets are for ",
            ui.em("Saccharomyces cerevisiae"),
            " (yeast).",
        ),
        ui.h3("How to"),
        ui.p(
            "The tabs above take you to pages for selecting and comparing " "datasets."
        ),
        ui.tags.ul(
            ui.tags.li(
                _nav_link("Dataset selection: ", "selection"),
                "Choose which binding and perturbation datasets to include "
                "in your analysis.",
            ),
            ui.tags.li(
                _nav_link("Binding: ", "binding"),
                "Compare TF binding targets in the selected binding datasets.",
            ),
            ui.tags.li(
                _nav_link("Perturbation: ", "perturbation"),
                "Compare transcriptional responses to TF perturbations in "
                "the selected perturbation datasets.",
            ),
            ui.tags.li(
                _nav_link("Comparison: ", "comparison"),
                "Compare selected binding datasets to selected perturbation "
                "datasets.",
            ),
        ),
        ui.h3("Getting Started"),
        ui.p(
            "Begin with ",
            _nav_link("Dataset selection", "selection"),
            " to choose and filter the datasets you want to analyse, "
            "then navigate to the other tabs to explore the results.",
        ),
    )
