# ADR 0005 — Orchestration with Airflow

- **Status:** Accepted
- **Phase:** 4 — Airflow
- **Date:** 2026-05-09

## Context

The pipeline (generate → load → dbt build → dbt test) needs orchestration:
scheduling, retries, alerting, backfill, and SLAs — runnable locally in Docker
and composable with the base stack.

## Decision

- **Airflow 2.9 (LocalExecutor) in Docker**
  (`orchestration/airflow/docker-compose.airflow.yml`). It keeps its **own**
  metadata Postgres (`airflow-db`) — orchestration state is separate from the
  **data** Postgres (`ghl-postgres`). Airflow joins the external `health-net` so
  the DAG can reach the data DB by service name.
- **Custom image** (`apache/airflow:2.9.2-python3.11` + our deps + dbt) so tasks
  can generate data, load Postgres, and run dbt in-container.
- **`health_pipeline` DAG**: `start → generate_data → load_to_postgres →
  dbt_build → dbt_test → end` (BashOperators calling the same modules the CLI
  uses). For fast demos it generates a **small** seeded dataset (env-tunable),
  not the full 7M rows.
- **Reliability features**, as required:
  - **Retries** (2) with **exponential backoff** on every task.
  - **Failure callback** (`on_failure_callback`) — an alert *stub* that logs a
    structured alert; a clearly-marked TODO shows where a Slack/email operator
    would go.
  - **SLA** per task (and an `sla_miss_callback`).
  - **Idempotent tasks**: seeded generator, replace-on-load, deterministic dbt —
    safe to retry/backfill.
  - **Backfill**: real `start_date` + `@daily` schedule; `airflow dags backfill`
    (or `catchup=True`) produces correct per-interval runs.
- **`retry_demo` DAG**: deliberately fails on the first try and succeeds on
  retry, to demonstrate retry + backoff + the failure callback in isolation
  (screenshot in `docs/img/`).

## Alternatives considered

- **CeleryExecutor / KubernetesExecutor** — overkill for a single-box portfolio
  pipeline; LocalExecutor still runs tasks in parallel and is far simpler.
- **Reusing the data Postgres for Airflow metadata** — rejected; mixing
  orchestration state with analytics data is bad hygiene and complicates resets.
- **PythonOperator calling functions directly** — BashOperator keeps each step
  identical to the documented CLI command (easy to reproduce by hand), which fits
  the "defensible by hand" goal; the retry demo uses PythonOperator where raising
  is the point.
- **Astronomer/MWAA** — out of scope; local Docker is reproducible and free.

## Bugs hit while building this (kept for honesty + interview value)

1. **Airflow 2.9 + SQLAlchemy 2.x.** Pinning `SQLAlchemy==2.0.30` in the image
   broke the scheduler (`ArgumentError: ... can't be correctly interpreted for
   Annotated Declarative`). Airflow 2.9 needs SQLAlchemy < 2.0. Fix: install
   project deps **under Airflow's official constraints file** and put **dbt in an
   isolated venv** so its dependency tree can't bump Airflow's SQLAlchemy.
2. **`if_exists="replace"` vs dependent views.** The loader dropped `raw.*`
   tables, which failed with `DependentObjectsStillExist` once dbt staging views
   sat on top. Fix: the loader now **TRUNCATE+append** when a table already
   exists (only `replace`/create on first load) — idempotent *and* dependency-safe.
3. **In-network port.** dbt connected to `postgres:5433` (the host mapping)
   instead of the in-network `5432`. Fix: set `DBT_PG_PORT=5432` in the Airflow env.
4. **Incremental fact + shrinking source.** The demo regenerates a *small*
   dataset, but the incremental `fct_daily_activity` retained 270k rows from the
   Phase 3 full run, orphaning the relationship test. Fix: the DAG runs
   `dbt build --full-refresh` because it fully re-creates the source each run; a
   production append-only pipeline would drop the flag.

## Consequences

- `docker compose up` for the base + the Airflow compose gives a working UI at
  :8080 and a DAG that runs green end-to-end.
- The DAG mirrors the Makefile steps, so the orchestrated and manual paths can't
  drift.
- Alerts are stubs (logged), honestly marked — no fake Slack integration.

## Interview check

**`execution_date` / logical date vs run date?**
The **logical date** (formerly `execution_date`) is the start of the data
interval the run represents — e.g. the `@daily` run *for* 2025-01-01 logically
processes that day's data, even though it physically runs at the *end* of the
interval (early 2025-01-02). The **run date** is wall-clock when it actually
executed. Tasks should key their work off the logical date, not "now", so reruns
and backfills are correct and deterministic.

**How to backfill?**
Give the DAG a real `start_date` and schedule, then either set `catchup=True` or
run `airflow dags backfill -s <start> -e <end> health_pipeline`. Because every
task is idempotent and keyed off the logical date, Airflow replays each missed
interval as its own run without duplicating data.

**What happens when a task exceeds its SLA?**
The task isn't killed — Airflow records an **SLA miss** (visible in the UI and
the `sla_miss` table) and fires `sla_miss_callback` so you can alert. SLAs are a
*timeliness* signal, distinct from failure: a task can succeed but still miss its
SLA if it ran too slowly.
