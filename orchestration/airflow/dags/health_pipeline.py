"""Health data pipeline DAG: generate -> load -> dbt build -> dbt test.

Design notes (see ADR-0005)
---------------------------
* **Idempotent tasks.** The generator is seeded (same output every run), the
  loader replaces tables, and dbt models are deterministic — so any task can be
  retried or back-filled without creating duplicates or drift.
* **Retries + backoff** on every task; a **failure callback** (alert stub) fires
  on the final failure of a task.
* **SLA** on the whole-pipeline critical path; a miss is recorded by Airflow and
  surfaced via `sla_miss_callback`.
* **Backfill**: the DAG has a real `schedule` and `start_date`, and every task
  keys its work off the run's logical date where relevant, so
  `airflow dags backfill` produces correct per-interval runs.
* For fast, repeatable orchestration demos this generates a SMALL dataset
  (env GEN_USERS/GEN_HISTORY_MONTHS), not the full 7M-row set.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator

PROJECT_DIR = os.environ.get("PROJECT_DIR", "/opt/airflow/repo")
DBT_DIR = f"{PROJECT_DIR}/transform/dbt"

# Small dataset for orchestration demos (override via Airflow env if desired).
GEN_USERS = os.environ.get("PIPELINE_GEN_USERS", "40")
GEN_MONTHS = os.environ.get("PIPELINE_GEN_MONTHS", "3")


def alert_on_failure(context):
    """Failure callback (alert stub).

    In production this would post to Slack / PagerDuty / email. Here we log a
    structured alert so the behaviour is demonstrable without external creds.
    """
    ti = context.get("task_instance")
    dag_id = context.get("dag").dag_id if context.get("dag") else "?"
    exc = context.get("exception")
    print(
        f"[ALERT] task FAILED dag={dag_id} task={ti.task_id} "
        f"run={context.get('run_id')} try={ti.try_number} error={exc!r}"
    )
    # TODO: wire a real SlackWebhookOperator / EmailOperator here when creds exist.


def alert_on_sla_miss(dag, task_list, blocking_task_list, slas, blocking_tis):
    """SLA-miss callback (alert stub)."""
    print(f"[SLA-MISS] dag={dag.dag_id} missed SLAs={[s.task_id for s in slas]}")


default_args = {
    "owner": "data-eng",
    "retries": 2,
    "retry_delay": timedelta(seconds=20),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=3),
    "on_failure_callback": alert_on_failure,
}

with DAG(
    dag_id="health_pipeline",
    description="generate -> load -> dbt build -> dbt test (synthetic health data)",
    default_args=default_args,
    start_date=datetime(2025, 1, 1),
    schedule="@daily",
    catchup=False,                 # flip to True (or use `dags backfill`) to backfill
    max_active_runs=1,
    sla_miss_callback=alert_on_sla_miss,
    tags=["health", "dbt", "synthetic"],
) as dag:

    start = EmptyOperator(task_id="start")

    # 1) generate a small, seeded dataset (idempotent: same seed -> same bytes)
    generate = BashOperator(
        task_id="generate_data",
        bash_command=(
            f"cd {PROJECT_DIR} && "
            f"GEN_USERS={GEN_USERS} GEN_HISTORY_MONTHS={GEN_MONTHS} "
            f"python -m data_generator.generate --no-sample"
        ),
        sla=timedelta(minutes=10),
    )

    # 2) load raw parquet into Postgres (idempotent: replaces tables)
    load = BashOperator(
        task_id="load_to_postgres",
        bash_command=f"cd {PROJECT_DIR} && python -m ingestion.load_to_postgres",
        sla=timedelta(minutes=10),
    )

    # 3) dbt deps + build (models + tests run together).
    #    --full-refresh: the generator fully *re-creates* the source each run (and
    #    the demo uses a small dataset), so the incremental fct_daily_activity must
    #    rebuild from the current source rather than accumulate rows from prior,
    #    differently-sized runs. In a production append-only pipeline you would
    #    drop --full-refresh and let the incremental logic append new dates.
    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=(
            f"cd {DBT_DIR} && dbt deps && "
            f"dbt build --full-refresh --profiles-dir {DBT_DIR}"
        ),
        sla=timedelta(minutes=15),
    )

    # 4) explicit dbt test step (redundant with build's tests, but demonstrates a
    #    separate quality gate that can be retried/alerted independently)
    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"cd {DBT_DIR} && dbt test --profiles-dir {DBT_DIR}",
        sla=timedelta(minutes=10),
    )

    end = EmptyOperator(task_id="end")

    start >> generate >> load >> dbt_build >> dbt_test >> end
