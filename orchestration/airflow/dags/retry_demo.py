"""A tiny DAG that deliberately fails once, then succeeds on retry.

Purpose: demonstrate Airflow's retry mechanics and the failure callback without
destabilising the real pipeline. The task fails on `try_number == 1` and passes
on the retry, so a single manual trigger visibly shows: fail -> wait (backoff)
-> retry -> success. See ADR-0005.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator


def alert_on_failure(context):
    ti = context["task_instance"]
    print(f"[ALERT] retry_demo failed on try={ti.try_number} (expected on try 1)")


def flaky(**context):
    ti = context["task_instance"]
    if ti.try_number == 1:
        raise RuntimeError("deliberate first-attempt failure to demonstrate retry")
    print(f"succeeded on try={ti.try_number}")


with DAG(
    dag_id="retry_demo",
    description="fails once, succeeds on retry (demonstrates retries + backoff)",
    start_date=datetime(2025, 1, 1),
    schedule=None,                    # manual trigger only
    catchup=False,
    tags=["demo", "retry"],
    default_args={
        "retries": 2,
        "retry_delay": timedelta(seconds=15),
        "on_failure_callback": alert_on_failure,
    },
) as dag:
    PythonOperator(task_id="flaky_task", python_callable=flaky)
