-- Masterdatabase for kommunale lokaler og anlegg
-- PostgreSQL 18, ingen PostGIS-avhengighet (geometri som WKT + lon/lat)
--
-- Modellen er et definisjons- og rutingslag:
--   * Matrikkelen er autoritativ for eiendoms- og bygningsidentitet.
--   * Kommunenes fagsystemer (Aktiv kommune m.fl.) eier booking, kalender og sanntid.
--   * Master eier identitet, plassering, klassifisering og rutinglenker.
--
-- Se db/schema_documentation.md for begrepsforklaring og lastestrategi.


-- =============================================================================
-- 0. Felles hjelpefunksjoner
-- =============================================================================

-- updated_at ble aldri vedlikeholdt i tidligere versjoner av skjemaet; kolonnene
-- fikk bare sin DEFAULT ved INSERT. Triggeren nederst i filen fikser det.
CREATE OR REPLACE FUNCTION sett_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;


-- =============================================================================
-- 1. Administrativ inndeling
-- =============================================================================

CREATE TABLE IF NOT EXISTS kommune
(
    kommune_id     BIGSERIAL PRIMARY KEY,
    kommunenr      CHAR(4) UNIQUE NOT NULL CHECK (kommunenr ~ '^[0-9]{4}$'),
    navn           TEXT NOT NULL,
    fylkesnr       CHAR(2) CHECK (fylkesnr IS NULL OR fylkesnr ~ '^[0-9]{2}$'),
    fylkesnavn     TEXT,
    geom_wkt       TEXT,
    ekstern_id     TEXT,
    kilde          TEXT,
    kilde_ref      TEXT,
    sist_oppdatert TIMESTAMPTZ,
    autoritativ    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bydel
(
    bydel_id       BIGSERIAL PRIMARY KEY,
    kommune_id     BIGINT NOT NULL REFERENCES kommune(kommune_id) ON DELETE CASCADE,
    navn           TEXT NOT NULL,
    bydelnr        INTEGER,
    geom_wkt       TEXT,
    ekstern_id     TEXT,
    kilde          TEXT,
    kilde_ref      TEXT,
    sist_oppdatert TIMESTAMPTZ,
    autoritativ    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uniq_bydel_per_kommune UNIQUE (kommune_id, navn)
);

CREATE INDEX IF NOT EXISTS ix_bydel_kommune ON bydel (kommune_id);


-- =============================================================================
-- 2. Matrikkel (autoritativ eiendomsidentitet)
-- =============================================================================

CREATE TABLE IF NOT EXISTS matrikkelenhet
(
    enhet_id       BIGSERIAL PRIMARY KEY,
    kommunenr      CHAR(4) NOT NULL CHECK (kommunenr ~ '^[0-9]{4}$'),
    gardsnr        INTEGER NOT NULL,
    bruksnr        INTEGER NOT NULL,
    festenr        INTEGER,
    seksjonsnr     INTEGER,
    anleggsnr      INTEGER,
    enhetstype     TEXT NOT NULL CHECK (enhetstype IN
                       ('grunneiendom','festegrunn','seksjon','anleggseiendom','jordsameie')),
    areal_m2       NUMERIC(12,2),
    geom_wkt       TEXT,
    ekstern_id     TEXT,
    kilde          TEXT,
    kilde_ref      TEXT,
    sist_oppdatert TIMESTAMPTZ,
    autoritativ    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- COALESCE fordi festenr/seksjonsnr/anleggsnr er NULL for vanlige grunneiendommer,
-- og NULL-verdier ellers ville gjort unikhetsregelen virkningsløs.
CREATE UNIQUE INDEX IF NOT EXISTS ux_matrikkelenhet
    ON matrikkelenhet (
        kommunenr, gardsnr, bruksnr,
        COALESCE(festenr, 0), COALESCE(seksjonsnr, 0), COALESCE(anleggsnr, 0)
    );

CREATE UNIQUE INDEX IF NOT EXISTS ux_matrikkelenhet_kilde
    ON matrikkelenhet (kilde, ekstern_id)
    WHERE kilde IS NOT NULL AND ekstern_id IS NOT NULL;


-- =============================================================================
-- 3. Bygning og bygningsstruktur
-- =============================================================================

-- kommune_id er NOT NULL og redundant med bydel -> kommune. Det er bevisst:
-- bydel finnes ikke i de fleste kommuner, og tverrkommunalt søk må alltid
-- kunne filtrere og gruppere på kommune uten å gå via en nullbar kjede.
CREATE TABLE IF NOT EXISTS bygning
(
    bygg_id        BIGSERIAL PRIMARY KEY,
    kommune_id     BIGINT NOT NULL REFERENCES kommune(kommune_id) ON DELETE CASCADE,
    bydel_id       BIGINT REFERENCES bydel(bydel_id) ON DELETE SET NULL,
    navn           TEXT,
    bygningsnr     BIGINT,
    bygningstype   TEXT,
    bygningstypekode TEXT,
    status         TEXT,
    byggeaar       INTEGER CHECK (byggeaar IS NULL OR byggeaar BETWEEN 800 AND 2200),
    antall_etasjer INTEGER CHECK (antall_etasjer IS NULL OR antall_etasjer > 0),
    bra_m2         NUMERIC(12,2) CHECK (bra_m2 IS NULL OR bra_m2 >= 0),
    geom_wkt       TEXT,
    lon            DOUBLE PRECISION CHECK (lon IS NULL OR lon BETWEEN -180 AND 180),
    lat            DOUBLE PRECISION CHECK (lat IS NULL OR lat BETWEEN -90 AND 90),
    srid           INTEGER NOT NULL DEFAULT 4258,
    hjemmeside     TEXT,
    -- Kun funksjonelle kontaktpunkter. Navngitte kontaktpersoner (tilsyn_name m.fl.
    -- i Aktiv kommune) er personopplysninger og lastes ikke inn.
    epost          TEXT,
    telefon        TEXT,
    apningstid_tekst TEXT,
    ekstern_id     TEXT,
    kilde          TEXT,
    kilde_ref      TEXT,
    sist_oppdatert TIMESTAMPTZ,
    autoritativ    BOOLEAN NOT NULL DEFAULT FALSE,
    aktiv          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_bygning_lon_lat_both
        CHECK ((lon IS NULL AND lat IS NULL) OR (lon IS NOT NULL AND lat IS NOT NULL)),
    CONSTRAINT uq_bygning_bygg_kommune UNIQUE (bygg_id, kommune_id)
);

-- bygningsnr er matrikkelens nøkkel og globalt unik der den finnes, men mangler
-- for bygg som kun er kjent fra et fagsystem. Partiell indeks tillater begge.
CREATE UNIQUE INDEX IF NOT EXISTS ux_bygning_bygningsnr
    ON bygning (bygningsnr)
    WHERE bygningsnr IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_bygning_kilde
    ON bygning (kilde, ekstern_id)
    WHERE kilde IS NOT NULL AND ekstern_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_bygning_kommune ON bygning (kommune_id);
CREATE INDEX IF NOT EXISTS ix_bygning_bydel ON bygning (bydel_id);
CREATE INDEX IF NOT EXISTS ix_bygning_lon_lat ON bygning (lon, lat);
CREATE INDEX IF NOT EXISTS ix_bygning_navn_lower ON bygning (lower(navn));

CREATE TABLE IF NOT EXISTS bygning_matrikkelenhet
(
    bygg_id      BIGINT NOT NULL REFERENCES bygning(bygg_id) ON DELETE CASCADE,
    enhet_id     BIGINT NOT NULL REFERENCES matrikkelenhet(enhet_id) ON DELETE CASCADE,
    rolle        TEXT,
    dekningsgrad NUMERIC(5,2) CHECK (dekningsgrad IS NULL OR dekningsgrad BETWEEN 0 AND 100),
    PRIMARY KEY (bygg_id, enhet_id)
);

CREATE INDEX IF NOT EXISTS ix_bygning_matrikkelenhet_enhet
    ON bygning_matrikkelenhet (enhet_id);

CREATE TABLE IF NOT EXISTS floy
(
    floy_id        BIGSERIAL PRIMARY KEY,
    bygg_id        BIGINT NOT NULL REFERENCES bygning(bygg_id) ON DELETE CASCADE,
    navn           TEXT NOT NULL,
    beskrivelse    TEXT,
    ekstern_id     TEXT,
    kilde          TEXT,
    kilde_ref      TEXT,
    sist_oppdatert TIMESTAMPTZ,
    autoritativ    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uniq_floy_per_bygg UNIQUE (bygg_id, navn),
    CONSTRAINT uq_floy_bygg UNIQUE (floy_id, bygg_id)
);

CREATE TABLE IF NOT EXISTS etasje
(
    etasje_id      BIGSERIAL PRIMARY KEY,
    bygg_id        BIGINT NOT NULL REFERENCES bygning(bygg_id) ON DELETE CASCADE,
    nummer         TEXT NOT NULL,
    betegnelse     TEXT,
    areal_m2       NUMERIC(10,2) CHECK (areal_m2 IS NULL OR areal_m2 >= 0),
    ekstern_id     TEXT,
    kilde          TEXT,
    kilde_ref      TEXT,
    sist_oppdatert TIMESTAMPTZ,
    autoritativ    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uniq_etasje_per_bygg UNIQUE (bygg_id, nummer),
    CONSTRAINT uq_etasje_bygg UNIQUE (etasje_id, bygg_id)
);

CREATE INDEX IF NOT EXISTS ix_etasje_bygg ON etasje (bygg_id);

CREATE TABLE IF NOT EXISTS bruksenhet
(
    bruksenhet_id     BIGSERIAL PRIMARY KEY,
    matrikkelenhet_id BIGINT NOT NULL REFERENCES matrikkelenhet(enhet_id) ON DELETE CASCADE,
    bygg_id           BIGINT REFERENCES bygning(bygg_id) ON DELETE CASCADE,
    etasje_id         BIGINT REFERENCES etasje(etasje_id) ON DELETE SET NULL,
    snr               INTEGER,
    bruksenhetsnr     TEXT,
    areal_m2          NUMERIC(10,2) CHECK (areal_m2 IS NULL OR areal_m2 >= 0),
    brukstype         TEXT,
    ekstern_id        TEXT,
    kilde             TEXT,
    kilde_ref         TEXT,
    sist_oppdatert    TIMESTAMPTZ,
    autoritativ       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_bruksenhet_kilde
    ON bruksenhet (kilde, ekstern_id)
    WHERE kilde IS NOT NULL AND ekstern_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_bruksenhet_bygg ON bruksenhet (bygg_id);
CREATE INDEX IF NOT EXISTS ix_bruksenhet_matrikkelenhet ON bruksenhet (matrikkelenhet_id);

-- bygg_id er NOT NULL slik at et rom aldri kan bli foreldreløst. Sammensatte
-- FK-er nedenfor bruker uq_rom_bygg for å garantere at rom, etasje og fløy som
-- refereres fra samme ressurs faktisk hører til samme bygning.
CREATE TABLE IF NOT EXISTS rom
(
    rom_id         BIGSERIAL PRIMARY KEY,
    bygg_id        BIGINT NOT NULL REFERENCES bygning(bygg_id) ON DELETE CASCADE,
    etasje_id      BIGINT,
    floy_id        BIGINT,
    bruksenhet_id  BIGINT REFERENCES bruksenhet(bruksenhet_id) ON DELETE SET NULL,
    nummer         TEXT,
    navn           TEXT,
    areal_m2       NUMERIC(10,2) CHECK (areal_m2 IS NULL OR areal_m2 >= 0),
    ekstern_id     TEXT,
    kilde          TEXT,
    kilde_ref      TEXT,
    sist_oppdatert TIMESTAMPTZ,
    autoritativ    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_rom_bygg UNIQUE (rom_id, bygg_id),
    CONSTRAINT fk_rom_etasje FOREIGN KEY (etasje_id, bygg_id)
        REFERENCES etasje (etasje_id, bygg_id) ON DELETE SET NULL,
    CONSTRAINT fk_rom_floy FOREIGN KEY (floy_id, bygg_id)
        REFERENCES floy (floy_id, bygg_id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_rom_kilde
    ON rom (kilde, ekstern_id)
    WHERE kilde IS NOT NULL AND ekstern_id IS NOT NULL;

-- Romnummer er valgfritt (fagsystemene har det sjelden), men skal være unikt
-- innenfor bygget når det finnes.
CREATE UNIQUE INDEX IF NOT EXISTS ux_rom_nummer_per_bygg
    ON rom (bygg_id, nummer)
    WHERE nummer IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_rom_bygg ON rom (bygg_id);
CREATE INDEX IF NOT EXISTS ix_rom_etasje ON rom (etasje_id);


-- =============================================================================
-- 4. Adresse
-- =============================================================================

CREATE TABLE IF NOT EXISTS gate
(
    gate_id        BIGSERIAL PRIMARY KEY,
    kommune_id     BIGINT NOT NULL REFERENCES kommune(kommune_id) ON DELETE CASCADE,
    gatenavn       TEXT NOT NULL,
    adressekode    INTEGER,
    ekstern_id     TEXT,
    kilde          TEXT,
    kilde_ref      TEXT,
    sist_oppdatert TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uniq_gate_per_kommune UNIQUE (kommune_id, gatenavn)
);

CREATE TABLE IF NOT EXISTS adresse
(
    adresse_id        BIGSERIAL PRIMARY KEY,
    bygg_id           BIGINT REFERENCES bygning(bygg_id) ON DELETE CASCADE,
    bruksenhet_id     BIGINT REFERENCES bruksenhet(bruksenhet_id) ON DELETE CASCADE,
    uteomraade_id     BIGINT,
    adressetype       TEXT NOT NULL CHECK (adressetype IN ('vegadresse','matrikkeladresse')),
    gate_id           BIGINT REFERENCES gate(gate_id) ON DELETE CASCADE,
    matrikkelenhet_id BIGINT REFERENCES matrikkelenhet(enhet_id) ON DELETE CASCADE,
    adressetekst      TEXT,
    husnr             TEXT,
    bokstav           CHAR(1),
    postnummer        CHAR(4) CHECK (postnummer IS NULL OR postnummer ~ '^[0-9]{4}$'),
    poststed          TEXT,
    lat               DOUBLE PRECISION CHECK (lat IS NULL OR lat BETWEEN -90 AND 90),
    lon               DOUBLE PRECISION CHECK (lon IS NULL OR lon BETWEEN -180 AND 180),
    srid              INTEGER NOT NULL DEFAULT 4258,
    -- Skiller geokodede treff fra autoritative matrikkelkoordinater, slik at en
    -- senere matrikkelimport trygt kan overskrive et usikkert geokodingsresultat.
    geokoding_status  TEXT NOT NULL DEFAULT 'ukjent'
                          CHECK (geokoding_status IN ('ukjent','matrikkel','geokodet','manuell','feilet')),
    er_hovedadresse   BOOLEAN NOT NULL DEFAULT FALSE,
    ekstern_id        TEXT,
    kilde             TEXT,
    kilde_ref         TEXT,
    sist_oppdatert    TIMESTAMPTZ,
    autoritativ       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_adresse_type_gate_parcel
        CHECK (
            (adressetype = 'vegadresse' AND gate_id IS NOT NULL)
            OR (adressetype = 'matrikkeladresse' AND matrikkelenhet_id IS NOT NULL)
        ),
    CONSTRAINT chk_adresse_lon_lat_both
        CHECK ((lon IS NULL AND lat IS NULL) OR (lon IS NOT NULL AND lat IS NOT NULL)),
    CONSTRAINT chk_adresse_ett_subjekt
        CHECK (
            (CASE WHEN bygg_id IS NOT NULL THEN 1 ELSE 0 END)
          + (CASE WHEN bruksenhet_id IS NOT NULL THEN 1 ELSE 0 END)
          + (CASE WHEN uteomraade_id IS NOT NULL THEN 1 ELSE 0 END)
          <= 1
        )
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_adresse_kilde
    ON adresse (kilde, ekstern_id)
    WHERE kilde IS NOT NULL AND ekstern_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_adresse_hovedadresse_bygg
    ON adresse (bygg_id)
    WHERE bygg_id IS NOT NULL AND er_hovedadresse;

CREATE INDEX IF NOT EXISTS ix_adresse_bygg ON adresse (bygg_id);
CREATE INDEX IF NOT EXISTS ix_adresse_gate ON adresse (gate_id);
CREATE INDEX IF NOT EXISTS ix_adresse_matrikkelenhet ON adresse (matrikkelenhet_id);
CREATE INDEX IF NOT EXISTS ix_adresse_postnummer ON adresse (postnummer);
CREATE INDEX IF NOT EXISTS ix_adresse_lon_lat ON adresse (lon, lat);


-- =============================================================================
-- 5. Uteområde
-- =============================================================================

CREATE TABLE IF NOT EXISTS uteomraade_type
(
    type_id     BIGSERIAL PRIMARY KEY,
    kode        TEXT UNIQUE NOT NULL,
    beskrivelse TEXT
);

INSERT INTO uteomraade_type (kode, beskrivelse) VALUES
    ('park','Parkområde'),
    ('lekeplass','Lekeplass'),
    ('idrettsanlegg','Idrettsanlegg utendørs'),
    ('naermiljoeanlegg','Nærmiljøanlegg'),
    ('friluftsomraade','Friluftsområde'),
    ('torg','Torg og møteplass'),
    ('badeplass','Badeplass'),
    ('annet','Annet uteområde')
ON CONFLICT (kode) DO NOTHING;

CREATE TABLE IF NOT EXISTS uteomraade
(
    uteomraade_id     BIGSERIAL PRIMARY KEY,
    kommune_id        BIGINT NOT NULL REFERENCES kommune(kommune_id) ON DELETE CASCADE,
    bydel_id          BIGINT REFERENCES bydel(bydel_id) ON DELETE SET NULL,
    matrikkelenhet_id BIGINT REFERENCES matrikkelenhet(enhet_id) ON DELETE SET NULL,
    type_id           BIGINT NOT NULL REFERENCES uteomraade_type(type_id),
    navn              TEXT NOT NULL,
    areal_m2          NUMERIC(12,2) CHECK (areal_m2 IS NULL OR areal_m2 >= 0),
    geom_wkt          TEXT,
    lon               DOUBLE PRECISION CHECK (lon IS NULL OR lon BETWEEN -180 AND 180),
    lat               DOUBLE PRECISION CHECK (lat IS NULL OR lat BETWEEN -90 AND 90),
    srid              INTEGER NOT NULL DEFAULT 4258,
    ekstern_id        TEXT,
    kilde             TEXT,
    kilde_ref         TEXT,
    sist_oppdatert    TIMESTAMPTZ,
    autoritativ       BOOLEAN NOT NULL DEFAULT FALSE,
    aktiv             BOOLEAN NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_uteomraade_lon_lat_both
        CHECK ((lon IS NULL AND lat IS NULL) OR (lon IS NOT NULL AND lat IS NOT NULL)),
    CONSTRAINT uq_uteomraade_kommune UNIQUE (uteomraade_id, kommune_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_uteomraade_kilde
    ON uteomraade (kilde, ekstern_id)
    WHERE kilde IS NOT NULL AND ekstern_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_uteomraade_kommune ON uteomraade (kommune_id);
CREATE INDEX IF NOT EXISTS ix_uteomraade_bydel ON uteomraade (bydel_id);
CREATE INDEX IF NOT EXISTS ix_uteomraade_type ON uteomraade (type_id);
CREATE INDEX IF NOT EXISTS ix_uteomraade_lon_lat ON uteomraade (lon, lat);

ALTER TABLE adresse
    DROP CONSTRAINT IF EXISTS fk_adresse_uteomraade;
ALTER TABLE adresse
    ADD CONSTRAINT fk_adresse_uteomraade
    FOREIGN KEY (uteomraade_id) REFERENCES uteomraade(uteomraade_id) ON DELETE CASCADE;

CREATE TABLE IF NOT EXISTS adkomstpunkt
(
    adkomstpunkt_id BIGSERIAL PRIMARY KEY,
    uteomraade_id   BIGINT REFERENCES uteomraade(uteomraade_id) ON DELETE CASCADE,
    bygg_id         BIGINT REFERENCES bygning(bygg_id) ON DELETE CASCADE,
    gate_id         BIGINT REFERENCES gate(gate_id) ON DELETE SET NULL,
    type            TEXT NOT NULL CHECK (type IN
                        ('inngang','port','rampe','parkering','hc_parkering','holdeplass','annet')),
    beskrivelse     TEXT,
    universell_utforming BOOLEAN,
    lon             DOUBLE PRECISION CHECK (lon IS NULL OR lon BETWEEN -180 AND 180),
    lat             DOUBLE PRECISION CHECK (lat IS NULL OR lat BETWEEN -90 AND 90),
    srid            INTEGER NOT NULL DEFAULT 4258,
    kilde           TEXT,
    kilde_ref       TEXT,
    ekstern_id      TEXT,
    sist_oppdatert  TIMESTAMPTZ,
    autoritativ     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_adkomstpunkt_lon_lat_both
        CHECK ((lon IS NULL AND lat IS NULL) OR (lon IS NOT NULL AND lat IS NOT NULL)),
    CONSTRAINT chk_adkomstpunkt_ett_subjekt
        CHECK (
            (CASE WHEN uteomraade_id IS NOT NULL THEN 1 ELSE 0 END)
          + (CASE WHEN bygg_id IS NOT NULL THEN 1 ELSE 0 END)
          = 1
        )
);

CREATE INDEX IF NOT EXISTS ix_adkomstpunkt_uteomraade ON adkomstpunkt (uteomraade_id);
CREATE INDEX IF NOT EXISTS ix_adkomstpunkt_bygg ON adkomstpunkt (bygg_id);
CREATE INDEX IF NOT EXISTS ix_adkomstpunkt_lon_lat ON adkomstpunkt (lon, lat);


-- =============================================================================
-- 6. Flate (bane, trasé, løype)
-- =============================================================================

-- Flaten er den fysiske spilleflaten. Bookbarheten ligger i ressurs, slik at to
-- halve baner kan bookes hver for seg eller slås sammen til én.
CREATE TABLE IF NOT EXISTS flate
(
    flate_id       BIGSERIAL PRIMARY KEY,
    navn           TEXT,
    type           TEXT NOT NULL CHECK (type IN ('bane','flate','trase','loype','annet')),
    rom_id         BIGINT REFERENCES rom(rom_id) ON DELETE CASCADE,
    uteomraade_id  BIGINT REFERENCES uteomraade(uteomraade_id) ON DELETE CASCADE,
    bygg_id        BIGINT REFERENCES bygning(bygg_id) ON DELETE CASCADE,
    dekke          TEXT,
    lengde_m       NUMERIC(10,2) CHECK (lengde_m IS NULL OR lengde_m >= 0),
    bredde_m       NUMERIC(10,2) CHECK (bredde_m IS NULL OR bredde_m >= 0),
    areal_m2       NUMERIC(12,2) CHECK (areal_m2 IS NULL OR areal_m2 >= 0),
    geom_wkt       TEXT,
    lon            DOUBLE PRECISION CHECK (lon IS NULL OR lon BETWEEN -180 AND 180),
    lat            DOUBLE PRECISION CHECK (lat IS NULL OR lat BETWEEN -90 AND 90),
    srid           INTEGER NOT NULL DEFAULT 4258,
    ekstern_id     TEXT,
    kilde          TEXT,
    kilde_ref      TEXT,
    sist_oppdatert TIMESTAMPTZ,
    autoritativ    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Minst én forankring, ikke nøyaktig én: en innendørs bane hører både til et
    -- rom og til bygget, og en hall uten registrerte rom må kunne festes i bygget.
    CONSTRAINT chk_flate_forankring
        CHECK (rom_id IS NOT NULL OR uteomraade_id IS NOT NULL OR bygg_id IS NOT NULL),
    CONSTRAINT chk_flate_inne_ute
        CHECK (NOT (uteomraade_id IS NOT NULL AND (rom_id IS NOT NULL OR bygg_id IS NOT NULL))),
    CONSTRAINT chk_flate_lon_lat_both
        CHECK ((lon IS NULL AND lat IS NULL) OR (lon IS NOT NULL AND lat IS NOT NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_flate_kilde
    ON flate (kilde, ekstern_id)
    WHERE kilde IS NOT NULL AND ekstern_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_flate_rom ON flate (rom_id);
CREATE INDEX IF NOT EXISTS ix_flate_uteomraade ON flate (uteomraade_id);
CREATE INDEX IF NOT EXISTS ix_flate_bygg ON flate (bygg_id);
CREATE INDEX IF NOT EXISTS ix_flate_lon_lat ON flate (lon, lat);

CREATE TABLE IF NOT EXISTS flate_rel_aggregates
(
    parent_flate_id BIGINT NOT NULL REFERENCES flate(flate_id) ON DELETE CASCADE,
    child_flate_id  BIGINT NOT NULL REFERENCES flate(flate_id) ON DELETE CASCADE,
    rolle           TEXT,
    dekning_pct     NUMERIC(5,2) CHECK (dekning_pct IS NULL OR dekning_pct BETWEEN 0 AND 100),
    PRIMARY KEY (parent_flate_id, child_flate_id),
    CONSTRAINT chk_flate_rel_ikke_selv CHECK (parent_flate_id <> child_flate_id)
);

CREATE INDEX IF NOT EXISTS ix_flate_rel_child ON flate_rel_aggregates (child_flate_id);


-- =============================================================================
-- 7. Kanoniske søkefasetter
--
-- Dette er kjernen i tverrkommunalt søk. Hver kommune har sitt eget lokale
-- kodeverk der samme ID betyr forskjellige ting (ID 13 = "Overnatting" i Bergen,
-- "Skateanlegg" i Stavanger). Master eier derfor ett kuratert kodeverk, og de
-- lokale kodene kartlegges inn mot det i seksjon 8.
-- =============================================================================

CREATE TABLE IF NOT EXISTS lokaletype
(
    lokaletype_id  BIGSERIAL PRIMARY KEY,
    kode           TEXT UNIQUE NOT NULL,
    navn           TEXT NOT NULL,
    parent_id      BIGINT REFERENCES lokaletype(lokaletype_id) ON DELETE SET NULL,
    beskrivelse    TEXT,
    innendors      BOOLEAN,
    aktiv          BOOLEAN NOT NULL DEFAULT TRUE,
    sortering      INTEGER,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_lokaletype_ikke_egen_forelder CHECK (parent_id IS NULL OR parent_id <> lokaletype_id)
);

CREATE INDEX IF NOT EXISTS ix_lokaletype_parent ON lokaletype (parent_id);

CREATE TABLE IF NOT EXISTS aktivitet
(
    aktivitet_id   BIGSERIAL PRIMARY KEY,
    kode           TEXT UNIQUE NOT NULL,
    navn           TEXT NOT NULL,
    parent_id      BIGINT REFERENCES aktivitet(aktivitet_id) ON DELETE SET NULL,
    beskrivelse    TEXT,
    aktiv          BOOLEAN NOT NULL DEFAULT TRUE,
    sortering      INTEGER,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_aktivitet_ikke_egen_forelder CHECK (parent_id IS NULL OR parent_id <> aktivitet_id)
);

CREATE INDEX IF NOT EXISTS ix_aktivitet_parent ON aktivitet (parent_id);

CREATE TABLE IF NOT EXISTS fasilitet
(
    fasilitet_id   BIGSERIAL PRIMARY KEY,
    kode           TEXT UNIQUE NOT NULL,
    navn           TEXT NOT NULL,
    gruppe         TEXT NOT NULL CHECK (gruppe IN
                       ('tilgjengelighet','sanitaer','teknisk','kjokken','sport','moblering','uteareal','annet')),
    beskrivelse    TEXT,
    aktiv          BOOLEAN NOT NULL DEFAULT TRUE,
    sortering      INTEGER,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_fasilitet_gruppe ON fasilitet (gruppe);

-- Eksterne standardkodeverk (NS 3451, TFM, Omniclass, bSDD) holdes atskilt fra
-- de kuraterte søkefasettene fordi de har andre eiere og andre livsløp.
CREATE TABLE IF NOT EXISTS classification
(
    class_id       BIGSERIAL PRIMARY KEY,
    scheme         TEXT NOT NULL,
    code           TEXT NOT NULL,
    title          TEXT,
    beskrivelse    TEXT,
    parent_class_id BIGINT REFERENCES classification(class_id) ON DELETE SET NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (scheme, code)
);


-- =============================================================================
-- 8. Fagsystem, instanser og lokale kildekoder
-- =============================================================================

CREATE TABLE IF NOT EXISTS fagsystem
(
    fagsystem_id BIGSERIAL PRIMARY KEY,
    navn         TEXT UNIQUE NOT NULL,
    type         TEXT NOT NULL CHECK (type IN ('booking','fdv','sensor','matrikkel','annet')),
    leverandor   TEXT,
    beskrivelse  TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fagsystem_instans
(
    instans_id   BIGSERIAL PRIMARY KEY,
    fagsystem_id BIGINT NOT NULL REFERENCES fagsystem(fagsystem_id) ON DELETE CASCADE,
    kommune_id   BIGINT NOT NULL REFERENCES kommune(kommune_id) ON DELETE CASCADE,
    -- Kildenøkkelen som brukes i kilde-kolonnene ellers i basen, f.eks.
    -- 'aktiv-kommune:bergen'. Gjør at eksterne IDer fra ulike instanser aldri
    -- kolliderer, siden de lokale heltalls-IDene overlapper på tvers av kommuner.
    kildenokkel  TEXT UNIQUE NOT NULL,
    base_url     TEXT NOT NULL,
    konfig_json  JSONB,
    aktiv        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uniq_fagsystem_per_kommune UNIQUE (fagsystem_id, kommune_id)
);

CREATE INDEX IF NOT EXISTS ix_fagsystem_instans_fagsystem ON fagsystem_instans (fagsystem_id);
CREATE INDEX IF NOT EXISTS ix_fagsystem_instans_kommune ON fagsystem_instans (kommune_id);

-- Rå lokal kode slik den står i kildesystemet. Beholdes uendret for sporbarhet;
-- all normalisering skjer i kildekode_mapping.
CREATE TABLE IF NOT EXISTS kildekode
(
    kildekode_id   BIGSERIAL PRIMARY KEY,
    instans_id     BIGINT NOT NULL REFERENCES fagsystem_instans(instans_id) ON DELETE CASCADE,
    kodetype       TEXT NOT NULL CHECK (kodetype IN ('lokaletype','aktivitet','fasilitet')),
    kode           TEXT NOT NULL,
    navn           TEXT NOT NULL,
    parent_kode    TEXT,
    aktiv          BOOLEAN NOT NULL DEFAULT TRUE,
    forste_sett    TIMESTAMPTZ NOT NULL DEFAULT now(),
    sist_sett      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uniq_kildekode UNIQUE (instans_id, kodetype, kode)
);

CREATE INDEX IF NOT EXISTS ix_kildekode_kodetype ON kildekode (kodetype);
CREATE INDEX IF NOT EXISTS ix_kildekode_navn_lower ON kildekode (lower(navn));

-- Kartleggingen er en menneskelig kvalitetssikret påstand, ikke en beregning.
-- Derfor bærer den status, konfidens og hvem som bestemte den.
-- status = 'ikke_relevant' brukes for kildekoder som ikke er lokaletyper i det
-- hele tatt (kildedata inneholder f.eks. "Stengt", "Fiktivt rom", "Streaming"
-- og stedsnavn som "Judaberg innbyggertorg" i kategorilisten).
CREATE TABLE IF NOT EXISTS kildekode_mapping
(
    mapping_id     BIGSERIAL PRIMARY KEY,
    kildekode_id   BIGINT NOT NULL REFERENCES kildekode(kildekode_id) ON DELETE CASCADE,
    lokaletype_id  BIGINT REFERENCES lokaletype(lokaletype_id) ON DELETE CASCADE,
    aktivitet_id   BIGINT REFERENCES aktivitet(aktivitet_id) ON DELETE CASCADE,
    fasilitet_id   BIGINT REFERENCES fasilitet(fasilitet_id) ON DELETE CASCADE,
    status         TEXT NOT NULL DEFAULT 'foreslatt'
                       CHECK (status IN ('foreslatt','godkjent','avvist','ikke_relevant')),
    konfidens      NUMERIC(3,2) CHECK (konfidens IS NULL OR konfidens BETWEEN 0 AND 1),
    kartlagt_av    TEXT,
    kartlagt_at    TIMESTAMPTZ,
    merknad        TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_kildekode_mapping_ett_mal
        CHECK (
            (CASE WHEN lokaletype_id IS NOT NULL THEN 1 ELSE 0 END)
          + (CASE WHEN aktivitet_id IS NOT NULL THEN 1 ELSE 0 END)
          + (CASE WHEN fasilitet_id IS NOT NULL THEN 1 ELSE 0 END)
          = CASE WHEN status IN ('avvist','ikke_relevant') THEN 0 ELSE 1 END
        )
);

CREATE INDEX IF NOT EXISTS ix_kildekode_mapping_kildekode ON kildekode_mapping (kildekode_id);
CREATE INDEX IF NOT EXISTS ix_kildekode_mapping_lokaletype ON kildekode_mapping (lokaletype_id);
CREATE INDEX IF NOT EXISTS ix_kildekode_mapping_status ON kildekode_mapping (status);


-- =============================================================================
-- 9. Ressurs: den søkbare og bookbare enheten
--
-- Denne tabellen erstatter rollen ifc_product + ifc_product_location hadde:
-- en identifiserbar ting som er plassert et sted i bygnings- eller uteområde-
-- strukturen. Plasseringen ligger inline for å unngå join i søk, og de
-- sammensatte fremmednøklene garanterer at rom/etasje/fløy hører til bygget.
-- =============================================================================

CREATE TABLE IF NOT EXISTS ressurs
(
    ressurs_id     BIGSERIAL PRIMARY KEY,
    kommune_id     BIGINT NOT NULL REFERENCES kommune(kommune_id) ON DELETE CASCADE,
    type           TEXT NOT NULL CHECK (type IN ('lokale','anlegg','bane','utstyr','tjeneste','annet')),
    navn           TEXT NOT NULL,
    lokaletype_id  BIGINT REFERENCES lokaletype(lokaletype_id) ON DELETE SET NULL,

    kapasitet      INTEGER CHECK (kapasitet IS NULL OR kapasitet >= 0),
    -- Kildesystemene har kapasitet utfylt på under 1 % av ressursene, og noen
    -- koder den i stedet som fasilitet. Opphavet må derfor følge verdien.
    kapasitet_kilde TEXT CHECK (kapasitet_kilde IS NULL OR kapasitet_kilde IN
                        ('kilde','utledet','manuell')),
    areal_m2       NUMERIC(10,2) CHECK (areal_m2 IS NULL OR areal_m2 >= 0),

    beskrivelse    TEXT,
    beskrivelse_nn TEXT,
    beskrivelse_en TEXT,
    apningstid_tekst TEXT,

    bygg_id        BIGINT,
    floy_id        BIGINT,
    etasje_id      BIGINT,
    rom_id         BIGINT,
    uteomraade_id  BIGINT REFERENCES uteomraade(uteomraade_id) ON DELETE SET NULL,
    flate_id       BIGINT REFERENCES flate(flate_id) ON DELETE SET NULL,

    aktiv          BOOLEAN NOT NULL DEFAULT TRUE,
    bookbar        BOOLEAN NOT NULL DEFAULT TRUE,
    skjult         BOOLEAN NOT NULL DEFAULT FALSE,

    metadata_json  JSONB,
    ekstern_id     TEXT NOT NULL,
    kilde          TEXT NOT NULL,
    kilde_ref      TEXT,
    sist_oppdatert TIMESTAMPTZ,
    autoritativ    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    sokevektor     tsvector GENERATED ALWAYS AS (
                       to_tsvector('norwegian',
                           coalesce(navn,'') || ' ' ||
                           coalesce(beskrivelse,'') || ' ' ||
                           coalesce(beskrivelse_nn,''))
                   ) STORED,

    CONSTRAINT fk_ressurs_bygg FOREIGN KEY (bygg_id, kommune_id)
        REFERENCES bygning (bygg_id, kommune_id) ON DELETE SET NULL,
    CONSTRAINT fk_ressurs_rom FOREIGN KEY (rom_id, bygg_id)
        REFERENCES rom (rom_id, bygg_id) ON DELETE SET NULL,
    CONSTRAINT fk_ressurs_etasje FOREIGN KEY (etasje_id, bygg_id)
        REFERENCES etasje (etasje_id, bygg_id) ON DELETE SET NULL,
    CONSTRAINT fk_ressurs_floy FOREIGN KEY (floy_id, bygg_id)
        REFERENCES floy (floy_id, bygg_id) ON DELETE SET NULL,

    -- Stedbundne ressurser må være lokaliserbare. Utstyr og tjenester kan være
    -- mobile og trenger ingen forankring.
    CONSTRAINT chk_ressurs_plassering
        CHECK (
            type IN ('utstyr','tjeneste','annet')
            OR bygg_id IS NOT NULL
            OR uteomraade_id IS NOT NULL
            OR flate_id IS NOT NULL
        ),
    -- Rom, etasje og fløy er meningsløse uten bygget de ligger i.
    CONSTRAINT chk_ressurs_innedel_krever_bygg
        CHECK (
            (rom_id IS NULL AND etasje_id IS NULL AND floy_id IS NULL)
            OR bygg_id IS NOT NULL
        ),
    CONSTRAINT chk_ressurs_inne_eller_ute
        CHECK (NOT (bygg_id IS NOT NULL AND uteomraade_id IS NOT NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_ressurs_kilde
    ON ressurs (kilde, ekstern_id);

CREATE UNIQUE INDEX IF NOT EXISTS ux_ressurs_flate
    ON ressurs (flate_id)
    WHERE flate_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_ressurs_kommune ON ressurs (kommune_id);
CREATE INDEX IF NOT EXISTS ix_ressurs_lokaletype ON ressurs (lokaletype_id);
CREATE INDEX IF NOT EXISTS ix_ressurs_bygg ON ressurs (bygg_id);
CREATE INDEX IF NOT EXISTS ix_ressurs_uteomraade ON ressurs (uteomraade_id);
CREATE INDEX IF NOT EXISTS ix_ressurs_sokevektor ON ressurs USING GIN (sokevektor);

-- Dekkende indeks for hovedsøket: aktive, bookbare, synlige ressurser filtrert
-- på type og kommune.
CREATE INDEX IF NOT EXISTS ix_ressurs_sok
    ON ressurs (lokaletype_id, kommune_id, kapasitet)
    WHERE aktiv AND bookbar AND NOT skjult;

CREATE TABLE IF NOT EXISTS ressurs_aktivitet
(
    ressurs_id   BIGINT NOT NULL REFERENCES ressurs(ressurs_id) ON DELETE CASCADE,
    aktivitet_id BIGINT NOT NULL REFERENCES aktivitet(aktivitet_id) ON DELETE CASCADE,
    PRIMARY KEY (ressurs_id, aktivitet_id)
);

CREATE INDEX IF NOT EXISTS ix_ressurs_aktivitet_aktivitet ON ressurs_aktivitet (aktivitet_id);

CREATE TABLE IF NOT EXISTS ressurs_fasilitet
(
    ressurs_id   BIGINT NOT NULL REFERENCES ressurs(ressurs_id) ON DELETE CASCADE,
    fasilitet_id BIGINT NOT NULL REFERENCES fasilitet(fasilitet_id) ON DELETE CASCADE,
    antall       INTEGER CHECK (antall IS NULL OR antall > 0),
    merknad      TEXT,
    PRIMARY KEY (ressurs_id, fasilitet_id)
);

CREATE INDEX IF NOT EXISTS ix_ressurs_fasilitet_fasilitet ON ressurs_fasilitet (fasilitet_id);

CREATE TABLE IF NOT EXISTS ressurs_classification
(
    ressurs_id BIGINT NOT NULL REFERENCES ressurs(ressurs_id) ON DELETE CASCADE,
    class_id   BIGINT NOT NULL REFERENCES classification(class_id) ON DELETE CASCADE,
    PRIMARY KEY (ressurs_id, class_id)
);

CREATE TABLE IF NOT EXISTS flate_classification
(
    flate_id BIGINT NOT NULL REFERENCES flate(flate_id) ON DELETE CASCADE,
    class_id BIGINT NOT NULL REFERENCES classification(class_id) ON DELETE CASCADE,
    PRIMARY KEY (flate_id, class_id)
);

-- Sammenstilling: en storsal som kan deles i tre, eller en hall som rommer to
-- baner. Erstatter ifc_rel_aggregates for bookbare enheter.
CREATE TABLE IF NOT EXISTS ressurs_rel_aggregates
(
    parent_ressurs_id BIGINT NOT NULL REFERENCES ressurs(ressurs_id) ON DELETE CASCADE,
    child_ressurs_id  BIGINT NOT NULL REFERENCES ressurs(ressurs_id) ON DELETE CASCADE,
    rolle             TEXT,
    -- Når TRUE kan ikke forelder og barn bookes samtidig. Master håndhever det
    -- ikke; flagget finnes for at fagsystemet og søket skal kunne vise det.
    utelukker_hverandre BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (parent_ressurs_id, child_ressurs_id),
    CONSTRAINT chk_ressurs_rel_ikke_selv CHECK (parent_ressurs_id <> child_ressurs_id)
);

CREATE INDEX IF NOT EXISTS ix_ressurs_rel_child ON ressurs_rel_aggregates (child_ressurs_id);


-- =============================================================================
-- 10. Ressurspool
-- =============================================================================

CREATE TABLE IF NOT EXISTS ressurspool
(
    pool_id       BIGSERIAL PRIMARY KEY,
    navn          TEXT NOT NULL,
    type          TEXT NOT NULL CHECK (type IN ('booking','utstyr','drift','annet')),
    kommune_id    BIGINT REFERENCES kommune(kommune_id) ON DELETE SET NULL,
    beskrivelse   TEXT,
    metadata_json JSONB,
    aktiv         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uniq_pool_per_scope UNIQUE (kommune_id, navn)
);

CREATE INDEX IF NOT EXISTS ix_pool_kommune ON ressurspool (kommune_id);

CREATE TABLE IF NOT EXISTS ressurspool_medlem
(
    pool_id    BIGINT NOT NULL REFERENCES ressurspool(pool_id) ON DELETE CASCADE,
    ressurs_id BIGINT NOT NULL REFERENCES ressurs(ressurs_id) ON DELETE CASCADE,
    rolle      TEXT,
    prioritet  INTEGER,
    gyldig_fra TIMESTAMPTZ,
    gyldig_til TIMESTAMPTZ,
    merknad    TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (pool_id, ressurs_id),
    CONSTRAINT chk_medlem_interval
        CHECK (gyldig_til IS NULL OR gyldig_fra IS NULL OR gyldig_til > gyldig_fra)
);

CREATE INDEX IF NOT EXISTS ix_pool_medlem_ressurs ON ressurspool_medlem (ressurs_id);
CREATE INDEX IF NOT EXISTS ix_pool_medlem_gyldighet ON ressurspool_medlem (gyldig_fra, gyldig_til);


-- =============================================================================
-- 11. Ruting til fagsystem
-- =============================================================================

CREATE TABLE IF NOT EXISTS ressurslenke
(
    ressurslenke_id BIGSERIAL PRIMARY KEY,
    kontekst        TEXT NOT NULL CHECK (kontekst IN ('booking','fdv','sensor','annet')),
    fagsystem_instans_id BIGINT NOT NULL REFERENCES fagsystem_instans(instans_id) ON DELETE CASCADE,
    bygg_id        BIGINT REFERENCES bygning(bygg_id) ON DELETE CASCADE,
    bruksenhet_id  BIGINT REFERENCES bruksenhet(bruksenhet_id) ON DELETE CASCADE,
    rom_id         BIGINT REFERENCES rom(rom_id) ON DELETE CASCADE,
    uteomraade_id  BIGINT REFERENCES uteomraade(uteomraade_id) ON DELETE CASCADE,
    flate_id       BIGINT REFERENCES flate(flate_id) ON DELETE CASCADE,
    ressurs_id     BIGINT REFERENCES ressurs(ressurs_id) ON DELETE CASCADE,
    -- Aldri personopplysninger i ekstern_id.
    ekstern_id     TEXT NOT NULL,
    ekstern_path   TEXT,
    metadata_json  JSONB,
    aktiv          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_ressurslenke_exactly_one
        CHECK (
            (CASE WHEN bygg_id IS NOT NULL THEN 1 ELSE 0 END)
          + (CASE WHEN bruksenhet_id IS NOT NULL THEN 1 ELSE 0 END)
          + (CASE WHEN rom_id IS NOT NULL THEN 1 ELSE 0 END)
          + (CASE WHEN uteomraade_id IS NOT NULL THEN 1 ELSE 0 END)
          + (CASE WHEN flate_id IS NOT NULL THEN 1 ELSE 0 END)
          + (CASE WHEN ressurs_id IS NOT NULL THEN 1 ELSE 0 END)
          = 1
        )
);

CREATE INDEX IF NOT EXISTS ix_ressurslenke_instans ON ressurslenke (fagsystem_instans_id);
CREATE INDEX IF NOT EXISTS ix_ressurslenke_instans_kontekst
    ON ressurslenke (fagsystem_instans_id, kontekst);
CREATE INDEX IF NOT EXISTS ix_ressurslenke_instans_ekstern
    ON ressurslenke (fagsystem_instans_id, ekstern_id);
CREATE INDEX IF NOT EXISTS ix_ressurslenke_ressurs ON ressurslenke (ressurs_id);

CREATE UNIQUE INDEX IF NOT EXISTS ux_ressurslenke_bygg
    ON ressurslenke (kontekst, fagsystem_instans_id, bygg_id) WHERE bygg_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_ressurslenke_bruksenhet
    ON ressurslenke (kontekst, fagsystem_instans_id, bruksenhet_id) WHERE bruksenhet_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_ressurslenke_rom
    ON ressurslenke (kontekst, fagsystem_instans_id, rom_id) WHERE rom_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_ressurslenke_uteomraade
    ON ressurslenke (kontekst, fagsystem_instans_id, uteomraade_id) WHERE uteomraade_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_ressurslenke_flate
    ON ressurslenke (kontekst, fagsystem_instans_id, flate_id) WHERE flate_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_ressurslenke_ressurs
    ON ressurslenke (kontekst, fagsystem_instans_id, ressurs_id) WHERE ressurs_id IS NOT NULL;


-- =============================================================================
-- 12. Identitet og feltautoritet
--
-- Et bygg har ofte flere eksterne identiteter samtidig: bygningsnummer fra
-- matrikkelen og en lokal ID i hvert fagsystem. Kolonnene kilde/ekstern_id på
-- tabellene holder den primære identiteten; identitetslenke holder resten.
-- =============================================================================

CREATE TABLE IF NOT EXISTS identitetslenke
(
    identitetslenke_id BIGSERIAL PRIMARY KEY,
    kilde          TEXT NOT NULL,
    ekstern_id     TEXT NOT NULL,
    bygg_id        BIGINT REFERENCES bygning(bygg_id) ON DELETE CASCADE,
    bruksenhet_id  BIGINT REFERENCES bruksenhet(bruksenhet_id) ON DELETE CASCADE,
    rom_id         BIGINT REFERENCES rom(rom_id) ON DELETE CASCADE,
    uteomraade_id  BIGINT REFERENCES uteomraade(uteomraade_id) ON DELETE CASCADE,
    flate_id       BIGINT REFERENCES flate(flate_id) ON DELETE CASCADE,
    ressurs_id     BIGINT REFERENCES ressurs(ressurs_id) ON DELETE CASCADE,
    matrikkelenhet_id BIGINT REFERENCES matrikkelenhet(enhet_id) ON DELETE CASCADE,
    adresse_id     BIGINT REFERENCES adresse(adresse_id) ON DELETE CASCADE,
    -- Hvor sikker koblingen er. Matrikkelmatching på adresse alene gir ofte
    -- 'sannsynlig', og da må den kunne overprøves uten å slette identiteten.
    match_status   TEXT NOT NULL DEFAULT 'bekreftet'
                       CHECK (match_status IN ('bekreftet','sannsynlig','usikker','avvist')),
    match_metode   TEXT,
    konfidens      NUMERIC(3,2) CHECK (konfidens IS NULL OR konfidens BETWEEN 0 AND 1),
    sist_oppdatert TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uniq_identitetslenke UNIQUE (kilde, ekstern_id),
    CONSTRAINT chk_identitetslenke_exactly_one
        CHECK (
            (CASE WHEN bygg_id IS NOT NULL THEN 1 ELSE 0 END)
          + (CASE WHEN bruksenhet_id IS NOT NULL THEN 1 ELSE 0 END)
          + (CASE WHEN rom_id IS NOT NULL THEN 1 ELSE 0 END)
          + (CASE WHEN uteomraade_id IS NOT NULL THEN 1 ELSE 0 END)
          + (CASE WHEN flate_id IS NOT NULL THEN 1 ELSE 0 END)
          + (CASE WHEN ressurs_id IS NOT NULL THEN 1 ELSE 0 END)
          + (CASE WHEN matrikkelenhet_id IS NOT NULL THEN 1 ELSE 0 END)
          + (CASE WHEN adresse_id IS NOT NULL THEN 1 ELSE 0 END)
          = 1
        )
);

CREATE INDEX IF NOT EXISTS ix_identitetslenke_bygg ON identitetslenke (bygg_id);
CREATE INDEX IF NOT EXISTS ix_identitetslenke_ressurs ON identitetslenke (ressurs_id);

-- Regelmotoren for autoritet, uttrykt som data i stedet for kode: hvilken kilde
-- vinner for hvilket felt. Matrikkelen har høyest prioritet for identitet,
-- fagsystemene for operative felt.
CREATE TABLE IF NOT EXISTS feltautoritet
(
    feltautoritet_id BIGSERIAL PRIMARY KEY,
    tabellnavn   TEXT NOT NULL,
    feltnavn     TEXT NOT NULL,
    kilde        TEXT NOT NULL,
    prioritet    INTEGER NOT NULL,
    merknad      TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uniq_feltautoritet UNIQUE (tabellnavn, feltnavn, kilde)
);

INSERT INTO feltautoritet (tabellnavn, feltnavn, kilde, prioritet, merknad) VALUES
    ('bygning','bygningsnr','matrikkel',100,'Matrikkelen er autoritativ for bygningsidentitet'),
    ('bygning','bygningstype','matrikkel',100,NULL),
    ('bygning','byggeaar','matrikkel',100,NULL),
    ('bygning','bra_m2','matrikkel',100,NULL),
    ('bygning','geom_wkt','matrikkel',100,NULL),
    ('bygning','navn','aktiv-kommune',80,'Fagsystemet har det publikumsvennlige navnet'),
    ('bygning','hjemmeside','aktiv-kommune',80,NULL),
    ('bygning','apningstid_tekst','aktiv-kommune',80,NULL),
    ('adresse','lat','matrikkel',100,'Representasjonspunkt fra matrikkelen slår geokoding'),
    ('adresse','lon','matrikkel',100,NULL),
    ('adresse','adressetekst','matrikkel',100,NULL),
    ('ressurs','navn','aktiv-kommune',100,'Fagsystemet eier det bookbare tilbudet'),
    ('ressurs','kapasitet','aktiv-kommune',60,'Nesten aldri utfylt; manuell verdi vinner'),
    ('ressurs','kapasitet','manuell',90,NULL),
    ('ressurs','lokaletype_id','manuell',100,'Kanonisk type settes av kuratert kartlegging')
ON CONFLICT (tabellnavn, feltnavn, kilde) DO NOTHING;


-- =============================================================================
-- 13. Ledighetscache
--
-- Master lagrer ikke bookinger. Denne tabellen er en ren, forkastbar cache slik
-- at et tverrkommunalt søk med tidsfilter ikke må gjøre ett API-kall per kommune
-- per spørring. Den kan trunkeres når som helst uten tap av masterdata.
-- =============================================================================

CREATE TABLE IF NOT EXISTS ledighet_cache
(
    ressurs_id   BIGINT NOT NULL REFERENCES ressurs(ressurs_id) ON DELETE CASCADE,
    dato         DATE NOT NULL,
    ledig_json   JSONB NOT NULL,
    har_ledighet BOOLEAN NOT NULL,
    hentet_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    gyldig_til   TIMESTAMPTZ NOT NULL,
    kilde_etag   TEXT,
    PRIMARY KEY (ressurs_id, dato)
);

CREATE INDEX IF NOT EXISTS ix_ledighet_cache_dato
    ON ledighet_cache (dato, har_ledighet);

CREATE INDEX IF NOT EXISTS ix_ledighet_cache_gyldig
    ON ledighet_cache (gyldig_til);


-- =============================================================================
-- 14. Uttrekk og synkronisering
-- =============================================================================

-- Rått svar fra kilden, lagret før transformasjon. Gjør at en last kan kjøres
-- om igjen uten nye kall mot kommunens system, og at uttrekket er revisjonsbart.
CREATE TABLE IF NOT EXISTS kildeuttrekk
(
    uttrekk_id   BIGSERIAL PRIMARY KEY,
    instans_id   BIGINT REFERENCES fagsystem_instans(instans_id) ON DELETE SET NULL,
    kilde        TEXT NOT NULL,
    endepunkt    TEXT NOT NULL,
    hentet_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    http_status  INTEGER,
    payload      JSONB,
    payload_sha256 CHAR(64),
    bytes        BIGINT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_kildeuttrekk_kilde_tid ON kildeuttrekk (kilde, hentet_at DESC);

CREATE TABLE IF NOT EXISTS synk_kjoring
(
    kjoring_id   BIGSERIAL PRIMARY KEY,
    kilde        TEXT NOT NULL,
    uttrekk_id   BIGINT REFERENCES kildeuttrekk(uttrekk_id) ON DELETE SET NULL,
    startet_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    avsluttet_at TIMESTAMPTZ,
    status       TEXT NOT NULL DEFAULT 'pagaar'
                     CHECK (status IN ('pagaar','fullfort','delvis','feilet')),
    antall_lest      INTEGER NOT NULL DEFAULT 0,
    antall_opprettet INTEGER NOT NULL DEFAULT 0,
    antall_oppdatert INTEGER NOT NULL DEFAULT 0,
    antall_avvist    INTEGER NOT NULL DEFAULT 0,
    melding      TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_synk_kjoring_kilde ON synk_kjoring (kilde, startet_at DESC);

-- Kildeuttrekket fra Aktiv kommune er delvis: koblingstabellene eksporteres
-- rått mens resources/buildings er filtrert, så en betydelig andel rader peker
-- på foreldre som ikke finnes i uttrekket. Avvik loggføres i stedet for å
-- forkastes stille.
CREATE TABLE IF NOT EXISTS synk_avvik
(
    avvik_id     BIGSERIAL PRIMARY KEY,
    kjoring_id   BIGINT NOT NULL REFERENCES synk_kjoring(kjoring_id) ON DELETE CASCADE,
    samling      TEXT NOT NULL,
    avvikstype   TEXT NOT NULL CHECK (avvikstype IN
                     ('manglende_forelder','ukjent_kode','ugyldig_verdi','duplikat',
                      'geokoding_feilet','ikke_kartlagt','annet')),
    ekstern_id   TEXT,
    detalj       TEXT,
    rad_json     JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_synk_avvik_kjoring ON synk_avvik (kjoring_id, avvikstype);


-- =============================================================================
-- 15. Søkevisninger
-- =============================================================================

-- Flat visning for tverrkommunalt søk. Kommune, adresse, koordinat, kanonisk
-- type, aktiviteter og fasiliteter i én rad per bookbar ressurs.
CREATE OR REPLACE VIEW v_ressurs_sok AS
SELECT
    r.ressurs_id,
    r.navn,
    r.type,
    r.kapasitet,
    r.areal_m2,
    r.beskrivelse,
    k.kommune_id,
    k.kommunenr,
    k.navn                         AS kommune_navn,
    k.fylkesnr,
    lt.lokaletype_id,
    lt.kode                        AS lokaletype_kode,
    lt.navn                        AS lokaletype_navn,
    parent.kode                    AS lokaletype_hovedgruppe,
    b.bygg_id,
    b.navn                         AS bygg_navn,
    u.uteomraade_id,
    u.navn                         AS uteomraade_navn,
    bd.navn                        AS bydel_navn,
    COALESCE(a.lat, b.lat, u.lat)  AS lat,
    COALESCE(a.lon, b.lon, u.lon)  AS lon,
    a.adressetekst,
    a.postnummer,
    a.poststed,
    (SELECT array_agg(ak.kode ORDER BY ak.kode)
       FROM ressurs_aktivitet ra
       JOIN aktivitet ak ON ak.aktivitet_id = ra.aktivitet_id
      WHERE ra.ressurs_id = r.ressurs_id)      AS aktivitet_koder,
    (SELECT array_agg(f.kode ORDER BY f.kode)
       FROM ressurs_fasilitet rf
       JOIN fasilitet f ON f.fasilitet_id = rf.fasilitet_id
      WHERE rf.ressurs_id = r.ressurs_id)      AS fasilitet_koder,
    r.sokevektor,
    r.sist_oppdatert
FROM ressurs r
JOIN kommune k          ON k.kommune_id = r.kommune_id
LEFT JOIN lokaletype lt ON lt.lokaletype_id = r.lokaletype_id
LEFT JOIN lokaletype parent ON parent.lokaletype_id = lt.parent_id
LEFT JOIN bygning b     ON b.bygg_id = r.bygg_id
LEFT JOIN uteomraade u  ON u.uteomraade_id = r.uteomraade_id
LEFT JOIN bydel bd      ON bd.bydel_id = COALESCE(b.bydel_id, u.bydel_id)
LEFT JOIN adresse a     ON a.bygg_id = b.bygg_id AND a.er_hovedadresse
WHERE r.aktiv AND r.bookbar AND NOT r.skjult;

-- Kildekoder som mangler godkjent kartlegging. Arbeidslisten for kuratering;
-- hver rad her er en lokal kode som ikke kan søkes på tvers av kommuner ennå.
CREATE OR REPLACE VIEW v_ukartlagte_kildekoder AS
SELECT
    kk.kildekode_id,
    fi.kildenokkel,
    k.navn AS kommune_navn,
    kk.kodetype,
    kk.kode,
    kk.navn,
    kk.sist_sett
FROM kildekode kk
JOIN fagsystem_instans fi ON fi.instans_id = kk.instans_id
JOIN kommune k            ON k.kommune_id = fi.kommune_id
WHERE kk.aktiv
  AND NOT EXISTS (
      SELECT 1 FROM kildekode_mapping m
       WHERE m.kildekode_id = kk.kildekode_id
         AND m.status IN ('godkjent','ikke_relevant')
  );

-- Ressurser som ikke kan rutes til noe fagsystem for booking, altså ressurser
-- et søk kan finne men ikke sende brukeren videre fra.
CREATE OR REPLACE VIEW v_ressurs_uten_bookinglenke AS
SELECT r.ressurs_id, r.navn, k.navn AS kommune_navn, r.kilde, r.ekstern_id
FROM ressurs r
JOIN kommune k ON k.kommune_id = r.kommune_id
WHERE r.bookbar
  AND NOT EXISTS (
      SELECT 1 FROM ressurslenke rl
       WHERE rl.ressurs_id = r.ressurs_id
         AND rl.kontekst = 'booking'
         AND rl.aktiv
  );


-- =============================================================================
-- 16. Kanonisk kodeverk (startsett)
--
-- Utledet fra de 142 distinkte kategorinavnene som faktisk finnes i de 12
-- Aktiv kommune-instansene, slått sammen på tvers av målform, skrivefeil og
-- synonymer. Kartleggingen fra lokale koder gjøres i kildekode_mapping.
-- =============================================================================

INSERT INTO lokaletype (kode, navn, parent_id, innendors, sortering) VALUES
    ('IDRETT','Idrett og fysisk aktivitet',NULL,NULL,10),
    ('KULTUR','Kultur og scene',NULL,NULL,20),
    ('UNDERVISNING','Undervisning og møte',NULL,NULL,30),
    ('VERKSTED','Verksted og produksjon',NULL,NULL,40),
    ('ARRANGEMENT','Selskap og arrangement',NULL,NULL,50),
    ('BEVERTNING','Mat og bevertning',NULL,NULL,60),
    ('NAERMILJO','Aktivitets- og nærmiljøhus',NULL,NULL,70),
    ('UTEAREAL','Utendørs areal',NULL,FALSE,80),
    ('OVERNATTING','Overnatting og bolig',NULL,TRUE,90),
    ('ANNET_LOKALE','Kontor og andre lokaler',NULL,NULL,100),
    ('UTSTYR','Utstyr',NULL,NULL,110)
ON CONFLICT (kode) DO NOTHING;

INSERT INTO lokaletype (kode, navn, parent_id, innendors, sortering)
SELECT v.kode, v.navn, p.lokaletype_id, v.innendors, v.sortering
FROM (VALUES
    ('IDRETTSHALL','Idrettshall','IDRETT',TRUE,11),
    ('GYMSAL','Gymsal','IDRETT',TRUE,12),
    ('SVOMMEANLEGG','Svømmeanlegg','IDRETT',TRUE,13),
    ('ISHALL','Ishall','IDRETT',TRUE,14),
    ('ISBANE_UTE','Utendørs isbane','IDRETT',FALSE,15),
    ('FRIIDRETTSANLEGG','Friidrettsanlegg','IDRETT',NULL,16),
    ('FOTBALLBANE','Fotballbane','IDRETT',FALSE,17),
    ('BALLBANE','Ballbane og ballbinge','IDRETT',NULL,18),
    ('TENNISANLEGG','Tennisanlegg','IDRETT',NULL,19),
    ('STYRKEROM','Styrke- og treningsrom','IDRETT',TRUE,20),
    ('KAMPSPORTROM','Kampsportrom','IDRETT',TRUE,21),
    ('KLATREANLEGG','Klatreanlegg','IDRETT',NULL,22),
    ('TURNANLEGG','Turnanlegg','IDRETT',TRUE,23),
    ('SKATEANLEGG','Skateanlegg','IDRETT',NULL,24),
    ('SKYTEBANE','Skytebane','IDRETT',NULL,25),
    ('SJOSPORTANLEGG','Sjøsportanlegg','IDRETT',FALSE,26),
    ('GARDEROBE','Garderobe','IDRETT',TRUE,27),
    ('OPPVARMINGSROM','Oppvarmingsrom','IDRETT',TRUE,28),

    ('KONSERTSAL','Konsertsal og kultursal','KULTUR',TRUE,21),
    ('SCENE','Scene','KULTUR',NULL,22),
    ('AUDITORIUM','Auditorium og foredragssal','KULTUR',TRUE,23),
    ('OVINGSROM','Øvingsrom og musikkrom','KULTUR',TRUE,24),
    ('DANSESAL','Dansesal','KULTUR',TRUE,25),
    ('LYDSTUDIO','Lydstudio','KULTUR',TRUE,26),
    ('UTSTILLINGSLOKALE','Utstillingslokale og atelier','KULTUR',TRUE,27),
    ('BIBLIOTEK','Bibliotek','KULTUR',TRUE,28),
    ('FOAJE','Foajé','KULTUR',TRUE,29),

    ('KLASSEROM','Klasserom og undervisningsrom','UNDERVISNING',TRUE,31),
    ('GRUPPEROM','Grupperom og prosjektrom','UNDERVISNING',TRUE,32),
    ('MOTEROM','Møterom og konferanserom','UNDERVISNING',TRUE,33),
    ('DATAROM','Datarom','UNDERVISNING',TRUE,34),
    ('AULA','Aula','UNDERVISNING',TRUE,35),

    ('SLOYDSAL','Sløydsal','VERKSTED',TRUE,41),
    ('KUNSTVERKSTED','Kunst- og håndverksverksted','VERKSTED',TRUE,42),
    ('SYSTUE','Systue','VERKSTED',TRUE,43),
    ('MEDIEVERKSTED','Multimedia- og streamingverksted','VERKSTED',TRUE,44),
    ('FRISORSALONG','Frisørsalong','VERKSTED',TRUE,45),

    ('SELSKAPSLOKALE','Selskapslokale','ARRANGEMENT',TRUE,51),
    ('FORSAMLINGSLOKALE','Forsamlingslokale','ARRANGEMENT',TRUE,52),
    ('SEREMONIROM','Seremonirom','ARRANGEMENT',TRUE,53),
    ('BURSDAGSLOKALE','Bursdagslokale','ARRANGEMENT',TRUE,54),
    ('ARRANGEMENTSARENA','Arrangementsarena','ARRANGEMENT',NULL,55),
    ('TORGPLASS','Torg og møteplass','ARRANGEMENT',FALSE,56),

    ('KJOKKEN','Kjøkken','BEVERTNING',TRUE,61),
    ('KANTINE','Kantine','BEVERTNING',TRUE,62),
    ('KAFE','Kafé og kiosk','BEVERTNING',TRUE,63),

    ('ALLAKTIVITETSHUS','Allaktivitetshus','NAERMILJO',TRUE,71),
    ('AKTIVITETSROM','Aktivitetsrom og flerbruksrom','NAERMILJO',TRUE,72),
    ('UNGDOMSLOKALE','Ungdomslokale','NAERMILJO',TRUE,73),
    ('DAGSENTER','Dagsenter og miljøstue','NAERMILJO',TRUE,74),
    ('INNBYGGERTORG','Innbyggertorg','NAERMILJO',TRUE,75),

    ('FRILUFTSOMRAADE','Friluftsområde','UTEAREAL',FALSE,81),
    ('UTEOMRAADE','Uteområde','UTEAREAL',FALSE,82),
    ('TURVEI','Turvei og løype','UTEAREAL',FALSE,83),
    ('GAPAHUK','Gapahuk og bålplass','UTEAREAL',FALSE,84),
    ('UTESCENE','Utendørsscene','UTEAREAL',FALSE,85),

    ('OVERNATTINGSROM','Overnattingsrom','OVERNATTING',TRUE,91),
    ('BEBOERROM','Beboerrom','OVERNATTING',TRUE,92),
    ('OVINGSLEILIGHET','Øvingsleilighet','OVERNATTING',TRUE,93),

    ('KONTOR','Kontor og arbeidsplass','ANNET_LOKALE',TRUE,101),
    ('BUTIKKLOKALE','Butikklokale','ANNET_LOKALE',TRUE,102),
    ('LAGER','Lager','ANNET_LOKALE',TRUE,103),
    ('GENERELT_LOKALE','Generelt lokale','ANNET_LOKALE',TRUE,104),

    ('SYKKEL','Sykkel og el-sykkel','UTSTYR',NULL,111),
    ('KANO_KAJAKK','Kano og kajakk','UTSTYR',NULL,112),
    ('FISKEUTSTYR','Fiskeutstyr','UTSTYR',NULL,113),
    ('REDNINGSVEST','Redningsvest','UTSTYR',NULL,114),
    ('LYDANLEGG','Lyd- og lysanlegg','UTSTYR',NULL,115),
    ('ANNET_UTSTYR','Annet utstyr','UTSTYR',NULL,116)
) AS v(kode, navn, parent_kode, innendors, sortering)
JOIN lokaletype p ON p.kode = v.parent_kode
ON CONFLICT (kode) DO NOTHING;

INSERT INTO aktivitet (kode, navn, parent_id, sortering) VALUES
    ('IDRETT','Idrett',NULL,10),
    ('KULTUR','Kultur',NULL,20),
    ('OPPLARING','Opplæring og kurs',NULL,30),
    ('MOTE','Møte og konferanse',NULL,40),
    ('PRIVAT','Privat arrangement',NULL,50),
    ('FRIVILLIGHET','Frivillighet og lag',NULL,60),
    ('FRILUFT','Friluftsliv',NULL,70),
    ('INTERNT','Internt kommunalt',NULL,80)
ON CONFLICT (kode) DO NOTHING;

INSERT INTO aktivitet (kode, navn, parent_id, sortering)
SELECT v.kode, v.navn, p.aktivitet_id, v.sortering
FROM (VALUES
    ('FOTBALL','Fotball','IDRETT',11),
    ('HANDBALL','Håndball','IDRETT',12),
    ('BASKETBALL','Basketball','IDRETT',13),
    ('VOLLEYBALL','Volleyball','IDRETT',14),
    ('TURN','Turn','IDRETT',15),
    ('KAMPSPORT','Kampsport','IDRETT',16),
    ('SVOMMING','Svømming','IDRETT',17),
    ('FRIIDRETT','Friidrett','IDRETT',18),
    ('ISHOCKEY','Ishockey og skøyter','IDRETT',19),
    ('KLATRING','Klatring','IDRETT',20),
    ('STYRKETRENING','Styrketrening','IDRETT',21),
    ('TENNIS','Tennis','IDRETT',22),
    ('SKYTING','Skyting','IDRETT',23),
    ('DANS','Dans','KULTUR',24),
    ('MUSIKK','Musikk og korps','KULTUR',25),
    ('KOR','Kor og sang','KULTUR',26),
    ('TEATER','Teater og revy','KULTUR',27),
    ('KUNST_HANDVERK','Kunst, håndverk og media','KULTUR',28),
    ('SPEIDER','Speider','FRILUFT',29),
    ('SYKLING','Sykling','FRILUFT',30)
) AS v(kode, navn, parent_kode, sortering)
JOIN aktivitet p ON p.kode = v.parent_kode
ON CONFLICT (kode) DO NOTHING;

INSERT INTO fasilitet (kode, navn, gruppe, sortering) VALUES
    ('HC_TILGANG','Rullestoltilgang','tilgjengelighet',10),
    ('HC_TOALETT','HC-toalett','tilgjengelighet',11),
    ('TELESLYNGE','Teleslynge','tilgjengelighet',12),
    ('HEIS','Heis','tilgjengelighet',13),
    ('GARDEROBE','Garderobe','sanitaer',20),
    ('DUSJ','Dusj','sanitaer',21),
    ('TOALETT','Toalett','sanitaer',22),
    ('PROSJEKTOR','Prosjektor','teknisk',30),
    ('SKJERM','Skjerm','teknisk',31),
    ('LYDANLEGG','Lydanlegg','teknisk',32),
    ('MIKROFON','Mikrofon','teknisk',33),
    ('WIFI','Trådløst nett','teknisk',34),
    ('STREAMING','Streamingutstyr','teknisk',35),
    ('FLYGEL','Flygel eller piano','teknisk',36),
    ('SCENELYS','Scenelys','teknisk',37),
    ('KJOKKEN','Kjøkken','kjokken',40),
    ('KJOLESKAP','Kjøleskap','kjokken',41),
    ('OPPVASKMASKIN','Oppvaskmaskin','kjokken',42),
    ('KAFFETRAKTER','Kaffetrakter','kjokken',43),
    ('KIOSK','Kiosk','kjokken',44),
    ('TRIBUNE','Tribune','sport',50),
    ('MAALBUR','Målbur','sport',51),
    ('BALLBINGE','Ballbinge','sport',52),
    ('TIDTAKING','Tidtakingsanlegg','sport',53),
    ('BANEDELING','Delbar bane','sport',54),
    ('BORD_STOLER','Bord og stoler','moblering',60),
    ('WHITEBOARD','Whiteboard','moblering',61),
    ('PARKETTGULV','Parkettgulv','moblering',62),
    ('PARKERING','Parkering','uteareal',70),
    ('HC_PARKERING','HC-parkering','uteareal',71),
    ('SYKKELPARKERING','Sykkelparkering','uteareal',72),
    ('BALLPLASS_UTE','Ballplass utendørs','uteareal',73),
    ('BAALPLASS','Bålplass','uteareal',74),
    ('FLOMLYS','Flomlys','uteareal',75),
    ('ELEKTRONISK_LAS','Elektronisk låssystem','annet',80)
ON CONFLICT (kode) DO NOTHING;


-- =============================================================================
-- 17. updated_at-triggere
-- =============================================================================

DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'kommune','bydel','matrikkelenhet','bygning','floy','etasje','bruksenhet',
        'rom','gate','adresse','uteomraade','adkomstpunkt','flate','lokaletype',
        'aktivitet','fasilitet','classification','fagsystem','fagsystem_instans',
        'kildekode','kildekode_mapping','ressurs','ressurspool','ressurspool_medlem',
        'ressurslenke','identitetslenke','feltautoritet'
    ]
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_%1$s_updated_at ON %1$I', t);
        EXECUTE format(
            'CREATE TRIGGER trg_%1$s_updated_at BEFORE UPDATE ON %1$I
             FOR EACH ROW EXECUTE FUNCTION sett_updated_at()', t);
    END LOOP;
END
$$;
