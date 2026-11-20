# Videre utvikling

## Sammendrag

Denne løsningen dekker kjernebehovet: samlet søk i ressurser på tvers av fagsystemer, med filtrering og synkronisering. Dokumentet beskriver hva vi ville prioritert videre med mer tid. De fleste punktene bygger på data som allerede ligger i databasen og viewet.

| # | Tiltak | Kompleksitet | Datagrunnlag finnes |
|---|--------|--------------|---------------------|
| 1 | Fuzzy-søk / toleranse for skrivefeil | Middels | Delvis |
| 2 | Endepunkt: antall ressurser per bygg | Lav | Ja |
| 3 | Filtrering på fylke | Lav | Ja (i viewet) |
| 4 | Filtrering på kapasitet | Lav–middels | Ja (i viewet) |
| 5 | Retting av feil totalantall på tomme søkesider | Lav | Ja |
| 6 | Flere tester | Middels | – |

## Anbefalt rekkefølge

**Raske gevinster (data finnes allerede):**
1. Punkt 3 (fylke) og 2 (antall per bygg)
2. Punkt 4 (kapasitet)

**Anbefalt neste store steg:**
3. Punkt 1 (fuzzy-søk). Krever mer arbeid, men gir størst effekt for sluttbruker.

**Kvalitet og stabilitet:**
4. Punkt 5 (feil totalantall på tomme søkesider, lite arbeid)
5. Punkt 6 (tester). Bør følge hvert tiltak løpende, ikke vente til slutt.

## 1. Fuzzy-søk / søk med toleranse for skrivefeil

**Anbefaling:** Vi anbefaler at dette følges opp som neste store steg. Brukere skriver ofte navn på bygg og ressurser med små avvik (stavefeil, æ/ø/å, bindestrek eller mellomrom). Et eksakt søk gir da null treff, selv om riktig ressurs finnes.

**Status:** Søket er i dag eksakt/delstreng-basert og håndterer ikke stavefeil. Vi startet på en fuzzy-løsning, men tok den ut igjen for å prioritere stabil kjernefunksjonalitet. Løsningen er derfor ikke ferdigstilt eller testet, og er ikke en del av leveransen.

**Forslag til videre arbeid:**
- Vurdere trigram-søk (`pg_trgm`) i PostgreSQL, evt. kombinert med normalisering av æ/ø/å og vanlige varianter. Dette gir bedre treff uten ekstern søkemotor.
- Teste rangering og terskelverdier mot reelle søkeord fra brukerne, for å unngå støy i treffene.
- Dekke løsningen med tester (se punkt 6) før den tas i bruk.

## 2. Endepunkt for antall ressurser i et bygg

**Behov:** Brukere ønsker å se hvor mange ressurser et bygg har, uten å hente hele ressurslisten.

**Forslag:** Eget lesende endepunkt som returnerer antall per bygg (evt. gruppert på ressurstype). Kan ofte løses med en enkel aggregering over eksisterende data, og kan også brukes til å vise antall i filtervalgene.

## 3. Filtrering på fylke

**Status:** Fylkesnavn er allerede med i viewet.

**Forslag:** Eksponere fylker som filterverdier i filterendepunktet og ta dem inn som søkeparameter i søket. Lite arbeid, siden datagrunnlaget er på plass.

## 4. Filtrering på kapasitet

**Status:** Kapasitet er allerede med i viewet.

**Forslag:** Utvide søket med kapasitetsfilter, enten som minimumskapasitet eller som intervall (fra–til). Avklaringspunkt: hvordan kapasitet skal tolkes der fagsystemene rapporterer ulikt eller mangler verdi.

## 5. Feil totalantall på tomme søkesider

**Feilen:** Søket (`/masterdb/search`) returnerer `totalt: 0` når brukeren ber om en side som ligger utenfor treffene, selv om søket har treff. Eksempel: et søk gir 25 treff, og klienten ber om `side=5&storrelse=20`. Siden er tom, og svaret sier at det finnes 0 treff i stedet for 25. Feilen gjelder både `bygg` og `ressurser`, siden de pagineres hver for seg.

**Årsak:** Totalantallet hentes fra radene i selve svaret (`count(*) OVER ()` i `RessursSokRepository`). Når siden er tom, finnes det ingen rader å lese totalen fra, og koden bruker 0 som standardverdi. Totalen er dermed riktig bare så lenge siden inneholder minst ett treff.

**Konsekvens:** Frontend kan få inntrykk av at søket ikke har treff, eller vise «0 treff» og feil antall sider. Dette skjer typisk når et filter eller en sortering endres mens brukeren står på en høy sidenummer, eller når data endres mellom to kall (for eksempel etter en refresh av søkeviewet). Siden `side × storrelse` er begrenset til 50 000, er feilen avgrenset til tomme sider innenfor den grensen. På side 0 er 0 riktig, fordi det da ikke finnes treff.

**Forslag til utbedring:** Hvis siden er tom og `side` er større enn 0, kjøres en egen telle-spørring med samme filter som søket, og totalen hentes derfra. Spørringen kjøres bare i dette sjeldne tilfellet og påvirker derfor ikke vanlige søk. For `bygg` må den telle antall bygg (`count(DISTINCT bygg_id)`), ikke antall ressurser. Et enklere alternativ er at frontend ikke går til sider utenfor `totalt` fra forrige svar, men det løser ikke tilfellet der data endres mellom kallene.

**Test:** Dekkes av en integrasjonstest (se punkt 6) som ber om en side utenfor treffene og verifiserer at `totalt` er det faktiske antallet, og at `treff` er tom.

## 6. Flere tester

**Status:** Testdekningen er begrenset, og løsningen bør få bredere automatisert testing før den tas videre i produksjon.

**Forslag:**
- **Enhetstester** for forretningslogikk, blant annet synkronisering og aktiv/inaktiv-markering av ressurser og bygninger.
- **Integrasjonstester** for søke-API og filterendepunkt mot en reell PostgreSQL-instans (f.eks. Testcontainers), slik at view og spørringer testes realistisk.
- **Tester for ETL og synk**, inkludert avvikshåndtering (`synk_avvik`) og forventede avvik som manglende forelder.
- **Regresjonstester** for nye tiltak (fylke, kapasitet, antall per bygg og evt. fuzzy-søk), slik at endringer ikke bryter eksisterende søk.
- **Kjøring i CI**, slik at testene kjøres automatisk ved hver pull request.
