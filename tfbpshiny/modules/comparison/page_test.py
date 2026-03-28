"""
Standalone app for developing the Comparison module in isolation.

Run with:
    poetry run shiny run tfbpshiny/modules/comparison/page_test.py

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

from tfbpshiny.modules.comparison.server import (
    comparison_sidebar_server,
    comparison_workspace_server,
)
from tfbpshiny.modules.comparison.ui import (
    comparison_sidebar_ui,
    comparison_workspace_ui,
)

logger = logging.getLogger("shiny")

# ---------------------------------------------------------------------------
# Mock data configuration
# ---------------------------------------------------------------------------

_RNG = np.random.default_rng(42)

_BINDING_DATASETS = ["callingcards", "harbison"]
_PERTURBATION_DATASETS = ["hackett", "kemmeren", "hu_reimand"]

# ---------------------------------------------------------------------------
# Mock DTO data
# ---------------------------------------------------------------------------

_DTO_ROWS: list[dict] = []
for _b_db in _BINDING_DATASETS:
    for _p_db in _PERTURBATION_DATASETS:
        _n = 40
        _pvals = _RNG.beta(0.5, 2, _n)
        for _i in range(_n):
            _DTO_ROWS.append(
                {
                    "binding_id_source": _b_db,
                    "perturbation_id_source": _p_db,
                    "dto_empirical_pvalue": float(_pvals[_i]),
                    "dto_fdr": float(min(_pvals[_i] * 1.5, 1.0)),
                    "binding_set_size": int(_RNG.integers(50, 500)),
                    "perturbation_set_size": int(_RNG.integers(200, 2000)),
                    "binding_sample_id": str(_i),
                    "pert_sample_id": str(_i),
                    "time": "standard",
                }
            )

_DTO_DF = pd.DataFrame(_DTO_ROWS)

# ---------------------------------------------------------------------------
# Mock top-N data
# ---------------------------------------------------------------------------

_TOP_N_ROWS: list[dict] = []
for _b_db in _BINDING_DATASETS:
    for _p_db in _PERTURBATION_DATASETS:
        _n_samples = 20
        _center = 0.35 if _b_db == "callingcards" else 0.20
        _ratios = np.clip(_RNG.normal(_center, 0.08, _n_samples), 0.0, 1.0)
        for _i in range(_n_samples):
            _TOP_N_ROWS.append(
                {
                    "binding_sample_id": str(_i),
                    "perturbation_sample_id": str(_i),
                    "n": 25,
                    "responsive_ratio": float(_ratios[_i]),
                    "_binding_db": _b_db,
                    "_perturbation_db": _p_db,
                }
            )

_TOP_N_DF = pd.DataFrame(_TOP_N_ROWS)


def _mock_vdb() -> MagicMock:
    vdb = MagicMock()
    vdb.get_datasets.return_value = _BINDING_DATASETS + _PERTURBATION_DATASETS

    def _query(sql: str, **params: Any) -> pd.DataFrame:
        sql_l = sql.lower()
        if "dto_expanded" in sql_l:
            return _DTO_DF.copy()
        # top-N query: find which binding/perturbation pair is referenced
        for b_db in _BINDING_DATASETS:
            if b_db in sql_l:
                for p_db in _PERTURBATION_DATASETS:
                    if p_db in sql_l:
                        sub = _TOP_N_DF[
                            (_TOP_N_DF["_binding_db"] == b_db)
                            & (_TOP_N_DF["_perturbation_db"] == p_db)
                        ][
                            [
                                "binding_sample_id",
                                "perturbation_sample_id",
                                "n",
                                "responsive_ratio",
                            ]
                        ]
                        return sub.copy()
        return pd.DataFrame()

    vdb.query.side_effect = _query
    vdb._conn.execute.return_value = None
    return vdb


vdb = _mock_vdb()

_active_binding: reactive.Value[list[str]] = reactive.value(_BINDING_DATASETS)
_active_perturbation: reactive.Value[list[str]] = reactive.value(_PERTURBATION_DATASETS)
_dataset_filters: reactive.Value[dict[str, Any]] = reactive.value({})

_CSS = (Path(__file__).parent.parent.parent / "app.css").resolve()

app_ui = ui.page_fillable(
    ui.include_css(_CSS),
    ui.div(
        {"class": "app-body", "style": "display:flex; height:100vh;"},
        comparison_sidebar_ui("comparison_sidebar"),
        comparison_workspace_ui("comparison_workspace"),
    ),
    padding=0,
    gap=0,
)


def server(input: Any, output: Any, session: Any) -> None:
    @reactive.calc
    def active_binding_datasets() -> list[str]:
        return _active_binding()

    @reactive.calc
    def active_perturbation_datasets() -> list[str]:
        return _active_perturbation()

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
        dataset_filters=_dataset_filters,
        top_n=top_n,
        effect_threshold=effect_threshold,
        pvalue_threshold=pvalue_threshold,
        facet_by=facet_by,
        vdb=vdb,
        logger=logger,
    )


app = App(ui=app_ui, server=server)
