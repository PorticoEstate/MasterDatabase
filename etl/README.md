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
radene i stedet for å dupliseres (`ON CONFLICT ... DO UPDATE`). Rader i
kildens koblingstabeller som peker på bygg eller ressurser utenfor uttrekket
kan ikke lastes og logges i stedet i `synk_avvik`, med `avvikstype` og en
kort forklaring - se den tabellen for å forstå datakvaliteten i det som ble
lastet inn.

## Geokoding

`geokod.py` fyller `adresse.posisjon` og `bygning.posisjon` fra Kartverkets åpne Adresse-API. Leser en enkel liste fra standard-inn, skriver SQL til standard-ut - samme mønster som `last_inn.py`, ingen ekstra Python-pakker.

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

## Kjent forenkling

`kommune_id` settes i dag fra hvilken Aktiv kommune-instans dataene kommer
fra (`bergen` → kommunenr 4601). Det stemmer for alle 12 instansene som
finnes i dag. Skjemaet støtter at en instans betjener flere kommuner
(tabellen `instans_kommune`); den dagen det faktisk skjer for en av
instansene vi laster fra, må `kommune_id` i stedet utledes fra en geokodet
adresse, ikke fra instansen.
