# Dashboards (Phase 8)

Two BI tools read the **BigQuery star schema** built by dbt (Phase 5):

- **Looker Studio** — primary, free, connects natively to BigQuery.
- **Power BI** — a `.pbix` (DirectQuery to the same warehouse) dropped in here.

> The dashboards read the warehouse marts (`dim_user`, `dim_device`, `dim_date`,
> `fct_daily_activity`, `fct_body_scan`, `fct_nutrition`, `dim_user_scd2`). All
> data is synthetic.

## Looker Studio setup

1. Build the BigQuery star schema first (see [`warehouse/`](../warehouse/README.md)
   and [ADR-0006](../docs/adr/0006-bigquery.md)) — needs credentials.
2. In Looker Studio → **Create → Data source → BigQuery** → pick project
   `$BQ_PROJECT_ID`, dataset `health_lakehouse`.
3. Add the marts as sources. Suggested report pages:
   - **Activity overview** — avg steps / active minutes / resting HR over time
     (`fct_daily_activity` × `dim_date`), filter by `dim_user.membership_tier`.
   - **Body composition** — weight / body-fat % / muscle-mass trend per cohort
     (`fct_body_scan`).
   - **Nutrition vs expenditure** — `calorie_balance` distribution
     (`fct_nutrition`).
   - **Rolling health score** — the PySpark output (load `data/processed` or a
     warehouse table) as a time series.
4. Export screenshots into [`../docs/img/`](../docs/img/) and link them here.

> Screenshots: _to be added once the BigQuery warehouse is live (credential
> boundary)._ Placeholders avoid claiming results that don't exist yet.

## Power BI (.pbix)

Drop the `.pbix` in this folder. Use **DirectQuery** to BigQuery (same dataset),
reuse the star schema relationships, and apply RLS on `dim_user` if demoing
row-level security.

```
dashboards/
  README.md          (this file)
  health.pbix        (add your Power BI file here)
```
