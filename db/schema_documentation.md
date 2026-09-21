# Masterdatabase for kommunale lokaler og anlegg

Referansedokumentasjon for `db/schema_perfect.sql`.

## Innhold

1. [Formål og premisser](#1-formål-og-premisser)
2. [Arkitektur i fire lag](#2-arkitektur-i-fire-lag)
3. [Tverrkommunalt søk: kjernemekanismen](#3-tverrkommunalt-søk-kjernemekanismen)
4. [Tabellreferanse](#4-tabellreferanse)
5. [Identitet og feltautoritet](#5-identitet-og-feltautoritet)
6. [Ruting til fagsystem](#6-ruting-til-fagsystem)
7. [Hva som bevisst ikke ligger i basen](#7-hva-som-bevisst-ikke-ligger-i-basen)
8. [Lastestrategi](#8-lastestrategi)
9. [Eksempelspørringer](#9-eksempelspørringer)
10. [Endringer fra schema_magnus.sql](#10-endringer-fra-schema_magnussql)
11. [Kjente begrensninger og åpne spørsmål](#11-kjente-begrensninger-og-åpne-spørsmål)

---

## 1. Formål og premisser

Databasen skal la en innbygger eller en frivillig organisasjon søke etter en **type lokale** — «gymsal med garderobe», «7er-kunstgress», «øvingsrom» — uten først å måtte velge kommune. I dagens løsning er hver kommune en separat Aktiv kommune-instans, og et lokale i nabokommunen er usynlig med mindre brukeren vet at det finnes og bytter instans manuelt.

Basen er bygget på fem premisser:

**Master er et definisjons- og rutingslag.** Den eier identitet, plassering, klassifisering og lenker. Den eier ikke bookinger, kalendere, sanntidsdata eller saksbehandling — det ligger i kommunens fagsystem.

**Matrikkelen er autoritativ for eiendomsidentitet.** Bygningsnummer, gårds- og bruksnummer, adresser og representasjonspunkter kommer fra Kartverket og overstyrer tilsvarende felt fra fagsystemene.

**Fagsystemene er autoritative for tilbudet.** Hvilke lokaler som finnes, hva de heter utad, og om de kan bookes, eies av kommunens bookingløsning.

**Klassifisering er masterens eget ansvar.** Kommunenes lokale kodeverk er innbyrdes uforenlige og kan ikke brukes direkte til søk på tvers. Master holder ett kuratert kodeverk og kartlegger de lokale kodene inn mot det.

**Ingen personopplysninger.** Se [kapittel 7](#7-hva-som-bevisst-ikke-ligger-i-basen).

Skjemaet krever PostgreSQL 12 eller nyere, siden søkevektoren er en generert kolonne, og er testet mot PostgreSQL 18. Det har ingen PostGIS-avhengighet; geometri lagres som WKT-tekst med `lon`/`lat` og `srid` ved siden av.

---

## 2. Arkitektur i fire lag

```
                       ┌──────────────────────────────┐
   MATRIKKELEN   ────▶  │  Lag 1: Eiendom og bygning   │
   (Kartverket)         │  matrikkelenhet, bygning,    │
                        │  etasje, floy, rom, adresse, │
                        │  uteomraade, flate           │
                        └──────────────┬───────────────┘
                                       │ plassering
                        ┌──────────────▼───────────────┐
   AKTIV KOMMUNE  ────▶ │  Lag 2: Bookbar ressurs      │
   (12 instanser)       │  ressurs (+ aggregering)     │
                        └──────────────┬───────────────┘
                                       │
                ┌──────────────────────┴──────────────────────┐
                │                                             │
   ┌────────────▼─────────────┐              ┌────────────────▼──────────────┐
   │  Lag 3: Søkefasetter     │              │  Lag 4: Ruting                │
   │  lokaletype, aktivitet,  │              │  fagsystem, fagsystem_instans,│
   │  fasilitet               │              │  ressurslenke                 │
   │  + kildekode/-mapping    │              │  + ledighet_cache             │
   └──────────────────────────┘              └───────────────────────────────┘
```

**Lag 1** er den fysiske virkeligheten, i hovedsak fra matrikkelen. Her er identiteten stabil over tid.

**Lag 2** er det som kan bookes. `ressurs` er plassert i lag 1 gjennom valgfrie fremmednøkler til bygning, fløy, etasje, rom, uteområde og flate.

**Lag 3** gjør lag 2 søkbart på tvers av kommuner. Dette er laget som løser hovedproblemet.

**Lag 4** sender brukeren videre til riktig kommunes fagsystem.

---

## 3. Tverrkommunalt søk: kjernemekanismen

Dette er den viktigste delen av modellen, så den fortjener en begrunnelse.

### Problemet

Hver Aktiv kommune-instans har sitt eget kodeverk for lokaletype, aktivitet og fasilitet, med lokale heltalls-ID-er. Disse ID-ene kolliderer på tvers av kommuner med helt ulik betydning. Faktiske tall fra de tolv instansene:

| Kodeverk | Lokal ID-kollisjon | Eksempel |
|---|---|---|
| `resource_categories` | 58 av 63 ID-er har mer enn én betydning | ID 13 = «Overnatting» i Bergen, «Skateanlegg» i Stavanger |
| `activities` | 48 konflikter mellom Bergen og Stavanger alene | ID 82 = «Privat arrangement» / «Sykling» |
| `facilities` | 56 av 60 ID-er i konflikt | ID 2 = «Garderobe» / «Kapasitet 1-20» |

Navnene lar seg heller ikke bruke direkte. På tvers av de tolv instansene finnes 142 distinkte kategorinavn, og de inneholder:

- **Målformvarianter** — `Gressbane`/`Grasbane`, `Kunstgressbane`/`Kunstgrasbane`, `Basseng - symjehall`
- **Skrivefeil og kasus** — `Sermonirom` mot `Seremonirom`, `Foaje` mot `Foajé`, `Ateliet`, `arrangementslokale`
- **Synonymer på ulike nivåer** — `Friidrettsanlegg`, `Friidrettsbane`, `Friidrettshall`
- **Verdier som ikke er lokaletyper i det hele tatt** — `Stengt`, `Fiktivt rom`, `Streaming`, `Kantinebidrag`, `Inkludering`, og stedsnavn som `Judaberg innbyggertorg`, `Kvitsøygata 3`, `Mostun Natursenter`
- **Utstyr blandet inn i lokaletypelisten** — `Sykler`, `EL-sykler`, `Kano`, `Kajakk`, `Bålpanne`, `Fiskestengar`, `Redningsvestar`

Et søk som matcher på lokal kode eller på rå navnetekst vil derfor gi feil treff eller ingen treff.

### Løsningen

Tre tabeller i kjede:

```
kildekode  ──▶  kildekode_mapping  ──▶  lokaletype / aktivitet / fasilitet
(rå lokal kode)   (kuratert påstand)       (kanonisk kodeverk)
```

**`kildekode`** lagrer den lokale koden uendret, nøklet på `(instans_id, kodetype, kode)`. Fordi `instans_id` er med i nøkkelen, kan Bergens ID 13 og Stavangers ID 13 eksistere side om side uten å kollidere. Tabellen normaliseres aldri og rettes aldri — den er kildens sannhet, og den er sporet med `forste_sett` og `sist_sett` slik at nye koder oppdages automatisk ved neste synk.

**`kildekode_mapping`** er en kartlegging fra en lokal kode til én kanonisk verdi. Den bærer `status`, `konfidens`, `kartlagt_av` og `kartlagt_at`, fordi kartleggingen er en menneskelig vurdering og ikke en beregning. Statusverdiene:

| Status | Betydning |
|---|---|
| `foreslatt` | Automatisk forslag, ikke kvalitetssikret. Brukes ikke i søk. |
| `godkjent` | Kvalitetssikret. Brukes i søk. |
| `avvist` | Forslaget var feil. Beholdes for å unngå at samme forslag genereres på nytt. |
| `ikke_relevant` | Kildekoden er ikke en lokaletype. Håndterer `Stengt`, `Fiktivt rom` og stedsnavnene. |

CHECK-regelen `chk_kildekode_mapping_ett_mal` krever nøyaktig ett kanonisk mål for `foreslatt` og `godkjent`, og ingen mål for `avvist` og `ikke_relevant`.

**`lokaletype`**, **`aktivitet`** og **`fasilitet`** er masterens egne kodeverk. De to første er hierarkiske via `parent_id`, slik at et søk på hovedgruppen `IDRETT` også treffer `GYMSAL` og `IDRETTSHALL`. `fasilitet` er flat men gruppert via `gruppe`, som lar grensesnittet vise fasetter samlet («Tilgjengelighet», «Teknisk», «Kjøkken»).

Skjemaet seeder et startsett på 80 lokaletyper, 28 aktiviteter og 35 fasiliteter, utledet fra de faktiske 142 kategorinavnene ved å slå sammen målform, skrivefeil og synonymer.

### Kuratering som løpende arbeid

Visningen `v_ukartlagte_kildekoder` er arbeidslisten. Hver rad er en lokal kode som ennå ikke kan søkes på tvers av kommuner. Når en ny kommune kobles til, eller en kommune legger inn en ny kategori, dukker den opp her.

Kartleggingen bør ligge som en versjonert fil i repoet og lastes inn derfra, ikke redigeres direkte i basen. Da kan en fagperson rette den uten kodeendring, og endringen kan gjennomgås i en pull request.

---

## 4. Tabellreferanse

### 4.1 Administrativ inndeling

| Tabell | Beskrivelse |
|---|---|
| `kommune` | Kommunenummer, navn, fylke. `kommunenr` er CHAR(4) med formatsjekk. |
| `bydel` | Valgfri inndeling under kommune. Finnes i Bergen og Stavanger, ikke i de små kommunene. |

### 4.2 Matrikkel

| Tabell | Beskrivelse |
|---|---|
| `matrikkelenhet` | Grunneiendom, festegrunn, seksjon, anleggseiendom, jordsameie. Unik på `(kommunenr, gardsnr, bruksnr, festenr, seksjonsnr, anleggsnr)` med COALESCE, siden de tre siste er NULL for vanlige grunneiendommer. |
| `bygning_matrikkelenhet` | M:N mellom bygning og matrikkelenhet, med `rolle` og `dekningsgrad`. Et bygg kan stå på flere eiendommer. |
| `bruksenhet` | Boenhet eller næringsenhet under en matrikkelenhet. |

### 4.3 Bygning og struktur

| Tabell | Beskrivelse |
|---|---|
| `bygning` | Bygg eller anlegg. Har både `navn` (publikumsvennlig, fra fagsystem) og `bygningsnr` (matrikkelens nøkkel). |
| `floy` | Fløy i et bygg. |
| `etasje` | Etasje i et bygg, unik på `(bygg_id, nummer)`. |
| `rom` | Rom i et bygg. |

Tre designvalg her fortjener forklaring.

**`bygning.kommune_id` er NOT NULL og redundant.** Kommune kan i prinsippet utledes via `bydel`, men `bydel_id` er nullbar og de fleste kommuner har ingen bydeler. Uten en direkte kobling ville tverrkommunalt søk måtte gå gjennom en nullbar kjede, og gruppering per kommune ville tape rader. Redundansen er bevisst.

**`rom.bygg_id` er NOT NULL.** I forrige versjon kunne et rom ha NULL i alle foreldrekolonner og bli helt foreldreløst. Samtidig var unikhetsregelen `UNIQUE (bruksenhet_id, nummer)` virkningsløs når `bruksenhet_id` var NULL, fordi PostgreSQL behandler NULL som ulik seg selv i unike indekser. Det ga stille duplikater ved hver reload. Nå er bygget obligatorisk, og romnummer er valgfritt men unikt innenfor bygget når det finnes.

**Sammensatte fremmednøkler garanterer at strukturen henger sammen.** `etasje`, `floy` og `rom` har alle en ekstra `UNIQUE (id, bygg_id)`. Det lar `rom` og `ressurs` bruke fremmednøkler på `(rom_id, bygg_id)` i stedet for bare `(rom_id)`. Effekten er at databasen avviser en ressurs som hevder å ligge i bygg A men i et rom som tilhører bygg B:

```
ERROR:  insert or update on table "ressurs" violates foreign key constraint "fk_ressurs_rom"
DETAIL:  Key (rom_id, bygg_id)=(1, 3) is not present in table "rom".
```

Dette er en vanlig feilklasse i ETL fra flere kilder, og den fanges her deklarativt uten triggere.

### 4.4 Adresse

| Tabell | Beskrivelse |
|---|---|
| `gate` | Gatenavn per kommune, med `adressekode` fra matrikkelen. |
| `adresse` | Veg- eller matrikkeladresse. Kan høre til bygning, bruksenhet eller uteområde — høyst én av dem. |

`adresse.geokoding_status` skiller hvordan koordinatene er fremskaffet: `matrikkel` (autoritativt representasjonspunkt), `geokodet` (oppslag mot Adresse-API), `manuell`, `feilet` eller `ukjent`. Uten dette skillet ville en senere matrikkelimport ikke kunne vite om den trygt kan overskrive et usikkert geokodingsresultat.

`ux_adresse_hovedadresse_bygg` sikrer at et bygg har høyst én hovedadresse, mens det fortsatt kan ha flere innganger registrert som egne adresser.

### 4.5 Uteområde og flate

| Tabell | Beskrivelse |
|---|---|
| `uteomraade_type` | Kodeverk: park, lekeplass, idrettsanlegg, nærmiljøanlegg, friluftsområde, torg, badeplass, annet. |
| `uteomraade` | Utendørs område, forankret i kommune og eventuelt bydel og matrikkelenhet. |
| `adkomstpunkt` | Inngang, port, rampe, parkering, HC-parkering, holdeplass. Kan høre til uteområde eller bygning. Har `universell_utforming`. |
| `flate` | Den fysiske spilleflaten: bane, flate, trasé, løype. Har `dekke`, `lengde_m`, `bredde_m`. |
| `flate_rel_aggregates` | Sammenslåing og deling: to halve baner som utgjør én stor. |

`flate` krever **minst én** forankring til rom, uteområde eller bygning, ikke nøyaktig én. Den forrige versjonen krevde nøyaktig én av rom eller uteområde, som gjorde det umulig å registrere en innendørs bane i en hall der rommene ikke er kartlagt. `chk_flate_inne_ute` hindrer at samme flate hevdes å være både inne og ute.

### 4.6 Ressurs

`ressurs` er den søkbare og bookbare enheten, og tabellen som gjenoppretter funksjonaliteten `ifc_product` og `ifc_product_location` hadde.

| Kolonnegruppe | Innhold |
|---|---|
| Identitet | `ressurs_id`, `kommune_id` (NOT NULL), `ekstern_id` + `kilde` (begge NOT NULL) |
| Klassifisering | `type`, `lokaletype_id` |
| Egenskaper | `kapasitet`, `kapasitet_kilde`, `areal_m2`, `beskrivelse` på bokmål, nynorsk og engelsk |
| Plassering | `bygg_id`, `floy_id`, `etasje_id`, `rom_id`, `uteomraade_id`, `flate_id` |
| Status | `aktiv`, `bookbar`, `skjult` |
| Søk | `sokevektor` — generert `tsvector` med norsk stemming, GIN-indeksert |
| Proveniens | `kilde_ref`, `sist_oppdatert`, `autoritativ` |

`type` er én av `lokale`, `anlegg`, `bane`, `utstyr`, `tjeneste`, `annet`. Dette er en direkte utvidelse av den gamle listen, som bare hadde `equipment`, `person`, `service` og `other` — altså ingen verdi som passet et lokale. En gymsal er verken utstyr, person eller tjeneste, og kunne dermed ikke registreres.

`kapasitet_kilde` finnes fordi kapasitet nesten aldri er utfylt i kildedata: 2 av 590 ressurser i Bergen, 3 av 371 i Stavanger. Stavanger koder det i stedet som fasilitet («Kapasitet 1-20», «9 seter»). Verdien må derfor kunne utledes eller settes manuelt, og opphavet må følge den.

Tre CHECK-regler styrer plasseringen:

| Regel | Innhold |
|---|---|
| `chk_ressurs_plassering` | Stedbundne typer må ha bygg, uteområde eller flate. Utstyr og tjenester kan være mobile. |
| `chk_ressurs_innedel_krever_bygg` | Rom, etasje og fløy krever at bygget er satt. |
| `chk_ressurs_inne_eller_ute` | En ressurs kan ikke være både i et bygg og på et uteområde. |

Tilknyttede tabeller:

| Tabell | Beskrivelse |
|---|---|
| `ressurs_aktivitet` | M:N mot kanonisk aktivitet. Motsvarer `resource_activities` i kilden. |
| `ressurs_fasilitet` | M:N mot kanonisk fasilitet, med `antall` og `merknad`. Motsvarer `resource_facilities`. |
| `ressurs_classification` | M:N mot eksterne standardkodeverk. |
| `ressurs_rel_aggregates` | Sammenstilling: storsal delbar i tre, hall med to baner. `utelukker_hverandre` markerer at forelder og barn ikke kan bookes samtidig. Erstatter `ifc_rel_aggregates`. |

### 4.7 Ressurspool

| Tabell | Beskrivelse |
|---|---|
| `ressurspool` | Navngitt samling per kommune, type `booking`, `utstyr`, `drift` eller `annet`. |
| `ressurspool_medlem` | M:N med gyldighetsintervall. |

### 4.8 Drift og sporing

| Tabell | Beskrivelse |
|---|---|
| `kildeuttrekk` | Rått JSON-svar fra kilden med tidsstempel, HTTP-status og SHA-256. Lar en last kjøres om igjen uten nye kall, og gjør uttrekket revisjonsbart. |
| `synk_kjoring` | Én rad per ETL-kjøring med antall lest, opprettet, oppdatert og avvist. |
| `synk_avvik` | Én rad per forkastet eller uavklart kilderad, med type og rådata. |
| `ledighet_cache` | Forkastbar cache for ledige tider. Se [kapittel 6](#6-ruting-til-fagsystem). |

`synk_avvik` finnes av en konkret grunn. `searchdataall` er et delvis uttrekk: koblingstabellene eksporteres rått mens `resources` og `buildings` er filtrert. Målt på faktiske data:

| Kommune | `building_resources` | Ukjent `resource_id` | Ukjent `building_id` |
|---|---:|---:|---:|
| Bergen | 980 rader | 388 | 28 |
| Stavanger | 489 rader | 125 | 40 |

I tillegg har Stavanger 11 ressurser med `rescategory_id` som ikke finnes i kommunens egen kategoriliste. En last med fremmednøkkelhåndheving vil avvise tusenvis av rader. De må filtreres bort, men de skal loggføres, ikke svelges stille — ellers oppdages det ikke hvis andelen plutselig dobles.

---

## 5. Identitet og feltautoritet

### Flere eksterne identiteter per objekt

Et bygg har som regel flere eksterne identiteter samtidig: et bygningsnummer i matrikkelen og en lokal ID i hvert fagsystem. Kolonnene `kilde` og `ekstern_id` på tabellen kan bare holde én av dem.

`identitetslenke` holder resten. Den bruker samme mønster som `ressurslenke`: én nullbar fremmednøkkel per objekttype og en CHECK som krever nøyaktig én. Dermed får koblingene reell fremmednøkkelintegritet, i motsetning til en polymorf `(objekt_type, objekt_id)`-løsning.

`match_status` og `konfidens` finnes fordi matching mot matrikkelen sjelden er sikker. Aktiv kommune oppgir ikke bygningsnummer i det hele tatt — bare gateadresse, postnummer og poststed. En kobling basert på adressematch er en kvalifisert gjetning, og den må kunne merkes `sannsynlig` og senere overprøves uten at identiteten slettes.

### Hvilken kilde vinner

`feltautoritet` uttrykker prioritetsreglene som data i stedet for kode: `(tabellnavn, feltnavn, kilde, prioritet)`. Skjemaet seeder et startsett:

| Tabell | Felt | Kilde | Prioritet |
|---|---|---|---|
| `bygning` | `bygningsnr`, `bygningstype`, `byggeaar`, `bra_m2`, `geom_wkt` | matrikkel | 100 |
| `bygning` | `navn`, `hjemmeside`, `apningstid_tekst` | aktiv-kommune | 80 |
| `adresse` | `lat`, `lon`, `adressetekst` | matrikkel | 100 |
| `ressurs` | `navn` | aktiv-kommune | 100 |
| `ressurs` | `kapasitet` | manuell (90) over aktiv-kommune (60) |
| `ressurs` | `lokaletype_id` | manuell | 100 |

ETL-en leser denne tabellen og oppdaterer bare felt der den innkommende kilden har prioritet minst like høy som den som sist skrev feltet. Mønsteret er lettere å endre enn kode fordi en ny kilde bare krever nye rader, og fordi en fagperson kan lese og etterprøve reglene.

---

## 6. Ruting til fagsystem

| Tabell | Beskrivelse |
|---|---|
| `fagsystem` | Systemkatalog med type `booking`, `fdv`, `sensor`, `matrikkel` eller `annet`. |
| `fagsystem_instans` | Én rad per system og kommune, med `base_url`, `konfig_json` og `kildenokkel`. |
| `ressurslenke` | Kobler et masterobjekt til riktig instans for en gitt kontekst, med ekstern nøkkel. |

`fagsystem_instans.kildenokkel` er verdien som brukes i `kilde`-kolonnene ellers i basen, for eksempel `aktiv-kommune:bergen`. Den er nødvendig fordi de lokale heltalls-ID-ene overlapper på tvers av kommuner: ressurs 438 finnes i flere instanser og betyr forskjellige ting. Sammen med `ekstern_id` gir `kildenokkel` en globalt entydig nøkkel, og partielle unike indekser på `(kilde, ekstern_id)` gjør oppdateringer idempotente.

### Ruteflyt for booking

1. Brukeren finner en ressurs i søket.
2. `ressurs.kommune_id` gir kommunen direkte, uten å gå via bydel.
3. `ressurslenke` slås opp på `(kontekst='booking', ressurs_id)`.
4. `fagsystem_instans.base_url` og `ressurslenke.ekstern_path` settes sammen til mål-URL.
5. Brukeren sendes videre, eller fagsystemets API kalles og svaret normaliseres.

Visningen `v_ressurs_uten_bookinglenke` viser ressurser som søket kan finne men ikke rute videre fra. Den bør være tom i produksjon.

### Ledighetscache

`ledighet_cache` er en ren cache med `gyldig_til` og kan trunkeres når som helst uten tap av masterdata. Den bryter ikke premisset om at master ikke lagrer bookinger — den lagrer ikke hvem som har booket, bare om det finnes ledige tider.

Den finnes av ytelseshensyn. Et søk som skal svare på «ledig gymsal førstkommende lørdag» på tvers av tolv kommuner kan ikke gjøre tolv synkrone API-kall per tastetrykk. Cachen fylles av en bakgrunnsjobb for ressurser som faktisk søkes på, med kort levetid, og `har_ledighet` gir et indeksert boolsk filter. Selve bookingen går alltid mot fagsystemet i sanntid.

---

## 7. Hva som bevisst ikke ligger i basen

### Organisasjons- og persondata

`searchdataall` returnerer en `organizations`-samling med 5 906 rader på tvers av de tolv kommunene. Stikkprøver viser at en betydelig andel er **privatpersoner**: navnefeltet inneholder et personnavn, `organization_number` er tomt, og radene har privat mobilnummer, privat e-postadresse og hjemmeadresse med postnummer.

Denne samlingen lastes ikke. Søkefunksjonen trenger den ikke — den beskriver søkere, ikke lokaler.

Tilsvarende utelates `buildings.tilsyn_name`, `tilsyn_phone`, `tilsyn_email` og de tilsvarende `*2`-feltene, som er navngitte kontaktpersoner. `bygning` har i stedet `epost` og `telefon`, som **kun** skal fylles med funksjonelle adresser av typen `idrettsetaten@bergen.kommune.no`. Feltet `resources.contact_info` er fritekst som kan inneholde navn, og utelates.

`ressurslenke.ekstern_id` skal aldri inneholde personopplysninger.

> Behandlingsgrunnlag, dataminimering og vurdering av om `organizations` i det hele tatt bør ligge på et uautentisert endepunkt, må avklares med Capgeminis Data Privacy Officer og med kommunene som behandlingsansvarlige. Dette dokumentet tar ikke stilling til det rettslige spørsmålet.

### Bookinger, kalendere og sanntidsdata

Ligger i fagsystemet. Master holder lenken, ikke innholdet.

### Bookingregelverk

Kildedata har rundt tjue kolonner med bookingregler på `resources`: `booking_time_minutes`, `cancellation_deadline_value`, `booking_month_horizon`, `deny_application_if_booked`, `activate_prepayment` og flere. Disse lastes ikke, fordi de er fagsystemets forretningslogikk og endres uten at master varsles. Hvis søket senere skal vise «kan bookes inntil 3 måneder fram», hentes det i sanntid.

### Personell og bemanning

Den forrige modellen tillot `ressurs.type = 'person'` og `ressurspool.type = 'staffing'`. Begge er tatt ut. Bemanningsplanlegging krever opplysninger om identifiserbare ansatte, og hører til i et HR- eller FDV-system, ikke i en publikumsrettet søkebase.

Dette er et bevisst valg som fjerner en mulighet som fantes før. Skal bemanning inn igjen, må det gjøres som en egen vurdering med eget behandlingsgrunnlag.

---

## 8. Lastestrategi

Datamengden er liten. Samlet fra de tolv instansene: 425 bygg, 1 805 ressurser, 418 bydelskoblinger, 2 661 bygg-ressurs-koblinger. Omtrent 6 MB JSON i alt. Dette er modellarbeid og datavask, ikke et skaleringsproblem.

### Steg 1 — Rå landing

Hent `https://<kommune>.aktiv-kommune.no/bookingfrontend/searchdataall` per instans og lagre hele svaret i `kildeuttrekk`. Tolv kall. Uttrekket blir revisjonsbart, og transformasjonen kan kjøres om igjen uten å belaste kommunenes systemer.

### Steg 2 — Normaliser til staging

Én staging-tabell per samling, med `kildenokkel` som del av nøkkelen. Her gjøres to opprydninger:

**Dobbel HTML-avkoding.** Ressursnavn kommer som `Rom 19 &amp;#40;219&amp;#41;`. Det er `&#40;` escapet én gang for mye, altså `(` etter to runder avkoding. `description_json` inneholder `&lt;p&gt;`-escapet HTML. Uten dette havner rå entiteter i søkeindeksen.

**Referansefiltrering.** Junction-rader som peker på ukjente foreldre filtreres bort og loggføres i `synk_avvik` med `avvikstype = 'manglende_forelder'`.

### Steg 3 — Kildekoder og kartlegging

Upsert alle `resource_categories`, `activities` og `facilities` til `kildekode`, med oppdatert `sist_sett`. Nye koder får automatisk et forslag i `kildekode_mapping` med status `foreslatt`, basert på normalisert navn. Forslagene kvalitetssikres manuelt og settes til `godkjent` eller `ikke_relevant`.

Målt på faktiske data er dette 142 distinkte kategorinavn, 264 fasilitetsnavn og 332 aktivitetsnavn på tvers av de tolv instansene. Førstegangs kuratering er et par dagers arbeid. Deretter er det marginalt, siden `v_ukartlagte_kildekoder` bare viser det nye.

### Steg 4 — Upsert til master

I avhengighetsrekkefølge:

```
kommune → bydel → fagsystem → fagsystem_instans
        → bygning → etasje/floy → rom
        → uteomraade → flate
        → ressurs → ressurs_aktivitet/_fasilitet
        → ressurslenke
```

Alle upserts går på `ON CONFLICT (kilde, ekstern_id) DO UPDATE`, med `kilde` satt til instansens `kildenokkel`.

### Steg 5 — Matrikkelberikelse

Kartverkets **Adresse-API** er åpent og krever ingen avtale. Slå opp `street` + `zip_code` og skriv `lat`, `lon`, `adressetekst` og `adressekode` til `adresse`, med `geokoding_status = 'geokodet'`. Dette steget er nødvendig fordi **kildedata ikke inneholder koordinater i det hele tatt** — ingen av de tolv instansene har lat, lon, UTM, geometri eller matrikkelreferanse. Uten geokoding finnes ingen «i nærheten av meg», som er halve poenget med tverrkommunalt søk.

**Matrikkeldata** (bygningsnummer, bygningstype, byggeår, BRA, gårds- og bruksnummer, bygningsomriss) krever avtale med Kartverket og dokumentert behandlingsgrunnlag, og hentes via Matrikkel Web Services eller periodiske uttrekk fra Geonorge. Når de er på plass:

1. Match bygg mot matrikkelen på adresse, og registrer treffet i `identitetslenke` med `match_status` etter hvor sikkert det er.
2. Oppdater `bygning`-felt der `feltautoritet` gir matrikkelen prioritet.
3. Sett `geokoding_status = 'matrikkel'` når representasjonspunktet erstatter et geokodet punkt.

Rekkefølgen er viktig: Aktiv kommune lastes først fordi den definerer hvilke bygg som er relevante, og matrikkelen beriker etterpå.

### Steg 6 — Ledighet

Fylles ikke i initiallasten. Bakgrunnsjobb per ressurs ved behov, med kort `gyldig_til`.

> Ledighetsendepunktet er ikke identifisert. `/bookingfrontend/availability`, `/freetime`, `/schedule` og `/bookings` svarer alle 404. `/bookingfrontend/buildings` finnes derimot som ekte JSON, og returnerer felt `searchdataall` mangler, blant annet `town_id` og `active`. Det tyder på et bredere API som bør avklares med leverandøren framfor å kartlegges ved gjetting.

### Verktøyvalg

`httpx` og `psycopg` er tilstrekkelig. Seks megabyte fra tolv kilder rettferdiggjør ikke dbt eller Airflow; et `make`-mål som kjører stegene i rekkefølge er lettere å overlevere og feilsøke.

---

## 9. Eksempelspørringer

### Finn gymsal med garderobe, uansett kommune

```sql
SELECT navn, kommune_navn, bygg_navn, kapasitet, adressetekst, lat, lon
FROM v_ressurs_sok
WHERE lokaletype_kode = 'GYMSAL'
  AND 'GARDEROBE' = ANY(fasilitet_koder);
```

### Søk på hovedgruppe, slik at undertyper treffer

```sql
WITH RECURSIVE gren AS (
    SELECT lokaletype_id FROM lokaletype WHERE kode = 'IDRETT'
    UNION ALL
    SELECT lt.lokaletype_id FROM lokaletype lt JOIN gren g ON lt.parent_id = g.lokaletype_id
)
SELECT s.navn, s.kommune_navn, s.lokaletype_navn
FROM v_ressurs_sok s
WHERE s.lokaletype_id IN (SELECT lokaletype_id FROM gren);
```

### Fritekstsøk med norsk stemming

```sql
SELECT navn, kommune_navn,
       ts_rank(sokevektor, to_tsquery('norwegian', 'garderobe & parkett')) AS rang
FROM v_ressurs_sok
WHERE sokevektor @@ to_tsquery('norwegian', 'garderobe & parkett')
ORDER BY rang DESC;
```

### Ressurser innenfor en kartutsnitt, med aktivitetsfilter

```sql
SELECT navn, kommune_navn, lat, lon
FROM v_ressurs_sok
WHERE lat BETWEEN 60.30 AND 60.50
  AND lon BETWEEN 5.20 AND 5.45
  AND 'HANDBALL' = ANY(aktivitet_koder);
```

### Finn ruting for en valgt ressurs

```sql
SELECT r.navn, fs.type, fi.base_url || COALESCE(rl.ekstern_path, '') AS mal_url, rl.ekstern_id
FROM ressurs r
JOIN ressurslenke rl        ON rl.ressurs_id = r.ressurs_id AND rl.kontekst = 'booking' AND rl.aktiv
JOIN fagsystem_instans fi   ON fi.instans_id = rl.fagsystem_instans_id
JOIN fagsystem fs           ON fs.fagsystem_id = fi.fagsystem_id
WHERE r.ressurs_id = $1;
```

### Hvordan en lokal kode ble tolket

```sql
SELECT fi.kildenokkel, kk.kode AS lokal_kode, kk.navn AS lokalt_navn,
       lt.kode AS kanonisk_kode, m.status, m.konfidens, m.kartlagt_av
FROM kildekode kk
JOIN fagsystem_instans fi        ON fi.instans_id = kk.instans_id
LEFT JOIN kildekode_mapping m    ON m.kildekode_id = kk.kildekode_id
LEFT JOIN lokaletype lt          ON lt.lokaletype_id = m.lokaletype_id
WHERE kk.kodetype = 'lokaletype'
ORDER BY fi.kildenokkel, kk.kode;
```

### Datakvalitet etter siste kjøring

```sql
SELECT k.kilde, k.status, k.antall_lest, k.antall_opprettet, k.antall_oppdatert, k.antall_avvist,
       a.avvikstype, count(*) AS antall
FROM synk_kjoring k
LEFT JOIN synk_avvik a ON a.kjoring_id = k.kjoring_id
WHERE k.startet_at > now() - interval '1 day'
GROUP BY 1,2,3,4,5,6,7
ORDER BY k.kilde, antall DESC;
```

---

## 10. Endringer fra schema_magnus.sql

### Det som ble borte da IFC-tabellene ble fjernet

Fjerningen av `ifc_product` og følgetabellene tok med seg én sentral funksjon som ikke ble erstattet: **en identifiserbar, bookbar ting plassert et sted i bygnings- eller uteområdestrukturen.** `ifc_product_location` bar plasseringen mot bygg, fløy, etasje, rom og uteområde, og `ifc_rel_aggregates` bar sammenstillinger.

Etter fjerningen fantes ingen tabell som kunne holde en gymsal: `rom` manglet proveniensfelt og kunne ikke oppdateres idempotent, `flate` krevde nøyaktig én av rom eller uteområde, og `ressurs` hadde ingen `type` som passet et lokale og kunne bare peke til `flate` — ikke til bygg eller rom.

`ressurs` i denne versjonen overtar rollen, uten IFC-apparatet rundt.

### Tabelloversikt

**Nye tabeller (15):** `lokaletype`, `aktivitet`, `fasilitet`, `kildekode`, `kildekode_mapping`, `ressurs_aktivitet`, `ressurs_fasilitet`, `ressurs_classification`, `ressurs_rel_aggregates`, `identitetslenke`, `feltautoritet`, `ledighet_cache`, `kildeuttrekk`, `synk_kjoring`, `synk_avvik`.

**Nye visninger (3):** `v_ressurs_sok`, `v_ukartlagte_kildekoder`, `v_ressurs_uten_bookinglenke`.

**Ingen tabeller fjernet.**

### Endringer på eksisterende tabeller

| Tabell | Endring | Begrunnelse |
|---|---|---|
| `bygning` | `navn` og `ekstern_id` lagt til | Kunne ikke lagre «Flaktveit stadion», og hadde ingen plass til fagsystemets bygg-ID. Idempotent upsert var umulig. |
| `bygning` | `kommune_id NOT NULL` lagt til | Bydel finnes ikke i de fleste kommuner, så `bydel → kommune` var en nullbar kjede. |
| `bygning` | `bygningsnr` fra `UNIQUE` til partiell unik indeks | Bygg kjent bare fra fagsystem har ikke bygningsnummer. |
| `bygning` | `lon`, `lat`, `hjemmeside`, `epost`, `telefon`, `apningstid_tekst`, `aktiv` lagt til | Kildedata har disse; ingen målplass fantes. |
| `rom` | `bygg_id NOT NULL`, `nummer` gjort nullbar | Rom kunne bli foreldreløst, og `UNIQUE (bruksenhet_id, nummer)` var virkningsløs når `bruksenhet_id` var NULL. |
| `rom`, `etasje`, `floy` | Proveniensfelt lagt til | Uten `kilde`/`ekstern_id` kunne ingenting oppdateres idempotent. |
| `rom`, `etasje`, `floy` | `UNIQUE (id, bygg_id)` lagt til | Muliggjør sammensatte fremmednøkler som garanterer at strukturen henger sammen. |
| `ressurs` | `type` utvidet med `lokale`, `anlegg`, `bane`; `person` fjernet | Ingen av de gamle verdiene passet et lokale. `person` fjernet av personvernhensyn. |
| `ressurs` | Plasseringskolonner, `kommune_id`, `kapasitet`, `lokaletype_id`, `sokevektor` m.m. lagt til | Overtar rollen til `ifc_product_location`. |
| `ressurs` | `ekstern_id` og `kilde` gjort NOT NULL | CHECK-en krevde dem allerede; nå er det synlig i kolonnedefinisjonen. |
| `flate` | «Nøyaktig én lokasjon» endret til «minst én», `bygg_id` lagt til | En innendørs bane i en hall uten kartlagte rom kunne ikke registreres. |
| `adresse` | `adressetekst`, `geokoding_status`, `er_hovedadresse` lagt til | Skiller geokodede treff fra autoritative matrikkelkoordinater. |
| `gate` | `kommunenr`-referanse byttet til `kommune_id` | Konsistens; refererte tidligere en UNIQUE-kolonne framfor primærnøkkelen. |
| `classification` | `parent_class_id`, `beskrivelse` lagt til | Standardkodeverk er hierarkiske. |
| `fagsystem_instans` | `kildenokkel` lagt til | Binder `kilde`-verdiene i basen til instansen de kommer fra. |
| `ressurslenke` | `flate_id` lagt til som subjekt | Flater var ikke direkte rutbare. |
| Alle | `updated_at`-trigger lagt til | Kolonnene fantes, men ble aldri oppdatert — bare satt ved INSERT. |
| Alle | `NOT NULL DEFAULT FALSE` på boolske flagg, områdesjekker på areal og årstall | Tretilstands-boolske verdier gir stille feil i filtrering. |

### Validering

Skjemaet er kjørt mot PostgreSQL 18. Det er idempotent ved gjentatt kjøring, oppretter 39 tabeller og 3 visninger, og seeder 80 lokaletyper, 28 aktiviteter, 35 fasiliteter, 8 uteområdetyper og 15 feltautoritetsregler.

Integritetsreglene er verifisert med negative tester. Databasen avviser: rom som tilhører et annet bygg enn ressursen hevder, stedbundne ressurser uten plassering, romreferanse uten byggreferanse, ressurs som er både inne og ute, duplikat på `(kilde, ekstern_id)`, godkjent kartlegging uten kanonisk mål, ressurslenke med flere subjekter, og kommunenummer med feil format. `updated_at`-triggeren er bekreftet å fyre.

---

## 11. Kjente begrensninger og åpne spørsmål

### Begrensninger i modellen

**Geometri uten PostGIS.** `lon`/`lat` med btree-indeks gir grei ytelse på kartutsnitt, men ikke på radiussøk eller avstandssortering. Nærhetssøk må for nå gjøres med en bounding box og etterfiltrering i applikasjonen. Migrering til `geography(Point, 4326)` med GiST-indeks er rett fram og bør vurderes når nærhetssøk blir et hovedgrep i grensesnittet.

**Feltautoritet håndheves ikke av basen.** `feltautoritet` er en policytabell som ETL-en må lese og respektere. Databasen hindrer ikke en klient fra å skrive et matrikkelfelt med data fra et fagsystem.

**Ett kanonisk lokaletype per ressurs.** `ressurs.lokaletype_id` er én enkelt fremmednøkkel. Det matcher kildedata, der hver ressurs har nøyaktig én `rescategory_id`, og flerbruk dekkes av `ressurs_aktivitet`. Skal en ressurs kunne ha flere likestilte typer, må dette bli en M:N-tabell.

**Åpningstider som fritekst.** `apningstid_tekst` er ustrukturert, slik kilden har det. Strukturerte åpningstider kan ikke utledes pålitelig fra feltet, og faktisk ledighet kommer uansett fra fagsystemet.

### Åpne spørsmål

**Skal booking gjennomføres i master, eller bare søk og videresending?** Dokumentasjonen forutsetter det siste: master finner lokalet og sender brukeren til kommunens fagsystem. Skal booking gjennomføres i master, må vesentlig mer bookingregelverk speiles, og da kommer også søker-identitet inn — med de personvernkonsekvensene det har.

**Ledighetsendepunktet er ikke identifisert.** Hele sanntidsdelen av arkitekturen forutsetter at det finnes. API-dokumentasjon bør etterspørres hos leverandøren.

**Kapasitetsdekningen er svak.** Under 1 % av ressursene har kapasitet i kilden. Kapasitetsfilter i søket vil derfor skjule de fleste treff med mindre verdier fylles manuelt eller utledes. Dette bør avklares før det loves som søkefunksjon.

**Kommunelisten bør bekreftes.** Tolv instanser er verifisert å svare på `searchdataall`: bergen, stavanger, baerum, oygarden, narvik, afjord, averoy, gamvik, inderoy, nordreisa, oksnes, sogndal. Oversikten på aktiv-kommune.no er JavaScript-generert, så listen er utledet fra lenker på siden og bør kontrolleres mot leverandørens egen oversikt.

**Bygningsmatching mot matrikkelen er uavklart i presisjon.** Aktiv kommune oppgir bare gateadresse og postnummer. Treffraten for adressebasert matching bør måles på et utvalg før den brukes til å sette `autoritativ`-flagg.
