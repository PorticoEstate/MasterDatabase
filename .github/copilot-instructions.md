# Copilot instructions for MasterDatabase

This repo defines a master database that unifies multiple local building/asset databases and enriches them with authoritative registries (Matrikkel, Nasjonalt anleggsregister). See `modellutvikling.md` for domain and data requirements; `README.md` for repo overview.

## Big picture
- Core goal: a single master identity (bygg/anlegg) with source-of-truth rules, provenance, versioning, and synchronization to/from local systems and registries.
- Integrations (from `modellutvikling.md`):
  - Matrikkel: authoritative for property/identity.
  - Lokale driftsdatabaser: operations and technical data.
  - Nasjonalt anleggsregister: structured catalog of installations.
- Spatial search: target a spatial DB (e.g., PostGIS) for map/tematic queries; results link to master building IDs.
- API boundaries:
  - Internal API: sync with underlying databases (push/pull metadata).
  - External API: integration endpoints to registries and external request handling.
- Request routing: forward context-specific requests (leie, skade, drift) to the correct fagsystem; reflect status back in the master UI.
- Data governance: each data element tracks last_updated, source, and authoritative status; rule engine decides precedence per field.

## Conventions in this repo
- Code style: Allman braces + tabs (width 4), LF line endings.
  - `.editorconfig` (tabs=4, LF; YAML uses spaces; C# new-line-before-open-brace=all).
  - `.clang-format` (BreakBeforeBraces: Allman; UseTab: ForIndentation; Tab/IndentWidth=4).
  - `.eslintrc.json` (brace-style: allman; indent: tab) for JS/TS.
  - `.vscode/settings.json` aligns editor behavior; ESLint fixes on save for JS/TS.
  - `.gitattributes` enforces LF in git.
- Language: documentation is in Norwegian; keep comments/docs consistent.

Example (brace + tabs):
```
if (condition)
{
	handle();
}
else
{
	fallback();
}
```

## How to extend this codebase
- Source-of-truth first: model entities and field-level precedence (Matrikkel > others for identity) as explicit rules and metadata.
- Provenance everywhere: ensure new tables/APIs include last_updated, source, authoritative flags as in section 7 of `modellutvikling.md`.
- Spatial first-class: queries that return objects should accept spatial/tematic filters and return master IDs.
- Request routing: new features that create “forespørsler” must propagate to the correct fagsystem and surface status in master.
- Security: design with role-based access, read tracking, and change audit; approvals for modifications when needed.

## Developer workflow (current state)
- There is no build system or runtime yet in this repo. Add language-specific tooling under these constraints:
  - Respect Allman + tabs via the existing configs (.editorconfig, .clang-format, ESLint).
  - YAML must use spaces (2). Makefiles must use real tabs.
- Suggest placing future components by responsibility: `api/` (internal/external), `ingest/` (sync/ETL), `rules/` (precedence engine), `db/` (migrations, PostGIS), `ui/` if applicable. Keep domain docs under root.

## References
- Domain/design: `modellutvikling.md`
- Repo overview + style summary: `README.md`
- Formatting/tooling: `.editorconfig`, `.clang-format`, `.eslintrc.json`, `.vscode/settings.json`, `.gitattributes`
