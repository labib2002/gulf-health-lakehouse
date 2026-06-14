# ADR 0008 — Heavy batch with PySpark

- **Status:** Accepted
- **Phase:** 7 — PySpark
- **Date:** 2026-06-14

## Context

We need one genuinely heavy, justified batch job (not a framework): recompute
every user's **rolling 30-day health score** across the **full** synthetic
history (hundreds of thousands → millions of rows). It must demonstrate a window
function, a broadcast join, and deliberate repartitioning, and actually run to
completion writing output.

## Decision

`batch/spark/rolling_health_score.py`, Spark **local mode**:

1. **Daily sub-score** — a transparent, bounded 0–100 score from steps (40%),
   sleep (30%), resting HR (30%); each component clipped to [0, 1].
2. **Repartition by `user_id`** before the window so each user's full time series
   is co-located on one partition — the per-user rolling window then needs no
   per-row shuffle. This is the deliberate repartition.
3. **Window function** — `avg(daily_score)` over
   `partitionBy(user_id).orderBy(activity_date).rowsBetween(-29, 0)`: the trailing
   30-day mean (this row + previous 29 days). `days_in_window` shows it filling up
   then capping at 30.
4. **Broadcast join** — `F.broadcast(dim_user)`; the user dimension is tiny (one
   row per user), so broadcasting it avoids shuffling the large fact to join.
5. **Write** date-partitioned parquet (`partitionBy(year)`).

Verified: processed **270,000 rows** and wrote `year=2024/`, `year=2025/`,
`_SUCCESS`. The executed plan contains `BroadcastHashJoin` and `Window`
(asserted in `tests/test_spark_health_score.py`).

## Environment notes (honest)

- Spark 3.5 is **incompatible with Java 21+** (`getSubject is not supported`);
  it needs Java 8/11/17. We run on **Temurin JDK 17**.
- On Windows, *writing* parquet needs Hadoop `winutils.exe` + `hadoop.dll`
  (`HADOOP_HOME`). Reading/`--show` works without them.
- `build_spark` sets `PYSPARK_PYTHON` to the current interpreter so workers launch
  (Windows has no `python3`).
These are documented in the batch README rather than hidden.

## Alternatives considered

- **pandas / SQL window** — works at 270k rows, but the brief is to justify Spark;
  the per-user windowed computation over the full (millions-at-larger-params)
  history is the distributable workload Spark is for. The code is also
  cluster-ready unchanged.
- **Sort-merge join for dim_user** — wasteful; the dimension is small enough to
  broadcast, turning a shuffle join into a map-side join.
- **No explicit repartition** — Spark would still shuffle for the window, but
  partitioning by the window key up front makes the data movement explicit and
  keeps each user's series together.

## Consequences

- A real heavy job that completes and writes partitioned output.
- The three probed concepts (window, broadcast, repartition) are present in the
  physical plan, not just claimed.

## Interview check

**What is a shuffle, and what triggers it?**
A shuffle is the redistribution of data across partitions (and usually across the
network/executors) so that rows sharing a key end up together. It's the expensive
part of distributed processing (disk + network + serialization). It's triggered by
wide transformations: `groupBy`/aggregations, joins (non-broadcast), `repartition`,
`distinct`, and window functions that partition by a key. Here, `repartition
("user_id")` and the windowed average cause the shuffle; the broadcast join
deliberately avoids one.

**Broadcast join vs sort-merge join?**
A **broadcast (map-side) join** ships a small table to every executor so the large
table is joined locally with no shuffle of the big side — great when one side fits
in memory (our `dim_user`). A **sort-merge join** shuffles *both* sides on the join
key, sorts, and merges — the default for two large tables, but it pays a full
shuffle. We force broadcast because the dimension is tiny.

**Why is the job partitioned the way it is?**
We repartition by `user_id` because every downstream operation (the rolling window)
is *per user*. Co-locating each user's whole series on one partition means the
window is computed without moving rows between partitions again, and the broadcast
join needs no shuffle either — so the only data movement is the one intentional
repartition. Output is partitioned by `year` for downstream read pruning.
