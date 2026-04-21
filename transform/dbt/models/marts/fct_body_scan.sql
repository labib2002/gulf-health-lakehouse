-- Body-composition fact at user/scan-date grain. This is where a user's
-- point-in-time weight history lives (a fact event), NOT in dim_user — weight
-- changes constantly and is measured, so it belongs on the fact, not the dim.
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
