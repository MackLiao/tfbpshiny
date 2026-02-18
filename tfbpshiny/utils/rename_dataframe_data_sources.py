"""Rename internal source keys to human-readable display names in DataFrames."""

from __future__ import annotations

import pandas as pd

from .source_name_lookup import get_source_name_dict


def rename_dataframe_data_sources(df: pd.DataFrame) -> pd.DataFrame:
    """
    Replace internal source keys with display names in-place on a copy.

    Applies the binding and perturbation source name mappings to the
    ``binding_source`` and ``expression_source`` columns if present.

    """
    out = df.copy()
    all_names = get_source_name_dict()

    if "binding_source" in out.columns:
        out["binding_source"] = (
            out["binding_source"].map(all_names).fillna(out["binding_source"])
        )

    if "expression_source" in out.columns:
        out["expression_source"] = (
            out["expression_source"].map(all_names).fillna(out["expression_source"])
        )

    return out
