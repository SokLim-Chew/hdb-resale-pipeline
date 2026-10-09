# Design decisions

A log of the significant choices in this project. Each entry gives the decision, why it was made, the alternatives considered, and the trade-off. Add new decisions at the end of their phase section. Don't edit old ones when something changes: mark them **Superseded by D-xx** and add a new entry, so the history of reasoning stays visible.

## Contents

- **Platform:** [D-01](#d-01-elt-not-etl) · [D-02](#d-02-separate-postgres-for-airflow-metadata) · [D-03](#d-03-airflow-standalone-in-one-container) · [D-04](#d-04-uv-with-python-pinned-to-312) · [D-05](#d-05-all-configuration-in-env)
- **Ingestion:** [D-06](#d-06-full-refresh-not-incremental) · [D-07](#d-07-download-everything-then-load-in-one-short-transaction) · [D-08](#d-08-copy-not-insert) · [D-09](#d-09-raw-columns-are-all-text) · [D-10](#d-10-offset-pagination-with-safeguards) · [D-11](#d-11-retry-only-http-429-with-exponential-backoff) · [D-12](#d-12-source_columns-is-the-contract-with-the-api) · [D-13](#d-13-unit-tests-with-a-hand-written-fake-session)
- **dbt:** [D-14](#d-14-profilesyml-in-the-repo-secrets-via-env_var) · [D-15](#d-15-override-generate_schema_name) · [D-16](#d-16-staging-as-views-marts-as-tables) · [D-17](#d-17-profile-the-raw-data-before-writing-staging) · [D-18](#d-18-test-severity-error-for-wrong-output-warn-for-human-decisions) · [D-19](#d-19-wide-fact-table-no-dimensions-yet) · [D-20](#d-20-transaction_id--source-row-id-for-now) · [D-21](#d-21-explicit-column-lists-in-marts) · [D-22](#d-22-medians-with-transaction-counts) · [D-23](#d-23-grain-and-reconciliation-tests-on-aggregates) · [D-25](#d-25-shared-doc-blocks-persisted-to-postgres) · [D-26](#d-26-town-regions-as-a-seed-dim_town-driven-by-the-data) · [D-27](#d-27-macros-only-for-repeated-nameable-logic) · [D-28](#d-28-unit-test-logic-with-edge-cases-not-pass-throughs)
- **Workflow:** [D-24](#d-24-feature-branches-pull-requests-merge-commits)

---

## Platform

### D-01: ELT, not ETL
**Phase 1.** Load API data untransformed into `raw`, then transform inside the warehouse with dbt.
- **Why:** The raw data is kept, so a transformation bug is fixed by rebuilding models, without re-downloading. Transformations are versioned, tested SQL instead of logic inside the loader. The loader only moves data, so it fails for fewer reasons.
- **Alternatives:** ETL, cleaning in Python before loading.
- **Trade-off:** Raw and transformed copies are both stored; the warehouse does the transformation work; messy or sensitive source data reaches the warehouse unfiltered.

### D-02: Separate Postgres for Airflow metadata
**Phase 0 (scaffold).** `airflow-db` and `warehouse` are different Postgres instances.
- **Why:** Mirrors a real setup. Orchestrator state and analytics data have different owners, backups and load patterns, and Airflow's tables shouldn't clutter the warehouse.
- **Trade-off:** One more container to run.

### D-03: Airflow standalone in one container
**Phase 0 (scaffold).** `airflow standalone` runs the API server, scheduler, DAG processor and triggerer together, with `LocalExecutor`.
- **Why:** Simplest local setup for learning.
- **Alternatives:** Separate services per component, CeleryExecutor or Kubernetes, as production would use.
- **Trade-off:** No isolation or scaling. Not a production layout.

### D-04: uv, with Python pinned to 3.12
**Phase 1.** uv manages the environment and lockfile; `.python-version` pins 3.12.
- **Why:** `uv.lock` makes installs reproducible. dbt typically supports new Python releases months late, and uv had picked the system's 3.14, so pinning avoids rebuilding the environment later.
- **Note:** `uv init --python 3.12` only sets a *minimum* (`requires-python >= 3.12`); `uv python pin` sets the exact version.

### D-05: All configuration in `.env`
**Phase 1.** Credentials, port and dataset id come from `.env` (gitignored), shared by Compose, the loader and dbt.
- **Why:** One source of truth and no secrets in code. Optional settings have defaults (`WAREHOUSE_HOST=localhost`), so the same code runs on the host and in containers.
- **Gotcha:** Postgres applies the credentials only when initializing an empty volume. See the 2026-09-30 entry in [changelog.md](changelog.md).

## Ingestion

### D-06: Full refresh, not incremental
**Phase 1.** Each run empties `raw.hdb_resale` and reloads everything.
- **Why:** The dataset has no reliable unique key (two genuine sales can be identical), so upserts can't match rows safely. About 240k rows is small enough to reload every run. A full refresh is always correct and idempotent.
- **Alternatives:** Upsert on a key; loading only new months.
- **Trade-off:** Downloads all data every run. Incremental processing is planned in dbt (Phase 3).

### D-07: Download everything, then load in one short transaction
**Phase 1.** Fetch all pages into memory first, then `TRUNCATE` + `COPY` in one transaction.
- **Why:** `TRUNCATE` is transactional in Postgres, so a failure rolls back to the previous complete load, and readers never see a half-loaded table. `TRUNCATE` locks the table until commit, so downloading first keeps the lock to seconds instead of the whole download.
- **Alternatives:** Streaming pages into the table inside the transaction (lower memory, much longer lock).
- **Trade-off:** About 240k rows held in memory, a few hundred MB.

### D-08: `COPY`, not `INSERT`
**Phase 1.** Bulk-load with Postgres `COPY` (psycopg `cursor.copy()`).
- **Why:** Rows are streamed in one operation instead of one statement per row, which is usually tens of times faster.

### D-09: Raw columns are all `TEXT`
**Phase 1.** Every source column is stored as text, plus a pipeline-added `_loaded_at TIMESTAMPTZ DEFAULT now()`.
- **Why:** The load never fails on an unexpected value; type conversion happens in dbt, where it's tested. `_loaded_at` records data freshness. Because `now()` returns the transaction start time, all rows from one load share one timestamp.

### D-10: Offset pagination with safeguards
**Phase 1.** Page with `limit`/`offset` and:
- **advance the offset by rows received, not by `limit`,** so an API that returns smaller pages can't make the loader skip rows;
- **stop on an empty page,** not after a computed page count;
- **compare the rows fetched with the API's `total` before writing,** so an incomplete download fails instead of being loaded.
- **Accepted risk: offset drift.** If the dataset changes during a download, rows can be skipped or repeated. The data updates monthly and a run takes about a minute, and the completeness check catches most cases.

### D-11: Retry only HTTP 429, with exponential backoff
**Phase 1.** On 429, wait 2s, 4s, 8s… for up to 5 attempts; any other error fails immediately. The timeout is 30s, and there's a 1s pause between pages.
- **Why:** 429 ("too many requests") is the one error that waiting fixes. Other errors fail fast, and retrying the whole run is the orchestrator's job (Phase 5). `requests` has no default timeout, so without one a stalled connection would hang forever.

### D-12: `SOURCE_COLUMNS` is the contract with the API
**Phase 1.** Rows are built with `record[col]` for a fixed column list.
- **Why:** A renamed or dropped API field fails the load with a `KeyError` naming the field, instead of loading NULLs. New API fields are ignored until added deliberately.

### D-13: Unit tests with a hand-written fake session
**Phase 1.** Tests replace `requests.Session` and `time.sleep` using pytest's `monkeypatch`.
- **Why:** Tests are fast, deterministic and offline. A hand-written fake needs no dependency and makes the mocking explicit.
- **Alternatives:** the `responses` library, which intercepts HTTP at a lower level.
- **Not covered:** `load_records()` needs a real Postgres; an integration test fits better with CI (Phase 7).

## dbt

### D-14: `profiles.yml` in the repo, secrets via `env_var()`
**Phase 2.** `dbt/profiles.yml` is committed and reads `WAREHOUSE_*` with `env_var()`; dbt is run with `uv run --env-file ../.env`.
- **Why:** Identical on the laptop, in the Airflow container and in CI, with no secrets in git. It reuses the loader's variables.
- **Alternatives:** `~/.dbt/profiles.yml` (what `dbt init` creates), which exists only on one machine.
- **Gotcha:** dbt doesn't read `.env` itself, hence `--env-file`.

### D-15: Override `generate_schema_name`
**Phase 2.** Custom schemas are used as-is: `staging`, `marts`.
- **Why:** dbt's default prefixes them with the profile's schema (`analytics_staging`) so team members' development schemas don't collide. With a single developer, the prefix is noise, and clean names match the architecture and are simpler for the dashboard.
- **Revisit if:** multiple developers or separate dev/prod targets are added.

### D-16: Staging as views, marts as tables
**Phase 2.** Set per folder in `dbt_project.yml`.
- **Why:** Staging is light, always reflects the latest raw load, and is read only by dbt. Marts are the dashboard's interface, so the results are stored for fast reads.

### D-17: Profile the raw data before writing staging
**Phase 2.** Before writing the casts, a query (digits replaced by `9`) showed the distinct formats in each column. Its findings shaped the model:
- **`resale_price` → `numeric`, not `integer`:** 68 prices have decimals, which would have failed an integer cast.
- **`remaining_lease`:** 4 formats (`… months`, no months, singular `month`, `0 months`), parsed with regular expressions into `remaining_lease_months`.
- **`month` → `transaction_month`** as a real `date`.
- **`lease_commence_date` → `lease_commence_year`** as an integer, since it's only a year.
- **`storey_range`** split into `storey_min`/`storey_max`, keeping the original text as a label.
- **`_id` → `source_row_id`,** kept for traceability, not as a business key.

### D-18: Test severity: error for wrong output, warn for human decisions
**Phase 2.** `accepted_values` on `flat_type` fails the build; on `town` and `flat_model` it warns.
- **Why:** Marts group by `flat_type`, so an unknown value most likely means the source format changed and outputs would be wrong. New towns (Tengah's first resales are expected soon) and new flat models are legitimate, but need a human to review, e.g. to update the town → region seed in Phase 3.
- **Also:** `not_null` on every staging column, because a silently failed cast or regular expression shows up as NULL.

### D-19: Wide fact table, no dimensions yet
**Phase 2. Partly superseded by [D-26](#d-26-town-regions-as-a-seed-dim_town-driven-by-the-data)** (`dim_town` added; the fact table stays wide). `town`, `flat_type` and similar stay as columns on `fct_resale_transactions`.
- **Why:** A dimension earns its place when it has attributes beyond a name. Towns only get one with the region seed (Phase 3).
- **Revisit:** Phase 3, `dim_town`.

### D-20: `transaction_id` = source row id, for now
**Phase 2.**
- **Why:** It's unique within a load (tested), and the table is fully rebuilt every run. Hashing columns into a key isn't possible, because identical genuine sales exist.
- **Risk:** data.gov.sg may renumber rows when the dataset is republished.
- **Revisit:** Phase 3 incremental models need a stable key.

### D-21: Explicit column lists in marts
**Phase 2.** Marts never `select *` from upstream models.
- **Why:** Marts are the public interface. A new staging column only appears there by deliberate choice.

### D-22: Medians, with transaction counts
**Phase 2.** `mart_town_monthly_prices` reports `percentile_cont(0.5)` medians and `transaction_count`, at the grain town × flat_type × month. Months with no sales have no row.
- **Why:** A few very expensive sales (e.g. a Queenstown cluster above $1M in 2017) skew averages; medians are the real-estate standard. Small groups make medians noisy, so the count lets consumers filter or flag them.
- **Constraint:** Medians can't be re-aggregated. All-Singapore figures must be computed from the fact table, not by averaging this mart (motivation for MetricFlow in Phase 4).

### D-23: Grain and reconciliation tests on aggregates
**Phase 2.** Singular tests check that town + flat_type + month is unique, and that `sum(transaction_count)` equals the fact table's row count.
- **Why:** These prove the aggregation neither drops nor double-counts sales. They're singular tests because dbt's built-in generic tests check one column at a time (`dbt_utils` offers a ready-made test; packages come in Phase 3).

### D-25: Shared doc blocks, persisted to Postgres
**Phase 2.** Shared column descriptions live once in `dbt/models/_column_docs.md` and are referenced with `{{ doc() }}`; `+persist_docs` writes all descriptions into Postgres as comments.
- **Why:** Pass-through columns appear in two or three models; one definition can't drift out of sync. Persisting the descriptions puts the documentation where the data is used (psql, the dashboard, any BI tool), not only on the docs site.
- **Alternatives:** Inline descriptions repeated per model; YAML anchors (only work within one file).
- **Trade-off:** Descriptions are one indirection away from the YAML; each build also issues `COMMENT` statements (negligible here).

### D-26: Town regions as a seed; `dim_town` driven by the data
**Phase 3.** `seeds/town_regions.csv` maps 26 towns to the 5 URA planning regions (verified against URA). `dim_town` is built from the **distinct towns in the data**, left-joined to the seed, with `not_null` on `region` as an **error**. `mart_town_monthly_prices` gets `region` as a label.
- **Why a seed:** Small, hand-maintained reference data that changes rarely; as a CSV in git, every change is reviewed in a PR.
- **Why data-driven:** If `dim_town` came from the seed, a new town (e.g. Tengah) would silently get no region. Driving it from the data guarantees a row, and the NULL region fails the build with a clear fix: add one CSV row. Under D-18's rule, a missing region makes output wrong (regional views would drop sales), so it's an error, while the `town` test in staging only warns.
- **Why region is a label in the mart:** The grain stays town × flat_type × month. Regional medians can't be derived by combining town medians; they need their own aggregation from the fact table (Phase 4, MetricFlow).
- **Alternatives:** Hard-coding regions in a SQL `CASE` (unreviewable data inside logic); a source table loaded by ingestion (overkill for 26 rows).
- **Trade-off:** The fact table stays wide; `region` isn't on it. Join `dim_town` when needed.

### D-27: Macros only for repeated, nameable logic
**Phase 3.** Added `median(column_name, decimals=0)`, wrapping `round(percentile_cont(0.5) within group (order by …)::numeric, n)`, used for both medians in `mart_town_monthly_prices`.
- **Why:** The expression was repeated, has three easy-to-forget details (no `median()` in Postgres, the `double precision` result, the cast before `round`), and every future aggregate would repeat it. A named macro reads as what it means.
- **Not a macro:** the `remaining_lease` parsing. It's used once (staging), and macros used once only add a place for readers to look. It's protected by unit tests instead.
- **Rule of thumb:** write a macro when logic repeats **and** deserves a name, or differs between databases. Not to shorten one-off SQL.

### D-28: Unit-test logic with edge cases, not pass-throughs
**Phase 3.** dbt unit tests cover the `remaining_lease` formats, storey and price parsing, median behaviour, and `dim_town`'s handling of unmapped towns.
- **Why:** Data tests only check today's data. A regex change that breaks a rare format could pass them if that format is absent from a load. Unit tests feed every edge case on every run, and catch logic bugs before the model is built.
- **What's not unit-tested:** renames and pass-through columns. Lots of YAML, no protection gained.
- **Alternatives:** Relying on data tests alone; a singular test against hard-coded real rows (breaks when the data changes).
- **Trade-off:** Expected values are written by hand, so they must be checked carefully; a wrong expectation proves nothing.
- **Gotcha:** Quote exact decimals in YAML (`"2000.00"`). Unquoted, YAML reads a float and drops trailing zeros (`2000.0`), which doesn't match Postgres `numeric`'s `2000.00` in dbt's comparison.

## Workflow

### D-24: Feature branches, pull requests, merge commits
**Phase 2.** All work happens on short-lived branches and is merged through GitHub PRs using "Create a merge commit". Nothing is committed directly to `main`.
- **Why:** Learned from a merge conflict (see the 2026-10-08 entry in [changelog.md](changelog.md)), caused by committing to `main` while a branch changed the same files. PRs give a reviewable diff and, from Phase 7, CI checks. Squash merges rewrite history and cause repeat conflicts for a branch that's still in use.
