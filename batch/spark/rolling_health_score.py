"""Recompute every user's rolling 30-day health score over the FULL history.

This is the one genuinely heavy batch job in the repo: it reads the full daily
activity history (hundreds of thousands to millions of rows depending on params),
computes a per-user 30-day rolling score with a **window function**, joins the
small `dim_user` with a **broadcast join**, and writes partitioned parquet.

Why Spark here (not pandas/SQL)?
* The full history is large and the rolling computation is per-user over time —
  a windowed aggregation that distributes naturally.
* It lets us show the three things an interviewer probes: a window function, a
  broadcast (map-side) join, and deliberate repartitioning to control shuffles.

Design choices (see ADR-0008):
* **Repartition by `user_id`** before the window so each user's whole series is
  co-located on one partition — the rolling window then needs no shuffle per row.
* **Window**: 30-day trailing average of a daily sub-score, partitioned by user,
  ordered by date, framed by the preceding 29 days + current row.
* **Broadcast join** `dim_user` (tiny: one row per user) so the large fact isn't
  shuffled to join it.

Run (Spark local mode):
    python -m batch.spark.rolling_health_score --source data/raw --out data/processed/health_score

EMR/Dataproc note: the same script runs on a cluster unchanged — submit with
`spark-submit` and point --source/--out at GCS/S3. Not required for the demo.
"""

from __future__ import annotations

import argparse
import os
import sys

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window


def build_spark(app_name: str = "rolling_health_score") -> SparkSession:
    # Make Spark's Python workers use THIS interpreter (avoids "python3 not found"
    # on Windows and venv mismatches), unless the caller already set it.
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)
    return (
        SparkSession.builder.appName(app_name)
        .master("local[*]")
        # modest shuffle partitions for a single machine; tune for a cluster
        .config("spark.sql.shuffle.partitions", "16")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )


def daily_subscore(df):
    """A 0-100 daily wellness sub-score from steps, sleep, and resting HR.

    Transparent and bounded: each component is clipped to [0, 1] then weighted.
    * steps   : ramps to full credit at 10k steps
    * sleep   : full credit around 7.5h (450 min), penalised away from it
    * resting : lower is better; full credit <= 55 bpm, zero by 90 bpm
    """
    steps_score = F.least(F.lit(1.0), F.col("steps") / F.lit(10000.0))
    sleep_score = F.greatest(
        F.lit(0.0), F.lit(1.0) - F.abs(F.col("sleep_minutes") - F.lit(450)) / F.lit(450.0)
    )
    rhr_score = F.greatest(
        F.lit(0.0),
        F.least(F.lit(1.0), (F.lit(90.0) - F.col("resting_hr")) / F.lit(35.0)),
    )
    score = (steps_score * 0.4 + sleep_score * 0.3 + rhr_score * 0.3) * 100.0
    return df.withColumn("daily_score", F.round(score, 2))


def compute(spark: SparkSession, source: str):
    activity = spark.read.parquet(f"{source}/daily_activity.parquet")
    users = spark.read.parquet(f"{source}/dim_user.parquet")

    activity = daily_subscore(activity)

    # Co-locate each user's full series on one partition so the per-user time
    # window needs no further shuffle. Deliberate repartition by the window key.
    activity = activity.repartition("user_id")

    # 30-day trailing window: this row + the previous 29 days, per user, by date.
    # rowsBetween(-29, 0) assumes one row per day (true for daily_activity).
    w = (
        Window.partitionBy("user_id")
        .orderBy("activity_date")
        .rowsBetween(-29, 0)
    )
    scored = activity.withColumn(
        "rolling_30d_score", F.round(F.avg("daily_score").over(w), 2)
    ).withColumn("days_in_window", F.count("daily_score").over(w))

    # Broadcast the tiny user dimension to avoid shuffling the large fact.
    enriched = scored.join(
        F.broadcast(users.select("user_id", "sex", "age", "country")),
        on="user_id",
        how="left",
    )

    return enriched.select(
        "user_id",
        "activity_date",
        "sex",
        "age",
        "country",
        "daily_score",
        "rolling_30d_score",
        "days_in_window",
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Rolling 30-day health score (Spark).")
    ap.add_argument("--source", default="data/raw", help="dir with *.parquet")
    ap.add_argument("--out", default="data/processed/health_score", help="output parquet dir")
    ap.add_argument("--show", action="store_true", help="print a small sample instead of writing")
    args = ap.parse_args()

    spark = build_spark()
    spark.sparkContext.setLogLevel("WARN")
    try:
        result = compute(spark, args.source)
        if args.show:
            print(f"rows: {result.count():,}")
            result.orderBy("user_id", "activity_date").show(15, truncate=False)
        else:
            # Partition output by date for downstream pruning; one write of the
            # full result set.
            (
                result.withColumn("year", F.year("activity_date"))
                .write.mode("overwrite")
                .partitionBy("year")
                .parquet(args.out)
            )
            print(f"wrote rolling health score to {args.out}")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
