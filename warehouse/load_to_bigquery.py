"""Load generated raw parquet into a BigQuery `raw` dataset.

The Postgres path (ingestion/load_to_postgres.py) is the one exercised in CI; this
is its BigQuery sibling for Phase 5. It is written to run as-is once credentials
exist — until then it's the documented, real code at the credential boundary.

Usage (requires google-cloud-bigquery + a service account):
    BQ_PROJECT_ID=... BQ_DATASET=raw \
    GOOGLE_APPLICATION_CREDENTIALS=/path/key.json \
    python -m warehouse.load_to_bigquery
"""

from __future__ import annotations

import os
from pathlib import Path

# Same table set / order as the Postgres loader.
from ingestion.load_to_postgres import TABLES


def load(source: str = "data/raw", dataset: str | None = None) -> None:
    # Imported lazily so this module is importable without the BQ client/creds.
    from google.cloud import bigquery  # noqa: PLC0415

    project = os.environ["BQ_PROJECT_ID"]          # >>> TODO(credentials) <<<
    dataset = dataset or os.environ.get("BQ_RAW_DATASET", "raw")
    client = bigquery.Client(project=project)

    ds_ref = bigquery.Dataset(f"{project}.{dataset}")
    ds_ref.location = os.environ.get("BQ_LOCATION", "US")
    client.create_dataset(ds_ref, exists_ok=True)

    src = Path(source)
    for name in TABLES:
        path = src / f"{name}.parquet"
        if not path.exists():
            print(f"  ! skip {name}: {path} not found")
            continue
        table_id = f"{project}.{dataset}.{name}"
        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.PARQUET,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,  # idempotent
        )
        with open(path, "rb") as fh:
            job = client.load_table_from_file(fh, table_id, job_config=job_config)
        job.result()
        print(f"  loaded {table_id} ({client.get_table(table_id).num_rows:,} rows)")


def main() -> None:
    print("Loading raw parquet -> BigQuery")
    load()
    print("Done. Now run: dbt build --target bigquery")


if __name__ == "__main__":
    main()
