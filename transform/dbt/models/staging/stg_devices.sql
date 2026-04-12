with source as (
    select * from {{ source('raw', 'dim_device') }}
)

select
    cast(device_id as integer) as device_id,
    brand,
    model,
    category
from source
