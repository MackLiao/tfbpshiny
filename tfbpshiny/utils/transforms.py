"""Statistical transformations for analysis data."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger("shiny")


def neglog10_with_pseudocount(series: pd.Series) -> pd.Series:
    """
    Transform p-values to -log10 scale using min non-zero value as pseudocount.

    Zeros are replaced with the smallest non-zero value in the series before applying
    -log10.  NA/NaN values are preserved.

    :param series: Numeric series of p-values (>= 0).
    :returns: Transformed series on -log10 scale.
    :raises ValueError: If all non-NA values are zero (no valid pseudocount).

    """
    non_na = series.dropna()
    if non_na.empty:
        return series.copy()

    positive = non_na[non_na > 0]
    if positive.empty:
        raise ValueError(
            "All p-values are zero; cannot compute pseudocount "
            "for -log10 transformation."
        )

    pseudocount = float(positive.min())
    clamped = series.clip(lower=pseudocount)

    result = -np.log10(clamped)
    # Restore original NA positions.
    result[series.isna()] = pd.NA

    return result
