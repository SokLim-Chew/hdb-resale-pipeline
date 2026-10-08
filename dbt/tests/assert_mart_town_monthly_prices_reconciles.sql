-- Every transaction must be counted exactly once in the aggregate.
-- Returns a row (fails) when the totals differ.
with mart as (

    select sum(transaction_count) as total from {{ ref('mart_town_monthly_prices') }}

),

fct as (

    select count(*) as total from {{ ref('fct_resale_transactions') }}

)

select
    mart.total as mart_total,
    fct.total as fct_total
from mart
cross join fct
where mart.total != fct.total
