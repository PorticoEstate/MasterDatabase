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
│ ressurs, kildekode(_mapping), aktivitet/fasilitet/lokaletype,         │
│ gate/matrikkelinfo, synk_avvik/kildeuttrekk. Idempotent — trygt å     │
│ kjøre på nytt.                                                        │
└───────────────────────────────────────────────────┬───────────────────┘
                                                      ▼
┌───────────────────────────────────────────────────────────────────────┐
│ STEG 2 — INNLASTING                                                   │
│ etl/last_inn.py          ←  Aktiv kommune API (12 kommuner)           │
│                                                                        │
│ Henter kommune, bygg, adresser (uten koordinater), ressurser,         │
│ kildekoder. Oversetter kildekoder til vårt eget kodeverk ved hjelp    │
│ av de statiske fasitfilene:                                           │
│   etl/lokaletype_mapping/mapping.json                                │
│   etl/fasilitet_mapping/mapping.json                                  │
│   etl/activity_mapping/mapping.json + activities.json (egen tabell   │
│   aktivitet_mapping, siden én kildekode kan gi flere aktiviteter)     │
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
| `etl/lokaletype_mapping/`, `fasilitet_mapping/`, `activity_mapping/` | Fasitfiler `last_inn.py` leser for kodeverk-oversettelse |
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
ressurser, kildekoder, og en automatisk kartlegging av de vanligste kildekodene
til vårt eget kodeverk (`lokaletype`/`aktivitet`/`fasilitet`). Aktivitetsvokabularet
og -mappingen leses fra `activity_mapping/` og skrives til tabellen `aktivitet_mapping`.
ETL-mappinger fornyes ved hver kjøring,
men en manuell mapping (`kartlagt_av` ulik `etl`) overskrives aldri.
Se "Endre en mapping" under.

Laster **ikke**: koordinater og matrikkeldata (eget steg, se
"Geokoding og bygningsberikelse" under), og **ikke** `organizations`-samlingen
fra kilden, som inneholder personopplysninger om søkere - se prosjektets
minne om dette.

Kjøres skriptet på nytt for en kommune som allerede er lastet inn, oppdateres
radene i stedet for å dupliseres (`ON CONFLICT ... DO UPDATE`). En adresse som
er geokodet eller satt manuelt, og en kapasitet som er satt manuelt, overskrives
ikke. Se db/schema_kjerne_dokumentasjon.md for detaljene.

## Endre en mapping

`mapping.json`-filene i `lokaletype_mapping/`, `fasilitet_mapping/` og
`activity_mapping/` er fasiten for alle mappinger med `kartlagt_av = 'etl'`.
Databasen følger fasiten, og trenger ikke bygges på nytt:

1. Rediger `mapping.json` (nytt navn, endret mål, eller fjernet navn) og
   commit endringen.
2. Kjør `last_inn.py` på nytt (`alle`, eller én kommune), se "Hvordan kjøre
   det". Det finnes ingen automatisk kjøring - ingenting skjer før noen
   kjører skriptet.

Ved hver kjøring, for hver kildekode:

- Den gamle `etl`-mappingen slettes og settes inn på nytt fra gjeldende
  `mapping.json`. Gjelder lokaletype, fasilitet og aktivitet.
- **Fjernes et navn fra `mapping.json`, slettes mappingen**, og kildekoden
  dukker opp i `v_ukartlagte_kildekoder` til den kartlegges på nytt.
- En manuell mapping (`kartlagt_av` ulik `etl`) berøres aldri. Vil du
  overstyre fasiten for én kode, sett en manuell mapping.
- `ressurs.lokaletype_id`, `ressurs_aktivitet` og `ressurs_fasilitet`
  beregnes på nytt fra kilden og den gjeldende mappingen, så ressursene følger
  med. Er kildekoden ikke lenger kartlagt, blir `lokaletype_id` `NULL`.

Nye navn fra en kommune (en ny aktivitet, eller et omdøpt navn) lastes
uendret inn i `kildekode` og vises i `v_ukartlagte_kildekoder`. Legg dem til i
`mapping.json` og kjør på nytt, eller sett en manuell mapping.

**Begrensning:** mappingen kan foreløpig bare brukes på nytt ved å hente
kilden på nytt, fordi databasen ikke lagrer hvilke kildekoder hver ressurs
har.

## Avvik og kildeuttrekk

Hver kjøring registrerer et `kildeuttrekk` (kilde, endepunkt, tidspunkt,
HTTP-status - ikke hele svaret fra kilden). Alt som ikke lar seg laste
loggføres i `synk_avvik` sammen med selve posten som feilet (`rapost`, renset
for personopplysninger som `organizations` og andre persondatafelt): ugyldige
verdier, koblinger til noe som ikke finnes i uttrekket, databasefeil og feilet
henting. En enkelt dårlig post stopper aldri hele lasten.

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
