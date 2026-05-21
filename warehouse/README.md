# BigQuery warehouse (Phase 5)

The same dbt project targets **BigQuery** as a star schema with date
**partitioning** and **clustering on `user_id`**, plus an **SCD Type 2** user
dimension. See [ADR-0006](../docs/adr/0006-bigquery.md).

> **Built offline.** Everything here is real dbt that compiles against the
> BigQuery adapter (`dbt parse --target bigquery` passes; the partition/cluster
> config is verified in `target/manifest.json`). The only thing missing is live
> credentials — see the single TODO below. The provided `BQ_PROJECT_ID` also
> looks truncated and should be re-checked.

## What targets BigQuery

The `bigquery` output in `transform/dbt/profiles.yml` (service-account auth).
The fact models apply BigQuery physical design **only when
`target.type == 'bigquery'`**, so the Postgres build is unaffected:

| Model               | Partition (BigQuery)        | Cluster   | Incremental         |
|---------------------|-----------------------------|-----------|---------------------|
| `fct_daily_activity`| `activity_date` (day)       | `user_id` | `insert_overwrite`  |
| `fct_body_scan`     | `scan_date` (month)         | `user_id` | table               |
| `fct_nutrition`     | `log_date` (day)            | `user_id` | table               |

SCD2:
- `dim_user_scd2` — derives Type-2 versions (valid_from / valid_to / is_current,
  surrogate key) from the effective-dated `user_attr_history` source.
- `snapshots/scd2_user_attrs.sql` — dbt's built-in snapshot SCD2 (check strategy)
  for when only the *current* value is available and history must be captured
  over time.

A user's **weight history stays on `fct_body_scan`** (measured, fast-changing
fact events), not in the SCD2 dimension (slowly-changing descriptive attributes).

## Run it against BigQuery (once credentials exist)

```bash
# >>> TODO(credentials): set these to a REAL project + service account. <<<
export BQ_PROJECT_ID=...                 # the provided id looks truncated — verify
export BQ_DATASET=health_lakehouse
export GOOGLE_APPLICATION_CREDENTIALS=/abs/path/to/service-account.json
export BQ_LOCATION=US

cd transform/dbt
dbt deps
dbt build  --target bigquery             # creates the partitioned/clustered star schema
dbt snapshot --target bigquery
dbt docs generate --target bigquery
```

### One-time BigQuery setup

1. Create a GCP project (or use the free **sandbox** — no billing, 10 GB storage
   / 1 TB query/month).
2. Create dataset `health_lakehouse` (location `US`).
3. Create a service account with **BigQuery Data Editor** + **BigQuery Job User**,
   download its JSON key, and point `GOOGLE_APPLICATION_CREDENTIALS` at it.
4. Land raw data in BigQuery (load the parquet via `bq load` or the Python client)
   into a `raw` dataset/schema, then run dbt as above.

## Offline verification done here

- `dbt parse --target bigquery` → success (whole project compiles on the BQ adapter).
- Partition/cluster config confirmed in `target/manifest.json`.
- `dbt build` on Postgres → **PASS=82** (BQ configs are no-ops there, so dual-target works).
