# Geokoding av adresser (etl/geokod.py)

Dette dokumentet beskriver hvordan `etl/geokod.py` faktisk ble kjørt, og hva
som ble gjort med resultatet. Skriptet slår opp adressetekst mot Kartverkets
åpne Adresse-API og fyller `adresse.posisjon` (og `bygning.posisjon` som
fallback) for adresser som mangler posisjon.

Miljø: Postgres/PostGIS kjører i Docker-containeren `portico_masterdb`
(image `postgis/postgis:18-3.6`, port 5432 eksponert til host). Databasen
som ble brukt her heter **`OppdatertDatabaseMagnus`** (ikke `masterdb`, som
står i docstringen i selve skriptet). pgAdmin 4 kan brukes til å bla i
resultatet etterpå via `localhost:5432`, men selve kjøringen skjer via
`docker exec` i terminalen — det er ikke nødvendig å ha `psql` installert
lokalt, siden containeren har det innebygd.

## Steg 1 – Hent adresser som mangler posisjon

```
docker exec portico_masterdb psql -U postgres -d OppdatertDatabaseMagnus -tA -F'|' -c "
    SELECT a.id, a.adressetekst, a.postnummer, a.poststed, k.kommunenr
    FROM adresse a
    JOIN bygning b ON b.id = a.bygning_id
    JOIN kommune k ON k.id = b.kommune_id
    WHERE a.posisjon IS NULL AND a.adressetekst IS NOT NULL;
" > etl/ut/adresser_a_geokode.txt
```

Dette er rent lesende og trygt å kjøre om igjen — filen overskrives, men
ingenting i databasen endres.

## Steg 2 – Kjør geokodingsskriptet lokalt

```
python3 etl/geokod.py < etl/ut/adresser_a_geokode.txt > etl/ut/geokoding.sql
```

Ren fil-inn/fil-ut, ingen databasetilkobling i dette steget. Skriptet kaller
Kartverkets API (`https://ws.geonorge.no/adresser/v1/sok`) én gang per rad,
med 0.2s pause mellom hvert kall. Fremdrift logges til stderr
(`geokoder [id] 'adressetekst' (postnummer)...`).

Output er en SQL-fil pakket i `BEGIN;` / `COMMIT;` — ingenting skjer mot
databasen før filen faktisk kjøres i steg 3. Kan trygt avbrytes og kjøres på
nytt uten at steg 1 må gjøres om, siden steg 2 aldri skriver til
inputfilen.

## Steg 3 – Skriv resultatet til databasen

```
docker exec -i portico_masterdb psql -U postgres -d OppdatertDatabaseMagnus < etl/ut/geokoding.sql
```

Kjøres som én transaksjon (`BEGIN;` ... `COMMIT;`) — feiler noe midtveis,
ruller alt tilbake i stedet for å gi delvise endringer.

## Prinsippet skriptet følger

Fra docstringen i [geokod.py](geokod.py): ett eksakt treff brukes. Null
treff eller flere enn ett treff logges som avvik i `synk_avvik` og
gjettes **ikke** på — et geokodet punkt som er feil er verre enn ingen
punkt, siden det gir falsk trygghet i et nærhetssøk.

Samme logikk gjelder kommunenummer: hvis Kartverket sitt geokodede
kommunenummer ikke stemmer med det adressen allerede har i databasen,
settes posisjonen likevel, men avviket logges og `kommune_id` overskrives
**ikke** automatisk — det regnes som identitetsdata satt av innlastingen,
ikke noe geokodingsskriptet skal endre stille.

## Resultat av kjøringen (2026-09-25)

420 adresser totalt, kjørt mot `OppdatertDatabaseMagnus`:

- **238 geokodet** — posisjon satt på adresse (og speilet til bygning der
  bygningen ikke allerede hadde posisjon).
- **182 feilet** (logget i `synk_avvik`, `avvikstype='geokoding_feilet'`):
  - **106 "ingen treff"** — hovedsakelig skrivefeil i adressetekst,
    adresser uten husnummer i det offisielle registeret, eller stedsnavn
    som ikke er en offisiell adresse (f.eks. "Nesttun torg").
  - **76 "N treff, ingen valgt automatisk"** (flere treff, ikke
    entydig):
    - 41 av disse traff API-taket `treffPerSide=5` i
      [geokod.py](geokod.py) (`sok_adresse`) — reelt antall treff kan
      være høyere enn 5:
      - 23 hadde ikke postnummer i kildedataen, så
        postnummer-filteret fikk ingen mulighet til å snevre inn.
      - 18 hadde postnummer, men fikk fortsatt 5 treff etter
        filtrering — sannsynligvis samme gate/postnummer med flere
        husnumre og en for upresis adressetekst.
    - 35 hadde 2–4 treff i utgangspunktet (ekte flertydighet).
- **4 kommune-mismatch** (logget som `avvikstype='annet'`, posisjon
  likevel satt):

  | id | adresse | postnummer/poststed | antatt kommunenr | Kartverket sier |
  |----|---------|----------------------|-------------------|------------------|
  | 365 | Moseidsletta 41 | 4052 Røyneberg | 1103 | 1124 |
  | 580 | Sentrum 17 | 9151 Storslett | 5540 | 5544 |
  | 581 | Flomstadvegen 14 | 9151 Storslett | 5540 | 5544 |
  | 582 | Lyngsmark 10 | 9151 Storslett | 5540 | 5544 |

  3 av 4 er samme postnummer (9151 Storslett) med samme avviksretning
  (5540 → 5544) — dette ser ut som et systematisk mønster (f.eks. hele
  postnummeret lastet inn mot feil kommune), ikke tre uavhengige
  skrivefeil. Hvilket kommunenummer som faktisk er korrekt er **ikke**
  bekreftet mot Kartverkets/SSBs offisielle kommuneliste her — det bør
  avklares manuelt, ikke gjettes på.

Konklusjon: 182/420 (~43 %) feilrate er høy, men i tråd med skriptets
prinsipp om ikke å gjette. Hovedårsaken ser ut til å være manglende
postnummer i kildedata (56 av 420 rader) kombinert med upresise
adressetekster, ikke en feil i skriptet selv.

## Oppfølging som gjenstår

- Manuell gjennomgang av de 186 radene i `synk_avvik` (samling='adresse')
  for adressene fra denne kjøringen.
- Avklare hvilket kommunenummer som er korrekt for de 4
  kommune-mismatch-radene over, og eventuelt sjekke om hele postnummer
  9151 (Storslett) er lastet inn mot feil kommune i utgangspunktet.
- Vurdere å øke `treffPerSide` i `sok_adresse()` i
  [geokod.py](geokod.py) for å se reelt antall treff på de 41 adressene
  som traff API-taket på 5, i stedet for å anta at 5 er det faktiske
  treff-antallet.
