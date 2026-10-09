# Innlasting fra Aktiv kommune

`last_inn.py` henter data fra Aktiv kommune og skriver SQL som fyller
masterdatabasen. Se `db/schema_kjerne_dokumentasjon.md` for hva tabellene betyr.

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
til vårt eget kodeverk (`lokaletype`/`aktivitet`/`fasilitet`).

Laster **ikke**: koordinater (krever et eget geokodingssteg mot Kartverkets
Adresse-API, ikke skrevet ennå), matrikkeldata (krever avtale med Kartverket),
og **ikke** `organizations`-samlingen fra kilden, som inneholder
personopplysninger om søkere - se prosjektets minne om dette.

Kjøres skriptet på nytt for en kommune som allerede er lastet inn, oppdateres
radene i stedet for å dupliseres (`ON CONFLICT ... DO UPDATE`). En adresse som
er geokodet eller satt manuelt, og en kapasitet som er satt manuelt, overskrives
ikke. Se db/schema_kjerne_dokumentasjon.md for detaljene.

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

## Geokoding

`geokod.py` fyller `adresse.posisjon` og `bygning.posisjon` fra Kartverkets åpne Adresse-API. Hvert geokodingsavvik lagrer oppslaget og Kartverkets svar direkte på avviket (`rapost`). Leser en enkel liste fra standard-inn, skriver SQL til standard-ut - samme mønster som `last_inn.py`, ingen ekstra Python-pakker.

```bash
docker exec portico_masterdb psql -U postgres -d masterdb -tA -F'|' -c "
    SELECT a.id, a.adressetekst, a.postnummer, a.poststed, k.kommunenr
    FROM adresse a
    JOIN bygning b ON b.id = a.bygning_id
    JOIN kommune k ON k.id = b.kommune_id
    WHERE a.posisjon IS NULL AND a.adressetekst IS NOT NULL;
" > etl/ut/adresser_a_geokode.txt

python3 etl/geokod.py < etl/ut/adresser_a_geokode.txt > etl/ut/geokoding.sql

docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/geokoding.sql
```

Kjøres trygt på nytt: `WHERE a.posisjon IS NULL` i dumpen sørger for at bare det som fortsatt mangler blir sendt til API-et igjen.

**Prinsipp: ett eksakt treff brukes, ellers logges det som avvik.** Ingen fuzzy-gjetning - et geokodet punkt som er feil er verre enn intet punkt. Er `postnummer` kjent, kreves nøyaktig ett treff *med det postnummeret*; finnes ingen slike, regnes søket som mislykket selv om et ufiltrert søk ga andre treff et annet sted i landet. Dette ble funnet nødvendig i praksis: et fritekstsøk på «Festplassen» (Bergen) matchet først den eneste «Festplassen» i hele adresseregisteret med husnummer - som ligger i Lørenskog.

Reelt resultat ved full kjøring (423 bygg, 419 adresser å geokode): 234 geokodet, 185 feilet og loggført i `synk_avvik` (stavefeil/formatforskjeller mellom Aktiv kommune og det offisielle registeret, f.eks. «Wolfsgate 12x» mot det offisielle «Wolffs gate»), og 4 tilfeller der geokodingen fant et annet kommunenummer enn det innlastingen antok - loggført, ikke overskrevet, siden `kommune_id` er identitetsdata som ikke skal endres stille av et geokodingsoppslag.

## Matrikkel-geokoding og bygningsberikelse (andre pass)

`matrikkel_adresse.py` kjøres etter `geokod.py`, og gjør to ting:

1. **Andre forsøk på geokoding** for det `geokod.py` ikke klarte - enten fordi
   Kartverkets åpne Adresse-API ikke fant noe treff (stavemåte/format), eller
   fordi det fant flere treff og ingen kunne velges automatisk (ofte fordi
   husnummer manglet i kildedata). MatrikkelAPI (SOAP, krever
   `MATRIKKEL_BRUKER`/`MATRIKKEL_PASSORD` - se `matrikkel/test_auth.py`) lar
   oss søke *innenfor riktig kommune*, som vi allerede kjenner fra
   innlastingen - det løser begge feiltypene over, siden det åpne API-et bare
   søker fritekst nasjonalt.
2. **Bygningsnummer og bygningsfakta** for enhver bygning som mangler det,
   uansett hvilken av de to metodene som løste adressen. Aktiv kommune oppgir
   ikke bygningsnummer i det hele tatt - dette er den eneste kilden til det.

Se modulens docstring for hele kjeden av SOAP-kall.

Fyller ved adressetreff: `gate` (adressekode+gatenavn), `matrikkelinfo`+
`bygning_matrikkelinfo` (gnr/bnr/fnr/snr), `adresse.posisjon/husnr/bokstav`
og `geokoding='matrikkel'` - den autoritative statusen, se
`db/schema_kjerne_dokumentasjon.md`. Fyller ved bygningstreff (alltid forsøkt,
også for adresser som var løst fra før): `bygning.bygningsnr`, `bygningstype`
(Matrikkelens rå kodeverdi, ikke oversatt til navn ennå), `bra_m2`,
`antall_etasjer` og `matrikkel_match='adresse'`.

```bash
docker exec portico_masterdb psql -U postgres -d masterdb -tA -F'|' -c "
    SELECT a.id, a.adressetekst, a.postnummer, a.poststed, k.kommunenr,
           a.bygning_id, a.geokoding, a.gate_id, a.husnr, a.bokstav, g.adressekode
    FROM adresse a
    JOIN bygning b ON b.id = a.bygning_id
    JOIN kommune k ON k.id = b.kommune_id
    LEFT JOIN gate g ON g.id = a.gate_id
    WHERE a.er_hovedadresse AND a.geokoding <> 'manuell' AND a.adressetekst IS NOT NULL
      AND (a.geokoding IN ('ukjent','feilet') OR b.bygningsnr IS NULL);
" > etl/ut/adresser_a_matrikkelsoke.txt

python3 etl/matrikkel_adresse.py < etl/ut/adresser_a_matrikkelsoke.txt > etl/ut/matrikkel.sql

docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/matrikkel.sql
```

Kjøres trygt på nytt: `b.bygningsnr IS NULL` i dumpen sørger for at bygg som
allerede har bygningsnummer ikke slås opp igjen.

Reelt resultat ved testkjøring på Bergen (173 adresser å geokode): `geokod.py`
løste 94, sto igjen med 79. Av disse løste `matrikkel_adresse.py` 33 til -
kombinert 127 av 173 (73 %), opp fra 54 % med bare det åpne API-et. De
resterende 46 er enten ekte stave-/formatfeil Matrikkelen heller ikke kan
matche (f.eks. «Wolfsgate 12x»), eller mangler husnummer helt i kildedata
(f.eks. «Festplassen», «Nygårdsparken») - et datakvalitetsproblem i kilden,
ikke noe et adresseoppslag kan løse.

## Kjent forenkling

`kommune_id` settes i dag fra hvilken Aktiv kommune-instans dataene kommer
fra (`bergen` → kommunenr 4601). Det stemmer for alle 12 instansene som
finnes i dag. Skjemaet støtter at en instans betjener flere kommuner
(tabellen `kommune_fagsystem_instans`); den dagen det faktisk skjer for en av
instansene vi laster fra, må `kommune_id` i stedet utledes fra en geokodet
adresse, ikke fra instansen.
