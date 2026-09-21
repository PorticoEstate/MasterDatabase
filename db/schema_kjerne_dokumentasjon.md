# Kjernemodell for masterdatabasen

Dokumentasjon for `db/schema_kjerne.sql`. 16 tabeller, 2 visninger. Alle tabellene får data.

**Navnekonvensjon:** hver tabells primærnøkkel heter `id`. En fremmednøkkel heter `<tabellnavn den peker til>_id`, f.eks. `kommune_id` på en kolonne som peker til `kommune`. Unntak: selvrefererende hierarkikolonner (`lokaletype.parent_id`, `aktivitet.parent_id`) heter `parent_id`, ikke `lokaletype_id`, for lesbarhet.

## Hva basen skal gjøre

La en innbygger søke etter en **type lokale** — «gymsal med garderobe» — uten å velge kommune først. I dag er hver kommune en separat Aktiv kommune-instans, så et lokale i nabokommunen er usynlig.

To kilder, to roller:

| Kilde | Eier |
|---|---|
| Aktiv kommune (12 instanser) | Tilbudet: hvilke lokaler finnes, hva heter de, kan de bookes |
| Matrikkelen (Kartverket) | Bygget: bygningsnummer, type, byggeår, areal, koordinat |

Master eier i tillegg **klassifiseringen**, fordi kommunenes egne kodeverk ikke lar seg sammenligne. Det er kjernen i hele løsningen.

Master eier **ikke** bookinger, kalendere eller søkerdata. Den finner lokalet og sender brukeren til kommunens system.

---

## Tabellene

### Kommune og kildesystem

**`kommune`** — 12 rader. Kommunenummer, navn, fylke.

**`fagsystem_instans`** — 12 rader. Én per Aktiv kommune-installasjon, med `base_url` og `kildenokkel` (`aktiv-kommune:bergen`).

Instansen må være med i nøklene fordi de lokale ID-ene overlapper mellom instanser. Ressurs 438 finnes i flere installasjoner og betyr ulike ting. `(fagsystem_instans_id, ekstern_id)` er entydig; `438` alene er ubrukelig.

**Én instans kan betjene flere kommuner** (interkommunalt samarbeid), men en kommune betjenes bare av én instans. Dette er en vanlig en-til-mange-relasjon, ikke mange-til-mange, og løses uten egen koblingstabell: `kommune.fagsystem_instans_id` peker opp til instansen. Fordi kolonnen er skalar, kan en kommune aldri ha to instanser samtidig; fordi flere kommunerader kan dele samme `fagsystem_instans_id`, kan én instans ha mange kommuner.

`kommune` har i tillegg `CONSTRAINT uq_kommune_fagsystem_instans UNIQUE (id, fagsystem_instans_id)`. Den finnes ikke for å håndheve noe på `kommune` selv — `id` er allerede unik — men som *mål* for de sammensatte fremmednøklene fra `bygning` og `ressurs`, som begge har `(kommune_id, fagsystem_instans_id)` pekende hit. Det hindrer at et bygg eller en ressurs havner i en kommune som instansen ikke betjener:

```
ERROR:  insert or update on table "ressurs" violates foreign key constraint
        "fk_ressurs_fagsystem_instans_kommune"
DETAIL:  Key (kommune_id, fagsystem_instans_id)=(2, 2) is not present in table "kommune".
```

For `bygning` er `fagsystem_instans_id` nullbar, og da er regelen ikke i kraft — det gjelder bygg som bare er kjent fra matrikkelen.

> **Viktig konsekvens for innlastingen.** Kommunen kan ikke lenger utledes fra subdomenet. Tidligere betydde `bergen.aktiv-kommune.no` at alt derfra var Bergen; det holder ikke når en instans dekker flere kommuner. `kommune_id` må settes fra **adressen**, og Kartverkets åpne Adresse-API returnerer `kommunenummer` direkte i samme oppslag som gir koordinatene. Geokodingssteget er dermed ikke lenger bare for kart — det er det som avgjør kommunetilhørighet.

### Matrikkel

**`matrikkelenhet`** — eiendommen, altså gårds- og bruksnummer.

Den unike indeksen bruker `COALESCE(festenr, 0)` fordi festenr og seksjonsnr er NULL for vanlige grunneiendommer, og NULL regnes ikke som lik NULL i en unik indeks. Uten dette kunne samme eiendom lagres mange ganger.

**`bygning_matrikkelenhet`** — koblingstabell. Et bygg kan stå på flere eiendommer, og en eiendom ha flere bygg. Hver rad er ett par.

### Bygning

**`bygning`** — 425 rader. Stedet.

Tabellen holder både bygg og utendørs anlegg, fordi Aktiv kommune bare har ett stedsbegrep: «Paradis kunstgressbane» er registrert som et bygg der. `er_uteanlegg` skiller dem uten at det trengs en egen tabell.

Raden bærer **to identiteter samtidig**:

```
(fagsystem_instans_id, ekstern_id)  →  identiteten i kommunens bookingsystem  (building.id = 85)
bygningsnr                          →  identiteten i matrikkelen
```

Derfor trengs ingen egen tabell for identitetskobling. Begge har sin egen partielle unike indeks, altså «unik der verdien finnes» — nødvendig fordi de fleste bygg mangler bygningsnummer til matrikkelen er koblet på, og en vanlig `UNIQUE` ville vært for streng.

`matrikkel_match` sier hvor sikker koblingen mot matrikkelen er. Aktiv kommune oppgir ikke bygningsnummer, bare gateadresse, så koblingen er en kvalifisert gjetning som må kunne merkes `sannsynlig` og overprøves senere.

`bydel_navn` er tekst, ikke en egen tabell. Bergen har 9 bydeler, de små kommunene ingen. En egen tabell tjener lite før noen faktisk skal vedlikeholde bydeler som register.

`epost` og `telefon` skal **kun** inneholde funksjonelle adresser som `idrettsetaten@bergen.kommune.no`. Se personvern nedenfor.

### Adresse

**`adresse`** — 421 rader. Egen tabell, ikke kolonner på bygning, fordi matrikkelen gir flere adresser per bygg (flere innganger) og fordi representasjonspunktet hører til adressen.

`geokoding` sier hvordan koordinatene ble til: `matrikkel` (autoritativt punkt), `geokodet` (oppslag på gateadresse), `manuell`, `feilet`, `ukjent`. Skillet er nødvendig fordi **kildedata ikke har koordinater i det hele tatt** — ingen av de 12 instansene har lat, lon, UTM eller geometri. Punktene må slås opp, og en senere matrikkelimport må kunne se at et geokodet punkt trygt kan overskrives.

Gatenavn ligger som tekst av samme grunn som bydel.

### Søkefasetter

**`lokaletype`** (78 rader), **`aktivitet`** (28), **`fasilitet`** (32) — masterens eget kodeverk.

Skillet er meningsbærende: `lokaletype` er hva stedet **er**, `aktivitet` er hva det kan **brukes til**, `fasilitet` er hva det **har**.

`lokaletype` og `aktivitet` er hierarkiske via `parent_id`, så et søk på `IDRETT` også treffer `GYMSAL` og `IDRETTSHALL`.

**`ressurs_aktivitet`** og **`ressurs_fasilitet`** — koblingstabeller. En gymsal brukes til håndball, turn og dans, og har garderobe, dusj og parkettgulv.

### Kildekoder og oversettelse — kjernen

Dette er tabellene som gjør tverrkommunalt søk mulig. Problemet, målt på faktiske data:

```
Kategori-ID 13  →  Bergen: "Overnatting"      Stavanger: "Skateanlegg"
Kategori-ID  4  →  "Friidrettsanlegg" / "Gressbane" / "Gymsal"
```

**58 av 63 kategori-ID-er betyr ulike ting i ulike kommuner.** Du kan altså ikke søke på kode.

Men du kan heller ikke søke på navn. Blant de 142 kategorinavnene finnes `Gressbane` og `Grasbane`, `Sermonirom` og `Seremonirom`, `Foaje` og `Foajé` — pluss verdier som ikke er lokaletyper i det hele tatt: `Stengt`, `Fiktivt rom`, `Streaming`, og stedsnavn som `Judaberg innbyggertorg`.

Løsningen er to tabeller:

```
kildekode                    kildekode_mapping              lokaletype
(kommunens kode, uendret)    (kuratert oversettelse)        (vårt kodeverk)

Bergen   "17: Gymsal"  ─┐
                         ├──→   godkjent   ──→   GYMSAL
Øygarden  "4: Gymsal"  ─┘
```

**`kildekode`** — 1 566 rader. Kommunens egen kode, lagret uendret. Nøkkelen `(fagsystem_instans_id, kodetype, kode)` gjør at Bergens 13 og Stavangers 13 kan ligge side om side. Tabellen rettes aldri; den er kildens sannhet. `sist_sett` gjør at nye koder oppdages ved neste innlasting.

**`kildekode_mapping`** — oversettelsen, modellert som en *påstand* og ikke en beregning: den har `status`, `kartlagt_av` og `merknad`, fordi dette er en menneskelig vurdering.

Tabellen er i praksis en ett-til-én-utvidelse av `kildekode`, men følger likevel navnekonvensjonen fullt ut: den har sin egen `id` som primærnøkkel, og en separat `kildekode_id BIGINT UNIQUE NOT NULL` som fremmednøkkel. Det unngår at én og samme kolonne må være både primærnøkkel og fremmednøkkel samtidig.

| Status | Betydning |
|---|---|
| `foreslatt` | Maskinelt forslag, ikke godkjent. Brukes ikke i søk. |
| `godkjent` | Kvalitetssikret. Brukes i søk. |
| `ikke_relevant` | Koden er ikke en lokaletype. Her havner `Stengt` og stedsnavnene. |

### Ressurs

**`ressurs`** — 1 805 rader. Det søkbare og bookbare.

`fagsystem_instans_id` og `ekstern_id` gir **både identitet og ruting**: `base_url` fra instansen pluss `ekstern_id` gir bookinglenken. Ingen egen rutingtabell trengs så lenge det finnes én bookingleverandør og én kontekst.

`kapasitet_kilde` finnes fordi kapasitet er utfylt på under 1 % av ressursene i kilden, og Stavanger koder den i stedet som fasilitet («Kapasitet 1-20»). Verdien må ofte settes manuelt, og da må opphavet følge den — ellers vet ingen om 120 er målt eller gjettet.

Den sammensatte fremmednøkkelen er verdt å forstå:

```sql
FOREIGN KEY (bygning_id, kommune_id) REFERENCES bygning (id, kommune_id)
```

En vanlig fremmednøkkel på `bygning_id` alene ville bare sjekket at bygget finnes. Denne sjekker *paret*, og hindrer dermed at en ressurs i Bergen havner i et bygg som ligger i Stavanger. Regelen håndheves av databasen, uansett hvem som skriver data.

`sokevektor` er en generert kolonne: databasen regner den ut selv fra navn og beskrivelse og holder den oppdatert. Gir fritekstsøk med norsk stemming, så «garderobe» også treffer «garderober», uten egen søkemotor.

### Innlasting og sporbarhet

**`kildeuttrekk`** — rått JSON-svar fra kilden, lagret før transformasjon. Lar en last kjøres om igjen uten nye kall mot kommunens system.

**`synk_avvik`** — 2 635 rader ved full innlasting. Denne finnes av en helt konkret grunn: `searchdataall` er et **delvis** uttrekk. Koblingstabellene eksporteres komplett, men bygg- og ressurslistene er filtrert. I Bergen peker 388 av 980 koblingsrader på ressurser som ikke finnes i uttrekket.

Radene må filtreres bort, ellers stopper innlastingen på fremmednøkkelfeil. Men de skal loggføres — hvis andelen plutselig endrer seg, har noe skjedd hos kommunen, og da vil du vite det.

---

## Visningene

En **view** er en lagret spørring som oppfører seg som en tabell. Den lagrer ingen data selv.

**`v_ressurs_sok`** — alt et søk trenger i én flat rad: ressurs, kommune, bygg, adresse, koordinat, kanonisk type, aktiviteter og fasiliteter som lister, og ferdig `booking_url`. Søkegrensesnittet slipper å kjenne tabellene bak.

**`v_ukartlagte_kildekoder`** — arbeidslisten for kuratering. Hver rad er en lokal kode som ennå ikke kan søkes på tvers.

---

## Personvern

`searchdataall` returnerer en `organizations`-samling med 5 906 rader. En betydelig andel er **privatpersoner**: personnavn i navnefeltet, tomt organisasjonsnummer, privat mobil, privat e-post og hjemmeadresse.

Samlingen lastes ikke. Det finnes ingen tabell for den, og det er bevisst. Søket beskriver lokaler, ikke søkere.

Tilsvarende utelates `buildings.tilsyn_name`, `tilsyn_phone`, `tilsyn_email` med `*2`-variantene, som er navngitte kontaktpersoner, og `resources.contact_info`, som er fritekst og kan inneholde navn.

> Behandlingsgrunnlag og vurdering av om `organizations` bør ligge på et uautentisert endepunkt, må avklares med Capgeminis Data Privacy Officer og med kommunene som behandlingsansvarlige. Dokumentet tar ikke stilling til det rettslige spørsmålet.

---

## Autoritet: hvem vinner når kildene er uenige

Med bare to kilder er dette en regel, ikke en mekanisme. Regelen ligger her og håndheves i innlastingen:

| Felt på `bygning` | Vinner |
|---|---|
| `bygningsnr`, `bygningstype`, `byggeaar`, `bra_m2`, `geom_wkt` | Matrikkelen |
| `navn`, `hjemmeside`, `epost`, `telefon`, `apningstid_tekst` | Aktiv kommune |
| `lat`, `lon` (via `adresse`) | Matrikkelen, hvis `geokoding='matrikkel'` |
| `kapasitet` på `ressurs` | Manuell verdi over kildeverdi |

Matrikkelen vinner på byggets fakta. Aktiv kommune vinner på det publikumsvennlige navnet, for matrikkelen vet ikke at bygget heter «Flaktveit stadion».

---

## Innlasting, steg for steg

1. **Hent** `https://<kommune>.aktiv-kommune.no/bookingfrontend/searchdataall` for hver av de 12 instansene. Lagre rått i `kildeuttrekk`. Cirka 6 MB i alt.
2. **Rens tekst.** Kilden er HTML-escapet én gang for mye: `Rom 19 &amp;#40;219&amp;#41;` skal bli `Rom 19 (219)` etter to runder avkoding. `description_json` inneholder `&lt;p&gt;`-escapet HTML.
3. **Last kildekoder.** Alle `resource_categories`, `activities` og `facilities` til `kildekode`. Nye koder får forslag i `kildekode_mapping` med status `foreslatt`.
4. **Kurer.** Godkjenn eller avvis forslagene. Førstegangsarbeid er noen dager; deretter viser `v_ukartlagte_kildekoder` bare det nye.
5. **Slå opp adressene mot Kartverket.** Dette steget må komme **før** byggene lagres, fordi Adresse-API-et er det som avgjør hvilken kommune bygget ligger i. Ett oppslag på gateadresse og postnummer gir `kommunenummer`, `adressenavn`, `nummer`, `bokstav`, `representasjonspunkt` (lat/lon med EPSG-kode) samt `gardsnummer` og `bruksnummer`. API-et er åpent og krever ingen avtale.
6. **Last bygg, adresser og ressurser.** `kommune_id` settes fra oppslaget i steg 5, ikke fra subdomenet. Alle upserts på `ON CONFLICT (fagsystem_instans_id, ekstern_id) DO UPDATE`, slik at gjentatt kjøring oppdaterer i stedet for å duplisere. Bygg der adresseoppslaget mislykkes, får `geokoding='feilet'` og loggføres i `synk_avvik`; de må få kommune satt manuelt.
7. **Matrikkelen senere.** Bygningsnummer, bygningstype, byggeår, BRA og bygningsomriss krever avtale med Kartverket og dokumentert behandlingsgrunnlag. Match bygg på adresse, sett `matrikkel_match` etter sikkerhet, og oppdater byggfeltene der matrikkelen vinner. Eiendomskoblingen (`matrikkelenhet`, `bygning_matrikkelenhet`) kan derimot fylles allerede i steg 5, siden det åpne API-et gir gårds- og bruksnummer.

Rekkefølgen er viktig: Aktiv kommune definerer hvilke bygg som er relevante, adresseoppslaget avgjør kommune og koordinat, og de lisensierte matrikkeldataene beriker til slutt.

`httpx` og `psycopg` er tilstrekkelig verktøy. 6 MB fra 12 kilder rettferdiggjør ikke dbt eller Airflow.

---

## Eksempelspørringer

Finn gymsal med garderobe, uansett kommune:

```sql
SELECT navn, kommune_navn, bygg_navn, adressetekst, booking_url
FROM v_ressurs_sok
WHERE lokaletype_kode = 'GYMSAL' AND 'GARDEROBE' = ANY(fasilitet_koder);
```

Søk på hovedgruppe, slik at undertyper treffer:

```sql
WITH RECURSIVE gren AS (
    SELECT id, kode FROM lokaletype WHERE kode = 'IDRETT'
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

Hvordan en lokal kode ble tolket:

```sql
SELECT fi.kildenokkel, kk.kode, kk.navn AS lokalt_navn,
       lt.kode AS kanonisk, m.status, m.kartlagt_av
FROM kildekode kk
JOIN fagsystem_instans fi     ON fi.id = kk.fagsystem_instans_id
LEFT JOIN kildekode_mapping m ON m.kildekode_id = kk.id
LEFT JOIN lokaletype lt       ON lt.id = m.lokaletype_id
WHERE kk.kodetype = 'lokaletype'
ORDER BY fi.kildenokkel, kk.kode;
```

---

## Validering

Skjemaet er kjørt mot PostgreSQL 18, er idempotent ved gjentatt kjøring, og oppretter 16 tabeller og 2 visninger.

Mange-til-én-relasjonen (én instans, flere kommuner) er verifisert direkte på `kommune.fagsystem_instans_id`, uten koblingstabell: to kommuner på samme instans godtas, et bygg med en annen instans enn sin kommunes instans avvises via `fk_bygning_fagsystem_instans_kommune`, en ressurs med feil instans for sin kommune avvises via `fk_ressurs_fagsystem_instans_kommune`, og en ressurs i et bygg fra en annen kommune avvises via `fk_ressurs_bygning`.

Alle 12 instanser er lastet inn med reelle data:

| Tabell | Rader |
|---|---:|
| `kommune` / `fagsystem_instans` | 12 / 12 |
| `bygning` | 425 |
| `adresse` | 421 |
| `ressurs` | 1 805 |
| — med kanonisk lokaletype | 1 755 (97 %) |
| — med byggtilknytning | 1 617 |
| `kildekode` | 1 566 |
| `ressurs_aktivitet` / `ressurs_fasilitet` | 672 / 1 221 |
| `synk_avvik` | 2 635 |

Tverrkommunalt søk er verifisert. Ett søk på `GYMSAL` finner 108 gymsaler i 3 kommuner, `IDRETTSHALL` finner 154 i 4 kommuner, `FOTBALLBANE` 129 i 4 — alt gjennom én kanonisk kode, til tross for at de lokale ID-ene er uforenlige. Søk på idrettshall med garderobe gir 41 treff i Bergen, 32 i Stavanger, 15 i Øygarden og 13 i Bærum.

---

## Funn om datakvalitet

Verdt å kjenne før noe loves som søkefunksjon.

**Ingen koordinater i kilden.** Ingen av de 12 instansene har geodata. Geokoding er et obligatorisk steg, ikke en forbedring.

**Kapasitet er nesten ikke utfylt.** 2 av 590 ressurser i Bergen, 3 av 371 i Stavanger. Kapasitetsfilter vil skjule nesten alle treff til verdier fylles manuelt.

**566 av 1 805 ressurser havner i «Generelt lokale».** De små kommunene har bare to kategorier, `Lokale` og `Utstyr`, så en tredjedel av tilbudet har ingen informativ type i kilden. Kartleggingen kan ikke gjøre det bedre enn kilden er; her må kommunene selv kategorisere.

**35 ressurser har ingen kategori i det hele tatt.** Gamvik har `rescategory_id = null` på alle sine 32 ressurser, Averøy på 2, Narvik på 1. De er usynlige i typebasert søk.

**11 Stavanger-ressurser peker på kategori 12, som ikke finnes i kommunens egen kategoriliste.**

**To Bergen-bygg har søppel i postnummerfeltet:** `Totlandsvegen 53` og `5221 Nesttun`. Skjemaet avviser dem, og innlastingen loggfører dem som `ugyldig_verdi` i stedet for å trunkere stille.

**810 aktivitetskoder og 292 fasilitetskoder er ennå ukartlagte.** Lokaletypene er ferdig kartlagt for alle 12 kommuner. Aktivitet og fasilitet er større og mer rotete lister — Stavanger bruker fasilitetslisten til fritekst som «Samsung 75'' 4K skjerm» og «9 seter» — og trenger en runde manuelt arbeid.

---

## Bevisst utenfor modellen

Disse fantes i `schema_perfect.sql` og er tatt ut, fordi ingen data fyller dem eller fordi de løser problemer som ikke finnes ennå. `db/schema_perfect.sql` ligger urørt i repoet hvis noe skal hentes tilbake.

| Utelatt | Hvorfor |
|---|---|
| `etasje`, `rom`, `floy` | Kilden har ingen felt for etasje, rom eller fløy. Verifisert: 63 feltnavn i kildedata, ingen treff. |
| `flate`, `flate_rel_aggregates` | Baner er vanlige ressurser i kilden, ikke et eget begrep. |
| `uteomraade`, `uteomraade_type` | Aktiv kommune har ett stedsbegrep. `bygning.er_uteanlegg` dekker det. |
| `bruksenhet` | Kommer fra matrikkelen, men trengs ikke for å finne et lokale. |
| `gate`, `bydel` | Tekstkolonner til noen skal vedlikeholde dem som register. |
| `identitetslenke` | Bygget bærer begge identitetene selv. |
| `feltautoritet` | Med to kilder er det en regel, ikke en konfigtabell. |
| `ressurslenke` | Én bookingleverandør, én kontekst. `fagsystem_instans_id` på `ressurs` holder. |
| `ledighet_cache` | Ledighetsendepunktet er ikke funnet ennå. |
| `ressurspool`, `ressurs_rel_aggregates` | Ingen data, og ingen bruker som trenger dem i dag. |
| `classification`, `ressurs_classification` | Eksterne standardkodeverk. Ingen har bedt om NS 3451 her. |
| `ressurs.type = 'person'`, `ressurspool.type = 'staffing'` | Bemanning krever persondata og hører i HR- eller FDV-system. |

---

## Åpne spørsmål

**Skal booking gjennomføres i master, eller bare søk og videresending?** Modellen forutsetter det siste. Skal booking skje i master, kommer søker-identitet inn, med personvernkonsekvenser.

**Ledighetsendepunktet er ikke identifisert.** `/bookingfrontend/availability`, `/freetime`, `/schedule` og `/bookings` svarer alle 404. `/bookingfrontend/buildings` finnes som ekte JSON med felt `searchdataall` mangler, blant annet `town_id` og `active`. Det tyder på et bredere API som bør etterspørres hos leverandøren.

**Kommunelisten bør bekreftes.** 12 instanser er verifisert å svare: bergen, stavanger, baerum, oygarden, narvik, afjord, averoy, gamvik, inderoy, nordreisa, oksnes, sogndal. Oversikten på aktiv-kommune.no er JavaScript-generert, så listen er utledet fra lenker på siden.

**Treffraten for matrikkelmatching er ukjent.** Aktiv kommune oppgir bare gateadresse. Andelen sikre treff bør måles på et utvalg før `matrikkel_match` brukes til å avgjøre hvilke felt som overskrives.
