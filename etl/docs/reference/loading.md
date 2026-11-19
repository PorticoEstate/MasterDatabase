# Lasting: hva bygging og synk gjør og ikke gjør

Gjelder både [`jobs/build.py`](../jobs/build.md) og
[`jobs/sync.py`](../jobs/sync.md). De deler selve lastingen i `lib/load.py`
(`generer_sql`). Forskjellen er flagget `initial_build`, som styrer opprettelsen
av kodeverkskonsepter og om instansen registreres som aktiv. En rettelse i
lastingen gjelder derfor begge; `jobs/build.py` og `jobs/sync.py` har bare
docstring og kommandolinje.

## Bygging og synk

Masteren eier vokabularet og hierarkiet (`lokaletype`, `aktivitet`, `fasilitet`).
Kommunen eier derimot det den selv registrerer: bygg, ressurser og koblingene
fra ressurs til bygg, lokaletype, aktivitet og fasilitet. Skriptene skiller seg
bare på hvordan de behandler kodeverkene (`lokaletype`, `aktivitet`, `fasilitet`):

| | `jobs/build.py` (bygging, én gang) | `jobs/sync.py` (jevnlig) |
|---|---|---|
| Kodeverk | Oppretter konsepter som mangler (`id`, `navn`, forelder). Et konsept som finnes røres aldri | Skriver aldri |
| Avvik fra masteren (samme id med annet navn eller annen forelder) | Loggføres i `synk_avvik` | Loggføres i `synk_avvik` |
| Bygg og ressurser, også nye | Lastes | Lastes |
| Koblinger ressurs → bygg, lokaletype, aktivitet, fasilitet | Lastes. Kilden vinner | Lastes. Kilden vinner |
| Kobling til en id masteren ikke kjenner | Lastes ikke, loggføres én gang per id | Lastes ikke, loggføres én gang per id |

Et nytt konsept opprettes altså bare i masteren (manuelt, med id satt manuelt),
aldri av en instans etter bygging. En instans som begynner å bruke en ny id,
gir avvik og ingen kobling til den id-en.

## Hva som lastes

Laster: kommune, bygg, adresser (som de står i kilden, uten koordinater) og
ressurser. Ressursene kobles direkte til kodeverkene på id
(`ressurs.lokaletype_id`, `ressurs_aktivitet`, `ressurs_fasilitet`). Kildens
egne koder lagres ikke; etter normalisering er de lik masterens id-er.

Skriptene gjør ingen oversettelse. Det er instansene som skal levere et
normalisert kodeverk med masterens id-er (se
[kildekontrakten](source-contract.md)). Brudd på kontrakten loggføres i
`synk_avvik`. Kodeverkene er tomme i en ny database til `jobs/build.py` er
kjørt.

Koblingene (`ressurs_aktivitet`, `ressurs_fasilitet`) bygges på nytt for
instansen ved hver kjøring. Kodeverkene selv får aldri konsepter fjernet; et
konsept som forsvinner fra kilden, blir stående.

## Hva som ikke lastes

- Koordinater og matrikkeldata: eget steg, se [geocode](../jobs/geocode.md).
- **`organizations`-samlingen fra kilden**, som inneholder personopplysninger om
  søkere. Den skal aldri lastes.

## Kildens bygningsnummer (`cadastral_references`)

Hvert bygg i kilden kan ha `cadastral_references` (en liste). Fra den leses
høyst ett bygningsnummer (entries med `cadastral_type` `BUILDING` og et positivt
heltall i `building_number`) og skrives til `bygning.bygningsnr` bare når
kolonnen er NULL; en verdi Matrikkelen har gitt overskrives aldri. Tallet er
en påstand fra kilden til geocode har bekreftet det.

Flere forskjellige tall, en ugyldig verdi, eller en entry med
`building_id`/`municipality_id` som ikke stemmer, gir en rad i `synk_avvik` og
brukes ikke. Settes et tall på et bygg som geocode allerede har sett uten å få
bygningsnr (`matrikkel_match` `adresse` eller `ikke_funnet`), tilbakestilles
`matrikkel_match` til `ikke_forsokt` så tallet blir verifisert.

Feltet er foreløpig tynt fylt i kildene (i demodataene er det utfylt på 2 av 720
bygg; eierne legger det inn fortløpende), så effekten er liten inntil videre.
gnr/bnr/fnr/snr i samme entries leses ikke ennå. Hva geocode gjør med tallet
står i [geokoding-design](geocoding-design.md).

## Idempotens

Kjøres et skript på nytt for en kommune som allerede er lastet inn, oppdateres
radene i stedet for å dupliseres (`ON CONFLICT ... DO UPDATE`). En adresse som
er geokodet eller satt manuelt, og en kapasitet som er satt manuelt,
overskrives ikke. Se `db/schema_kjerne_dokumentasjon.md` for detaljene.

## `ressurslenke`

`ressurslenke` kobler samme ressurs til flere fagsystemer (f.eks. booking +
FDV), med én rad og URL per system. `lib/load.py` skriver ressursens egen
bookinglenke (`ressurslenke_sql` i `lib/sqlgen.py`), og
`v_ressurs_sok.booking_url` leses derfra. Lenker til andre systemer legges til
av det som laster dem; synken rører dem ikke. Bygglenker bygges fortsatt i
viewet.

## Kjent forenkling

`kommune_id` settes i dag fra hvilken Aktiv kommune-instans dataene kommer fra
(`bergen` → kommunenr 4601). Det stemmer for alle 12 instansene som finnes i
dag. Skjemaet støtter at en instans betjener flere kommuner (tabellen
`kommune_fagsystem_instans`); den dagen det faktisk skjer for en av instansene
vi laster fra, må `kommune_id` i stedet utledes fra en geokodet adresse, ikke
fra instansen.
