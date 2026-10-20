# API (OpenAPI-first)

Dette kataloget inneholder OpenAPI-kontrakten (`openapi.yaml`).
Kontrakten er "single source of truth" for endepunkter og datamodeller.

## Filstruktur

- `openapi.yaml` – OpenAPI 3.1 spesifikasjonen.

## Implementasjon

Ligger i `../backend` (Spring Boot/Java) - se `backend/README.md`. Den
levende Swagger UI-en (generert fra koden, ikke denne filen direkte) serveres
av appen selv på `/swagger-ui.html` når den kjører.
