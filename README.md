# gulf-health-lakehouse

> **I rebuilt my production health-tech data domain on an open, modern data stack.**

A public portfolio monorepo that reproduces a consumer health-tech data domain
(wearables, body-composition scans, nutrition logs) on an open stack —
**Docker · dbt · Airflow · BigQuery · Kafka · PySpark** — with an A/B-testing
analysis and a BI dashboard on top.

> ⚠️ **All data in this repository is 100% synthetic.** It is generated
> programmatically with `numpy` + `faker` (see [`data_generator/`](data_generator/)).
> There is **no real user data** anywhere in this repo, and no performance
> claims are made about the synthetic project.

---

## Status

🚧 Building in public, incrementally. See per-component READMEs and
[`docs/adr/`](docs/adr/) for design decisions.

## Why this exists

I'm a Python-first data engineer who owns an automated AWS ETL pipeline ingesting
10k+ daily wearable records at a health-tech app. This repo is the open-stack
public demonstration of that same problem domain: realistic synthetic data, a
warehouse-centric transform layer, orchestration, streaming, and a heavy batch
job — all reproducible by hand.

## Architecture (high level)

```
data_generator ─► ingestion ─► Postgres ─► dbt (staging→marts) ─► BigQuery star schema ─► Looker Studio
        │                                        ▲
        ├─► Kafka (producer→topic→consumer) ─────┘
        └─► PySpark rolling health score (full history)
                         Airflow orchestrates generate→load→dbt
```

A detailed mermaid diagram lives in [`docs/architecture.md`](docs/architecture.md).

## License

[MIT](LICENSE)
