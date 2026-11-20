# `main.py` og `jobserver.py` — daemonen

`main.py` er inngangen til etl-containeren (`ENTRYPOINT`). Uten argument
kjører den `daemon`; de andre kommandoene kjører én jobb direkte og avslutter,
uten jobbserveren. Python-skriptene skriver bare SQL; `main.py` sender den til
`psql`. SQL-en ligger i `$UT` (volumet `etl_ut`, `/app/ut`), så siste kjøring
kan gjennomgås etterpå.

## Kommandoer

```bash
docker compose exec etl python3 main.py status    # radtall, geokodingsstatus, siste uttrekk (skriver ikke)
docker compose exec etl python3 main.py sync      # én jobb nå
docker compose exec etl python3 main.py <build|sync|geocode|gater [kommunenr...]|prune>
```

| Kommando | Gjør | Dokument |
|---|---|---|
| `daemon` (standard) | Starter jobbserveren, kjører oppstartssekvensen, så nattsyklusen | under |
| `build` | `jobs/build.py` og `psql` | [build](build.md) |
| `sync` | `jobs/sync.py` og `psql` | [sync](sync.md) |
| `geocode` | Spørring, `jobs/geocode.py`, `psql` | [geocode](geocode.md) |
| `gater [kommunenr...]` | `jobs/gater.py` og `psql`. Uten argument: alle kommuner | [gater](gater.md) |
| `prune` | Sletter gamle `synk_avvik`-rader | [avvik](../reference/avvik-and-extracts.md) |
| `refresh` | Bare jobbtype i jobbserveren, ikke en `main.py`-kommando ennå | [under](#refresh-av-søkeviewet) |
| `status` | Kjører `sql/status.sql` (skriver ikke) | |

## Innstillinger (miljøvariabler)

Alle er valgfrie, unntatt `PG*`-tilkoblingen og, for geokoding, Matrikkel-innloggingen.

| Variabel | Standard | Betydning |
|---|---|---|
| `KOMMUNER` | `alle` | `alle` eller én slug, f.eks. `bergen`. For synk betyr `alle` alle kommuner registrert i databasen ([sync](sync.md#hvilke-kommuner-som-synkroniseres)) |
| `SYNK_TID` | `03:00` | Tidspunkt for nattsyklusen, i `TZ`. Må være `HH:MM` |
| `NORMALISER_DEMO` | `true` | Kjør [demo-normaliseringen](../../dev/demo_normalisering/README.md) før lasting |
| `DRY_RUN` | `false` | Skriv SQL, men ikke anvend den (heller ikke `prune`) |
| `AVVIK_RETENTION_DAYS` | `30` | `synk_avvik`-rader eldre enn dette slettes (positivt heltall) |
| `ETL_PORT` | `8000` | Port for jobbserveren. Publiser den aldri |
| `MATRIKKEL_BRUKER`, `MATRIKKEL_PASSORD`, `MATRIKKEL_MILJO` | `MATRIKKEL_MILJO=test` | Se [geocode](geocode.md). Er bruker eller passord tomme, hoppes geokoding og gater over |
| `EXTRA_CA_DIR` | `/extra-ca` | Mappe med ekstra rotsertifikater (`*.crt`, `*.pem`), lagt til tillitslageret ved oppstart. I compose er `./certs` montert dit; se `certs/README.md` |

Ugyldig `SYNK_TID`, `AVVIK_RETENTION_DAYS` eller `ETL_PORT` gjør at daemonen
avslutter ved oppstart.

## Oppstartssekvensen

Daemonen venter på at skjemaet finnes (Flyway V1; opptil 10 minutter, ellers
avslutter den slik at docker starter den på nytt). Så sjekker den kodeverkene:

- **Tomme** (`lokaletype`, `aktivitet` og `fasilitet`): kjører den første
  bygget: [build](build.md), [gater](gater.md), [geocode](geocode.md), i den
  rekkefølgen. Feiler byggingen, prøver neste oppstart eller nattkjøring på
  nytt så lenge kodeverkene fortsatt er tomme.
- **Ikke tomme:** hopper over den første bygget.

## Nattsyklusen

Ved `SYNK_TID` (standard kl. 03:00) legges fire jobber i køen, i denne rekkefølgen:

1. `nightly-load`: [synk](sync.md), eller bygging (med gater etterpå) hvis
   kodeverkene fortsatt er tomme.
2. `geocode`: kjører selv om synken feilet, så nye bygg får posisjon. Synk-jobben
   geokoder ikke selv: trigges `sync` alene (`main.py sync` eller jobbserveren),
   kommer ingen geokoding etter, og `geocode` må trigges for seg.
3. `refresh`: oppdaterer søkeviewet, se [Refresh av søkeviewet](#refresh-av-søkeviewet).
4. `prune`: sletter `synk_avvik` eldre enn `AVVIK_RETENTION_DAYS`, unntatt rader
   i `v_synk_avvik_gjeldende` (siste kjøring per kilde), så en kilde som slutter
   å kjøre beholder sine aktuelle problemer synlige.

`gater` er ikke del av nattsyklusen.

## Jobbserveren

All jobbkjøring går gjennom én kø med én worker, så jobber overlapper aldri
(alle skriver de samme tabellene). Jobber kjøres i den rekkefølgen de ble
lagt i køen. En identisk jobb (samme type og argumenter) som fortsatt venter,
legges ikke i køen på nytt. De siste 50 jobbene beholdes, med opptil 200
linjer output hver.

### Refresh av søkeviewet

`refresh` kjører `REFRESH MATERIALIZED VIEW mv_ressurs_sok`, viewet søket i
backend leser fra. Uten refresh ser søket gamle data. Feiler refresh, beholder
viewet det gamle innholdet.

Jobbserveren setter selv en `refresh` i kø etter `sync`, `geocode`,
`nightly-load`, `build` og `startup` (`REFRESH_AFTER` i `jobserver.py`). Like
ventende refresh slås sammen. Kjøres jobbene direkte med `main.py` (for
eksempel `main.py sync`), skjer ikke dette. `refresh` finnes foreløpig ikke som
kommando i `main.py`, så viewet må da oppdateres med:

```bash
docker compose exec etl psql -c "REFRESH MATERIALIZED VIEW mv_ressurs_sok"
```

Refresh som følge av en jobb gjennom API-et (`POST /masterdb/etl/jobs/sync`
eller `/geocode`) er en **egen jobb som køes etter at den første er ferdig**:

- Jobb-id-en API-et svarer med, gjelder bare synken eller geokodingen, som står
  som `ok` før viewet er oppdatert.
- Refresh-jobben dukker opp for seg i `GET /masterdb/etl/jobs`, og søket viser
  endringene først når den er ferdig.
- Refresh køes uavhengig av om jobben gikk bra (jobbserveren ser bare på
  jobbtypen), så en `failed`-jobb kan likevel følges av en refresh.
- Går selve refresh-jobben feil, vises det bare i status og logg for den jobben.

### Internt HTTP-API

Brukes av backend. **Uten autentisering, med vilje.** Eneste beskyttelse er at
etl-tjenesten ikke har `ports:` i `docker-compose.yml`, så bare containere på
compose-nettverket når den. Publiser aldri porten. Av den grunn er
inputvalideringen streng.

| Metode og sti | Gjør |
|---|---|
| `GET /health` | `{"status":"UP"}` |
| `GET /jobs` | De siste jobbene, nyeste først |
| `GET /jobs/{id}` | Én jobb: status, tidspunkter, melding og output |
| `POST /jobs/sync` | Legger en synk i køen |
| `POST /jobs/geocode` | Legger en geokoding i køen |
| `POST /jobs/gater` | Legger gater i køen. Valgfri JSON-kropp `{"kommunenr": ["4601", ...]}`; uten den hentes alle kommuner |

`POST` svarer `202` med `id`, `status`, `queuePosition` og `deduplicated`.
Bare `sync`, `geocode` og `gater` kan startes over HTTP; `build`, `prune` og de
interne `startup`/`nightly-load` kan ikke det. Kroppen må være et JSON-objekt
(maks 64 KB), og `kommunenr` er en ikke-tom liste med firesifrede strenger
(maks 500). Ukjente felt gir `400`. En jobb har status `queued`, `running`, `ok`
eller `failed`.

## Feilhåndtering

- Mislykkede `psql`-kjøringer og `ERROR`-linjer fra `psql` logges. Feil inne i
  én kommunes transaksjon ruller den kommunen tilbake, og neste kommune kjører
  likevel.
- Exit-kode 2 fra en jobb betyr at noen hentinger feilet (logget i
  `synk_avvik`), men at SQL-en er komplett; det er en advarsel, ikke en feil.
- En krasj i en jobb tar ikke ned workeren.
- Geokoding anvendes ikke hvis `jobs.geocode` feilet (utdata er én transaksjon
  som committer helt til slutt, så en avkortet fil må aldri anvendes).

## Se også

- [running](../running.md), [DEPLOY.md](../../../DEPLOY.md)
