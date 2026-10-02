# Aktivitetsmapping – dokumentasjon

**Versjon:** 2.0 · **Dato:** 02.10.2026 · **Status:** Utkast – til faglig gjennomgang

## Sammendrag

Masterdatabasen samler bookingdata fra flere kommuners instanser av Aktiv kommune. Hver kommune har sin egen liste over aktiviteter, med ulik stavemåte, bokmål og nynorsk, og verdier som ikke er aktiviteter (lokaler, statuser, intern bruk). For å gjøre dataene søkbare og sammenlignbare er alle **450 unike aktivitetsnavn** fra Aktiv kommune klassifisert i to filer:

| Fil | Innhold | Antall |
|---|---|---|
| `aktivitet_nif_mapping.json` | Idrettsaktiviteter mappet til NIFs idrettsstruktur | 105 |
| `aktivitet_ikke_nif_struktur.json` | Øvrige aktiviteter mappet til en egen kategoristruktur | 345 |

Hvert aktivitetsnavn finnes i nøyaktig én av filene. Begge filene har samme JSON-struktur og kan leses med samme kode. 52 mappinger har middels eller lav sikkerhet og bør bekreftes av fagpersoner før de tas i bruk i produksjon.

**Endringer fra versjon 1.0:** Versjon 1.0 bygde på en liste som allerede var delvis normalisert (332 verdier). Versjon 2.0 bygger på de originale navnene fra Aktiv kommune (450 verdier). Verdier som bare fantes i den normaliserte listen, er fjernet, og nye originalverdier er lagt til. To underkategorier har fått nye navn (koden er den samme): FRT-IDR heter nå *Idrett, trening og bading uten NIF-gren*, og IKR-TJE heter *Tjenester og utstyr*.

---

## 1. Kildegrunnlag

| Kilde | Beskrivelse |
|---|---|
| `activities-2026-09-29-450items.csv` | Uttrekk 29.09.2026 med 450 unike aktivitetsnavn (`Name`) på tvers av Aktiv kommune-instansene. Inneholder også kommuner, aktivitets-ID-er, beskrivelser og relasjoner mellom aktivitetene. UTF-8. |
| `aktiviteter_nif.csv` | NIFs idrettsstruktur (238 grener under 57 hovedidretter), filtrert på `IsValidForReporting = Sann`. Kolonner: `SportCode`, `SportName`, `IsValidForReporting`, `ParentSportName`. **Merk:** Filen er Latin-1-kodet og må leses med riktig tegnsett for å få korrekte æ/ø/å. |

### 1.1 Datakvalitet i kildenavnene

- **Variasjoner i store og små bokstaver** regnes som egne verdier og er mappet hver for seg, f.eks. «Møterom»/«møterom», «Internt Bergen kommune»/«Internt Bergen Kommune», «Ju jitsu»/«Ju Jitsu» og «Gymnastikk og turn»/«Gymnastikk og Turn».
- **HTML-kodede tegn** finnes i noen navn, f.eks. `Ski &amp;#40;Langrenn/Alpin&amp;#41;`. Nøkkelen er navnet nøyaktig slik det står i dataene, og den lesbare versjonen står i `note`. Vi anbefaler å dekode tegnene allerede når dataene hentes inn.
- **Skrivefeil og stavevarianter** er mappet til riktig kategori, f.eks. «Klartring», «Fektting», «Forestilllinger» og «Interesseorganiasjoner».

---

## 2. Felles filstruktur

Begge filene følger denne strukturen:

```json
{
  "mapping": {
    "<kildeverdi>": {
      "<overordnet nivå>": "...",
      "<underordnet nivå>": "...",
      "<kode>": "...",
      "confidence": "high | medium | low",
      "note": "..."
    }
  },
  "unmapped": []
}
```

- **Nøkkelen** i `mapping` er navnet nøyaktig slik det står i Aktiv kommune (uendret, også med skrivefeil og HTML-koder).
- **`confidence`** angir hvor sikker mappingen er (se kapittel 5).
- **`note`** finnes bare der det er behov for en forklaring.
- **`unmapped`** inneholder navn som ikke er mappet i filen.

---

## 3. NIF-mapping (`aktivitet_nif_mapping.json`)

### 3.1 Felter

| Felt | Type | Beskrivelse |
|---|---|---|
| `nif_parent` | string | Hovedidrett i NIF (`ParentSportName`), f.eks. `Dans`, `Ski`, `Kampsport`. Alltid utfylt. |
| `nif_sport` | string \| null | Konkret gren (`SportName`), f.eks. `Sportsdrill`. `null` når navnet er for generelt til å peke på én gren (f.eks. «Ski» kan være både langrenn og alpint). |
| `sport_code` | integer \| null | NIFs `SportCode` for grenen. `null` når `nif_sport` er `null`. |
| `confidence` | string | `high`, `medium` eller `low`. |
| `note` | string | Valgfri forklaring (på engelsk i denne versjonen). |

### 3.2 Eksempel

```json
"Padeltennis": {
  "nif_parent": "Tennis",
  "nif_sport": "Padel",
  "sport_code": 462,
  "confidence": "high"
},
"Dansing": {
  "nif_parent": "Dans",
  "nif_sport": null,
  "sport_code": null,
  "confidence": "high"
}
```

### 3.3 Dekning

- 105 aktivitetsnavn er mappet, hvorav 65 helt ned til konkret gren med `sport_code`.
- 48 av NIFs 57 hovedidretter og 51 av 238 grener er i bruk.
- Mappingen går én vei: fra aktivitetsnavn til NIF. NIF-grener som ingen kommune bruker i dag, er ikke med.
- `unmapped` i denne filen inneholder de 345 navnene som ikke passer i NIF. Alle er klassifisert i `aktivitet_ikke_nif_struktur.json`.
- Generell trening og bading («Trening», «Spinning», «Vanntrening», «Bading») og sjakk er ikke mappet til NIF, fordi det ikke finnes noen NIF-gren for dem.

### 3.4 Kjente forhold i NIF-strukturen

- **Grener med flere hovedidretter:** Enkelte grener finnes under flere hovedidretter (f.eks. Paintball under både *Bedrift* og *Studentidrett*, og Futsal under *Fotball*, *Bedrift* og *Studentidrett*). Valgt hovedidrett er forklart i `note`.
- **Grener som bare finnes under Studentidrett:** Noen aktiviteter (Yoga, Friluftsliv) finnes bare under *Studentidrett* og er derfor mappet dit med redusert sikkerhet.
- **Allidrett** ligger i NIF under *Idrett for funksjonshemmede*. I kommunene betyr ordet vanligvis allsidig idrett for barn.
- **Duplisert kode:** `SportCode` 992 brukes både for *Offshore* (Motorsport) og *Testgrenen* (Testaktivitet). Ingen navn er mappet til kode 992.

---

## 4. Øvrige aktiviteter (`aktivitet_ikke_nif_struktur.json`)

### 4.1 Felter

| Felt | Type | Beskrivelse |
|---|---|---|
| `parent` | string | Hovedkategori. Tilsvarer `nif_parent`. |
| `category` | string | Underkategori. Tilsvarer `nif_sport`. Alltid utfylt. |
| `category_code` | string | Stabil kode på formen `XXX-YYY`. Tilsvarer `sport_code`. |
| `confidence` | string | `high` eller `low`. |
| `note` | string | Valgfri forklaring (på norsk). |

### 4.2 Eksempel

```json
"Revy og teater": {
  "parent": "Kultur",
  "category": "Scenekunst og film",
  "category_code": "KUL-SCENE",
  "confidence": "high"
}
```

### 4.3 Kategoristruktur

| Kode | Hovedkategori | Underkategori | Antall |
|---|---|---|---|
| KUL-MUS | Kultur | Musikk, kor og korps | 10 |
| KUL-SCENE | Kultur | Scenekunst og film | 10 |
| KUL-KUNST | Kultur | Kunst, håndverk og foto | 13 |
| KUL-ARV | Kultur | Kulturarv og litteratur | 6 |
| KUL-GEN | Kultur | Kultur generelt | 3 |
| MOP-MOTE | Møter og opplæring | Møter og foredrag | 23 |
| MOP-OPP | Møter og opplæring | Undervisning og kurs | 27 |
| ORG-BU | Organisasjoner og møteplasser | Barn og unge | 11 |
| ORG-LAG | Organisasjoner og møteplasser | Lag og foreninger | 29 |
| ORG-MPL | Organisasjoner og møteplasser | Sosiale møteplasser og inkludering | 17 |
| ARR-PRIV | Arrangementer og selskap | Private selskap og bursdager | 14 |
| ARR-SER | Arrangementer og selskap | Seremonier og markeringer | 10 |
| ARR-OFF | Arrangementer og selskap | Offentlige arrangementer | 28 |
| FRT-FRI | Friluftsliv og trening | Friluftsliv | 13 |
| FRT-IDR | Friluftsliv og trening | Idrett, trening og bading uten NIF-gren | 25 |
| IKR-LOK | Ikke relevant | Lokale eller fasilitet | 43 |
| IKR-STA | Ikke relevant | Bookingstatus eller systemtekst | 17 |
| IKR-BRUK | Ikke relevant | Intern eller kommersiell bruk | 20 |
| IKR-TJE | Ikke relevant | Tjenester og utstyr | 16 |
| IKR-USP | Ikke relevant | Uspesifisert eller ukjent | 10 |
| | | **Totalt** | **345** |

### 4.4 Kategorien «Ikke relevant»

Aktivitetsfeltet i Aktiv kommune brukes også til informasjon som ikke er aktiviteter. Slike verdier samles under *Ikke relevant* (106 verdier), og underkategorien forteller hvorfor:

- **Lokale eller fasilitet (IKR-LOK):** navn på rom eller anlegg, f.eks. Gymsal, Møterom, Kulturhus, Varmtvannsbasseng.
- **Bookingstatus eller systemtekst (IKR-STA):** Stengt, Ferie, Renhold og vedlikehold, Åpningstid, systemmeldinger.
- **Intern eller kommersiell bruk (IKR-BRUK):** Internt Bergen kommune, Kommunalt bruk, Kommersiell utleie, Sambruk.
- **Tjenester og utstyr (IKR-TJE):** kommunale tjenester og utlån, f.eks. Innbyggerbussen, Veiledningstime Byggesak, Fysiotimer, Lyd, Lys, Utstyr.
- **Uspesifisert eller ukjent (IKR-USP):** Annet, Andre, X Annet, Uorganisert, og verdier med ukjent betydning.

Disse verdiene bør holdes utenfor aktivitetssøk.

### 4.5 Avgrensning mot NIF

*Idrett, trening og bading uten NIF-gren* (FRT-IDR) brukes for:

- idrettsrelaterte navn som er for generelle til å plasseres i NIF (Idrett, Barneidrett, Trening, Trim)
- trening uten NIF-gren (Spinning, Styrketrening, Vanntrening)
- bading
- aktiviteter som ikke er NIF-idretter (E-sport, Sjakk, Bowls)

---

## 5. Sikkerhetsnivå (`confidence`)

| Nivå | Betydning |
|---|---|
| `high` | Entydig treff, også ved skrivefeil eller nynorsk/bokmål-variant (f.eks. «Klartring» → Klatring, «Symjehall» → Svømming). |
| `medium` | Rimelig tolkning, men navnet er f.eks. et anleggsnavn eller kan passe flere steder. Brukes bare i NIF-filen. |
| `low` | Usikker tolkning. Bør bekreftes av en fagperson eller av kommunen. |

### 5.1 Mappinger som bør bekreftes – NIF

| Navn | Mappet til | Sikkerhet | Merknad |
|---|---|---|---|
| Allidrett | Idrett for funksjonshemmede → Allidrett (878) | medium | I kommunene vanligvis allsidig idrett for barn |
| Babysvømming | Svømming | medium | Babysvømming, ikke konkurransesvømming |
| Bandy - inne | Bandy | medium | Kan være innebandy eller rinkbandy |
| Dans/trening | Dans | medium | Kombinert dans og trening |
| Drill | Dans → Sportsdrill (518) | medium | Finnes også under Studentidrett (981) |
| Fleiridrettslag / Fleridrettslag | Fleridretter | medium | Et fleridrettslag er ikke nødvendigvis NIFs «Fleridretter» |
| Fotballbane | Fotball | medium | Anleggsnavn |
| Innefotball | Fotball → Futsal (262) | medium | |
| Klatrevegg | Klatring → Klatring (591) | medium | Anleggsnavn |
| Paintball | Bedrift → Paintball (152) | medium | Finnes også under Studentidrett (984) |
| Symjehall | Svømming | medium | Anleggsnavn |
| Yoga | Studentidrett → Yoga (628) | medium | Finnes bare under Studentidrett |
| Bil/MC klubb | Motorsport | low | Klubben driver ikke nødvendigvis idrett |
| Friluftsliv | Studentidrett → Friluftsliv (622) | low | Finnes bare under Studentidrett |
| Funksjonhemma | Idrett for funksjonshemmede | low | Brukergruppe, ikke nødvendigvis idrett |
| Hundesport | Hundekjøring | low | Kan være agility o.l. (ikke NIF) |
| Musikk og dans | Dans | low | Blandet kategori |
| Skating | Brett → Skateboard (732) | low | Kan også bety skøyter eller rulleskøyter |

I tillegg er **Taekwondo** mappet til Kampsport uten gren, fordi det er ukjent om det gjelder ITF (524) eller WT (522), og **Ski (Langrenn/Alpin)** er mappet til Ski uten gren.

### 5.2 Mappinger som bør bekreftes – øvrige

| Navn | Mappet til | Merknad |
|---|---|---|
| Andre aktivitetar, konsertar, o.l | KUL-MUS | Blandet kategori |
| Arrangement og møte | ARR-OFF | Blandet kategori |
| Bowls | FRT-IDR | Kan være skrivefeil for Bowling (NIF) |
| Buekorps | ORG-BU | Bergensk tradisjon, ikke bueskyting |
| Båtforeingar | ORG-LAG | Kan være seiling/padling (NIF) |
| Dans/ Musikk/ Kor/ Korps | KUL-MUS | Blandet kategori – dans hører til NIF Dans |
| Datahjelp | MOP-OPP | Kan også være kommunal tjeneste |
| Disko | ARR-PRIV | Kan også være ungdomsarrangement |
| Drop-in / arbeidsplasser | IKR-LOK | Kan også være sosial møteplass |
| Flykningekontoret | IKR-BRUK | Kan også være Inkludering |
| Foreldreutval | ORG-LAG | Kan også høre til Opplæring |
| Frisklivsentralen | FRT-IDR | Kommunal helsetjeneste med treningsgrupper |
| Fritidstilbud | ORG-BU | Generelt fritidstilbud – antatt for barn og unge |
| Kamera | IKR-TJE | Antatt kamerautstyr |
| Lokale aktiviteter-idrett-kultur | IKR-USP | Blandet kategori |
| Lyd | IKR-TJE | Antatt lydutstyr |
| Lys | IKR-TJE | Antatt lysutstyr |
| Makeup & Hundpleie | IKR-TJE | Uklar verdi |
| Markering | ARR-SER | Kan også være offentlig markering/demonstrasjon |
| Matlaging | MOP-OPP | Kan også være Sosial møteplass |
| Messe | ARR-OFF | Kan være varemesse eller gudstjeneste |
| Møter, kurs, mindre selskaper | MOP-MOTE | Blandet kategori |
| NRG | IKR-USP | Ukjent forkortelse |
| Offentlig | IKR-USP | Antatt brukertype, ikke aktivitet |
| Privat | ARR-PRIV | Antatt privat booking – uklart innhold |
| PU/HU | ORG-MPL | Antatt tilrettelagt tilbud – bekreft betydning |
| Saltimer | IKR-LOK | Generell saltid for ulike aktiviteter |
| Sirkus | KUL-SCENE | Kan også være sirkustrening/akrobatikk |
| Sjakk | FRT-IDR | Sjakk er ikke NIF-idrett |
| Spill | ORG-MPL | Kan være brettspill/rollespill eller e-sport |
| Team-building | MOP-MOTE | Kan også være privat/bedriftsarrangement |
| Treklang | IKR-USP | Ukjent – muligens navn på kor/ensemble |
| Walk and talk - test | FRT-FRI | Testverdi |

---

## 6. Bruk i masterdatabasen

1. **Ta vare på originalverdien.** Navnet (og instans/kommune) lagres uendret. Mappingen legges i en egen koblingstabell, slik at kategorier kan endres uten å røre historiske data.
2. **Slå opp i begge filene.** Et navn slås først opp i NIF-filen, deretter i filen for øvrige aktiviteter. Det skal aldri gi treff i begge.
3. **Filtrer «Ikke relevant».** Verdier med `parent = "Ikke relevant"` eller `category_code` som starter på `IKR-`, holdes utenfor aktivitetssøk.
4. **Bruk koder som nøkler.** Bruk `sport_code` og `category_code` som stabile nøkler, siden navn kan endres.

---

## 7. Vedlikehold

- **Nye verdier:** Når nye kommuner kobles på, eller eksisterende kommuner legger til aktiviteter, sammenlignes nye navn med nøklene som finnes. Navn uten treff legges i `unmapped` og vurderes manuelt.
- **Matching:** Mappingen må bruke navnet nøyaktig som det står, fordi varianter med store og små bokstaver og HTML-koder er egne nøkler. Normalisering (små bokstaver, dekodet HTML, uten ekstra mellomrom) kan brukes til å *foreslå* mapping for nye verdier.
- **Endringer i NIF:** NIF-strukturen kan endres. Kontroller jevnlig at hver `sport_code` fortsatt finnes og er gyldig for rapportering.
- **Nye kategorier:** Nye kategorikoder legges til, men eksisterende koder endres eller gjenbrukes ikke.

---

## 8. Begrensninger

- Mappingen er laget ut fra aktivitetsnavnet og de tilgjengelige beskrivelsene, uten innsyn i bookingene. Navn som er tvetydige, er merket med lav sikkerhet.
- Noen navn beskriver egentlig en brukergruppe eller organisasjonstype (f.eks. Speider, Barnehage) og ikke en aktivitet. De er likevel plassert i aktivitetsstrukturen fordi det er slik de brukes i dag.
- Relasjonene mellom aktiviteter i kildeuttrekket (parent/child) er ikke brukt i mappingen. De ser ut til å følge ID-er per kommune og er ikke konsistente på tvers av kommunene.
- `note`-feltet er på engelsk i NIF-filen og på norsk i filen for øvrige aktiviteter.

---

*Mappingene og dokumentasjonen er laget med KI-støtte og må kvalitetssikres før de deles eksternt eller tas i bruk i produksjon.*
