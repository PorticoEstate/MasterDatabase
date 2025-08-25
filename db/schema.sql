-- Kommune
CREATE TABLE IF NOT EXISTS kommune
(
    kommune_id  BIGSERIAL PRIMARY KEY,
    kommunenr   CHAR(4) UNIQUE NOT NULL CHECK (kommunenr ~ '^[0-9]{4}$'),
    navn        TEXT NOT NULL,
    geom_wkt    TEXT,
    ekstern_id  TEXT,
    kilde       TEXT,
    kilde_ref   TEXT,
    sist_oppdatert TIMESTAMPTZ,
    autoritativ BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Bydel
CREATE TABLE IF NOT EXISTS bydel
(
    bydel_id    BIGSERIAL PRIMARY KEY,
    kommune_id  BIGINT NOT NULL REFERENCES kommune(kommune_id) ON DELETE CASCADE,
    navn        TEXT NOT NULL,
    bydelnr     INTEGER,
    geom_wkt    TEXT,
    ekstern_id  TEXT,
    kilde       TEXT,
    kilde_ref   TEXT,
    sist_oppdatert TIMESTAMPTZ,
    autoritativ BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uniq_bydel_per_kommune UNIQUE (kommune_id, navn)
);

CREATE INDEX IF NOT EXISTS ix_bydel_kommune
    ON bydel (kommune_id);

-- Matrikkelenhet
CREATE TABLE IF NOT EXISTS matrikkelenhet
(
    enhet_id    BIGSERIAL PRIMARY KEY,
    kommunenr   CHAR(4) NOT NULL CHECK (kommunenr ~ '^[0-9]{4}$'),
    gardsnr     INTEGER NOT NULL,
    bruksnr     INTEGER NOT NULL,
    festenr     INTEGER,
    seksjonsnr  INTEGER,
    anleggsnr   INTEGER,
    enhetstype  TEXT NOT NULL CHECK (enhetstype IN ('grunneiendom','festegrunn','seksjon','anleggseiendom')),
    areal_m2    NUMERIC(12,2),
    geom_wkt    TEXT,
    ekstern_id  TEXT,
    kilde       TEXT,
    kilde_ref   TEXT,
    sist_oppdatert TIMESTAMPTZ,
    autoritativ BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Ensure uniqueness across nullable festenr/seksjonsnr using an expression index
CREATE UNIQUE INDEX IF NOT EXISTS ux_matrikkelenhet
    ON matrikkelenhet (
        kommunenr,
        gardsnr,
        bruksnr,
        COALESCE(festenr, 0),
        COALESCE(seksjonsnr, 0),
        COALESCE(anleggsnr, 0)
    );

-- Bygning
CREATE TABLE IF NOT EXISTS bygning
(
    bygg_id     BIGSERIAL PRIMARY KEY,
    bygningsnr  BIGINT UNIQUE,
    bydel_id    BIGINT REFERENCES bydel(bydel_id) ON DELETE SET NULL,
    bygningstype TEXT,
    status      TEXT,
    geom_wkt    TEXT,
    kilde       TEXT,
    kilde_ref   TEXT,
    sist_oppdatert TIMESTAMPTZ,
    autoritativ BOOLEAN DEFAULT FALSE,
    byggeaar    INTEGER,
    antall_etasjer INTEGER,
    bra_m2      NUMERIC(12,2),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_bygning_bydel
    ON bygning (bydel_id);

-- relasjon til matrikkelenhet håndteres via koblingstabellen bygning_matrikkelenhet

-- Fløy
CREATE TABLE IF NOT EXISTS floy
(
    floy_id     BIGSERIAL PRIMARY KEY,
    bygg_id     BIGINT NOT NULL REFERENCES bygning(bygg_id) ON DELETE CASCADE,
    navn        TEXT NOT NULL,
    beskrivelse TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uniq_floy_per_bygg UNIQUE (bygg_id, navn)
);

-- Etasje
CREATE TABLE IF NOT EXISTS etasje
(
    etasje_id   BIGSERIAL PRIMARY KEY,
    bygg_id     BIGINT NOT NULL REFERENCES bygning(bygg_id) ON DELETE CASCADE,
    nummer      TEXT NOT NULL,
    betegnelse  TEXT,
    areal_m2    NUMERIC(10,2),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uniq_etasje_per_bygg UNIQUE (bygg_id, nummer)
);

CREATE INDEX IF NOT EXISTS ix_etasje_bygg
    ON etasje (bygg_id);

-- Bruksenhet
CREATE TABLE IF NOT EXISTS bruksenhet
(
    bruksenhet_id   BIGSERIAL PRIMARY KEY,
    matrikkelenhet_id BIGINT NOT NULL REFERENCES matrikkelenhet(enhet_id) ON DELETE CASCADE,
    bygg_id         BIGINT REFERENCES bygning(bygg_id) ON DELETE CASCADE,
    etasje_id       BIGINT REFERENCES etasje(etasje_id) ON DELETE SET NULL,
    snr             INTEGER,
    bruksenhetsnr   TEXT,
    areal_m2        NUMERIC(10,2),
    brukstype       TEXT,
    kilde           TEXT,
    kilde_ref       TEXT,
    sist_oppdatert  TIMESTAMPTZ,
    autoritativ     BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_bruksenhet_bygg
    ON bruksenhet (bygg_id);

CREATE INDEX IF NOT EXISTS ix_bruksenhet_matrikkelenhet
    ON bruksenhet (matrikkelenhet_id);

-- Rom
CREATE TABLE IF NOT EXISTS rom
(
    rom_id      BIGSERIAL PRIMARY KEY,
    bruksenhet_id BIGINT REFERENCES bruksenhet(bruksenhet_id) ON DELETE CASCADE,
    etasje_id   BIGINT REFERENCES etasje(etasje_id) ON DELETE CASCADE,
    floy_id     BIGINT REFERENCES floy(floy_id) ON DELETE SET NULL,
    nummer      TEXT NOT NULL,
    navn        TEXT,
    areal_m2    NUMERIC(10,2),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uniq_rom_per_bruksenhet UNIQUE (bruksenhet_id, nummer)
);

-- Gate
CREATE TABLE IF NOT EXISTS gate
(
    gate_id     BIGSERIAL PRIMARY KEY,
    kommunenr   CHAR(4) NOT NULL REFERENCES kommune(kommunenr) ON DELETE CASCADE,
    gatenavn    TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uniq_gate_per_kommune UNIQUE (kommunenr, gatenavn)
);

-- Adresse
CREATE TABLE IF NOT EXISTS adresse
(
    adresse_id  BIGSERIAL PRIMARY KEY,
    bygg_id     BIGINT REFERENCES bygning(bygg_id) ON DELETE CASCADE,
    bruksenhet_id BIGINT REFERENCES bruksenhet(bruksenhet_id) ON DELETE CASCADE,
    uteomraade_id BIGINT,
    adressetype TEXT NOT NULL CHECK (adressetype IN ('vegadresse','matrikkeladresse')),
    gate_id     BIGINT REFERENCES gate(gate_id) ON DELETE CASCADE,
    matrikkelenhet_id BIGINT REFERENCES matrikkelenhet(enhet_id) ON DELETE CASCADE,
    husnr       TEXT,
    bokstav     CHAR(1),
    postnummer  CHAR(4) CHECK (postnummer ~ '^[0-9]{4}$'),
    poststed    TEXT,
    lat         DOUBLE PRECISION CHECK (lat IS NULL OR (lat >= -90 AND lat <= 90)),
    lon         DOUBLE PRECISION CHECK (lon IS NULL OR (lon >= -180 AND lon <= 180)),
    srid        INTEGER DEFAULT 4258,
    ekstern_id  TEXT,
    kilde       TEXT,
    kilde_ref   TEXT,
    sist_oppdatert TIMESTAMPTZ,
    autoritativ BOOLEAN DEFAULT FALSE,
    CONSTRAINT chk_adresse_type_gate_parcel
        CHECK (
            (adressetype = 'vegadresse' AND gate_id IS NOT NULL)
            OR (adressetype = 'matrikkeladresse' AND matrikkelenhet_id IS NOT NULL)
        ),
    CONSTRAINT chk_adresse_lon_lat_both
        CHECK ((lon IS NULL AND lat IS NULL) OR (lon IS NOT NULL AND lat IS NOT NULL)),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Uteområde-type (kodeverk)
CREATE TABLE IF NOT EXISTS uteomraade_type
(
    type_id     BIGSERIAL PRIMARY KEY,
    kode        TEXT UNIQUE NOT NULL,
    beskrivelse TEXT
);

INSERT INTO uteomraade_type (kode, beskrivelse)
    VALUES ('park','Parkområde'), ('lekeplass','Lekeplass'),
           ('fotballbane','Fotballbane'), ('idrettsbane','Idrettsanlegg')
    ON CONFLICT DO NOTHING;

-- Uteområde
CREATE TABLE IF NOT EXISTS uteomraade
(
    uteomraade_id BIGSERIAL PRIMARY KEY,
    matrikkelenhet_id BIGINT REFERENCES matrikkelenhet(enhet_id) ON DELETE SET NULL,
    bydel_id      BIGINT REFERENCES bydel(bydel_id) ON DELETE SET NULL,
    type_id       BIGINT NOT NULL REFERENCES uteomraade_type(type_id),
    navn          TEXT NOT NULL,
    areal_m2      NUMERIC(12,2),
    geom_wkt      TEXT,
    kilde         TEXT,
    kilde_ref     TEXT,
    sist_oppdatert TIMESTAMPTZ,
    autoritativ   BOOLEAN DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE adresse
    ADD CONSTRAINT fk_adresse_uteomraade
    FOREIGN KEY (uteomraade_id) REFERENCES uteomraade(uteomraade_id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS ix_uteomraade_type
    ON uteomraade (type_id);

CREATE INDEX IF NOT EXISTS ix_uteomraade_bydel
    ON uteomraade (bydel_id);

-- Adkomstpunkt til uteområde (inngang/port/rampe/parkering)
CREATE TABLE IF NOT EXISTS adkomstpunkt
(
    adkomstpunkt_id BIGSERIAL PRIMARY KEY,
    uteomraade_id   BIGINT NOT NULL REFERENCES uteomraade(uteomraade_id) ON DELETE CASCADE,
    gate_id         BIGINT REFERENCES gate(gate_id) ON DELETE SET NULL,
    type            TEXT NOT NULL CHECK (type IN ('inngang','port','rampe','parkering','annet')),
    beskrivelse     TEXT,
    lon             DOUBLE PRECISION CHECK (lon IS NULL OR (lon >= -180 AND lon <= 180)),
    lat             DOUBLE PRECISION CHECK (lat IS NULL OR (lat >= -90 AND lat <= 90)),
    srid            INTEGER DEFAULT 4258,
    kilde           TEXT,
    kilde_ref       TEXT,
    sist_oppdatert  TIMESTAMPTZ,
    autoritativ     BOOLEAN DEFAULT FALSE,
    CONSTRAINT chk_adkomstpunkt_lon_lat_both
        CHECK ((lon IS NULL AND lat IS NULL) OR (lon IS NOT NULL AND lat IS NOT NULL)),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_adkomstpunkt_uteomraade
    ON adkomstpunkt (uteomraade_id);

CREATE INDEX IF NOT EXISTS ix_adkomstpunkt_gate
    ON adkomstpunkt (gate_id);

CREATE INDEX IF NOT EXISTS ix_adkomstpunkt_lon_lat
    ON adkomstpunkt (lon, lat);

-- M:N kobling mellom bygning og matrikkelenhet
CREATE TABLE IF NOT EXISTS bygning_matrikkelenhet
(
    bygg_id   BIGINT NOT NULL REFERENCES bygning(bygg_id) ON DELETE CASCADE,
    enhet_id  BIGINT NOT NULL REFERENCES matrikkelenhet(enhet_id) ON DELETE CASCADE,
    rolle     TEXT, -- f.eks. 'hovedtomt', 'tilleggsareal'
    dekningsgrad NUMERIC(5,2), -- prosentvis dekning av bygg på enheten, valgfritt
    PRIMARY KEY (bygg_id, enhet_id)
);

CREATE INDEX IF NOT EXISTS ix_bygning_matrikkelenhet_enhet
    ON bygning_matrikkelenhet (enhet_id);

-- Indekser for adresse for effektiv oppslag
CREATE INDEX IF NOT EXISTS ix_adresse_gate
    ON adresse (gate_id);

CREATE INDEX IF NOT EXISTS ix_adresse_matrikkelenhet
    ON adresse (matrikkelenhet_id);

CREATE INDEX IF NOT EXISTS ix_adresse_postnummer
    ON adresse (postnummer);

CREATE INDEX IF NOT EXISTS ix_adresse_lon_lat
    ON adresse (lon, lat);

-- IFC: Type definitions (IfcTypeObject)
CREATE TABLE IF NOT EXISTS ifc_type
(
    type_id        BIGSERIAL PRIMARY KEY,
    ifc_guid       CHAR(22) UNIQUE,
    entity         TEXT NOT NULL,          -- e.g., 'IfcDoor','IfcWall','IfcUnitaryEquipment'
    predefined_type TEXT,
    name           TEXT,
    description    TEXT,
    properties_json JSONB,
    kilde          TEXT,
    kilde_ref      TEXT,
    sist_oppdatert TIMESTAMPTZ,
    autoritativ    BOOLEAN DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_ifc_type_entity
    ON ifc_type (entity);

-- IFC: Product instances (IfcProduct)
CREATE TABLE IF NOT EXISTS ifc_product
(
    product_id     BIGSERIAL PRIMARY KEY,
    ifc_guid       CHAR(22) UNIQUE,
    entity         TEXT NOT NULL,
    predefined_type TEXT,
    name           TEXT,
    tag            TEXT,
    serial_no      TEXT,
    type_id        BIGINT REFERENCES ifc_type(type_id) ON DELETE SET NULL,
    status         TEXT,
    geom_wkt       TEXT,
    lon            DOUBLE PRECISION CHECK (lon IS NULL OR (lon BETWEEN -180 AND 180)),
    lat            DOUBLE PRECISION CHECK (lat IS NULL OR (lat BETWEEN -90 AND 90)),
    srid           INTEGER DEFAULT 4258,
    properties_json JSONB,
    ekstern_id     TEXT, -- external ID from FDV/BAS/ERP/CMMS/etc.
    kilde          TEXT,
    kilde_ref      TEXT,
    sist_oppdatert TIMESTAMPTZ,
    autoritativ    BOOLEAN DEFAULT FALSE,
    CONSTRAINT chk_ifc_product_lon_lat_both
        CHECK ((lon IS NULL AND lat IS NULL) OR (lon IS NOT NULL AND lat IS NOT NULL)),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_ifc_product_ekstern
    ON ifc_product (kilde, ekstern_id);

CREATE INDEX IF NOT EXISTS ix_ifc_product_entity
    ON ifc_product (entity);

-- Location/containment of product within building structure
CREATE TABLE IF NOT EXISTS ifc_product_location
(
    product_id     BIGINT PRIMARY KEY REFERENCES ifc_product(product_id) ON DELETE CASCADE,
    bygg_id        BIGINT REFERENCES bygning(bygg_id) ON DELETE SET NULL,
    floy_id        BIGINT REFERENCES floy(floy_id) ON DELETE SET NULL,
    etasje_id      BIGINT REFERENCES etasje(etasje_id) ON DELETE SET NULL,
    rom_id         BIGINT REFERENCES rom(rom_id) ON DELETE SET NULL,
    uteomraade_id  BIGINT REFERENCES uteomraade(uteomraade_id) ON DELETE SET NULL,
    placement_json JSONB,
    ref_elevation  NUMERIC(10,2),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_ifc_loc_parent
        CHECK (
            bygg_id IS NOT NULL OR floy_id IS NOT NULL OR etasje_id IS NOT NULL OR rom_id IS NOT NULL OR uteomraade_id IS NOT NULL
        )
);

CREATE INDEX IF NOT EXISTS ix_ifc_loc_bygg
    ON ifc_product_location (bygg_id);
CREATE INDEX IF NOT EXISTS ix_ifc_loc_etasje
    ON ifc_product_location (etasje_id);
CREATE INDEX IF NOT EXISTS ix_ifc_loc_rom
    ON ifc_product_location (rom_id);

CREATE INDEX IF NOT EXISTS ix_ifc_loc_uteomraade
    ON ifc_product_location (uteomraade_id);

-- Systems (e.g., HVAC loop, electrical circuit) and membership
CREATE TABLE IF NOT EXISTS ifc_system
(
    system_id      BIGSERIAL PRIMARY KEY,
    name           TEXT NOT NULL,
    system_type    TEXT,
    description    TEXT,
    kilde          TEXT,
    kilde_ref      TEXT,
    sist_oppdatert TIMESTAMPTZ,
    autoritativ    BOOLEAN DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ifc_product_system
(
    product_id     BIGINT NOT NULL REFERENCES ifc_product(product_id) ON DELETE CASCADE,
    system_id      BIGINT NOT NULL REFERENCES ifc_system(system_id) ON DELETE CASCADE,
    rolle          TEXT,
    PRIMARY KEY (product_id, system_id)
);

CREATE INDEX IF NOT EXISTS ix_ifc_product_system_system
    ON ifc_product_system (system_id);

-- Product aggregation (assemblies): parent-child structure
CREATE TABLE IF NOT EXISTS ifc_rel_aggregates
(
    parent_product_id BIGINT NOT NULL REFERENCES ifc_product(product_id) ON DELETE CASCADE,
    child_product_id  BIGINT NOT NULL REFERENCES ifc_product(product_id) ON DELETE CASCADE,
    role              TEXT,
    PRIMARY KEY (parent_product_id, child_product_id)
);

-- External classifications (NS 3451, TFM, Omniclass) mapped to products
CREATE TABLE IF NOT EXISTS classification
(
    class_id       BIGSERIAL PRIMARY KEY,
    scheme         TEXT NOT NULL,
    code           TEXT NOT NULL,
    title          TEXT,
    UNIQUE (scheme, code)
);

CREATE TABLE IF NOT EXISTS product_classification
(
    product_id     BIGINT NOT NULL REFERENCES ifc_product(product_id) ON DELETE CASCADE,
    class_id       BIGINT NOT NULL REFERENCES classification(class_id) ON DELETE CASCADE,
    PRIMARY KEY (product_id, class_id)
);

-- Optional: normalized property sets beyond JSONB
CREATE TABLE IF NOT EXISTS ifc_property_set
(
    pset_id        BIGSERIAL PRIMARY KEY,
    name           TEXT NOT NULL,
    description    TEXT
);

CREATE TABLE IF NOT EXISTS ifc_property
(
    property_id    BIGSERIAL PRIMARY KEY,
    pset_id        BIGINT NOT NULL REFERENCES ifc_property_set(pset_id) ON DELETE CASCADE,
    product_id     BIGINT NOT NULL REFERENCES ifc_product(product_id) ON DELETE CASCADE,
    name           TEXT NOT NULL,
    value_text     TEXT,
    value_num      NUMERIC,
    value_json     JSONB,
    UNIQUE (pset_id, product_id, name)
);

-- Fagsystemer og ruting: systemkatalog, instanser per kommune og ressurslenker

-- Fagsystem (type: booking, FDV, sensor, annet)
CREATE TABLE IF NOT EXISTS fagsystem
(
    fagsystem_id BIGSERIAL PRIMARY KEY,
    navn         TEXT UNIQUE NOT NULL,
    type         TEXT NOT NULL CHECK (type IN ('booking','fdv','sensor','annet')),
    beskrivelse  TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Fagsystem-instans per kommune (én per system/kommune)
CREATE TABLE IF NOT EXISTS fagsystem_instans
(
    instans_id   BIGSERIAL PRIMARY KEY,
    fagsystem_id BIGINT NOT NULL REFERENCES fagsystem(fagsystem_id) ON DELETE CASCADE,
    kommune_id   BIGINT NOT NULL REFERENCES kommune(kommune_id) ON DELETE CASCADE,
    base_url     TEXT NOT NULL,
    konfig_json  JSONB,
    aktiv        BOOLEAN DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uniq_fagsystem_per_kommune UNIQUE (fagsystem_id, kommune_id)
);

CREATE INDEX IF NOT EXISTS ix_fagsystem_instans_fagsystem
    ON fagsystem_instans (fagsystem_id);

CREATE INDEX IF NOT EXISTS ix_fagsystem_instans_kommune
    ON fagsystem_instans (kommune_id);

-- Ressurslenke: kobler master-ressurser til riktig fagsystem-instans for en gitt kontekst
CREATE TABLE IF NOT EXISTS ressurslenke
(
    ressurslenke_id BIGSERIAL PRIMARY KEY,
    kontekst        TEXT NOT NULL CHECK (kontekst IN ('booking','fdv','sensor','annet')),
    fagsystem_instans_id BIGINT NOT NULL REFERENCES fagsystem_instans(instans_id) ON DELETE CASCADE,
    -- Pekere til én og kun én ressurs
    bygg_id        BIGINT REFERENCES bygning(bygg_id) ON DELETE CASCADE,
    bruksenhet_id  BIGINT REFERENCES bruksenhet(bruksenhet_id) ON DELETE CASCADE,
    rom_id         BIGINT REFERENCES rom(rom_id) ON DELETE CASCADE,
    uteomraade_id  BIGINT REFERENCES uteomraade(uteomraade_id) ON DELETE CASCADE,
    product_id     BIGINT REFERENCES ifc_product(product_id) ON DELETE CASCADE,
    -- Ekstern adressat i fagsystemet
    ekstern_id     TEXT NOT NULL,
    ekstern_path   TEXT,
    metadata_json  JSONB,
    aktiv          BOOLEAN DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_ressurslenke_exactly_one
        CHECK (
            (CASE WHEN bygg_id IS NOT NULL THEN 1 ELSE 0 END)
          + (CASE WHEN bruksenhet_id IS NOT NULL THEN 1 ELSE 0 END)
          + (CASE WHEN rom_id IS NOT NULL THEN 1 ELSE 0 END)
          + (CASE WHEN uteomraade_id IS NOT NULL THEN 1 ELSE 0 END)
          + (CASE WHEN product_id IS NOT NULL THEN 1 ELSE 0 END)
          = 1
        )
);

CREATE INDEX IF NOT EXISTS ix_ressurslenke_instans
    ON ressurslenke (fagsystem_instans_id);

CREATE INDEX IF NOT EXISTS ix_ressurslenke_instans_kontekst
    ON ressurslenke (fagsystem_instans_id, kontekst);

CREATE INDEX IF NOT EXISTS ix_ressurslenke_instans_ekstern
    ON ressurslenke (fagsystem_instans_id, ekstern_id);

-- Unike lenker per instans/kontekst for hver ressurs-type
CREATE UNIQUE INDEX IF NOT EXISTS ux_ressurslenke_bygg
    ON ressurslenke (kontekst, fagsystem_instans_id, bygg_id)
    WHERE bygg_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_ressurslenke_bruksenhet
    ON ressurslenke (kontekst, fagsystem_instans_id, bruksenhet_id)
    WHERE bruksenhet_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_ressurslenke_rom
    ON ressurslenke (kontekst, fagsystem_instans_id, rom_id)
    WHERE rom_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_ressurslenke_uteomraade
    ON ressurslenke (kontekst, fagsystem_instans_id, uteomraade_id)
    WHERE uteomraade_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_ressurslenke_product
    ON ressurslenke (kontekst, fagsystem_instans_id, product_id)
    WHERE product_id IS NOT NULL;
