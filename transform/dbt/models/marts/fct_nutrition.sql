-- Nutrition fact at user/day grain (rolled up from individual meals in the
-- intermediate layer). Joins the daily activity calories so analysts can compare
-- intake vs expenditure in one place.
--
-- On BigQuery: partition by log_date, cluster by user_id. No-ops on Postgres.
{{
    config(
        partition_by=(
            {'field': 'log_date', 'data_type': 'date', 'granularity': 'day'}
            if target.type == 'bigquery' else none
        ),
        cluster_by=(['user_id'] if target.type == 'bigquery' else none)
    )
}}

with nutrition as (
    select * from {{ ref('int_nutrition_daily') }}
),

activity as (
    select user_id, activity_date, calories as calories_burned
    from {{ ref('stg_daily_activity') }}
)

select
    n.user_id,
    cast(to_char(n.log_date, 'YYYYMMDD') as integer) as date_key,
    n.log_date,
    n.meals_logged,
    n.total_calories as calories_consumed,
    n.protein_g,
    n.carbs_g,
    n.fat_g,
    a.calories_burned,
    (n.total_calories - a.calories_burned) as calorie_balance
from nutrition n
left join activity a
    on n.user_id = a.user_id
    and n.log_date = a.activity_date
