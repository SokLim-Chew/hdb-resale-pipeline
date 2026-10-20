{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='transaction_month',
        on_schema_change='fail'
    )
}}

-- Incremental: the first run (or --full-refresh) loads everything. Later runs
-- reprocess only the last `lookback_months` already loaded, plus newer months,
-- and replace those months as a whole (delete+insert on transaction_month).
-- The lookback picks up late-registered sales and corrections to recent months.

with transactions as (

    select * from {{ ref('stg_hdb_resale') }}

    {% if is_incremental() %}
    where transaction_month >= (
        select max(transaction_month) - interval '{{ var("lookback_months") }} months'
        from {{ this }}
    )
    {% endif %}

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

    -- Numerics cast to the exact types in the contract (_marts_models.yml): on
    -- incremental runs, on_schema_change compares precision, and the new batch's
    -- types come from this SELECT, so a bare numeric would count as a type change.
    floor_area_sqm::numeric(6,2) as floor_area_sqm,
    lease_commence_year,
    extract(year from transaction_month)::integer - lease_commence_year as flat_age_years,
    remaining_lease_months,
    round(remaining_lease_months / 12.0, 1)::numeric(4,1) as remaining_lease_years,

    resale_price::numeric(12,2) as resale_price,
    price_per_sqm::numeric(10,2) as price_per_sqm,

    _loaded_at

from transactions
