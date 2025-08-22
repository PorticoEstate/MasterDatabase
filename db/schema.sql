-- Postgres schema for Matrikkel + building model with addresses under building
-- Spatial columns are stored without PostGIS for now (WKT and lon/lat)

-- Kommune
CREATE TABLE IF NOT EXISTS kommune
(
	kommune_id	BIGSERIAL PRIMARY KEY,
	kommunenr	CHAR(4) NOT NULL UNIQUE,
	navn		TEXT NOT NULL,
	created_at	TIMESTAMPTZ NOT NULL DEFAULT now(),
	updated_at	TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Bydel (delområde innen kommune)
CREATE TABLE IF NOT EXISTS bydel
(
	bydel_id	BIGSERIAL PRIMARY KEY,
	kommune_id	BIGINT NOT NULL REFERENCES kommune(kommune_id) ON DELETE CASCADE,
	kode		TEXT NOT NULL,
	navn		TEXT NOT NULL,
	created_at	TIMESTAMPTZ NOT NULL DEFAULT now(),
	updated_at	TIMESTAMPTZ NOT NULL DEFAULT now(),
	CONSTRAINT uniq_bydel_per_kommune UNIQUE (kommune_id, kode)
);

CREATE INDEX IF NOT EXISTS ix_bydel_kommune
	ON bydel (kommune_id);

-- Matrikkelenhet
CREATE TABLE IF NOT EXISTS matrikkelenhet
(
	enhet_id		BIGSERIAL PRIMARY KEY,
	kommune_id		BIGINT NOT NULL REFERENCES kommune(kommune_id) ON DELETE RESTRICT,
	gnr			INTEGER NOT NULL CHECK (gnr > 0),
	bnr			INTEGER NOT NULL CHECK (bnr > 0),
	fnr			INTEGER CHECK (fnr IS NULL OR fnr >= 0),
	snr			INTEGER CHECK (snr IS NULL OR snr >= 0),
	enhetstype		TEXT NOT NULL CHECK (enhetstype IN ('grunneiendom','festegrunn','jordsameie','seksjon')),
	status			TEXT,
	-- Proveniens
	kilde			TEXT,
	kilde_ref		TEXT,
	sist_oppdatert	TIMESTAMPTZ,
	autorativ		BOOLEAN DEFAULT FALSE,
	created_at		TIMESTAMPTZ NOT NULL DEFAULT now(),
	updated_at		TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Ensure uniqueness across nullable fnr/snr using an expression index
CREATE UNIQUE INDEX IF NOT EXISTS ux_matrikkelenhet_natkey
	ON matrikkelenhet (kommune_id, gnr, bnr, COALESCE(fnr, 0), COALESCE(snr, 0));

CREATE INDEX IF NOT EXISTS ix_matrikkelenhet_kommune
	ON matrikkelenhet (kommune_id);

-- Bygning
CREATE TABLE IF NOT EXISTS bygning
(
	bygg_id		BIGSERIAL PRIMARY KEY,
	bygningsnr	BIGINT UNIQUE, -- Matrikkel bygningsnummer (unik nasjonalt)
	bydel_id	BIGINT REFERENCES bydel(bydel_id) ON DELETE SET NULL,
	bygningstype	TEXT,
	status		TEXT,
	geom_wkt	TEXT, -- WKT Polygon i EPSG:25833 (kan migreres til PostGIS senere)
	-- Proveniens
	kilde		TEXT,
	kilde_ref	TEXT,
	sist_oppdatert	TIMESTAMPTZ,
	autorativ	BOOLEAN DEFAULT FALSE,
	created_at	TIMESTAMPTZ NOT NULL DEFAULT now(),
	updated_at	TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_bygning_bygningsnr
	ON bygning (bygningsnr);

CREATE INDEX IF NOT EXISTS ix_bygning_bydel
	ON bygning (bydel_id);

-- (Ingen spatial indeks uten PostGIS)

CREATE TABLE IF NOT EXISTS gate
(
	gate_id		BIGSERIAL PRIMARY KEY,
	kommune_id	BIGINT NOT NULL REFERENCES kommune(kommune_id) ON DELETE CASCADE,
	navn			TEXT NOT NULL,
	created_at		TIMESTAMPTZ NOT NULL DEFAULT now(),
	updated_at		TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- Adresse (under bygning; en bygning kan ha flere adresser/inn-/adkomstpunkt)
CREATE TABLE IF NOT EXISTS adresse
(
	adresse_id	BIGSERIAL PRIMARY KEY,
	bygg_id		BIGINT NOT NULL REFERENCES bygning(bygg_id) ON DELETE CASCADE,
	adressetype	TEXT NOT NULL CHECK (adressetype IN ('vegadresse','matrikkeladresse')),
	gate_id		BIGINT NOT NULL REFERENCES gate(gate_id) ON DELETE CASCADE,
	husnr		TEXT,
	bokstav		CHAR(1),
	postnummer	CHAR(4) CHECK (postnummer ~ '^[0-9]{4}$'),
	poststed	TEXT,
	lat		DOUBLE PRECISION CHECK (lat IS NULL OR (lat >= -90 AND lat <= 90)),
	lon		DOUBLE PRECISION CHECK (lon IS NULL OR (lon >= -180 AND lon <= 180)),
	srid		INTEGER DEFAULT 4258, -- ETRS89
	ekstern_id	TEXT, -- f.eks. adressenummer-ID fra Kartverket
	-- Proveniens
	kilde		TEXT,
	kilde_ref	TEXT,
	sist_oppdatert	TIMESTAMPTZ,
	autorativ	BOOLEAN DEFAULT FALSE,
	created_at	TIMESTAMPTZ NOT NULL DEFAULT now(),
	updated_at	TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_adresse_bygg
	ON adresse (bygg_id);

CREATE INDEX IF NOT EXISTS ix_adresse_postnummer
	ON adresse (postnummer);

CREATE INDEX IF NOT EXISTS ix_adresse_lon_lat
	ON adresse (lon, lat);


-- Bruksenhet (primært knyttet til matrikkelenhet i Matrikkel)
CREATE TABLE IF NOT EXISTS bruksenhet
(
	bruksenhet_id	BIGSERIAL PRIMARY KEY,
	bygg_id		BIGINT NOT NULL REFERENCES bygning(bygg_id) ON DELETE CASCADE,
	matrikkelenhet_id	BIGINT NOT NULL REFERENCES matrikkelenhet(enhet_id) ON DELETE CASCADE,
	snr				INTEGER, -- seksjons-/bruksenhetsnummer der relevant
	areal_m2		NUMERIC(10, 2),
	brukstype		TEXT,
	-- Proveniens
	kilde			TEXT,
	kilde_ref		TEXT,
	sist_oppdatert	TIMESTAMPTZ,
	autorativ		BOOLEAN DEFAULT FALSE,
	created_at		TIMESTAMPTZ NOT NULL DEFAULT now(),
	updated_at		TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_bruksenhet_bygg
	ON bruksenhet (bygg_id);

-- FDV-utvidelser
CREATE TABLE IF NOT EXISTS floy
(
	floy_id	BIGSERIAL PRIMARY KEY,
	bygg_id	BIGINT NOT NULL REFERENCES bygning(bygg_id) ON DELETE CASCADE,
	kode	TEXT NOT NULL,
	navn	TEXT,
	created_at	TIMESTAMPTZ NOT NULL DEFAULT now(),
	updated_at	TIMESTAMPTZ NOT NULL DEFAULT now(),
	CONSTRAINT uniq_floy_per_bygg UNIQUE (bygg_id, kode)
);

CREATE TABLE IF NOT EXISTS etasje
(
	etasje_id	BIGSERIAL PRIMARY KEY,
	bygg_id		BIGINT NOT NULL REFERENCES bygning(bygg_id) ON DELETE CASCADE,
	nummer		TEXT NOT NULL,
	betegnelse	TEXT,
	created_at	TIMESTAMPTZ NOT NULL DEFAULT now(),
	updated_at	TIMESTAMPTZ NOT NULL DEFAULT now(),
	CONSTRAINT uniq_etasje_per_bygg UNIQUE (bygg_id, nummer)
);

CREATE TABLE IF NOT EXISTS rom
(
	rom_id		BIGSERIAL PRIMARY KEY,
	etasje_id	BIGINT NOT NULL REFERENCES etasje(etasje_id) ON DELETE CASCADE,
	floy_id		BIGINT REFERENCES floy(floy_id) ON DELETE SET NULL,
	adresse_id	BIGINT NOT NULL REFERENCES adresse(adresse_id) ON DELETE CASCADE,
	nummer		TEXT NOT NULL,
	navn		TEXT,
	areal_m2	NUMERIC(10, 2),
	created_at	TIMESTAMPTZ NOT NULL DEFAULT now(),
	updated_at	TIMESTAMPTZ NOT NULL DEFAULT now(),
	CONSTRAINT uniq_rom_per_etasje UNIQUE (etasje_id, nummer)
);

CREATE TABLE IF NOT EXISTS rom_detaljer
(
	rom_id		BIGINT PRIMARY KEY REFERENCES rom(rom_id) ON DELETE CASCADE,
	brukstype	TEXT,
	kommentar	TEXT,
	hoyde_m	NUMERIC(6, 2),
	ant_personer INTEGER,
	radonklasse	TEXT,
	created_at	TIMESTAMPTZ NOT NULL DEFAULT now(),
	updated_at	TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Note: Triggers to auto-update updated_at can be added in a later migration.

-- Uteområder (park, lekeplass, ballbane m.m.)
CREATE TABLE IF NOT EXISTS uteomrade
(
	uteomrade_id	BIGSERIAL PRIMARY KEY,
	bydel_id		BIGINT REFERENCES bydel(bydel_id) ON DELETE SET NULL,
	navn			TEXT NOT NULL,
	omradetype		TEXT NOT NULL CHECK (omradetype IN ('park','lekeplass','fotballbane','idrettsanlegg','grontomrade','torg','friomrade')),
	status			TEXT,
	geom_wkt		TEXT, -- WKT Polygon i EPSG:25833
	lon			DOUBLE PRECISION CHECK (lon IS NULL OR (lon >= -180 AND lon <= 180)),
	lat			DOUBLE PRECISION CHECK (lat IS NULL OR (lat >= -90 AND lat <= 90)),
	srid			INTEGER DEFAULT 4258,
	ekstern_id		TEXT, -- ID fra kommunal WFS/Geonorge/OSM
	egenskaper		JSONB,
	-- Proveniens
	kilde			TEXT,
	kilde_ref		TEXT,
	sist_oppdatert	TIMESTAMPTZ,
	autorativ		BOOLEAN DEFAULT FALSE,
	created_at		TIMESTAMPTZ NOT NULL DEFAULT now(),
	updated_at		TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_uteomrade_bydel
	ON uteomrade (bydel_id);

CREATE INDEX IF NOT EXISTS ix_uteomrade_type
	ON uteomrade (omradetype);

CREATE INDEX IF NOT EXISTS ix_uteomrade_lon_lat
	ON uteomrade (lon, lat);

-- Kobling til matrikkelenhet (mange-til-mange)
CREATE TABLE IF NOT EXISTS uteomrade_matrikkelenhet
(
	uteomrade_id	BIGINT NOT NULL REFERENCES uteomrade(uteomrade_id) ON DELETE CASCADE,
	enhet_id		BIGINT NOT NULL REFERENCES matrikkelenhet(enhet_id) ON DELETE CASCADE,
	merknad			TEXT,
	PRIMARY KEY (uteomrade_id, enhet_id)
);

-- Adkomstpunkter til uteområde (innganger, porter, parkering)
CREATE TABLE IF NOT EXISTS adkomstpunkt
(
	adkomstpunkt_id	BIGSERIAL PRIMARY KEY,
	uteomrade_id		BIGINT NOT NULL REFERENCES uteomrade(uteomrade_id) ON DELETE CASCADE,
	gate_id			BIGINT REFERENCES gate(gate_id) ON DELETE SET NULL,
	type			TEXT NOT NULL CHECK (type IN ('inngang','port','rampe','parkering','annet')),
	beskrivelse		TEXT,
	lon			DOUBLE PRECISION CHECK (lon IS NULL OR (lon >= -180 AND lon <= 180)),
	lat			DOUBLE PRECISION CHECK (lat IS NULL OR (lat >= -90 AND lat <= 90)),
	srid			INTEGER DEFAULT 4258,
	-- Proveniens
	kilde			TEXT,
	kilde_ref		TEXT,
	sist_oppdatert	TIMESTAMPTZ,
	autorativ		BOOLEAN DEFAULT FALSE,
	created_at		TIMESTAMPTZ NOT NULL DEFAULT now(),
	updated_at		TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_adkomstpunkt_uteomrade
	ON adkomstpunkt (uteomrade_id);

CREATE INDEX IF NOT EXISTS ix_adkomstpunkt_lon_lat
	ON adkomstpunkt (lon, lat);
