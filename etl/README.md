# Innlasting fra Aktiv kommune

Skriptene i denne mappen henter data fra Aktiv kommune og Matrikkelen og
skriver SQL som fyller masterdatabasen. Se `db/schema_kjerne_dokumentasjon.md`
for hva tabellene betyr.

## Oversikt over hele pipelinen

Fra tom database til populert database, i fire steg:

```
┌───────────────────────────────────────────────────────────────────────┐
│ STEG 1 — SKJEMA                                                       │
│ Flyway i backenden (backend/src/main/resources/db/migration)          │
│                                                                       │
│ Kjøres når backenden starter. Oppretter og oppdaterer alle tabeller   │
│ og visninger. En ny migrasjonsfil krever --build, siden migrasjonene  │
│ ligger i JAR-en.                                                      │
└───────────────────────────────────────────────────┬───────────────────┘
                                                    ▼
┌───────────────────────────────────────────────────────────────────────┐
│ STEG 2 — INNLASTING                                                   │
│ etl/last_inn.py          ←  Aktiv kommune API (12 kommuner)           │
│                                                                       │
│ Henter kommune, bygg, adresser (uten koordinater), ressurser og       │
│ kildekoder. Lagrer bare hva kilden sa (kildekode, ressurs_kildekode), │
│ uten å tolke det.                                                     │
│ Laster ALDRI `organizations` (persondata).                            │
└───────────────────────────────────────────────────┬───────────────────┘
                                                    ▼
┌───────────────────────────────────────────────────────────────────────┐
│ STEG 3 — MAPPING                                                      │
│ etl/last_mapping.py      ←  fasitfilene i etl/*_mapping/              │
│                                                                       │
│ Oversetter kildekodene til vårt eget kodeverk:                        │
│   etl/activity_mapping/mapping.json + activities.json                 │
│   etl/lokaletype_mapping/mapping.json                                 │
│   etl/fasilitet_mapping/mapping.json                                  │
│ Henter ingenting fra kommunene, så den kan kjøres alene når en        │
│ fasitfil er endret.                                                   │
└───────────────────────────────────────────────────┬───────────────────┘
                                                    ▼
┌───────────────────────────────────────────────────────────────────────┐
│ STEG 4 — GEOKODING + BYGNINGSBERIKELSE                                │
│ etl/matrikkel_adresse.py  ←  MatrikkelAPI (SOAP, krever innlogging)   │
│                                                                       │
│ a) Løser adressene — søker *innenfor riktig kommune* (kjent fra       │
│    steg 2) i Matrikkelen. Eneste geokodingskilde; se begrunnelsen i   │
│    seksjonen under for hvorfor Kartverkets åpne Adresse-API ikke      │
│    lenger brukes som et eget forsteg.                                 │
│ b) Henter bygningsnr/bygningstype/bra_m2/antall_etasjer for ALLE      │
│    bygg som mangler det (Aktiv kommune har ikke dette feltet i det    │
│    hele tatt — dette er eneste kilde).                                │
│ Prinsipp: ett eksakt treff, ellers avvik.                             │
└───────────────────────────────────────────────────┬───────────────────┘
                                                    ▼
                                          ╔════════════════════╗
                                          ║   FERDIG: masterdb ║
                                          ╚════════════════════╝
```

**Tverrgående, på hvert steg:** alt som feiler (ugyldig verdi, duplikat,
API-feil, manglende treff) logges i `synk_avvik` sammen med selve posten som
feilet — én dårlig rad stopper aldri hele kjøringen. Hver kjøring registreres
i `kildeuttrekk` (metadata, ikke selve svaret). Se "Avvik og kildeuttrekk"
under.

Alle stegene er trygge å kjøre på nytt — de endrer kun det som fortsatt
mangler/er ukjent, aldri manuelt satte verdier. `etl/kjor_alt.sh` kjører
steg 2–4 i riktig rekkefølge; se "Hvordan kjøre det".

**Filoversikt:**

| Fil | Rolle |
|---|---|
| `backend/src/main/resources/db/migration/` | Skjemaet som Flyway-migrasjoner (steg 1) |
| `db/schema_kjerne_dokumentasjon.md` | Hva hver tabell/kolonne betyr og hvorfor |
| `etl/kjor_alt.sh` | Kjører steg 2–4 mot databasen i Docker |
| `etl/last_inn.py` | Steg 2 |
| `etl/last_mapping.py` | Steg 3 |
| `etl/lokaletype_mapping/`, `fasilitet_mapping/`, `activity_mapping/` | Fasitfilene `last_mapping.py` leser for kodeverk-oversettelse |
| `etl/matrikkel_adresse.py` | Steg 4 |
| `etl/.env.example` | Mal for `etl/.env` med Matrikkel-innloggingen |
| `matrikkel/test_auth.py` | Verifiserer at Matrikkel-innlogging virker, før man kjører steg 4 |

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

## Databasen og skjemaet

Databasen `masterdb` opprettes av Postgres-containeren, og skjemaet av
backenden (Flyway) når den starter:

```bash
docker compose up -d --build backend
```

`--build` trengs hver gang det har kommet en ny migrasjonsfil, siden
migrasjonene bygges inn i backendens JAR. `kjor_alt.sh` sjekker at databasen er
på samme Flyway-versjon som repoet, og stopper med en melding om den ikke er
det. `db/schema_kjerne.sql` er en lesbar, samlet kopi av skjemaet etter siste
migrasjon, til oversikt. Den skal ikke kjøres mot en database Flyway styrer.

## Hvordan kjøre det

```bash
etl/kjor_alt.sh last bergen         # én kommune: innlasting + mapping
etl/kjor_alt.sh last alle           # alle 12 kommunene: innlasting + mapping
etl/kjor_alt.sh mapping --dry-run   # vis hva en endret fasitfil ville endret
etl/kjor_alt.sh mapping             # kjør mappingen på nytt
etl/kjor_alt.sh matrikkel           # geokoding og bygningsberikelse
etl/kjor_alt.sh alle                # alt: innlasting + mapping + matrikkel
```

Matrikkel-steget trenger innlogging. Kopier `etl/.env.example` til `etl/.env`
og fyll inn; `kjor_alt.sh` leser filen selv. `etl/.env` ligger i `.gitignore`
og skal aldri committes.

Python-skriptene bruker bare Pythons innebygde bibliotek - ingen `pip install`
er nødvendig. De gjør ingenting mot databasen selv; de skriver SQL-tekst til
standard-ut. `kjor_alt.sh` lagrer SQL-en i `etl/ut/` (`<kommune>.sql`,
`mapping.sql`, `matrikkel.sql`) før den kjøres, så du kan se i ettertid hva som
ble gjort. `etl/ut/` er generert output og ligger i `.gitignore` - filene der er
en ferskvare, ikke noe som skal committes.

**Uten kjøreskriptet** (det er dette `kjor_alt.sh` gjør, steg for steg). `-q`
gjør psql stille; utelat den for å se hver setning:

```bash
# Steg 2
python3 etl/last_inn.py bergen > etl/ut/bergen.sql
docker exec -i portico_masterdb psql -q -U postgres -d masterdb < etl/ut/bergen.sql

# Steg 3: kildekodene hentes fra databasen og sendes rett inn i skriptet
docker exec portico_masterdb psql -q -tA -F$'\t' -U postgres -d masterdb -c "
    SELECT fi.kildenokkel, kk.kodetype, kk.kode, kk.navn
    FROM kildekode kk JOIN fagsystem_instans fi ON fi.id = kk.fagsystem_instans_id
    ORDER BY 1, 2, 3" \
    | python3 etl/last_mapping.py --dry-run > etl/ut/mapping.sql
docker exec -i portico_masterdb psql -q -U postgres -d masterdb < etl/ut/mapping.sql
```

Steg 4 står under "Geokoding og bygningsberikelse".

## Innlasting: hva last_inn.py gjør og ikke gjør

Laster: kommune, bygg, adresser (som de står i kilden, uten koordinater),
ressurser og kildekoder. For hver ressurs lagres hvilke kildekoder kilden
oppga (lokaletype, aktiviteter, fasiliteter) i `ressurs_kildekode`, uten
tolkning. Oversettelsen til vårt eget kodeverk er et eget steg, se "Mapping".

Laster **ikke**: koordinater og matrikkeldata (eget steg, se
"Geokoding og bygningsberikelse" under), og **ikke** `organizations`-samlingen
fra kilden, som inneholder personopplysninger om søkere - se prosjektets
minne om dette.

Kjøres skriptet på nytt for en kommune som allerede er lastet inn, oppdateres
radene i stedet for å dupliseres (`ON CONFLICT ... DO UPDATE`). En adresse som
er geokodet eller satt manuelt, og en kapasitet som er satt manuelt, overskrives
ikke. Se db/schema_kjerne_dokumentasjon.md for detaljene.

## Mapping: fra kildekode til vårt eget kodeverk

Fasitfilene i `etl/*_mapping/` er fasiten for mappingen, og databasen er
avledet fra dem. En endring i mappingen gjøres derfor i filen, committes og
kjøres med `etl/kjor_alt.sh mapping`. Det hentes ingenting fra kommunene på
nytt. Å angre er `git revert` og en ny kjøring.

`last_mapping.py` skriver mappingen til én tabell per kodetype:
`aktivitet_mapping` (én kildekode kan gi flere aktiviteter),
`lokaletype_mapping` og `fasilitet_mapping`. Vokabularet de peker på lastes fra
vokabularfilen ved siden av hver mappingfil (`activity_mapping/activities.json`,
`lokaletype_mapping/venue_types.json`, `fasilitet_mapping/facilities.json`).
Konsepter i fasetten `exclude` gir `ikke_relevant`. Rader laget av skriptet (`kartlagt_av =
'etl'`) fornyes ved hver kjøring. En manuell rad (`kartlagt_av` ulik `etl`)
overskrives aldri, og så lenge den finnes, lar skriptet den koden være i fred.

Koblingene `ressurs_aktivitet`, `ressurs_fasilitet` og `ressurs_lokaletype` er
visninger, regnet ut fra `ressurs_kildekode` og godkjent mapping hver gang de
leses. En endret mapping, enten fra fil eller manuelt, slår derfor inn med en
gang uten at noe annet må kjøres.

Kjør med `--dry-run` først: alt kjøres i én transaksjon, og til slutt skrives en
rapport over hvilke koblinger som ble lagt til og fjernet per aktivitet og
fasilitet, og hvilke ressurser som byttet lokaletype. Med `--dry-run` rulles
alt tilbake etterpå. Kildekoder uten mapping vises i `v_ukartlagte_kildekoder`.

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
   (SOAP, krever `MATRIKKELAPI_LOGIN`/`MATRIKKELAPI_PASSWORD` i `etl/.env` -
   se `matrikkel/test_auth.py`) lar oss søke *innenfor riktig kommune*, som vi
   allerede kjenner fra innlastingen. Skriptet bruker foreløpig testmiljøet
   `prodtest.matrikkel.no`.
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

Kjøres med `etl/kjor_alt.sh matrikkel`. Uten kjøreskriptet må innloggingen
eksporteres til skallet først:

```bash
set -a; . etl/.env; set +a

docker exec portico_masterdb psql -q -U postgres -d masterdb -tA -F'|' -c "
    SELECT a.id, a.adressetekst, a.postnummer, a.poststed, k.kommunenr,
           a.bygning_id, a.geokoding, a.gate_id, a.husnr, a.bokstav, g.adressekode
    FROM adresse a
    JOIN bygning b ON b.id = a.bygning_id
    JOIN kommune k ON k.id = b.kommune_id
    LEFT JOIN gate g ON g.id = a.gate_id
    WHERE a.er_hovedadresse AND a.geokoding <> 'manuell' AND a.adressetekst IS NOT NULL
      AND (a.geokoding IN ('ukjent','feilet') OR b.bygningsnr IS NULL
           OR NOT EXISTS (SELECT 1 FROM matrikkelinfo m WHERE m.bygning_id = b.id));" \
    | python3 etl/matrikkel_adresse.py > etl/ut/matrikkel.sql

docker exec -i portico_masterdb psql -q -U postgres -d masterdb < etl/ut/matrikkel.sql
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
