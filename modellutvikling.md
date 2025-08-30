# Inputdokument for AI-modellutvikling: Integrasjon av masterdatabase med matrikkelinformasjon og anleggsdata

## 1. Målsetting

Etablere en masterdatabase som integrerer data fra flere lignende databaseinstanser (lokale databaser med bygnings- og anleggsdata) og supplerer med informasjon fra autoritative registre som matrikkelen og det nasjonale anleggsregisteret.


## 2. Datakilder

- **Matrikkel**: Autorativ for bygningsnummer, gatenummer, husnummer, eiendomsdata
- **Lokale driftsdatabaser**: Anleggsdetaljer, bookingstatus, driftsmeldinger, tekniske data
- **Nasjonalt anleggsregister**: Strukturert katalog over tekniske installasjoner
- **Fagsystemer for**:
  - Leie av lokaler
  - Drift og ressursforvaltning

---


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

- Eksterne forespørselssvar og oppdateringsprotokoller

---


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

2. Tjenestevalg

- Adresse/lett oppslag: Adresse-API (offentlig) for adresser og koordinater.
- Autorative matrikkeldata: Matrikkel Web Services (SOAP) og/eller WFS/WMS (lisensiert).
- Masseoppdatering: Periodiske uttrekk via Geonorge/FTP der det er hensiktsmessig.

3. ETL og modelltilpasning

- Hente data til «staging», validere, normalisere og mappe til master-IDer.
- Feltvis prioritet: Sett Matrikkel som autorativ for identitet (gnr/bnr/fnr/snr, bygningsnummer, adresser).
- Proveniens: lagre kilde, sist oppdatert og autorativ-status per felt.

4. Drift

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

Tips:

- Bruk `properties_json` for hele Pset-innholdet, og speil kun søkbare nøkler i `ifc_property`.
- Sørg for konsekvente navn/units (f.eks. `Effekt_kW`).

### 10.3 Eksempel: lekeapparat plassert på uteområde

Dette viser et lekeapparat som plasseres direkte på et uteområde (utenfor bygg), med valgfri posisjon.

        -- 1) Opprett produkt (kan være generisk eller IFC-klassifisert)
        INSERT INTO ifc_product (entity, predefined_type, name, properties_json, kilde, ekstern_id, lon, lat)
        VALUES (
            'CustomEquipment',           -- eller f.eks. 'IfcFurnishingElement'
            'PLAY_EQUIPMENT',
            'Lekeapparat – huske',
            '{"materiale":"tre","alder_6_12":true}',
            'FDV',
            'fdv:play:huske:001',
            10.7461, 59.9127             -- valgfritt: posisjon (ETRS89/EPSG:4258)
        );

        -- 2) Plasser det på et uteområde (angi riktig uteomraade_id)
        INSERT INTO ifc_product_location (product_id, uteomraade_id)
        SELECT product_id, 42  -- erstatt 42 med faktisk uteomraade_id
        FROM ifc_product
        WHERE kilde='FDV' AND ekstern_id='fdv:play:huske:001';

        -- 3) (Valgfritt) Klassifiser i eget skjema eller kjent kodeverk
        INSERT INTO classification (scheme, code, title)
        VALUES ('CUSTOM','PLAY_EQUIPMENT','Lekeapparat')
        ON CONFLICT DO NOTHING;

        INSERT INTO product_classification (product_id, class_id)
        SELECT p.product_id, c.class_id
        FROM ifc_product p, classification c
        WHERE p.kilde='FDV' AND p.ekstern_id='fdv:play:huske:001'
          AND c.scheme='CUSTOM' AND c.code='PLAY_EQUIPMENT';

Merk:

- `ifc_product_location` støtter `uteomraade_id` i tillegg til bygg/fløy/etasje/rom. Minst én av disse må være satt.
- Koordinater (`lon`/`lat`) er valgfrie, men nyttige for kart og nærmeste-adkomst.


## 11. Proveniens og kontekstsensitiv ruting til fagsystemer

Denne løsningen samler autorative data (Matrikkel) og supplerer med lokale data pr. kommune (f.eks. «Aktiv kommune» for booking) samt FDV/andre fagsystemer. Målet er at brukeren ikke trenger å velge kommune; systemet leder automatisk til riktig instans basert på kontekst og valgt ressurs.

- Proveniens (kilde, ekstern_id, autoritativ)
  - Alle kjerne-tabeller har feltene: kilde, kilde_ref, sist_oppdatert, autoritativ.
  - Eksterne nøkler per objekt (ekstern_id) brukes sammen med kilde for oppslag og idempotente oppdateringer.
  - Prioritetsregler: Matrikkel er autoritativ for eiendomsidentitet (gnr/bnr/fnr/snr, adresser, bygningsnr). Andre kilder kan være autoritative for tekniske/operative felt.

- Kommune-kontekst
  - Bygning forankres via bydel → kommune.
  - Uteområde forankres via bydel → kommune (evt. matrikkelenhet).
  - Adresser og matrikkelenheter bærer kommunenr. Dermed kan en valgt ressurs entydig kobles til kommune.

- Fagsystemkobling (konsepter)
  - Fagsystem: navn og type (booking, FDV, sensordata, …).
  - Fagsystem-instans: én instans per kommune (base-URL, API-nøkler, teknisk metadata).
  - Ressurslenke: kobler master-ressurs (bygg/rom/uteområde/produkt) til korrekt fagsystem-instans med ekstern nøkkel for gitt kontekst (booking/FDV).
  - Klassifisering: brukes for enkel filtrering/ruting (f.eks. hvilke produkter tilhører FDV vs. booking).

- Ruteprosess (booking-eksempel)
  1. Bruker velger en ressurs (f.eks. gymsal) i master-UI.
  2. Systemet finner ressursens kommune via bygg/bydel/kommune (eller via adresse/matrikkelenhet).
  3. Slå opp Ressurslenke for kontekst=booking → hent fagsystem-instans (Aktiv kommune for aktuell kommune) og ekstern_id.
  4. Redirect eller kall API med base-URL fra instansen og ekstern_id fra lenken.
  5. Status/kvittering speiles tilbake i master (leser via samme lenke).

- FDV/andre kilder (komponenter/utstyr)
  - ifc_product kan representere både IFC og ikke-IFC utstyr (ifc_guid valgfritt) med ekstern_id+kilde.
  - ifc_product_location forankrer objekter i bygg/etasje/rom eller uteområde.
  - Egenskaper lagres i properties_json og normaliseres ved behov i ifc_property_set/ifc_property for spørringer.
  - For ruting til FDV: Ressurslenke peker produktet til riktig FDV-instans per kommune med ekstern_id fra FDV.

- Personvern og tilgang
  - Ingen persondata i ekstern_id.
  - Ruting skjer på system- og ressursnivå; tilgangskontroll og logging håndteres i både master og underliggende fagsystem.

Praktisk anbefaling

- Etabler små referansetabeller (utenfor scope i denne filen) for: fagsystem, fagsystem_instans (per kommune), ressurslenke (resource_type, resource_id, context, system_instans_id, ekstern_id).
- Hold oppslag idempotent: oppdater lenker på (resource, context) og kilde/ekstern_id uten duplikater.


## 12. Ressurser og ressurspooler (ikke-stedsbundne)

Denne seksjonen beskriver hvordan vi håndterer ressurser som ikke er permanent knyttet til et fysisk sted (utstyr på lager, mobile enheter, personer, tjenester), samt hvordan de kan organiseres i ressurspooler og rutes til riktig fagsystem på samme måte som stedbundne objekter.

- Formål
  - Modellere “ressurser” (utstyr, personell, tjenester) som kan brukes/planlegges uavhengig av bygg/rom.
  - Samle ressurser i navngitte pooler (for eksempel «Vaktmesterteam sentrum», «Låneutstyr skole A»).
  - Ruting: samme kontekstsensitive mekanisme som for bygg/rom/IFC, men på ressursnivå.
- Tabeller (skisse, se `db/schema.sql` for detaljer)
  - `ressurs`
    - type: equipment | person | service | other.
    - enten koblet til `ifc_product` ELLER identifisert via `(kilde, ekstern_id)`; CHECK sikrer “minst én identitet”.
    - proveniensfelt: kilde, kilde_ref, sist_oppdatert, autoritativ.
    - unikhet: delvis UNIQUE på `(kilde, ekstern_id)` når ekstern_id finnes.
  - `ressurspool`
    - navngitt samling per kommune; UNIQUE (kommune_id, navn).
    - type: booking | staffing | equipment | other.
  - `ressurspool_medlem`
    - M:N mellom pool og ressurs.
    - gyldighetsintervall (gyldig_fra, gyldig_til) med CHECK (fra < til) eller åpen slutt.
  - `ressurslenke` (utvidet)
    - nå også `ressurs_id` i tillegg til bygg/bruksenhet/rom/uteområde/ifc_product.
    - CHECK «eksakt én referanse er satt» er oppdatert til å inkludere `ressurs_id`.
    - unikhet: (instans_id, context, ekstern_id) og, for ressurs-lenker, UNIQUE (context, instans_id, ressurs_id).

- Samspill med ruting (seksjon 11)
  - Ruting til fagsystemer gjenbruker `fagsystem` og `fagsystem_instans`.
  - Når en forespørsel gjelder en ressurs (context f.eks. booking), slås `ressurslenke` opp på `(instans_id, context, ressurs_id)` for å finne ekstern identitet i riktig instans.
  - Overlappende ekstern-ID’er på tvers av instanser håndteres ved at unikhet skopes per instans og kontekst.
- Eksempler
  - Opprette en ressurs (person fra HR-systemet):

        INSERT INTO ressurs (type, navn, kilde, ekstern_id, sist_oppdatert, autoritativ)

  - Opprette en pool og legge til medlem med gyldighet:

        INSERT INTO ressurspool (kommune_id, navn, type)
        VALUES (42, 'Vaktmesterteam Sentrum', 'staffing')
        RETURNING id;

        INSERT INTO ressurspool_medlem (pool_id, ressurs_id, gyldig_fra)
        VALUES (<pool_id>, <ressurs_id>, CURRENT_DATE);

  - Rute en bookingforespørsel for en ressurs:
    1) Finn instansen for booking i kommunen: `SELECT i.id, i.base_url FROM fagsystem_instans i JOIN fagsystem f ON f.id=i.fagsystem_id WHERE f.type='booking' AND i.kommune_id = <kommune_id>;`
    2) Finn ekstern-ID for ressursen i denne instansen: `SELECT ekstern_id FROM ressurslenke WHERE context='booking' AND instans_id = <instans_id> AND ressurs_id = <ressurs_id>;`
    3) Kall fagsystemets API med `base_url` og `ekstern_id`.

  - Nyttige spørringer
  - Aktive medlemmer i en pool på en dato:

        SELECT r.*
        FROM ressurspool_medlem m
        JOIN ressurs r ON r.id = m.ressurs_id
        WHERE m.pool_id = <pool_id>
          AND (m.gyldig_fra IS NULL OR m.gyldig_fra <= CURRENT_DATE)
          AND (m.gyldig_til IS NULL OR m.gyldig_til >= CURRENT_DATE);

  - Alle lenker for en ressurs i en gitt kontekst (for eksempel booking):

        SELECT i.base_url, l.ekstern_id
        FROM ressurslenke l
        JOIN fagsystem_instans i ON i.id = l.instans_id
        WHERE l.context = 'booking' AND l.ressurs_id = <ressurs_id>;

---

## 13. Semantisk graf som parallell utvidelse (valgfritt)

Denne utvidelsen skisserer hvordan en semantisk kunnskapsgraf kan kjøres parallelt med den relasjonelle masterdatabasen, uten å erstatte Postgres-skjemaet. Målet er å tilby SPARQL, standardiserte begreper (ontologi) og regel-/valideringslag (OWL/SHACL) på tvers av kilder.

### 13.1 Motivasjon (hvorfor)

- Felles semantikk for heterogene kilder (BOT, SOSA/SSN, GeoSPARQL, IFC-OWL + et lett lokalt namespace).
- Multihopp-spørringer (bygg → etasje → rom → utstyr → system → sensor) uten kompliserte JOIN-kjeder.
- Datakvalitet og samsvar: SHACL-kontrakter og lettvekts-inferens (OWL RL/EL) for avledede relasjoner.
- Identitetsforening: modellere og «binde» flere eksterne identiteter til én masteridentitet.
- Løs kobling: utvikle begreper og regler uten å endre databaseskjemaet.
- Federering: slå opp eksterne vokabularer/kataloger via SPARQL SERVICE.

### 13.2 Arkitekturoppsett

To komplementære mønstre:

1. Virtuell graf (OBDA/R2RML) over Postgres
   - Verktøy: Ontop eller Apache Jena. Mappinger beskriver hvordan tabeller/visninger fremstår som RDF ved spørring.
   - Fordeler: ingen ETL/duplisering; rask å ta i bruk; SPARQL direkte fra masterdata.
   - Avveiing: svært tunge grafer kan være trege; krever god indeksering og bevisst spørring.

2. Materialisert graf (triplestore) med løpende oppdatering
   - Verktøy: GraphDB, Fuseki, Blazegraph/Neptune m.fl.
   - Synk: CDC (Debezium) eller batch-eksporter fra Postgres.
   - Fordeler: ytelse for komplekse grafer/inferens; dedikert cachelag.
   - Avveiing: drift/ETL-kompleksitet og duplisering som må styres (proveniens/versjon).

Anbefaling: start virtuelt (OBDA); materialiser selektivt ved behov.

### 13.3 Integrasjonspunkter mot modellen

- IRI-strategi: stabile IRIs pr. entitet (kommune/bygn./rom/ifc_product) basert på primærnøkler.
- Ontologi: gjenbruk standardvokabularer og supplér med et «pe:»-namespace for prosjektspesifikke begreper.
- Identitet: eksponer eksterne IDer (f.eks. owl:sameAs/skos:exactMatch) i tråd med identitetslenker i DB.
- Proveniens: dct:source, prov:wasDerivedFrom, dct:modified for kilde/autorativitet/tidsstempel.
- Geometri: WKT/GeoSPARQL-literals i første omgang; PostGIS-binding senere.
- Ruting: modeller fagsystem/instans/ressurslenke i grafen for å forklare «hvorfor» forespørsler rutes.

### 13.4 Minimum første leveranse

- En liten mappingpakke (R2RML/RML) for: kommune, matrikkelenhet, bygning, etasje, rom, ifc_product.
- En SQL-view som genererer IRIs deterministisk (f.eks. per tabell).
- 3–5 SPARQL-eksempler (rom i bygg X, utstyr i rom Y, produkter i system Z).
- Kort README for å kjøre Ontop lokalt mot Postgres med mappingene.

Foreslått struktur (senere): db/semantic/ med ontology.ttl, mapping/*.ttl, README.md.

### 13.5 Sikkerhet og tilgang

- Speil tilgangsregler fra master-DB. Bruk named graphs for å skille kommune/tenant/domene.
- Ikke map felter med begrenset tilgang (personopplysninger) til grafen.
- Loggfør spørringer; vurder rate limiting for åpne endepunkt.

### 13.6 Ytelse og drift

- Cache hyppige spørringer; vurder delvis materialisering for tunge analyser.
- Begrens inferens til det som trengs (RL/EL) eller kjør batch-inferens.
- Etabler SHACL-shapes for viktige integritetskrav (bygg–etasje–rom, klassifikasjon, etc.).

### 13.7 Kom i gang (kort)

1. Lag en enkel IRI-view i databasen.
2. Skriv en R2RML-mapping for «bygning» og «rom».
3. Start et OBDA-endepunkt (Ontop) mot Postgres og test med SPARQL.
4. Utvid trinnvis med flere entiteter, identiteter og proveniens.

Dette gir SPARQL og semantikk over masterdata uten å endre datalaget og kan tas i bruk selektivt der det gir mest verdi.
