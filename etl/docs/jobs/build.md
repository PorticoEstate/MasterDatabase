# `jobs/build.py` — bygging

Steg 2 i pipelinen (se [pipeline](../pipeline.md)), kjøres én gang for å bygge
masteren. Etter det holder [`jobs/sync.py`](sync.md) databasen oppdatert.

## Formål

Henter data fra Aktiv kommune og skriver SQL som fyller en tom master: kommune,
bygg, adresser (uten koordinater), ressurser og koblingene ressurs →
lokaletype/aktivitet/fasilitet, på id. I tillegg oppretter den kodeverkene
(`lokaletype`, `aktivitet`, `fasilitet`) fra instansene. Det er det som skiller
den fra synk: se tabellen i [lasting](../reference/loading.md).

Et konsept som allerede finnes i masteren røres aldri. Avvik (samme id med annet
navn eller annen forelder, eller en id masteren ikke kjenner) loggføres i
`synk_avvik` og kommer ikke inn i masteren.

## Bruk

Skriptet bruker bare Pythons innebygde bibliotek (ingen `pip install`) og
rører aldri databasen selv. Det skriver SQL til stdout, som du sender til
Postgres i et eget steg, så du kan se hva som skal skje før noe endres.

```bash
# En kommune, for å teste
(cd etl && python3 -m jobs.build bergen) > etl/ut/bergen.sql
docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/bergen.sql

# Alle 12 kommunene
(cd etl && python3 -m jobs.build alle) > etl/ut/alle.sql
docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/alle.sql
```

Databasen må finnes og ha skjemaet først: se [running](../running.md).

I containeren kjører `main.py build` det samme. Daemonen kjører bygging selv
når de tre kodeverkene er tomme, og geokoder etterpå (se [daemon](daemon.md)).

## Flagg

| Flagg | Hva det gjør |
|---|---|
| `--fra-fil MAPPE` | Leser `<mappe>/<slug>.json` i stedet for å hente fra nettet. Brukes av [demo-normaliseringen](../../dev/demo_normalisering/README.md) |

`jobs/build.py` har ikke `--kommuner-fil`: den bruker alltid den innebygde
`KOMMUNER` i `lib/kommuner.py`. Den er utgangspunktet for en tom master, og
byggingen registrerer hver kommune og dens Aktiv kommune-instans i databasen.
Se [adding-a-kommune](../reference/adding-a-kommune.md) for forskjellen mot synk.

## Hva den gjør og ikke gjør

Se [lasting](../reference/loading.md) for det som gjelder både bygging og synk
(hva som lastes, personvern, `cadastral_references`, idempotens). Spesielt for
bygging:

- Oppretter kodeverkskonsepter som mangler, og registrerer instansen som aktiv.
- Et nytt konsept opprettes ellers bare i masteren (manuelt, med id satt
  manuelt), aldri av en instans etter bygging.
- Kodeverkene er tomme i en ny database til denne er kjørt.

## Feilhåndtering

Alt som ikke lar seg laste loggføres i `synk_avvik`; én dårlig post stopper
aldri kjøringen. Se [avvik og kildeuttrekk](../reference/avvik-and-extracts.md)
og [kildekontrakten](../reference/source-contract.md).

## Se også

- [sync](sync.md), [geocode](geocode.md)
- [lasting](../reference/loading.md)
