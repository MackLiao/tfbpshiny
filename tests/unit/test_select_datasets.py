"""Unit tests for select_datasets pure helper functions."""

from tfbpshiny.modules.select_datasets.queries import (
    _build_where,
    full_data_query,
    metadata_query,
    regulator_breakdown_query,
    regulator_display_labels_query,
    regulator_locus_tags_query,
    sample_count_query,
)
from tfbpshiny.modules.select_datasets.server.sidebar import _filter_btn_id, _toggle_id

# --- ID generators ---


def test_toggle_id_is_stable():
    assert _toggle_id("harbison") == _toggle_id("harbison")


def test_toggle_id_differs_by_dataset():
    assert _toggle_id("harbison") != _toggle_id("hackett")


def test_filter_btn_id_is_stable():
    assert _filter_btn_id("harbison") == _filter_btn_id("harbison")


# --- _build_where ---


def test_build_where_no_filters():
    params: dict = {}
    assert _build_where(None, params) == ""
    assert params == {}


def test_build_where_categorical():
    params: dict = {}
    where = _build_where(
        {"strain": {"type": "categorical", "value": ["BY4741"]}}, params
    )
    assert '"strain" IN' in where
    assert "BY4741" in params.values()


def test_build_where_numeric():
    params: dict = {}
    where = _build_where({"time": {"type": "numeric", "value": [0.0, 30.0]}}, params)
    assert "BETWEEN" in where
    assert params["num_time_lo"] == 0.0
    assert params["num_time_hi"] == 30.0


def test_build_where_bool():
    params: dict = {}
    where = _build_where({"is_wt": {"type": "bool", "value": True}}, params)
    assert "is_wt" in where
    assert params["bool_is_wt"] is True


# --- query builders ---


def test_metadata_query_no_filters():
    sql, params = metadata_query("harbison")
    assert sql == "SELECT * FROM harbison_meta"
    assert params == {}


def test_metadata_query_with_filter():
    sql, params = metadata_query(
        "harbison", {"strain": {"type": "categorical", "value": ["BY4741"]}}
    )
    assert "WHERE" in sql
    assert "BY4741" in params.values()


def test_sample_count_query():
    sql, params = sample_count_query("harbison")
    assert "COUNT(sample_id)" in sql
    assert params == {}


def test_sample_count_query_with_regulators():
    sql, params = sample_count_query("harbison", restrict_to_regulators=["YAL001C"])
    assert "regulator_locus_tag IN" in sql
    assert "YAL001C" in params.values()


def test_regulator_locus_tags_query():
    sql, params = regulator_locus_tags_query("harbison")
    assert "DISTINCT regulator_locus_tag" in sql
    assert params == {}


def test_regulator_display_labels_query():
    sql, params = regulator_display_labels_query("harbison")
    assert "regulator_locus_tag" in sql
    assert "regulator_symbol" in sql
    assert "harbison_meta" in sql
    assert params == {}


# --- regulator_breakdown_query ---


def test_regulator_breakdown_query_no_filters_no_cols():
    sql, params = regulator_breakdown_query("harbison", [])
    assert "n_multi" in sql
    assert "harbison_meta" in sql
    assert "HAVING COUNT(*) > 1" in sql
    assert params == {}


def test_regulator_breakdown_query_candidate_cols_in_select():
    sql, params = regulator_breakdown_query(
        "harbison", ["Carbon source", "Temperature"]
    )
    assert 'COUNT(DISTINCT "Carbon source")' in sql
    assert 'COUNT(DISTINCT "Temperature")' in sql
    assert params == {}


def test_regulator_breakdown_query_with_filters():
    sql, params = regulator_breakdown_query(
        "harbison",
        ["Carbon source"],
        {"strain": {"type": "categorical", "value": ["BY4741"]}},
    )
    assert "BY4741" in params.values()
    assert 'COUNT(DISTINCT "Carbon source")' in sql
    # filters produce WHERE; the regulator IN clause must use AND, not a second WHERE
    assert "AND regulator_locus_tag IN" in sql
    assert sql.count("WHERE") == 3  # filters appear in both multi and per_reg CTEs


def test_full_data_query_no_filters():
    sql, params = full_data_query("harbison")
    assert sql == "SELECT * FROM harbison"
    assert params == {}


def test_full_data_query_with_filter():
    sql, params = full_data_query(
        "harbison", {"strain": {"type": "categorical", "value": ["BY4741"]}}
    )
    assert "WHERE" in sql
    assert "harbison" in sql
    assert "harbison_meta" not in sql
    assert "BY4741" in params.values()


def test_regulator_breakdown_query_no_filters_uses_where():
    sql, params = regulator_breakdown_query("harbison", ["Carbon source"])
    # no filters — regulator IN clause must open with WHERE, not AND
    assert "WHERE regulator_locus_tag IN" in sql
