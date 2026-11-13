# Innlasting fra Aktiv kommune

To skript henter data fra Aktiv kommune og skriver SQL som fyller
masterdatabasen: `last_inn.py` bygger databasen (kjøres én gang), og `synk.py`
holder den oppdatert etterpå (kjøres jevnlig, f.eks. fra cron). Se
`db/schema_kjerne_dokumentasjon.md` for hva tabellene betyr.

## Oversikt over hele pipelinen

Fra tomt skjema til populert database, i tre steg:

```
┌───────────────────────────────────────────────────────────────────────┐
│ STEG 1 — SKJEMA                                                       │
│ backend/src/main/resources/db/migration/V*.sql (Flyway)               │
│                                                                        │
│ Oppretter alle tabeller i en tom database: kommune, bygning, adresse, │
│ ressurs, aktivitet/fasilitet/lokaletype,                              │
│ gate/matrikkelinfo, synk_avvik/kildeuttrekk. Kjøres av backend-       │
│ containeren ved oppstart; ingenting å kjøre for hånd.                 │
└───────────────────────────────────────────────────┬───────────────────┘
                                                      ▼
┌───────────────────────────────────────────────────────────────────────┐
│ STEG 2 — INNLASTING                                                   │
│ etl/last_inn.py (bygging, én gang)  ←  Aktiv kommune API              │
│ etl/synk.py     (jevnlig, cron)     ←  Aktiv kommune API              │
│                                                                        │
│ Henter kommune, bygg, adresser (uten koordinater), ressurser og       │
│ koblingene ressurs → lokaletype/aktivitet/fasilitet, på id.           │
│ last_inn.py oppretter i tillegg kodeverkene fra instansene; synk.py   │
│ skriver dem aldri, og logger avvik fra masteren. Se "Bygging og      │
│ synk" og "Kildekontrakt" under.                                       │
│ Laster ALDRI `organizations` (persondata).                             │
└───────────────────────────────────────────────────┬───────────────────┘
                                                      ▼
┌───────────────────────────────────────────────────────────────────────┐
│ STEG 3 — GEOKODING + BYGNINGSBERIKELSE                                │
│ etl/matrikkel_adresse.py  ←  MatrikkelAPI (SOAP, krever innlogging)   │
│                                                                        │
│ a) Løser adressene — søker *innenfor riktig kommune* (kjent fra      │
│    steg 2) i Matrikkelen. Eneste geokodingskilde; se begrunnelsen i   │
│    seksjonen under for hvorfor Kartverkets åpne Adresse-API ikke      │
│    lenger brukes som et eget forsteg.                                 │
│ b) Henter bygningsnr/bygningstype/bra_m2/antall_etasjer for ALLE      │
│    bygg som mangler det (Aktiv kommune har ikke dette feltet i det    │
│    hele tatt — dette er eneste kilde).                                │
│ Prinsipp: ett eksakt treff, ellers avvik.                             │
└───────────────────────────────────────────────────┬───────────────────┘
                                                      ▼
                                          ╔═══════════════════╗
                                          ║   FERDIG: masterdb ║
                                          ╚═══════════════════╝
```

**Demo-normalisering (valgfritt, før steg 2).** Aktiv kommune-instansene er ennå
ikke normalisert. `etl/demo_normalisering/normaliser.py` viser hvordan masterdatabasen kan
bli når de er det: det gjør en rå `searchdataall` om til det en normalisert
instans ville levere, og `last_inn.py` laster resultatet med `--fra-fil`. Hele
mappen kan slettes når instansene er normalisert; verken `last_inn.py` eller
`synk.py` trenger endring. Se "Demo-normalisering" under.

**Tverrgående, på hvert steg:** alt som feiler (ugyldig verdi, duplikat,
API-feil, manglende treff) logges i `synk_avvik` sammen med selve posten som
feilet — én dårlig rad stopper aldri hele kjøringen. Hver kjøring registreres
i `kildeuttrekk` (metadata, ikke selve svaret). Se "Avvik og kildeuttrekk"
under.

Alle tre stegene er trygge å kjøre på nytt — de endrer kun det som fortsatt
mangler/er ukjent, aldri manuelt satte verdier. De eksakte kommandoene for
hvert steg står i seksjonene under, i samme rekkefølge.

**Filoversikt:**

| Fil | Rolle |
|---|---|
| `backend/src/main/resources/db/migration/V*.sql` | Skjemaet (steg 1), kjøres av Flyway i backend |
| `db/schema_kjerne_dokumentasjon.md` | Hva hver tabell/kolonne betyr og hvorfor |
| `etl/last_inn.py` | Steg 2, bygging: oppretter kodeverkene og laster alt annet. Kjøres én gang |
| `etl/synk.py` | Steg 2, jevnlig synkronisering: som `last_inn.py`, men skriver aldri kodeverkene |
| `etl/helpers.py` | Hjelpefunksjoner delt av de to skriptene (`rens`, `q`, `logg`, `hent_json`, `KOMMUNER`, `les_kommuner` osv.) |
| `etl/kommuner_query.sql` | Henter listen over kommuner som skal synkroniseres fra databasen (se "Hvilke kommuner som synkroniseres") |
| `etl/demo_normalisering/normaliser.py` | DEMO: lager normalisert JSON fra rå `searchdataall`. Slettes ved normalisering |
| `etl/demo_normalisering/{lokaletype,fasilitet,activity}_mapping/` | DEMO: vokabular (`venue_types.json`, `facilities.json`, `activities.json`) og mapping (`mapping.json`) som `normaliser.py` leser |
| `etl/matrikkel_adresse.py` | Steg 3. Kjøres etter bygging og etter hver synk, så nye bygg får posisjon |
| `etl/hent_gater.py` | Henter ALLE gater for en kommune fra Matrikkelen inn i `gate`. Kjøres av daemonen én gang etter første bygg, og ellers for hånd med `run.sh gater` |
| `etl/matrikkel_test/test_auth.py` | Verifiserer at Matrikkel-innlogging virker, før man kjører steg 3 |

**Ikke bygget ennå:** `ressurslenke` (koble samme fysiske bygg/ressurs til
flere fagsystemer samtidig, f.eks. booking + FDV) — bevisst utsatt til det
faktisk finnes et andre fagsystem å koble til, se `db/ressurslenke.md`.

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
python3 etl/last_inn.py bergen > etl/ut/bergen.sql
docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/bergen.sql
```

**Bygging, alle 12 kommunene:**

```bash
python3 etl/last_inn.py alle > etl/ut/alle.sql
docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/alle.sql
```

**Synk etter bygging** (samme måte å sende SQL-en til Postgres, men synk trenger kommunelisten fra databasen først, se «Hvilke kommuner som synkroniseres»):

```bash
psql -tA -F'|' -f etl/kommuner_query.sql > etl/ut/kommuner.txt
python3 etl/synk.py alle --kommuner-fil etl/ut/kommuner.txt > etl/ut/synk.sql
docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/synk.sql
```

Den planlagte kjøringen gjøres av etl-containeren (`etl/run.sh`, hver natt kl. 03:00; se `DEPLOY.md`). Etter hver synk
kjøres `matrikkel_adresse.py` (steg 3), så nye bygg får posisjon.

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

Masteren eier vokabularet og hierarkiet (`lokaletype`, `aktivitet`, `fasilitet`).
Kommunen eier derimot det den selv registrerer: bygg, ressurser og koblingene
fra ressurs til bygg, lokaletype, aktivitet og fasilitet. Skriptene skiller seg
bare på hvordan de behandler kodeverkene(`lokaletype`, `aktivitet`, `fasilitet`):

| | `last_inn.py` (bygging, én gang) | `synk.py` (jevnlig) |
|---|---|---|
| Kodeverk | Oppretter konsepter som mangler (`id`, `navn`, forelder). Et konsept som finnes røres aldri | Skriver aldri |
| Avvik fra masteren (samme id med annet navn eller annen forelder) | Loggføres i `synk_avvik` | Loggføres i `synk_avvik` |
| Bygg og ressurser, også nye | Lastes | Lastes |
| Koblinger ressurs → bygg, lokaletype, aktivitet, fasilitet | Lastes. Kilden vinner | Lastes. Kilden vinner |
| Kobling til en id masteren ikke kjenner | Lastes ikke, loggføres én gang per id | Lastes ikke, loggføres én gang per id |

Et nytt konsept opprettes altså bare i masteren (manuelt, med id satt manuelt),
aldri av en instans etter bygging. En instans som begynner å bruke en ny id,
gir avvik og ingen kobling til den id-en.

## Hvilke kommuner som synkroniseres

De to skriptene får kommunelisten fra hver sin kilde, og det er ikke valgfritt:

- **Bygging** (`last_inn.py`) bruker alltid den innebygde `KOMMUNER` i `helpers.py`. Den er
  utgangspunktet for en tom master, og byggingen registrerer hver kommune og dens Aktiv
  kommune-instans i databasen.
- **Synk** (`synk.py`) bruker alltid kommunene som er registrert i databasen, og nekter å
  kjøre uten `--kommuner-fil`. Den faller aldri tilbake på den innebygde listen.
  Demo-normaliseringen følger samme liste som skriptet den mater: uten `--kommuner-fil`
  (bygging) bruker den den innebygde listen, med filen (synk) databaselisten.

`run.sh sync` lager synk-listen ved å kjøre `kommuner_query.sql`, som lister alle kommuner
som har en **aktiv** `fagsystem_instans` av typen `booking` med `kildenokkel` som begynner
på `aktiv-kommune:`. Resultatet (`slug|kommunenr|navn|fylke|base_url`, én linje per kommune) skrives
til `etl/ut/kommuner.txt` og sendes med `--kommuner-fil`. Hvis spørringen feiler,
synkroniseres ingenting den natten.

For hånd:

```bash
psql -tA -F'|' -f etl/kommuner_query.sql > etl/ut/kommuner.txt
python3 etl/synk.py alle --kommuner-fil etl/ut/kommuner.txt > etl/ut/synk.sql
```

### `--kommuner-fil` og `--fra-fil`

De to flaggene gjør hver sin ting og kan brukes sammen:

| Flagg | Hva det styrer | Innhold |
|---|---|---|
| `--kommuner-fil FIL` | **Hvilke kommuner** som behandles | En tekstfil, én linje per kommune: `slug\|kommunenr\|navn\|fylke\|base_url` (utdata fra `kommuner_query.sql`) |
| `--fra-fil MAPPE` | **Hvor dataene hentes fra** | En mappe med `<slug>.json` i samme form som `searchdataall`, i stedet for å hente fra nettet (brukes av demo-normaliseringen) |

### Legge til en kommune

Opprett kommunen med `POST /masterdb/kommune` og oppgi `bookingBaseUrl`, for eksempel
`https://bergen.aktiv-kommune.no`. Det eneste som kreves er det ene kallet: API-et
registrerer Aktiv kommune-instansen og kobler den til kommunen i samme transaksjon, og
kommunen synkroniseres når kilden er aktivert (se under).

```json
{ "kommunenr": "4601", "navn": "Bergen", "fylkesnavn": "Vestland",
  "bookingBaseUrl": "https://bergen.aktiv-kommune.no" }
```

- **URL-en valideres strengt:** `https`, ett subdomene under `aktiv-kommune.no`, ingen sti,
  ingen port. ETL henter fra URL-en som er lagret, så andre verter avvises (400) både i API-et
  og når ETL leser listen.
- **En kilde tilhører én kommune.** Er URL-en allerede registrert på en annen kommune, blir
  svaret 409 og kommunen opprettes ikke.
- **`bookingBaseUrl` er påkrevd** ved opprettelse (uten den blir svaret 400), og kilden registreres
  som inaktiv.
- **URL-en settes bare ved opprettelse.** `PUT /masterdb/kommune/{id}` endrer `kommunenr`, `navn` og
  `fylkesnavn`, og rører aldri bookingkilden, fordi kommunens bygg og ressurser er knyttet til instansen
  de ble lastet fra. For å bytte URL: slett kommunen og opprett den på nytt.
- Å fjerne en kommune med `DELETE` fjerner også kilden hvis ingen annen kommune bruker den, så
  samme URL kan registreres på nytt.
- En ny kommune opprettes med inaktiv bookingkilde (`aktiv = false`) og synkroniseres ikke før den
  aktiveres med `PATCH` under. Seed-kommunene fra `last_inn.py` er aktive.
- **Stoppe og gjenoppta synkroniseringen** uten å slette kommunen: `PATCH /masterdb/kommune/{id}/booking`
  med `{"aktiv": false}` (eller `true`). `bookingAktiv` i svaret fra `GET` viser status.

Er kommunen opprettet på annen måte enn gjennom API-et, kan kilden også registreres for hånd.
Bytt ut `<slug>` (subdomenet; små bokstaver, tall og `-`), `<Navn>` og
`<kommunenr>`:

```sql
INSERT INTO fagsystem_instans (kildenokkel, type, navn, base_url)
VALUES ('aktiv-kommune:<slug>', 'booking', 'Aktiv kommune <Navn>', 'https://<slug>.aktiv-kommune.no');

INSERT INTO kommune_fagsystem_instans (kommune_id, fagsystem_instans_id, type)
SELECT k.id, fi.id, fi.type FROM kommune k, fagsystem_instans fi
WHERE k.kommunenr = '<kommunenr>' AND fi.kildenokkel = 'aktiv-kommune:<slug>';
```

Ting å vite:
- Bare `synk.py` laster en kommune som er lagt til slik. Den laster bygg, ressurser og
  koblinger, men skriver aldri kodeverkene, så id-er masteren ikke kjenner loggføres i
  `synk_avvik` og kobles ikke.
- Mens `NORMALISER_DEMO=true` kjenner demo-mappingfilene bare de eksisterende kildene, så
  regn med `synk_avvik`-rader for en ny kommune helt til instansen er normalisert.
- Kommunen lastes ved neste nattlige synk. For å laste den med en gang:
  `docker compose exec etl ./run.sh sync`.
- En URL med skrivefeil blir godtatt hvis formen stemmer. Den gir en mislykket henting i
  `synk_avvik` ved neste synk, ikke en feil ved opprettelsen.

## Hva skriptene gjør og ikke gjør

Laster: kommune, bygg, adresser (som de står i kilden, uten koordinater) og
ressurser. Ressursene kobles direkte til kodeverkene på id
(`ressurs.lokaletype_id`, `ressurs_aktivitet`, `ressurs_fasilitet`). Kildens
egne koder lagres ikke; etter normalisering er de lik masterens id-er.

Skriptene gjør ingen oversettelse. Det er instansene som skal levere et
normalisert kodeverk med masterens id-er (se "Kildekontrakt"). Brudd på
kontrakten loggføres i `synk_avvik`. Kodeverkene er tomme i en ny database til
`last_inn.py` er kjørt.

Koblingene (`ressurs_aktivitet`, `ressurs_fasilitet`)
bygges på nytt for instansen ved hver kjøring. Kodeverkene selv får aldri
konsepter fjernet; et konsept som forsvinner fra kilden, blir stående.

Laster **ikke**: koordinater og matrikkeldata (eget steg, se
"Geokoding og bygningsberikelse" under), og **ikke** `organizations`-samlingen
fra kilden, som inneholder personopplysninger om søkere - se prosjektets
minne om dette.

Kjøres et skript på nytt for en kommune som allerede er lastet inn, oppdateres
radene i stedet for å dupliseres (`ON CONFLICT ... DO UPDATE`). En adresse som
er geokodet eller satt manuelt, og en kapasitet som er satt manuelt, overskrives
ikke. Se db/schema_kjerne_dokumentasjon.md for detaljene.

De to skriptene deler hjelpefunksjonene i `helpers.py`, men har hver sin kopi
av selve lastingen, så en rettelse i den må gjøres i begge. `diff
etl/last_inn.py etl/synk.py` skal i praksis bare vise docstringen og
kodeverksdelen.

## Avvik og kildeuttrekk

Hver kjøring registrerer et `kildeuttrekk` (kilde, endepunkt, tidspunkt,
HTTP-status - ikke hele svaret fra kilden). Alt som ikke lar seg laste
loggføres i `synk_avvik` sammen med selve posten som feilet (`rapost`, renset
for personopplysninger som `organizations` og andre persondatafelt): ugyldige
verdier, koblinger til noe som ikke finnes i uttrekket, brudd på kildekontrakten,
databasefeil og feilet henting. En enkelt dårlig post stopper aldri hele lasten.

Gå gjennom avvikene fra siste kjøring slik:

```bash
docker exec portico_masterdb psql -U postgres -d masterdb -c "
    SELECT d.avvik_id, d.kilde, d.avvikstype, d.felt, d.detalj, d.post
    FROM v_synk_avvik_gjeldende g JOIN v_synk_avvik_detalj d ON d.avvik_id = g.id
    WHERE g.avvikstype <> 'manglende_forelder';"
```

`post` er selve posten fra kilden som feilet, lagret direkte på avviket. De to
nyeste uttrekkene per kilde beholdes, uforbeholdent - bevis for et avvik ligger
på avviket selv, ikke i uttrekket, så gammel metadata kan ryddes trygt bort.

## Kildekontrakt: hva en normalisert instans må levere

Skriptene laster kodeverkene direkte fra `searchdataall`, uten mapping, og
kobler på id. Det forutsetter at hver instans er normalisert og
leverer kodeverkene med masterens id-er:

| Samling | Felt | Krav |
|---|---|---|
| `resource_categories` (lokaletype), `activities`, `facilities` | `id` | Unik i samlingen, og **den samme id-en på tvers av instanser**: masterens `id` er den delte id-en. Nye konsepter opprettes manuelt i masteren med manuelt satt id (neste ledige tall, aldri gjenbruk) |
| | `name` | Samme navn som masteren har for denne id-en. Navnet er unikt per tabell |
| | `parent_id` | Samme forelder som masteren. `id` i samme samling, eller `null` for en rot. Én forelder, ingen sykluser. `facilities` har ikke dette feltet i dag |
| `resources` | `rescategory_id` | `id` i `resource_categories`, og masteren kjenner den |
| `resource_activities`, `resource_facilities` | `resource_id`, `activity_id`/`facility_id` | Peker på en rad i `resources`, og på en id masteren kjenner |

Masteren eier vokabularet og hierarkiet, så en instans som viker fra det
påvirker aldri masteren, men loggføres i `synk_avvik`. Koblingene eies av
kommunen og følger kilden. Brudd lastes ikke stille:

| Brudd | Avvikstype | Følge |
|---|---|---|
| Manglende eller ugyldig `id`, tomt `name`, id som går igjen | `ugyldig_verdi` | Posten sammenlignes ikke med masteren |
| Samme `id` med annet `name` eller annen `parent_id` enn i masteren | `ugyldig_verdi` | Masteren beholder sitt. Avviket sier hva begge har |
| `id` i kodeverket som masteren ikke har | `manglende_forelder` | Ved synk opprettes den ikke. Ved bygging bare hvis navnet ikke er tatt av en annen id |
| Kobling til en id masteren ikke kjenner (`rescategory_id`, `activity_id`, `facility_id`) | `manglende_forelder` | Koblingen lastes ikke; én avviksrad per id |
| Kobling til en ressurs som ikke finnes i uttrekket | `manglende_forelder` | Raden lastes ikke |

**Åpent: fullstendighet.** Kontrakten krever ikke at hele treet er med, men i
dag er det ikke det. Målt på Bergen (2026-11-02) mangler 8 av 102 aktiviteter og
4 av 56 lokaletyper sin forelder i samlingen, fem aktivitets-id-er brukes av
koblinger uten å finnes, og 389 ressurser og 28 bygg er referert uten å være med
i uttrekket. Årsaken er ikke avklart (filtrering i `searchdataall`, eller et
annet endepunkt som gir alt). Med masteren som eier av vokabularet er det
mindre kritisk at hver instans leverer hele treet, men koblingene må fortsatt
peke på id-er som finnes.

## Demo-normalisering

Mappingen er midlertidig. Den viser hvordan masterdatabasen blir når instansene
er normalisert, og brukes ikke i produksjon. Alt den trenger ligger i
`etl/demo_normalisering/`, og mappen slettes når normaliseringen er på plass.

`normaliser.py` leser `searchdataall` (nettet, eller `--fra-fil`), og skriver
`<kommune>.json` med samme form, men med kodeverkene erstattet av vokabularet
fra filene (`id`, `name`, `parent_id`) og koblingene omskrevet. Kildenavn uten
mapping, eller som mappes til et exclude-konsept, får ingen kobling og skrives
til standard-feil.

```bash
python3 etl/demo_normalisering/normaliser.py alle              # skriver etl/ut/normalisert/
python3 etl/last_inn.py alle --fra-fil etl/ut/normalisert > etl/ut/alle.sql
docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/alle.sql
```

`synk.py` tar samme `--fra-fil`.

Konseptene i vokabularfilene har hver en fast `id` (den delte id-en), og
`broader` er forelderens navn. Et nytt konsept får neste ledige id; en id
endres eller gjenbrukes aldri. En endring i `mapping.json` eller
vokabularfilene slår igjennom ved neste kjøring av `normaliser.py`, men
`last_inn.py` oppretter bare konsepter som mangler, så en omdøping eller en
ny forelder i filene når ikke en database som allerede er bygget. Fasettene
(`facets`) er bare en gruppering i filene og havner ikke i databasen.

I produksjon finnes ingen vokabularfiler i prosjektet: kodeverkene bygges fra
de normaliserte instansene ved bygging, og eies deretter av masteren.

Demoen skjuler brudd på kontrakten: den bygger vokabularet fra filene, så
manglende foreldre og ukjente kodeverks-id-er i kilden gir ingen avvik. Et rent
`synk_avvik` for kodeverkene etter en demokjøring sier derfor ingenting om
kildens kvalitet. Avvikene på koblingene (til ressurser som ikke er med i
uttrekket) kommer derimot med.

## Geokoding og bygningsberikelse (MatrikkelAPI)

`matrikkel_adresse.py` er eneste geokodingssteg i pipelinen, og gjør to ting:

1. **Geokoding** av enhver hovedadresse som ennå ikke er løst. MatrikkelAPI
   (SOAP, krever `MATRIKKEL_BRUKER`/`MATRIKKEL_PASSORD` - se
   `etl/matrikkel_test/test_auth.py`) lar oss søke *innenfor riktig kommune*, som vi
   allerede kjenner fra innlastingen.
2. **Bygningsnummer og bygningsfakta** for enhver bygning som mangler det,
   uansett om adressen ble løst i denne kjøringen eller en tidligere. Aktiv
   kommune oppgir ikke bygningsnummer i det hele tatt - dette er den eneste
   kilden til det.

Se modulens docstring for hele kjeden av SOAP-kall.

**Hvorfor ikke Kartverkets åpne Adresse-API i tillegg?** Det ble det tidligere
(`etl/geokod.py`, fjernet), som et raskere, uautentisert forsteg - Matrikkelen
ble bare brukt som fallback for det det åpne API-et bommet på. Prosjektet har
bevisst gått bort fra det: siden denne pipelinen bare kjøres ved populering og
innimellom, er den ekstra tiden MatrikkelAPI-kjeden tar ikke noe problem, og
ett system med én kilde er enklere å forstå og vedlikeholde enn to. Kostnaden er
målt: en nasjonal test av alle 12 kommunene viste 69,7 % automatisk treffrate
med Matrikkelen alene, mot 73,1 % med det todelte oppsettet - et bevisst valg
om noen få prosentpoengs lavere automatikk, ikke et ukjent tap. De adressene
det gjelder havner i `synk_avvik` og rettes manuelt, akkurat som før.

Fyller `matrikkelinfo` (gnr/bnr/fnr/snr, knyttet til adressens bygg via
`bygning_id`) uansett geokodingsstatus - billig og idempotent (`ON CONFLICT
DO NOTHING`), så det forsøkes for enhver adresse vi klarer å slå opp i
Matrikkelen, ikke bare de som fortsatt mangler geokoding. Fyller ved adressetreff som *fortsatt* mangler
geokoding: i tillegg `gate` (adressekode+gatenavn), `adresse.posisjon/husnr/
bokstav` og `geokoding='matrikkel'` - den autoritative statusen, se
`db/schema_kjerne_dokumentasjon.md`. Fyller ved bygningstreff (alltid forsøkt,
også for adresser som var løst fra før): `bygning.bygningsnr`, `bygningstype`
(Matrikkelens rå kodeverdi, ikke oversatt til navn ennå), `bra_m2`,
`antall_etasjer` og `matrikkel_match='adresse'`. Mislykkes bygningsoppslaget
(ingen/flere bygg funnet, API-feil, eller bygg uten bygningsnummer), settes
`matrikkel_match='ikke_funnet'` i stedet - uten dette ville et forsøkt-men-
mislykket oppslag sett identisk ut som et som aldri ble forsøkt. Overskriver
aldri en `'adresse'`-match adressesteget nettopp satte for samme bygg.

```bash
docker exec portico_masterdb psql -U postgres -d masterdb -tA -F'|' -c "
    SELECT a.id, a.adressetekst, a.postnummer, a.poststed, k.kommunenr,
           a.bygning_id, a.geokoding, a.gate_id, a.husnr, a.bokstav, g.adressekode
    FROM adresse a
    JOIN bygning b ON b.id = a.bygning_id
    JOIN kommune k ON k.id = b.kommune_id
    LEFT JOIN gate g ON g.id = a.gate_id
    WHERE a.er_hovedadresse AND a.geokoding <> 'manuell' AND a.adressetekst IS NOT NULL
      AND (a.geokoding IN ('ukjent','feilet') OR b.bygningsnr IS NULL
           OR NOT EXISTS (SELECT 1 FROM matrikkelinfo m WHERE m.bygning_id = b.id));
" > etl/ut/adresser_a_matrikkelsoke.txt

python3 etl/matrikkel_adresse.py < etl/ut/adresser_a_matrikkelsoke.txt > etl/ut/matrikkel.sql

docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/matrikkel.sql
```

Reelt resultat ved nasjonal testkjøring (alle 12 kommuner, 399 adresser):
278 geokodet (70 %), 121 feilet og loggført i `synk_avvik`. Feilårsakene er
enten ekte stave-/formatfeil Matrikkelen heller ikke kan matche (f.eks.
«Wolfsgate 12x» mot det offisielle «Wolffs gate»), eller mangler husnummer
helt i kildedata (f.eks. «Festplassen», «Nygårdsparken») - et
datakvalitetsproblem i kilden, ikke noe et adresseoppslag kan løse.

## Gater for hele kommunen (`gate`)

`gate` fylles på to måter. `matrikkel_adresse.py` legger inn gaten til hver
adresse den løser. `hent_gater.py` henter i tillegg *alle* veger i kommunen
(`AdresseService.findVegerForKommune`, så adressekode og navn via
`StoreService.getObjects`), uten at kommunen trenger en Aktiv kommune-instans,
bygg eller adresser. Det eneste som kreves er en rad i `kommune`.

Daemonen kjører steget bare én gang: etter den første bygget av en tom
database (rekkefølge: bygging, gater, geokoding), for *alle* kommuner i
`kommune`. Det kjøres ikke ved senere oppstarter og ikke om natten. Etter det
holdes `gate` oppdatert ved å kjøre steget for hånd (se under), for eksempel
for en ny kommune eller for å fange nye og omdøpte gater. En kommune der
henting feilet (logget i `synk_avvik`, kilde `matrikkel-gate`) prøves på nytt
neste gang steget kjøres for den. Gater slettes aldri, siden `adresse.gate_id`
peker på dem.

```bash
docker compose exec etl ./run.sh gater              # alle kommuner
docker compose exec etl ./run.sh gater 4601 5601    # bestemte kommuner
```

Trygt å kjøre om igjen: eksisterende gater beholder id-en, så `adresse.gate_id`
peker fortsatt riktig.

## Kjent forenkling

`kommune_id` settes i dag fra hvilken Aktiv kommune-instans dataene kommer
fra (`bergen` → kommunenr 4601). Det stemmer for alle 12 instansene som
finnes i dag. Skjemaet støtter at en instans betjener flere kommuner
(tabellen `kommune_fagsystem_instans`); den dagen det faktisk skjer for en av
instansene vi laster fra, må `kommune_id` i stedet utledes fra en geokodet
adresse, ikke fra instansen.
