# Backend (søke-API)

Spring Boot-applikasjon som lar nettsiden søke på tvers av kommuner. Brukeren kan søke på fritekst, filtrere (kommune, lokaletype, aktivitet, fasilitet), eventuelt begrense til et område rundt et punkt, og få treff som bygg-kort og ressursliste. Et treff lenker videre til det lokale bookingsystemet. API-et sjekker aldri tilgjengelighet og booker ingenting. I tillegg finnes et API for administrasjon av kommuner (`/masterdb/kommune`), beskyttet av en API-nøkkel.

## Kjøre lokalt

Fra rotmappen:

```bash
docker compose up -d --build backend
```

Backend kjører på <http://localhost:8080>. `--build` er nødvendig etter endringer i kode eller `pom.xml`. Databasen (volumet `postgres_data`) berøres ikke. Ikke bruk `docker compose down -v` med mindre du vil slette databasen.

Databasetilkobling styres av miljøvariablene `DB_URL`, `DB_USER` og `DB_PASSWORD` (se `src/main/resources/application.properties` og `docker-compose.yml`).

The kommune endpoints require an API key. Set `MASTERDB_API_KEY` in `.env` (required: the backend refuses to start without it, and `docker compose` stops with an error). Clients send the key in the `X-API-KEY` header. The key is checked by `config/ApiKeyFilter.java`, which only applies to paths starting with `/masterdb/kommune`.

## Endepunkter

| Metode | Sti | Beskrivelse |
|---|---|---|
| GET | `/masterdb/search` | Fritekstsøk med filtre. Returnerer både `bygg` og `ressurser`, hver paginert. |
| GET | `/masterdb/search/filter` | Valgene til filterpanelet: kommuner (kode + navn), lokaletyper, aktiviteter og fasiliteter (id + navn). Hentes én gang, ikke per tastetrykk. |
| GET | `/masterdb/kommune` | All kommuner, ordered by name. Requires API key. |
| GET | `/masterdb/kommune/{id}` | One kommune by internal id. 404 if it does not exist. Requires API key. |
| POST | `/masterdb/kommune` | Create a kommune from `{kommunenr, navn, fylkesnavn}`. 201 with the created kommune, 400 on invalid input, 409 if `kommunenr` exists. Requires API key. |
| PUT | `/masterdb/kommune/{id}` | Replace `kommunenr`, `navn` and `fylkesnavn` (so `kommunenr` can be corrected, e.g. after a renumbering). 404 if the id does not exist, 409 if the `kommunenr` is taken. Requires API key. |
| DELETE | `/masterdb/kommune/{id}` | Delete a kommune. **Also deletes its buildings, addresses, streets and resources** (`ON DELETE CASCADE`). 204, or 404. Requires API key. |

Stiene er engelske, mens query-parametre (`q`, `kommune`, `lokaletype`, `aktivitet`, `fasilitet`, `sorter`, `side`, `storrelse`, `lat`, `lon`, `radiusMeter`) og JSON-felt er norske. Lister kan sendes som `?aktivitet=1&aktivitet=2` eller `?aktivitet=1,2`.

Koden ligger i `controller/RessursSokController.java`, `service/RessursSokService.java` og `dto/`.

The kommune endpoints live in `controller/KommuneController.java`, `service/KommuneService.java` and `repository/KommuneRepository.java` (plain SQL through `JdbcClient`). The request body is `dto/KommuneRequest.java`. Input format is validated in the controller (`@Valid`); "not found" and "already exists" are turned into 404 and 409 in the service.

## API-dokumentasjon (Swagger / OpenAPI)

Dokumentasjonen **genereres fra koden** av [springdoc](https://springdoc.org) (avhengighet i `pom.xml`). Den skrives ikke for hånd.

| Hva | Adresse |
|---|---|
| Swagger UI | <http://localhost:8080/masterdb/swagger-ui.html> |
| OpenAPI (JSON) | <http://localhost:8080/masterdb/api-docs> |
| OpenAPI (YAML) | <http://localhost:8080/masterdb/api-docs.yaml> |

Adressene settes i `application.properties` (`springdoc.api-docs.path` og `springdoc.swagger-ui.path`). Tittel og beskrivelse settes i `config/OpenApiConfig.java`, som også deklarerer API-nøkkelen (`X-API-KEY`) som sikkerhetsskjemaet `apiKey`. I Swagger UI gir **Authorize** deg et felt for nøkkelen.

Den levende dokumentasjonen stemmer alltid med koden etter ombygging og omstart av backend.

### `api/openapi.yaml` er en øyeblikkskopi

Filen [api/openapi.yaml](api/openapi.yaml) er en kopi av spesifikasjonen, til bruk for dem som trenger en fil (for eksempel klientgeneratorer eller deling med eksterne). **Den oppdateres ikke automatisk.** Etter hver endring av endepunkter, parametre eller DTO-er må den hentes på nytt mens backend kjører:

```bash
curl -s http://localhost:8080/masterdb/api-docs.yaml > backend/api/openapi.yaml
```

Husk å committe den oppdaterte filen. Hvis ingen bruker filen, kan den fjernes, og `/masterdb/api-docs` er da eneste kilde.

### Slik dokumenterer du nye endepunkter

- Legg `@Operation(summary = "...", description = "...")` på metoden og `@Tag` på controlleren.
- Bruk `@ParameterObject` på en DTO som tar imot query-parametre. Uten den vises DTO-en som ett parameter i stedet for ett per felt.
- Beskriv felt med `@Schema(description = "...")` i DTO-ene.
- A controller that needs the API key gets `@SecurityRequirement(name = "apiKey")` (the scheme is declared in `OpenApiConfig`). Document the errors springdoc cannot guess (400, 401, 404, 409) with `@ApiResponse`; the success code is picked up from `@ResponseStatus`.

## Testing med Bruno

Forespørslene ligger i `bruno/` i rotmappen, og `baseUrl` settes i `bruno/environments/lokal.bru`. Kjør dem etter endringer i endepunktene. The requests in `bruno/kommune/` need the `apiKey` secret set once in the `lokal` environment (the same value as `MASTERDB_API_KEY`). Run them in order: they create a test kommune (9999), change and delete it, and leave the database as it was.

## Endre sti eller skru av docs

- **Endre stiene:** `@RequestMapping` og `@GetMapping` i controlleren. Oppdater deretter Bruno-filene i `bruno/sok/` og `bruno/kommune/`, andre klienter (frontend) og `api/openapi.yaml`.
- **Skru av Swagger UI i produksjon:** sett `springdoc.swagger-ui.enabled=false` (og eventuelt `springdoc.api-docs.enabled=false`). Swagger UI og spesifikasjonen er ellers åpne for alle som når backend.
