# Aktivitetsmapping – dokumentasjon

**Versjon:** 1.0 · **Dato:** 01.10.2026 · **Status:** Utkast – til faglig gjennomgang

## Sammendrag

Masterdatabasen samler bookingdata fra flere kommuners instanser av Aktiv kommune. Kommunene har hver sin frie liste over aktiviteter, med varierende stavemåter, bokmål/nynorsk og verdier som ikke er aktiviteter (lokaler, statuser, intern bruk). For å gjøre dataene søkbare og sammenlignbare er alle **332 unike aktivitetsverdier** klassifisert i to filer:

| Fil | Innhold | Antall |
|---|---|---|
| `aktivitet_nif_mapping.json` | Idrettsaktiviteter mappet til NIFs idrettsstruktur | 90 |
| `aktivitet_ikke_nif_struktur.json` | Øvrige aktiviteter mappet til en egen kategoristruktur | 242 |

Hver kildeverdi finnes i nøyaktig én av filene. Begge filene har samme JSON-struktur, slik at de kan leses med samme kode. 36 mappinger har middels eller lav sikkerhet og bør bekreftes av fagpersoner før produksjonsbruk.

---

## 1. Kildegrunnlag

| Kilde | Beskrivelse |
|---|---|
| `unike aktiviteter .csv` | 332 unike verdier av feltet `navn` fra aktivitetstabellen på tvers av alle Aktiv kommune-instanser. UTF-8. |
| `aktiviteter_nif.csv` | NIFs idrettsstruktur (238 grener under 57 hovedidretter), filtrert på `IsValidForReporting = Sann`. Kolonner: `SportCode`, `SportName`, `IsValidForReporting`, `ParentSportName`. **Merk:** filen er Latin-1-kodet og må leses med riktig tegnsett for å få korrekte æ/ø/å. |

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

- **Nøkkel** i `mapping` er kildeverdien nøyaktig slik den står i Aktiv kommune (uendret, inkludert skrivefeil).
- **`confidence`** angir hvor sikker mappingen er (se kapittel 5).
- **`note`** finnes bare der det er behov for forklaring.
- **`unmapped`** inneholder verdier som ikke er mappet i filen.

---

## 3. NIF-mapping (`aktivitet_nif_mapping.json`)

### 3.1 Felter

| Felt | Type | Beskrivelse |
|---|---|---|
| `nif_parent` | string | Hovedidrett i NIF (`ParentSportName`), f.eks. `Dans`, `Ski`, `Kampsport`. Alltid utfylt. |
| `nif_sport` | string \| null | Konkret gren (`SportName`), f.eks. `Sportsdrill`. `null` når kildeverdien er for generell til å peke på én gren (f.eks. «Ski» kan være både langrenn og alpint). |
| `sport_code` | integer \| null | NIFs `SportCode` for grenen. `null` når `nif_sport` er `null`. |
| `confidence` | string | `high`, `medium` eller `low`. |
| `note` | string | Valgfri forklaring (på engelsk i denne versjonen). |

### 3.2 Eksempel

```json
"Sandhåndball": {
  "nif_parent": "Håndball",
  "nif_sport": "Beach håndball",
  "sport_code": 332,
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

- 90 kildeverdier er mappet, hvorav 53 helt ned til konkret gren med `sport_code`.
- 48 av NIFs 57 hovedidretter og 48 av 238 grener er i bruk.
- Mappingen går én vei: fra kildeverdi til NIF. NIF-grener som ingen kommune bruker i dag, er ikke med.
- `unmapped` i denne filen inneholder de 242 verdiene som ikke passer i NIF. Alle er klassifisert i `aktivitet_ikke_nif_struktur.json`.

### 3.4 Kjente forhold i NIF-strukturen

- **Grener med flere hovedidretter:** Enkelte grener finnes under flere hovedidretter (f.eks. Paintball under både *Bedrift* og *Studentidrett*, Futsal under *Fotball*, *Bedrift* og *Studentidrett*). Valgt hovedidrett er beskrevet i `note`.
- **Grener som bare finnes under Studentidrett:** Noen aktiviteter (Yoga, Friluftsliv) finnes bare under *Studentidrett* og er derfor mappet dit med redusert sikkerhet.
- **Duplisert kode:** `SportCode` 992 brukes både for *Offshore* (Motorsport) og *Testgrenen* (Testaktivitet). Ingen kildeverdier er mappet til kode 992.

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
"Kor": {
  "parent": "Kultur",
  "category": "Musikk, kor og korps",
  "category_code": "KUL-MUS",
  "confidence": "high"
}
```

### 4.3 Kategoristruktur

| Kode | Hovedkategori | Underkategori | Antall |
|---|---|---|---|
| KUL-MUS | Kultur | Musikk, kor og korps | 8 |
| KUL-SCENE | Kultur | Scenekunst og film | 6 |
| KUL-KUNST | Kultur | Kunst, håndverk og foto | 10 |
| KUL-ARV | Kultur | Kulturarv og litteratur | 6 |
| KUL-GEN | Kultur | Kultur generelt | 3 |
| MOP-MOTE | Møter og opplæring | Møter og foredrag | 17 |
| MOP-OPP | Møter og opplæring | Undervisning og kurs | 22 |
| ORG-BU | Organisasjoner og møteplasser | Barn og unge | 8 |
| ORG-LAG | Organisasjoner og møteplasser | Lag og foreninger | 23 |
| ORG-MPL | Organisasjoner og møteplasser | Sosiale møteplasser og inkludering | 13 |
| ARR-PRIV | Arrangementer og selskap | Private selskap og bursdager | 9 |
| ARR-SER | Arrangementer og selskap | Seremonier og markeringer | 8 |
| ARR-OFF | Arrangementer og selskap | Offentlige arrangementer | 15 |
| FRT-FRI | Friluftsliv og trening | Friluftsliv | 12 |
| FRT-IDR | Friluftsliv og trening | Idrett og trening uten NIF-gren | 12 |
| IKR-LOK | Ikke relevant | Lokale eller fasilitet | 27 |
| IKR-STA | Ikke relevant | Bookingstatus eller systemtekst | 10 |
| IKR-BRUK | Ikke relevant | Intern eller kommersiell bruk | 16 |
| IKR-TJE | Ikke relevant | Tjenester og utlån | 8 |
| IKR-USP | Ikke relevant | Uspesifisert eller ukjent | 9 |
| | | **Totalt** | **242** |

### 4.4 Kategorien «Ikke relevant»

Kildefeltet i Aktiv kommune brukes også til informasjon som ikke er aktiviteter. Dette samles under *Ikke relevant* (70 verdier), med underkategori som angir årsaken:

- **Lokale eller fasilitet:** navn på rom eller anlegg (Gymsal, Møterom, Kulturhus).
- **Bookingstatus eller systemtekst:** Stengt, Slettet/utgått, Vedlikehold, systemmeldinger.
- **Intern eller kommersiell bruk:** Internt Bergen kommune, Kommersiell utleie.
- **Tjenester og utlån:** Innbyggerbussen, Leie av lastesykkel, Transporthjelp.
- **Uspesifisert eller ukjent:** Annet, Andre, X Annet, og verdier med ukjent betydning.

Disse verdiene bør filtreres bort fra aktivitetssøk. Underkategoriene gjør det mulig å bruke dem som egne felter (lokaletype, status, brukstype) i masterdatabasen.

### 4.5 Avgrensning mot NIF

*Idrett og trening uten NIF-gren* (FRT-IDR) brukes for idrettsrelaterte verdier som er for generelle til å plasseres i NIF (Idrett, Ballsport, Trim, Styrketrening) eller som ikke er NIF-idretter (E-sport, Bowls).

---

## 5. Sikkerhetsnivå (`confidence`)

| Nivå | Betydning |
|---|---|
| `high` | Entydig treff, også ved skrivefeil eller nynorsk/bokmål-variant (f.eks. «Klartring» → Klatring, «Symjehall» → Svømming). |
| `medium` | Rimelig tolkning, men verdien er f.eks. et anleggsnavn eller kan passe flere steder. Kun i NIF-filen. |
| `low` | Usikker tolkning. Bør bekreftes av fagperson eller kommunen. |

### 5.1 Mappinger som bør bekreftes – NIF

| Kildeverdi | Mappet til | Sikkerhet | Merknad |
|---|---|---|---|
| Bandy - inne | Bandy | medium | Kan være Innebandy eller Rinkbandy |
| Dans/trening | Dans | medium | Kombinert dans/trening |
| Drill | Dans → Sportsdrill (518) | medium | Finnes også under Studentidrett (981) |
| Fleiridrettslag / Fleridrettslag | Fleridretter | medium | Fleridrettslag er ikke nødvendigvis NIFs «Fleridretter» |
| Fotballbane | Fotball | medium | Anleggsnavn |
| Innefotball | Fotball → Futsal (262) | medium | |
| Paintball | Bedrift → Paintball (152) | medium | Finnes også under Studentidrett (984) |
| Svømmehall / Symjehall | Svømming | medium | Anleggsnavn |
| Yoga | Studentidrett → Yoga (628) | medium | Finnes kun under Studentidrett |
| Bil/MC klubb | Motorsport | low | Klubben kan være uten idrettsaktivitet |
| Friluftsliv | Studentidrett → Friluftsliv (622) | low | Finnes kun under Studentidrett |
| Funksjonhemma | Idrett for funksjonshemmede | low | Brukergruppe, ikke nødvendigvis idrett |
| Hundesport | Hundekjøring | low | Kan være agility o.l. (ikke NIF) |
| Musikk og dans | Dans | low | Blandet kategori |
| Skating | Brett → Skateboard (732) | low | Kan også bety skøyter/rulleskøyter |

I tillegg er **Taekwondo** mappet til Kampsport uten gren, fordi det er ukjent om det gjelder ITF (524) eller WT (522).

### 5.2 Mappinger som bør bekreftes – øvrige

| Kildeverdi | Mappet til | Merknad |
|---|---|---|
| Andre aktivitetar, konsertar, o.l | KUL-MUS | Blandet kategori |
| Bowls | FRT-IDR | Kan være skrivefeil for Bowling (NIF) |
| Buekorps | ORG-BU | Bergensk tradisjon, ikke bueskyting |
| Båtforeingar | ORG-LAG | Kan være seiling/padling (NIF) |
| Disko | ARR-PRIV | Kan også være ungdomsarrangement |
| Drop-in / arbeidsplasser | IKR-LOK | Kan også være sosial møteplass |
| Flykningekontoret | IKR-BRUK | Kan også være Inkludering |
| Foreldreutval | ORG-LAG | Kan også høre til Opplæring |
| Hund | FRT-FRI | Kan være hundekjøring (NIF) eller hundetrening |
| Lokale aktiviteter-idrett-kultur | IKR-USP | Blandet kategori |
| Makeup & Hundpleie | IKR-TJE | Uklar verdi |
| Matlaging | MOP-OPP | Kan også være sosial møteplass |
| Mini | IKR-USP | Ukjent – muligens minihåndball/minifotball |
| NRG | IKR-USP | Ukjent forkortelse |
| PU/HU | ORG-MPL | Antatt tilrettelagt tilbud – bekreft betydning |
| Sirkus | KUL-SCENE | Kan også være sirkustrening/akrobatikk |
| Spill | ORG-MPL | Kan være brettspill/rollespill eller e-sport |
| Treklang | IKR-USP | Ukjent – muligens navn på kor/ensemble |
| Walk and talk - test | FRT-FRI | Testverdi |

---

## 6. Bruk i masterdatabasen

1. **Ta vare på originalverdien.** Kildeverdien (og instans/kommune) lagres uendret. Mappingen legges i en egen koblingstabell, slik at kategorier kan endres uten å røre historiske data.
2. **Slå opp begge filene.** En kildeverdi slås først opp i NIF-filen, deretter i filen for øvrige aktiviteter. Treff i begge skal ikke forekomme.
3. **Filtrer «Ikke relevant».** Verdier med `parent = "Ikke relevant"` eller `category_code` som starter på `IKR-` holdes utenfor aktivitetssøk.
4. **Bruk koder som nøkler.** Bruk `sport_code` og `category_code` som stabile nøkler. Navn kan endres.

---

## 7. Vedlikehold

- **Nye verdier:** Når nye kommuner kobles på eller eksisterende kommuner legger til aktiviteter, matches nye verdier mot eksisterende nøkler. Verdier uten treff legges i `unmapped` og vurderes manuelt.
- **Matching:** Sammenligningen bør skje på normalisert verdi (små bokstaver, uten ekstra mellomrom). Nøklene i filene er derimot alltid den originale verdien.
- **Endringer i NIF:** NIF-strukturen kan endres. Kontroller jevnlig at `sport_code` fortsatt finnes og er gyldig for rapportering.
- **Nye kategorier:** Nye kategorikoder legges til; eksisterende koder endres eller gjenbrukes ikke.

---

## 8. Begrensninger

- Mappingen er laget ut fra aktivitetsnavnet alene, uten innsyn i bookingene bak. Verdier som er tvetydige ut fra navnet, er merket med lav sikkerhet.
- Noen kildeverdier beskriver egentlig brukergruppe eller organisasjonstype (f.eks. Speider, Barnehage) og ikke en aktivitet. De er likevel plassert i aktivitetsstrukturen fordi det er slik de brukes i dag.
- `note`-feltet er på engelsk i NIF-filen og på norsk i filen for øvrige aktiviteter.

---

*Mappingene og dokumentasjonen er laget med KI-støtte og må kvalitetssikres før de deles eksternt eller tas i bruk i produksjon.*
