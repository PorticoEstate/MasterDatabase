# Copilot instructions for MasterDatabase

This repo is a master database that unifies building, address and resource data from the municipal "Aktiv kommune" booking instances and enriches it with the Matrikkel. See `README.md` for the overview, `etl/README.md` for the pipeline and `backend/README.md` for the API.

## What exists today
- **Database:** PostgreSQL + PostGIS. The schema is owned by the Flyway migrations in `backend/src/main/resources/db/migration/`; their comments document the tables. Change the schema with a new migration, never by editing an applied one.
- **ETL (`etl/`):** Python, standard library only. `last_inn.py` (initial build) and `synk.py` (nightly sync) only write SQL, which `run.sh` pipes to `psql`. `matrikkel_adresse.py` geocodes addresses and fetches building data from the Matrikkel.
- **Backend (`backend/`):** Spring Boot with plain SQL via `JdbcClient`. Open search under `/masterdb/search`, kommune administration under `/masterdb/kommune` (API key in `X-API-KEY`). The OpenAPI documentation is generated from the code by springdoc.
- **Run it:** `docker compose up -d --build` starts the database, backend and ETL. See `DEPLOY.md`.

## Rules to keep
- The master owns the vocabulary (`lokaletype`, `aktivitet`, `fasilitet`); the municipalities own buildings, resources and the links to the vocabulary. The sync never creates vocabulary.
- ETL steps are idempotent and never overwrite manually set values. Anything that fails is logged in `synk_avvik` instead of stopping the run; each run is recorded in `kildeuttrekk`.
- Personal data in the source (`organizations`) is never loaded.
- The Matrikkel is authoritative for building identity and position: one exact match, otherwise a deviation.
- New backend endpoints are protected by the API key by default (`config/ApiKeyFilter.java`). Document them with springdoc annotations as described in `backend/README.md`, and update the Bruno requests in `bruno/`.

## Not built yet (direction, not current state)
- Integration with the national facility register (Nasjonalt anleggsregister).
- More subsystems per resource (facility management, sensors) through `ressurslenke`; only the booking link is filled in today.
- Request routing to subsystems, field-level provenance and precedence rules, role-based access and audit.

## Conventions in this repo
- Code style: Allman braces + tabs (width 4), LF line endings.
  - `.editorconfig` (tabs=4, LF; YAML uses spaces; C# new-line-before-open-brace=all).
  - `.clang-format` (BreakBeforeBraces: Allman; UseTab: ForIndentation; Tab/IndentWidth=4).
  - `.eslintrc.json` (brace-style: allman; indent: tab) for JS/TS.
  - `.vscode/settings.json` aligns editor behavior; ESLint fixes on save for JS/TS.
  - `.gitattributes` enforces LF in git.
- YAML uses 2 spaces. The existing Python in `etl/` is the reference for its own style.
- Language: older documentation and code comments are in Norwegian; new documents are written in English.

Example (brace + tabs):
```
if (condition)
{
	handle();
}
else
{
	fallback();
}
```
