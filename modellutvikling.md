# Inputdokument for AI-modellutvikling: Integrasjon av masterdatabase med matrikkelinformasjon og anleggsdata

---

## 1. Målsetting
Etablere en masterdatabase som integrerer data fra flere lignende databaseinstanser (lokale databaser med bygnings- og anleggsdata) og supplerer med informasjon fra autoritative registre som matrikkelen og det nasjonale anleggsregisteret.

---

## 2. Datakilder
- **Matrikkel**: Autorativ for bygningsnummer, gatenummer, husnummer, eiendomsdata
- **Lokale driftsdatabaser**: Anleggsdetaljer, bookingstatus, driftsmeldinger, tekniske data
- **Nasjonalt anleggsregister**: Strukturert katalog over tekniske installasjoner
- **Fagsystemer for**:
  - Leie av lokaler
  - Skade- og vedlikeholdsmeldinger
  - Drift og ressursforvaltning

---

## 3. Masterdatabasefunksjoner
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
- Integrasjon med nasjonalt anleggsregister
- Eksterne forespørselssvar og oppdateringsprotokoller

---

## 5. Kontekstuell forespørselshåndtering
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

