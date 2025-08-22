-- Kommune
CREATE TABLE IF NOT EXISTS kommune
(
    kommune_id  BIGSERIAL PRIMARY KEY,
    kommunenr   CHAR(4) UNIQUE NOT NULL CHECK (kommunenr ~ '^[0-9]{4}$'),
    navn        TEXT NOT NULL,
    geom_wkt    TEXT,
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
    enhetstype  TEXT NOT NULL CHECK (enhetstype IN ('grunneiendom','festegrunn','seksjon','anleggseiendom')),
    areal_m2    NUMERIC(12,2),
    geom_wkt    TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Ensure uniqueness across nullable festenr/seksjonsnr using an expression index
CREATE UNIQUE INDEX IF NOT EXISTS ux_matrikkelenhet
    ON matrikkelenhet (kommunenr, gardsnr, bruksnr, COALESCE(festenr, 0), COALESCE(seksjonsnr, 0));

-- Bygning
CREATE TABLE IF NOT EXISTS bygning
(
    bygg_id     BIGSERIAL PRIMARY KEY,
    bygningsnr  BIGINT UNIQUE,
    matrikkelenhet_id BIGINT NOT NULL REFERENCES matrikkelenhet(enhet_id) ON DELETE CASCADE,
    bydel_id    BIGINT REFERENCES bydel(bydel_id) ON DELETE SET NULL,
    bygningstype TEXT,
    status      TEXT,
    geom_wkt    TEXT,
    kilde       TEXT,
    kilde_ref   TEXT,
    sist_oppdatert TIMESTAMPTZ,
    autorativ   BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_bygning_bydel
    ON bygning (bydel_id);

CREATE INDEX IF NOT EXISTS ix_bygning_matrikkelenhet
    ON bygning (matrikkelenhet_id);

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
    bygg_id         BIGINT NOT NULL REFERENCES bygning(bygg_id) ON DELETE CASCADE,
    etasje_id       BIGINT REFERENCES etasje(etasje_id) ON DELETE SET NULL,
    snr             INTEGER,
    areal_m2        NUMERIC(10,2),
    brukstype       TEXT,
    kilde           TEXT,
    kilde_ref       TEXT,
    sist_oppdatert  TIMESTAMPTZ,
    autorativ       BOOLEAN DEFAULT FALSE,
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
    gate_id     BIGINT NOT NULL REFERENCES gate(gate_id) ON DELETE CASCADE,
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
    autorativ   BOOLEAN DEFAULT FALSE,
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
    autorativ     BOOLEAN DEFAULT FALSE,
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
    autorativ       BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_adkomstpunkt_uteomraade
    ON adkomstpunkt (uteomraade_id);

CREATE INDEX IF NOT EXISTS ix_adkomstpunkt_gate
    ON adkomstpunkt (gate_id);

CREATE INDEX IF NOT EXISTS ix_adkomstpunkt_lon_lat
    ON adkomstpunkt (lon, lat);
