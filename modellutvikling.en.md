# Input document for AI model development: Integrating a master database with cadastral (Matrikkel) and asset data

---

## 1. Objectives

Establish a master database that integrates data from multiple similar database instances (local databases with building and installation data) and enriches it with information from authoritative registries such as the Norwegian cadastre (Matrikkelen) and the national installations register.

---

## 2. Data sources

- Matrikkel (Norwegian cadastre): Authoritative for cadastral units, building numbers, addresses, and property data.
- Local operational databases: Installation details, booking status, operational messages, technical data.
- National installations register: Structured catalog of technical installations.
- Line-of-business systems for:
  - Lease of premises
  - Damage/maintenance requests
  - Operations and resource management

---

## 3. Master database functions

- Unique identity for each building/installation via linking tables.
- Data cleansing and validation (incl. versioning and quality control).
- Provenance: track data source and update responsibility.
- Rule engine that decides which data is authoritative per field.

---

## 4. API requirements

### Internal API

- Synchronize with underlying databases.
- Push/pull updated metadata.

### External API

- Integrate with the national installations register and other registries.
- Handle external requests and update protocols.

---

## 5. Contextual request handling

- A request (e.g., lease or damage) must be routed to the correct system based on type and context.
- All requests operate on the same master building ID.
- The system should trigger events in the appropriate application and surface status back in the master database UI.

---

## 6. Map- and theme-based search

- Use a spatial database (e.g., PostGIS).
- Filter on thematic criteria, for example:
  - Population density
  - Landslide risk
  - Radon
- Results link back to the building ID in the master database.

---

## 7. Authoritative rules and data synchronization

- Matrikkel data has highest priority for identity (cadastral and address identity, building numbers).
- The installations register and local databases may have different freshness for different data types.
- Each data component is tagged with:
  - last_updated
  - source
  - authoritative status

---

## 8. Security and access

- Role-based access at the line-of-business system level.
- Read tracking and change audit log.
- Optional approval flows for data modifications.

---

## 9. Cadastral (Matrikkel) data pull

### 9.1 Options overview

- Open and public
  - Kartverket Adresse-API (address search/lookup). Based on Matrikkelen but not full cadastre.
    - Docs: <https://ws.geonorge.no/adresser/>

- Licensed access (full cadastre)
  - Matrikkel Web Services (MWS): SOAP services for cadastral unit, building, address, etc. Requires data license with Kartverket, organizational access, and secure authentication (typically Maskinporten/OAuth2 and/or client certificates). Endpoints/WSDLs are provided upon approval.
  - Matrikkel WMS/WFS: map and feature services for property boundaries and related layers. Also license-gated; useful for visualization and some feature queries.
  - Periodic data extracts: bulk deliveries to licensees (e.g., via Geonorge/FTP) for ingestion.

### 9.2 Access and security prerequisites

- Data license agreement with Kartverket/Geonorge and organization onboarding.
- Authentication and security:
  - Maskinporten client (machine-to-machine OAuth2 with JWT client credentials) for token issuance.
  - In some cases mTLS with client certificates and IP allowlisting.
- Separate test and production endpoints; rate limits and usage logging apply.

Access summary (Kartverket “Electronic access to property data” <https://kartverket.no/api-og-data/eiendomsdata>):

- Access: Data are free but regulated. A lawful basis and an agreement with Kartverket are required to receive data from the cadastre and land register.
- Access levels: Different organization categories receive different scopes. Data processors can receive and forward to controllers with a valid basis.
- Obligations: Technical/organizational controls, pass-through obligations to customers, and compliance with privacy law; violations can result in access being revoked.
- Restrictions: No advertising/marketing use without consent.
- Apply: Submit the application form (<https://kartverket.no/api-og-data/eiendomsdata/soknad-api-tilgang>). Kartverket assesses eligibility.
- Catalog: Services/datasets are listed in the Geonorge catalogs.

### 9.3 Implementation patterns

- Address and coordinate lookups only: use the Adresse-API.
- Full cadastre (parcels/cadastral units, buildings, addresses, boundaries): use MWS and/or WFS.
- Bulk refresh: schedule periodic extracts and reconcile with incremental updates.

Plan for this project (data pull):

1. Legal and access

- Confirm lawful basis and sign the agreement with Kartverket.
- Set up a Maskinporten client and, if required, mTLS/IP allowlisting.

1. Service selection

- Address/quick lookups: Adresse-API (public) for addresses and coordinates.
- Authoritative cadastre: Matrikkel Web Services (SOAP) and/or WFS/WMS (licensed).
- Bulk: periodic extracts via Geonorge/FTP where appropriate.

1. ETL and model alignment

- Ingest to staging, validate/normalize, map to master IDs.
- Field-level precedence: Matrikkel authoritative for identity (gnr/bnr/fnr/snr, building number, addresses).
- Provenance per field (source, last_updated, authoritative).

1. Operations

- Handle rate limits/errors with retry/backoff and idempotent upserts.
- Log and audit access per agreement/regulation.

### 9.4 Mapping to the master data model

- Cadastral unit (matrikkelenhet): municipality number (kommunenummer), GNR (gaardsnummer), BNR (bruksnummer), FNR (festenummer), SNR (seksjonsnummer).
- Address: street/road address (vegadresse) vs cadastral address (matrikkeladresse); include house number, letter, post code/place, and unique identifiers.
- Building: bygningsnummer as a stable identifier for buildings.
- Geometry: boundary polygons and coordinates. Recommended SRIDs: ETRS89 (EPSG:4258) for geographic, ETRS89 / UTM zones (EPSG:25832/25833/25835) for projected coordinates. Store canonical SRID in PostGIS.
- Provenance and precedence: mark source=Matrikkel; carry last_updated as delivered by the registry; set authoritative=true for identity fields, with rule-engine fallbacks otherwise.

### 9.5 Examples

- Adresse-API search (public):

  Example (address search with ETRS89/EPSG:4258 coordinates and 5 results):

  ```bash
  curl "https://ws.geonorge.no/adresser/v1/sok?adresse=Storgata%2010%2C%20Oslo&utkoordsys=4258&treffPerSide=5"
  ```

  Typical fields: matrikkelId (if present), address components, coordinates, and quality codes.

- MWS (licensed): use the WSDLs provided after approval to generate a SOAP client (e.g., with dotnet-svcutil or wsimport). Authenticate via Maskinporten; call services like Matrikkelenhet, Bygg, and Adresse to retrieve authoritative records.

### 9.6 Edge cases and considerations

- Multiple/ambiguous matches; historical/retired units; varying address formats.
- Privacy and usage restrictions for ownership/occupancy data; store only what you’re licensed for.
- Rate limiting and availability; implement retries with backoff and idempotent upserts.
- Synchronization: detect deltas via lastUpdated/version fields where available; avoid full reloads unless necessary.

### 9.7 Operationalization (ETL outline)

- Scheduler triggers pull (Adresse-API for lookups; MWS/WFS for authoritative data; bulk extracts for large updates).
- Normalize and validate fields, map to master IDs, and write to staging tables.
- Apply rule engine for field-level precedence; record provenance (source, last_updated, authoritative).
- Upsert into production tables; emit change events for downstream systems.

---

This document is the English translation of `modellutvikling.md` with an added section (9) detailing options and patterns for pulling cadastral (Matrikkel) data.

---

## 10. IFC modeling of building components and equipment

This model supports importing and managing building components (architecture/structure, HVAC, electrical, etc.) and equipment identified and classified as IFC objects. It is designed to work without PostGIS for now, using WKT and/or lon/lat for geometry.

- Key elements
  - `ifc_type` (IfcTypeObject): type/product families (e.g., IfcDoor, IfcUnitaryEquipment) with optional `ifc_guid` for the type, `entity`, `predefined_type`, and default properties in `properties_json`.
  - `ifc_product` (IfcProduct): instances with `ifc_guid` (GlobalId), `entity`, `predefined_type`, name/tag/serial number, optional `geom_wkt` and/or `lon`/`lat` (with `srid`), and free-form properties in `properties_json`. Can reference `ifc_type`.
  - `ifc_product_location`: placement/containment in the building structure via FKs to `bygning`/`floy`/`etasje`/`rom` (building/wing/floor/room), with `placement_json` for local transform (IfcLocalPlacement). Requirement: at least one of these references must be set.
  - `ifc_system` and `ifc_product_system`: systems (HVAC, ELEC, PLUMB) and product membership in systems.
  - `ifc_rel_aggregates`: parent–child (assembly) relations between products.
  - `classification` and `product_classification`: mapping to external classification schemes (e.g., NS 3451, TFM, OmniClass).
  - Optional normalized property layer: `ifc_property_set` and `ifc_property` for properties that need efficient querying by key (in addition to the JSON on type/instance).

- Relation to the rest of the model
  - Building: IFC products link to `bygning` via `ifc_product_location.bygg_id`, and can be narrowed to `floy`, `etasje`, and/or `rom`.
  - Room/Floor/Wing: enables analysis of components at the right level (room inventory, floor maps, wing-specific overviews) without requiring PostGIS.
  - Cadastral/parcel: linkage primarily via the building/room hierarchy. Where needed, products in outdoor areas can be modeled as separate products and associated to `uteomraade` via address/position (or captured in properties) until a dedicated link is introduced.
  - Provenance: all tables include `kilde` (source), `kilde_ref`, `sist_oppdatert` (last_updated), and `autoritativ` to power the rule engine.

- Geometry and coordinates
  - `geom_wkt` can store simple geometry in WKT. `lon`/`lat` with `srid` can be used for points. Use a consistent SRID (4258 ETRS89 in this model).
  - When PostGIS is introduced, these columns can be migrated/complemented with geometry types and spatial indexes.

- Usage pattern (example)
  1. Parse IFC and create rows in `ifc_type` for each unique `entity`/`predefined_type` combination (store Pset defaults in `properties_json`).
  2. Create `ifc_product` for each instance with `ifc_guid`; reference `ifc_type` where applicable; store Pset values in `properties_json`.
  3. Place instances via `ifc_product_location`, pointing to the appropriate `bygning`/`etasje`/`rom`.
  4. Associate equipment to `ifc_system` (via `ifc_product_system`) and build assemblies in `ifc_rel_aggregates`.
  5. Apply external classifications in `classification`/`product_classification`.

- Benefits
  - Scalable: JSONB for flexible IFC properties, with normalized tables when queries demand it.
  - Interoperable: unique `ifc_guid` makes it straightforward to synchronize with the source model.
  - Connected: location via building/floor/room grounds IFC products in the master data model without a hard PostGIS dependency.

### 10.1 External ID on IFC product (ifc_product.ekstern_id)

`ekstern_id` links products/equipment to external sources (FM/BAS/BMS/ERP/CMMS, sensors, etc.) and supports items not classified in IFC.

- Purpose
  - Stable technical key from the source system (e.g., "fdv:ahu:1").
  - Enables idempotent upserts without an IFC GlobalId.
  - Supports multiple sources by pairing with `kilde` (source).

- Key and index
  - An index exists on `(kilde, ekstern_id)` for fast lookups.
  - Do not require `ekstern_id` to be globally unique; always qualify with `kilde`.

- Matching and upsert strategy (recommended)
  1. Attempt to match on `ifc_guid` when present (primary identity for IFC-derived objects).
  2. If not found, match on `(kilde, ekstern_id)`.
  3. If still not found, insert a new `ifc_product` with a generic `entity` (e.g., "CustomEquipment"), set `ekstern_id` and `kilde`, and store attributes in `properties_json`.
  4. On subsequent imports, update the same row via `(kilde, ekstern_id)`.

- Duplicate merge
  - If the same physical asset ends up as two rows (one with `ifc_guid`, another with `(kilde, ekstern_id)`), merge them: keep the row with `ifc_guid`, copy properties/links, and reassign `(kilde, ekstern_id)` to that row.

- Best practices
  - Do not store personal data in `ekstern_id`; keep it as a technical identifier.
  - Use `classification`/`product_classification` to position non-IFC items in known schemes (NS 3451/TFM), even if `entity` is generic.
  - Provide consistent `entity` and `predefined_type` values for search/filtering, also for non-IFC sources.

### 10.2 Example: non-IFC asset with normalized properties

This example creates an FM asset without an IFC GUID, adds properties in a property set, and upserts them idempotently.

```sql
-- 1) Create a property set (one-time)
INSERT INTO ifc_property_set (name, description)
VALUES ('FDV_Common', 'Properties from FM system');

-- 2) Create the asset (non-IFC) with an external key from the source
INSERT INTO ifc_product (entity, name, tag, properties_json, kilde, ekstern_id)
VALUES (
  'CustomEquipment',
  'Air Handling Unit AHU-1',
  'AHU-1',
  '{"power_kw":5.5, "manufacturer":"X"}',
  'FDV',
  'fdv:ahu:1'
);

-- 3) Normalize selected properties for querying/reporting
INSERT INTO ifc_property (pset_id, product_id, name, value_text, value_num)
SELECT p.pset_id, pr.product_id, v.name, v.value_text, v.value_num
FROM (SELECT pset_id FROM ifc_property_set WHERE name='FDV_Common') p,
   (SELECT product_id FROM ifc_product WHERE kilde='FDV' AND ekstern_id='fdv:ahu:1') pr,
   (VALUES
    ('Manufacturer', 'X', NULL::NUMERIC),
    ('Power_kW', NULL::TEXT, 5.5::NUMERIC)
   ) AS v(name, value_text, value_num)
ON CONFLICT (pset_id, product_id, name)
DO UPDATE SET value_text = EXCLUDED.value_text,
        value_num  = EXCLUDED.value_num;

-- 4) (Optional) Place the asset in the model
INSERT INTO ifc_product_location (product_id, bygg_id, etasje_id, rom_id)
SELECT product_id, 1, NULL, 10
FROM ifc_product WHERE kilde='FDV' AND ekstern_id='fdv:ahu:1';
```

Tips:

- Use `properties_json` for the full Pset content, and mirror only query-critical keys into `ifc_property`.
- Keep names/units consistent (e.g., `Power_kW`).

### 10.3 Example: playground equipment placed on an outdoor area

This shows a playground device placed directly on an outdoor area (outside buildings), with optional coordinates.

```sql
-- 1) Create product (generic or IFC-classified)
INSERT INTO ifc_product (entity, predefined_type, name, properties_json, kilde, ekstern_id, lon, lat)
VALUES (
    'CustomEquipment',           -- or e.g., 'IfcFurnishingElement'
    'PLAY_EQUIPMENT',
    'Play equipment – swing',
    '{"material":"wood","age_6_12":true}',
    'FDV',
    'fdv:play:swing:001',
    10.7461, 59.9127             -- optional position (ETRS89/EPSG:4258)
);

-- 2) Place it on an outdoor area (provide correct uteomraade_id)
INSERT INTO ifc_product_location (product_id, uteomraade_id)
SELECT product_id, 42  -- replace 42 with actual uteomraade_id
FROM ifc_product
WHERE kilde='FDV' AND ekstern_id='fdv:play:swing:001';

-- 3) (Optional) Classify in a custom scheme or known code system
INSERT INTO classification (scheme, code, title)
VALUES ('CUSTOM','PLAY_EQUIPMENT','Play equipment')
ON CONFLICT DO NOTHING;

INSERT INTO product_classification (product_id, class_id)
SELECT p.product_id, c.class_id
FROM ifc_product p, classification c
WHERE p.kilde='FDV' AND p.ekstern_id='fdv:play:swing:001'
  AND c.scheme='CUSTOM' AND c.code='PLAY_EQUIPMENT';
```

Notes:

- `ifc_product_location` supports `uteomraade_id` in addition to building/wing/floor/room. At least one of these must be set.
- Coordinates (`lon`/`lat`) are optional but useful for maps and nearest-access.
