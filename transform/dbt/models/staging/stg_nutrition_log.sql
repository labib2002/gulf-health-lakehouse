-- One row per logged meal. Lowercase meal_type for stable downstream grouping.
with source as (
    select * from {{ source('raw', 'nutrition_log') }}
)

select
    cast(user_id as integer)        as user_id,
    cast(log_date as date)          as log_date,
    lower(meal_type)                as meal_type,
    cast(calories as numeric(7, 1)) as calories,
    cast(protein_g as numeric(6, 1)) as protein_g,
    cast(carbs_g as numeric(6, 1))  as carbs_g,
    cast(fat_g as numeric(6, 1))    as fat_g
from source
