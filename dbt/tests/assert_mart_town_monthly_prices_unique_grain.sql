-- Returns any town x flat_type x month that appears more than once.
select
    transaction_month,
    town,
    flat_type,
    count(*) as row_count
from {{ ref('mart_town_monthly_prices') }}
group by transaction_month, town, flat_type
having count(*) > 1
