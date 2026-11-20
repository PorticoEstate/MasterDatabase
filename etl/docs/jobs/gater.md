# `jobs/gater.py` — gater for hele kommunen

Henter *alle* veger i en kommune fra Matrikkelen inn i tabellen `gate`.
Ligger utenfor den løpende kjeden build → sync → geocode (se
[pipeline](../pipeline.md)): daemonen kjører den etter en bygging, og ellers
kjøres den for hånd.

## Formål

`gate` fylles på to måter:

- [`jobs/geocode.py`](geocode.md) legger inn gaten til hver adresse den løser.
- `jobs/gater.py` henter i tillegg *alle* veger i kommunen, uten at kommunen
  trenger en Aktiv kommune-instans, bygg eller adresser. Det eneste som kreves
  er en rad i `kommune`.

## Bruk

```bash
docker compose exec etl python3 main.py gater              # alle kommuner
docker compose exec etl python3 main.py gater 4601 5601    # bestemte kommuner
```

Uten containeren, som modul fra `etl/`:

```bash
(cd etl && python3 -m jobs.gater 4601 5601) > etl/ut/gater.sql
```

Miljøvariabler: `MATRIKKEL_BRUKER`, `MATRIKKEL_PASSORD` og `MATRIKKEL_MILJO`,
som for `jobs/geocode.py`. Verdiene skrives aldri ut. Er brukernavn eller
passord ikke satt, hoppes steget over i `main.py`.

## Når det kjøres

Daemonen kjører steget etter en bygging, for *alle* kommuner i `kommune`
(rekkefølge: bygging, gater, geokoding):

- etter den første bygget av en tom database, og
- i det nattlige forsøket som bygger på nytt når kodeverkene fortsatt er tomme.

Det kjøres aldri etter en vanlig synk, og ikke ved senere oppstarter. Etter det
holdes `gate` oppdatert ved å kjøre steget for hånd, for eksempel for en ny
kommune eller for å fange nye og omdøpte gater.

## Inn og ut

- **Inn:** kommunenumre som argumenter.
- **Ut:** SQL på stdout (rører aldri databasen selv), som `main.py` sender til
  `psql`. Hver kommune er sin egen transaksjon.

Kjeden (MatrikkelAPI, SOAP):

```
KommuneService.findKommuneIdForIdent   kommunenummer -> intern KommuneId
AdresseService.findVegerForKommune     KommuneId -> alle VegId-er
StoreService.getObjects                VegId-er -> adressekode + adressenavn
```

## Hva den gjør og ikke gjør

- Trygt å kjøre om igjen: `gate` har `UNIQUE (kommune_id, adressekode)`, og en
  eksisterende gate beholder id-en sin (bare gatenavnet oppdateres hvis
  Matrikkelen har endret det), så `adresse.gate_id` peker fortsatt riktig.
- Sletter aldri gater, siden `adresse.gate_id` peker på dem.
- Krever ikke Aktiv kommune; rører ikke bygg eller adresser.

## Feilhåndtering

Feiler en kommune (ukjent i Matrikkelen, nettverk), logges det i `synk_avvik`
med kilde `matrikkel-gate`, og de andre kommunene fortsetter. Exit-kode 2 betyr
at minst én kommune feilet. En kommune der henting feilet prøves på nytt neste
gang steget kjøres for den. Se
[avvik og kildeuttrekk](../reference/avvik-and-extracts.md).
