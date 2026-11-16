# MasterDatabase

A master database that unifies building, address and resource data from several
similar local booking/facility databases (the "Aktiv kommune" instances, one per
municipality) and enriches it with authoritative registries: the Matrikkel today,
the national facility register later.

## Status

- **Working:** the data pipeline. It loads all configured kommuner, geocodes
  addresses and fetches building data from the Matrikkel, and syncs every night.
- **Schema:** owned by Flyway migrations in the backend.
- **Early:** the Spring Boot API is minimal (one resource endpoint,
  `/api/ressurser`) and parts of it are out of date with the schema. There is no
  written API contract at the moment.
- **Temporary:** the source systems are not normalised yet, so a demo normaliser
  rewrites their data before loading (`etl/demo_normalisering/`).
- **`ressurslenke`:** links one resource to several subsystems (booking, facility
  management, sensors), one row with the resource's URL per system. The ETL fills in
  the booking link; the search view reads `booking_url` from it.

## Run it

```bash
cp .env.example .env     # set POSTGRES_PASSWORD and, for geocoding, the Matrikkel login
docker compose up -d --build
docker compose logs -f etl
```

This starts PostGIS, the backend and the `etl` container. On first start `etl`
loads everything; after that it syncs at 03:00 every night. See
[DEPLOY.md](DEPLOY.md) for configuration, operations and troubleshooting.
Behind a corporate proxy, also see [DEVELOPMENT_WSL2.md](DEVELOPMENT_WSL2.md) and
[certs/README.md](certs/README.md).

## How it works

```
Aktiv kommune instances --last_inn.py / synk.py--> PostGIS <--matrikkel_adresse.py-- Matrikkel
                                                      ^
                                    Spring Boot backend (Flyway owns the schema)
```

- The ETL scripts only write SQL, which `etl/run.sh` pipes to `psql`. They are
  idempotent, and anything that fails is logged in `synk_avvik` instead of
  stopping the run.
- The master owns the vocabulary (`lokaletype`, `aktivitet`, `fasilitet`); the
  municipalities own the links from resources to it.
- Personal data in the source (`organizations`) is never loaded.

## Where things are

| Path | Contents |
|---|---|
| [etl/](etl/README.md) | The pipeline: `last_inn.py`, `synk.py`, `matrikkel_adresse.py`, `run.sh`, and the demo normaliser |
| [backend/](backend/) | Spring Boot application. The Flyway migration in `src/main/resources/db/migration/` is the schema, and its comments document the tables |
| [bruno/](bruno/) | Bruno request collection for trying the local API |
| [certs/](certs/README.md) | Optional extra CA certificates for networks that inspect TLS |
| [DEPLOY.md](DEPLOY.md) | Deployment guide |
| [DEVELOPMENT_WSL2.md](DEVELOPMENT_WSL2.md) | Development setup on WSL2 behind a corporate proxy |


Most of the older documentation is in Norwegian; new documents are written in
English. - Will be changed if time permits

## Code style

Allman braces, real tabs (width 4) and LF line endings, enforced by
`.editorconfig`, `.clang-format`, `.eslintrc.json` and `.gitattributes`. YAML uses
2 spaces. The existing Python in `etl/` is the reference for its own style.
