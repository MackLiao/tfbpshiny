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


def _feature_card(
    title: str,
    target_id: str,
    description: str,
    *,
    image: str | None = None,
) -> ui.Tag:
    """
    Feature card for the home page grid.

    :param title: Card heading (rendered as a nav link).
    :param target_id: Shiny input ID of the nav button to navigate to.
    :param description: Short description text below the title.
    :param image: Optional filename in ``www/`` to display above the title.

    """
    content = ui.div(
        {"class": "home-card-content"},
        ui.div({"class": "home-card-title"}, _nav_link(title, target_id)),
        ui.div({"class": "home-card-text"}, description),
    )
    if image is not None:
        return ui.div(
            {"class": "home-card"},
            ui.img(src=image, alt=title),
            content,
        )
    return ui.div({"class": "home-card"}, content)


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
        ui.div(
            {"class": "home-cards"},
            _feature_card(
                "Dataset selection",
                "selection",
                "Choose which binding and perturbation datasets to include "
                "in your analysis.",
            ),
            _feature_card(
                "Binding",
                "binding",
                "Compare TF binding targets in the selected binding " "datasets.",
                image="binding.png",
            ),
            _feature_card(
                "Perturbation",
                "perturbation",
                "Compare transcriptional responses to TF perturbations in "
                "the selected perturbation datasets.",
                image="perturbation.png",
            ),
            _feature_card(
                "Comparison",
                "comparison",
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
