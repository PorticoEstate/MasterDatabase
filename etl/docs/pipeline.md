# Pipelinen

Fra tomt skjema til populert database, i tre steg. Kommandoene for å kjøre dem
står i [running](running.md); hver jobb har sitt eget dokument.

```
┌───────────────────────────────────────────────────────────────────────┐
│ STEG 1 — SKJEMA                                                       │
│ backend/src/main/resources/db/migration/V*.sql (Flyway)               │
│                                                                       │
│ Oppretter alle tabeller i en tom database: kommune, bygning, adresse, │
│ ressurs, aktivitet/fasilitet/lokaletype,                              │
│ gate/matrikkelinfo, synk_avvik/kildeuttrekk. Kjøres av backend-       │
│ containeren ved oppstart; ingenting å kjøre for hånd.                 │
└───────────────────────────────────────────────────┬───────────────────┘
                                                      ▼
┌───────────────────────────────────────────────────────────────────────┐
│ STEG 2 — INNLASTING                                                   │
│ etl/jobs/build.py  (bygging, én gang)  ←  Aktiv kommune API           │
│ etl/jobs/sync.py   (jevnlig, cron)     ←  Aktiv kommune API           │
│                                                                       │
│ Henter kommune, bygg, adresser (uten koordinater), ressurser og       │
│ koblingene ressurs → lokaletype/aktivitet/fasilitet, på id.           │
│ jobs/build.py oppretter i tillegg kodeverkene fra instansene;         │
│ jobs/sync.py skriver dem aldri, og logger avvik fra masteren.         │
│ Laster ALDRI `organizations` (persondata).                            │
└───────────────────────────────────────────────────┬───────────────────┘
                                                      ▼
┌───────────────────────────────────────────────────────────────────────┐
│ STEG 3 — GEOKODING + BYGNINGSBERIKELSE                                │
│ etl/jobs/geocode.py  ←  MatrikkelAPI (SOAP, krever innlogging)        │
│                                                                       │
│ a) Løser adressene — søker *innenfor riktig kommune* (kjent fra       │
│    steg 2) i Matrikkelen. Eneste geokodingskilde.                     │
│ b) Henter bygningsnr/bygningstype/bra_m2/antall_etasjer for ALLE      │
│    bygg som mangler det, og bekrefter kildens bygningsnr (fra         │
│    cadastral_references, foreløpig tynt fylt) mot Matrikkelen.        │
│ Prinsipp: ett eksakt treff, ellers avvik.                             │
└───────────────────────────────────────────────────┬───────────────────┘
                                                      ▼
                                          ╔═══════════════════╗
                                          ║   FERDIG: masterdb ║
                                          ╚═══════════════════╝
```

| Steg | Jobb | Dokument | Detaljer |
|---|---|---|---|
| 1 Skjema | Flyway i backend | — | `db/schema_kjerne_dokumentasjon.md` |
| 2 Innlasting | `jobs/build.py`, `jobs/sync.py` | [build](jobs/build.md), [sync](jobs/sync.md) | [lasting](reference/loading.md), [kildekontrakt](reference/source-contract.md), [legge til kommune](reference/adding-a-kommune.md) |
| 3 Geokoding | `jobs/geocode.py` | [geocode](jobs/geocode.md) | [design](reference/geocoding-design.md) |
| Utenfor kjeden | `jobs/gater.py` | [gater](jobs/gater.md) | |
| Orkestrering | `main.py`, `jobserver.py` | [daemon](jobs/daemon.md) | |

## Prinsipper

- **ETL-skriptene rører aldri databasen.** De skriver SQL til stdout, som sendes
  til `psql` i et eget steg, så endringen kan gjennomgås først.
- **Alle tre stegene er trygge å kjøre på nytt.** De endrer kun det som fortsatt
  mangler/er ukjent, aldri manuelt satte verdier.
- **Feil stopper aldri en kjøring.** Alt som feiler (ugyldig verdi, duplikat,
  API-feil, manglende treff) logges i `synk_avvik` sammen med selve posten som
  feilet. Hver kjøring registreres i `kildeuttrekk` (metadata, ikke selve
  svaret). Se [avvik og kildeuttrekk](reference/avvik-and-extracts.md).
- **Personvern:** kildens `organizations`-samling inneholder persondata og lastes
  aldri.
- **Masteren eier vokabularet, kommunen eier koblingene.** Se
  [lasting](reference/loading.md).

## Demo-normalisering (valgfritt, før steg 2)

Aktiv kommune-instansene er ennå ikke normalisert.
[`etl/dev/demo_normalisering/`](../dev/demo_normalisering/README.md) viser hvordan
masterdatabasen kan bli når de er det: den gjør en rå `searchdataall` om til det
en normalisert instans ville levere, og `jobs/build.py` laster resultatet med
`--fra-fil`. Hele mappen kan slettes når instansene er normalisert; verken
`jobs/build.py` eller `jobs/sync.py` trenger endring.

## Mappestruktur (`etl/`)

```
main.py        inngangen (ENTRYPOINT): kommandoer, daemon, sender SQL til psql
jobserver.py   jobbkø, nattlig timer og internt HTTP-API
jobs/          én fil per jobb: build.py, sync.py, geocode.py, gater.py
lib/           delt kode: load.py, matrikkel.py, kommuner.py, source.py, sqlgen.py
sql/           spørringene som kjøres med psql
docs/          denne dokumentasjonen
dev/           bare for utvikling: demo_normalisering/, check_matrikkel_auth.py
ut/            generert SQL og mellomfiler (i .gitignore)
```

Jobbene kjøres som moduler fra `etl/`, f.eks. `cd etl && python3 -m jobs.sync ...`.

## Filoversikt

| Fil | Rolle |
|---|---|
| `backend/src/main/resources/db/migration/V*.sql` | Skjemaet (steg 1), kjøres av Flyway i backend |
| `db/schema_kjerne_dokumentasjon.md` | Hva hver tabell/kolonne betyr og hvorfor |
| `etl/main.py`, `etl/jobserver.py` | Daemonen og kommandoene, se [daemon](jobs/daemon.md) |
| `etl/jobs/build.py`, `etl/jobs/sync.py` | Steg 2, se [build](jobs/build.md) og [sync](jobs/sync.md) |
| `etl/jobs/geocode.py` | Steg 3, se [geocode](jobs/geocode.md) |
| `etl/jobs/gater.py` | Alle gater for en kommune, se [gater](jobs/gater.md) |
| `etl/lib/load.py` | Lastingen av én kommune, brukt av bygging og synk |
| `etl/lib/matrikkel.py` | SOAP-klient mot MatrikkelAPI, brukt av `geocode.py` og `gater.py` |
| `etl/lib/kommuner.py` | `KOMMUNER`, `les_kommuner` |
| `etl/lib/source.py` | `rens`, `hent_json`, `rens_post`, `som_heltall` |
| `etl/lib/sqlgen.py` | `q`, `logg`, `i_blokk`, `ressurslenke_sql`, `logg_matrikkel` |
| `etl/sql/geocode_query.sql` | Spørringen som lager input til geokodingen |
| `etl/sql/kommuner_query.sql` | Kommunelisten for synk |
| `etl/sql/status.sql` | Oversikten som `main.py status` viser |
| `etl/dev/demo_normalisering/` | DEMO: normaliserer rå `searchdataall`. Slettes ved normalisering |
| `etl/dev/check_matrikkel_auth.py` | Verifiserer at Matrikkel-innlogging virker, før geokoding |
