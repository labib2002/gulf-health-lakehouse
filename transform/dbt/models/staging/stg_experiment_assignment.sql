with source as (
    select * from {{ source('raw', 'experiment_assignment') }}
)

select
    cast(user_id as integer)        as user_id,
    experiment_name,
    variant,
    cast(engaged_next_day as integer) as engaged_next_day
from source
