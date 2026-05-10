-- Body-composition fact at user/scan-date grain. This is where a user's
-- point-in-time weight history lives (a fact event), NOT in dim_user — weight
-- changes constantly and is measured, so it belongs on the fact, not the dim.
--
-- On BigQuery: partition by scan_date, cluster by user_id (same access pattern as
-- the activity fact). No-ops on Postgres.
{{
    config(
        partition_by=(
            {'field': 'scan_date', 'data_type': 'date', 'granularity': 'month'}
            if target.type == 'bigquery' else none
        ),
        cluster_by=(['user_id'] if target.type == 'bigquery' else none)
    )
}}

select
    user_id,
    cast(to_char(scan_date, 'YYYYMMDD') as integer) as date_key,
    scan_date,
    device_id,
    weight_kg,
    bmi,
    body_fat_pct,
    muscle_mass_kg,
    visceral_fat
from {{ ref('stg_body_scan') }}
