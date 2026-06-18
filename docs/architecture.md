# Architecture

> All data is **synthetic** (generated with numpy + Faker). No real users.

## System overview

```mermaid
flowchart TB
  subgraph gen["Phase 0 — Generation"]
    G[data_generator<br/>seeded, ~7.3M rows]
  end

  subgraph storage["Storage"]
    RAW[(data/raw<br/>parquet + csv)]
    PG[(Postgres 16<br/>raw + analytics)]
    BQ[(BigQuery<br/>star schema)]
  end

  subgraph transform["Phase 3 / 5 — Transform"]
    DBT[dbt<br/>staging → intermediate → marts]
  end

  subgraph stream["Phase 6 — Streaming"]
    KP[producer]
    KT{{wearable-events<br/>3 partitions}}
    KC[consumer group]
  end

  subgraph batch["Phase 7 — Batch"]
    SP[PySpark<br/>rolling 30-day score]
  end

  subgraph bi["Phase 8 — BI"]
    LS[Looker Studio]
    PB[Power BI .pbix]
  end

  AF[[Phase 4 — Airflow<br/>orchestrates generate→load→dbt]]
  AB[Phase 2 — A/B test<br/>z-test + power]

  G --> RAW
  RAW -->|ingestion loader| PG
  PG --> DBT --> PG
  DBT -. dbt-bigquery .-> BQ
  RAW --> SP --> RAW
  G --> KP --> KT --> KC --> PG
  RAW --> AB
  BQ --> LS
  BQ --> PB
  AF -.-> G
  AF -.-> PG
  AF -.-> DBT
```

## Data flow (happy path)

1. **Generate** — `data_generator` writes parquet + csv to `data/raw/`
   (deterministic; full set ~7.3M rows).
2. **Ingest** — `ingestion/load_to_postgres.py` lands `raw.*` tables in Postgres
   (idempotent truncate+append).
3. **Transform** — dbt builds `staging → intermediate → marts` (star schema:
   `dim_user`, `dim_device`, `dim_date`, `fct_daily_activity` (incremental),
   `fct_body_scan`, `fct_nutrition`, plus `dim_user_scd2`).
4. **Orchestrate** — Airflow chains generate → load → `dbt build` → `dbt test`
   with retries, SLAs, and alerts.
5. **Warehouse** — the same dbt models target BigQuery with date partitioning,
   `user_id` clustering, and SCD2 (built offline pending credentials).
6. **Stream** — a Kafka producer emits wearable events (keyed by `user_id`,
   `acks=all`) → topic → consumer group → Postgres.
7. **Batch** — PySpark recomputes a rolling 30-day health score over the full
   history (window + broadcast join + repartition) → partitioned parquet.
8. **Analyze / visualize** — a two-proportion z-test + power analysis on the
   experiment; Looker Studio / Power BI on the warehouse star schema.

## The star schema (marts)

```mermaid
erDiagram
  dim_user ||--o{ fct_daily_activity : user_id
  dim_user ||--o{ fct_body_scan : user_id
  dim_user ||--o{ fct_nutrition : user_id
  dim_device ||--o{ fct_daily_activity : device_id
  dim_date ||--o{ fct_daily_activity : date_key
  dim_date ||--o{ fct_body_scan : date_key
  dim_date ||--o{ fct_nutrition : date_key
```

`fct_body_scan` holds point-in-time **weight history** (measured facts);
`dim_user_scd2` holds **slowly-changing attributes** (tier / company) as Type-2
versions. See [ADR-0006](adr/0006-bigquery.md).
