# Legge til en kommune

En kommune synkroniseres av [`jobs/sync.py`](../jobs/sync.md) når den har en
aktiv Aktiv kommune-instans i databasen. Her står hvordan den registreres, og
formatet på listen og flaggene synk bruker.

## Med API-et (anbefalt)

Opprett kommunen med `POST /masterdb/kommune` og oppgi `bookingBaseUrl`, for
eksempel `https://bergen.aktiv-kommune.no`. Det eneste som kreves er det ene
kallet: API-et registrerer Aktiv kommune-instansen og kobler den til kommunen i
samme transaksjon, og kommunen synkroniseres når kilden er aktiv.

```json
{ "kommunenr": "4601", "navn": "Bergen", "fylkesnavn": "Vestland",
  "bookingBaseUrl": "https://bergen.aktiv-kommune.no", "active": true }
```

- **URL-en valideres strengt:** `https`, ett subdomene under `aktiv-kommune.no`,
  ingen sti, ingen port. ETL henter fra URL-en som er lagret, så andre verter
  avvises (400) både i API-et og når ETL leser listen.
- **En kilde tilhører én kommune.** Er URL-en allerede registrert på en annen
  kommune, blir svaret 409 og kommunen opprettes ikke.
- **`bookingBaseUrl` og `active` er påkrevd** ved opprettelse (mangler en av
  dem, blir svaret 400). Kilden registreres med aktiv-status fra `active`
  (boolean).
- **URL-en settes bare ved opprettelse.** `PUT /masterdb/kommune/{id}` endrer
  `kommunenr`, `navn` og `fylkesnavn`, og rører aldri bookingkilden, fordi
  kommunens bygg og ressurser er knyttet til instansen de ble lastet fra. For å
  bytte URL: slett kommunen og opprett den på nytt.
- Å fjerne en kommune med `DELETE` fjerner også kilden hvis ingen annen kommune
  bruker den, så samme URL kan registreres på nytt. Bygg og ressurser for
  kommunen slettes samtidig.
- **Stoppe og gjenoppta synkroniseringen** uten å slette kommunen:
  `PATCH /masterdb/kommune/{id}/booking` med `{"aktiv": false}` (eller `true`).
  `bookingAktiv` i svaret fra `GET` viser status.
- Seed-kommunene fra `jobs/build.py` er aktive.

## For hånd

Er kommunen opprettet på annen måte enn gjennom API-et, kan kilden også
registreres for hånd. Bytt ut `<slug>` (subdomenet; små bokstaver, tall og `-`),
`<Navn>` og `<kommunenr>`:

```sql
INSERT INTO fagsystem_instans (kildenokkel, type, navn, base_url)
VALUES ('aktiv-kommune:<slug>', 'booking', 'Aktiv kommune <Navn>', 'https://<slug>.aktiv-kommune.no');

INSERT INTO kommune_fagsystem_instans (kommune_id, fagsystem_instans_id, type)
SELECT k.id, fi.id, fi.type FROM kommune k, fagsystem_instans fi
WHERE k.kommunenr = '<kommunenr>' AND fi.kildenokkel = 'aktiv-kommune:<slug>';
```

## Ting å vite

- Bare `jobs/sync.py` laster en kommune som er lagt til slik. Den laster bygg,
  ressurser og koblinger, men skriver aldri kodeverkene, så id-er masteren ikke
  kjenner loggføres i `synk_avvik` og kobles ikke.
- Mens `NORMALISER_DEMO=true` kjenner demo-mappingfilene bare de eksisterende
  kildene, så regn med `synk_avvik`-rader for en ny kommune helt til instansen
  er normalisert.
- Kommunen lastes ved neste nattlige synk. For å laste den med en gang:
  `docker compose exec etl python3 main.py sync`.
- En URL med skrivefeil blir godtatt hvis formen stemmer. Den gir en mislykket
  henting i `synk_avvik` ved neste synk, ikke en feil ved opprettelsen.

## Hvilken liste hver jobb bruker

| Jobb | Kommuneliste |
|---|---|
| `jobs/build.py` | Alltid den innebygde `KOMMUNER` i `lib/kommuner.py` (utgangspunktet for en tom master). Har ikke `--kommuner-fil` |
| `jobs/sync.py` | Alltid databasen, via `sql/kommuner_query.sql`. Nekter å kjøre uten `--kommuner-fil` |

## Flaggene `--kommuner-fil` og `--fra-fil`

De gjør hver sin ting og kan brukes sammen:

| Flagg | Hva det styrer | Innhold |
|---|---|---|
| `--kommuner-fil FIL` | **Hvilke kommuner** som behandles | En tekstfil, én linje per kommune: `slug\|kommunenr\|navn\|fylke\|base_url` (utdata fra `sql/kommuner_query.sql`) |
| `--fra-fil MAPPE` | **Hvor dataene hentes fra** | En mappe med `<slug>.json` i samme form som `searchdataall`, i stedet for å hente fra nettet (brukes av demo-normaliseringen). Kildeuttrekket registreres da med `file:///...` som endepunkt og uten HTTP-status |
