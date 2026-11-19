# `jobs/geocode.py` — geokoding og bygningsberikelse

Steg 3 i pipelinen (se [pipeline](../pipeline.md)). Kjøres etter bygging og
etter hver synk, så nye bygg får posisjon.

## Formål

`jobs/geocode.py` er eneste geokodingssteg i pipelinen, og gjør to ting:

1. **Geokoding** av enhver hovedadresse som ennå ikke er løst. MatrikkelAPI
   (SOAP, krever `MATRIKKEL_BRUKER`/`MATRIKKEL_PASSORD` - se
   `etl/dev/check_matrikkel_auth.py`) lar oss søke *innenfor riktig kommune*, som vi
   allerede kjenner fra innlastingen.
2. **Bygningsnummer og bygningsfakta** for bygninger som mangler det,
   uansett om adressen ble løst i denne kjøringen eller en tidligere.
   Matrikkelen er kilden til bygningsfaktaene. Aktiv kommune kan oppgi et
   bygningsnummer i `cadastral_references`, men det er foreløpig tynt fylt.
   Bygningsoppslaget gjøres for hver adresse spørringen under returnerer, uten å
   sjekke om bygget allerede har `bygningsnr`: kommer et bygg med fordi
   `matrikkelinfo` mangler, oppdateres også `bygningsnr`, `bygningstype`,
   `bra_m2` og `antall_etasjer` på nytt fra Matrikkelen (`posisjon`
   overskrives ikke).

Skriptet slår bare opp adressene spørringen under returnerer, ikke hele
databasen: etter første kjøring er det restmengden som prøves på nytt.

Se modulens docstring for hele kjeden av SOAP-kall, og
[geokoding-design](../reference/geocoding-design.md) for begrunnelsene og
detaljene i oppslagskjeden.

## Bruk

Miljøvariabler: `MATRIKKEL_BRUKER`, `MATRIKKEL_PASSORD`, og `MATRIKKEL_MILJO`
(`test` = `prodtest.matrikkel.no`, standard; `prod` = `matrikkel.no`). Verifiser
innloggingen først med `python3 etl/dev/check_matrikkel_auth.py`.

```bash
docker exec portico_masterdb psql -U postgres -d masterdb -tA -F'|' -c "
    SELECT a.id, a.adressetekst, a.postnummer, a.poststed, k.kommunenr,
           a.bygning_id, a.geokoding, a.gate_id, a.husnr, a.bokstav, g.adressekode,
           b.bygningsnr
    FROM adresse a
    JOIN bygning b ON b.id = a.bygning_id
    JOIN kommune k ON k.id = b.kommune_id
    LEFT JOIN gate g ON g.id = a.gate_id
    WHERE a.er_hovedadresse AND a.geokoding <> 'manuell' AND a.adressetekst IS NOT NULL
      AND (a.geokoding = 'ukjent' OR b.bygningsnr IS NULL
           OR NOT EXISTS (SELECT 1 FROM matrikkelinfo m WHERE m.bygning_id = b.id)
           OR (b.bygningsnr IS NOT NULL AND b.matrikkel_match IN ('ikke_forsokt','ikke_funnet')));
" > etl/ut/adresser_a_matrikkelsoke.txt

(cd etl && python3 -m jobs.geocode) < etl/ut/adresser_a_matrikkelsoke.txt > etl/ut/matrikkel.sql

docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/matrikkel.sql
```

Spørringen finnes også i `etl/sql/geocode_query.sql`. I containeren gjør
`main.py geocode` alle tre stegene selv.

## Inn og ut

- **Inn:** rader fra spørringen over, på stdin.
- **Ut:** SQL på stdout (rører aldri databasen selv), og et sammendrag på
  stderr. Sammendraget teller blant annet bekreftelser (`bygningsnr bekreftet
  mot kildens cadastral_references`).

## Hva den skriver

- `matrikkelinfo` (gnr/bnr/fnr/snr, knyttet til adressens bygg via
  `bygning_id`) uansett geokodingsstatus - billig og idempotent (`ON CONFLICT
  DO NOTHING`), så det forsøkes for enhver adresse vi klarer å slå opp i
  Matrikkelen, ikke bare de som fortsatt mangler geokoding.
- Ved adressetreff som *fortsatt* mangler geokoding: i tillegg `gate`
  (adressekode+gatenavn), `adresse.posisjon/husnr/bokstav` og
  `geokoding='matrikkel'` - den autoritative statusen, se
  `db/schema_kjerne_dokumentasjon.md`.
- Ved bygningstreff (alltid forsøkt, også for adresser som var løst fra
  før): `bygning.bygningsnr`, `bygningstype` (Matrikkelens rå kodeverdi, ikke
  oversatt til navn ennå), `bra_m2`, `antall_etasjer` og `matrikkel_match`:
  `'bygningsnr'` når kildens nummer ble bekreftet, ellers `'adresse'`.

## Hva den ikke gjør

- Overskriver aldri `geokoding='manuell'`.
- Overskriver aldri en `'adresse'`-match adressesteget nettopp satte for samme bygg.
- Skriver ikke `posisjon` fra bygningsnummer-oppslaget (den kommer fra adressen).
- Bruker ikke Kartverkets åpne Adresse-API (fjernet med vilje, se
  [geokoding-design](../reference/geocoding-design.md)).
- Bruker ikke kildens gnr/bnr ennå.

## Feilhåndtering

- Mislykkes bygningsoppslaget (ingen/flere bygg funnet, API-feil, eller bygg uten
  bygningsnummer), settes `matrikkel_match='ikke_funnet'` i stedet - uten dette
  ville et forsøkt-men-mislykket oppslag sett identisk ut som et som aldri ble
  forsøkt.
- En adresse som ikke lar seg løse får en rad i `synk_avvik` og blir stående
  som `'ukjent'`, og er dermed med i neste kjøring. Det finnes ingen egen
  `'feilet'`-status.
- Se [avvik og kildeuttrekk](../reference/avvik-and-extracts.md).

## Se også

- [geokoding-design](../reference/geocoding-design.md) - begrunnelser, oppslagskjeden for bygningsnummer, testresultater
- [gater](gater.md) - henter alle gater i en kommune
