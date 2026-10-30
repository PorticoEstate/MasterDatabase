# Kjernemodell for masterdatabasen

Dokumentasjon for `db/schema_kjerne.sql`. 19 egne tabeller, 4 visninger, pluss PostGIS' egen referansetabell `spatial_ref_sys`. Alle våre egne tabeller får data i dag, unntatt `ressurslenke` (se der).

**Krever PostGIS.** Docker-imaget er `postgis/postgis:18-3.6` (ikke rent `postgres:18`), og skjemaet starter med `CREATE EXTENSION IF NOT EXISTS postgis;`.

**Navnekonvensjon:** hver tabells primærnøkkel heter `id`. En fremmednøkkel heter `<tabellnavn den peker til>_id`, f.eks. `kommune_id` på en kolonne som peker til `kommune`. Unntak: selvrefererende hierarkikolonner (`lokaletype.parent_id`, `aktivitet.parent_id`) heter `parent_id`, ikke `lokaletype_id`, for lesbarhet.

## Hva basen skal gjøre

La en innbygger søke etter en **type lokale** — «gymsal med garderobe» — uten å velge kommune først. I dag er hver kommune en separat Aktiv kommune-instans, så et lokale i nabokommunen er usynlig.

To kilder, to roller:

| Kilde | Eier |
|---|---|
| Aktiv kommune (12 instanser) | Tilbudet: hvilke lokaler finnes, hva heter de, kan de bookes |
| Matrikkelen (Kartverket) | Bygget og stedet: bygningsnummer, type, areal (BRA), antall etasjer, gate og adressekode, eiendom (gårds- og bruksnummer), koordinat |

Master eier i tillegg **klassifiseringen**, fordi kommunenes egne kodeverk ikke lar seg sammenligne. Det er kjernen i hele løsningen.

Master eier **ikke** bookinger, kalendere eller søkerdata. Den finner lokalet og sender brukeren til kommunens system.

---

## Tabellene

### Kommune og kildesystem

**`kommune`** — 12 rader. Kommunenummer, navn, fylke.

**`fagsystem_instans`** — 12 rader i dag, alle `type='booking'`. Én per fagsysteminstallasjon, med `base_url`, `kildenokkel` (`aktiv-kommune:bergen`) og en `type` (`booking`, `fdv`, `sensor`, `annet`).

Instansen må være med i nøklene fordi de lokale ID-ene overlapper mellom instanser. Ressurs 438 finnes i flere installasjoner og betyr ulike ting. `(fagsystem_instans_id, ekstern_id)` er entydig; `438` alene er ubrukelig.

**`kommune_fagsystem_instans`** — koblingstabell, **ekte mange-til-mange**. Én instans kan betjene flere kommuner (interkommunalt samarbeid), og én kommune kan ha flere instanser samtidig — men bare én per `type`. Bergen kan altså ha én booking-instans (Aktiv kommune) og én FDV-instans samtidig, men ikke to booking-instanser.

`type`-kolonnen på koblingstabellen er en kopi av `fagsystem_instans.type`, satt når raden opprettes. Den finnes bare for at `UNIQUE (kommune_id, type)` skal kunne håndheve «maks én instans per type per kommune» — Postgres kan ikke lage en unik-regel som refererer en kolonne i en annen tabell direkte, så kopien er den vanlige måten å løse det på.

Ruting til riktig instans er ett filter på typen, ikke et eget «kontekst»-begrep:

```sql
SELECT fi.base_url FROM kommune k
JOIN kommune_fagsystem_instans kfi ON kfi.kommune_id = k.id
JOIN fagsystem_instans fi ON fi.id = kfi.fagsystem_instans_id
WHERE k.kommunenr = '4601' AND fi.type = 'booking';
```

`bygning` og `ressurs` har sammensatte fremmednøkler `(kommune_id, fagsystem_instans_id)` mot `kommune_fagsystem_instans` (ikke mot `kommune` direkte). Det hindrer at et bygg eller en ressurs havner i en kommune/instans-kombinasjon som ikke faktisk finnes:

```
ERROR:  insert or update on table "bygning" violates foreign key constraint
        "fk_bygning_fagsystem_instans_kommune"
DETAIL:  Key (kommune_id, fagsystem_instans_id)=(1, 3) is not present in table
         "kommune_fagsystem_instans".
```

For `bygning` er `fagsystem_instans_id` nullbar, og da er regelen ikke i kraft — det gjelder bygg som bare er kjent fra matrikkelen.

**Hvorfor ikke `ressurslenke`/`kontekst` (som i `schema_perfect.sql`)?** Det løser et annet, vanskeligere problem: at *samme ressurs* har forskjellig identitet i flere fagsystemer samtidig (en gymsal med én ekstern-ID i bookingsystemet og en annen i FDV-systemet). Det problemet finnes ikke i dag — hver ressurs kommer fra nøyaktig én kilde. Løsningen her løser bare «hvilken instans skal en kommune rutes til for en gitt type», som er alt vi har bruk for nå.

> **Viktig konsekvens for innlastingen.** Kommunen kan ikke lenger utledes fra subdomenet. Tidligere betydde `bergen.aktiv-kommune.no` at alt derfra var Bergen; det holder ikke når en instans dekker flere kommuner. `kommune_id` må settes fra **adressen**, og matrikkelen oppgir kommunenummer på både adresse og eiendom. Matrikkelsteget er dermed ikke lenger bare for kart — det er det som avgjør kommunetilhørighet.

### Matrikkel

**`matrikkelinfo`** — eiendommen, altså gårds- og bruksnummer (med feste- og seksjonsnummer), knyttet til ett bygg via `bygning_id` (`NOT NULL`, `REFERENCES bygning(id) ON DELETE CASCADE`). Tabellen holder identiteten `(bygning_id, kommunenr, gardsnr, bruksnr, festenr, seksjonsnr)` og tidsstempler. Enhetstype, areal og geometri er ikke med.

Forholdet til `bygning` er en-til-mange, uten koblingstabell: ett bygg kan ha flere `matrikkelinfo`-rader (flere adresser, eller en eiendom som strekker seg over flere tomter), og hver rad hører til nøyaktig ett bygg. Siden `bygning_id` står først i `ux_matrikkelinfo`, kan samme gnr/bnr også lagres for flere ulike bygg — det er nettopp det som gjør at en hall og en bane på samme eiendom (f.eks. Hetlandshallen og Hetlandshallbanen, begge på gnr 20/bnr 287 i Stavanger) hver får sin egen rad, i stedet for at den ene faller bort. Med dagens kilder (én adresse per bygg i Aktiv kommune) blir resultatet i praksis én rad per bygg, men modellen tillater flere.

Den unike indeksen `ux_matrikkelinfo` bruker `COALESCE(festenr, 0)` fordi festenr og seksjonsnr er NULL for vanlige grunneiendommer, og NULL regnes ikke som lik NULL i en unik indeks. Uten dette kunne samme eiendom lagres mange ganger for samme bygg. Indeksen `ix_matrikkelinfo_eiendom` på `(kommunenr, gardsnr, bruksnr)` dekker det motsatte oppslaget: hvilke bygg som står på en gitt eiendom.

**`gate`** — gaten, slik matrikkelen kjenner den. Identiteten er `(kommune_id, adressekode)`, ikke navnet: samme gatenavn kan finnes flere ganger i en kommune, og samme adressekode brukes i flere kommuner. Postnummer ligger på `adresse`, ikke her, siden en gate kan krysse flere postnumre. Én gate har mange adresser (`adresse.gate_id`). Aktiv kommune oppgir ikke adressekode, så tabellen kan ikke fylles av `last_inn.py`; den må fylles av matrikkelsteget.

### Bygning

**`bygning`** — 423 rader. Stedet.

`antall_etasjer` er lagt til etter å ha sett faktiske data i Matrikkelen — feltet finnes der som et tall per bygg (ikke en egen rad per etasje), og hadde ingen plass i den opprinnelige versjonen av denne tabellen.

Tabellen holder både bygg og utendørs anlegg, fordi Aktiv kommune bare har ett stedsbegrep: «Paradis kunstgressbane» er registrert som et bygg der, på linje med ekte bygninger.

**Innendørs/utendørs avgjøres ikke på bygningsnivå.** Vi prøvde først en `er_uteanlegg`-kolonne på `bygning`, men den ble aldri fylt riktig: Aktiv kommune har ingen strukturert markering for dette i kildedataen (kun navnet, f.eks. «Møhlenpris kunstgress», gir et hint — og det er fritekst, ikke et felt å stole på). Verre: et bygg kan i praksis romme *begge* — en idrettspark kan ha en innendørshall og en utendørs kunstgressbane under samme adresse — så «er dette bygget utendørs» har ikke ett riktig svar per bygg. Kolonnen er derfor fjernet. Innendørs/utendørs filtreres i stedet på **ressursnivå**, via `ressurs.lokaletype_id` — `lokaletype` har egne utendørsfasetter (`LOK-SO-` utendørs idrett og `LOK-OU-` friluft og uteområder). Det er den riktige granulariteten: to ressurser i samme bygg kan ha ulik status, selv om bygget ikke kan.

Raden har **én identitet og én referanse**:

```
(fagsystem_instans_id, ekstern_id)  →  identiteten i kommunens bookingsystem  (building.id = 85)
bygningsnr                          →  referanse til bygget i matrikkelen
```

Bare den første er en **identitet**. `(fagsystem_instans_id, ekstern_id)` har en partiell unik indeks (`ux_bygning_ekstern`), altså «unik der verdien finnes». `bygningsnr` er en **referanse** til matrikkelen og har en vanlig, ikke-unik indeks (`ix_bygning_bygningsnr`): flere Aktiv kommune-bygg, for eksempel en hall og en bane, kan ligge i samme matrikkelbygg.

**Matrikkelen er single source of truth for byggets fakta.** Aktiv kommune leverer ikke bygningsnummer i dag, bare gateadresse. Det er besluttet at Aktiv kommunes databaser skal utvikles slik at hvert bygg har et bygningsnummer, og modellen bygges med den forutsetningen. Funksjonen er **ikke utviklet ennå**, så frem til den finnes er `bygningsnr` tomt etter innlasting, og koblingen til matrikkelen må gjøres på adresse.

`matrikkel_match` sier **hvilken metode** som fant koblingen mot matrikkelen, ikke hvor sikker den er: `bygningsnr`, `gnr_bnr`, `adresse`, `manuell`, `ikke_funnet`, eller `ikke_forsokt` (standard). Når Aktiv kommune leverer bygningsnummer, blir `bygningsnr` den normale metoden, og `adresse` blir en reserve for bygg som mangler nummeret. Frem til da vil mange bygg få `adresse`, som er den svakeste metoden og bør kunne overprøves senere.

`bydel_navn` er tekst, ikke en egen tabell. Bergen har 9 bydeler, de små kommunene ingen. En egen tabell tjener lite før noen faktisk skal vedlikeholde bydeler som register.

Kontaktfeltene (`hjemmeside`, `epost`, `telefon`, `apningstid_tekst`) og `byggeaar` er tatt ut av modellen. Se endringsloggen.

### Adresse

**`adresse`** — 421 rader. Egen tabell, ikke kolonner på bygning, fordi matrikkelen gir flere adresser per bygg (flere innganger) og fordi representasjonspunktet hører til adressen.

Hver adresse tilhører én bygning og, etter matrikkelkobling, én gate (`gate_id`, nullbar til gaten er funnet). Et hjørnebygg med innganger i to gater har to adresser. `husnr` er et heltall og `bokstav` ligger separat. `ux_adresse_ekstern` hindrer samme `ekstern_id` to ganger på ett bygg.

`geokoding` sier hvordan koordinatene ble til: `matrikkel` (autoritativt punkt), `geokodet` (oppslag på gateadresse), `manuell`, `feilet`, `ukjent`. Skillet er nødvendig fordi **kildedata ikke har koordinater i det hele tatt** — ingen av de 12 instansene har lat, lon, UTM eller geometri. Punktene må slås opp, og en senere matrikkelimport må kunne se at et geokodet punkt trygt kan overskrives.

Punktet selv ligger i `posisjon geography(Point, 4326)` — samme kolonnetype på `bygning` og `adresse`. `geography` (ikke `geometry`) er valgt fordi `ST_Distance` og `ST_DWithin` da regner ekte avstand i meter direkte, uten at man selv må velge riktig UTM-sone for Norge. Én kolonne erstatter det som før var tre (`lat`, `lon`, `srid`), og den kan ikke stå «halvveis utfylt» slik to separate nullbare tall kunne.

Gatenavnet ligger ikke lenger på `adresse`, men i `gate` via `gate_id`.

### Søkefasetter

**`lokaletype`** (94 konsepter), **`aktivitet`** (208), **`fasilitet`** (153) — masterens eget kodeverk.

Skillet er meningsbærende: `lokaletype` er hva stedet **er**, `aktivitet` er hva det kan **brukes til**, `fasilitet` er hva det **har**.

Ingen av kodeverkene seedes i skjemaet. Vokabularet eies av JSON-filer og lastes av `etl/last_inn.py`: `lokaletype_mapping/venue_types.json`, `activity_mapping/activities.json` og `fasilitet_mapping/facilities.json`. Fasetten bæres av prefikset i `kode`, ikke av en egen kolonne: `LOK-SI-` innendørs idrett, `LOK-CU-` kultur og så videre for lokaletype, `FAC-AV-` lyd og bilde, `FAC-SN-` sanitær og så videre for fasilitet, og `ACT-` aktivitet, `EVT-` arrangement, `ORG-` organisasjon, `GRP-` målgruppe, `VEN-` lokale, `SRV-` tjeneste for aktivitet (en `CHECK` håndhever aktivitetsformatet). `exclude`-konseptene lastes ikke inn. Se `etl/activity_mapping/AktivKommune_activity_normalisation.md`.

Alle tre er hierarkiske via `parent_id`, satt fra `broader` i vokabularet, så et søk på Idrettshall (`LOK-SI-001`) også treffer Gymsal (`LOK-SI-004`). Noen få aktivitetskonsepter har to foreldre i vokabularet (Dans, Curling, E-sport). `parent_id` får den første. Fordi kodeverkene ikke seedes, er de tomme i en ny database til `last_inn.py` er kjørt.

**`ressurs_aktivitet`** og **`ressurs_fasilitet`** — koblingstabeller. En gymsal brukes til håndball, turn og dans, og har garderobe, dusj og parkettgulv.

### Kildekoder og oversettelse — kjernen

Dette er tabellene som gjør tverrkommunalt søk mulig. Problemet, målt på faktiske data:

```
Kategori-ID 13  →  Bergen: "Overnatting"      Stavanger: "Skateanlegg"
Kategori-ID  4  →  "Friidrettsanlegg" / "Gressbane" / "Gymsal"
```

**58 av 63 kategori-ID-er betyr ulike ting i ulike kommuner.** Du kan altså ikke søke på kode.

Men du kan heller ikke søke på navn. Blant de 142 kategorinavnene finnes `Gressbane` og `Grasbane`, `Sermonirom` og `Seremonirom`, `Foaje` og `Foajé` — pluss verdier som ikke er lokaletyper i det hele tatt: `Stengt`, `Fiktivt rom`, `Streaming`, og stedsnavn som `Judaberg innbyggertorg`.

Løsningen er at kildens kode lagres uendret, og at ETL oversetter den til masterens kodeverk ved innlasting:

```
kildekode                    etl/*_mapping/ (JSON)          lokaletype
(kommunens kode, uendret)    (oversettelse, kun i ETL)      (vårt kodeverk)

Bergen   "17: Gymsal"  ─┐
                         ├──→   "gymsal" → LOK-SI-004   ──→   Gymsal
Øygarden  "4: Gymsal"  ─┘
```

**`kildekode`** — kommunens egen kode, lagret uendret. Nøkkelen `(fagsystem_instans_id, kodetype, kode)` gjør at Bergens 13 og Stavangers 13 kan ligge side om side. Tabellen rettes aldri; den er kildens sannhet. `sist_sett` gjør at nye koder oppdages ved neste innlasting.

**`ressurs_kildekode`** — ressursens koder slik kilden har dem: én lokaletype-kode (`rescategory_id`) og null eller flere aktivitets- og fasilitetskoder. Den står ved siden av de normaliserte koblingene (`ressurs.lokaletype_id`, `ressurs_aktivitet`, `ressurs_fasilitet`), slik at begge formene kan sammenlignes.

**Mappingen er ikke en del av modellen.** Oversettelsen fra kildekode til masterkode finnes bare i JSON-filene i `etl/*_mapping/` og påføres av `etl/last_inn.py` ved hver innlasting. Bakgrunnen er at Aktiv kommune-instansene skal normaliseres, slik at de selv bruker et felles kodeverk; da blir mappingen overflødig, og `kildekode` og `ressurs_kildekode` kan fjernes uten at resten av modellen berøres. Til da gjelder:

| Utfall i ETL | Resultat |
|---|---|
| Navnet finnes i `mapping.json` | Ressursen kobles til masterkoden(e). Lokaletype er én-til-én; ett aktivitets- eller fasilitetsnavn kan gi flere konsepter («Barnebursdag 3 - 12 år» gir Barnebursdag og Barn). |
| Navnet peker på et `exclude`-konsept, eller står i `IKKE_RELEVANT_*` | Koden er ikke relevant (`Stengt`, stedsnavn). Ingen kobling, ingen avvik. |
| Navnet finnes ikke | Avvik `ikke_kartlagt` i `synk_avvik`; koden vises i `v_ukartlagte_kildekoder` og må legges inn i `mapping.json`. |

### Ressurs

**`ressurs`** — 1 805 rader. Det søkbare og bookbare.

`fagsystem_instans_id` og `ekstern_id` gir **både identitet og ruting**: `base_url` fra instansen pluss `ekstern_id` gir bookinglenken. Ingen egen rutingtabell trengs så lenge det finnes én bookingleverandør og én kontekst.

`apningstid_tekst` er tatt ut av modellen. 

Den sammensatte fremmednøkkelen er verdt å forstå:

```sql
FOREIGN KEY (bygning_id, kommune_id) REFERENCES bygning (id, kommune_id)
```

En vanlig fremmednøkkel på `bygning_id` alene ville bare sjekket at bygget finnes. Denne sjekker *paret*, og hindrer dermed at en ressurs i Bergen havner i et bygg som ligger i Stavanger. Regelen håndheves av databasen, uansett hvem som skriver data. Fremmednøkkelen har ingen `ON DELETE`-regel, så et bygg som en ressurs peker på kan ikke slettes.

`sokevektor` er en generert kolonne: databasen regner den ut selv fra navn og beskrivelse og holder den oppdatert. Gir fritekstsøk med norsk stemming, så «garderobe» også treffer «garderober», uten egen søkemotor.

### Ressurslenke

**`ressurslenke`** — 0 rader i dag. Løser multi-fagsystem-routing: at samme fysiske bygg eller ressurs er kjent under forskjellige eksterne id-er i *flere* fagsystemer samtidig (typisk Aktiv kommune for booking OG et driftssystem (fdv) OG kanskje en sensorkilde). `ressurs.fagsystem_instans_id`/`ekstern_id` gir allerede identitet+ruting for den ENE instansen en ressurs stammer fra (se over) — denne tabellen er for de *andre* instansene som også kjenner samme fysiske ting.

"Exclusive arc": nøyaktig én av `bygning_id`/`ressurs_id` er fylt ut per rad (håndhevet av `chk_ressurslenke_exactly_one`), håndtert av to partielle unike indekser (én per type) siden en vanlig `UNIQUE` over begge kolonnene ikke fungerer når den ene alltid er NULL.

Bevisst **ingen** egen `kontekst`/type-kolonne. Hvilken type fagsystem (booking/fdv/sensor/annet) en lenke tilhører er allerede `fagsystem_instans.type`, nåbart via `fagsystem_instans_id` — å kopiere den inn her ville vært ren duplisering (se `kommune_fagsystem_instans` for det ene unntaket der en slik kopi faktisk trengs, fordi en `UNIQUE` der må krysse tabellgrenser). Konsekvensen er at et helt nytt fagsystem ikke krever noen endring i denne tabellen, bare en ny `fagsystem_instans`-rad.

Forblir tom til et konkret andre fagsystem faktisk kobles på — se `db/ressurslenke.md` for bakgrunnen.

### Innlasting og sporbarhet

**`kildeuttrekk`** — metadata om én henting fra en kilde: `kilde`, `endepunkt`, `hentet_at`, `http_status`. Ett per kommune per kjøring av `last_inn.py` og ett per kjøring av `matrikkel_adresse.py`. Registreres som første setning i hver SQL-fil, før noe er tolket. `payload` lagrer **ikke** hele kildens retur — se begrunnelsen under `synk_avvik`.

Beholdning: de to nyeste uttrekkene per kilde, uforbeholdent. `rydd_kildeuttrekk(kilde, antall)` kalles automatisk på slutten av hver last.

**`synk_avvik`** — hver rad er én ting som ikke lot seg laste, sammen med **selve posten som utløste det** (`rapost`, renset for personopplysninger - se «Personvern»), hvilket felt det gjaldt (`felt`) og hvilket felt i `rapost` som `ekstern_id` er verdien av (`nokkelfelt`). `kildeuttrekk_id` peker til uttrekket avviket oppstod i, men er bare til orientering (`endepunkt`/`hentet_at`) — selve beviset ligger i `rapost`, ikke i det uttrekket. Det er derfor FK-en er `ON DELETE SET NULL`: et gammelt uttrekk kan ryddes bort uten at avviksbeviset forsvinner med det. Typene:

| `avvikstype` | Når |
|---|---|
| `ugyldig_verdi` | Et felt bryter en regel (postnummer ikke fire siffer, kapasitet negativ eller ikke et tall, tomt navn). Feltet settes til NULL eller erstattes med plassholder, og resten av raden lastes. |
| `manglende_forelder` | En koblingsrad peker på noe som ikke finnes i uttrekket (se under). |
| `geokoding_feilet` | Ingen eller flere treff hos Kartverket, eller API-kallet feilet. |
| `db_feil` | Databasen avviste posten av en grunn vi ikke har forutsett (f.eks. et CHECK-brudd). Bare den posten rulles tilbake; feilteksten og SQLSTATE står i `detalj`, og resten av lasten fortsetter. |
| `annet` | Bl.a. at henting fra kilden feilet, eller at geokodet kommunenummer avviker fra antatt. |
| `ikke_kartlagt` | En kildekode har ikke noe navn i `mapping.json`. Ett avvik per kode per instans, med koden i `ekstern_id` og kildens samling (`resource_categories`, `activities`, `facilities`) i `samling`. Leses via `v_ukartlagte_kildekoder`. |

Mekanikken: skriptene skriver bare SQL og kjenner ikke id-en til uttrekket de oppretter. Første setning, `CALL registrer_kildeuttrekk(...)`, setter derfor id-en i en transaksjonslokal innstilling (`masterdb.kildeuttrekk_id`), og `CALL logg_avvik(...)` henter den derfra. Hver bygning/adresse, hver ressurs og hver geokodet adresse kjøres i sin egen `DO`-blokk med `EXCEPTION`-håndtering, som er det som gjør at én dårlig post ikke stopper hele transaksjonen. Python-skriptet har posten i minnet akkurat når avviket oppdages, og sender den rett med i `logg_avvik`-kallet som `rapost` — databasen trenger aldri grave den ut igjen av et lagret svar.

Til å lese avvik finnes to visninger (se «Visningene»).

Eksempelet som motiverte tabellen: Denne finnes av en helt konkret grunn: `searchdataall` er et **delvis** uttrekk. Koblingstabellene eksporteres komplett, men bygg- og ressurslistene er filtrert. I Bergen peker 388 av 980 koblingsrader på ressurser som ikke finnes i uttrekket.

Radene må filtreres bort, ellers stopper innlastingen på fremmednøkkelfeil. Men de skal loggføres — hvis andelen plutselig endrer seg, har noe skjedd hos kommunen, og da vil du vite det.

---

## Visningene

En **view** er en lagret spørring som oppfører seg som en tabell. Den lagrer ingen data selv.

**`v_ressurs_sok`** — alt et søk trenger i én flat rad: ressurs, kommune, bygg, adresse, koordinat, kanonisk type, aktiviteter og fasiliteter som lister, og ferdig `booking_url`. Søkegrensesnittet slipper å kjenne tabellene bak.

**`v_ukartlagte_kildekoder`** — arbeidslisten for kuratering. Hver rad er en lokal kode som ETL ikke fant en oversettelse for i siste kjøring, og som dermed ikke kan søkes på tvers. Bygger på `ikke_kartlagt`-avvikene i `v_synk_avvik_gjeldende`, koblet mot `kildekode`: samlingen oversettes til kodetype (`resource_categories` → `lokaletype`, `activities` → `aktivitet`, `facilities` → `fasilitet`). Blir koden lagt inn i `mapping.json`, forsvinner den ved neste kjøring.

**`v_synk_avvik_gjeldende`** — avvikene fra den siste kjøringen per kilde. Eldre avvik ligger i `synk_avvik` som historikk, men regnes ikke som åpne: finnes feilen fortsatt, er den logget på nytt i nyeste kjøring.

**`v_synk_avvik_detalj`** — avviket sammen med posten det gjelder (`rapost`, lagret direkte på avviket - se «Innlasting og sporbarhet»). Dette er visningen for den som går gjennom avviksslisten:

```sql
SELECT avvik_id, samling, avvikstype, felt, detalj, jsonb_pretty(post)
FROM v_synk_avvik_detalj
WHERE avvikstype = 'ugyldig_verdi';
```

`post` er bare den relevante posten (eller postene, for koblingsrader) — ikke hele svaret, og krever ikke at det tilhørende `kildeuttrekk` fortsatt finnes. For geokodingsavvik er det Kartverkets svar for adressen.

---

## Personvern

`searchdataall` returnerer en `organizations`-samling med 5 906 rader. En betydelig andel er **privatpersoner**: personnavn i navnefeltet, tomt organisasjonsnummer, privat mobil, privat e-post og hjemmeadresse.

Samlingen lastes ikke. Det finnes ingen tabell for den, og det er bevisst. Søket beskriver lokaler, ikke søkere. Den brukes heller aldri av innlastingsskriptet, og havner derfor aldri i en `rapost` på et avvik.

Tilsvarende utelates `buildings.tilsyn_name`, `tilsyn_phone`, `tilsyn_email` med `*2`-variantene, som er navngitte kontaktpersoner, og `resources.contact_info`, som er fritekst og kan inneholde navn: `rens_post()` i `etl/last_inn.py` fjerner disse feltene fra enhver post før den limes inn som `rapost`, slik at personopplysningene ikke havner i basen via avviksloggen.

> Behandlingsgrunnlag og vurdering av om `organizations` bør ligge på et uautentisert endepunkt, må avklares med Capgeminis Data Privacy Officer og med kommunene som behandlingsansvarlige. Dokumentet tar ikke stilling til det rettslige spørsmålet.

---

## Autoritet: hvem vinner når kildene er uenige

Med bare to kilder er dette en regel, ikke en mekanisme. Regelen ligger her og håndheves i innlastingen:

| Felt på `bygning` | Vinner |
|---|---|
| `bygningsnr`, `bygningstype`, `bra_m2`, `antall_etasjer`, `geom_wkt` | Matrikkelen |
| `navn`, `bydel_navn` | Aktiv kommune |
| `posisjon` (via `adresse`) | Matrikkelen, hvis `geokoding='matrikkel'` |
| `gate_id` på `adresse`, `gate` | Matrikkelen |

Matrikkelen vinner på byggets fakta. Aktiv kommune vinner på det publikumsvennlige navnet, for matrikkelen vet ikke at bygget heter «Flaktveit stadion».

---

## Innlasting: filene og rekkefølgen

Dette er den faktiske pipelinen, ikke en plan — alle filnavn og kommandoer under er det som brukes i praksis (se `etl/README.md` for kjøreinstruksjoner i detalj).

```
                    KILDER                          FILER/SKRIPT                    DATABASE
                    ───────                          ────────────                    ────────

  12 × Aktiv kommune   ──HTTPS──▶  etl/last_inn.py       ──skriver──▶  etl/ut/alle.sql     ──psql──▶  masterdb
  (searchdataall)                 (hardkodet logikk)                   (forkastbar output)

  Matrikkel-API        ──SOAP───▶  etl/matrikkel_adresse.py ──skriver──▶ etl/ut/matrikkel.sql ──psql──▶  masterdb
  (geokoding+bygning)              (eneste geokodingssteg)              (forkastbar output)

  db/schema_kjerne.sql ────────────────────────────────────────────────psql────────────▶  masterdb
  (strukturen, kjøres først, én gang eller ved endring)
```

Ingen av disse tre stegene trigger det neste automatisk — alt er manuelle kommandoer i rekkefølge, bevisst, gitt hvor lite data det er tale om (noen få MB, et par hundre adresser). Kartverkets åpne Adresse-API ble tidligere brukt som et raskere forsteg (`etl/geokod.py`), men er fjernet til fordel for ett system med én geokodingskilde å forstå og vedlikeholde - se `etl/README.md` for den målte kostnaden ved det valget.

| Fil | Kjøres når | Hva den gjør | Hardkodet? |
|---|---|---|---|
| `db/schema_kjerne.sql` | Én gang mot en ny database, eller på nytt etter en modellendring | Lager alle tabellene, indeksene og visningene. Kodeverkene fylles av `last_inn.py` | Ja — dette er selve modellen |
| `etl/last_inn.py` | Hver gang vi vil oppdatere kommunedata | Henter `searchdataall` fra én eller alle 12 kommuner, renser tekst (HTML er escapet to ganger i kilden), laster kodeverkene fra vokabularfilene og oversetter lokale koder via `mapping.json` i `etl/*_mapping/` (reserve: `IKKE_RELEVANT_*`), skriver SQL til standard-ut | Ja — avvisningslogikken er hardkodet Python; ordbøkene er JSON-filer |
| `etl/ut/alle.sql` | Aldri «kjørt» — bare skrevet | Ferskt SQL-øyeblikksbilde av hva kommunene sa akkurat da skriptet kjørte | Nei — forkastbar output, ligger i `.gitignore`, ulik hver dag |
| `etl/matrikkel_adresse.py` | Etter hver `last_inn.py`-kjøring, for det som fortsatt mangler geokoding/bygningsnr/matrikkelinfo | Slår opp adresser mot MatrikkelAPI *innenfor riktig kommune*, og bygningsobjektet for enhver bygning som mangler bygningsnummer. Krever ett eksakt treff; null eller flere treff logges i `synk_avvik` i stedet for å gjettes | Ja — matchingsregelen er hardkodet |
| `etl/ut/matrikkel.sql` | Aldri «kjørt» — bare skrevet | Ferskt SQL-øyeblikksbilde av geokodings- og bygningsresultatet | Nei — samme som over |

Kommandorekkefølgen i praksis:

```bash
# 1. Struktur (kun ved ny database eller modellendring)
docker exec -i portico_masterdb psql -U postgres -d masterdb < db/schema_kjerne.sql

# 2. Kommunedata
python3 etl/last_inn.py alle > etl/ut/alle.sql
docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/alle.sql

# 3. Geokoding + bygningsberikelse
docker exec portico_masterdb psql -U postgres -d masterdb -tA -F'|' -c "
    SELECT a.id, a.adressetekst, a.postnummer, a.poststed, k.kommunenr,
           a.bygning_id, a.geokoding, a.gate_id, a.husnr, a.bokstav, g.adressekode
    FROM adresse a JOIN bygning b ON b.id=a.bygning_id JOIN kommune k ON k.id=b.kommune_id
    LEFT JOIN gate g ON g.id = a.gate_id
    WHERE a.er_hovedadresse AND a.geokoding <> 'manuell' AND a.adressetekst IS NOT NULL
      AND (a.geokoding IN ('ukjent','feilet') OR b.bygningsnr IS NULL
           OR NOT EXISTS (SELECT 1 FROM matrikkelinfo m WHERE m.bygning_id = b.id));
" > etl/ut/adresser_a_matrikkelsoke.txt
python3 etl/matrikkel_adresse.py < etl/ut/adresser_a_matrikkelsoke.txt > etl/ut/matrikkel.sql
docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/matrikkel.sql
```

Gjentatt kjøring oppdaterer i stedet for å duplisere, men ikke alt overskrives:

- `bygning`: navn og bydel følger kilden (Aktiv kommune vinner på disse feltene).
- `adresse`: oppdateres bare mens `geokoding` er `ukjent` eller `feilet`. En geokodet eller manuelt satt adresse røres ikke. Konsekvens: endres adressen i kilden etter geokoding, fanges det ikke opp av innlastingen.
- `ressurs`: navn, `kapasitet` og `lokaletype_id` følger kilden og mappingen.
- `lokaletype`, `aktivitet`, `fasilitet`: navn og `parent_id` følger vokabularfilene.
- `ressurs_kildekode`, `ressurs_aktivitet`, `ressurs_fasilitet`: bygges på nytt for instansen ved hver kjøring, så endringer i kilden eller mapping-filene slår alltid igjennom. Det finnes ingen manuelle mappinger i databasen; rettinger gjøres i `mapping.json`.

**Kjent forenkling, verdt å lese to ganger:** `kommune_id` settes i steg 2 fra hvilken Aktiv kommune-instans dataene kommer fra (instansens slug slås opp direkte mot en kommune), **ikke** fra geokodingen i steg 3. Det stemmer for alle 12 instansene i dag, siden hver av dem betjener nøyaktig én kommune (se `kommune_fagsystem_instans`). Skulle en instans senere betjene flere kommuner, holder ikke denne forenklingen — da må steg 2 vente på steg 3, og `kommune_id` avgjøres av adressens geokodede `kommunenummer` i stedet.

**Matrikkelen** er kilden til bygningsnummer, bygningstype, BRA, antall etasjer, gate, adressekode og eiendomskoblingen (`matrikkelinfo`, knyttet til bygget via `bygning_id`) - alt fylt av `etl/matrikkel_adresse.py` (se `etl/README.md`, "Geokoding og bygningsberikelse"), som kjører mot MatrikkelAPI-ets testmiljø (`prodtest.matrikkel.no`). Produksjonstilgang krever avtale med Kartverket - `BASE_URL` må oppdateres den dagen den er på plass. Bygg og adresser det ikke lykkes å finne noe for, forblir `bygning.matrikkel_match='ikke_forsokt'`/`'ikke_funnet'` og er loggført i `synk_avvik`, ikke gjettet på.

**Ikke del av pipelinen ennå:** ingen automatisk gjentakelse (ingen cron/planlagt jobb — alt kjøres manuelt) og ingen automatisert kuratering av `v_ukartlagte_kildekoder` — det er fortsatt en manuell jobb å lese visningen og redigere `mapping.json` i `etl/*_mapping/`.

---

## Eksempelspørringer

Finn gymsal med garderobe, uansett kommune:

```sql
SELECT navn, kommune_navn, bygg_navn, adressetekst, booking_url
FROM v_ressurs_sok
WHERE lokaletype_kode = 'LOK-SI-004'            -- Gymsal
  AND 'FAC-SN-002' = ANY(fasilitet_koder);     -- Garderobe
```

Søk på hovedgruppe, slik at undertyper treffer:

```sql
WITH RECURSIVE gren AS (
    SELECT id, kode FROM lokaletype WHERE kode = 'LOK-SI-001'   -- Idrettshall
    UNION ALL
    SELECT lt.id, lt.kode FROM lokaletype lt JOIN gren g ON lt.parent_id = g.id
)
SELECT navn, kommune_navn, lokaletype_navn FROM v_ressurs_sok
WHERE lokaletype_kode IN (SELECT kode FROM gren);
```

Fritekstsøk:

```sql
SELECT navn, kommune_navn FROM v_ressurs_sok
WHERE sokevektor @@ to_tsquery('norwegian', 'garderobe & parkett');
```

Nærhetssøk — lokaler innenfor 10 km av et gitt punkt, sortert etter avstand (krever at `posisjon` er fylt via geokoding):

```sql
SELECT navn, kommune_navn,
       round(ST_Distance(posisjon, ST_SetSRID(ST_MakePoint(5.3221, 60.3948), 4326)::geography)) AS meter
FROM v_ressurs_sok
WHERE ST_DWithin(posisjon, ST_SetSRID(ST_MakePoint(5.3221, 60.3948), 4326)::geography, 10000)
ORDER BY posisjon <-> ST_SetSRID(ST_MakePoint(5.3221, 60.3948), 4326)::geography;
```

`ST_DWithin` er filteret (alt innenfor radiusen), `<->` er sorteringen (nærmest først). Begge bruker GiST-indeksen på `posisjon` — bekreftet med `EXPLAIN`, som viser `Index Scan using ix_bygning_posisjon`, ikke en full tabellskanning.

Åpne avvik fra siste kjøring, med posten de gjelder:

```sql
SELECT d.avvik_id, d.kilde, d.avvikstype, d.felt, d.detalj, d.post
FROM v_synk_avvik_gjeldende g
JOIN v_synk_avvik_detalj d ON d.avvik_id = g.id
WHERE g.avvikstype IN ('ugyldig_verdi', 'db_feil');
```

Ikke-normalisert og normalisert lokaletype side om side:

```sql
SELECT fi.kildenokkel, r.navn, kk.kode, kk.navn AS lokalt_navn,
       lt.kode AS kanonisk, lt.navn AS kanonisk_navn
FROM ressurs r
JOIN fagsystem_instans fi ON fi.id = r.fagsystem_instans_id
JOIN ressurs_kildekode rk ON rk.ressurs_id = r.id
JOIN kildekode kk         ON kk.id = rk.kildekode_id AND kk.kodetype = 'lokaletype'
LEFT JOIN lokaletype lt   ON lt.id = r.lokaletype_id
ORDER BY fi.kildenokkel, kk.kode;
```

---

## Validering

Skjemaet er kjørt mot PostgreSQL 18 med PostGIS 3.6, er idempotent ved gjentatt kjøring, og oppretter 18 egne tabeller og 4 egne visninger (pluss PostGIS' egen `spatial_ref_sys`, samt geography_columns og geometry_columns i view.).


Mange-til-mange-relasjonen mellom `kommune` og `fagsystem_instans` er verifisert: én kommune kan knyttes til flere instanser av forskjellig type (booking + fdv samtidig, testet på Bergen), men `UNIQUE (kommune_id, type)` avviser en andre instans av *samme* type for samme kommune. Ruting fungerer ved å filtrere på `fagsystem_instans.type` — bekreftet at et oppslag på Bergens booking-instans og Bergens fdv-instans gir to forskjellige, korrekte `base_url`. Et bygg med en kommune/instans-kombinasjon som ikke finnes i `kommune_fagsystem_instans` avvises fortsatt via `fk_bygning_fagsystem_instans_kommune`, og det samme gjelder `ressurs` via `fk_ressurs_fagsystem_instans_kommune` og `fk_ressurs_bygning`.

**PostGIS-nærhetssøk er verifisert med reelle avstander**, først med midlertidige testkoordinater (7 662 meter mellom to Bergen-bygg, riktig størrelsesorden, `EXPLAIN` bekreftet `Index Scan using ix_bygning_posisjon`), deretter med ekte geokodede koordinater fra en kjøring av daværende geokodingssteg (se `etl/README.md` for dagens steg, `etl/matrikkel_adresse.py`). 234 av 419 adresser ble geokodet mot Kartverkets åpne Adresse-API den gang (steget er siden fjernet, se `etl/README.md`); de resterende 185 er loggført i `synk_avvik` fordi Aktiv kommunes adressetekst ikke alltid stemmer med det offisielle registeret (stavefeil, mellomrom, feil postnummer). Et nærhetssøk på gymsaler innenfor 5 km av Bergen sentrum gir nå 13 reelle treff, sortert etter faktisk avstand.

Geokodingen fanget også et eget bugfunn: et fritekstsøk uten streng postnummer-håndtering matchet «Festplassen» (Bergen) mot den eneste «Festplassen» i hele adresseregisteret med husnummer — i Lørenskog. Rettet til at postnummer-filteret må gi et faktisk treff for at et resultat skal godtas; ellers regnes søket som mislykket. 4 adresser fikk et annet kommunenummer fra geokodingen enn det innlastingen antok (trolig postnummer som strekker seg over en kommunegrense) — loggført i `synk_avvik`, ikke overskrevet, siden `kommune_id` er identitetsdata.

Alle 12 instanser er lastet inn med reelle data:

| Tabell | Rader |
|---|---:|
| `kommune` / `fagsystem_instans` | 12 / 12 |
| `bygning` | 423 |
| `adresse` | 419 |
| `ressurs` | 1 805 |
| — med kanonisk lokaletype | 1 755 (97 %) |
| — med byggtilknytning | 1 613 |
| `kildekode` | 1 557 |
| `ressurs_aktivitet` / `ressurs_fasilitet` | 672 / 1 221 |
| `synk_avvik` (siste kjøring) | 2 829 |

Radtallene svinger litt fra kjøring til kjøring (kommunene endrer sine egne data daglig); det er `GYMSAL`/`IDRETTSHALL`-mønsteret som er det stabile beviset. Tverrkommunalt søk er verifisert: ett søk på `GYMSAL` finner gymsaler i 3 kommuner, `IDRETTSHALL` i 4 kommuner — alt gjennom én kanonisk kode, til tross for at de lokale ID-ene er uforenlige.

---

## Funn om datakvalitet

Verdt å kjenne før noe loves som søkefunksjon.

**Ingen koordinater i kilden.** Ingen av de 12 instansene har geodata. Geokoding var derfor et obligatorisk steg, ikke en forbedring — se `etl/matrikkel_adresse.py`. En nasjonal test av alle 12 kommunene ga 70 % automatisk treffrate (278 av 399); resten krever manuell retting av adressetekst eller postnummer, siden Aktiv kommunes fritekst ikke alltid stemmer med det offisielle registeret.

**Kapasitet er nesten ikke utfylt i kilden.** 2 av 590 ressurser i Bergen, 3 av 371 i Stavanger. Det er planlagt å legge inn kapasitetsdata, derfor beholdes dette feltet i modellen. Kilden leverer i dag ofte capacity = 0 som standardverdi når kapasitet ikke er registrert. Innlastingen i last_inn.py lagrer verdien uendret fra kilden (0 lagres som 0, null som NULL). Negative verdier og ikke-tall loggføres som avvik og lagres som NULL. Eksempel:
capacity = null  -> NULL i databasen
capacity = 0     -> 0 i databasen
capacity = 25    -> 25 i databasen
capacity = -5    -> NULL + avvik i synk_avvik
capacity = "abc" -> NULL + avvik i synk_avvik

**566 av 1 805 ressurser havner i «Generelt lokale».** De små kommunene har bare to kategorier, `Lokale` og `Utstyr`, så en tredjedel av tilbudet har ingen informativ type i kilden. Kartleggingen kan ikke gjøre det bedre enn kilden er; her må kommunene selv kategorisere.

**35 ressurser har ingen kategori i det hele tatt.** Gamvik har `rescategory_id = null` på alle sine 32 ressurser, Averøy på 2, Narvik på 1. De er usynlige i typebasert søk.

**11 Stavanger-ressurser peker på kategori 12, som ikke finnes i kommunens egen kategoriliste.**

**To Bergen-bygg har søppel i postnummerfeltet:** `Totlandsvegen 53` og `5221 Nesttun`. Skjemaet avviser dem, og innlastingen loggfører dem som `ugyldig_verdi` i stedet for å trunkere stille.

**Ukartlagte koder.** Med mapping-filene for lokaletype (v0.2), aktivitet (v0.3) og fasilitet (v0.1) står Bergen igjen med 2 ukartlagte fasilitetskoder. Fasilitetslistene er de mest rotete — Stavanger bruker dem til fritekst som «Samsung 75'' 4K skjerm» og «9 seter»; se `v_ukartlagte_kildekoder` etter en kjøring av alle kommunene.

---

## Bevisst utenfor modellen

Disse fantes i `schema_perfect.sql` og er tatt ut, fordi ingen data fyller dem eller fordi de løser problemer som ikke finnes ennå. `db/schema_perfect.sql` ligger urørt i repoet hvis noe skal hentes tilbake.

| Utelatt | Hvorfor |
|---|---|
| `etasje`, `rom`, `floy` | Kilden har ingen felt for etasje, rom eller fløy. Verifisert: 63 feltnavn i kildedata, ingen treff. |
| `flate`, `flate_rel_aggregates` | Baner er vanlige ressurser i kilden, ikke et eget begrep. |
| `uteomraade`, `uteomraade_type` | Aktiv kommune har ett stedsbegrep. `bygning` dekker det; innendørs/utendørs filtreres via `ressurs.lokaletype_id` i stedet for en egen stedstabell. |
| `bruksenhet` | Kommer fra matrikkelen, men trengs ikke for å finne et lokale. |
| `bydel` | Tekstkolonne (`bygning.bydel_navn`) til noen skal vedlikeholde bydeler som register. (`gate` er nå en egen tabell.) |
| `identitetslenke` | Bygget bærer begge identitetene selv. |
| `feltautoritet` | Med to kilder er det en regel, ikke en konfigtabell. |
| `ressurslenke` | Én bookingleverandør, én kontekst. `fagsystem_instans_id` på `ressurs` holder. |
| `ledighet_cache` | Ledighetsendepunktet er ikke funnet ennå. |
| `ressurspool`, `ressurs_rel_aggregates` | Ingen data, og ingen bruker som trenger dem i dag. |
| `classification`, `ressurs_classification` | Eksterne standardkodeverk. Ingen har bedt om NS 3451 her. |
| `ressurs.type = 'person'`, `ressurspool.type = 'staffing'` | Bemanning krever persondata og hører i HR- eller FDV-system. |

---

## Endringslogg

### Mapping ut av modellen (feat/db_forenkling)

Aktiv kommune-instansene skal normaliseres, så mappingen er tatt ut av databasemodellen og påføres bare i ETL. Endret direkte i V1 (`schema_kjerne.sql` er lik); eksisterende databaser må bygges på nytt.

- Fjernet `kildekode_mapping` og `aktivitet_mapping`. `kildekode` er beholdt.
- Ny tabell `ressurs_kildekode` med ressursens koder slik kilden har dem.
- `v_ukartlagte_kildekoder` bygger nå på `ikke_kartlagt`-avvik i `v_synk_avvik_gjeldende`.
- Seed-dataene for `lokaletype` og `fasilitet` er fjernet; alle tre kodeverkene lastes fra vokabularfilene i `etl/*_mapping/` med nye koder (`LOK-xx-nnn`, `FAC-xx-nnn`).
- `fasilitet.gruppe` er erstattet av `parent_id`, slik at fasilitet er hierarkisk som de to andre.

### Tidligere endringer

Endringer i `schema_kjerne.sql` siden commit `86847b9`.

### Tabeller og navn

- `matrikkelenhet` er omdøpt til `matrikkelinfo`. Det gjelder også den unike indeksen, som heter `ux_matrikkelinfo`.
- Ny tabell `gate` med `kommune_id`, `adressekode` og `gatenavn`. Den har `UNIQUE (kommune_id, adressekode)`, en indeks på `(kommune_id, lower(gatenavn))` og tidsstempler. `gate` er lagt til i trigger-listen for `updated_at`.
- Koblingstabellen `bygning_matrikkelenhet` (senere omdøpt til `bygning_matrikkelinfo`) er fjernet, sammen med indeksen `ix_bygning_matrikkelinfo_enhet`. `matrikkelinfo` har i stedet fått kolonnen `bygning_id` (`NOT NULL`, `REFERENCES bygning(id) ON DELETE CASCADE`), slik at forholdet mellom bygg og matrikkelinfo er en-til-mange uten egen koblingstabell. Tabellen er flyttet til etter `bygning` i skjemaet, siden den nå peker på den. `ux_matrikkelinfo` har fått `bygning_id` som første kolonne, slik at samme gnr/bnr kan lagres for flere bygg (f.eks. en hall og en bane på samme eiendom). Ny indeks `ix_matrikkelinfo_eiendom` på `(kommunenr, gardsnr, bruksnr)` dekker oppslag fra eiendom til bygg. `etl/matrikkel_adresse.py` er oppdatert til å sette `bygning_id` direkte fra adressen ved innsetting, i stedet for en egen kobling etterpå.

### Fjernede kolonner

| Tabell | Fjernet |
|---|---|
| `matrikkelinfo` | `enhetstype`, `areal_m2`, `geom_wkt`, `ekstern_id` |
| `bygning` | `hjemmeside`, `epost`, `telefon`, `apningstid_tekst`, `byggeaar` |
| `ressurs` | `apningstid_tekst` |
| `adresse` | `gatenavn` (erstattet av `gate_id`) |
| `lokaletype`, `aktivitet`, `fasilitet` | `sortering`, også fra alle seed-data |

### Endrede og nye kolonner

- `bygning.matrikkel_match` har nye verdier: `ikke_forsokt`, `bygningsnr`, `gnr_bnr`, `adresse`, `manuell` og `ikke_funnet`. Før var de `bekreftet`, `sannsynlig` og `usikker`. Verdien beskriver nå hvilken metode som fant koblingen, ikke hvor sikker den er.
- `adresse.husnr` er nå `INTEGER`, tidligere `TEXT`.
- `adresse.gate_id` er ny: en nullbar fremmednøkkel til `gate` med `ON DELETE SET NULL`, og en indeks. Den er `NULL` til matrikkelkoblingen har funnet gaten.
- Ny unik indeks `ux_adresse_ekstern (bygning_id, ekstern_id)`.

### Identitet og constraints

- `ux_bygning_bygningsnr` er byttet fra unik indeks til vanlig indeks `ix_bygning_bygningsnr`. Flere Aktiv kommune-bygg (for eksempel hall og bane) kan ligge i samme matrikkelbygg, så `bygningsnr` er en referanse og ikke en identitet. Identiteten er `(fagsystem_instans_id, ekstern_id)`.

### Annet

- Seed-INSERTene er skrevet om uten `sortering`.
- Seksjonene i filen er nummerert 1 til 12, og «Gate» er ny seksjon 4.

### Ikke endret

`bygning.geom_wkt` er fortsatt `TEXT`, og `fk_ressurs_bygning` har fortsatt standard fremmednøkkeloppførsel. Et bygg som en ressurs peker på kan derfor ikke slettes.

---

## Åpne spørsmål

**Ledighetsendepunktet er ikke identifisert.** `/bookingfrontend/availability`, `/freetime`, `/schedule` og `/bookings` svarer alle 404. `/bookingfrontend/buildings` finnes som ekte JSON med felt `searchdataall` mangler, blant annet `town_id` og `active`. Det tyder på et bredere API som bør etterspørres hos leverandøren.

**Kommunelisten bør bekreftes.** 12 instanser er verifisert å svare: bergen, stavanger, baerum, oygarden, narvik, afjord, averoy, gamvik, inderoy, nordreisa, oksnes, sogndal. Oversikten på aktiv-kommune.no er JavaScript-generert, så listen er utledet fra lenker på siden.

**Treffraten for matrikkelmatching er ukjent.** Aktiv kommune oppgir bare gateadresse. Andelen treff per metode (`bygningsnr`, `gnr_bnr`, `adresse`) bør måles på et utvalg før `matrikkel_match` brukes til å avgjøre hvilke felt som overskrives.
