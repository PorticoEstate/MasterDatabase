# Backend (søke-API)

Spring Boot-applikasjon som lar nettsiden søke på tvers av kommuner. Brukeren kan søke på fritekst, filtrere (kommune, lokaletype, aktivitet, fasilitet), eventuelt begrense til et område rundt et punkt, og få treff som bygg-kort og ressursliste. Et treff lenker videre til det lokale bookingsystemet. API-et sjekker aldri tilgjengelighet og booker ingenting.

## Kjøre lokalt

Fra rotmappen:

```bash
docker compose up -d --build backend
```

Backend kjører på <http://localhost:8080>. `--build` er nødvendig etter endringer i kode eller `pom.xml`. Databasen (volumet `postgres_data`) berøres ikke. Ikke bruk `docker compose down -v` med mindre du vil slette databasen.

Databasetilkobling styres av miljøvariablene `DB_URL`, `DB_USER` og `DB_PASSWORD` (se `src/main/resources/application.properties` og `docker-compose.yml`).

## Endepunkter

| Metode | Sti | Beskrivelse |
|---|---|---|
| GET | `/masterdb/search` | Fritekstsøk med filtre. Returnerer både `bygg` og `ressurser`, hver paginert. |
| GET | `/masterdb/search/filter` | Valgene til filterpanelet: kommuner (kommunenr + navn), lokaletyper, aktiviteter og fasiliteter (id + navn). Hentes én gang, ikke per tastetrykk. |

Stiene er engelske, mens query-parametre (`q`, `kommune`, `lokaletype`, `aktivitet`, `fasilitet`, `sorter`, `side`, `storrelse`, `lat`, `lon`, `radiusMeter`) og JSON-felt er norske. Lister kan sendes som `?aktivitet=1&aktivitet=2` eller `?aktivitet=1,2`.

Koden ligger i `controller/RessursSokController.java`, `service/RessursSokService.java` og `dto/`.

## API-dokumentasjon (Swagger / OpenAPI)

Dokumentasjonen **genereres fra koden** av [springdoc](https://springdoc.org) (avhengighet i `pom.xml`). Den skrives ikke for hånd.

| Hva | Adresse |
|---|---|
| Swagger UI | <http://localhost:8080/masterdb/swagger-ui.html> |
| OpenAPI (JSON) | <http://localhost:8080/masterdb/api-docs> |
| OpenAPI (YAML) | <http://localhost:8080/masterdb/api-docs.yaml> |

Adressene settes i `application.properties` (`springdoc.api-docs.path` og `springdoc.swagger-ui.path`). Tittel og beskrivelse settes i `config/OpenApiConfig.java`.

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

## Testing med Bruno

Forespørslene ligger i `bruno/` i rotmappen, og `baseUrl` settes i `bruno/environments/lokal.bru`. Kjør dem etter endringer i endepunktene.

## Endre sti eller skru av docs

- **Endre stiene:** `@RequestMapping` og `@GetMapping` i controlleren. Oppdater deretter Bruno-filene i `bruno/sok/`, andre klienter (frontend) og `api/openapi.yaml`.
- **Skru av Swagger UI i produksjon:** sett `springdoc.swagger-ui.enabled=false` (og eventuelt `springdoc.api-docs.enabled=false`). Swagger UI og spesifikasjonen er ellers åpne for alle som når backend.
