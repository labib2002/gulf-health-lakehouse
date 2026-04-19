-- User dimension enriched with the user's CURRENT membership tier + company,
-- derived from the latest effective-dated span. (The full SCD2 history version
-- lives in the BigQuery target in Phase 5; on Postgres we keep the current view.)
with users as (
    select * from {{ ref('stg_users') }}
),

history as (
    select * from {{ ref('stg_user_attr_history') }}
),

current_attrs as (
    -- pick the most recent span per user
    select
        user_id,
        membership_tier,
        company,
        effective_from
    from (
        select
            *,
            row_number() over (
                partition by user_id order by effective_from desc
            ) as rn
        from history
    ) ranked
    where rn = 1
)

select
    u.user_id,
    u.full_name,
    u.sex,
    u.age,
    u.height_cm,
    u.country,
    u.primary_device_id,
    u.signup_date,
    c.membership_tier,
    c.company,
    c.effective_from as tier_effective_from
from users u
left join current_attrs c on u.user_id = c.user_id
