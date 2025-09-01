# MasterDatabase

Masterdatabase som integrerer data fra flere lignende databaseinstanser (lokale databaser med bygnings- og anleggsdata) og supplerer med informasjon fra autoritative registre som matrikkelen og det nasjonale anleggsregisteret.

## API i Docker (OpenAPI-first)

- Kontrakten ligger i `api/openapi.yaml`.
- Swagger UI: <http://localhost:8083/swagger.html>
- Redoc: <http://localhost:8083/redoc.html>

Kjør i Docker:

1. Bygg: `docker compose build`
2. Start: `docker compose up -d`
3. Åpne Swagger eller Redoc på lenkene over.

## Kode-stil

- Bracestil: Allman (åpne klamme på ny linje)
- Innrykk: ekte tabulatorer (Tab) med bredde 4
- Linjeslutt: LF

Konfigurasjon:

- `.editorconfig` styrer grunnleggende innstillinger på tvers av editorer
- `.clang-format` for språk som støttes av clang-format (C/C++/C#/Java/TS/JS)
- `.eslintrc.json` håndhever Allman-braces og tab=4 i JS/TS
- `.vscode/settings.json` sikrer samme oppsett i VS Code og auto-fiks med ESLint
- `.gitattributes` håndhever LF i repo

Tips: Installer ESLint-utvidelsen i VS Code og aktiver «Format on Save» hvis ønskelig.
