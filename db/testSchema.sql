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

-- Aktivitet (kodeverk for aktivitetstyper, hentet fra booking-/aktivitetssystem)
CREATE TABLE IF NOT EXISTS aktivitet
(
    aktivitet_id   BIGSERIAL PRIMARY KEY,
    parent_id      BIGINT REFERENCES aktivitet(aktivitet_id) ON DELETE SET NULL,
    navn           TEXT NOT NULL,
    beskrivelse    TEXT,
    aktiv          BOOLEAN DEFAULT TRUE,
    ekstern_id     TEXT,
    kilde          TEXT,
    kilde_ref      TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_aktivitet_source_external
    ON aktivitet (kilde, ekstern_id)
    WHERE kilde IS NOT NULL AND ekstern_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_aktivitet_parent
    ON aktivitet (parent_id);

-- Bygning
CREATE TABLE IF NOT EXISTS bygning
(
    bygg_id     BIGSERIAL PRIMARY KEY,
    bygningsnr  BIGINT UNIQUE,
    bydel_id    BIGINT REFERENCES bydel(bydel_id) ON DELETE SET NULL,
    aktivitet_id BIGINT REFERENCES aktivitet(aktivitet_id) ON DELETE SET NULL,
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
    telefon     TEXT,
    epost       TEXT,
    hjemmeside  TEXT,
    apningstider TEXT,
    tilsyn_navn TEXT,
    tilsyn_telefon TEXT,
    tilsyn_epost TEXT,
    tilsyn_navn2 TEXT,
    tilsyn_telefon2 TEXT,
    tilsyn_epost2 TEXT,
    metadata_json JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_bygning_bydel
    ON bygning (bydel_id);

CREATE INDEX IF NOT EXISTS ix_bygning_aktivitet
    ON bygning (aktivitet_id);

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
    bygg_id         BIGINT NOT NULL REFERENCES bygning(bygg_id) ON DELETE CASCADE,
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
    adressetype TEXT NOT NULL DEFAULT 'vegadresse' CHECK (adressetype IN ('vegadresse')),
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
    autoritativ BOOLEAN DEFAULT FALSE,
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

-- Flater/baner/løyper (inne/ute) med felles identitet og provenance
CREATE TABLE IF NOT EXISTS flate
(
    flate_id	   BIGSERIAL PRIMARY KEY,
    navn	       TEXT,
    type	       TEXT NOT NULL CHECK (type IN ('bane','flate','trase','loype','annet')),
    -- plassering: velg nøyaktig én
    rom_id	       BIGINT REFERENCES rom(rom_id) ON DELETE CASCADE,
    uteomraade_id BIGINT REFERENCES uteomraade(uteomraade_id) ON DELETE CASCADE,
    -- geometri og kartstøtte uten PostGIS
    geom_wkt	   TEXT,
    lon	       DOUBLE PRECISION CHECK (lon IS NULL OR (lon BETWEEN -180 AND 180)),
    lat	       DOUBLE PRECISION CHECK (lat IS NULL OR (lat BETWEEN -90 AND 90)),
    srid	       INTEGER DEFAULT 4258,
    -- identitet og provenance
    kilde	       TEXT,
    ekstern_id   TEXT,
    kilde_ref	   TEXT,
    sist_oppdatert TIMESTAMPTZ,
    autoritativ  BOOLEAN DEFAULT FALSE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- nøyaktig én lokasjonsreferanse må være satt
    CONSTRAINT chk_flate_one_location
        CHECK (
            (CASE WHEN rom_id IS NOT NULL THEN 1 ELSE 0 END) +
            (CASE WHEN uteomraade_id IS NOT NULL THEN 1 ELSE 0 END)
            = 1
        ),
    CONSTRAINT chk_flate_lon_lat_both
        CHECK ((lon IS NULL AND lat IS NULL) OR (lon IS NOT NULL AND lat IS NOT NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_flate_source_external
    ON flate (kilde, ekstern_id)
    WHERE kilde IS NOT NULL AND ekstern_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_flate_rom
    ON flate (rom_id);
CREATE INDEX IF NOT EXISTS ix_flate_uteomraade
    ON flate (uteomraade_id);
CREATE INDEX IF NOT EXISTS ix_flate_lon_lat
    ON flate (lon, lat);

-- Komposisjon: kombiner/del flater (f.eks. 2 små baner -> 1 stor)
CREATE TABLE IF NOT EXISTS flate_rel_aggregates
(
    parent_flate_id BIGINT NOT NULL REFERENCES flate(flate_id) ON DELETE CASCADE,
    child_flate_id  BIGINT NOT NULL REFERENCES flate(flate_id) ON DELETE CASCADE,
    role		    TEXT,                 -- f.eks. 'kombinasjon','del'
    dekning_pct	  NUMERIC(5,2),         -- valgfritt: hvor mye av parent arealet barnet dekker
    PRIMARY KEY (parent_flate_id, child_flate_id)
);

-- External classifications (NS 3451, TFM, Omniclass)
CREATE TABLE IF NOT EXISTS classification
(
    class_id       BIGSERIAL PRIMARY KEY,
    scheme         TEXT NOT NULL,
    code           TEXT NOT NULL,
    title          TEXT,
    UNIQUE (scheme, code)
);

-- Klassifisering av flater via eksisterende classification
CREATE TABLE IF NOT EXISTS flate_classification
(
    flate_id  BIGINT NOT NULL REFERENCES flate(flate_id) ON DELETE CASCADE,
    class_id  BIGINT NOT NULL REFERENCES classification(class_id) ON DELETE CASCADE,
    PRIMARY KEY (flate_id, class_id)
);

-- Indekser for adresse for effektiv oppslag
CREATE INDEX IF NOT EXISTS ix_adresse_gate
    ON adresse (gate_id);

CREATE INDEX IF NOT EXISTS ix_adresse_postnummer
    ON adresse (postnummer);

CREATE INDEX IF NOT EXISTS ix_adresse_lon_lat
    ON adresse (lon, lat);

-- Fasilitet (kodeverk for utstyr/fasiliteter knyttet til en ressurs, f.eks. "Garderobe")
CREATE TABLE IF NOT EXISTS fasilitet
(
    fasilitet_id   BIGSERIAL PRIMARY KEY,
    navn           TEXT NOT NULL,
    aktiv          BOOLEAN DEFAULT TRUE,
    ekstern_id     TEXT,
    kilde          TEXT,
    kilde_ref      TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_fasilitet_source_external
    ON fasilitet (kilde, ekstern_id)
    WHERE kilde IS NOT NULL AND ekstern_id IS NOT NULL;

-- Ressurskategori (kodeverk for kategorisering av ressurser, f.eks. "Overnatting")
CREATE TABLE IF NOT EXISTS ressurskategori
(
    kategori_id    BIGSERIAL PRIMARY KEY,
    parent_id      BIGINT REFERENCES ressurskategori(kategori_id) ON DELETE SET NULL,
    navn           TEXT NOT NULL,
    aktiv          BOOLEAN DEFAULT TRUE,
    capacity       INTEGER,
    e_lock         BOOLEAN,
    ekstern_id     TEXT,
    kilde          TEXT,
    kilde_ref      TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_ressurskategori_source_external
    ON ressurskategori (kilde, ekstern_id)
    WHERE kilde IS NOT NULL AND ekstern_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_ressurskategori_parent
    ON ressurskategori (parent_id);

-- Organisasjon (klubber/lag/kontaktpersoner fra fagsystem)
-- ADVARSEL: kan inneholde personopplysninger (navn, telefon, e-post, adresse til
-- privatpersoner/kontaktpersoner). Avklar behandlingsgrunnlag, lagringstid og
-- tilgangsbegrensning med Personvernombud/Data Privacy Officer før bruk (GDPR).
CREATE TABLE IF NOT EXISTS organisasjon
(
    organisasjon_id     BIGSERIAL PRIMARY KEY,
    organisasjonsnummer TEXT,
    navn                TEXT NOT NULL,
    hjemmeside          TEXT,
    telefon             TEXT,
    epost               TEXT,
    c_o_adresse         TEXT,
    gate                TEXT,
    postnummer          CHAR(4) CHECK (postnummer IS NULL OR postnummer ~ '^[0-9]{4}$'),
    poststed            TEXT,
    aktivitet_id        BIGINT REFERENCES aktivitet(aktivitet_id) ON DELETE SET NULL,
    vis_i_portal        BOOLEAN DEFAULT FALSE,
    ekstern_id          TEXT,
    kilde               TEXT,
    kilde_ref           TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_organisasjon_source_external
    ON organisasjon (kilde, ekstern_id)
    WHERE kilde IS NOT NULL AND ekstern_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_organisasjon_aktivitet
    ON organisasjon (aktivitet_id);

-- Generiske ressurser (utstyr/person/tjeneste), ressurspooler og medlemskap
CREATE TABLE IF NOT EXISTS ressurs
(
    ressurs_id     BIGSERIAL PRIMARY KEY,
    type           TEXT NOT NULL CHECK (type IN ('equipment','person','service','other')),
    flate_id       BIGINT REFERENCES flate(flate_id) ON DELETE SET NULL,
    kategori_id    BIGINT REFERENCES ressurskategori(kategori_id) ON DELETE SET NULL,
    navn           TEXT,
    metadata_json  JSONB,
    kilde          TEXT,
    kilde_ref      TEXT,
    ekstern_id     TEXT,
    sist_oppdatert TIMESTAMPTZ,
    autoritativ    BOOLEAN DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_ressurs_ident
        CHECK (kilde IS NOT NULL AND ekstern_id IS NOT NULL)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_ressurs_source_external
    ON ressurs (kilde, ekstern_id)
    WHERE kilde IS NOT NULL AND ekstern_id IS NOT NULL;

-- Én-til-én kobling (valgfritt) mellom flate og ressurs når flate brukes som bookbar ressurs
CREATE UNIQUE INDEX IF NOT EXISTS ux_ressurs_flate
    ON ressurs (flate_id)
    WHERE flate_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_ressurs_kategori
    ON ressurs (kategori_id);

-- Kobling ressurs <-> aktivitet
CREATE TABLE IF NOT EXISTS ressurs_aktivitet
(
    ressurs_id    BIGINT NOT NULL REFERENCES ressurs(ressurs_id) ON DELETE CASCADE,
    aktivitet_id  BIGINT NOT NULL REFERENCES aktivitet(aktivitet_id) ON DELETE CASCADE,
    PRIMARY KEY (ressurs_id, aktivitet_id)
);

CREATE INDEX IF NOT EXISTS ix_ressurs_aktivitet_aktivitet
    ON ressurs_aktivitet (aktivitet_id);

-- Kobling ressurs <-> fasilitet
CREATE TABLE IF NOT EXISTS ressurs_fasilitet
(
    ressurs_id    BIGINT NOT NULL REFERENCES ressurs(ressurs_id) ON DELETE CASCADE,
    fasilitet_id  BIGINT NOT NULL REFERENCES fasilitet(fasilitet_id) ON DELETE CASCADE,
    PRIMARY KEY (ressurs_id, fasilitet_id)
);

CREATE INDEX IF NOT EXISTS ix_ressurs_fasilitet_fasilitet
    ON ressurs_fasilitet (fasilitet_id);

-- Kobling ressurskategori <-> aktivitet
CREATE TABLE IF NOT EXISTS ressurskategori_aktivitet
(
    kategori_id   BIGINT NOT NULL REFERENCES ressurskategori(kategori_id) ON DELETE CASCADE,
    aktivitet_id  BIGINT NOT NULL REFERENCES aktivitet(aktivitet_id) ON DELETE CASCADE,
    PRIMARY KEY (kategori_id, aktivitet_id)
);

CREATE INDEX IF NOT EXISTS ix_ressurskategori_aktivitet_aktivitet
    ON ressurskategori_aktivitet (aktivitet_id);

-- Kobling bygning <-> ressurs (direkte tilknytning uten rom/bruksenhet i mellom)
CREATE TABLE IF NOT EXISTS bygning_ressurs
(
    bygg_id      BIGINT NOT NULL REFERENCES bygning(bygg_id) ON DELETE CASCADE,
    ressurs_id   BIGINT NOT NULL REFERENCES ressurs(ressurs_id) ON DELETE CASCADE,
    PRIMARY KEY (bygg_id, ressurs_id)
);

CREATE INDEX IF NOT EXISTS ix_bygning_ressurs_ressurs
    ON bygning_ressurs (ressurs_id);

CREATE TABLE IF NOT EXISTS ressurspool
(
    pool_id       BIGSERIAL PRIMARY KEY,
    navn          TEXT NOT NULL,
    type          TEXT NOT NULL CHECK (type IN ('booking','staffing','equipment','other')),
    kommune_id    BIGINT REFERENCES kommune(kommune_id) ON DELETE SET NULL,
    beskrivelse   TEXT,
    metadata_json JSONB,
    aktiv         BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uniq_pool_per_scope UNIQUE (kommune_id, navn)
);

CREATE INDEX IF NOT EXISTS ix_pool_kommune
    ON ressurspool (kommune_id);

CREATE TABLE IF NOT EXISTS ressurspool_medlem
(
    pool_id      BIGINT NOT NULL REFERENCES ressurspool(pool_id) ON DELETE CASCADE,
    ressurs_id   BIGINT NOT NULL REFERENCES ressurs(ressurs_id) ON DELETE CASCADE,
    rolle        TEXT,
    prioritet    INTEGER,
    gyldig_fra   TIMESTAMPTZ,
    gyldig_til   TIMESTAMPTZ,
    merknad      TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (pool_id, ressurs_id),
    CONSTRAINT chk_medlem_interval
        CHECK (gyldig_til IS NULL OR gyldig_fra IS NULL OR gyldig_til > gyldig_fra)
);

CREATE INDEX IF NOT EXISTS ix_pool_medlem_ressurs
    ON ressurspool_medlem (ressurs_id);

CREATE INDEX IF NOT EXISTS ix_pool_medlem_gyldighet
    ON ressurspool_medlem (gyldig_fra, gyldig_til);

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

-- Fagsystem-instans (kan betjene én eller flere kommuner, se fagsystem_instans_kommune)
CREATE TABLE IF NOT EXISTS fagsystem_instans
(
    instans_id   BIGSERIAL PRIMARY KEY,
    fagsystem_id BIGINT NOT NULL REFERENCES fagsystem(fagsystem_id) ON DELETE CASCADE,
    base_url     TEXT NOT NULL,
    konfig_json  JSONB,
    aktiv        BOOLEAN DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_fagsystem_instans_fagsystem
    ON fagsystem_instans (fagsystem_id);

-- Kobling fagsystem_instans <-> kommune: mange-til-mange (én instans kan betjene
-- flere kommuner, f.eks. en delt/regional instans; én kommune kan bruke flere instanser)
CREATE TABLE IF NOT EXISTS fagsystem_instans_kommune
(
    instans_id  BIGINT NOT NULL REFERENCES fagsystem_instans(instans_id) ON DELETE CASCADE,
    kommune_id  BIGINT NOT NULL REFERENCES kommune(kommune_id) ON DELETE CASCADE,
    PRIMARY KEY (instans_id, kommune_id)
);

CREATE INDEX IF NOT EXISTS ix_fagsystem_instans_kommune_kommune
    ON fagsystem_instans_kommune (kommune_id);

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
    ressurs_id     BIGINT REFERENCES ressurs(ressurs_id) ON DELETE CASCADE,
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
                    + (CASE WHEN ressurs_id IS NOT NULL THEN 1 ELSE 0 END)
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

CREATE UNIQUE INDEX IF NOT EXISTS ux_ressurslenke_ressurs
    ON ressurslenke (kontekst, fagsystem_instans_id, ressurs_id)
    WHERE ressurs_id IS NOT NULL;
