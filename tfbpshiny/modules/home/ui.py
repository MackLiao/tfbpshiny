"""Splash page shown on initial load."""

from shiny import ui


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
            "This application provides an interactive interface for exploring "
            "datasets of transcription factor (TF) binding and gene expression "
            "responses following TF perturbation in yeast."
        ),
        ui.h3("How to"),
        ui.p(
            "Navigate through the tabs above to select datasets and compare them "
            "both within and across binding and perturbation types"
        ),
        ui.tags.ul(
            ui.tags.li(
                ui.strong("Select Datasets: "),
                "Choose which binding and perturbation datasets to include in your "
                "analysis. Use the 'filter' for each dataset to select samples "
                "by regulator or experimental condition. The matrix shows how many "
                "samples each selected dataset contributes, and how many samples are "
                "shared across dataset pairs based on common regulators.",
            ),
            ui.tags.li(
                ui.strong("Binding: "),
                ui.em("(Under development.) "),
                "Explore how TF binding targets compare across the selected binding "
                "datasets.",
            ),
            ui.tags.li(
                ui.strong("Perturbation: "),
                ui.em("(Under development.) "),
                "Explore how transcriptional responses to TF perturbations "
                "(gene deletion, overexpression, and TF degradation) compare across "
                "the selected perturbation datasets.",
            ),
            ui.tags.li(
                ui.strong("Comparison: "),
                ui.em("(Under development.) "),
                "Compare selected binding datasets to selected perturbation datasets. "
                "Rank response and dual threshold optimization are implemented. "
                "Dual threshold optimization is an algorithm developed in the Brent "
                "lab to find the optimal rank thresholds on two ranked lists that "
                "minimize the hypergeometric p-value — see ",
                ui.a(
                    "Kang et al., Genome Research 2020",
                    href="https://pubmed.ncbi.nlm.nih.gov/32060051/",
                    target="_blank",
                ),
                " for details.",
            ),
        ),
        ui.h3("Getting Started"),
        ui.p(
            "Begin with ",
            ui.strong("Select Datasets"),
            " to choose and filter the datasets you want to analyse, "
            "then navigate to the other tabs to explore the results.",
        ),
    )
