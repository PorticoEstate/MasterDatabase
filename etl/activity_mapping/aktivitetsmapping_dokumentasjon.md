# Aktivitetsmapping – dokumentasjon

**Versjon:** 3.0 · **Dato:** 02.10.2026 · **Status:** Utkast – til faglig gjennomgang

## Sammendrag

Masterdatabasen samler bookingdata fra flere kommuners instanser av Aktiv kommune. Hver kommune har sin egen liste over aktiviteter, med ulik stavemåte, bokmål og nynorsk, og verdier som ikke er aktiviteter (lokaler, statuser, intern bruk). For å gjøre dataene søkbare og sammenlignbare er alle **450 unike aktivitetsnavn** fra Aktiv kommune klassifisert i to filer:

| Fil | Innhold | Antall |
|---|---|---|
| `aktivitet_nif_mapping.json` | Idrettsaktiviteter mappet til NIFs idrettsstruktur | 100 |
| `aktivitet_ikke_nif_struktur.json` | Øvrige aktiviteter mappet til en egen kategoristruktur | 350 |

Hvert aktivitetsnavn finnes i nøyaktig én av filene. Begge filene har samme JSON-struktur og kan leses med samme kode. 63 mappinger har middels eller lav sikkerhet og bør bekreftes av fagpersoner før de tas i bruk i produksjon.

**Endringer i versjon 3.0:** Et aktivitetsnavn kan nå mappes til **flere** NIF-grener. Feltet `nif_sport`/`sport_code` er erstattet av listen `nif_sports`, og tilsvarende `categories` i filen for øvrige aktiviteter. Generelle navn som «Ski» og «Dans» mappes til NIF-grenen med samme navn (f.eks. Ski 892 under *Bedrift*) i stedet for en vilkårlig undergren. Navn som nevner flere grener («Ski (Langrenn/Alpin)», «Kano/kajakk») mappes til hver av dem. Generelle navn uten egen NIF-gren («Seiling», «Friidrett») mappes til alle grenene under hovedidretten, slik at ressursen dukker opp uansett hvilken gren det søkes på.

**Endringer i versjon 2.1:** Alle NIF-mappinger peker nå på en konkret gren med `sport_code` (`nif_sport` er aldri `null`). Der navnet er generelt, er den vanligste grenen valgt med sikkerhet `medium`, og alternativene står i `note` (se kapittel 3.4). «Bandy - inne» er mappet til Innebandy (133). Fem navn uten passende NIF-gren er flyttet til filen for øvrige aktiviteter: «Fleiridrettslag», «Fleridrettslag», «Hundesport», «Funksjonhemma» og «Musikk og dans».

**Endringer i versjon 2.0:** Versjon 1.0 bygde på en liste som allerede var delvis normalisert (332 verdier). Versjon 2.0 bygger på de originale navnene fra Aktiv kommune (450 verdier). Verdier som bare fantes i den normaliserte listen, er fjernet, og nye originalverdier er lagt til. To underkategorier har fått nye navn (koden er den samme): FRT-IDR heter nå *Idrett, trening og bading uten NIF-gren*, og IKR-TJE heter *Tjenester og utstyr*.

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
      "<liste med mål>": [
        { "<overordnet nivå>": "...", "<underordnet nivå>": "...", "<kode>": "..." }
      ],
      "confidence": "high | medium | low",
      "note": "..."
    }
  },
  "unmapped": []
}
```

- **Nøkkelen** i `mapping` er navnet nøyaktig slik det står i Aktiv kommune (uendret, også med skrivefeil og HTML-koder).
- **Listen med mål** har ett eller flere innslag. Flere innslag betyr at ressursen skal treffes ved søk på alle disse grenene/kategoriene.
- **`confidence`** angir hvor sikker mappingen er (se kapittel 5).
- **`note`** finnes bare der det er behov for en forklaring.
- **`unmapped`** inneholder navn som ikke er mappet i filen.

---

## 3. NIF-mapping (`aktivitet_nif_mapping.json`)

### 3.1 Felter

| Felt | Type | Beskrivelse |
|---|---|---|
| `nif_sports` | liste | Ett eller flere NIF-mål. Hvert innslag har `nif_parent` (hovedidrett, `ParentSportName`), `nif_sport` (gren, `SportName`) og `sport_code` (NIFs `SportCode`). Alltid minst ett innslag. |
| `confidence` | string | `high`, `medium` eller `low`. |
| `note` | string | Valgfri forklaring (på engelsk i denne versjonen). |

### 3.2 Eksempel

```json
"Ski &amp;#40;Langrenn/Alpin&amp;#41;": {
  "nif_sports": [
    { "nif_parent": "Ski", "nif_sport": "Langrenn", "sport_code": 422 },
    { "nif_parent": "Ski", "nif_sport": "Alpint", "sport_code": 424 }
  ],
  "confidence": "high",
  "note": "Name covers several grener; mapped to each; HTML-encoded name, decoded: Ski (Langrenn/Alpin)"
},
"Ski": {
  "nif_sports": [
    { "nif_parent": "Bedrift", "nif_sport": "Ski", "sport_code": 892 }
  ],
  "confidence": "high"
}
```

### 3.3 Dekning

- 100 aktivitetsnavn er mappet, alle til minst én konkret gren med `sport_code`. 21 navn er mappet til flere grener.
- 46 av NIFs 57 hovedidretter og 137 av 238 grener er i bruk.
- Mappingen går én vei: fra aktivitetsnavn til NIF. NIF-grener som ingen kommune bruker i dag, er ikke med.
- `unmapped` i denne filen inneholder de 350 navnene som ikke passer i NIF. Alle er klassifisert i `aktivitet_ikke_nif_struktur.json`.
- Generell trening og bading («Trening», «Spinning», «Vanntrening», «Bading»), sjakk, fleridrettslag og hundesport er ikke mappet til NIF, fordi ingen NIF-gren passer.

### 3.4 Regler for valg av gren

1. **Gren med samme navn finnes:** Navnet mappes til den grenen, uavhengig av hvilken hovedidrett den ligger under. «Ski», «Dans», «Skyting», «Skøyter» og «Sykkel» finnes som grener under *Bedrift* og brukes for de generelle navnene. `confidence: high`.
2. **Navnet nevner flere grener:** Mappes til hver av dem, f.eks. «Ski (Langrenn/Alpin)» → Langrenn (422) og Alpint (424), «Kano/kajakk» → Kano, Havpadling og Flattvann, «Taekwondo» → WT (522) og ITF (524), «Bandy - inne» → Innebandy (133) og Rinkbandy (132). `confidence: high`.
3. **Generelt navn uten egen gren:** Mappes til alle grenene under hovedidretten, f.eks. «Seiling» → alle 7 grener under *Seiling*, «Kampsport» → alle 9 grener under *Kampsport*. Dette gjelder Friidrett, Seiling/Seilsport, Riding/Hestesport, Bryting, Bueskyting, Roing, Luftsport, Motorsport, Kampsport, Gymnastikk (og turn) og Bedriftsidrett. `confidence: medium`, fordi enkelte av grenene kan være lite aktuelle for ressursen.
(Dette er et design valg som må vurderes! Noen parentSports har ikke selv en sportCode. Eks. Judo og karate er child av Kampsport, men kampsport har ingen sportCode til sammenligning så er Volleyball en sport med egen sportCode men den har også Sandvolleyball som child)

Hensikten er at en ressurs skal dukke opp uansett om det søkes på hovedidretten eller på en gren.

### 3.5 Kjente forhold i NIF-strukturen

- **Grener med flere hovedidretter:** Enkelte grener finnes under flere hovedidretter (f.eks. Paintball under både *Bedrift* og *Studentidrett*, og Futsal under *Fotball*, *Bedrift* og *Studentidrett*). Valgt hovedidrett er forklart i `note`.
- **Grener som bare finnes under Studentidrett:** Noen aktiviteter (Yoga, Friluftsliv) finnes bare under *Studentidrett* og er derfor mappet dit med redusert sikkerhet.
- **Grener under *Bedrift*:** NIF har generelle grener som Ski (892), Dans (885), Skyting (883), Skøyter (886) og Sykkel (881) under hovedidretten *Bedrift*. De brukes her som mål for generelle navn; at hovedidretten er *Bedrift*, er ikke en begrensning.
- **Allidrett** ligger i NIF under *Idrett for funksjonshemmede*. I kommunene betyr ordet vanligvis allsidig idrett for barn.
- **Duplisert kode:** `SportCode` 992 brukes både for *Offshore* (Motorsport) og *Testgrenen* (Testaktivitet). Ingen navn er mappet til kode 992.


## 4. Øvrige aktiviteter (`aktivitet_ikke_nif_struktur.json`)

### 4.1 Felter

| Felt | Type | Beskrivelse |
|---|---|---|
| `categories` | liste | Ett eller flere mål. Hvert innslag har `parent` (hovedkategori), `category` (underkategori) og `category_code` (stabil kode på formen `XXX-YYY`). I denne versjonen har alle navn nøyaktig ett innslag, men strukturen tillater flere. |
| `confidence` | string | `high` eller `low`. |
| `note` | string | Valgfri forklaring (på norsk). |

### 4.2 Eksempel

```json
"Revy og teater": {
  "categories": [
    { "parent": "Kultur", "category": "Scenekunst og film", "category_code": "KUL-SCENE" }
  ],
  "confidence": "high"
}
```

### 4.3 Kategoristruktur

| Kode | Hovedkategori | Underkategori | Antall |
|---|---|---|---|
| KUL-MUS | Kultur | Musikk, kor og korps | 11 |
| KUL-SCENE | Kultur | Scenekunst og film | 10 |
| KUL-KUNST | Kultur | Kunst, håndverk og foto | 13 |
| KUL-ARV | Kultur | Kulturarv og litteratur | 6 |
| KUL-GEN | Kultur | Kultur generelt | 3 |
| MOP-MOTE | Møter og opplæring | Møter og foredrag | 23 |
| MOP-OPP | Møter og opplæring | Undervisning og kurs | 27 |
| ORG-BU | Organisasjoner og møteplasser | Barn og unge | 11 |
| ORG-LAG | Organisasjoner og møteplasser | Lag og foreninger | 29 |
| ORG-MPL | Organisasjoner og møteplasser | Sosiale møteplasser og inkludering | 18 |
| ARR-PRIV | Arrangementer og selskap | Private selskap og bursdager | 14 |
| ARR-SER | Arrangementer og selskap | Seremonier og markeringer | 10 |
| ARR-OFF | Arrangementer og selskap | Offentlige arrangementer | 28 |
| FRT-FRI | Friluftsliv og trening | Friluftsliv | 13 |
| FRT-IDR | Friluftsliv og trening | Idrett, trening og bading uten NIF-gren | 28 |
| IKR-LOK | Ikke relevant | Lokale eller fasilitet | 43 |
| IKR-STA | Ikke relevant | Bookingstatus eller systemtekst | 17 |
| IKR-BRUK | Ikke relevant | Intern eller kommersiell bruk | 20 |
| IKR-TJE | Ikke relevant | Tjenester og utstyr | 16 |
| IKR-USP | Ikke relevant | Uspesifisert eller ukjent | 10 |
| | | **Totalt** | **350** |

### 4.4 Kategorien «Ikke relevant»

Aktivitetsfeltet i Aktiv kommune brukes også til informasjon som ikke er aktiviteter. Slike verdier samles under *Ikke relevant* (106 verdier), og underkategorien forteller hvorfor:

- **Lokale eller fasilitet (IKR-LOK):** navn på rom eller anlegg, f.eks. Gymsal, Møterom, Kulturhus, Varmtvannsbasseng.
- **Bookingstatus eller systemtekst (IKR-STA):** Stengt, Ferie, Renhold og vedlikehold, Åpningstid, systemmeldinger.
- **Intern eller kommersiell bruk (IKR-BRUK):** Internt Bergen kommune, Kommunalt bruk, Kommersiell utleie, Sambruk.
- **Tjenester og utstyr (IKR-TJE):** kommunale tjenester og utlån, f.eks. Innbyggerbussen, Veiledningstime Byggesak, Fysiotimer, Lyd, Lys, Utstyr.
- **Uspesifisert eller ukjent (IKR-USP):** Annet, Andre, X Annet, Uorganisert, og verdier med ukjent betydning.

Disse verdiene bør holdes utenfor aktivitetssøk. Underkategoriene gjør det mulig å bruke dem som egne felter (lokaletype, status, brukstype) i masterdatabasen.

### 4.5 Avgrensning mot NIF

*Idrett, trening og bading uten NIF-gren* (FRT-IDR) brukes for:

- idrettsrelaterte navn som er for generelle til å plasseres i NIF (Idrett, Barneidrett, Trening, Trim)
- trening uten NIF-gren (Spinning, Styrketrening, Vanntrening)
- bading
- aktiviteter som ikke er NIF-idretter (E-sport, Sjakk, Bowls, Hundesport)
- fleridrettslag (Fleiridrettslag, Fleridrettslag), som ikke har én bestemt gren

---

## 5. Sikkerhetsnivå (`confidence`)

| Nivå | Betydning |
|---|---|
| `high` | Entydig treff, også ved skrivefeil eller nynorsk/bokmål-variant (f.eks. «Klartring» → Klatring, «Symjehall» → Svømming). |
| `medium` | Rimelig tolkning, men navnet er et anleggsnavn, kan passe flere steder, eller er et generelt idrettsnavn mappet til alle grener under hovedidretten. Brukes bare i NIF-filen. |
| `low` | Usikker tolkning. Bør bekreftes av en fagperson eller av kommunen. |

### 5.1 Mappinger som bør bekreftes – NIF

3 mappinger med lav og 24 med middels sikkerhet. Merknaden er hentet direkte fra `note` (på engelsk).

| Navn | Mappet til | Sikkerhet | Merknad |
|---|---|---|---|
| Bil/MC klubb | MC Touring (996) | low | Club may be non-sporting; car clubs may fit Circuit (993) |
| Friluftsliv | Friluftsliv (622) | low | Only exists under Studentidrett in NIF |
| Skating | Skateboard (732) | low | Could also mean skøyter/rulleskøyter |
| Allidrett | Allidrett (878) | medium | NIF Allidrett is under disability sport; municipal 'allidrett' is usually general multi-sport for children |
| Babysvømming | Svømming (451) | medium | Swimming for infants; mapped to general Svømming |
| Bedriftsidrett | 15 grener under Bedrift | medium | Generic name for hovedidrett Bedrift; mapped to all grener under it |
| Bryting | 6 grener under Bryting | medium | Generic name for hovedidrett Bryting; mapped to all grener under it |
| Bueskyting | Ski - Bueskyting (203); Skivebueskyting (201); Skogsskyting (3D og Felt) (202) | medium | Generic name for hovedidrett Bueskyting; mapped to all grener under it |
| Drill | Sportsdrill (518) | medium | Also 'Drill' under Studentidrett (981) |
| Fotballbane | Fotball (261) | medium | Facility name |
| Friidrett | 5 grener under Friidrett | medium | Generic name for hovedidrett Friidrett; mapped to all grener under it |
| Gymnastikk | 9 grener under Gymnastikk og turn | medium | Generic name for hovedidrett Gymnastikk og turn; mapped to all grener under it |
| Gymnastikk og turn | 9 grener under Gymnastikk og turn | medium | Generic name for hovedidrett Gymnastikk og turn; mapped to all grener under it |
| Gymnastikk og Turn | 9 grener under Gymnastikk og turn | medium | Generic name for hovedidrett Gymnastikk og turn; mapped to all grener under it |
| Hestesport | 9 grener under Ridning | medium | Generic name for hovedidrett Ridning; mapped to all grener under it |
| Innefotball | Futsal (262) | medium |  |
| Kampsport | 9 grener under Kampsport | medium | Generic name for hovedidrett Kampsport; mapped to all grener under it |
| Klatrevegg | Klatring (591) | medium | Facility name |
| Luftsport | 7 grener under Luftsport | medium | Generic name for hovedidrett Luftsport; mapped to all grener under it |
| Motorsport | 13 grener under Motorsport | medium | Generic name for hovedidrett Motorsport; mapped to all grener under it |
| Paintball | Paintball (152) | medium | Also exists under Studentidrett (984) |
| Riding | 9 grener under Ridning | medium | Generic name for hovedidrett Ridning; mapped to all grener under it |
| Roing | Flattvannsroing (391); Turroing (393) | medium | Generic name for hovedidrett Roing; mapped to all grener under it |
| Seiling | 6 grener under Seiling | medium | Generic name for hovedidrett Seiling; mapped to all grener under it |
| Seilsport | 6 grener under Seiling | medium | Generic name for hovedidrett Seiling; mapped to all grener under it |
| Symjehall | Svømming (451) | medium | Facility name (nynorsk) |
| Yoga | Yoga (628) | medium | Only exists under Studentidrett in NIF |

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
| Funksjonhemma | ORG-MPL | Brukergruppe – tilrettelagt tilbud |
| Hundesport | FRT-IDR | Kan være hundekjøring (NIF) eller agility/lydighet (ikke NIF) |
| Kamera | IKR-TJE | Antatt kamerautstyr |
| Lokale aktiviteter-idrett-kultur | IKR-USP | Blandet kategori |
| Lyd | IKR-TJE | Antatt lydutstyr |
| Lys | IKR-TJE | Antatt lysutstyr |
| Makeup & Hundpleie | IKR-TJE | Uklar verdi |
| Markering | ARR-SER | Kan også være offentlig markering/demonstrasjon |
| Matlaging | MOP-OPP | Kan også være Sosial møteplass |
| Messe | ARR-OFF | Kan være varemesse eller gudstjeneste |
| Musikk og dans | KUL-MUS | Blandet kategori – dans hører til NIF Dans |
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
3. **Filtrer «Ikke relevant».** Verdier der `categories` inneholder `parent = "Ikke relevant"` (kode `IKR-*`), holdes utenfor aktivitetssøk.
5. **Koblingstabellen er mange-til-mange.** Ett aktivitetsnavn kan gi flere rader (én per innslag i `nif_sports`/`categories`). Ved søk på en gren eller på hovedidretten returneres alle navn som har et innslag som treffer.
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
