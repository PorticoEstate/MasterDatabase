# Innlasting fra Aktiv kommune

To skript henter data fra Aktiv kommune og skriver SQL som fyller
masterdatabasen: `jobs/build.py` bygger databasen (kjøres én gang), og `jobs/sync.py`
holder den oppdatert etterpå (kjøres jevnlig, f.eks. fra cron). Se
`db/schema_kjerne_dokumentasjon.md` for hva tabellene betyr.

## Oversikt over hele pipelinen

Fra tomt skjema til populert database, i tre steg:

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
│ Se "Bygging og synk" og "Kildekontrakt" under.                        │
│ Laster ALDRI `organizations` (persondata).                            │
└───────────────────────────────────────────────────┬───────────────────┘
                                                      ▼
┌───────────────────────────────────────────────────────────────────────┐
│ STEG 3 — GEOKODING + BYGNINGSBERIKELSE                                │
│ etl/jobs/geocode.py  ←  MatrikkelAPI (SOAP, krever innlogging)        │
│                                                                       │
│ a) Løser adressene — søker *innenfor riktig kommune* (kjent fra       │
│    steg 2) i Matrikkelen. Eneste geokodingskilde; se begrunnelsen i   │
│    seksjonen under for hvorfor Kartverkets åpne Adresse-API ikke      │
│    lenger brukes som et eget forsteg.                                 │
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

**Demo-normalisering (valgfritt, før steg 2).** Aktiv kommune-instansene er ennå
ikke normalisert. `etl/dev/demo_normalisering/normaliser.py` viser hvordan masterdatabasen kan
bli når de er det: det gjør en rå `searchdataall` om til det en normalisert
instans ville levere, og `jobs/build.py` laster resultatet med `--fra-fil`. Hele
mappen kan slettes når instansene er normalisert; verken `jobs/build.py` eller
`jobs/sync.py` trenger endring. Se "Demo-normalisering" under.

**Tverrgående, på hvert steg:** alt som feiler (ugyldig verdi, duplikat,
API-feil, manglende treff) logges i `synk_avvik` sammen med selve posten som
feilet — én dårlig rad stopper aldri hele kjøringen. Hver kjøring registreres
i `kildeuttrekk` (metadata, ikke selve svaret). Se "Avvik og kildeuttrekk"
under.

Alle tre stegene er trygge å kjøre på nytt — de endrer kun det som fortsatt
mangler/er ukjent, aldri manuelt satte verdier. De eksakte kommandoene for
hvert steg står i seksjonene under, i samme rekkefølge.

**Mappestruktur** (`etl/`):

```
main.py        inngangen (ENTRYPOINT): kommandoer, daemon, sender SQL til psql
jobserver.py   jobbkø, nattlig timer og internt HTTP-API
jobs/          én fil per jobb: build.py, sync.py, geocode.py, gater.py
lib/           delt kode: load.py, matrikkel.py, kommuner.py, source.py, sqlgen.py
sql/           spørringene som kjøres med psql
dev/           bare for utvikling: demo_normalisering/, check_matrikkel_auth.py
ut/            generert SQL og mellomfiler (i .gitignore)
```

Jobbene kjøres som moduler fra `etl/`, f.eks. `cd etl && python3 -m jobs.sync ...`.

**Filoversikt:**

| Fil | Rolle |
|---|---|
| `backend/src/main/resources/db/migration/V*.sql` | Skjemaet (steg 1), kjøres av Flyway i backend |
| `db/schema_kjerne_dokumentasjon.md` | Hva hver tabell/kolonne betyr og hvorfor |
| `etl/main.py` | Inngangen til etl-containeren (`ENTRYPOINT`): kommandoene `daemon`, `build`, `sync`, `geocode`, `gater`, `prune` og `status`. Kjører jobbene som moduler og sender SQL-en til `psql` |
| `etl/jobserver.py` | Jobbkø, nattlig timer og det interne HTTP-API-et som backend bruker (se `main.py daemon`) |
| `etl/jobs/build.py` | Steg 2, bygging: oppretter kodeverkene og laster alt annet. Kjøres én gang |
| `etl/jobs/sync.py` | Steg 2, jevnlig synkronisering: som `jobs/build.py`, men skriver aldri kodeverkene |
| `etl/lib/` | Kode delt av skriptene: `load.py` (lastingen av én kommune, brukt av bygging og synk), `matrikkel.py` (SOAP-klient mot MatrikkelAPI, brukt av `geocode.py` og `gater.py`), `kommuner.py` (`KOMMUNER`, `les_kommuner`), `source.py` (`rens`, `hent_json`, `rens_post`, `som_heltall`) og `sqlgen.py` (`q`, `logg`, `i_blokk`, `ressurslenke_sql`, `logg_matrikkel`) |
| `etl/sql/geocode_query.sql`, `etl/sql/status.sql` | Spørringen som lager input til geokodingen, og oversikten som `main.py status` viser |
| `etl/sql/kommuner_query.sql` | Henter listen over kommuner som skal synkroniseres fra databasen (se "Hvilke kommuner som synkroniseres") |
| `etl/dev/demo_normalisering/normaliser.py` | DEMO: lager normalisert JSON fra rå `searchdataall`. Slettes ved normalisering |
| `etl/dev/demo_normalisering/{lokaletype,fasilitet,activity}_mapping/` | DEMO: vokabular (`venue_types.json`, `facilities.json`, `activities.json`) og mapping (`mapping.json`) som `normaliser.py` leser |
| `etl/jobs/geocode.py` | Steg 3. Kjøres etter bygging og etter hver synk, så nye bygg får posisjon |
| `etl/jobs/gater.py` | Henter ALLE gater for en kommune fra Matrikkelen inn i `gate`. Kjøres av daemonen én gang etter første bygg, og ellers for hånd med `main.py gater` |
| `etl/dev/check_matrikkel_auth.py` | Verifiserer at Matrikkel-innlogging virker, før man kjører steg 3 |

## Forutsetning: HTTPS må virke fra WSL

Skriptet henter data over internett. På en Capgemini-maskin krever det at
Capgeminis rotsertifikat er installert i WSL (se prosjektets minne
`wsl-ca-sertifikat-lost` eller spør Claude). Test at det virker:

```bash
curl -sS -o /dev/null -w "%{http_code}\n" https://bergen.aktiv-kommune.no/bookingfrontend/searchdataall
```

Skal svare `200`. Svarer den med en sertifikatfeil, må sertifikatet installeres først.

## Hvordan kjøre det

Skriptet bruker bare Pythons innebygde bibliotek - ingen `pip install` er
nødvendig. Det gjør ingenting mot databasen selv; det skriver SQL-tekst til
standard-ut, som du deretter sender til Postgres i et eget steg. Det gir deg
mulighet til å se hva som skal skje før noe endres.

**Bygging, én kommune for å teste:**

```bash
(cd etl && python3 -m jobs.build bergen) > etl/ut/bergen.sql
docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/bergen.sql
```

**Bygging, alle 12 kommunene:**

```bash
(cd etl && python3 -m jobs.build alle) > etl/ut/alle.sql
docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/alle.sql
```

**Synk etter bygging** (samme måte å sende SQL-en til Postgres, men synk trenger kommunelisten fra databasen først, se «Hvilke kommuner som synkroniseres»):

```bash
psql -tA -F'|' -f etl/sql/kommuner_query.sql > etl/ut/kommuner.txt
(cd etl && python3 -m jobs.sync alle --kommuner-fil ut/kommuner.txt) > etl/ut/synk.sql
docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/synk.sql
```

Den planlagte kjøringen gjøres av etl-containeren (`etl/main.py`, hver natt kl. 03:00; se `DEPLOY.md`). Den kjører
tre separate jobber etter hverandre: `nightly-load` (synk), `geocode` (`jobs/geocode.py`, steg 3, så nye bygg får
posisjon) og `prune`. Synk-jobben geokoder ikke selv: trigges `sync` alene (`main.py sync` eller jobbserveren),
kommer ingen geokoding etter, og `geocode` må trigges for seg.

Skriptene kan også lese `<mappe>/<kommune>.json` i stedet for å hente fra nettet,
med `--fra-fil <mappe>`. Det brukes av demoen (under), og er nyttig for å kjøre
samme data på nytt uten nettverk. Kildeuttrekket registreres da med
`file:///...` som endepunkt og uten HTTP-status.

`etl/ut/` er generert output og ligger i `.gitignore` - filene der er en
ferskvare, ikke noe som skal committes.

## Databasen må finnes og ha skjemaet fra før

Databasen `masterdb` opprettes av db-containeren, og backend-containeren legger
på skjemaet med Flyway (`backend/src/main/resources/db/migration/`) hver gang
den starter. Start stacken og vent til backend er `healthy` (`docker compose ps`)
før du kjører skriptene.

## Bygging og synk

Flyttet: se [docs/jobs/build.md](docs/jobs/build.md), [docs/jobs/sync.md](docs/jobs/sync.md),
[docs/reference/loading.md](docs/reference/loading.md) (felles for begge),
[docs/reference/adding-a-kommune.md](docs/reference/adding-a-kommune.md) (kommunelisten, `--kommuner-fil`/`--fra-fil`, legge til en kommune).

## Avvik og kildeuttrekk

Flyttet: se [docs/reference/avvik-and-extracts.md](docs/reference/avvik-and-extracts.md).

## Kildekontrakt: hva en normalisert instans må levere

Flyttet: se [docs/reference/source-contract.md](docs/reference/source-contract.md).

## Demo-normalisering

Flyttet: se [dev/demo_normalisering/README.md](dev/demo_normalisering/README.md).

## Geokoding og bygningsberikelse (MatrikkelAPI)

Flyttet: se [docs/jobs/geocode.md](docs/jobs/geocode.md) (bruk og oppførsel) og
[docs/reference/geocoding-design.md](docs/reference/geocoding-design.md) (begrunnelser og oppslagskjeden).

## Gater for hele kommunen (`gate`)

Flyttet: se [docs/jobs/gater.md](docs/jobs/gater.md).

## Kjent forenkling

Flyttet: se [docs/reference/loading.md](docs/reference/loading.md#kjent-forenkling).
