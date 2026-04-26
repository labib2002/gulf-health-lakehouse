# dbt transform layer (Postgres)

Star schema over the synthetic health data. See [ADR-0004](../../docs/adr/0004-dbt.md).

## Layout

```
models/
  staging/        views   — one per raw source, light cleaning
  intermediate/   ephemeral — reusable building blocks
  marts/          tables  — dim_user, dim_device, fct_daily_activity (incremental),
                            fct_body_scan, fct_nutrition
seeds/  dim_date.csv      — conformed date dimension
macros/ test_positive.sql — custom generic test
tests/  *.sql             — singular tests
```

## Run it

Prereqs: the compose Postgres is up and raw data is loaded
(`make up` then `make load`, or load from host on port 5433).

```bash
cd transform/dbt
export DBT_PROFILES_DIR="$PWD" POSTGRES_HOST=localhost   # host port 5433 by default
../../.venv/Scripts/dbt deps     # first time: install dbt_utils
dbt build                        # run models + tests
dbt docs generate && dbt docs serve   # lineage graph
```

Latest run: **14 models, 1 seed, 59 data tests — PASS=72**.

## Notes

- `fct_daily_activity` is incremental on `activity_date`
  (`unique_key=(user_id, date_key)`, `delete+insert`). A normal re-run inserts 0
  rows; `dbt build --full-refresh` rebuilds.
- Profiles are env-var driven and secret-free. A `bigquery` output is stubbed for
  Phase 5.
