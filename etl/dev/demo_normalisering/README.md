# Demo-normalisering

Mappingen er midlertidig. Den viser hvordan masterdatabasen blir når instansene
er normalisert, og brukes ikke i produksjon. Alt den trenger ligger i denne
mappen, og mappen (med dette dokumentet) slettes når normaliseringen er på
plass. Verken `jobs/build.py` eller `jobs/sync.py` trenger endring da.
Kontrakten den simulerer står i
[source-contract](../../docs/reference/source-contract.md).

`normaliser.py` leser `searchdataall` (nettet, eller `--fra-fil`), og skriver
`<kommune>.json` med samme form, men med kodeverkene erstattet av vokabularet
fra filene (`id`, `name`, `parent_id`) og koblingene omskrevet. Kildenavn uten
mapping, eller som mappes til et exclude-konsept, får ingen kobling og skrives
til standard-feil.

```bash
python3 etl/dev/demo_normalisering/normaliser.py alle              # skriver etl/ut/normalisert/
(cd etl && python3 -m jobs.build alle --fra-fil ut/normalisert) > etl/ut/alle.sql
docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/alle.sql
```

`jobs/sync.py` tar samme `--fra-fil`. I containeren styres demoen av
`NORMALISER_DEMO=true`.

## Vokabular og mapping

Konseptene i vokabularfilene har hver en fast `id` (den delte id-en), og
`broader` er forelderens navn. Et nytt konsept får neste ledige id; en id
endres eller gjenbrukes aldri. En endring i `mapping.json` eller
vokabularfilene slår igjennom ved neste kjøring av `normaliser.py`, men
`jobs/build.py` oppretter bare konsepter som mangler, så en omdøping eller en
ny forelder i filene når ikke en database som allerede er bygget. Fasettene
(`facets`) er bare en gruppering i filene og havner ikke i databasen.

| Mappe | Vokabular | Mapping |
|---|---|---|
| `lokaletype_mapping/` | `venue_types.json` | `mapping.json` |
| `fasilitet_mapping/` | `facilities.json` | `mapping.json` |
| `activity_mapping/` | `activities.json` | `mapping.json` |

I produksjon finnes ingen vokabularfiler i prosjektet: kodeverkene bygges fra
de normaliserte instansene ved bygging, og eies deretter av masteren.

## Begrensning: demoen skjuler brudd på kontrakten

Demoen bygger vokabularet fra filene, så manglende foreldre og ukjente
kodeverks-id-er i kilden gir ingen avvik. Et rent `synk_avvik` for kodeverkene
etter en demokjøring sier derfor ingenting om kildens kvalitet. Avvikene på
koblingene (til ressurser som ikke er med i uttrekket) kommer derimot med.
