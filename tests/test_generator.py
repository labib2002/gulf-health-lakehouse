"""Generator tests: schema, row counts, value ranges, determinism, correlations."""

from __future__ import annotations

import numpy as np
import pandas as pd

from data_generator.generate import generate

EXPECTED_TABLES = {
    "dim_device",
    "dim_user",
    "user_attr_history",
    "daily_activity",
    "intraday_hr",
    "body_scan",
    "nutrition_log",
    "experiment_assignment",
}


def test_all_tables_present(tables):
    assert set(tables) == EXPECTED_TABLES
    for name, df in tables.items():
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0, f"{name} is empty"


def test_row_counts(tables, small_cfg):
    n_users = small_cfg["users"]
    n_days = small_cfg["history_months"] * 30
    assert len(tables["dim_user"]) == n_users
    assert len(tables["dim_device"]) == len(small_cfg["devices"])
    # one daily row per user/day
    assert len(tables["daily_activity"]) == n_users * n_days
    # 24 intraday rows per daily row
    assert len(tables["intraday_hr"]) == n_users * n_days * 24
    # experiment: one row per user
    assert len(tables["experiment_assignment"]) == n_users


def test_schema_columns(tables):
    assert {"user_id", "activity_date", "steps", "resting_hr", "calories"} <= set(
        tables["daily_activity"].columns
    )
    assert {"user_id", "scan_date", "weight_kg", "body_fat_pct"} <= set(
        tables["body_scan"].columns
    )
    assert {"user_id", "variant", "engaged_next_day"} <= set(
        tables["experiment_assignment"].columns
    )


def test_value_ranges(tables):
    da = tables["daily_activity"]
    assert da["steps"].between(0, 35000).all()
    assert da["resting_hr"].between(38, 100).all()
    assert da["active_minutes"].ge(0).all()
    assert (da["sleep_deep_minutes"] + da["sleep_rem_minutes"]
            + da["sleep_light_minutes"] <= da["sleep_minutes"] + 1).all()

    hr = tables["intraday_hr"]
    assert hr["heart_rate"].between(35, 200).all()
    assert hr["hour"].between(0, 23).all()

    bs = tables["body_scan"]
    assert bs["body_fat_pct"].between(5, 55).all()
    assert bs["weight_kg"].between(40, 200).all()

    exp = tables["experiment_assignment"]
    assert set(exp["variant"].unique()) <= {"A", "B"}
    assert set(exp["engaged_next_day"].unique()) <= {0, 1}


def test_no_nulls_in_keys(tables):
    for name, df in tables.items():
        if "user_id" in df.columns:
            assert df["user_id"].notna().all(), f"null user_id in {name}"


def test_determinism_same_seed(small_cfg):
    """Same seed -> byte-identical tables."""
    a = generate(small_cfg)
    b = generate(small_cfg)
    for name in a:
        pd.testing.assert_frame_equal(
            a[name].reset_index(drop=True), b[name].reset_index(drop=True)
        )


def test_different_seed_changes_data(small_cfg):
    other = dict(small_cfg)
    other["seed"] = small_cfg["seed"] + 1
    a = generate(small_cfg)
    b = generate(other)
    # daily activity should differ under a different seed
    assert not a["daily_activity"]["steps"].equals(b["daily_activity"]["steps"])


def test_steps_calories_correlation(tables):
    """Realism check: steps and calories should be positively correlated."""
    da = tables["daily_activity"]
    corr = np.corrcoef(da["steps"], da["calories"])[0, 1]
    assert corr > 0.2, f"weak steps↔calories correlation: {corr:.2f}"


def test_scd_history_is_effective_dated(tables):
    h = tables["user_attr_history"]
    assert {"user_id", "membership_tier", "company", "effective_from"} <= set(h.columns)
    # each user starts with at least one span
    assert h.groupby("user_id").size().min() >= 1
    # spans are ordered per user
    for _, g in h.groupby("user_id"):
        eff = g["effective_from"].tolist()
        assert eff == sorted(eff)
