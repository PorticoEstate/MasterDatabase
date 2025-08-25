# Inputdokument for AI-modellutvikling: Integrasjon av masterdatabase med matrikkelinformasjon og anleggsdata

---

## 1. Målsetting

Etablere en masterdatabase som integrerer data fra flere lignende databaseinstanser (lokale databaser med bygnings- og anleggsdata) og supplerer med informasjon fra autoritative registre som matrikkelen og det nasjonale anleggsregisteret.

---

## 2. Datakilder

- **Matrikkel**: Autorativ for bygningsnummer, gatenummer, husnummer, eiendomsdata
- **Lokale driftsdatabaser**: Anleggsdetaljer, bookingstatus, driftsmeldinger, tekniske data
- **Nasjonalt anleggsregister**: Strukturert katalog over tekniske installasjoner
- **Fagsystemer for**:
  - Leie av lokaler
  - Skade- og vedlikeholdsmeldinger
  - Drift og ressursforvaltning

---

## 3. Masterdatabasefunksjoner

- Unik identitet for hvert bygg/anlegg via koplingstabeller
- Datavask og validering (inkl. versjonssporing og kvalitetskontroll)
- Sporing av datakilde og oppdateringsansvar
- Regelmotor som avgjør hvilke data som er autorative

---

## 4. API-krav

### Intern API

- Synkronisering med underliggende databaser
- Push/pull av oppdaterte metadata

### Ekstern API

- Integrasjon med nasjonalt anleggsregister
- Eksterne forespørselssvar og oppdateringsprotokoller

---

## 5. Kontekstuell forespørselshåndtering

- En forespørsel (som leie eller skade) skal rutes til riktig fagsystem basert på type og kontekst.
- Alle henvendelser opererer på samme bygg-ID.
- Systemet må kunne trigge hendelser mot riktig applikasjon og vise status tilbake i masterdatabasegrensesnittet.

---

## 6. Kart- og temabasert søk

- Bruk av spatial database (f.eks. PostGIS)
- Filtrering på tematiske kriterier:
  - Befolkningstetthet
  - Rasfare
  - Radon
- Resultat koblet til bygg-ID i masterdatabasen

---

## 7. Autorative regler og datasynkronisering

- Matrikkeldata har høyest prioritet for eiendomsidentifikasjon
- Anleggsregister og lokale databaser kan ha ulik aktualitet for forskjellige datatyper
- Hver datakomponent merkes med:
  - Sist oppdatert
  - Kilde
  - Autorativ status

---

## 8. Sikkerhet og tilgang

- Tilgangsstyring på fagsystemnivå
- Lesesporing og endringslogg
- Mulighet for godkjenningsflyt ved datamodifikasjoner

---

Dette dokumentet skal brukes som input til AI-generert modellutvikling og systemdesign.


---

## 9. Matrikkel: Datauttak via Kartverket (Eiendomsdata)

Oppsummert fra Kartverket: «Elektronisk tilgang til eiendomsdata» (<https://kartverket.no/api-og-data/eiendomsdata>):

- Tilgang: Data er gratis, men regulert. Det kreves lovlig behandlingsgrunnlag og avtale med Kartverket før utlevering av data fra grunnbok og matrikkel.
- Tilgangsnivå: Ulike virksomhetskategorier får ulikt omfang av opplysninger. Databehandlere kan få tilgang når de videreformidler til behandlingsansvarlige med grunnlag.
- Forpliktelser: Krav til tekniske og organisatoriske tiltak, videreføringsplikt til kunder, og etterlevelse av personvernregelverk. Brudd kan medføre stenging av tilgang.
- Bruksbegrensninger: Ikke lov å bruke til reklame/markedsføring uten samtykke.
- Søknad: Tilgang søkes via nettskjema (<https://kartverket.no/api-og-data/eiendomsdata/soknad-api-tilgang>). Kartverket vurderer vilkår for utlevering.
- Katalog: Tjenester/datasett finnes i Geonorge kartkatalog og API-oversikt.

Plan for data-pull i dette prosjektet:

1. Juridisk og tilgang

- Avklare behandlingsgrunnlag og inngå avtale med Kartverket.
- Etablere Maskinporten-klient og evt. mTLS/IP-tilgang etter krav.

1. Tjenestevalg

- Adresse/lett oppslag: Adresse-API (offentlig) for adresser og koordinater.
- Autorative matrikkeldata: Matrikkel Web Services (SOAP) og/eller WFS/WMS (lisensiert).
- Masseoppdatering: Periodiske uttrekk via Geonorge/FTP der det er hensiktsmessig.

1. ETL og modelltilpasning

- Hente data til «staging», validere, normalisere og mappe til master-IDer.
- Feltvis prioritet: Sett Matrikkel som autorativ for identitet (gnr/bnr/fnr/snr, bygningsnummer, adresser).
- Proveniens: lagre kilde, sist oppdatert og autorativ-status per felt.

1. Drift

- Håndtere rate limits og feil via retry/backoff og idempotente oppdateringer.
- Loggføre og revidere tilgang i henhold til avtale og utleveringsforskrift.


## 10. IFC-modellering av bygningskomponenter og utstyr

Denne modellen støtter innlesing og forvaltning av bygningskomponenter (arkitektur/bygg, VVS, elektro, etc.) og utstyr som er identifisert og klassifisert som IFC-objekter. Løsningen er laget for å fungere uten PostGIS (inntil videre), med mulighet for geometri som WKT og/eller lon/lat.

- Nøkkelelementer
  - `ifc_type` (IfcTypeObject): typer/produkt-familier (f.eks. IfcDoor, IfcUnitaryEquipment) med valgfri `ifc_guid` for type, `entity`, `predefined_type`, og standard egenskaper i `properties_json`.
  - `ifc_product` (IfcProduct): instanser med `ifc_guid` (GlobalId), `entity`, `predefined_type`, navn/tagg/serienr, valgfri `geom_wkt` og/eller `lon`/`lat` (med `srid`), samt frie egenskaper i `properties_json`. Kan lenkes til `ifc_type`.
  - `ifc_product_location`: plassering/tilhørighet i byggstrukturen via FK til `bygning`/`floy`/`etasje`/`rom`, og `placement_json` for lokal transformasjon (IfcLocalPlacement). Krav: minst én av disse referansene må være satt.
  - `ifc_system` og `ifc_product_system`: systemer (HVAC, EL, VVS) og medlemskap for produkter i systemer.
  - `ifc_rel_aggregates`: foreldre–barn-relasjoner (assemblies) mellom produkter.
  - `classification` og `product_classification`: kopling til eksterne klassifikasjonsskjema (f.eks. NS 3451, TFM, OmniClass).
  - Valgfritt normalisert egenskapslag: `ifc_property_set` og `ifc_property` for egenskaper som må kunne spørres effektivt per nøkkel (i tillegg til `properties_json` på type/instans).

- Relasjon til resten av modellen
  - Bygning: IFC-produkter knyttes til `bygning` via `ifc_product_location.bygg_id` og kan presiseres videre til `floy`, `etasje` og/eller `rom`.
  - Rom/Etasje/Fløy: gjør det mulig å analysere komponenter på riktig nivå (romliste, etasjekart, fløyspesifikk oversikt) uten PostGIS.
  - Matrikkel/eiendom: kobling går primært via bygg- og romhierarkiet. Der det er behov, kan produkter i uteområder modelleres som egne produkter og lenkes til `uteomraade` via adresse/posisjon (alternativt beskrives i egenskaper) inntil en dedikert kobling ønskes.
  - Proveniens: alle tabeller har feltene `kilde`, `kilde_ref`, `sist_oppdatert`, `autoritativ` for sporing og regelmotor.

- Geometri og koordinater
  - `geom_wkt` kan lagre enkel geometri i WKT. `lon`/`lat` med `srid` kan brukes for punkter. Konsistent SRID anbefales (4258 ETRS89 i denne modellen).
  - Når PostGIS tas i bruk, kan kolonnene migreres/komplementeres med geometrityper og romlige indekser.

- Bruksmønster (eksempel)
  1. Les IFC og opprett rader i `ifc_type` for hver unik kombinasjon av `entity`/`predefined_type` (sett `properties_json` med Pset-defaults).
  2. Opprett `ifc_product` for hver instans med `ifc_guid`, referer til `ifc_type` ved behov, og lagre Pset-verdier i `properties_json`.
  3. Plasser instanser via `ifc_product_location` og pek til riktig `bygning`/`etasje`/`rom`.
  4. Knytt utstyr inn i `ifc_system` (via `ifc_product_system`) og bygg assemblies i `ifc_rel_aggregates`.
  5. Legg på eksterne klassifikasjoner i `classification`/`product_classification`.

- Fordeler
  - Skalerbar: JSONB for fri struktur i IFC-egenskaper, og normaliserte tabeller der spørringer krever det.
  - Integrerbar: GlobalId (`ifc_guid`) gjør det lett å synkronisere mot kildemodellen.
  - Sammenkoblet: Lokasjon via bygg/etasje/rom gir god forankring i masterdatamodellen uten hard PostGIS-avhengighet.

### 10.1 Ekstern ID på IFC-produkt (ifc_product.ekstern_id)

`ekstern_id` brukes til å knytte produkter/utstyr til eksterne kilder (FDV/BAS/SD/ERP/CMMS, sensorer o.l.) og til å modellere objekter som ikke er klassifisert i IFC.

- Formål
  - Stabil teknisk nøkkel fra kildesystemet (f.eks. «fdv:ahu:1»).
  - Muliggjør oppdateringer via upsert uten IFC GlobalId.
  - Støtter flere kilder samtidig ved å kombinere med `kilde`.

- Nøkkel og indeks
  - Det finnes indeks på `(kilde, ekstern_id)` for raske oppslag.
  - Ikke krev unik `ekstern_id` globalt; bruk alltid sammen med `kilde`.

- Matching- og upsert-regler (anbefalt)
  1. Finn eksisterende produkt på `ifc_guid` når tilgjengelig (primær nøkkel for IFC-baserte objekter).
  2. Hvis ikke funnet, forsøk match på `(kilde, ekstern_id)`.
  3. Hvis fortsatt ikke funnet, opprett nytt `ifc_product` med `entity` (f.eks. "CustomEquipment"), sett `ekstern_id` og `kilde`, og legg egenskaper i `properties_json`.
  4. Ved senere import: oppdater samme rad via `(kilde, ekstern_id)`.

- Sammenfletting av dubletter
  - Dersom samme fysiske objekt får både `ifc_guid` og `(kilde, ekstern_id)` på ulike rader, bør de flettes: behold raden med `ifc_guid`, kopier egenskaper og referanser, og oppdater/videreskriv `(kilde, ekstern_id)` til denne raden.

- Beste praksis
  - Ikke lagre personinformasjon i `ekstern_id`; hold det som en teknisk identifikator.
  - Bruk `classification`/`product_classification` for å plassere ikke-IFC-objekter i kjente kodeverk (NS 3451/TFM), selv om `entity` er generisk.
  - Oppgi `entity` og `predefined_type` konsekvent (for søk/filtrering), også for ikke-IFC-kilder.

### 10.2 Eksempel: ikke-IFC-objekt med normaliserte egenskaper

Dette eksemplet oppretter et FDV-objekt uten IFC GUID, legger egenskaper i et egenskapssett og oppdaterer dem idempotent.

```sql
-- 1) Opprett et egenskapssett (engangsoperasjon)
INSERT INTO ifc_property_set (name, description)
VALUES ('FDV_Common', 'Egenskaper fra FDV-system');

-- 2) Opprett produktet (ikke-IFC) med ekstern nøkkel fra kilden
INSERT INTO ifc_product (entity, name, tag, properties_json, kilde, ekstern_id)
VALUES (
  'CustomEquipment',
  'Ventilasjonsaggregat AHU-1',
  'AHU-1',
  '{"effekt_kw":5.5, "produsent":"X"}',
  'FDV',
  'fdv:ahu:1'
);

-- 3) Normaliser utvalgte egenskaper for spørringer/rapportering
INSERT INTO ifc_property (pset_id, product_id, name, value_text, value_num)
SELECT p.pset_id, pr.product_id, v.name, v.value_text, v.value_num
FROM (SELECT pset_id FROM ifc_property_set WHERE name='FDV_Common') p,
   (SELECT product_id FROM ifc_product WHERE kilde='FDV' AND ekstern_id='fdv:ahu:1') pr,
   (VALUES
    ('Produsent', 'X', NULL::NUMERIC),
    ('Effekt_kW', NULL::TEXT, 5.5::NUMERIC)
   ) AS v(name, value_text, value_num)
ON CONFLICT (pset_id, product_id, name)
DO UPDATE SET value_text = EXCLUDED.value_text,
        value_num  = EXCLUDED.value_num;

-- 4) (Valgfritt) Plasser objektet i modellen
INSERT INTO ifc_product_location (product_id, bygg_id, etasje_id, rom_id)
SELECT product_id, 1, NULL, 10
FROM ifc_product WHERE kilde='FDV' AND ekstern_id='fdv:ahu:1';
```

Tips:

- Bruk `properties_json` for hele Pset-innholdet, og speil kun søkbare nøkler i `ifc_property`.
- Sørg for konsekvente navn/units (f.eks. `Effekt_kW`).

