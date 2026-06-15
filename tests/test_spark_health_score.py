"""Tests for the Spark rolling-health-score job.

These spin up a tiny local Spark session, so they're skipped automatically if
PySpark/Java aren't available (e.g. minimal CI). When they run, they verify the
daily sub-score bounds/weights, the 30-day window mechanics, and that the
broadcast join + window appear in the physical plan.
"""

from __future__ import annotations

import datetime as dt
import os
import sys

import pytest

# Spark workers must use this interpreter (Windows has no `python3`).
os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)

pyspark = pytest.importorskip("pyspark")

from pyspark.sql import SparkSession  # noqa: E402

from batch.spark.rolling_health_score import compute, daily_subscore  # noqa: E402


@pytest.fixture(scope="module")
def spark():
    try:
        s = (
            SparkSession.builder.appName("test_health_score")
            .master("local[1]")
            .config("spark.sql.shuffle.partitions", "2")
            .config("spark.ui.enabled", "false")
            .getOrCreate()
        )
    except Exception as exc:  # Java missing / incompatible -> skip cleanly
        pytest.skip(f"Spark session unavailable: {exc}")
    # Probe a trivial action so a broken worker setup (e.g. no compatible Java /
    # no python3) skips these tests instead of failing them in minimal CI.
    try:
        s.createDataFrame([(1,)], ["x"]).count()
    except Exception as exc:
        s.stop()
        pytest.skip(f"Spark workers unavailable: {exc}")
    yield s
    s.stop()


def test_daily_subscore_bounds_and_perfect_day(spark):
    rows = [
        # perfect-ish day: 12k steps, 450 min sleep, low RHR -> high score
        (1, dt.date(2025, 1, 1), 12000, 450, 50.0),
        # poor day: few steps, little sleep, high RHR -> low score
        (1, dt.date(2025, 1, 2), 500, 200, 95.0),
    ]
    df = spark.createDataFrame(
        rows, ["user_id", "activity_date", "steps", "sleep_minutes", "resting_hr"]
    )
    out = {r["activity_date"].day: r["daily_score"] for r in daily_subscore(df).collect()}
    assert 0.0 <= out[2] <= out[1] <= 100.0
    assert out[1] > 80.0   # good day scores high
    assert out[2] < 40.0   # bad day scores low


def test_rolling_window_is_trailing_30d(spark):
    # 35 consecutive days for one user; the window count should cap at 30.
    base = dt.date(2025, 1, 1)
    rows = [
        (1, base + dt.timedelta(days=i), 8000, 450, 60.0) for i in range(35)
    ]
    activity = spark.createDataFrame(
        rows, ["user_id", "activity_date", "steps", "sleep_minutes", "resting_hr"]
    )
    users = spark.createDataFrame(
        [(1, "M", 40, "US")], ["user_id", "sex", "age", "country"]
    )
    # monkeypatch reads by calling compute's internals via temp parquet
    import os
    import tempfile  # noqa: E401

    d = tempfile.mkdtemp()
    activity.write.parquet(os.path.join(d, "daily_activity.parquet"))
    users.write.parquet(os.path.join(d, "dim_user.parquet"))

    res = compute(spark, d).orderBy("activity_date").collect()
    # first row: window has 1 day; day 30 onward: capped at 30
    assert res[0]["days_in_window"] == 1
    assert res[29]["days_in_window"] == 30
    assert res[34]["days_in_window"] == 30  # still 30, not 35


def test_plan_uses_broadcast_and_window(spark):
    import os
    import tempfile  # noqa: E401

    rows = [(1, dt.date(2025, 1, 1), 8000, 450, 60.0)]
    activity = spark.createDataFrame(
        rows, ["user_id", "activity_date", "steps", "sleep_minutes", "resting_hr"]
    )
    users = spark.createDataFrame([(1, "M", 40, "US")],
                                  ["user_id", "sex", "age", "country"])
    d = tempfile.mkdtemp()
    activity.write.parquet(os.path.join(d, "daily_activity.parquet"))
    users.write.parquet(os.path.join(d, "dim_user.parquet"))

    plan = compute(spark, d)._jdf.queryExecution().executedPlan().toString()
    assert "BroadcastHashJoin" in plan
    assert "Window" in plan
