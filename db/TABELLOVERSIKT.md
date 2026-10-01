# Tabelloversikt – masterdatabasen

Kort forklaring av alle 17 tabeller i [magnusDB.sql](magnusDB.sql): attributter og relasjoner.

Alle tabeller har `created_at` og `updated_at`, og det gjentas ikke under. Primærnøkler heter `id`, og fremmednøkler heter `<tabell>_id`. Unntak er selvrefererende hierarki-kolonner, som heter `parent_id`.

## Oversikt over relasjonene

```
kommune ──< kommune_fagsystem_instans >── fagsystem_instans
   │                   │ (sammensatt FK)         │
   │                   ▼                         │
   ├──< bygning ──< adresse                      │
   │      │ └──< bygning_matrikkelenhet >── matrikkelenhet
   │      ▼                                      │
   └──< ressurs >────────────────────────────────┘
          │ ├──< ressurs_aktivitet >── aktivitet
          │ ├──< ressurs_fasilitet >── fasilitet
          │ └── lokaletype
   kildekode ──1:1── kildekode_mapping ──► lokaletype | aktivitet | fasilitet
```

## 1. Kilde og kommune

### `fagsystem_instans`
Én rad per installasjon av et fagsystem, for eksempel Aktiv kommune Bergen.

| Attributt | Forklaring |
|---|---|
| `kildenokkel` | Unik, for eksempel `aktiv-kommune:bergen`. Brukes som kildemerking. |
| `type` | `booking`, `fdv`, `sensor` eller `annet`. |
| `navn`, `base_url` | Visningsnavn og rot-URL. `base_url` brukes til å bygge booking-lenken. |
| `aktiv` | Om instansen er i bruk. |

### `kommune`
| Attributt | Forklaring |
|---|---|
| `kommunenr` | 4 siffer, unik. |
| `navn`, `fylkesnavn` | Navn og fylke. |

### `kommune_fagsystem_instans`
Mange-til-mange mellom kommune og instans.

| Attributt | Forklaring |
|---|---|
| PK `(kommune_id, fagsystem_instans_id)` | Begge er FK. |
| `type` | Kopi av instansens type. Den finnes bare for at `UNIQUE (kommune_id, type)` skal gi maks én instans per type per kommune. |

Tabellen er mål for de sammensatte FK-ene fra `bygning` og `ressurs`. Den sikrer at et bygg eller en ressurs bare kan knyttes til en instans som faktisk betjener kommunen.

## 2. Matrikkel

### `matrikkelenhet`
En eiendom i matrikkelen.

| Attributt | Forklaring |
|---|---|
| `kommunenr`, `gardsnr`, `bruksnr`, `festenr`, `seksjonsnr` | Matrikkelnummeret. Unik indeks med `COALESCE` for NULL-verdier. |
| `enhetstype` | For eksempel grunneiendom, festegrunn eller seksjon. |
| `areal_m2`, `geom_wkt` | Areal og geometri som tekst. |
| `ekstern_id`, `sist_oppdatert` | ID i matrikkelen og tidspunkt for siste oppdatering. |

## 3. Bygning og adresse

### `bygning`
Bygg og utendørs anlegg. Raden har to identiteter samtidig.

| Attributt | Forklaring |
|---|---|
| `kommune_id` | FK til `kommune`. |
| `fagsystem_instans_id`, `ekstern_id` | Identitet i bookingsystemet. Unik sammen, og NULL for bygg som bare er kjent fra matrikkelen. |
| `bygningsnr` | Identitet i matrikkelen. Unik der den finnes. |
| `navn`, `bydel_navn`, `hjemmeside`, `epost`, `telefon`, `apningstid_tekst` | Fra Aktiv kommune. Navngitte kontaktpersoner lagres ikke (personopplysninger). |
| `bygningstype`, `byggeaar`, `bra_m2`, `antall_etasjer`, `geom_wkt` | Fra matrikkelen. |
| `matrikkel_match` | Hvor sikker koblingen til matrikkelen er: `ikke_forsokt`, `bekreftet`, `sannsynlig`, `usikker` eller `ikke_funnet`. |
| `posisjon` | `geography(Point, 4326)` med GiST-indeks for nærhetssøk. |
| `aktiv`, `sist_oppdatert` | Status og tidsstempel. |

### `bygning_matrikkelenhet`
Mange-til-mange mellom bygning og matrikkelenhet. PK er `(bygning_id, matrikkelenhet_id)`. `rolle` er valgfri.

### `adresse`
Ett bygg kan ha flere adresser.

| Attributt | Forklaring |
|---|---|
| `bygning_id` | FK til `bygning`. |
| `adressetekst` | Hele gateadressen fra kilden. |
| `gatenavn`, `husnr`, `bokstav` | Fylles av senere geokoding. |
| `postnummer` | 4 siffer, validert. |
| `poststed`, `posisjon` | Poststed og punkt (geography). |
| `geokoding` | `ukjent`, `matrikkel`, `geokodet`, `manuell` eller `feilet`. Styrer hva som trygt kan overskrives. |
| `er_hovedadresse` | Maks én per bygg, håndhevet av en unik indeks. |

## 4. Kanonisk kodeverk (våre egne koder)

| Tabell | Attributter | Forklaring |
|---|---|---|
| `lokaletype` | `kode` (unik), `navn`, `parent_id`, `sortering` | Hierarki via `parent_id`, for eksempel `IDRETT` → `GYMSAL`. |
| `aktivitet` | `kode` (unik), `navn`, `parent_id`, `sortering` | Samme oppsett som `lokaletype`. Overkategoriene er `IDRETT`, `KULTUR`, `OPPLARING`, `MOTE`, `PRIVAT`, `FRIVILLIGHET`, `FRILUFT` og `INTERNT`. |
| `fasilitet` | `kode` (unik), `navn`, `gruppe`, `sortering` | Ingen hierarki. `gruppe` er en av `tilgjengelighet`, `sanitaer`, `teknisk`, `kjokken`, `sport`, `moblering`, `uteareal` eller `annet`. |

Søk på en overkategori gjøres via `parent_id`, for eksempel `WHERE a.id = :valgt OR a.parent_id = :valgt`. Ved flere nivåer brukes en rekursiv CTE.

## 5. Oversettelse fra kilde

### `kildekode`
Kildens egne koder, uendret.

| Attributt | Forklaring |
|---|---|
| `fagsystem_instans_id`, `kodetype`, `kode`, `navn` | Unik på de tre første. `kodetype` er `lokaletype`, `aktivitet` eller `fasilitet`. |
| `sist_sett` | Når koden sist ble sett i et uttrekk. |

### `kildekode_mapping`
Én-til-én med `kildekode`.

| Attributt | Forklaring |
|---|---|
| `kildekode_id` | Unik FK til `kildekode`. |
| `lokaletype_id`, `aktivitet_id`, `fasilitet_id` | Nøyaktig én er satt, unntatt når statusen er `ikke_relevant`. Da er ingen satt. |
| `status` | `foreslatt`, `godkjent` eller `ikke_relevant`. Bare `godkjent` brukes ved innlasting av ressurser. |
| `kartlagt_av`, `merknad` | Hvem som bestemte mappingen, og fritekst. |

## 6. Ressurs

### `ressurs`
Det søkbare og bookbare, for eksempel en gymsal.

| Attributt | Forklaring |
|---|---|
| `fagsystem_instans_id`, `ekstern_id` | Identitet. Unik sammen. Sammen med `base_url` gir de booking-lenken. |
| `kommune_id` | FK til `kommune`. |
| `bygning_id` | Sammensatt FK `(bygning_id, kommune_id)` mot `bygning`, slik at ressursen ikke kan ligge i et bygg i en annen kommune. |
| `lokaletype_id` | FK til `lokaletype`. NULL hvis kildekoden ikke er kartlagt. |
| `navn`, `beskrivelse`, `apningstid_tekst` | Tekstfelt. |
| `kapasitet`, `kapasitet_kilde` | Kapasitet og opphavet: `kilde`, `utledet` eller `manuell`. |
| `areal_m2` | Areal. |
| `aktiv`, `bookbar` | Status. `v_ressurs_sok` viser bare ressurser som er begge deler. |
| `sokevektor` | Generert `tsvector` (norsk) fra navn og beskrivelse, med GIN-indeks for fritekstsøk. |

### `ressurs_aktivitet` og `ressurs_fasilitet`
Mange-til-mange mellom ressurs og henholdsvis aktivitet og fasilitet. PK er de to FK-ene.

## 7. Innlasting og sporbarhet

### `kildeuttrekk`
Rått JSON-svar (`payload`) før transformasjon, med `kilde`, `endepunkt`, `hentet_at` og `http_status`. Dermed kan en last kjøres om uten nye kall mot kommunen.

### `synk_avvik`
Logg over avvik.

| Attributt | Forklaring |
|---|---|
| `kildeuttrekk_id` | Valgfri FK til `kildeuttrekk`. |
| `kilde`, `samling`, `ekstern_id`, `detalj` | Hvor avviket oppstod. |
| `avvikstype` | `manglende_forelder`, `ikke_kartlagt`, `geokoding_feilet`, `ugyldig_verdi` eller `annet`. |

**Merk:** [last_inn.py](../etl/last_inn.py) skriver i dag ikke til `kildeuttrekk`. Skriptet lagrer ikke råsvaret, så `synk_avvik.kildeuttrekk_id` blir NULL. Skriptet fyller heller ikke `matrikkelenhet`, `bygning_matrikkelenhet` eller matrikkelkolonnene på `bygning`.

## Visninger

- `v_ressurs_sok`: én flat rad per aktiv og bookbar ressurs, med kommune, lokaletype og hovedgruppe, bygg, adresse, posisjon, booking-URL og aktivitets- og fasilitetskoder.
- `v_ukartlagte_kildekoder`: arbeidslisten for kuratering. Den viser koder uten mapping eller med status `foreslatt`.
