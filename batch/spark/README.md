# PySpark batch (Phase 7)

One heavy batch job: recompute every user's **rolling 30-day health score** over
the **full** synthetic history. See [ADR-0008](../../docs/adr/0008-pyspark.md).

## What it does

1. Reads `daily_activity.parquet` (full history — 270k rows at default params).
2. Computes a transparent 0–100 daily sub-score (steps / sleep / resting HR).
3. **Repartitions by `user_id`**, then a **window function** computes the trailing
   30-day average per user.
4. **Broadcast-joins** the tiny `dim_user`.
5. Writes date-partitioned parquet to `data/processed/health_score/`.

## Run it (Spark local mode)

Spark 3.5 needs **Java 8/11/17** (NOT Java 21+). On Windows, writing parquet also
needs Hadoop `winutils.exe` + `hadoop.dll`.

```bash
export JAVA_HOME=/path/to/jdk-17          # Java 17 (Temurin works)
export HADOOP_HOME=/c/hadoop              # contains bin/winutils.exe + hadoop.dll (Windows only)

python -m batch.spark.rolling_health_score --source data/raw --out data/processed/health_score
python -m batch.spark.rolling_health_score --source data/raw/sample --show   # quick peek
```

Verified locally: processed **270,000 rows** and wrote partitioned parquet
(`year=2024/`, `year=2025/`, `_SUCCESS`). The physical plan contains
`BroadcastHashJoin` and `Window` (checked in the tests).

## Cluster note (not required)

The same script runs unchanged on EMR/Dataproc: `spark-submit
rolling_health_score.py --source gs://.../raw --out gs://.../health_score`. Only
the master and paths change; the logic is cluster-ready.
