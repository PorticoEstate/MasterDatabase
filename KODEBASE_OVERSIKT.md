# Kodebase-oversikt

Kort gjennomgang av hva hver del av repoet gjør, og hvordan delene henger sammen.
Prosjektet er en **masterdatabase** som skal samle data fra flere kommunale
fagsystemer (booking av lokaler) og supplere med autoritative registre
(Matrikkelen). Filene faller i fire grupper: **skjema/dokumentasjon**, **ETL**,
**API-kontrakt** og **infrastruktur**. Det finnes ingen ferdig backend-kode
ennå — API-et er foreløpig bare en spesifikasjon.

## 1. Design-/planleggingsdokumenter (rot-nivå)

- `modellutvikling.md` / `modellutvikling.en.md` — overordnet designdokument:
  masterdatabasen skal være et *definisjons- og rutingslag*, ikke lagre rå
  sensordata/tidsserier fra fagsystemene, bare lenker + metadata + proveniens.
  Dette er "grunnloven" alle skjemaene under prøver å følge.
- `README.md` — prosjektoversikt, hvordan kjøre alt i Docker, kodestil-regler
  (Allman-braces, tab-innrykk).
- `DEVELOPMENT_WSL2.md` — oppsett av WSL2 + Docker bak brannmur/proxy, ikke
  koblet til noe annet enn utviklermiljøet.

## 2. Databaseskjemaer (`db/`) — tre parallelle versjoner

Disse har utviklet seg i rekkefølge, og bare én er faktisk i bruk:

- `db/schema.sql` — første versjon: matrikkelenheter + bygg/FDV, geometri som
  WKT-tekst (ingen PostGIS). Dokumentert i `db/README.md`.
- `db/testSchema.sql` — variant av `schema.sql` der matrikkeldomenet er
  *bevisst fjernet* (kun vegadresser). Dokumentert i
  `db/SCHEMA_DOKUMENTASJON.md`.
- `db/magnusDB.sql` (kjernemodellen) — **den som faktisk er populert med ekte
  data** (bekreftet i databasen `OppdatertDatabaseMagnus`). Krever PostGIS,
  bruker `geography(Point,4326)` i stedet for WKT-tekst, og legger til
  proveniens-/kvalitetslaget: `kildekode`/`kildekode_mapping` (oversetter
  kommunenes egne kodeverk til et felles kodeverk), `kildeuttrekk` (rå
  JSON-lagring før transformasjon — se eget avsnitt under) og `synk_avvik`
  (feilloggføring). Dokumentert i `db/schema_kjerne_dokumentasjon_Magnus.md`.
- `db/erdiagram_v7.puml`/`v8.puml` og `Master_database_v7/v8*.svg` —
  PlantUML-diagrammer og rendrede bilder, tilhører `schema.sql`/
  `testSchema.sql`-sporet (**ikke** kjernemodellen — derfor stemmer ikke
  disse diagrammene med `kildeuttrekk`/`spatial_ref_sys` i den populerte
  databasen).
- `db/semantic/` — en frittstående, valgfri gren: eksponerer databasen som en
  RDF/SPARQL-graf via Ontop (OBDA), med ontologi (`ontology.ttl`), R2RML-mapping
  og SHACL-validering. Kobler til skjemaet kun gjennom `sql/iri_views.sql`,
  ellers uavhengig av resten.

## 3. ETL (`etl/`) — fyller kjernemodellen med data

To Python-script, ingen eksterne biblioteker, ingen direkte databasetilkobling
— begge skriver SQL-tekst som kjøres manuelt etterpå:

- `etl/last_inn.py` — henter rådata fra 12 "Aktiv kommune"-instanser
  (`bookingfrontend/searchdataall`), oversetter kommunenes kodeverk via
  `LOKALETYPE`/`FASILITET`/`AKTIVITET`-ordbøkene, og genererer SQL som fyller
  `kommune`, `fagsystem_instans`, `kildekode(+mapping)`, `bygning`, `adresse`,
  `ressurs` og koblingstabeller. Logger brutte referanser til `synk_avvik`.
  **Skriver foreløpig ikke til `kildeuttrekk`** — tabellen finnes i skjemaet,
  men blir aldri fylt av dagens kode, så den står tom.
- `etl/geokod.py` — tar adresser uten posisjon (produsert av steget over),
  slår dem opp mot Kartverkets Adresse-API, og genererer SQL som setter
  `adresse.posisjon`/`bygning.posisjon`. Krever nøyaktig ett treff, ellers
  logges avvik i `synk_avvik` i stedet for å gjette.
- `etl/geokod.md` — logg/dokumentasjon av en faktisk kjøring av `geokod.py`
  (238/420 adresser geokodet, feilanalyse).
- `etl/ut/` — genererte output-filer fra de to scriptene (`bergen.sql`,
  `alle.sql`, `geokoding.sql`, `adresser_a_geokode.txt`) — dette er
  artefakter, ikke kildekode.

**Flyt:** `last_inn.py` → SQL kjøres mot Postgres → adresser mangler posisjon
→ `geokod.py` → SQL kjøres mot samme database. Begge trinnene er
idempotente/trygge å kjøre på nytt (`ON CONFLICT`-klausuler, ren
fil-inn/fil-ut).

## 4. API-kontrakt (`api/`, `docs/`)

- `api/openapi.yaml` — OpenAPI 3.1-spesifikasjon, "single source of truth"
  for endepunkter. Foreløpig bare `/health` og `/buildings` definert. Ingen
  serverimplementasjon finnes ennå (kommentaren nevner en planlagt
  Slim 4 + PHP-DI-backend).
- `docs/swagger.html` / `docs/redoc.html` — statiske HTML-viewere som
  rendrer `openapi.yaml`, servert av Apache-containeren.
- `api/README.md` — kort forklaring av mappen.

## 5. Infrastruktur

- `Dockerfile` — PHP 8.4 + Apache-image, installerer `pdo_pgsql` (for
  fremtidig PHP-backend mot Postgres) og Xdebug, serverer hele repoet
  (inkl. Swagger/Redoc).
- `docker-compose.yml` — to tjenester: `portico_masterdata` (Apache/PHP,
  port 8083) og `db` (`postgis/postgis:18-3.6`, container
  `portico_masterdb`, port 5432) på samme nettverk.
- `docker-entrypoint.sh` — starter bare `apache2-foreground`.
- `build_config/apache-masterdb.conf`, `build_config/xdebug.ini` — kopieres
  inn i imaget av Dockerfilen.

## Kort oppsummert kobling

```
last_inn.py ──(SQL)──> Postgres (schema_kjerne/magnusDB.sql, i containeren portico_masterdb)
                              │
geokod.py <───(leser adresser uten posisjon)
   │
   └──(SQL)──> samme database

openapi.yaml ──beskriver──> (fremtidig) backend som skal lese fra samme database
docker-compose.yml ──bygger/kjører──> Dockerfile (Apache/PHP) + db (postgis)
db/semantic/ ──leser (valgfritt, frikoblet)──> samme database, via Ontop
```

Kort sagt: `db/magnusDB.sql` er den reelle kjernen, ETL-scriptene i `etl/`
fyller den, `api/openapi.yaml` er en kontrakt uten implementasjon ennå, og
`db/schema.sql`/`testSchema.sql`/diagrammene er tidligere iterasjoner som
ikke lenger matcher det som faktisk kjører.

## Om `kildeuttrekk`-tabellen (oppsummering av egen diskusjon)

`kildeuttrekk` er ment å lagre det rå JSON-svaret fra Aktiv kommune *før*
transformasjon, slik at en last kan kjøres om igjen uten nye API-kall. Den
er:

- **Ikke det samme som `spatial_ref_sys`** — sistnevnte er PostGIS' egen
  interne oppslagstabell for koordinatsystemer, opprettet automatisk av
  `CREATE EXTENSION postgis` og helt urelatert.
- **Ikke erstattet av `synk_avvik`** — `synk_avvik` logger bare
  spesifikke, allerede kjente feiltyper (kort tekst), ikke hele det
  opprinnelige svaret. Uten `kildeuttrekk` kan man ikke i ettertid skille
  "kilden var rar" fra "vår transformasjonskode tolket kilden feil", og man
  mister muligheten til å re-kjøre transformasjonen uten å hente på nytt
  fra kommunen.
- **For øyeblikket tom**, fordi `etl/last_inn.py` aldri skriver til den —
  funksjonaliteten er designet i skjemaet, men ikke implementert i ETL-koden.
- **Append-only av design**: tabellen har ingen unik-constraint på
  `kilde`/`endepunkt`, og indeksen `ix_kildeuttrekk_kilde (kilde, hentet_at DESC)`
  er laget for å finne "siste uttrekk per kilde" — altså vil hver kjøring
  legge til en ny rad, ikke overskrive den forrige. Det gir full historikk,
  men betyr også at tabellen vokser ubegrenset over tid uten en bevisst
  slette-/retensjonsstrategi.

**Forslag til implementasjon:** i `etl/last_inn.py`, rett etter at rådataene
hentes (`d = hent_json(url)`), sette inn en rad i `kildeuttrekk` og bruke
psql sin `\gset`-mekanisme til å hente ut den nye radens `id`, slik at de
påfølgende `synk_avvik`-innsettingene kan referere til riktig
`kildeuttrekk_id` i stedet for å stå løse slik de gjør i dag.
