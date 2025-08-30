# Semantic graph (parallel) – quick start

This folder contains a minimal setup to expose a virtual RDF graph over the existing Postgres schema using OBDA (Ontop). It also includes a lightweight ontology and R2RML mappings for core entities.

Contents

- ontology.ttl – lightweight project ontology (namespaces and a few classes/properties)
- mapping/core-mapping.ttl – R2RML mappings for building/floor/room/ifc_product and admin layers
- sql/iri_views.sql – helper SQL to create stable IRIs as views (optional)
- shapes/core-shapes.ttl – SHACL shapes for basic integrity checks
- queries/examples.sparql – sample SPARQL queries (building/room/product + parcel/address/outdoor)
- queries/constructs.sparql – sample CONSTRUCTs for subgraphs

## Graph overview (conceptual)

- Municipality (pe:Municipality)
  - Districts (pe:District)
    - Buildings (bot:Building)
      - Floors (bot:Storey)
        - Rooms (bot:Space)
          - Products (pe:Product)
    - Outdoor areas (pe:OutdoorArea)
  - Parcels (pe:Parcel) — linked from addresses
- Addresses (pe:Address) — may link to building/unit/outdoor and parcel

## Motivation

- SPARQL multi-hop queries across building → floor → room → equipment.
- Standard vocabularies (BOT/SOSA/SSN/GeoSPARQL/IFC-OWL) plus a local namespace.
- Data quality via SHACL and explicit provenance.

## Prerequisites

- Postgres with the schema from `db/schema.sql` applied.
- Docker (recommended) to run Ontop.

## 1) Create IRI views (optional but helpful)

Apply `sql/iri_views.sql` to your DB.

## 2) Run Ontop (virtual graph)

Example command:

```bash
# Optional: set these environment variables or inline the values
export DB_URL="jdbc:postgresql://localhost:5432/masterdb"
export DB_USER="postgres"
export DB_PASSWORD="postgres"

docker run --rm -p 8080:8080 \
  -v $(pwd):/opt/ontop/mapping \
  ontop/ontop endpoint \
  --db-url=${DB_URL} \
  --db-user=${DB_USER} \
  --db-password=${DB_PASSWORD} \
  --mapping=/opt/ontop/mapping/mapping/core-mapping.ttl
```

Ontop will expose a SPARQL endpoint at <http://localhost:8080/sparql>.

## 3) Try SPARQL queries

See `queries/examples.sparql` for ready-to-run examples, including parcels, addresses and outdoor areas.

## 4) Validate with SHACL (optional)

Use a SHACL validator (e.g., TopBraid SHACL API, pySHACL) against `shapes/core-shapes.ttl` and the RDF graph. With OBDA, export a snapshot (CONSTRUCT) or test on a materialized subset.

### Export a subgraph and validate with pySHACL

- Run a CONSTRUCT (e.g., first in `queries/constructs.sparql`) and save as TTL.
- Validate locally with pySHACL:

```bash
pyshacl -s db/semantic/shapes/core-shapes.ttl -m -i rdfs -f human -a -j \
  -t your_construct_output.ttl
```

## Notes

- The mapping is illustrative; adapt columns and joins to your actual data population level.
- For performance-heavy use cases, consider materializing into a triplestore later.
