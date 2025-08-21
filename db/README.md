# Database schema (PostgreSQL, no PostGIS required)

This schema models the Norwegian cadastre (Matrikkel) entities extended with buildings and facility management (FDV) details, with addresses placed under buildings (so a building can have multiple addresses/entrances).

Key choices

- Addresses under building: a building (`bygning`) may have multiple addresses/entrances; `adresse.bygg_id` references `bygning`.
- Bydel between kommune and bygning: `bydel` belongs to a `kommune` and groups buildings; `bygning.bydel_id` references `bydel`.
- Bruksenhet under matrikkelenhet: in the official cadastre, units (apartments, rooms, commercial units) are tied to the cadastral unit. `bruksenhet.enhet_id` references `matrikkelenhet`.
- Bygning is decoupled from `matrikkelenhet` in this schema (no FK); linkage can be inferred via addresses or separate association tables if needed later.
- Provenance & authority: core tables include `kilde`, `kilde_ref`, `sist_oppdatert`, `autorativ` to align with the master data precedence rules.
- Spatial (no PostGIS): `bygning.geom_wkt` stores WKT Polygon in EPSG:25833; `adresse.lon`/`lat` with `srid` (default 4258/ETRS89). Can be migrated to PostGIS later.
- Natural keys: `matrikkelenhet` unique key across `(kommune_id, gnr, bnr, fnr, snr)` with COALESCE to handle NULLs; `bygning.bygningsnr` unique.
- Constraints & indexes: checks on numeric IDs, unique indices for typical lookups, GiST for spatial.

How to apply

- Run `schema.sql` on your PostgreSQL database.

Mapping notes

- `matrikkelenhet.enhetstype`: one of `grunneiendom`, `festegrunn`, `jordsameie`, `seksjon`.
- `adresse.adressetype`: `vegadresse` or `matrikkeladresse`.
- `bruksenhet.snr`: section/unit number where applicable.

Next steps

- Add migration tooling (e.g., Flyway or dbmate) and seed scripts.
- Create staging tables for raw Matrikkel pulls and a small rules engine to set `autorativ` per field.
