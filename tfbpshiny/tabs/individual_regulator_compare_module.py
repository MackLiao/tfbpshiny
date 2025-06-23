from logging import Logger

from shiny import Inputs, Outputs, Session, module, reactive, render, ui

from ..rank_response.replicate_plot_module import (
    rank_response_replicate_plot_overexpression_ui,
    rank_response_replicate_plot_server,
    rank_response_replicate_plot_tfko_ui,
)
from ..rank_response.replicate_selection_table_module import (
    DEFAULT_REPLICATE_SELECTION_TABLE_GENERAL_QC_COLUMNS,
    REPLICATE_SELECTION_TABLE_GENERAL_QC_CHOICES_DICT,
    REPLICATE_SELECTION_TABLE_INSERT_CHOICES_DICT,
    replicate_selection_table_server,
    replicate_selection_table_ui,
)
from ..rank_response.summarized_binding_perturbation_comparison_module import (
    DEFAULT_SUMMARIZED_BINDING_PERTURBATION_COLUMNS,
    SUMMARIZED_BINDING_PERTURBATION_CHOICES_DICT,
    SUMMARIZED_BINDING_PERTURBATION_DATABASE_IDENTIFIER_CHOICES_DICT,
    summarized_binding_perturbation_comparison_server,
    summarized_binding_perturbation_comparison_ui,
)
from ..utils.create_accordion_panel import create_accordion_panel


def rr_plot_panel(label: str, output_id: str) -> ui.nav_panel:
    """Create a panel for rank response plots with a specific label and output ID."""
    return ui.nav_panel(
        label,
        ui.div(
            ui.output_ui(output_id),
            style="max-width: 100%; overflow-x: auto;",
        ),
    )


@module.ui
def individual_regulator_compare_ui():

    general_ui_panel = create_accordion_panel(
        "General",
        ui.tooltip(
            ui.input_switch(
                "symbol_locus_tag_switch",
                label="Use Systematic Gene Names",
                value=False,
            ),
            ui.tags.div(
                "Switch to systematic gene names (e.g., locus tags) "
                "for selecting the regulator.",
                style="font-size: 1em; color: #ffffff; "
                "line-height: 1.6; padding: 4px 0;",
            ),
        ),
        ui.input_select(
            "regulator",
            label="Select Regulator",
            selectize=True,
            selected=None,
            choices=[],
        ),
    )

    replicate_selection_table_columns_panel = create_accordion_panel(
        "Replicate Selection Table Columns",
        ui.input_checkbox_group(
            "replicate_selection_table_general_qc_columns",
            label="General QC Metrics",
            choices=REPLICATE_SELECTION_TABLE_GENERAL_QC_CHOICES_DICT,
            selected=DEFAULT_REPLICATE_SELECTION_TABLE_GENERAL_QC_COLUMNS,
        ),
        ui.input_checkbox_group(
            "replicate_selection_table_insert_table_columns",
            label="Calling Cards QC Metrics",
            choices=REPLICATE_SELECTION_TABLE_INSERT_CHOICES_DICT,
            selected=[],
        ),
    )

    summarized_binding_perturbation_columns_panel = create_accordion_panel(
        "Comparison Summary Columns",
        ui.input_checkbox_group(
            "summarized_binding_perturbation_columns",
            label="Comparison Metrics",
            choices=SUMMARIZED_BINDING_PERTURBATION_CHOICES_DICT,
            selected=DEFAULT_SUMMARIZED_BINDING_PERTURBATION_COLUMNS,
        ),
        ui.input_checkbox_group(
            "database_identifier_columns",
            label="Database Identifier Columns",
            choices=SUMMARIZED_BINDING_PERTURBATION_DATABASE_IDENTIFIER_CHOICES_DICT,
            selected=[],
        ),
    )

    update_button_ui = (
        ui.input_action_button(
            "update_tables",
            "Update Tables",
            class_="btn-primary mt-2",
            style="width: 100%;",
        ),
    )

    option_panels = [
        general_ui_panel,
        replicate_selection_table_columns_panel,
        summarized_binding_perturbation_columns_panel,
    ]

    return ui.layout_sidebar(
        ui.sidebar(
            ui.accordion(
                *option_panels,
                id=module.resolve_id("input_accordion"),
                open=None,
                multiple=True,
            ),
            update_button_ui,
            width="300px",
        ),
        ui.div(
            ui.div(
                ui.p(
                    "This page shows comparisons between binding locations "
                    "and perturbation responses for individual TFs. Use the sidebar "
                    "to type in the name of a TF or select it from a drop-down menu. "
                    "Results are shown in the rank response plots and in summarized "
                    "binding-perturbation comparisons, each of which is explained "
                    "below.",
                ),
                ui.div(
                    ui.accordion(
                        ui.accordion_panel(
                            "Rank Response Plots Description",
                            ui.p(
                                ui.tags.strong("Overview:"),
                                ui.br(),
                                "Each solid line on a rank response plot shows a ",
                                "comparison of one binding dataset to one perturbation "
                                "dataset. The genes are first ranked according to the "
                                "strength of the perturbed TF's binding signal in their"
                                " regulatory DNA.",
                            ),
                            ui.p(
                                ui.tags.strong("Plot Axes:"),
                                ui.br(),
                                "The vertical axis shows the fraction of most "
                                "strongly bound genes that are responsive to the "
                                "perturbation. Responsiveness is determined using a "
                                "fixed threshold on the differential expression "
                                "p-value and/or log fold change. The horizontal axis "
                                "indicates the number of most strongly bound genes "
                                "considered. For example, 20 on the horizontal axis "
                                "indicates the 20 most strongly bound genes. There is "
                                "no fixed threshold on binding strength.",
                            ),
                            ui.p(
                                ui.tags.strong("Reference Lines:"),
                                ui.br(),
                                "The dashed horizontal "
                                "line shows the random expectation – the fraction of "
                                "all genes that are responsive. For example, a dashed "
                                "line at 0.1 means that 10% of all genes are "
                                "responsive to perturbation of this TF. The gray area "
                                "shows a 95% confidence interval for the null "
                                "hypothesis that the bound genes are no more responsive"
                                " than the random expectation.",
                            ),
                        ),
                        id="rank_response_plots_accordion",
                        open=False,
                    ),
                    ui.br(),
                    ui.div(
                        ui.tags.strong("How to Use:"),
                        " ",
                        "Clicking on rows in the ",
                        ui.tags.b("Replicate Selection Table"),
                        " controls which binding datasets are plotted. Tabs at "
                        "the top show plots for different perturbation "
                        "datasets. The sidebar allows control over which "
                        "columns are displayed in this table.",
                        style="padding: 10px; background-color: #f8f9fa; "
                        "border-left: 4px solid #007bff; "
                        "margin: 10px 0; "
                        "font-size: 0.9em;",
                    ),
                    ui.row(
                        ui.column(
                            7,
                            ui.card(
                                ui.card_header("Rank Response Plots"),
                                ui.navset_tab(
                                    *[
                                        rr_plot_panel("TFKO", "tfko_plots"),
                                        rr_plot_panel(
                                            "Overexpression", "overexpression_plots"
                                        ),
                                    ],
                                    id="plot_tabs",
                                ),
                            ),
                        ),
                        ui.column(
                            5,
                            ui.card(
                                ui.card_header("Replicate Selection Table"),
                                ui.div(
                                    replicate_selection_table_ui(
                                        "replicate_selection_table"
                                    ),
                                    style="overflow: auto; width: 100%;",
                                ),
                                ui.card_footer(
                                    ui.p(
                                        ui.tags.b("How to use: "),
                                        "Select rows in this table to filter and "
                                        "highlight corresponding data in the "
                                        "summarized binding-perturbation comparison "
                                        "table and plots. Multiple rows can be "
                                        "selected by holding Ctrl/Cmd while clicking.",
                                        style="margin: 0; font-size: 0.9em; "
                                        "color: #666; padding: 10px;",
                                    )
                                ),
                                style="display: flex; flex-direction: column; "
                                "min-height: 0; padding: 10px;",
                            ),
                        ),
                        style="min-height: 600px; margin-bottom: 20px;",
                    ),
                    style="margin-bottom: 1.5em;",
                ),
            ),
            ui.div(
                ui.accordion(
                    ui.accordion_panel(
                        "Summarized Binding-Perturbation Comparisons Description",
                        ui.p(
                            ui.tags.strong("Overview:"),
                            ui.br(),
                            "Each row of this table shows summary statistics "
                            "for comparisons of one binding dataset (or replicate) "
                            "to one perturbation-response dataset.",
                        ),
                        ui.p(
                            ui.tags.strong("Navigation:"),
                            ui.br(),
                            "The tabs at the top show tables for different "
                            "perturbation datasets. "
                            "The sidebar allows control over which columns are "
                            "displayed in this table.",
                        ),
                        ui.p(
                            ui.tags.strong("Analysis Methods:"),
                            ui.br(),
                            "The statistics are derived from three methods of "
                            "comparison:",
                        ),
                        ui.tags.ol(
                            ui.tags.li(
                                "Fraction responsive among the 25 or 50 most "
                                "strongly bound genes;"
                            ),
                            ui.tags.li(
                                "A linear model fit to predict the response "
                                "strength from the binding strength (",
                                ui.a("details here", href="#", target="_blank"),
                                ").",
                            ),
                            ui.tags.li(
                                "Dual Threshold Optimization (",
                                ui.a(
                                    "details here",
                                    href="#",
                                    target="_blank",
                                ),
                                ").",
                            ),
                        ),
                    ),
                    id="summary_binding_perturbation_accordion",
                    open=False,
                ),
                ui.br(),
                ui.card(
                    ui.card_header("Summarized Binding-Perturbation Comparison Table"),
                    ui.navset_tab(
                        ui.nav_panel(
                            "TFKO",
                            summarized_binding_perturbation_comparison_ui("tfko_table"),
                        ),
                        ui.nav_panel(
                            "Overexpression",
                            summarized_binding_perturbation_comparison_ui(
                                "overexpression_table"
                            ),
                        ),
                        id="expression_source_tabs",
                    ),
                    ui.card_footer(
                        ui.p(
                            ui.tags.b("Note: "),
                            "Rows corresponding to your replicate selection table "
                            "selection are automatically highlighted in aqua. "
                            "This table shows detailed metrics for the selected "
                            "expression source. "
                            "Switch between tabs to view different expression "
                            "conditions.",
                            style="margin: 0; font-size: 0.9em; color: #666;",
                        )
                    ),
                    style="min-height: 400px;",
                ),
            ),
        ),
    )


@module.server
def individual_regulator_compare_server(
    input: Inputs,
    output: Outputs,
    session: Session,
    *,
    rank_response_metadata: reactive.ExtendedTask,
    bindingmanualqc_result: reactive.ExtendedTask,
    logger: Logger,
) -> None:
    """
    This function produces the reactive/render functions necessary to producing the
    individual_regulator_compare module which inclues the rank response plots and
    associated QC tables.

    :param rank_response_metadata: This is the result from a reactive.extended_task.
        Result can be retrieved with .result()
    :param bindingmanualqc_result: This is the result from a reactive.extended_task.
        Result can be retrieved with .result()
    :param logger: A logger object

    """
    # This reactive stores the selected promotersetsigs from the replicate selection
    # table server. This needs to be a reactive.value at the top in order to be shared
    # across modules which must be coded before the replicate selection table server
    # is called.
    selected_promotersetsigs_reactive: reactive.value[set] = reactive.Value(set())

    # This reactive stores the columns selected from the side bar for
    # the summarized binding-perturbation comparison table
    selected_summarized_binding_perturbation_columns: reactive.value[list] = (
        reactive.Value(DEFAULT_SUMMARIZED_BINDING_PERTURBATION_COLUMNS)
    )

    # This reactive stores the database identifier columns selected from the side bar
    # for the summarized binding-perturbation comparison table
    selected_database_identifier_columns: reactive.value[list] = reactive.Value([])

    # This reactive stores the columns selected from the side bar for
    # the replicate selection table
    selected_replicate_selection_table_columns: reactive.value[list] = reactive.Value(
        DEFAULT_REPLICATE_SELECTION_TABLE_GENERAL_QC_COLUMNS
    )

    # This reactive stores the columns selected from the side bar for
    # the replicate selection table
    selected_replicate_selection_table_insert_columns: reactive.value[list] = (
        reactive.Value([])
    )

    @reactive.calc
    def selected_replicate_selection_table_columns_calc():
        return selected_replicate_selection_table_columns.get()

    @reactive.calc
    def selected_summarized_binding_perturbation_columns_calc():
        return selected_summarized_binding_perturbation_columns.get()

    @reactive.calc
    def selected_database_identifier_columns_calc():
        return selected_database_identifier_columns.get()

    @reactive.effect
    def _():
        """Update the regulator ui drop down selector based on the
        rank_response_metadata."""
        rank_response_metadata_local = rank_response_metadata.result()

        input_switch_value = input.symbol_locus_tag_switch.get()

        logger.info("switch: %s", input_switch_value)

        regulator_col = (
            "regulator_symbol" if not input_switch_value else "regulator_locus_tag"
        )

        logger.info("regulator_col: %s", regulator_col)

        regulator_dict = (
            rank_response_metadata_local[["regulator_id", regulator_col]]
            .drop_duplicates()
            .sort_values(by=regulator_col)
            .set_index("regulator_id")
            .to_dict(orient="dict")
        )

        logger.info("regulator_dict: %s", regulator_dict.keys())

        ui.update_select("regulator", choices=regulator_dict)

    rr_metadata = rank_response_replicate_plot_server(
        "rank_response_replicate_plot",
        selected_regulator=input.regulator,
        selected_promotersetsigs=selected_promotersetsigs_reactive,
        logger=logger,
    )

    @reactive.calc
    def has_column_changes():
        """Reactive to check if there are changes in column selection."""
        current_replicate_selection_general_qc_table_selection = set(
            input.replicate_selection_table_general_qc_columns.get() or []
        )
        current_replicate_selection_insert_table_selection = set(
            input.replicate_selection_table_insert_table_columns.get() or []
        )
        confirmed_replicate_selection_general_qc_table_selection = set(
            selected_replicate_selection_table_columns.get()
        )
        confirmed_replicate_selection_insert_table_selection = set(
            selected_replicate_selection_table_insert_columns.get()
        )
        current_summarized_binding_perturbation_selection = set(
            input.summarized_binding_perturbation_columns.get() or []
        )
        confirmed_summarized_binding_perturbation_selection = set(
            selected_summarized_binding_perturbation_columns.get()
        )
        current_database_identifier_selection = set(
            input.database_identifier_columns.get() or []
        )
        confirmed_database_identifier_selection = set(
            selected_database_identifier_columns.get()
        )

        return (
            current_summarized_binding_perturbation_selection
            != confirmed_summarized_binding_perturbation_selection
            or current_database_identifier_selection
            != confirmed_database_identifier_selection
            or current_replicate_selection_general_qc_table_selection
            != confirmed_replicate_selection_general_qc_table_selection
            or current_replicate_selection_insert_table_selection
            != confirmed_replicate_selection_insert_table_selection
        )

    @reactive.effect
    def _():
        """Update column choices for replicate selection table."""
        selected_general_qc = list(
            input.replicate_selection_table_general_qc_columns.get()
        )
        selected_insert = list(
            input.replicate_selection_table_insert_table_columns.get()
        )

        ui.update_checkbox_group(
            "replicate_selection_table_general_qc_columns",
            selected=selected_general_qc,
        )
        ui.update_checkbox_group(
            "replicate_selection_table_insert_table_columns",
            selected=selected_insert,
        )

    @reactive.effect
    def _():
        """Update column choices for summarized binding-perturbation comparison
        table."""
        selected = list(input.summarized_binding_perturbation_columns.get())
        selected_db_id = list(input.database_identifier_columns.get())

        ui.update_checkbox_group(
            "summarized_binding_perturbation_columns",
            selected=selected,
        )
        ui.update_checkbox_group(
            "database_identifier_columns",
            selected=selected_db_id,
        )

    # Update button appearance based on changes
    @reactive.effect
    def _():
        has_changes = has_column_changes()

        ui.update_action_button(
            "update_tables",
            label="Update Tables",
            disabled=not has_changes,
        )

    # Update the confirmed column selections when the button is clicked
    @reactive.effect
    @reactive.event(input.update_tables)
    def _():

        selected_summarized_binding_perturbation_columns_local = list(
            input.summarized_binding_perturbation_columns.get()
        )
        selected_summarized_binding_perturbation_columns.set(
            selected_summarized_binding_perturbation_columns_local
        )

        selected_database_identifier_columns_local = list(
            input.database_identifier_columns.get()
        )
        selected_database_identifier_columns.set(
            selected_database_identifier_columns_local
        )

        selected_replicate_selection_cols = list(
            input.replicate_selection_table_general_qc_columns.get()
        )
        selected_replicate_selection_cols.extend(
            list(input.replicate_selection_table_insert_table_columns.get())
        )
        selected_replicate_selection_table_columns.set(
            selected_replicate_selection_cols
        )

        logger.debug(
            "Updated summarized binding-perturbation comparison columns: %s",
            selected_summarized_binding_perturbation_columns_local,
        )
        logger.debug(
            "Updated database identifier columns: %s",
            selected_database_identifier_columns_local,
        )
        logger.debug(
            "Updated replicate selection table columns: %s",
            selected_replicate_selection_cols,
        )

    # Replicate selection table with selection capability
    selected_promotersetsigs = replicate_selection_table_server(
        "replicate_selection_table",
        rr_metadata=rr_metadata,
        bindingmanualqc_result=bindingmanualqc_result,
        selected_columns=selected_replicate_selection_table_columns_calc,
        logger=logger,
    )

    # Update the reactive value when replicate selection table selection changes
    @reactive.effect
    def _():
        selected_promotersetsigs_local = selected_promotersetsigs()
        selected_promotersetsigs_reactive.set(selected_promotersetsigs_local)
        logger.debug(
            "selected_promotersetsigs_reactive: %s", selected_promotersetsigs_reactive()
        )

    # Summarized binding-perturbation comparison tables
    summarized_binding_perturbation_comparison_server(
        "tfko_table",
        rr_metadata=rr_metadata,
        expression_source="kemmeren_tfko",
        selected_promotersetsigs=selected_promotersetsigs_reactive,
        selected_columns=selected_summarized_binding_perturbation_columns_calc,
        selected_database_identifier_columns=selected_database_identifier_columns_calc,
        logger=logger,
    )

    summarized_binding_perturbation_comparison_server(
        "overexpression_table",
        rr_metadata=rr_metadata,
        expression_source="mcisaac_oe",
        selected_promotersetsigs=selected_promotersetsigs_reactive,
        selected_columns=selected_summarized_binding_perturbation_columns_calc,
        selected_database_identifier_columns=selected_database_identifier_columns_calc,
        logger=logger,
    )

    # Synchronize plot tabs and expression source table tabs
    @reactive.effect
    def _():
        """Update expression source table tab when plot tab changes."""
        plot_tab = input.plot_tabs()
        if plot_tab:
            ui.update_navs("expression_source_tabs", selected=plot_tab)

    @reactive.effect
    def _():
        """Update plot tab when expression source table tab changes."""
        table_tab = input.expression_source_tabs()
        if table_tab:
            ui.update_navs("plot_tabs", selected=table_tab)

    # Render plots for different expression sources
    @render.ui
    def tfko_plots():
        # Return the plots filtered for TFKO expression source
        return rank_response_replicate_plot_tfko_ui("rank_response_replicate_plot")

    @render.ui
    def overexpression_plots():
        # Return the plots filtered for overexpression source
        return rank_response_replicate_plot_overexpression_ui(
            "rank_response_replicate_plot"
        )
