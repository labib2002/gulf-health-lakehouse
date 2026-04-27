# Custom Airflow image: base Airflow + this project's runtime deps, with dbt
# isolated in its own virtualenv so dbt's dependency tree can't upgrade
# Airflow's pinned SQLAlchemy (Airflow 2.9 needs SQLAlchemy < 2.0).
FROM apache/airflow:2.9.2-python3.11

ARG AIRFLOW_VERSION=2.9.2
ARG PY=3.11

# 1) Project runtime deps for the generator + loader, installed UNDER Airflow's
#    official constraints so no core Airflow dependency is silently bumped.
COPY orchestration/airflow/requirements-airflow.txt /tmp/requirements-airflow.txt
RUN pip install --no-cache-dir -r /tmp/requirements-airflow.txt \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PY}.txt"

# 2) dbt in an isolated venv (its own SQLAlchemy etc.), exposed on PATH as `dbt`.
USER root
RUN python -m venv /opt/dbt-venv \
    && /opt/dbt-venv/bin/pip install --no-cache-dir "dbt-core==1.8.2" "dbt-postgres==1.8.2" \
    && ln -s /opt/dbt-venv/bin/dbt /usr/local/bin/dbt
USER airflow
