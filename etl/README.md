# Innlasting fra Aktiv kommune

To skript henter data fra Aktiv kommune og skriver SQL som fyller
masterdatabasen: `jobs/build.py` bygger databasen (kjøres én gang), og `jobs/sync.py`
holder den oppdatert etterpå (kjøres jevnlig, f.eks. fra cron). Se
kommentarene i `backend/src/main/resources/db/migration/V1__masterdatabase__skjema.sql`
for hva tabellene betyr.

## Pipelinen

| Steg | Jobb | Hva | Dokument |
|---|---|---|---|
| 1 | Flyway (backend) | Oppretter skjemaet | — |
| 2 | `jobs/build.py` | Bygger masteren, én gang | [build](docs/jobs/build.md) |
| 2 | `jobs/sync.py` | Holder den oppdatert, jevnlig | [sync](docs/jobs/sync.md) |
| 3 | `jobs/geocode.py` | Geokoding og bygningsberikelse (MatrikkelAPI) | [geocode](docs/jobs/geocode.md) |
| — | `jobs/gater.py` | Alle gater i en kommune | [gater](docs/jobs/gater.md) |
| — | `main.py`, `jobserver.py` | Daemon, nattsyklus, jobbkø, HTTP-API | [daemon](docs/jobs/daemon.md) |

Oversikt med diagram, prinsipper og filoversikt: [pipeline](docs/pipeline.md).

## Jeg vil…

| Jeg vil | Les |
|---|---|
| Starte og kjøre alt | [running](docs/running.md) |
| Forstå hva som skjer om natten | [daemon](docs/jobs/daemon.md) |
| Legge til en kommune | [adding-a-kommune](docs/reference/adding-a-kommune.md) |
| Forstå hva bygging og synk laster (og ikke laster) | [loading](docs/reference/loading.md) |
| Se hva en Aktiv kommune-instans må levere | [source-contract](docs/reference/source-contract.md) |
| Finne ut hvorfor en rad ble avvist | [avvik og kildeuttrekk](docs/reference/avvik-and-extracts.md) |
| Forstå hvordan geokodingen velger bygg og adresse | [geocoding-design](docs/reference/geocoding-design.md) |
| Prøve demo-normaliseringen | [demo_normalisering](dev/demo_normalisering/README.md) |

## Mappene

```
main.py        inngangen (ENTRYPOINT): kommandoer, daemon, sender SQL til psql
jobserver.py   jobbkø, nattlig timer og internt HTTP-API
jobs/          én fil per jobb: build.py, sync.py, geocode.py, gater.py
lib/           delt kode: load.py, matrikkel.py, kommuner.py, source.py, sqlgen.py
sql/           spørringene som kjøres med psql
docs/          dokumentasjonen: pipeline.md, running.md, jobs/, reference/
dev/           bare for utvikling: demo_normalisering/, check_matrikkel_auth.py
ut/            generert SQL og mellomfiler (i .gitignore)
```

Jobbene kjøres som moduler fra `etl/`, f.eks. `cd etl && python3 -m jobs.sync ...`.
