# Input document for AI model development: Integrating a master database with cadastral (Matrikkel) and asset data

---

## 1. Overview

This document summarizes the master data model for buildings/assets and how it integrates with authoritative registries (Matrikkel) and local operational systems. It mirrors the Norwegian document `modellutvikling.md` and only highlights the key concepts and changes introduced in recent iterations.

... [Sections 1–12 mirror the Norwegian version and are intentionally summarized here for brevity in this initial draft. Expand as needed to full parity.] ...

---

## 13. Surfaces and lanes (indoor/outdoor)

This section describes how “surfaces” (courts, areas, lanes/tracks) are modeled consistently for both indoor and outdoor contexts, including classification, composition (merge/split), and routing/booking via resource.

- Core concepts
  - `flate`: represents a court/surface/track. Exactly one location reference must be set: either `rom_id` (indoor) or `uteomraade_id` (outdoor). Geometry can be stored as `geom_wkt` and/or `lon`/`lat` (SRID 4258 by default).
  - Composition: `flate_rel_aggregates` models that multiple child-surfaces can form a parent-surface (e.g., two small courts merged to one large). Optional `dekning_pct` indicates coverage/share.
  - Classification: `classification` + `flate_classification` to bind surfaces to a code scheme (e.g., “football 7-a-side”, “tennis single/double”, “ski trail blue”).
  - Booking/O&M: `ressurs` may reference `flate` (optional 1:1 via unique index). `ressurslenke` with context `booking`/`fdv` routes to the correct external system instance per municipality.

- Anchoring/integration
  - Indoor: `flate.rom_id` anchors to `rom` → `etasje` → `bygning` → `bydel` → `kommune`.
  - Outdoor: `flate.uteomraade_id` anchors to `uteomraade` → `bydel` → `kommune` (optionally to parcel).
  - Routing is performed as in section 11 (resource link and system instance resolution).

- Examples

  Create an outdoor 7-a-side football field, classify it and make it bookable

        -- 1) Create surface (outdoor)
        INSERT INTO flate (navn, type, uteomraade_id, geom_wkt)
        VALUES ('Football 7-a A', 'bane', 42, 'POLYGON((...))')
        RETURNING flate_id;

        -- 2) Classify (local or standard scheme)
        INSERT INTO classification (scheme, code, title)
        VALUES ('SPORT', 'FOOTBALL_7', 'Football 7-a side')
        ON CONFLICT DO NOTHING;

        - `chk_flate_one_location` enforces exactly-one of `rom_id` or `uteomraade_id`.
        - `ux_flate_source_external` enables idempotent upserts per source.
        - `ux_ressurs_flate` enforces an optional 1:1 between surface and resource when the surface is bookable.

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

## 14. Semantic graph as a parallel extension (optional)

This section outlines how to run a semantic knowledge graph in parallel with the relational master database without replacing the Postgres schema. The goal is to provide SPARQL, standardized concepts (ontology), and rules/validation (OWL/SHACL) across sources.

### 14.1 Motivation (why)

- Common semantics across heterogeneous sources (BOT, SOSA/SSN, GeoSPARQL, IFC-OWL + a lightweight local namespace).
- Multi-hop queries (building → floor → room → equipment → system → sensor) without complex JOIN chains.
- Data quality and conformance: SHACL shapes and lightweight inference (OWL RL/EL) for derived relations.
- Identity reconciliation: model and bind multiple external identities to one master identity.
- Loose coupling: evolve concepts and rules without changing the database schema.
- Federation: look up external vocabularies/catalogs via SPARQL SERVICE.

### 14.2 Architecture patterns

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

### 14.3 Integration points with the model

- IRI strategy: stable IRIs per entity (municipality/building/room/ifc_product) based on primary keys.
- Ontology: reuse standard vocabularies and add a "pe:" namespace for project-specific concepts.
- Identity: expose external IDs (e.g., owl:sameAs/skos:exactMatch) aligned with identity links in the DB.
- Provenance: dct:source, prov:wasDerivedFrom, dct:modified for source/authoritativeness/timestamps.
- Geometry: WKT/GeoSPARQL literals initially; PostGIS binding later.
- Routing: model line-of-business system/instance/resource-link in the graph to explain routing decisions.

### 14.4 Minimal first delivery

- A small mapping package (R2RML/RML) for: municipality, cadastral unit, building, floor, room, ifc_product.
- A SQL view that deterministically generates IRIs (e.g., per table).
- 3–5 SPARQL examples (rooms in building X, equipment in room Y, products in system Z).
- A short README to run Ontop locally against Postgres with the mappings.

Suggested structure (later): db/semantic/ with ontology.ttl, mapping/*.ttl, README.md.

### 14.5 Security and access

- Mirror access rules from the master DB. Use named graphs to separate municipality/tenant/domain.
- Do not map fields with restricted access (personal data) to the graph.
- Log queries; consider rate limiting for public endpoints.

### 14.6 Performance and operations

- Cache frequent queries; consider partial materialization for heavy analytics.
- Limit inference to what you need (RL/EL) or run batch inference.
- Establish SHACL shapes for key integrity constraints (building–floor–room chains, classification, etc.).

### 14.7 Getting started (quick)

1. Create a simple IRI view in the database.
2. Write an R2RML mapping for "building" and "room".
3. Start an OBDA endpoint (Ontop) against Postgres and test with SPARQL.
4. Expand gradually with more entities, identities, and provenance.

This adds SPARQL and semantics over the master data without changing the data layer and can be adopted selectively where it brings the most value.

## 15. References and similar projects

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
