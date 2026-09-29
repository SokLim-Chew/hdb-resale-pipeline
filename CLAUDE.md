# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## How to work with me

I'm learning data engineering and building this project for my portfolio.

- Explain the concepts and design choices before writing code, including why this approach and what the alternatives are.
- Keep steps small, one piece at a time, so I can follow and review each change.
- Let me run commands myself so I learn them. Give me the command and explain what it does, rather than running it for me.

## Project state

Portfolio ELT project: Singapore HDB resale transactions (data.gov.sg) → Postgres → dbt → Streamlit, orchestrated by Airflow. Currently a scaffold. Only `docker-compose.yml`, `.env.example` and `README.md` exist. The directories in the README's "Project structure" (`ingestion/`, `dbt/`, `dags/`, `dashboard/`, `tests/`, `docs/`) and `pyproject.toml` still need to be created, following the roadmap phases in `README.md`. Update this file as each phase lands.

## Commands

```bash
cp .env.example .env                     # required; compose reads WAREHOUSE_* from it
docker compose up -d                     # warehouse only (Postgres 17, container hdb_warehouse)
docker compose --profile airflow up -d   # + Airflow 3 standalone, UI at http://localhost:8080 (no login)
docker compose down                      # stop, keep data
docker compose down -v                   # stop AND wipe warehouse + Airflow metadata volumes
```

Planned (per README, once the code exists). Python is managed with uv:

```bash
uv run python ingestion/load_hdb_resale.py
cd dbt && uv run dbt build
uv run pytest                            # tests/ covers ingestion code
mf query ...                             # MetricFlow metrics (Phase 4)
```

## Architecture

- **Two separate Postgres instances on purpose.** `warehouse` holds the analytics data (raw → staging → marts schemas). `airflow-db` holds only Airflow metadata. Never point dbt or ingestion at `airflow-db`.
- **ELT layering:** Python ingestion loads API rows untransformed into `raw.hdb_resale`, and all cleaning happens in dbt (`staging` → `marts`). Ingestion must be idempotent and safe to re-run, and must paginate the data.gov.sg `datastore_search` endpoint. The resource id comes from `HDB_RESALE_RESOURCE_ID` in `.env`.
- **Host vs container connections:** from the host, connect to the warehouse at `localhost:${WAREHOUSE_PORT}` (default 5432; set 5433 if a local Postgres is running). Inside the Airflow container, use host `warehouse:5432`, or the Airflow connection `conn_id="warehouse"` (injected via `AIRFLOW_CONN_WAREHOUSE`).
- **Airflow container mounts** `./dags`, `./ingestion` and `./dbt` at `/opt/airflow/{dags,ingestion,dbt}`, so DAGs should reference those container paths. The planned DAG runs ingest → `dbt build` on a monthly schedule.
- Gitignored runtime output that should never be committed: `.env`, `dbt/target/`, `dbt/logs/`, `dbt/dbt_packages/`, `logs/`, `data/`, `*.csv` and `*.parquet`.
