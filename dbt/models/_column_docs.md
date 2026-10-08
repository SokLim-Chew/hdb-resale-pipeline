{# Shared column descriptions, referenced from YAML with {{ doc('name') }}.
   Write once here instead of repeating them in staging and marts. #}

{% docs transaction_month %}
Month of the sale, stored as the first day of that month. Parsed from the source `month` field ('YYYY-MM').
{% enddocs %}

{% docs town %}
HDB town, e.g. 'ANG MO KIO'. 26 towns as of 2026. New towns such as Tengah are expected, so the `accepted_values` test only warns on unknown values.
{% enddocs %}

{% docs flat_type %}
Number of rooms or flat category: '1 ROOM' to '5 ROOM', 'EXECUTIVE' or 'MULTI-GENERATION'. Marts group by this, so an unknown value fails the build.
{% enddocs %}

{% docs flat_model %}
HDB design model, e.g. 'Model A', 'Improved', 'DBSS'. 21 models as of 2026; unknown values only warn.
{% enddocs %}

{% docs block %}
Block number, as text (it can include a letter suffix).
{% enddocs %}

{% docs street_name %}
Street name as published by HDB, often abbreviated (e.g. 'ANG MO KIO AVE 10').
{% enddocs %}

{% docs storey_range %}
Storey band as published, e.g. '01 TO 03'. HDB publishes bands, not exact floors.
{% enddocs %}

{% docs storey_min %}
Lowest storey of the band, parsed from `storey_range`.
{% enddocs %}

{% docs storey_max %}
Highest storey of the band, parsed from `storey_range`.
{% enddocs %}

{% docs floor_area_sqm %}
Floor area in square metres.
{% enddocs %}

{% docs lease_commence_year %}
Year the 99-year lease started. The source field is called `lease_commence_date` but holds only a year.
{% enddocs %}

{% docs remaining_lease_months %}
Remaining lease at the time of sale, in months. Parsed from text in four source formats ('61 years 04 months', '61 years', '61 years 01 month', '61 years 0 months'). NULL would mean an unrecognised format.
{% enddocs %}

{% docs resale_price %}
Sale price in SGD. Stored as numeric because a few prices have cents.
{% enddocs %}

{% docs price_per_sqm %}
`resale_price / floor_area_sqm` in SGD, rounded to 2 decimals.
{% enddocs %}

{% docs _loaded_at %}
When the ingestion script loaded the row into `raw.hdb_resale`. Identical for every row of one load.
{% enddocs %}
