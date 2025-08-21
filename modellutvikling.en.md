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
