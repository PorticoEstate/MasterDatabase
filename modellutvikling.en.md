# Input document for AI model development: Integrating a master database with cadastral (Matrikkel) and asset data

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

  curl "<https://ws.geonorge.no/adresser/v1/sok?adresse=Storgata%2010%2C%20Oslo&utkoordsys=4258&treffPerSide=5>"

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
        
        -- 1) Create an asset placed outdoors (generic or IFC-classified)
        INSERT INTO ifc_product (entity, predefined_type, name, properties_json, kilde, ekstern_id, lon, lat)
        VALUES (
            'CustomEquipment',           -- or e.g. 'IfcFurnishingElement'
            'PLAY_EQUIPMENT',
            'Playground – swing',
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

Notes:

- `ifc_product_location` supports `uteomraade_id` in addition to building/wing/floor/room. At least one of these must be set.
- Coordinates (`lon`/`lat`) are optional but useful for maps and nearest-access.

## 11. Provenance and context-aware routing to line-of-business systems

This master DB combines authoritative registries (Matrikkel) with local per-municipality systems (e.g., “Aktiv kommune” for booking) and FDV/CMMS. The user should not select a municipality; the system auto-routes based on the chosen resource and context.

- Provenance (source, external ID, authoritative)
  - Core tables carry: source (kilde), source ref, last updated, authoritative flag.
  - External IDs (ekstern_id) + source identify records for idempotent upserts.
  - Precedence: Matrikkel is authoritative for property identity; other systems for domain-specific fields.

- Municipality context
  - Buildings anchor via district → municipality.
  - Outdoor areas anchor via district → municipality (optionally via parcel).
  - Addresses and parcels carry municipality codes, enabling deterministic mapping.

- LOB system linking (concepts)
  - System: logical system with a type (booking, FDV, sensors, …).
  - System instance: one per municipality (base URL, credentials, metadata).
  - Resource link: maps a master resource (building/room/outdoor area/product) to the correct system instance with an external ID for a given context (booking/FDV).
  - Classification: optional for filtering/routing.

- Routing flow (booking example)
  1. User picks a resource (e.g., sports hall) in the master UI.
  2. Determine municipality via building/district or address/parcel.
  3. Look up the Resource link for context=booking → fetch system instance (Aktiv kommune for that municipality) and external_id.
  4. Redirect or call the API using the instance base URL and the external_id.
  5. Mirror status/ack back into the master UI via the same mapping.

- FDV/other sources (components/equipment)
  - ifc_product supports IFC and non-IFC assets (ifc_guid optional) with external_id+source.
  - ifc_product_location anchors assets to building/floor/room or outdoor area.
  - Properties live in properties_json and, when needed, normalized in ifc_property_set/ifc_property.
  - For FDV routing: the Resource link points the product to the correct FDV instance per municipality using the FDV external_id.

- Privacy and access
  - Do not store personal data in external_id.
  - Routing happens at system/resource level; access and audit are enforced in both master and downstream systems.

Practical recommendation

- Introduce small reference tables (out of scope in this file) for: system, system_instance (per municipality), and resource_link (resource_type, resource_id, context, system_instance_id, external_id).
- Keep upserts idempotent: maintain unique (resource, context) mapping per system instance and avoid duplicates.

## 12. Resources and resource pools (non location-bound)

This section describes how we handle resources that are not permanently tied to a physical place (equipment in storage, mobile devices, people, services), organize them into pools, and route them to the correct line-of-business system with the same context-aware mechanism used for location-bound objects.

- Purpose
  - Model resources (equipment, personnel, services) independent of buildings/rooms.
  - Group resources into named pools (e.g., “Custodian Team Central”, “Loan equipment – School A”).
  - Routing: reuse the context-aware mechanism at the resource level.

- Tables (sketch, see `db/schema.sql`)
  - ressurs: type (equipment|person|service|other), either linked to ifc_product or identified by (kilde, ekstern_id); metadata_json; provenance fields; partial UNIQUE on (kilde, ekstern_id).
  - ressurspool: named collection per municipality; UNIQUE (kommune_id, navn); type (booking|staffing|equipment|other).
  - ressurspool_medlem: M:N pool–resource with validity window (gyldig_fra/gyldig_til).
  - ressurslenke: adds ressurs_id; exactly-one-reference CHECK; uniqueness per (instans_id, context, ekstern_id) and per (context, instans_id, ressurs_id).

- Interaction with routing
  - Reuse fagsystem and fagsystem_instans.
  - For a resource request, look up ressurslenke by (instans_id, context, ressurs_id) to get the external ID in the correct instance.
  - Overlapping IDs across instances are safe due to scoped uniqueness.

- Examples
  - Create a resource (person from HR):

        INSERT INTO ressurs (type, navn, kilde, ekstern_id, sist_oppdatert, autoritativ)
        VALUES ('person', 'Ola Normann', 'hr', 'EMP-12345', NOW(), true);

  - Create a pool and add a member:

        INSERT INTO ressurspool (kommune_id, navn, type)
        VALUES (42, 'Vaktmesterteam Sentrum', 'staffing')
        RETURNING id;

        INSERT INTO ressurspool_medlem (pool_id, ressurs_id, gyldig_fra)
        VALUES (<pool_id>, <ressurs_id>, CURRENT_DATE);

  - Resolve routing for booking:
    1) Instance: SELECT i.id, i.base_url FROM fagsystem_instans i JOIN fagsystem f ON f.id=i.fagsystem_id WHERE f.type='booking' AND i.kommune_id=<kommune_id>;
    2) External ID: SELECT ekstern_id FROM ressurslenke WHERE context='booking' AND instans_id=<instans_id> AND ressurs_id=<ressurs_id>;

  - Useful query: active pool members today:

        SELECT r.*
        FROM ressurspool_medlem m
        JOIN ressurs r ON r.id = m.ressurs_id
        WHERE m.pool_id = <pool_id>
          AND (m.gyldig_fra IS NULL OR m.gyldig_fra <= CURRENT_DATE)
          AND (m.gyldig_til IS NULL OR m.gyldig_til >= CURRENT_DATE);

---

## 13. Semantic graph as a parallel extension (optional)

This section outlines how to run a semantic knowledge graph in parallel with the relational master database without replacing the Postgres schema. The goal is to provide SPARQL, standardized concepts (ontology), and rules/validation (OWL/SHACL) across sources.

### 13.1 Motivation (why)

- Common semantics across heterogeneous sources (BOT, SOSA/SSN, GeoSPARQL, IFC-OWL + a lightweight local namespace).
- Multi-hop queries (building → floor → room → equipment → system → sensor) without complex JOIN chains.
- Data quality and conformance: SHACL shapes and lightweight inference (OWL RL/EL) for derived relations.
- Identity reconciliation: model and bind multiple external identities to one master identity.
- Loose coupling: evolve concepts and rules without changing the database schema.
- Federation: look up external vocabularies/catalogs via SPARQL SERVICE.

### 13.2 Architecture patterns

Two complementary options:

1. Virtual graph (OBDA/R2RML) over Postgres
   - Tools: Ontop or Apache Jena. Mappings express how tables/views appear as RDF at query-time.
   - Pros: no ETL/duplication; fast to adopt; SPARQL directly from master data.
   - Trade-offs: very heavy graph queries may be slow; needs indexing and mindful query design.

2. Materialized graph (triplestore) with ongoing updates
   - Tools: GraphDB, Fuseki, Blazegraph/Neptune, etc.
   - Sync: CDC (Debezium) or batch exports from Postgres.
   - Pros: performance for complex graphs/inference; dedicated caching layer.
   - Trade-offs: operational/ETL complexity and duplication to manage (provenance/versioning).

Recommendation: start virtual (OBDA); materialize selectively when needed.

### 13.3 Integration points with the model

- IRI strategy: stable IRIs per entity (municipality/building/room/ifc_product) based on primary keys.
- Ontology: reuse standard vocabularies and add a "pe:" namespace for project-specific concepts.
- Identity: expose external IDs (e.g., owl:sameAs/skos:exactMatch) aligned with identity links in the DB.
- Provenance: dct:source, prov:wasDerivedFrom, dct:modified for source/authoritativeness/timestamps.
- Geometry: WKT/GeoSPARQL literals initially; PostGIS binding later.
- Routing: model line-of-business system/instance/resource-link in the graph to explain routing decisions.

### 13.4 Minimal first delivery

- A small mapping package (R2RML/RML) for: municipality, cadastral unit, building, floor, room, ifc_product.
- A SQL view that deterministically generates IRIs (e.g., per table).
- 3–5 SPARQL examples (rooms in building X, equipment in room Y, products in system Z).
- A short README to run Ontop locally against Postgres with the mappings.

Suggested structure (later): db/semantic/ with ontology.ttl, mapping/*.ttl, README.md.

### 13.5 Security and access

- Mirror access rules from the master DB. Use named graphs to separate municipality/tenant/domain.
- Do not map fields with restricted access (personal data) to the graph.
- Log queries; consider rate limiting for public endpoints.

### 13.6 Performance and operations

- Cache frequent queries; consider partial materialization for heavy analytics.
- Limit inference to what you need (RL/EL) or run batch inference.
- Establish SHACL shapes for key integrity constraints (building–floor–room chains, classification, etc.).

### 13.7 Getting started (quick)

1. Create a simple IRI view in the database.
2. Write an R2RML mapping for "building" and "room".
3. Start an OBDA endpoint (Ontop) against Postgres and test with SPARQL.
4. Expand gradually with more entities, identities, and provenance.

This adds SPARQL and semantics over the master data without changing the data layer and can be adopted selectively where it brings the most value.

## 13. References and similar projects

- City of Helsinki – semantic city model (CityGML/CityJSON) integrated with municipal data: <https://www.hel.fi/3d/>
- Amsterdam DataPunt – knowledge graph/open data: <https://data.amsterdam.nl/>
- Ordnance Survey Linked Data (UK) – buildings/addresses with SPARQL: <https://www.ordnancesurvey.co.uk/products/os-open-linked-identifiers>
- Netherlands Kadaster BAG Linked Data – property/address (BAG/BGT): <https://bag.basisregistraties.overheid.nl/>
- UK National Digital Twin (CDBB/IMF) – framework for shared information models: <https://www.cdbb.cam.ac.uk/what-we-did/national-digital-twin-programme>
- buildingSMART bSDD – semantic dictionary/code sets for AEC assets: <https://bsdd.buildingsmart.org/>
- IFC-OWL / IfcWoD – IFC as RDF for integration with sensors/FM: <https://technical.buildingsmart.org/standards/ifc/ifc-formats/ifcowl/>
- FIWARE Smart Data Models – open semantic models (buildings/IoT/assets): <https://smartdatamodels.org/>
- OGC standards – GeoSPARQL, CityGML/CityJSON: <https://www.ogc.org/standards/>
- Norway – GeoNorge/Kartverket (Cadastre/Addresses): <https://www.geonorge.no/> and <https://kartverket.no/>
