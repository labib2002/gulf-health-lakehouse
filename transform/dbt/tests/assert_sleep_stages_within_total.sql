-- Singular test: the sum of sleep stage minutes must not exceed total sleep
-- (allow a tiny rounding slack). Returns offending rows -> test fails if any.
select
    user_id,
    activity_date,
    sleep_minutes,
    sleep_deep_minutes + sleep_rem_minutes + sleep_light_minutes as stage_sum
from {{ ref('stg_daily_activity') }}
where sleep_deep_minutes + sleep_rem_minutes + sleep_light_minutes > sleep_minutes + 1
