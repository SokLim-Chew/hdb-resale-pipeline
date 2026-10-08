# Changelog

Progress, changes and incidents, newest first. Dates are working-session dates. Design reasoning lives in [decisions.md](decisions.md) and is referenced here by id (D-xx).

## Status

| Phase | Status |
|---|---|
| 1. Ingestion | ✅ Done |
| 2. Transformation (dbt) | 🚧 Nearly done: staging, both marts and docs built; descriptions + `persist_docs` awaiting a build |
| 3. Advanced dbt | Not started |
| 4. Semantic layer | Not started |
| 5. Orchestration | Not started (Compose services already defined) |
| 6. Serving | Not started |
| 7. Quality & CI | Not started |

---

## 2026-10-08

### Added
- `fct_resale_transactions` (marts, table): one row per sale, with an explicit column list and `transaction_year`, `flat_age_years` and `remaining_lease_years`. Built and checked: 241,597 rows (D-19, D-20, D-21).
- `mart_town_monthly_prices` (marts, table): median price and price per sqm, plus `transaction_count`, per town × flat_type × month, with grain-uniqueness and reconciliation tests (D-22, D-23). Full `dbt build` passes: 3 models, all tests green.
- `docs/`: commands, architecture, decisions and this changelog.
- dbt docs site (`dbt docs generate` / `serve --port 8081`) working, with lineage graph.
- Descriptions for every model, source and column; shared ones as doc blocks in `dbt/models/_column_docs.md`; `+persist_docs` writes them to Postgres comments (D-25). New `not_null` test on `stg_hdb_resale._loaded_at`.

### Changed
- `dbt_project.yml`: `marts` folder → schema `marts`, materialized as tables (D-16).

### Findings
- **Flats resold 1–2 years after lease start.** `flat_age_years` has a minimum of 1, despite the 5-year Minimum Occupation Period. 57 sales are aged 1–2, all in Queenstown with leases starting in 2015, sold from 2017 at premium prices. The separate `remaining_lease` field agrees (about 96.7 years left), so the data is genuine, not a parsing bug. It looks like a single development with special conditions; the street/block query in [commands.md](commands.md#useful-queries) identifies it. No model change needed. Ages 3–4 come from comparing calendar years only.

### Incidents
- **Merge conflict merging `main` into the feature branch** (`CLAUDE.md`, `uv.lock`). Cause: commits made directly on `main` while the branch changed the same files. Resolved `CLAUDE.md` by hand and regenerated `uv.lock` (`git checkout --theirs uv.lock` + `uv lock`). Committing failed until the merge was finished. Merged through a PR, then started a fresh `phase2-marts` branch. Led to D-24.

## 2026-10-07

### Added
- `stg_hdb_resale` (staging, view), shaped by profiling the raw data first (D-17). Verified: 241,597 rows, 0 unparsed leases, lease range 472–1,173 months, months 2017-01 to 2026-09, price per sqm about $2,090–$16,150.
- Staging tests: `not_null` on all columns, `unique` on `source_row_id`, `accepted_values` on `town`/`flat_type`/`flat_model` with error/warn severities (D-18), and the singular test `assert_stg_hdb_resale_values_in_range`.

## 2026-10-06

### Added
- Phase 2 started. `uv add dbt-postgres`.
- `dbt/dbt_project.yml` and `dbt/profiles.yml` (connection via `env_var()`, D-14). `dbt debug` passes.
- `macros/generate_schema_name.sql` (D-15), `models/staging/_sources.yml` declaring `raw.hdb_resale`, staging folder → schema `staging`, as views (D-16).

### Changed
- `CLAUDE.md` restored after being reverted to its first version, and updated for Phase 2.

## 2026-10-01

### Added
- Phase 1 completed: full-refresh load with `TRUNCATE` + `COPY` in one transaction (D-06, D-07, D-08). Verified idempotent: the row count is unchanged after a re-run.
- `tests/test_load_hdb_resale.py`: 5 unit tests (pagination, completeness check, 429 retry, giving up after max retries, no retry on other errors) with a fake session (D-13). `uv add --dev pytest`; pytest config in `pyproject.toml`.
- Phase 1 design notes in the README.

### Changed
- `CLAUDE.md`: project state, working commands, gotchas.

## 2026-09-30

### Added
- Pagination loop with retry and completeness check (D-10, D-11). Fetched the full dataset (241,597 rows).

### Incidents
- **`password authentication failed for user "hdb"` on first run.** `lsof` showed only Docker listening on 5432, ruling out a local Postgres. Cause: the warehouse volume had been initialized with an earlier password, and Postgres applies `.env` credentials only on first start. Fixed with `docker compose down -v` + `up -d`, which was safe because no data had been loaded yet. Recorded as a gotcha in `CLAUDE.md`.

## 2026-09-29

### Added
- Python project: `uv init --bare`, dependencies `requests`, `psycopg[binary]`, `python-dotenv`.
- `ingestion/load_hdb_resale.py`, first part: connection from `.env`, `raw` schema and `raw.hdb_resale` table (D-05, D-09).
- "How to work with me" section in `CLAUDE.md`.

### Changed
- Python pinned to 3.12 with `uv python pin` after uv picked the system's 3.14 (D-04).

## 2026-09-28

### Added
- `CLAUDE.md` (via `/init`).

### Changed
- `docker-compose.yml` comments aligned with the README roadmap: warehouse only for Phases 1–4, Airflow from Phase 5.
