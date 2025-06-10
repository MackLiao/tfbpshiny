from logging import Logger

from shiny import Inputs, Outputs, Session, module, reactive, render, req, ui

from ..utils.apply_column_names import apply_column_names
from ..utils.rename_dataframe_data_sources import rename_dataframe_data_sources

# Main table column metadata for selection
MAIN_TABLE_COLUMN_METADATA = {
    "binding_source": (
        "Binding Source",
        "Source of the binding data.",
    ),
    "genomic_inserts": (
        "Genomic Inserts",
        "Number of genomic inserts.",
    ),
    "mito_inserts": (
        "Mito Inserts",
        "Number of mitochondrial inserts.",
    ),
    "plasmid_inserts": (
        "Plasmid Inserts",
        "Number of plasmid inserts.",
    ),
    "rank_response_status": (
        "Rank Response Status",
        "Quality control status for rank response analysis.",
    ),
    "dto_status": (
        "DTO Status",
        "Quality control status for DTO analysis.",
    ),
}

# Convert to dictionary: {value: HTML label}
MAIN_TABLE_CHOICES_DICT = {
    key: ui.span(label, title=desc)
    for key, (label, desc) in MAIN_TABLE_COLUMN_METADATA.items()
}

# Default selection for main table columns
DEFAULT_MAIN_TABLE_COLUMNS = [
    "binding_source",
    "rank_response_status",
    "dto_status",
]


@module.ui
def main_table_ui():
    return ui.output_data_frame("main_table")


@module.server
def main_table_server(
    input: Inputs,
    output: Outputs,
    session: Session,
    *,
    rr_metadata: reactive.calc,
    bindingmanualqc_result: reactive.ExtendedTask,
    selected_columns: reactive.calc,
    logger: Logger,
) -> reactive.calc:
    """
    Main table server showing promotersetsig, binding_source, insert columns, and QC
    columns.

    :param rr_metadata: Complete rank response metadata
    :param bindingmanualqc_result: Binding manual QC data
    :param selected_columns: Reactive calc containing selected columns to display
    :param logger: Logger object
    :return: Reactive calc returning selected promotersetsigs

    """

    df_local_reactive: reactive.value = reactive.Value()

    @render.data_frame
    def main_table():
        req(rr_metadata)
        req(selected_columns)
        rr_df = rr_metadata().copy()  # type: ignore

        qc_df = bindingmanualqc_result.result()

        # Get unique combinations with insert columns
        main_df = rr_df[
            [
                "promotersetsig",
                "binding_source",
                "single_binding",
                "composite_binding",
                "genomic_inserts",
                "mito_inserts",
                "plasmid_inserts",
            ]
        ].drop_duplicates()

        # Merge with QC data
        if "rank_response_status" in qc_df.columns and "dto_status" in qc_df.columns:
            qc_subset = qc_df[
                [
                    "single_binding",
                    "composite_binding",
                    "rank_response_status",
                    "dto_status",
                ]
            ].drop_duplicates()
            main_df = main_df.merge(
                qc_subset, on=["single_binding", "composite_binding"], how="left"
            )

        # Get selected columns from the sidebar
        selected_cols = selected_columns()  # type: ignore

        # Always include promotersetsig (needed for selection logic)
        columns_to_show = ["promotersetsig"] + [
            col for col in selected_cols if col != "promotersetsig"
        ]

        # Filter to only show columns that exist in the dataframe and are selected
        available_columns = [col for col in columns_to_show if col in main_df.columns]

        if available_columns:
            main_df = main_df[available_columns]

        main_df = rename_dataframe_data_sources(main_df)

        # Apply friendly column names from metadata
        main_df = apply_column_names(main_df, MAIN_TABLE_COLUMN_METADATA)

        main_df.set_index("id", inplace=True)
        main_df.sort_index(ascending=True, inplace=True)
        main_df.reset_index(inplace=True)

        df_local_reactive.set(main_df)

        return render.DataGrid(
            main_df,
            selection_mode="rows",
        )

    @reactive.calc
    def get_selected_promotersetsigs():
        """A reactive calc that gets from the main table the selected rows, and returns
        the set of promotersetsigs corresponding to those rows."""
        req(df_local_reactive)
        selected_rows = main_table.cell_selection()["rows"]
        df_local = df_local_reactive.get()
        if not selected_rows or df_local.empty:
            return set()
        promotersetsig_col = "id"
        if promotersetsig_col in df_local.columns:
            return set(df_local.loc[list(selected_rows), promotersetsig_col])
        return set()

    return get_selected_promotersetsigs
