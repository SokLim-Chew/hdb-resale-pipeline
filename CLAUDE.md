# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## How to work with me

I'm learning data engineering and building this project for my portfolio.

- Explain the concepts and design choices before writing code, including why this approach and what the alternatives are.
- Keep steps small, one piece at a time, so I can follow and review each change.
- Let me run commands myself so I learn them. Give me the command and explain what it does, rather than running it for me.

## Project state

Portfolio ELT project: Singapore HDB resale transactions (data.gov.sg) → Postgres → dbt → Streamlit, orchestrated by Airflow. Follows the roadmap phases in `README.md`.

- **Phase 1 (ingestion) is done:** `ingestion/load_hdb_resale.py` loads the full dataset into `raw.hdb_resale`, with unit tests in `tests/`.
- **Phase 2 (dbt) is in progress:** `dbt/` has the `raw` source, `stg_hdb_resale`, `fct_resale_transactions` and `mart_town_monthly_prices`, with tests, full descriptions (shared ones as doc blocks in `dbt/models/_column_docs.md`) and `persist_docs`. Phase 3 is next.
- `dags/` and `dashboard/` don't exist yet.

Update this section as each phase lands.

## Project documentation

`docs/` holds the project's living documentation. Update it as part of each step, not afterwards:

- `docs/commands.md`: add every new command with a one-line explanation; move **(planned)** commands into the main sections once they're confirmed working.
- `docs/architecture.md`: update when models, schemas, components or configuration change.
- `docs/decisions.md`: add a D-xx entry for each significant design choice (why, alternatives, trade-off). Never rewrite old entries; mark them superseded.
- `docs/changelog.md`: add dated entries for what changed, findings and incidents; keep the status table current.

The README's "What I learned / design decisions" section is written by the user in their own words; don't edit it.

## Commands

```bash
cp .env.example .env                     # required; compose and the loader read WAREHOUSE_* from it
docker compose up -d                     # warehouse only (Postgres 17, container hdb_warehouse)
docker compose --profile airflow up -d   # + Airflow 3 standalone, UI at http://localhost:8080 (no login)
docker compose down                      # stop, keep data
docker compose down -v                   # stop AND wipe warehouse + Airflow metadata volumes

uv sync                                  # create/update .venv from uv.lock
uv run python ingestion/load_hdb_resale.py
uv run pytest                            # all tests
uv run pytest tests/test_load_hdb_resale.py::test_retries_after_rate_limit   # single test

docker exec -it hdb_warehouse psql -U hdb -d hdb_warehouse -c 'SELECT count(*), max(_loaded_at) FROM raw.hdb_resale'
```

dbt runs from inside `dbt/`. It doesn't read `.env` itself, and `dbt/profiles.yml` takes all connection settings from the `WAREHOUSE_*` variables:

```bash
cd dbt
uv run --env-file ../.env dbt debug                         # check config + connection
uv run --env-file ../.env dbt build                         # all models + tests
uv run --env-file ../.env dbt build --select stg_hdb_resale # one model + its tests
```

Full command reference, including planned ones per phase: `docs/commands.md`.

## Gotchas

- **Python is pinned to 3.12** via `.python-version`, for dbt compatibility. Don't let uv pick a newer interpreter.
- **Postgres only applies `WAREHOUSE_USER`/`WAREHOUSE_PASSWORD` the first time it starts on an empty volume.** Changing them in `.env` afterwards causes "password authentication failed". Fix it with `docker compose down -v` (wipes data), then reload.
- **Avoid `$` in `.env` values.** Compose and python-dotenv interpolate `$` differently, so the container and the loader can end up with different passwords.

## Architecture

- **Two separate Postgres instances on purpose.** `warehouse` holds the analytics data (raw → staging → marts schemas). `airflow-db` holds only Airflow metadata. Never point dbt or ingestion at `airflow-db`.
- **ELT layering:** ingestion loads API rows untransformed into `raw.hdb_resale`, with every source column as `TEXT` plus a `_loaded_at` column. All casting and cleaning belong in dbt (`staging` → `marts`), not in Python.
- **Ingestion is an idempotent full refresh.**
  - It pages through data.gov.sg `datastore_search`, advancing the offset by rows received.
  - It retries HTTP 429 with exponential backoff.
  - It fails if the row count doesn't match the API's `total`.
  - It downloads everything into memory first, then runs `TRUNCATE` + `COPY` in one transaction, keeping the table lock short and making a failed run roll back to the previous load.
  - `SOURCE_COLUMNS` is the contract with the API: a renamed or dropped field fails the load with a `KeyError`.
  - Incremental loading is deliberately left for dbt in Phase 3.
- **Tests** mock `requests.Session` and `time.sleep` with pytest's `monkeypatch`, so they need no network or database. `pyproject.toml` puts `ingestion/` on `pythonpath`, so tests `import load_hdb_resale` directly.
- **Host vs container connections:** from the host, connect to the warehouse at `localhost:${WAREHOUSE_PORT}`. Inside the Airflow container, set `WAREHOUSE_HOST=warehouse` (the loader defaults to `localhost`), or use the Airflow connection `conn_id="warehouse"` (injected via `AIRFLOW_CONN_WAREHOUSE`).
- **Airflow container mounts** `./dags`, `./ingestion` and `./dbt` at `/opt/airflow/{dags,ingestion,dbt}`, so DAGs should reference those container paths. The planned DAG runs ingest → `dbt build` on a monthly schedule.
- Gitignored runtime output that should never be committed: `.env`, `dbt/target/`, `dbt/logs/`, `dbt/dbt_packages/`, `logs/`, `data/`, `*.csv` and `*.parquet`.
