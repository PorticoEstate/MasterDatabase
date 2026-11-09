# Deploying MasterDatabase (test deployment)

MasterDatabase collects building, address and resource data from the Aktiv
kommune booking systems (one instance per municipality), adds position and
building data from the Matrikkel, and keeps everything in one PostGIS
database. This guide gets a test instance running with one configuration file
and one command.

## What runs

| Container | Role |
|---|---|
| `portico_masterdb` | PostgreSQL 18 with PostGIS. The data lives in the Docker volume `postgres_data`. |
| `portico_masterdb_backend` | Spring Boot API on port 8080. On startup it creates and migrates the database schema (Flyway). |
| `portico_masterdb_etl` | The data pipeline. Loads all kommuner on first start and syncs them every night. |

## Requirements

- Docker with Compose v2 (`docker compose version`).
- Outbound HTTPS from the server to `*.aktiv-kommune.no` and to the Matrikkel
  (`prodtest.matrikkel.no` for the test environment, `matrikkel.no` for
  production).
- Matrikkel API credentials, if you want positions and building data. Without
  them everything else still works and geocoding is skipped.
- Ports: 8080 (API) is published on all interfaces; PostgreSQL is published on
  `127.0.0.1` only.

## Quick start

```bash
git clone <repository-url> masterdatabase
cd masterdatabase
cp .env.example .env
# edit .env: set POSTGRES_PASSWORD, MASTERDB_API_KEY, MATRIKKEL_BRUKER, MATRIKKEL_PASSORD, MATRIKKEL_MILJO
# (generate a key with: openssl rand -hex 32)
docker compose up -d --build
docker compose logs -f etl
```

The first build downloads and compiles images and takes a few minutes. Then
the `etl` log shows, in this order:

1. `no vocabulary in the master yet: initial build`
2. one `henter https://<kommune>.aktiv-kommune.no/...` line per kommune
3. `geocode: ...` (or `skipped` if no credentials are set)
4. `next sync at 03:00 (in ...s)`

When step 4 appears the data is loaded. Check it with:

```bash
docker compose exec etl ./run.sh status
```

## Configuration

Everything is set in `.env` (copied from `.env.example`; never commit it).
After changing `.env`, recreate the affected container, because a restart keeps
the old values: `docker compose up -d --force-recreate etl`.

| Variable | Default | Meaning |
|---|---|---|
| `POSTGRES_PASSWORD` | none (required) | Password of the database superuser. See the note below. |
| `MASTERDB_API_KEY` | none (required) | API key for the protected backend endpoints (`/masterdb/kommune`). Clients send it in the `X-API-KEY` header. The backend does not start without it. Treat it like a password; generate one with `openssl rand -hex 32`. |
| `MATRIKKEL_BRUKER` / `MATRIKKEL_PASSORD` | empty | Matrikkel API login. If either is empty, geocoding is skipped. |
| `MATRIKKEL_MILJO` | `test` | `test` = `prodtest.matrikkel.no`, `prod` = `matrikkel.no`. Must match where your credentials are valid. |
| `KOMMUNER` | `alle` | `alle`, or a single kommune name such as `bergen`. |
| `SYNK_TID` | `03:00` | Time of the nightly sync, `HH:MM`, in `TZ`. |
| `TZ` | `Europe/Oslo` | Time zone for the schedule and the log timestamps. |
| `NORMALISER_DEMO` | `true` | The source systems are not normalised yet, so a demo normaliser is applied before loading. Keep `true` for now. |
| `AVVIK_RETENTION_DAYS` | `30` | Deviation records older than this are deleted nightly. |
| `DRY_RUN` | `false` | `true` writes the generated SQL but does not apply it. |
| `DB_PORT` | `5432` | Host port for PostgreSQL (bound to `127.0.0.1`). |

`POSTGRES_PASSWORD` is only applied when the database is created. Changing it
afterwards makes the backend and ETL fail to log in, because the existing
volume keeps the old password. Either set it back, or start from scratch with
`docker compose down -v`, which deletes all data.

## What happens automatically

- **First start:** if the code lists (`lokaletype`, `aktivitet`, `fasilitet`)
  are empty, the ETL loads all kommuner and creates those lists. If that load
  fails completely, the lists stay empty and it is retried at the next start
  and at the next nightly run.
- **Every night at `SYNK_TID`:** the ETL syncs all kommuner (new kommuner,
  buildings, resources and links are picked up), geocodes what is still
  missing, and deletes old deviation records. A failed step is logged and the
  next night runs as normal.
- **Geocoding** covers only addresses and buildings that are still incomplete,
  never the ones already resolved or set manually. Addresses the Matrikkel
  cannot resolve are tried again every night.
- Data from the source systems' `organizations` collection contains personal
  data and is never loaded.

### What is kept, and for how long

| Data | Kept |
|---|---|
| Buildings, addresses, resources and links | Updated from the source on each sync |
| `kildeuttrekk` (metadata about each fetch) | The last two fetches per source |
| `synk_avvik` (deviation records) | `AVVIK_RETENTION_DAYS` days, except the latest run per source |

## Day-to-day commands

```bash
docker compose logs -f etl                   # follow the pipeline
docker compose exec etl ./run.sh status      # row counts, geocoding status, latest fetches
docker compose exec etl ./run.sh sync        # run a sync now
docker compose exec etl ./run.sh geocode     # run geocoding now
docker compose exec etl ./run.sh prune       # delete old deviation records now
docker compose exec etl ls -l ut             # the SQL generated by the last runs
docker compose stop                          # stop, keep the data
docker compose down -v                       # stop and DELETE all data
```

Back up the database:

```bash
docker compose exec -T db pg_dump -U postgres masterdb > masterdb-backup.sql
```

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `CERTIFICATE_VERIFY_FAILED ... self-signed certificate in certificate chain` in the `etl` log | The network inspects HTTPS traffic. Add its root CA certificate to `certs/`; see [certs/README.md](certs/README.md). |
| `geocode: skipped, MATRIKKEL_BRUKER / MATRIKKEL_PASSORD are not set` | The credentials are empty in the container. Set them in `.env`, then `docker compose up -d --force-recreate etl`, then `docker compose exec etl ./run.sh geocode`. |
| Geocoding errors such as `Ugyldig XML fra KommuneService: '<!doctype html>...` | The Matrikkel endpoint answered with a web page instead of an API response. Check that `MATRIKKEL_MILJO` matches your credentials, run `docker compose exec etl python3 matrikkel_test/test_auth.py`, and look for a proxy or block page. |
| `docker compose up` stops with `Set MASTERDB_API_KEY in .env` | The key is required. Add `MASTERDB_API_KEY` to `.env`, then run `docker compose up -d` again. |
| `401` from `/masterdb/kommune` | The `X-API-KEY` header is missing or does not match `MASTERDB_API_KEY`. After changing the key in `.env`, run `docker compose up -d --force-recreate backend`. |
| `etl` container stays `Created` and never starts | It waits for a healthy backend. Run `docker compose logs backend`. |
| `etl` log repeats `waiting for the schema (Flyway V1)...` | The backend has not migrated the database yet; see the backend log. |
| One kommune fails to fetch | It is logged in `synk_avvik` and the other kommuner continue. The next nightly sync tries again. |
| Login failures after changing `POSTGRES_PASSWORD` | See the note under Configuration. |

## Known limitations

- The Aktiv kommune instances are not normalised yet, so a demo normaliser
  (`NORMALISER_DEMO=true`) rewrites their data first.
- Some of the backend's API entities are out of date with the database schema.
  The backend therefore starts with schema validation disabled
  (`spring.jpa.hibernate.ddl-auto=none`), and API endpoints that read the
  affected tables may fail. The data pipeline does not depend on the API.
- Only the `/masterdb/kommune` endpoints require an API key (`X-API-KEY`),
  and there is one shared key. The search endpoints, Swagger UI and
  `/actuator` on port 8080 are open. Do not expose the API to the internet;
  restrict access with a firewall.
