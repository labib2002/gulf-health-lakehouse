-- Enrich daily activity with derived metrics used by the activity fact.
-- Ephemeral building block; keeps the fact model focused on grain + keys.
with activity as (
    select * from {{ ref('stg_daily_activity') }}
)

select
    user_id,
    activity_date,
    device_id,
    steps,
    active_minutes,
    resting_hr,
    calories,
    sleep_minutes,
    sleep_deep_minutes,
    sleep_rem_minutes,
    sleep_light_minutes,
    -- sleep efficiency proxy: share of sleep that is deep+rem
    round(
        (sleep_deep_minutes + sleep_rem_minutes)::numeric
        / nullif(sleep_minutes, 0), 3
    ) as restorative_sleep_ratio,
    -- simple activity flag for downstream filtering / marts
    case when steps >= 10000 then true else false end as hit_step_goal
from activity
