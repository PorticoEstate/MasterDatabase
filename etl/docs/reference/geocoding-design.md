# Geokoding: design og begrunnelser

Bakgrunn for [`jobs/geocode.py`](../jobs/geocode.md). Her står *hvorfor* den
gjør som den gjør; bruk og kommandoer står i jobbdokumentet.

## Hvorfor ikke Kartverkets åpne Adresse-API i tillegg?

Det ble det tidligere (`etl/geokod.py`, fjernet), som et raskere, uautentisert
forsteg - Matrikkelen ble bare brukt som fallback for det det åpne API-et
bommet på. Prosjektet har bevisst gått bort fra det: siden denne pipelinen bare
kjøres ved populering og innimellom, er den ekstra tiden MatrikkelAPI-kjeden
tar ikke noe problem, og ett system med én kilde er enklere å forstå og
vedlikeholde enn to. Kostnaden er målt: en nasjonal test av alle 12 kommunene
viste 69,7 % automatisk treffrate med Matrikkelen alene, mot 73,1 % med det
todelte oppsettet - et bevisst valg om noen få prosentpoengs lavere
automatikk, ikke et ukjent tap. De adressene det gjelder havner i
`synk_avvik` og rettes manuelt, akkurat som før.

## Kildens bygningsnummer (`cadastral_references`)

Innlastingen legger et bygningsnummer fra kilden i `bygning.bygningsnr`, og
`geocode_query.sql` tar med bygg der tallet ennå ikke er bekreftet
(`bygningsnr` satt og `matrikkel_match` `ikke_forsokt` eller `ikke_funnet`).
Rekkefølgen per rad er: (1) kildens bygningsnr, (2) gnr/bnr fra kilden - ikke
implementert, (3) adressen som før, for bygg uten brukbar referanse. I
praksis brukes bygningsnummeret slik:

- **Direkte oppslag først** (`BygningService.findBygning`, uten kommune), før
  adressen slås opp. Gir det ett bygg med samme bygningsnummer, settes
  `bygningsnr`, `bygningstype`, `bra_m2`, `antall_etasjer` og
  `matrikkel_match='bygningsnr'` - også når adressen ikke lar seg løse, og
  bygningsoppslaget via adressen hoppes over. `posisjon` skrives ikke her (den
  kommer fra adressen), så et feil nummer i kilden ikke kan plassere bygget et
  annet sted i landet. Finnes ikke nummeret, eller svaret ikke stemmer, logges
  avvik og kjeden går videre.
- **Adressen fra det bekreftede bygget** (`AdresseService.findAdresserForBygg`):
  av adressene Matrikkelen har for bygget brukes bare den med samme gatenavn,
  husnummer og bokstav som kildens adresse (nøyaktig ett treff); de andre
  lagres ikke. Matrikkelen markerer ikke en hovedadresse, så kildens adresse
  avgjør. Uten entydig treff slås adresseteksten opp som før. `adressetekst` er
  fortsatt kildens tekst; `gate`, `husnr`, `bokstav`, `posisjon` og
  `geokoding='matrikkel'` kommer fra Matrikkelen. Det finnes ennå ingen egen
  kolonne som sier at adressen er hentet via bygget.
- **Reserveveien**, når det direkte oppslaget ikke bekreftet nummeret: gir
  adressen **flere** bygg, hentes hvert kandidatbygg og det med samme
  bygningsnummer som kilden velges - bare ved nøyaktig ett treff
  (`matrikkel_match='bygningsnr'`). Ingen eller flere treff gir avvik og ingen
  valg. Dette er der tallet hjelper mest: av 486 løste adresser i
  demodatabasen fikk 205 ikke bygningsnr automatisk, 191 av dem fordi adressen
  har 2-7 bygg.
- Gir adressen **ett** bygg med samme nummer som kilden, settes
  `matrikkel_match='bygningsnr'`. Er nummeret et annet, logges et avvik med
  begge verdier og Matrikkelens verdi skrives (Matrikkelen vinner på identitet;
  `matrikkel_match='adresse'`).
- Rader uten bygningsnr følger kjeden uendret.

## Status for bekreftelsen og `findBygning`

**Bekreftelsen virker i praksis.** Det ene bygget som har en
`cadastral_references` i kilden fikk `matrikkel_match='bygningsnr'` i en reell
kjøring, det vil si at kildens nummer er bekreftet mot Matrikkelen. Det er
foreløpig ett bygg, ikke en systematisk test.

**Det direkte `findBygning`-kallet er ikke separat verifisert.**
`findBygning` er funnet i Kartverkets dokumentasjon (parameter `bygningsnr`, type
long; returverdien er valgfri, og dokumentasjonen nevner `FinderException` når
ingen bygning finnes) og er lagt inn i `lib/matrikkel.py`. `'bygningsnr'` settes
av tre stier (direkte oppslag, og reserveveien med flere eller ett bygg på
adressen), og verdien sier ikke hvilken som traff. Sammendraget på stderr teller
alle tre samlet. Bare det direkte oppslaget legger `bygning_via_bygningsnr` i
sporet, og reserveveien kjører bare etter et avvik fra det direkte oppslaget i
`synk_avvik`.

At bygningsnummeret er landsunikt er en slutning fra at kall og
duplikatkontroll (`finnesAnnenBygningMedSammeIdent`) ikke tar kommune, ikke noe
dokumentasjonen sier rett ut.

## Testresultat

Reelt resultat ved nasjonal testkjøring (alle 12 kommuner, 399 adresser):
278 geokodet (70 %), 121 feilet og loggført i `synk_avvik`. Feilårsakene er
enten ekte stave-/formatfeil Matrikkelen heller ikke kan matche (f.eks.
«Wolfsgate 12x» mot det offisielle «Wolffs gate»), eller mangler husnummer
helt i kildedata (f.eks. «Festplassen», «Nygårdsparken») - et
datakvalitetsproblem i kilden, ikke noe et adresseoppslag kan løse.
