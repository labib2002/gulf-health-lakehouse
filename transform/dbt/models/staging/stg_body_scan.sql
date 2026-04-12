with source as (
    select * from {{ source('raw', 'body_scan') }}
)

select
    cast(user_id as integer)            as user_id,
    cast(scan_date as date)             as scan_date,
    cast(device_id as integer)          as device_id,
    cast(weight_kg as numeric(6, 1))    as weight_kg,
    cast(bmi as numeric(4, 1))          as bmi,
    cast(body_fat_pct as numeric(4, 1)) as body_fat_pct,
    cast(muscle_mass_kg as numeric(5, 1)) as muscle_mass_kg,
    cast(visceral_fat as numeric(4, 1)) as visceral_fat
from source
