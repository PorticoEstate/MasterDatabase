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


---

## 9. Matrikkel: Datauttak via Kartverket (Eiendomsdata)

Oppsummert fra Kartverket: «Elektronisk tilgang til eiendomsdata» (<https://kartverket.no/api-og-data/eiendomsdata>):

- Tilgang: Data er gratis, men regulert. Det kreves lovlig behandlingsgrunnlag og avtale med Kartverket før utlevering av data fra grunnbok og matrikkel.
- Tilgangsnivå: Ulike virksomhetskategorier får ulikt omfang av opplysninger. Databehandlere kan få tilgang når de videreformidler til behandlingsansvarlige med grunnlag.
- Forpliktelser: Krav til tekniske og organisatoriske tiltak, videreføringsplikt til kunder, og etterlevelse av personvernregelverk. Brudd kan medføre stenging av tilgang.
- Bruksbegrensninger: Ikke lov å bruke til reklame/markedsføring uten samtykke.
- Søknad: Tilgang søkes via nettskjema (<https://kartverket.no/api-og-data/eiendomsdata/soknad-api-tilgang>). Kartverket vurderer vilkår for utlevering.
- Katalog: Tjenester/datasett finnes i Geonorge kartkatalog og API-oversikt.

Plan for data-pull i dette prosjektet:

1. Juridisk og tilgang

- Avklare behandlingsgrunnlag og inngå avtale med Kartverket.
- Etablere Maskinporten-klient og evt. mTLS/IP-tilgang etter krav.

1. Tjenestevalg

- Adresse/lett oppslag: Adresse-API (offentlig) for adresser og koordinater.
- Autorative matrikkeldata: Matrikkel Web Services (SOAP) og/eller WFS/WMS (lisensiert).
- Masseoppdatering: Periodiske uttrekk via Geonorge/FTP der det er hensiktsmessig.

1. ETL og modelltilpasning

- Hente data til «staging», validere, normalisere og mappe til master-IDer.
- Feltvis prioritet: Sett Matrikkel som autorativ for identitet (gnr/bnr/fnr/snr, bygningsnummer, adresser).
- Proveniens: lagre kilde, sist oppdatert og autorativ-status per felt.

1. Drift

- Håndtere rate limits og feil via retry/backoff og idempotente oppdateringer.
- Loggføre og revidere tilgang i henhold til avtale og utleveringsforskrift.

