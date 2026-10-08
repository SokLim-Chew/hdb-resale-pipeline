with transactions as (

    select * from {{ ref('stg_hdb_resale') }}

)

-- Columns listed explicitly: this is the public interface, so new staging
-- columns only appear here by deliberate choice.
select
    source_row_id as transaction_id,
    transaction_month,
    extract(year from transaction_month)::integer as transaction_year,

    town,
    flat_type,
    flat_model,
    block,
    street_name,
    storey_range,
    storey_min,
    storey_max,

    floor_area_sqm,
    lease_commence_year,
    extract(year from transaction_month)::integer - lease_commence_year as flat_age_years,
    remaining_lease_months,
    round(remaining_lease_months / 12.0, 1) as remaining_lease_years,

    resale_price,
    price_per_sqm,

    _loaded_at

from transactions
