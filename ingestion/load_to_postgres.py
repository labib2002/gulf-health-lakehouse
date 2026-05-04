"""Load generated raw tables into Postgres (the `raw` schema).

This is the bridge between Phase 0 (files) and Phase 3 (dbt on Postgres). It
reads the parquet files in ``data/raw/`` and writes one Postgres table per file
under a ``raw`` schema. Loads are **idempotent**: each table is fully replaced
(``if_exists="replace"``), so re-running is safe and Airflow can retry it.

Usage
-----
    python -m ingestion.load_to_postgres                # load all tables
    python -m ingestion.load_to_postgres --only dim_user daily_activity
    python -m ingestion.load_to_postgres --source data/raw/sample   # tiny sample
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

RAW_SCHEMA = "raw"

# Tables we expect from the generator, in FK-friendly load order.
TABLES = [
    "dim_device",
    "dim_user",
    "user_attr_history",
    "daily_activity",
    "intraday_hr",
    "body_scan",
    "nutrition_log",
    "experiment_assignment",
]


def engine_from_env():
    user = os.getenv("POSTGRES_USER", "health")
    pwd = os.getenv("POSTGRES_PASSWORD", "health")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "health")
    url = f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"
    return create_engine(url, future=True)


def _table_exists(eng, schema: str, table: str) -> bool:
    """True if schema.table already exists (so we TRUNCATE instead of DROP)."""
    q = text(
        "select 1 from information_schema.tables "
        "where table_schema = :s and table_name = :t"
    )
    with eng.connect() as conn:
        return conn.execute(q, {"s": schema, "t": table}).first() is not None


def load(source: str = "data/raw", only: list[str] | None = None, chunksize: int = 50_000) -> None:
    src = Path(source)
    eng = engine_from_env()
    with eng.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {RAW_SCHEMA}"))

    targets = only or TABLES
    for name in targets:
        path = src / f"{name}.parquet"
        if not path.exists():
            print(f"  ! skip {name}: {path} not found")
            continue
        df = pd.read_parquet(path)
        # Idempotent reload that is safe even when dbt views depend on these
        # tables: on the FIRST load the table doesn't exist, so we create it via
        # `replace`; on subsequent loads we TRUNCATE + append instead of dropping,
        # so dependent objects (the dbt staging views) are preserved. A naive
        # `if_exists="replace"` would DROP the table and fail with
        # DependentObjectsStillExist once views exist on top of it.
        exists = _table_exists(eng, RAW_SCHEMA, name)
        if exists:
            with eng.begin() as conn:
                conn.execute(text(f'TRUNCATE TABLE {RAW_SCHEMA}."{name}"'))
            mode = "append"
        else:
            mode = "replace"
        df.to_sql(
            name,
            eng,
            schema=RAW_SCHEMA,
            if_exists=mode,
            index=False,
            chunksize=chunksize,
            method="multi",
        )
        print(f"  loaded {RAW_SCHEMA}.{name:24s} {len(df):>12,} rows ({mode})")


def main() -> None:
    p = argparse.ArgumentParser(description="Load raw parquet into Postgres.")
    p.add_argument("--source", default="data/raw", help="dir containing <table>.parquet")
    p.add_argument("--only", nargs="*", help="subset of tables to load")
    args = p.parse_args()
    print(f"Loading from {args.source} -> Postgres schema '{RAW_SCHEMA}'")
    load(source=args.source, only=args.only)
    print("Load complete.")


if __name__ == "__main__":
    main()
