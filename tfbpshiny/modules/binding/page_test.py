"""
Standalone app for developing the Binding analysis page in isolation.

Run with:
    poetry run shiny run tfbpshiny/modules/binding/page_test.py

Uses mock data so no real VirtualDB connection is required.

"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
from shiny import App, reactive, ui

from tfbpshiny.modules.binding.server import (
    binding_sidebar_server,
    binding_workspace_server,
)
from tfbpshiny.modules.binding.ui import binding_sidebar_ui, binding_workspace_ui

logger = logging.getLogger("shiny")

# ---------------------------------------------------------------------------
# Mock data: 3 datasets, all sharing the column "effect"
# ---------------------------------------------------------------------------
_RNG = np.random.default_rng(42)

_REGULATORS = [f"YJR{i:03d}W" for i in range(1, 21)]
_TARGETS = [f"YAL{i:03d}C" for i in range(1, 101)]

_MOCK_TAGS = {
    "dataset_a": {"data_type": "binding", "display_name": "Mock Dataset A"},
    "dataset_b": {"data_type": "binding", "display_name": "Mock Dataset B"},
    "dataset_c": {"data_type": "binding", "display_name": "Mock Dataset C"},
}

_DATASETS = list(_MOCK_TAGS.keys())


def _make_binding_df(noise: float = 0.0) -> pd.DataFrame:
    """Create a mock binding DataFrame with shared 'effect' and 'pvalue' columns."""
    n = len(_REGULATORS) * len(_TARGETS)
    base = _RNG.standard_normal(n)
    rows = []
    for i, reg in enumerate(_REGULATORS):
        for j, tgt in enumerate(_TARGETS):
            idx = i * len(_TARGETS) + j
            effect = float(base[idx] + noise * _RNG.standard_normal())
            pvalue = float(np.clip(_RNG.uniform(0, 1) + noise * 0.1, 0.0, 1.0))
            rows.append(
                {
                    "regulator_locus_tag": reg,
                    "target_locus_tag": tgt,
                    "effect": effect,
                    "pvalue": pvalue,
                }
            )
    return pd.DataFrame(rows)


_DATA: dict[str, pd.DataFrame] = {
    "dataset_a": _make_binding_df(noise=0.1),
    "dataset_b": _make_binding_df(noise=0.5),
    "dataset_c": _make_binding_df(noise=1.0),
}

_META: dict[str, pd.DataFrame] = {
    db: pd.DataFrame(
        {
            "regulator_locus_tag": _REGULATORS,
            "regulator_symbol": _REGULATORS,
            "sample_id": range(len(_REGULATORS)),
        }
    )
    for db in _DATASETS
}


def _mock_vdb() -> MagicMock:
    vdb = MagicMock()
    vdb.get_datasets.return_value = _DATASETS
    vdb.get_tags.side_effect = lambda db: _MOCK_TAGS.get(db, {})

    def _describe(table: str) -> pd.DataFrame:
        base = table.replace("_meta", "")
        df = _DATA.get(base) if base in _DATA else _META.get(base)
        if df is None:
            return pd.DataFrame(columns=["column_name", "column_type"])
        rows = []
        for col in df.columns:
            col_type = "DOUBLE" if df[col].dtype == float else "VARCHAR"
            rows.append({"column_name": col, "column_type": col_type})
        return pd.DataFrame(rows)

    vdb.describe.side_effect = _describe

    def _query(sql: str, **params: Any) -> pd.DataFrame:
        sql_l = sql.lower()
        for db in _DATASETS:
            if db + "_meta" in sql_l:
                return _META[db].copy()
            if db in sql_l:
                df = _DATA[db].copy()
                reg = params.get("reg")
                if reg:
                    df = df[df["regulator_locus_tag"] == reg]
                return df
        return pd.DataFrame()

    vdb.query.side_effect = _query
    return vdb


vdb = _mock_vdb()

_active_binding: reactive.Value[list[str]] = reactive.value(_DATASETS)
_dataset_filters: reactive.Value[dict[str, Any]] = reactive.value({})

_CSS = (Path(__file__).parent.parent.parent / "app.css").resolve()

app_ui = ui.page_fillable(
    ui.include_css(_CSS),
    ui.div(
        {"class": "app-body", "style": "display:flex; height:100vh;"},
        binding_sidebar_ui("binding_sidebar"),
        binding_workspace_ui("binding_workspace"),
    ),
    padding=0,
    gap=0,
)


def server(input: Any, output: Any, session: Any) -> None:
    @reactive.calc
    def active_binding_datasets() -> list[str]:
        return _active_binding()

    corr_type, col_preference = binding_sidebar_server(
        "binding_sidebar",
        active_binding_datasets=active_binding_datasets,
        dataset_filters=_dataset_filters,
        vdb=vdb,
        logger=logger,
    )

    binding_workspace_server(
        "binding_workspace",
        active_binding_datasets=active_binding_datasets,
        corr_type=corr_type,
        col_preference=col_preference,
        dataset_filters=_dataset_filters,
        vdb=vdb,
        logger=logger,
    )


app = App(ui=app_ui, server=server)
