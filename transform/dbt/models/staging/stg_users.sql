-- Light cleaning of the raw user dimension: typing + tidy column names.
with source as (
    select * from {{ source('raw', 'dim_user') }}
)

select
    cast(user_id as integer)            as user_id,
    full_name,
    sex,
    cast(age as integer)                as age,
    cast(height_cm as numeric(5, 1))    as height_cm,
    country,
    cast(primary_device_id as integer)  as primary_device_id,
    cast(signup_date as date)           as signup_date
from source
