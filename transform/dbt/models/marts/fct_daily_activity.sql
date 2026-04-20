-- Daily activity fact at user/day grain.
--
-- INCREMENTAL on activity_date: the big daily table grows by date, so on a
-- normal run we only process rows newer than what's already loaded, instead of
-- rebuilding 270k+ rows every time. `unique_key` makes late-arriving rows for an
-- existing day upsert rather than duplicate. Full-refresh rebuilds from scratch.
{{
    config(
        materialized='incremental',
        unique_key=['user_id', 'date_key'],
        incremental_strategy='delete+insert'
    )
}}

with activity as (
    select * from {{ ref('int_activity_enriched') }}
)

select
    -- surrogate composite is captured via (user_id, date_key)
    a.user_id,
    cast(to_char(a.activity_date, 'YYYYMMDD') as integer) as date_key,
    a.activity_date,
    a.device_id,
    a.steps,
    a.active_minutes,
    a.resting_hr,
    a.calories,
    a.sleep_minutes,
    a.sleep_deep_minutes,
    a.sleep_rem_minutes,
    a.sleep_light_minutes,
    a.restorative_sleep_ratio,
    a.hit_step_goal
from activity a

{% if is_incremental() %}
    -- only new days since the max already loaded
    where a.activity_date > (select coalesce(max(activity_date), '1900-01-01') from {{ this }})
{% endif %}
