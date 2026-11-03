# Innlasting fra Aktiv kommune

`last_inn.py` henter data fra Aktiv kommune og skriver SQL som fyller
masterdatabasen. Se `db/schema_kjerne_dokumentasjon.md` for hva tabellene betyr.

## Oversikt over hele pipelinen

Fra tomt skjema til populert database, i tre steg:

```
┌───────────────────────────────────────────────────────────────────────┐
│ STEG 1 — SKJEMA                                                       │
│ db/schema_kjerne.sql                                                  │
│                                                                        │
│ Oppretter alle tabeller i en tom database: kommune, bygning, adresse, │
│ ressurs, kildekode, aktivitet/fasilitet/lokaletype,                   │
│ gate/matrikkelinfo, synk_avvik/kildeuttrekk. Idempotent — trygt å     │
│ kjøre på nytt.                                                        │
└───────────────────────────────────────────────────┬───────────────────┘
                                                      ▼
┌───────────────────────────────────────────────────────────────────────┐
│ STEG 2 — INNLASTING                                                   │
│ etl/last_inn.py          ←  Aktiv kommune API (12 kommuner)           │
│                                                                        │
│ Henter kommune, bygg, adresser (uten koordinater), ressurser,         │
│ kildekoder og kodeverkene (lokaletype, aktivitet, fasilitet) slik     │
│ instansen leverer dem: id, name, parent_id. Koblingene ressurs →      │
│ kodeverk lastes direkte, på navn. Se "Kildekontrakt" under.           │
│ Laster ALDRI `organizations` (persondata).                             │
└───────────────────────────────────────────────────┬───────────────────┘
                                                      ▼
┌───────────────────────────────────────────────────────────────────────┐
│ STEG 3 — GEOKODING + BYGNINGSBERIKELSE                                │
│ etl/matrikkel_adresse.py  ←  MatrikkelAPI (SOAP, krever innlogging)   │
│                                                                        │
│ a) Løser adressene — søker *innenfor riktig kommune* (kjent fra      │
│    steg 2) i Matrikkelen. Eneste geokodingskilde; se begrunnelsen i   │
│    seksjonen under for hvorfor Kartverkets åpne Adresse-API ikke      │
│    lenger brukes som et eget forsteg.                                 │
│ b) Henter bygningsnr/bygningstype/bra_m2/antall_etasjer for ALLE      │
│    bygg som mangler det (Aktiv kommune har ikke dette feltet i det    │
│    hele tatt — dette er eneste kilde).                                │
│ Prinsipp: ett eksakt treff, ellers avvik.                             │
└───────────────────────────────────────────────────┬───────────────────┘
                                                      ▼
                                          ╔═══════════════════╗
                                          ║   FERDIG: masterdb ║
                                          ╚═══════════════════╝
```

**Demo-normalisering (valgfritt, før steg 2).** Aktiv kommune-instansene er ennå
ikke normalisert. `etl/demo_normalisering/normaliser.py` viser hvordan masterdatabasen kan
bli når de er det: det gjør en rå `searchdataall` om til det en normalisert
instans ville levere, og `last_inn.py` laster resultatet med `--fra-fil`. Hele
mappen kan slettes når instansene er normalisert; `last_inn.py` trenger ingen
endring. Se "Demo-normalisering" under.

**Tverrgående, på hvert steg:** alt som feiler (ugyldig verdi, duplikat,
API-feil, manglende treff) logges i `synk_avvik` sammen med selve posten som
feilet — én dårlig rad stopper aldri hele kjøringen. Hver kjøring registreres
i `kildeuttrekk` (metadata, ikke selve svaret). Se "Avvik og kildeuttrekk"
under.

Alle tre stegene er trygge å kjøre på nytt — de endrer kun det som fortsatt
mangler/er ukjent, aldri manuelt satte verdier. De eksakte kommandoene for
hvert steg står i seksjonene under, i samme rekkefølge.

**Filoversikt:**

| Fil | Rolle |
|---|---|
| `db/schema_kjerne.sql` | Skjemaet (steg 1) |
| `db/schema_kjerne_dokumentasjon.md` | Hva hver tabell/kolonne betyr og hvorfor |
| `etl/last_inn.py` | Steg 2 |
| `etl/demo_normalisering/normaliser.py` | DEMO: lager normalisert JSON fra rå `searchdataall`. Slettes ved normalisering |
| `etl/demo_normalisering/{lokaletype,fasilitet,activity}_mapping/` | DEMO: vokabular (`venue_types.json`, `facilities.json`, `activities.json`) og mapping (`mapping.json`) som `normaliser.py` leser |
| `etl/matrikkel_adresse.py` | Steg 3 |
| `matrikkel/test_auth.py` | Verifiserer at Matrikkel-innlogging virker, før man kjører steg 3 |

**Ikke bygget ennå:** `ressurslenke` (koble samme fysiske bygg/ressurs til
flere fagsystemer samtidig, f.eks. booking + FDV) — bevisst utsatt til det
faktisk finnes et andre fagsystem å koble til, se `db/ressurslenke.md`.

## Forutsetning: HTTPS må virke fra WSL

Skriptet henter data over internett. På en Capgemini-maskin krever det at
Capgeminis rotsertifikat er installert i WSL (se prosjektets minne
`wsl-ca-sertifikat-lost` eller spør Claude). Test at det virker:

```bash
curl -sS -o /dev/null -w "%{http_code}\n" https://bergen.aktiv-kommune.no/bookingfrontend/searchdataall
```

Skal svare `200`. Svarer den med en sertifikatfeil, må sertifikatet installeres først.

## Hvordan kjøre det

Skriptet bruker bare Pythons innebygde bibliotek - ingen `pip install` er
nødvendig. Det gjør ingenting mot databasen selv; det skriver SQL-tekst til
standard-ut, som du deretter sender til Postgres i et eget steg. Det gir deg
mulighet til å se hva som skal skje før noe endres.

**Én kommune, for å teste:**

```bash
python3 etl/last_inn.py bergen > etl/ut/bergen.sql
docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/bergen.sql
```

**Alle 12 kommunene:**

```bash
python3 etl/last_inn.py alle > etl/ut/alle.sql
docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/alle.sql
```

Skriptet kan også lese `<mappe>/<kommune>.json` i stedet for å hente fra nettet,
med `--fra-fil <mappe>`. Det brukes av demoen (under), og er nyttig for å kjøre
samme data på nytt uten nettverk. Kildeuttrekket registreres da med
`file:///...` som endepunkt og uten HTTP-status.

`etl/ut/` er generert output og ligger i `.gitignore` - filene der er en
ferskvare, ikke noe som skal committes.

## Databasen må finnes og ha skjemaet fra før

```bash
docker exec portico_masterdb psql -U postgres -c "CREATE DATABASE masterdb;"
docker exec -i portico_masterdb psql -U postgres -d masterdb < db/schema_kjerne.sql
```

Skjemaet er idempotent - du kan kjøre den kommandoen på nytt uten å ødelegge noe.

## Hva skriptet gjør og ikke gjør

Laster: kommune, bygg, adresser (som de står i kilden, uten koordinater),
ressurser, og kodeverkene `lokaletype`, `aktivitet` og `fasilitet` fra kildens
`resource_categories`, `activities` og `facilities`. Et konsept nøkles på navn
(unikt per tabell), og forelderen settes fra `parent_id` i kilden. Ressursene
kobles direkte til kodeverkene (`ressurs.lokaletype_id`, `ressurs_aktivitet`,
`ressurs_fasilitet`). Kildens egne id-er lagres i `kildekode` og
`ressurs_kildekode`.

Skriptet gjør ingen oversettelse. Det er instansene som skal levere et
normalisert kodeverk (se "Kildekontrakt"). Brudd på kontrakten loggføres i
`synk_avvik`. Kodeverkene er tomme i en ny database til skriptet er kjørt.

Koblingene (`ressurs_kildekode`, `ressurs_aktivitet`, `ressurs_fasilitet`)
bygges på nytt for instansen ved hver kjøring. Kodeverkene selv får aldri
konsepter fjernet; et konsept som forsvinner fra kilden, blir stående.

Laster **ikke**: koordinater og matrikkeldata (eget steg, se
"Geokoding og bygningsberikelse" under), og **ikke** `organizations`-samlingen
fra kilden, som inneholder personopplysninger om søkere - se prosjektets
minne om dette.

Kjøres skriptet på nytt for en kommune som allerede er lastet inn, oppdateres
radene i stedet for å dupliseres (`ON CONFLICT ... DO UPDATE`). En adresse som
er geokodet eller satt manuelt, og en kapasitet som er satt manuelt, overskrives
ikke. Se db/schema_kjerne_dokumentasjon.md for detaljene.

## Avvik og kildeuttrekk

Hver kjøring registrerer et `kildeuttrekk` (kilde, endepunkt, tidspunkt,
HTTP-status - ikke hele svaret fra kilden). Alt som ikke lar seg laste
loggføres i `synk_avvik` sammen med selve posten som feilet (`rapost`, renset
for personopplysninger som `organizations` og andre persondatafelt): ugyldige
verdier, koblinger til noe som ikke finnes i uttrekket, brudd på kildekontrakten,
databasefeil og feilet henting. En enkelt dårlig post stopper aldri hele lasten.

Gå gjennom avvikene fra siste kjøring slik:

```bash
docker exec portico_masterdb psql -U postgres -d masterdb -c "
    SELECT d.avvik_id, d.kilde, d.avvikstype, d.felt, d.detalj, d.post
    FROM v_synk_avvik_gjeldende g JOIN v_synk_avvik_detalj d ON d.avvik_id = g.id
    WHERE g.avvikstype <> 'manglende_forelder';"
```

`post` er selve posten fra kilden som feilet, lagret direkte på avviket. De to
nyeste uttrekkene per kilde beholdes, uforbeholdent - bevis for et avvik ligger
på avviket selv, ikke i uttrekket, så gammel metadata kan ryddes trygt bort.

## Kildekontrakt: hva en normalisert instans må levere

`last_inn.py` laster kodeverkene direkte fra `searchdataall`, uten mapping. Det
forutsetter at hver instans leverer dem i masterens form:

| Samling | Felt | Krav |
|---|---|---|
| `resource_categories` (lokaletype), `activities`, `facilities` | `id` | Unik i samlingen |
| | `name` | Unikt i samlingen, og lik på tvers av instanser (navnet er nøkkelen i masteren) |
| | `parent_id` | `id` i samme samling, eller `null` for en rot. Én forelder, ingen sykluser. `facilities` har ikke dette feltet i dag |
| `resources` | `rescategory_id` | `id` i `resource_categories` |
| `resource_activities`, `resource_facilities` | `resource_id`, `activity_id`/`facility_id` | Peker på en rad i `resources` og i samlingen |

Brudd lastes ikke stille; de loggføres i `synk_avvik`:

| Brudd | Avvikstype | Følge |
|---|---|---|
| Manglende `id`, tomt `name`, navn som går igjen, syklus | `ugyldig_verdi` | Posten faller bort (syklus: noden blir rot) |
| `parent_id` som ikke finnes i samlingen | `manglende_forelder` | Noden blir rot |
| Kobling til en ressurs eller et konsept som ikke finnes | `manglende_forelder` | Raden lastes ikke |

**Åpent: fullstendighet.** Kontrakten krever ikke at hele treet er med, men i
dag er det ikke det. Målt på Bergen (2026-11-02) mangler 8 av 102 aktiviteter og
4 av 56 lokaletyper sin forelder i samlingen, fem aktivitets-id-er brukes av
koblinger uten å finnes, og 389 ressurser og 28 bygg er referert uten å være med
i uttrekket. Årsaken er ikke avklart (filtrering i `searchdataall`, eller et
annet endepunkt som gir alt).

**Åpent: eierskap.** Kunden kan på sikt ønske at masterdatabasen eier vokabular
og hierarki, og at instansene sjekkes mot det. Da byttes lasting av vokabularet/hirarkiet til aktivitet/fasilitet/lokaletype fra kilden ut med en sjekk av at navnet finnes i masteren.

## Demo-normalisering

Mappingen er midlertidig. Den viser hvordan masterdatabasen blir når instansene
er normalisert, og brukes ikke i produksjon. Alt den trenger ligger i
`etl/demo_normalisering/`, og mappen slettes når normaliseringen er på plass.

`normaliser.py` leser `searchdataall` (nettet, eller `--fra-fil`), og skriver
`<kommune>.json` med samme form, men med kodeverkene erstattet av vokabularet
fra filene (`id`, `name`, `parent_id`) og koblingene omskrevet. Kildenavn uten
mapping, eller som mappes til et exclude-konsept, får ingen kobling og skrives
til standard-feil.

```bash
python3 etl/demo_normalisering/normaliser.py alle              # skriver etl/ut/normalisert/
python3 etl/last_inn.py alle --fra-fil etl/ut/normalisert > etl/ut/alle.sql
docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/alle.sql
```

Konseptene i vokabularfilene nøkles på navn, med `broader` som forelderens
navn. En endring i `mapping.json` eller vokabularfilene slår igjennom ved neste
kjøring av `normaliser.py`. Fasettene (`facets`) er bare en gruppering i
filene og havner ikke i databasen.

Demoen skjuler brudd på kontrakten: den bygger vokabularet fra filene, så
manglende foreldre og ukjente kodeverks-id-er i kilden gir ingen avvik. Et rent
`synk_avvik` for kodeverkene etter en demokjøring sier derfor ingenting om
kildens kvalitet.

## Geokoding og bygningsberikelse (MatrikkelAPI)

`matrikkel_adresse.py` er eneste geokodingssteg i pipelinen, og gjør to ting:

1. **Geokoding** av enhver hovedadresse som ennå ikke er løst. MatrikkelAPI
   (SOAP, krever `MATRIKKEL_BRUKER`/`MATRIKKEL_PASSORD` - se
   `matrikkel/test_auth.py`) lar oss søke *innenfor riktig kommune*, som vi
   allerede kjenner fra innlastingen.
2. **Bygningsnummer og bygningsfakta** for enhver bygning som mangler det,
   uansett om adressen ble løst i denne kjøringen eller en tidligere. Aktiv
   kommune oppgir ikke bygningsnummer i det hele tatt - dette er den eneste
   kilden til det.

Se modulens docstring for hele kjeden av SOAP-kall.

**Hvorfor ikke Kartverkets åpne Adresse-API i tillegg?** Det ble det tidligere
(`etl/geokod.py`, fjernet), som et raskere, uautentisert forsteg - Matrikkelen
ble bare brukt som fallback for det det åpne API-et bommet på. Prosjektet har
bevisst gått bort fra det: siden denne pipelinen bare kjøres ved populering og
innimellom, er den ekstra tiden MatrikkelAPI-kjeden tar ikke noe problem, og
ett system med én kilde er enklere å forstå og vedlikeholde enn to. Kostnaden er
målt: en nasjonal test av alle 12 kommunene viste 69,7 % automatisk treffrate
med Matrikkelen alene, mot 73,1 % med det todelte oppsettet - et bevisst valg
om noen få prosentpoengs lavere automatikk, ikke et ukjent tap. De adressene
det gjelder havner i `synk_avvik` og rettes manuelt, akkurat som før.

Fyller `matrikkelinfo` (gnr/bnr/fnr/snr, knyttet til adressens bygg via
`bygning_id`) uansett geokodingsstatus - billig og idempotent (`ON CONFLICT
DO NOTHING`), så det forsøkes for enhver adresse vi klarer å slå opp i
Matrikkelen, ikke bare de som fortsatt mangler geokoding. Fyller ved adressetreff som *fortsatt* mangler
geokoding: i tillegg `gate` (adressekode+gatenavn), `adresse.posisjon/husnr/
bokstav` og `geokoding='matrikkel'` - den autoritative statusen, se
`db/schema_kjerne_dokumentasjon.md`. Fyller ved bygningstreff (alltid forsøkt,
også for adresser som var løst fra før): `bygning.bygningsnr`, `bygningstype`
(Matrikkelens rå kodeverdi, ikke oversatt til navn ennå), `bra_m2`,
`antall_etasjer` og `matrikkel_match='adresse'`. Mislykkes bygningsoppslaget
(ingen/flere bygg funnet, API-feil, eller bygg uten bygningsnummer), settes
`matrikkel_match='ikke_funnet'` i stedet - uten dette ville et forsøkt-men-
mislykket oppslag sett identisk ut som et som aldri ble forsøkt. Overskriver
aldri en `'adresse'`-match adressesteget nettopp satte for samme bygg.

```bash
docker exec portico_masterdb psql -U postgres -d masterdb -tA -F'|' -c "
    SELECT a.id, a.adressetekst, a.postnummer, a.poststed, k.kommunenr,
           a.bygning_id, a.geokoding, a.gate_id, a.husnr, a.bokstav, g.adressekode
    FROM adresse a
    JOIN bygning b ON b.id = a.bygning_id
    JOIN kommune k ON k.id = b.kommune_id
    LEFT JOIN gate g ON g.id = a.gate_id
    WHERE a.er_hovedadresse AND a.geokoding <> 'manuell' AND a.adressetekst IS NOT NULL
      AND (a.geokoding IN ('ukjent','feilet') OR b.bygningsnr IS NULL
           OR NOT EXISTS (SELECT 1 FROM matrikkelinfo m WHERE m.bygning_id = b.id));
" > etl/ut/adresser_a_matrikkelsoke.txt

python3 etl/matrikkel_adresse.py < etl/ut/adresser_a_matrikkelsoke.txt > etl/ut/matrikkel.sql

docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/matrikkel.sql
```

Reelt resultat ved nasjonal testkjøring (alle 12 kommuner, 399 adresser):
278 geokodet (70 %), 121 feilet og loggført i `synk_avvik`. Feilårsakene er
enten ekte stave-/formatfeil Matrikkelen heller ikke kan matche (f.eks.
«Wolfsgate 12x» mot det offisielle «Wolffs gate»), eller mangler husnummer
helt i kildedata (f.eks. «Festplassen», «Nygårdsparken») - et
datakvalitetsproblem i kilden, ikke noe et adresseoppslag kan løse.

## Kjent forenkling

`kommune_id` settes i dag fra hvilken Aktiv kommune-instans dataene kommer
fra (`bergen` → kommunenr 4601). Det stemmer for alle 12 instansene som
finnes i dag. Skjemaet støtter at en instans betjener flere kommuner
(tabellen `kommune_fagsystem_instans`); den dagen det faktisk skjer for en av
instansene vi laster fra, må `kommune_id` i stedet utledes fra en geokodet
adresse, ikke fra instansen.
