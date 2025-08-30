-- Helper views to generate stable IRIs per entity (adjust base URI as needed)

CREATE OR REPLACE VIEW v_iri_municipality AS
SELECT kommune_id AS id,
       'https://data.example.org/kommune/' || kommune_id AS iri
FROM kommune;

CREATE OR REPLACE VIEW v_iri_district AS
SELECT bydel_id AS id,
       'https://data.example.org/bydel/' || bydel_id AS iri,
       kommune_id
FROM bydel;

CREATE OR REPLACE VIEW v_iri_parcel AS
SELECT enhet_id AS id,
       'https://data.example.org/matrikkelenhet/' || enhet_id AS iri
FROM matrikkelenhet;

CREATE OR REPLACE VIEW v_iri_outdoor AS
SELECT uteomraade_id AS id,
       'https://data.example.org/uteomraade/' || uteomraade_id AS iri,
       bydel_id
FROM uteomraade;

CREATE OR REPLACE VIEW v_iri_address AS
SELECT adresse_id AS id,
       'https://data.example.org/adresse/' || adresse_id AS iri,
       bygg_id, bruksenhet_id, uteomraade_id
FROM adresse;

-- Existing views
CREATE OR REPLACE VIEW v_iri_building AS
SELECT bygg_id AS id,
       'https://data.example.org/bygning/' || bygg_id AS iri
FROM bygning;

CREATE OR REPLACE VIEW v_iri_floor AS
SELECT etasje_id AS id,
       'https://data.example.org/etasje/' || etasje_id AS iri,
       bygg_id
FROM etasje;

CREATE OR REPLACE VIEW v_iri_room AS
SELECT rom_id AS id,
       'https://data.example.org/rom/' || rom_id AS iri,
       etasje_id
FROM rom;

CREATE OR REPLACE VIEW v_iri_product AS
SELECT product_id AS id,
       'https://data.example.org/ifc/product/' || product_id AS iri,
       rom_id
FROM ifc_product_location;
