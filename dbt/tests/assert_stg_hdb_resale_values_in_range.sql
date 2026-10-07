-- Singular test: returns rows that violate basic sanity rules; passes when empty.
-- HDB leases are 99 years (1188 months) at most.
select *
from {{ ref('stg_hdb_resale') }}
where remaining_lease_months not between 0 and 1188
    or resale_price <= 0
    or floor_area_sqm <= 0
    or storey_min > storey_max
