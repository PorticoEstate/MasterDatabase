# Dokumentasjon av testSchema.sql

## Sammendrag

`testSchema.sql` definerer en PostgreSQL-database for kommunale bygg, rom, uteområder og bookbare ressurser. Skjemaet er bygget rundt to hoveddomener:

1. **Eiendom/bygg-struktur** — kommune, bydel, bygning, etasje, rom, adresse, uteområde og flater (baner/løyper). Dette dekker den fysiske strukturen.
2. **Booking-/aktivitetsdomene** — aktivitet, fasilitet, ressurskategori, ressurs og organisasjon. Dette dekker data hentet fra kommunale booking-/aktivitetssystemer (eksemplifisert ved JSON-eksportene i `ak-aktivitetsanalyse-master/searchdataall-<kommune>.json`).

Skjemaet inneholder **ingen matrikkeldata** (gårds-/bruksnummer, festenummer, seksjonsnummer). Denne delen er bevisst fjernet, se [Endringslogg](#endringslogg-matrikkel-og-booking-domenet). All adresse er dermed vegadresse-basert.

**Viktig personvernmerknad:** tabellen `organisasjon` kan komme til å inneholde personopplysninger (navn, telefon, e-post, adresse til privatpersoner/kontaktpersoner) dersom den fylles med data fra kilder som inneholder slikt. Avklar behandlingsgrunnlag, lagringstid og tilgangsbegrensning med Personvernombud/Data Privacy Officer før denne tabellen tas i bruk i produksjon.

---

## Innholdsfortegnelse

- [1. Eiendom/bygg-domenet](#1-eiendombygg-domenet)
- [2. Adresse](#2-adresse)
- [3. Uteområder og flater](#3-uteområder-og-flater)
- [4. Klassifisering](#4-klassifisering)
- [5. Booking-/aktivitetsdomenet](#5-booking-aktivitetsdomenet)
- [6. Ressurspooler](#6-ressurspooler)
- [7. Fagsystemer og ruting](#7-fagsystemer-og-ruting)
- [8. Gjennomgående konvensjoner](#8-gjennomgående-konvensjoner)
- [9. Kobling mot kilde-JSON (aktivitetsanalyse per kommune)](#9-kobling-mot-kilde-json-aktivitetsanalyse-per-kommune)
- [10. Kjente hull og videre arbeid](#10-kjente-hull-og-videre-arbeid)
- [Endringslogg: matrikkel og booking-domenet](#endringslogg-matrikkel-og-booking-domenet)

---

## 1. Eiendom/bygg-domenet

### `kommune`
Norske kommuner. `kommunenr` er det offisielle 4-sifrede kommunenummeret.

| Kolonne | Type | Merknad |
|---|---|---|
| kommune_id | BIGSERIAL PK | |
| kommunenr | CHAR(4) | Unik, må matche `^[0-9]{4}$` |
| navn | TEXT | |
| geom_wkt | TEXT | Geometri som WKT (uten PostGIS) |
| ekstern_id, kilde, kilde_ref | TEXT | Sporbarhet til kildesystem (se pkt. 9) |
| sist_oppdatert, autoritativ | | Provenance |

### `bydel`
Bydeler/delområder innenfor en kommune. `UNIQUE (kommune_id, navn)`.

### `bygning`
Fysiske bygg. Utvidet med kontakt- og bookingfelter (se [Endringslogg](#endringslogg-matrikkel-og-booking-domenet)):

| Kolonne | Type | Merknad |
|---|---|---|
| bygg_id | BIGSERIAL PK | |
| bygningsnr | BIGINT UNIQUE | |
| bydel_id | FK → bydel | |
| bygningstype, status | TEXT | |
| byggeaar, antall_etasjer, bra_m2 | | |
| aktivitet_id | FK → aktivitet | Hovedkategori for bygget |
| telefon, epost, hjemmeside, apningstider | TEXT | Kontaktinfo |
| tilsyn_navn/telefon/epost (+ `_2`-variant) | TEXT | Tilsynskontakt(er) |
| metadata_json | JSONB | Øvrige booking-flagg uten egen kolonne (f.eks. kalenderinnstillinger) |

### `floy` (fløy)
Fysisk del av et bygg. `UNIQUE (bygg_id, navn)`.

### `etasje`
Etasjer i et bygg. `UNIQUE (bygg_id, nummer)`.

### `bruksenhet`
En bruksenhet tilhører alltid en bygning (`bygg_id NOT NULL`) — det finnes ingen matrikkelbasert kobling lenger.

### `rom`
Rom i en bruksenhet/etasje/fløy. `UNIQUE (bruksenhet_id, nummer)`.

---

## 2. Adresse

### `gate`
Gatenavn per kommune. `UNIQUE (kommunenr, gatenavn)`.

### `adresse`
Kun **vegadresser** støttes (`adressetype` er låst til `'vegadresse'` via CHECK, og `gate_id` er `NOT NULL`). Kan kobles til en bygning, en bruksenhet og/eller et uteområde. Koordinater (`lat`/`lon`) må enten begge være satt eller begge `NULL` (`chk_adresse_lon_lat_both`).

---

## 3. Uteområder og flater

### `uteomraade_type`
Kodeverk for uteområdetyper (park, lekeplass, fotballbane, idrettsbane — forhåndsutfylt).

### `uteomraade`
Utendørs områder, knyttet til bydel og en type. Kan refereres fra `adresse` (via `fk_adresse_uteomraade`, satt opp etter at begge tabeller finnes).

### `adkomstpunkt`
Inngang/port/rampe/parkering til et uteområde.

### `flate`
Generisk "flate" (bane, trasé, løype) som enten ligger i et rom **eller** i et uteområde — akkurat én av `rom_id`/`uteomraade_id` må være satt (`chk_flate_one_location`). Har egen kilde/ekstern_id-sporbarhet.

### `flate_rel_aggregates`
Kombinasjon/oppdeling av flater (f.eks. to små baner som utgjør én stor).

---

## 4. Klassifisering

### `classification`
Eksterne klassifiseringsskjema (NS 3451, TFM, Omniclass). `UNIQUE (scheme, code)`.

### `flate_classification`
Kobler en `flate` til én eller flere `classification`-koder.

---

## 5. Booking-/aktivitetsdomenet

Dette domenet ble lagt til for å dekke data fra kommunale booking-/aktivitetssystemer (se pkt. 9).

### `aktivitet`
Kodeverk for aktivitetstyper (f.eks. "Kultur", "Idrett"). Selvrefererende via `parent_id` for hierarki.

### `fasilitet`
Kodeverk for fasiliteter/utstyr tilknyttet en ressurs (f.eks. "Garderobe").

### `ressurskategori`
Kodeverk for kategorisering av ressurser (f.eks. "Overnatting"). Selvrefererende via `parent_id`. Har `capacity` og `e_lock` som ekstra attributter.

### `organisasjon` ⚠️
Klubber/lag/kontaktpersoner. **Kan inneholde personopplysninger** — se personvernmerknaden i sammendraget.

### `ressurs`
Generisk bookbar ressurs (utstyr, person, tjeneste, annet). Kan kobles til en `flate` (1:1, valgfritt) og en `ressurskategori`. `metadata_json` tar unna systemspesifikke booking-innstillinger. Krever `kilde` og `ekstern_id` satt (`chk_ressurs_ident`).

### Koblingstabeller (mange-til-mange)
| Tabell | Kobler |
|---|---|
| `ressurs_aktivitet` | ressurs ↔ aktivitet |
| `ressurs_fasilitet` | ressurs ↔ fasilitet |
| `ressurskategori_aktivitet` | ressurskategori ↔ aktivitet |
| `bygning_ressurs` | bygning ↔ ressurs (direkte, uten rom/bruksenhet i mellom) |

---

## 6. Ressurspooler

### `ressurspool`
Gruppering av ressurser (booking, staffing, equipment, other), valgfritt scopet til en kommune. `UNIQUE (kommune_id, navn)`.

### `ressurspool_medlem`
Medlemskap av en `ressurs` i en `ressurspool`, med rolle, prioritet og gyldighetsperiode (`gyldig_til > gyldig_fra` håndheves).

---

## 7. Fagsystemer og ruting

### `fagsystem`
Katalog over fagsystemtyper (booking, fdv, sensor, annet).

### `fagsystem_instans`
En instans av et fagsystem, med `base_url` og fri `konfig_json`. Kan betjene én eller flere kommuner — koblingen ligger i `fagsystem_instans_kommune`, ikke som egen kolonne her.

### `fagsystem_instans_kommune`
Mange-til-mange-kobling mellom `fagsystem_instans` og `kommune`. Gjør det mulig for én instans (f.eks. en delt/regional instans) å betjene flere kommuner, og for én kommune å bruke flere instanser (av samme eller forskjellige fagsystem). `PRIMARY KEY (instans_id, kommune_id)`.

### `ressurslenke`
Kobler en master-ressurs (bygg, bruksenhet, rom, uteområde **eller** ressurs — akkurat én) til riktig fagsystem-instans for en gitt kontekst (booking/fdv/sensor/annet), med ekstern identifikator i fagsystemet.

---

## 8. Gjennomgående konvensjoner

- **Provenance-felter**: de fleste tabeller har `kilde`, `kilde_ref`, `ekstern_id`, `sist_oppdatert` og `autoritativ` for å spore hvor data kommer fra og hvilken kilde som er autoritativ ved konflikt.
- **Tidsstempler**: `created_at`/`updated_at` med `DEFAULT now()` på alle egne tabeller.
- **Unik ekstern identitet**: mønsteret `UNIQUE INDEX ... (kilde, ekstern_id) WHERE kilde IS NOT NULL AND ekstern_id IS NOT NULL` brukes gjennomgående for å unngå duplikatimport fra samme kildesystem.
- **Geometri uten PostGIS**: `geom_wkt` (tekst-WKT) og enkle `lat`/`lon`/`srid`-kolonner brukes i stedet for PostGIS-typer.

---

## 9. Kobling mot kilde-JSON (aktivitetsanalyse per kommune)

Repoet inneholder eksempeldata i `ak-aktivitetsanalyse-master/searchdataall-<kommune>.json` (én fil per kommune, f.eks. `searchdataall-bergen.json`). Disse filene inneholder nøklene `activities`, `buildings`, `building_resources`, `facilities`, `resources`, `resource_activities`, `resource_facilities`, `resource_categories`, `resource_category_activity`, `towns` og `organizations`.

| JSON-nøkkel | Skjema-tabell | Merknad |
|---|---|---|
| `activities` | `aktivitet` | |
| `buildings` | `bygning` (+ `adresse`, `gate`) | Adressefelter (`street`, `zip_code`, `city`) må splittes ut i `gate`/`adresse` |
| `facilities` | `fasilitet` | |
| `resource_categories` | `ressurskategori` | |
| `resources` | `ressurs` (+ `metadata_json` for booking-config) | |
| `resource_activities` | `ressurs_aktivitet` | |
| `resource_facilities` | `ressurs_fasilitet` | |
| `resource_category_activity` | `ressurskategori_aktivitet` | |
| `building_resources` | `bygning_ressurs` | |
| `towns` | `bydel` (+ `bygning.bydel_id`) | Er en kobling bygning→bydel, ikke frittstående "byer" |
| `organizations` | `organisasjon` | ⚠️ Inneholder personopplysninger |

**Kommunenummer finnes ikke i JSON-filene** — kommunen identifiseres kun via filnavnet (f.eks. `bergen`). Bruk `kommune.kilde` (f.eks. `'aktivitetsanalyse'`) og `kommune.ekstern_id` (f.eks. `'bergen'`) til å lagre denne koblingen ved import. Dette krever ingen skjemaendring.

---

## 10. Kjente hull og videre arbeid

- `buildings.district` i kildedataene stemmer ikke alltid overens med bydelsnavnet i `towns` (observert i Bergen-datasettet: 69 av 127 rader avvek). Bruk `towns`-koblingen som fasit for bydel, ikke `district`-feltet.
- Adressefelt fra kilden (`street`, `zip_code`, `city`) er fritekst og må parses/normaliseres før de kan settes inn i strukturerte `gate`/`adresse`-rader.
- Ingen validering/RLS er satt opp for `organisasjon` ennå — bør vurderes før produksjonsbruk (se personvernmerknad).
- Skjemaet er ikke kjørt/validert mot en live database etter siste endringer (brukeren valgte å teste selv).
- ⚠️ **VIKTIG: Ingen constraint hindrer at én kommune kobles til to forskjellige instanser av *samme* fagsystem** via `fagsystem_instans_kommune` (PK er kun `(instans_id, kommune_id)`, som ikke kjenner til `fagsystem_id`). Eksempel: kommune 42 kobles til både `instans_id=1` og `instans_id=2`, der begge har `fagsystem_id=5` — da er det tvetydig hvilken `base_url` som er "riktig" Active-instans for kommune 42. Dette hindres **ikke** av databasen i dag; **må** håndteres i applikasjonslogikk eller en trigger før dette tas i bruk med flere kommuner/instanser i praksis.

---

## Endringslogg: matrikkel og booking-domenet

**Fjernet (matrikkeldata skal ikke lagres):**
- Tabellen `matrikkelenhet` og dens unike indeks.
- Tabellen `bygning_matrikkelenhet` (kobling bygning↔matrikkelenhet) og dens indeks.
- Kolonnen `matrikkelenhet_id` i `bruksenhet`, `adresse` og `uteomraade`.
- Adressetypen `'matrikkeladresse'` i `adresse.adressetype` (kun `'vegadresse'` gjenstår, satt som default).
- CHECK-constrainten `chk_adresse_type_gate_parcel` (overflødig med kun én adressetype).
- Indeksen `ix_adresse_matrikkelenhet`.

**Konsekvensendringer av fjerningen:**
- `bruksenhet.bygg_id` er nå `NOT NULL` (eneste kobling til fysisk bygg).
- `adresse.gate_id` er nå `NOT NULL` (eneste adressetype er vegadresse).

**Lagt til (for å dekke booking-/aktivitetsdata):**
- Nye tabeller: `aktivitet`, `fasilitet`, `ressurskategori`, `organisasjon`.
- Nye koblingstabeller: `ressurs_aktivitet`, `ressurs_fasilitet`, `ressurskategori_aktivitet`, `bygning_ressurs`.
- Ny kolonne `ressurs.kategori_id` (FK til `ressurskategori`).
- Nye kolonner på `bygning`: `aktivitet_id`, `telefon`, `epost`, `hjemmeside`, `apningstider`, `tilsyn_navn/telefon/epost` (+ `_2`), `metadata_json`.

**Lagt til (fagsystem_instans <-> kommune som mange-til-mange):**
- `fagsystem_instans.kommune_id` og `CONSTRAINT uniq_fagsystem_per_kommune` er fjernet — en instans er ikke lenger bundet til akkurat én kommune.
- Ny relasjonstabell `fagsystem_instans_kommune (instans_id, kommune_id)` med `PRIMARY KEY (instans_id, kommune_id)`, slik at én instans kan betjene flere kommuner (f.eks. en delt/regional instans), og én kommune kan bruke flere instanser.
- Indeksen `ix_fagsystem_instans_kommune` (på `fagsystem_instans.kommune_id`) er fjernet og ersattet med `ix_fagsystem_instans_kommune_kommune` (på `fagsystem_instans_kommune.kommune_id`).
- Kjent hull etter denne endringen: se punktet om tvetydig fagsystem-kobling under [Kjente hull og videre arbeid](#10-kjente-hull-og-videre-arbeid).
