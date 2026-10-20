# backend (Java/Spring Boot)

Read-only API mot `masterdb`, pluss et admin-API for å oppdatere
`etl/*_mapping/mapping.json` og automatisk trigge en ny
`etl/last_inn.py alle`-kjøring. Kontrakten står i `../api/openapi.yaml`.

Erstatter den gamle PHP/Apache-skissen i repo-roten (`Dockerfile`,
`docker-compose.yml`), som bare serverte spec-en statisk.

## Endepunkter

**Offentlige, read-only:**
- `GET /health`
- `GET /buildings?bydelNavn=&limit=&cursor=`
- `GET /swagger-ui.html` - levende Swagger UI, generert fra koden
- `GET /v3/api-docs` - samme spec som rå JSON

**Admin (krever JWT med `scope: admin`):**
- `GET /admin/mapping/{lokaletype|fasilitet|aktivitet}` - hent gjeldende fil
- `PUT /admin/mapping/{lokaletype|fasilitet|aktivitet}` - oppdater (body = hele JSON-filen)
- `POST /admin/etl-jobs` - trigg en kjøring manuelt (nyttig for å teste kjeden uten å vente på filovervåkingen)
- `GET /admin/etl-jobs/latest`, `GET /admin/etl-jobs` - status/historikk

En `PUT` mot `/admin/mapping/...` trigger **ikke** kjøringen direkte - den
skriver filen, og `MappingFileWatcherService` oppdager endringen og trigger
etter en kort debounce (`etl.debounce-seconds`, default 3s). Det er bevisst
étt enhetlig triggerpunkt, uansett om endringen kom fra admin-API-et eller en
vanlig fil-redigering/git-endring i det mountede repoet.

## Hvorfor dette er trygt å automatisere

`etl/last_inn.py` er allerede bygget for akkurat dette: hver kommunes
innlasting er sin egen `BEGIN;...COMMIT;`-transaksjon, manuelt satte verdier
overskrives aldri, og én dårlig post/kommune stopper aldri resten (se
`../etl/README.md`). `EtlTriggerService` kjører skriptet, fanger opp den
genererte SQL-en fra stdout, og sender den rett til Postgres via JDBC -
samme SQL som dere ellers ville sett over og limt inn i `psql` manuelt.

Kjøringer serialiseres (én om gangen) via en enkelt-tråds kø, slik at to
triggere aldri kan overlappe.

## Kjøre lokalt

```bash
cd backend
mvn spring-boot:run \
  -Dspring-boot.run.arguments="--spring.datasource.url=jdbc:postgresql://localhost:5432/masterdb"
```

Eller via Docker Compose fra repo-roten (se `../docker-compose.yml`).

## Teste admin-endepunktene lokalt

Det finnes ingen identitetsleverandør ennå - JWT valideres med en delt
HMAC-nøkkel (`security.jwt.secret` / miljøvariabelen `JWT_SECRET`). For å
generere et testtoken som matcher default-nøkkelen:

```bash
mvn test-compile
java -cp "target/test-classes:target/classes:$(mvn -q dependency:build-classpath -Dmdep.outputFile=/dev/stdout)" \
  no.bergenkommune.masterdb.dev.DevTokenPrinter
```

(Eller kjør `DevTokenPrinter.main()` direkte fra IDE-en - enklest i praksis.)

```bash
TOKEN=$(...)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/admin/etl-jobs/latest
```

**Dette er kun for lokal utvikling.** Før reell drift må den delte nøkkelen
erstattes med en ekte identitetsleverandør (OAuth2/OIDC) - se
`SecurityConfig.java`.

## Kjøre testene

```bash
mvn test
```

`MappingFileServiceTest` dekker selve skrive-/valideringsflyten uten å kreve
en kjørende database. For en reell ende-til-ende-test av hele kjeden
(admin-endring → trigget kjøring → data i databasen), bruk en engangsdatabase
slik resten av prosjektet gjør:

```bash
docker exec portico_masterdb psql -U postgres -c "CREATE DATABASE masterdb_test;"
# pek SPRING_DATASOURCE_URL mot masterdb_test, kjør appen, gjør et PUT-kall
# mot /admin/mapping/lokaletype, og verifiser at kildekode_mapping endrer seg.
docker exec portico_masterdb psql -U postgres -c "DROP DATABASE masterdb_test;"
```
