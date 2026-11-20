# `jobs/sync.py` — jevnlig synkronisering

Steg 2 i pipelinen (se [pipeline](../pipeline.md)), kjøres jevnlig etter at
[`jobs/build.py`](build.md) har bygget masteren. Containeren kjører den hver
natt.

## Formål

Holder masteren oppdatert fra Aktiv kommune: kommune, bygg, adresser,
ressurser og koblingene ressurs → bygg/lokaletype/aktivitet/fasilitet, også
nye bygg og ressurser. Kilden vinner på koblingene.

Forskjellen fra bygging er at synk **aldri skriver kodeverkene**
(`lokaletype`, `aktivitet`, `fasilitet`). En id masteren ikke kjenner, et
annet navn eller en annen forelder loggføres i `synk_avvik`. Se tabellen i
[lasting](../reference/loading.md).

## Hvilke kommuner som synkroniseres

Synk bruker alltid kommunene som er registrert i databasen, og **nekter å kjøre
uten `--kommuner-fil`**. Den faller aldri tilbake på den innebygde listen
(det gjør bare [bygging](build.md)). Demo-normaliseringen følger samme liste som
skriptet den mater.

`main.py sync` lager listen ved å kjøre `sql/kommuner_query.sql`, som lister
alle kommuner som har en **aktiv** `fagsystem_instans` av typen `booking` med
`kildenokkel` som begynner på `aktiv-kommune:`. Resultatet
(`slug|kommunenr|navn|fylke|base_url`, én linje per kommune) skrives til
`etl/ut/kommuner.txt` og sendes med `--kommuner-fil`. Hvis spørringen feiler,
synkroniseres ingenting den natten.

En kommune synkroniseres altså når den har en slik aktiv instans. Se
[adding-a-kommune](../reference/adding-a-kommune.md) for hvordan den
registreres og aktiveres.

## Bruk

```bash
psql -tA -F'|' -f etl/sql/kommuner_query.sql > etl/ut/kommuner.txt
(cd etl && python3 -m jobs.sync alle --kommuner-fil ut/kommuner.txt) > etl/ut/synk.sql
docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/synk.sql
```

I containeren: `docker compose exec etl python3 main.py sync`.

## Flagg

Se tabellen over `--kommuner-fil` og `--fra-fil` i
[adding-a-kommune](../reference/adding-a-kommune.md#flaggene---kommuner-fil-og---fra-fil).

## Geokoding kommer ikke av seg selv

Den planlagte nattkjøringen er tre separate jobber etter hverandre:
`nightly-load` (synk), `geocode` ([`jobs/geocode.py`](geocode.md), så nye bygg
får posisjon) og `prune`. Synk-jobben geokoder ikke selv: trigges `sync` alene
(`main.py sync` eller jobbserveren), kommer ingen geokoding etter, og `geocode`
må trigges for seg. Se [daemon](daemon.md).

## Hva den gjør og ikke gjør

Se [lasting](../reference/loading.md) for det som gjelder både bygging og synk.
Spesielt for synk:

- Skriver aldri kodeverkene, og fjerner aldri konsepter.
- Koblingene (`ressurs_aktivitet`, `ressurs_fasilitet`) bygges på nytt for
  instansen ved hver kjøring.
- Laster en kommune som er lagt til etter bygging, men siden den ikke skriver
  kodeverkene, loggføres id-er masteren ikke kjenner i `synk_avvik` og kobles
  ikke.
- Mens `NORMALISER_DEMO=true` kjenner demo-mappingfilene bare de eksisterende
  kildene, så regn med `synk_avvik`-rader for en ny kommune helt til instansen
  er normalisert.

## Se også

- [build](build.md), [geocode](geocode.md)
- [lasting](../reference/loading.md)
- [avvik og kildeuttrekk](../reference/avvik-and-extracts.md)
