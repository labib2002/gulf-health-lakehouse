-- Daily wearable activity, one row per user/day. Light typing + a derived
-- total-sleep sanity column kept out; downstream marts compute derived metrics.
with source as (
    select * from {{ source('raw', 'daily_activity') }}
)

select
    cast(user_id as integer)            as user_id,
    cast(activity_date as date)         as activity_date,
    cast(device_id as integer)          as device_id,
    cast(steps as integer)              as steps,
    cast(active_minutes as integer)     as active_minutes,
    cast(resting_hr as numeric(5, 1))   as resting_hr,
    cast(sleep_minutes as integer)      as sleep_minutes,
    cast(sleep_deep_minutes as integer) as sleep_deep_minutes,
    cast(sleep_rem_minutes as integer)  as sleep_rem_minutes,
    cast(sleep_light_minutes as integer) as sleep_light_minutes,
    cast(calories as integer)           as calories
from source
