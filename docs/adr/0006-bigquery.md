# ADR 0006 — BigQuery warehouse (partitioning, clustering, SCD2)

- **Status:** Accepted (built offline, pending credentials)
- **Phase:** 5 — BigQuery
- **Date:** 2026-05-23

## Context

The marts should also run on a cloud columnar warehouse (BigQuery), modeling a
proper **star schema** with **date partitioning** and **clustering on user_id**
on the facts, plus an **SCD Type 2** user dimension. We have no live BigQuery
credentials yet (and the provided `BQ_PROJECT_ID` looks truncated), so this is
built and validated **offline** with a single clearly-marked credential TODO.

## Decision

- **One dbt project, two targets.** A `bigquery` output is added to
  `profiles.yml` (service-account auth, env-driven). The fact models apply
  BigQuery physical design **conditionally** — `partition_by` / `cluster_by` /
  `insert_overwrite` are set only `if target.type == 'bigquery'`, otherwise
  `none`. So the Postgres build is completely unaffected (still PASS), and the
  same code produces a partitioned/clustered star schema on BigQuery.
- **Partitioning + clustering** (verified in `target/manifest.json`):
  - `fct_daily_activity`: partition by `activity_date` (day), cluster `user_id`,
    `insert_overwrite` incremental (partition-replace — the right BQ strategy).
  - `fct_body_scan`: partition by `scan_date` (month — scans are sparse), cluster
    `user_id`.
  - `fct_nutrition`: partition by `log_date` (day), cluster `user_id`.
- **SCD2, two ways:**
  - `dim_user_scd2` (model): *derives* Type-2 versions
    (`valid_from`/`valid_to`/`is_current` + surrogate key) from the
    effective-dated `user_attr_history` source.
  - `snapshots/scd2_user_attrs.sql`: dbt's **built-in snapshot** (check strategy)
    that *captures* history over time when the source only carries the current
    value.
- **Weight history stays on `fct_body_scan`**, not in the SCD2 dimension —
  measured fast-changing values are facts, not slowly-changing attributes.
- **`warehouse/load_to_bigquery.py`**: the real raw-load sibling of the Postgres
  loader, ready to run once creds exist.

## Offline validation performed

- `dbt parse --target bigquery` → success (entire project compiles on the BQ
  adapter, including SCD2 and the conditional configs).
- Partition/cluster config confirmed in the manifest for all three facts.
- `dbt build` on Postgres → **PASS=82** (BQ configs no-op there; SCD2 model +
  its "exactly one current row per user" singular test pass).

## The credential boundary (single TODO)

`warehouse/README.md` and `load_to_bigquery.py` carry the only blocker:
`BQ_PROJECT_ID` + a service-account JSON. Re-verify the project id (looks
truncated). Everything else is ready: `dbt build --target bigquery` will create
the partitioned/clustered star schema and the SCD2 dimension as-is.

## Alternatives considered

- **A second, BigQuery-only copy of the models** — rejected; conditional config
  keeps one source of truth and avoids drift between targets.
- **Partition by ingestion time** — rejected; partitioning by the event date
  (`activity_date` etc.) matches how analysts filter (by day/range) and prunes
  scanned bytes.
- **SCD2 via snapshot only** — kept *both* to show the derive-from-history and
  capture-over-time approaches; the model is the source-driven one, the snapshot
  is the change-data-capture one.
- **Type 1 (overwrite) dim_user** — that's the Postgres `dim_user` (current
  state). BigQuery gets the Type-2 history because point-in-time correctness is
  the explicit deliverable here.

## Interview check

**Why partition on date?**
BigQuery bills by bytes scanned. Date partitioning lets a query that filters on a
date range read only the relevant partitions instead of the whole table —
cheaper and faster. Our facts are almost always sliced by date, so the event date
is the natural partition key (with `user_id` clustering to co-locate a user's
rows within each partition for further pruning).

**Fact vs dimension — and where does a user's weight history live, and why?**
Dimensions hold descriptive, slowly-changing context (who the user is, their tier
/ company); facts hold measured events at a grain. Weight is **measured and
changes constantly**, so each measurement is a **fact event in `fct_body_scan`**
(user/scan-date grain). Putting it in the dimension would either lose history or
explode the dimension with versions for a value that isn't a descriptive
attribute.

**What is an SCD, and which type did we use?**
A Slowly Changing Dimension handles attributes that change over time. **Type 1**
overwrites (no history). **Type 2** keeps a new versioned row per change with
validity dates + a current flag (full history). We use **Type 2** for membership
tier / company in `dim_user_scd2` (and a dbt snapshot), so a fact can be joined to
the dimension version that was current as of the fact's date for correct
point-in-time reporting.
