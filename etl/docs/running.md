# Kjøre pipelinen

To måter: med containeren (vanlig), eller for hånd (utvikling). Selve
utrullingen står i [DEPLOY.md](../../DEPLOY.md).

## Med containeren

Kopier `.env.example` til `.env`, sett `POSTGRES_PASSWORD` og `MASTERDB_API_KEY`
(og Matrikkel-innloggingen for geokoding), og start:

```bash
docker compose up -d --build        # db (PostGIS) + backend (Spring, Flyway) + etl
docker compose logs -f etl          # første start: bygging; så nattlig synk ved SYNK_TID
docker compose exec etl python3 main.py status    # radtall, geokodingsstatus, siste uttrekk
docker compose exec etl python3 main.py sync      # eller build | geocode | gater | prune: én jobb nå
```

Hva daemonen gjør på egen hånd (oppstartssekvens, nattsyklus, innstillinger):
[daemon](jobs/daemon.md).

## Forutsetninger

**Skjemaet må finnes.** Databasen `masterdb` opprettes av db-containeren, og
backend-containeren legger på skjemaet med Flyway
(`backend/src/main/resources/db/migration/`) hver gang den starter. Start stacken
og vent til backend er `healthy` (`docker compose ps`) før du kjører jobbene.

**HTTPS må virke fra WSL.** Jobbene henter data over internett. På en
Capgemini-maskin krever det at Capgeminis rotsertifikat er installert i WSL (se
prosjektets minne `wsl-ca-sertifikat-lost` eller spør Claude). Test at det virker:

```bash
curl -sS -o /dev/null -w "%{http_code}\n" https://bergen.aktiv-kommune.no/bookingfrontend/searchdataall
```

Skal svare `200`. Svarer den med en sertifikatfeil, må sertifikatet installeres
først. I containeren legges nettverkets rotsertifikat i `certs/` (se
`certs/README.md`); `.env` og `certs/*` ligger i `.gitignore`.

**Matrikkel-innlogging** (bare for geokoding og gater): `MATRIKKEL_BRUKER` og
`MATRIKKEL_PASSORD`. Verifiser med `python3 etl/dev/check_matrikkel_auth.py`.

## For hånd

Det samme arbeidet som containeren gjør, steg for steg. Skriptene bruker bare
Pythons innebygde bibliotek (ingen `pip install`), og skriver SQL til stdout som
du sender til Postgres i et eget steg, slik at du kan se hva som skal skje før noe
endres. `etl/ut/` er generert output og ligger i `.gitignore`.

| Steg | Jobb | Kommandoer |
|---|---|---|
| 1 Skjema | Flyway | Ingenting å kjøre; vent på at backend er `healthy` |
| 2a Bygging, én gang | `jobs/build.py` | [build](jobs/build.md#bruk) |
| 2b Synk, jevnlig | `jobs/sync.py` | [sync](jobs/sync.md#bruk) |
| 3 Geokoding | `jobs/geocode.py` | [geocode](jobs/geocode.md#bruk) |
| Gater | `jobs/gater.py` | [gater](jobs/gater.md#bruk) |

Kjør geokoding etter bygging og etter hver synk, så nye bygg får posisjon.

Valgfritt, med demo-normalisering (mens instansene ikke er normalisert):
[demo_normalisering](../dev/demo_normalisering/README.md).

## Uten nettverk

Jobbene kan lese `<mappe>/<kommune>.json` i stedet for å hente fra nettet, med
`--fra-fil <mappe>`. Nyttig for å kjøre samme data på nytt. Se
[adding-a-kommune](reference/adding-a-kommune.md#flaggene---kommuner-fil-og---fra-fil).
