# API (OpenAPI-first)

Dette kataloget inneholder OpenAPI-kontrakten (`openapi.yaml`).
Kontrakten er "single source of truth" for endepunkter og datamodeller.

## Filstruktur

- `openapi.yaml` – OpenAPI 3.1 spesifikasjonen.

## Neste steg

- Tjen opp `openapi.yaml` via Swagger UI / Redoc i Docker-konteiner.
- Generer server-stubber fra kontrakten og koble til valgt runtime.
