-- Roll meals up to one row per user/day with summed macros and a meal count.
-- Ephemeral: this is a reusable building block for fct_nutrition, not a table.
with meals as (
    select * from {{ ref('stg_nutrition_log') }}
)

select
    user_id,
    log_date,
    count(*)                as meals_logged,
    sum(calories)           as total_calories,
    sum(protein_g)          as protein_g,
    sum(carbs_g)            as carbs_g,
    sum(fat_g)              as fat_g
from meals
group by user_id, log_date
