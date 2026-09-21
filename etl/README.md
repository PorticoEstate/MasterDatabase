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

## Kjent forenkling

`kommune_id` settes i dag fra hvilken Aktiv kommune-instans dataene kommer
fra (`bergen` → kommunenr 4601). Det stemmer for alle 12 instansene som
finnes i dag. Skjemaet støtter at en instans betjener flere kommuner
(tabellen `instans_kommune`); den dagen det faktisk skjer for en av
instansene vi laster fra, må `kommune_id` i stedet utledes fra en geokodet
adresse, ikke fra instansen.
