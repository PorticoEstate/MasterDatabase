# Videre utvikling

## Sammendrag

Dagens løsning dekker kjernebehovet til masterdatabasen, men grunnet prosjektets tidsbegrensede natur er ikke tjenesten fullstendig.
Vi lister derfor her funksjoner som tjenesten ikke har i dag men som har vært nevnt at bør implementeres:

- Normalisering av hierarkiene (aktivitet/lokaletype/fasilitet) i Aktiv Kommune
- Fuzzy-søk / toleranse for skrivefeil i søkeendepunktet
- Endepunkt for å hente seed data til ny AK-instans
- Endepunkt: antall ressurser per bygg
- Filtrering på fylke
- Filtrering på kapasitet
- Retting av feil totalantall på tomme søkesider
- Flere tester

## Normalisering av hierarkiene (aktivitet/lokaletype/fasilitet) i Aktiv Kommune
**Beskrivelse:** Per dags dato (23.11.26) er hierarkiene for aktivitet/lokaletype/fasilitet ikke normaliserte. Det vil si at en aktivitet kan ligge med én id i Bergen og en annen i Stavanger. Da får man også kollisjoner på parent IDs, noe som bryter den hierarkiske strukturen man ønsker å bruke ved søk i databasen.

**Status:** Vi har dokumentert et forslag for hvordan man kan normalisere dataen i Aktiv Kommune-instansene, som ligger i: [/normalization-playbook/AktivKommune_normalisation_playbook.md](/normalization-playbook/AktivKommune_normalisation_playbook.md).

**Avhengighet:** Før man normaliserer dataen må man avklare det endelige hierarkiet for de tre kodeverkene. Man må også gå gjennom mappingene som skal ta de gamle kodeverkene og overføre koblingene deres til de nye normaliserte kodeverkene.

## Fuzzy-søk / søk med toleranse for skrivefeil

**Beskrivelse:**  Brukere skriver ofte navn på bygg og ressurser med små avvik (stavefeil, æ/ø/å, bindestrek eller mellomrom). Et eksakt søk gir da null treff, selv om riktig ressurs finnes.

**Status:** Søket er i dag eksakt/delstreng-basert og håndterer ikke stavefeil. Vi startet på en fuzzy-løsning, men tok den ut igjen for å prioritere stabil kjernefunksjonalitet. Løsningen er derfor ikke ferdigstilt eller testet, og er ikke en del av leveransen.

**Forslag til videre arbeid:**
- Vurdere trigram-søk (`pg_trgm`) i PostgreSQL, evt. kombinert med normalisering av æ/ø/å og vanlige varianter. Dette gir bedre treff uten ekstern søkemotor.
- Teste rangering og terskelverdier mot reelle søkeord fra brukerne, for å unngå støy i treffene.
- Dekke løsningen med tester (se punkt 6) før den tas i bruk.

## Endepunkt for antall ressurser i et bygg

**Behov:** Brukere ønsker å se hvor mange ressurser et bygg har, uten å hente hele ressurslisten.

**Forslag:** Eget lesende endepunkt som returnerer antall per bygg (evt. gruppert på ressurstype). Kan ofte løses med en enkel aggregering over eksisterende data, og kan også brukes til å vise antall i filtervalgene.

## Endepunkt for seed data til nye Aktiv Kommune-instanser

**Beskrivelse:** Underveis i prosjektet har det blitt nevnt at man ønsker et endepunkt for å hente ut seed data for å starte nye Aktiv Kommune-instanser. Ved å legge inn en ny kommune i databasen vil hele gatetabellen for kommunen hentes. Med denne dataen kan man da lage grunnlaget for en ny Aktiv Kommune-instans. De får hele hierarkiet for aktivitet/lokaletype/fasilitet samt alle gatene i kommunen som startdata før de begynner å legge til egne bygg og ressurser.


## Filtrering på fylke

**Status:** Fylkesnavn er allerede med i viewet.

**Forslag:** Eksponere fylker som filterverdier i filterendepunktet og ta dem inn som søkeparameter i søket. Lite arbeid, siden datagrunnlaget er på plass.

## Filtrering på kapasitet

**Status:** Kapasitet er allerede med i viewet, men dataen er veldig tynn, da det ikke ligger inne for de fleste ressurser, og noen har det i tekstbeskrivelsen.

**Forslag:** Utvide søket med kapasitetsfilter, enten som minimumskapasitet eller som intervall (fra–til). 

**Avhengighet:** Krever at man legger inn dataen for kapasitet i ressursene til Aktiv Kommune-instansene.

## Feil totalantall på tomme søkesider

**Feilen:** Søket (`/masterdb/search`) returnerer `totalt: 0` når brukeren ber om en side som ligger utenfor treffene, selv om søket har treff. Eksempel: et søk gir 25 treff, og klienten ber om `side=5&storrelse=20`. Siden er tom, og svaret sier at det finnes 0 treff i stedet for 25. Feilen gjelder både `bygg` og `ressurser`, siden de pagineres hver for seg.

**Årsak:** Totalantallet hentes fra radene i selve svaret (`count(*) OVER ()` i `RessursSokRepository`). Når siden er tom, finnes det ingen rader å lese totalen fra, og koden bruker 0 som standardverdi. Totalen er dermed riktig bare så lenge siden inneholder minst ett treff.

**Konsekvens:** Frontend kan få inntrykk av at søket ikke har treff, eller vise «0 treff» og feil antall sider. Dette skjer typisk når et filter eller en sortering endres mens brukeren står på en høy sidenummer, eller når data endres mellom to kall (for eksempel etter en refresh av søkeviewet). Siden `side × storrelse` er begrenset til 50 000, er feilen avgrenset til tomme sider innenfor den grensen. På side 0 er 0 riktig, fordi det da ikke finnes treff.

**Forslag til utbedring:** Hvis siden er tom og `side` er større enn 0, kjøres en egen telle-spørring med samme filter som søket, og totalen hentes derfra. Spørringen kjøres bare i dette sjeldne tilfellet og påvirker derfor ikke vanlige søk. For `bygg` må den telle antall bygg (`count(DISTINCT bygg_id)`), ikke antall ressurser. Et enklere alternativ er at frontend ikke går til sider utenfor `totalt` fra forrige svar, men det løser ikke tilfellet der data endres mellom kallene.

**Test:** Dekkes av en integrasjonstest (se punkt 6) som ber om en side utenfor treffene og verifiserer at `totalt` er det faktiske antallet, og at `treff` er tom.

## Flere tester

**Status:** Testdekningen er veldig begrenset, og løsningen bør få bredere automatisert testing før den tas videre i produksjon.

**Forslag:**
- **Enhetstester** for forretningslogikk, blant annet synkronisering og aktiv/inaktiv-markering av ressurser og bygninger.
- **Integrasjonstester** for søke-API og filterendepunkt mot en reell PostgreSQL-instans (f.eks. Testcontainers), slik at view og spørringer testes realistisk.
- **Tester for ETL og synk**, inkludert avvikshåndtering (`synk_avvik`) og forventede avvik som manglende forelder.
- **Regresjonstester** for nye tiltak (fylke, kapasitet, antall per bygg og evt. fuzzy-søk), slik at endringer ikke bryter eksisterende søk.
- **Kjøring i CI**, slik at testene kjøres automatisk ved hver pull request.
