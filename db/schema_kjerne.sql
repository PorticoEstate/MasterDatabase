-- Masterdatabase for kommunale lokaler — kjernemodell
-- PostgreSQL 12+ med PostGIS 3.x. Testet mot PostgreSQL 18 / PostGIS 3.6.
--
-- 18 tabeller. Alle får data, enten fra Aktiv kommune-endepunktene eller fra
-- matrikkelen. Se db/schema_kjerne_dokumentasjon.md.
--
-- To kilder, to roller:
--   Aktiv kommune  definerer tilbudet  (hvilke lokaler finnes, hva heter de)
--   Matrikkelen    definerer bygget    (bygningsnr, type, byggeår, areal, punkt)
--
-- Navnekonvensjon: hver tabells primærnøkkel heter "id". En fremmednøkkel
-- heter <tabellnavn som den refererer>_id, f.eks. "kommune_id" på en tabell
-- som peker til kommune. Unntak: selvrefererende hierarkikolonner (f.eks.
-- lokaletype.parent_id) heter "parent_id" for lesbarhet, ikke "lokaletype_id".
--
-- Geometri: punkter lagres som geography(Point, 4326), ikke lat/lon-tall i to
-- kolonner. En geography-verdi kan ikke være "halvveis utfylt" (i motsetning
-- til to nullbare tall), bærer sitt eget koordinatsystem, og støtter ekte
-- avstands- og radiussøk (ST_DWithin, <->) med en GiST-indeks, i stedet for
-- de grove rektangelsøkene en vanlig indeks på (lon, lat) er begrenset til.

CREATE EXTENSION IF NOT EXISTS postgis;
-- Trigram-indeks på ressurs.navn: dekker det sokevektor (se der) ikke kan,
-- siden norsk er et sammensatt-ord-språk og Postgres' innebygde stemmer ikke
-- splitter dem - "svømme" stammer ikke til samme rot som "svømmebasseng".
-- Trigram gir substreng-/fuzzy-treff uavhengig av ord-grenser.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Senket fra standard 0.3: et søk uten æøå ("svomme" for "svømme") endrer
-- 3 av 7 trigram og lander på ~0.2 - rett under standardterskelen, så treffet
-- ville ellers blitt filtrert bort tross at det er det brukeren mente.
-- Satt på databasen, ikke per spørring, så alle `%`-søk får dette automatisk.
ALTER DATABASE masterdb SET pg_trgm.similarity_threshold = 0.2;


CREATE OR REPLACE FUNCTION sett_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;


-- =============================================================================
-- 1. Kildesystem og kommune
--
-- Ekte mange-til-mange: en kommune kan ha flere fagsystem-instanser (booking,
-- fdv, sensor, ...), og én instans kan betjene flere kommuner. "Hvilken av
-- kommunens instanser er booking-instansen" avgjøres ved å filtrere på
-- fagsystem_instans.type - ikke med et eget "kontekst"-begrep. En kommune kan
-- likevel bare ha én instans PER TYPE: uniq_kommune_fagsystem_type håndhever
-- det ved at typen er kopiert inn i koblingstabellen.
-- =============================================================================

-- Én rad per fagsysteminstallasjon (booking, fdv, sensor, ...). kildenokkel
-- ('aktiv-kommune:bergen') brukes som kildemerking ellers i basen. Instansen
-- er nødvendig i nøklene fordi de lokale ID-ene overlapper: ressurs 438
-- finnes i flere instanser.
CREATE TABLE IF NOT EXISTS fagsystem_instans
(
    id           BIGSERIAL PRIMARY KEY,
    kildenokkel  TEXT UNIQUE NOT NULL,
    type         TEXT NOT NULL CHECK (type IN ('booking','fdv','sensor','annet')),
    navn         TEXT,
    base_url     TEXT NOT NULL,
    aktiv        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kommune
(
    id           BIGSERIAL PRIMARY KEY,
    kommunenr    CHAR(4) UNIQUE NOT NULL CHECK (kommunenr ~ '^[0-9]{4}$'),
    navn         TEXT NOT NULL,
    fylkesnavn   TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Koblingstabell: hvilke instanser betjener hvilke kommuner. "type" er en
-- kopi av fagsystem_instans.type, satt ved innsetting - ikke en uavhengig
-- verdi. Kopien finnes bare for at UNIQUE (kommune_id, type) skal kunne
-- håndheve "maks én instans per type per kommune"; Postgres kan ikke
-- håndheve en unik-regel som refererer en kolonne i en annen tabell direkte.

CREATE TABLE IF NOT EXISTS kommune_fagsystem_instans
(
    kommune_id           BIGINT NOT NULL REFERENCES kommune(id) ON DELETE CASCADE,
    fagsystem_instans_id BIGINT NOT NULL REFERENCES fagsystem_instans(id) ON DELETE CASCADE,
    type                 TEXT NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Primærnøkkelen er samtidig målet for de sammensatte fremmednøklene fra
    -- bygning og ressurs - ingen egen indeks trengs for det.
    PRIMARY KEY (kommune_id, fagsystem_instans_id),
    CONSTRAINT uniq_kommune_fagsystem_type UNIQUE (kommune_id, type)
);

CREATE INDEX IF NOT EXISTS ix_kommune_fagsystem_instans_instans
    ON kommune_fagsystem_instans (fagsystem_instans_id);

-- =============================================================================
-- 2. Matrikkel
-- =============================================================================

CREATE TABLE IF NOT EXISTS matrikkelinfo
(
    id             BIGSERIAL PRIMARY KEY,
    kommunenr      CHAR(4) NOT NULL CHECK (kommunenr ~ '^[0-9]{4}$'),
    gardsnr        INTEGER NOT NULL,
    bruksnr        INTEGER NOT NULL,
    festenr        INTEGER,
    seksjonsnr     INTEGER,
    sist_oppdatert TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- COALESCE fordi festenr og seksjonsnr er NULL for vanlige grunneiendommer, og
-- NULL regnes ikke som lik NULL i en unik indeks. Uten dette ville samme
-- eiendom kunne lagres mange ganger.
CREATE UNIQUE INDEX IF NOT EXISTS ux_matrikkelinfo
    ON matrikkelinfo (kommunenr, gardsnr, bruksnr,
                       COALESCE(festenr, 0), COALESCE(seksjonsnr, 0));

-- =============================================================================
-- 3. Bygning
--
-- Holder både bygg og utendørs anlegg. Aktiv kommune har bare ett stedsbegrep:
-- "Paradis kunstgressbane" er registrert som et bygg der, på linje med ekte
-- bygninger. Vi skiller dem ikke på bygningsnivå - kildedata har ingen felt
-- som sier "dette er utendørs", og et bygg kan i praksis romme både en hall
-- og en utendørs kunstgressbane under samme adresse. Innendørs/utendørs
-- avgjøres derfor per ressurs, via ressurs.lokaletype_id (se UTEAREAL-gruppen
-- og de utendørs-spesifikke kodene i lokaletype).
--
-- Identitet: (fagsystem_instans_id, ekstern_id) fra bookingsystemet.
-- bygningsnr er en referanse til matrikkelen, ikke en identitet: flere
-- Aktiv kommune-bygg (f.eks. hall og bane) kan ligge i samme matrikkelbygg.
-- =============================================================================

CREATE TABLE IF NOT EXISTS bygning
(
    id             BIGSERIAL PRIMARY KEY,
    kommune_id     BIGINT NOT NULL REFERENCES kommune(id) ON DELETE CASCADE,
    navn           TEXT NOT NULL,
    bydel_navn     TEXT,

    -- Fra Aktiv kommune. NULL for bygg som bare er kjent fra matrikkelen.
    -- Ingen direkte REFERENCES her - konsistens med kommunens instans
    -- håndheves av den sammensatte fremmednøkkelen nedenfor.
    fagsystem_instans_id BIGINT,
    ekstern_id     TEXT,

    -- Fra matrikkelen
    bygningsnr     BIGINT,
    bygningstype   TEXT,
    bra_m2         NUMERIC(12,2) CHECK (bra_m2 IS NULL OR bra_m2 >= 0),
    geom_wkt       TEXT,

	-- Hvilket nivå koblingen mot matrikkelen ble funnet på: bygningsnr (fra
	-- cadastral_references), gnr_bnr, adresse, manuell - eller ikke_funnet.

    matrikkel_match TEXT NOT NULL DEFAULT 'ikke_forsokt'
                       CHECK (matrikkel_match IN
                           ('ikke_forsokt', 'bygningsnr', 'gnr_bnr' , 'adresse', 'manuell', 'ikke_funnet')),
    -- Fra matrikkelen: antall etasjer i bygget som helhet (ikke en egen rad
    -- per etasje - kilden har bare et tall her).
    antall_etasjer INTEGER CHECK (antall_etasjer IS NULL OR antall_etasjer > 0),

    -- Representasjonspunktet for bygget. geography (ikke geometry) fordi
    -- ST_DWithin og <-> da gir avstand i meter direkte, uten at man selv må
    -- velge riktig projeksjon/UTM-sone for å få korrekt avstand.
    posisjon       geography(Point, 4326),

    aktiv          BOOLEAN NOT NULL DEFAULT TRUE,
    sist_oppdatert TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Mål for ressurs.fk_ressurs_bygning.
    CONSTRAINT uq_bygning_kommune UNIQUE (id, kommune_id),
    -- Bygget kan bare tilhøre en instans som faktisk betjener kommunen bygget
    -- ligger i. Ikke håndhevet når fagsystem_instans_id er NULL (bygg fra
    -- matrikkelen, uten booking-tilknytning).
    CONSTRAINT fk_bygning_fagsystem_instans_kommune FOREIGN KEY (kommune_id, fagsystem_instans_id)
        REFERENCES kommune_fagsystem_instans (kommune_id, fagsystem_instans_id)
);

-- Identitet fra bookingsystemet, unik per instans.
CREATE UNIQUE INDEX IF NOT EXISTS ux_bygning_ekstern
    ON bygning (fagsystem_instans_id, ekstern_id)
    WHERE fagsystem_instans_id IS NOT NULL AND ekstern_id IS NOT NULL;

-- Ikke unik: flere Aktiv kommune-bygg (f.eks hall og bane) kan ligge i samme
-- matrikkelbygg. Indeksen finnes for oppslag ved matrikkelkobling.
CREATE INDEX IF NOT EXISTS ix_bygning_bygningsnr
    ON bygning (bygningsnr)
    WHERE bygningsnr IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_bygning_kommune ON bygning (kommune_id);
-- GiST, ikke btree: nødvendig for ST_DWithin/<-> (nærhetssøk) skal kunne
-- bruke indeksen. En vanlig btree-indeks kan ikke svare på "innenfor 5 km".
CREATE INDEX IF NOT EXISTS ix_bygning_posisjon ON bygning USING GIST (posisjon);

-- =============================================================================
-- 4. Gate har mange adresser (adresse.gate_id). Identiteten er
-- (kommune, adressekode) fra matrikkelen, ikke navnet: samme gatenavn kan
-- finnes flere ganger i en kommune, og samme adressekode brukes i flere
-- kommuner. Postnummer ligger på adresse, ikke her, siden en gate kan krysse
-- flere postnummer.
-- =============================================================================

CREATE TABLE IF NOT EXISTS gate
(
    id       BIGSERIAL PRIMARY KEY,
    kommune_id BIGINT NOT NULL REFERENCES kommune(id) ON DELETE CASCADE,
    adressekode INTEGER NOT NULL,
    gatenavn TEXT NOT NULL,
	created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
   	updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
 CONSTRAINT uq_gate_kommune_adressekode UNIQUE (kommune_id, adressekode)
);

CREATE INDEX IF NOT EXISTS ix_gate_navn
ON gate (kommune_id, lower(gatenavn));
-- Et bygg kan stå på flere eiendommer, og en eiendom kan ha flere bygg.
CREATE TABLE IF NOT EXISTS bygning_matrikkelinfo
(
    bygning_id       BIGINT NOT NULL REFERENCES bygning(id) ON DELETE CASCADE,
    matrikkelinfo_id BIGINT NOT NULL REFERENCES matrikkelinfo(id) ON DELETE CASCADE,
    rolle            TEXT,
    PRIMARY KEY (bygning_id, matrikkelinfo_id)
);

CREATE INDEX IF NOT EXISTS ix_bygning_matrikkelinfo_enhet
    ON bygning_matrikkelinfo (matrikkelinfo_id);


-- =============================================================================
-- 5. Adresse
--
-- Egen tabell, ikke kolonner på bygning, fordi matrikkelen gir flere adresser
-- per bygg (flere innganger) og fordi representasjonspunktet hører til adressen.
-- Hver adresse tilhører én bygning og (etter geokoding/etter matrikkelkobling) én gate. Et hjørnebygg
-- med innganger i to gater har to adresser.
-- =============================================================================

CREATE TABLE IF NOT EXISTS adresse
(
    id             BIGSERIAL PRIMARY KEY,
    bygning_id     BIGINT NOT NULL REFERENCES bygning(id) ON DELETE CASCADE,
	-- NULL før geokoding har funnet gaten:
	gate_id 		BIGINT REFERENCES gate(id) ON DELETE SET NULL,
    adressetekst   TEXT,
    husnr          INTEGER,
    bokstav        CHAR(1),
    postnummer     CHAR(4) CHECK (postnummer IS NULL OR postnummer ~ '^[0-9]{4}$'),
    poststed       TEXT,
    posisjon       geography(Point, 4326),
    -- Kildedata har ingen koordinater i det hele tatt, så punktet må slås opp.
    -- Statusen gjør at en senere matrikkelimport trygt kan overskrive et
    -- geokodet punkt, men ikke et autoritativt representasjonspunkt.
    geokoding      TEXT NOT NULL DEFAULT 'ukjent'
                       CHECK (geokoding IN ('ukjent','matrikkel','geokodet','manuell','feilet')),
    er_hovedadresse BOOLEAN NOT NULL DEFAULT FALSE,
    ekstern_id     TEXT,
    sist_oppdatert TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_adresse_hovedadresse
    ON adresse (bygning_id) WHERE er_hovedadresse;
CREATE UNIQUE INDEX IF NOT EXISTS ux_adresse_ekstern
	ON adresse (bygning_id, ekstern_id) WHERE ekstern_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_adresse_bygning ON adresse (bygning_id);
CREATE INDEX IF NOT EXISTS ix_adresse_gate ON adresse (gate_id);
CREATE INDEX IF NOT EXISTS ix_adresse_postnummer ON adresse (postnummer);
CREATE INDEX IF NOT EXISTS ix_adresse_posisjon ON adresse USING GIST (posisjon);


-- =============================================================================
-- 6. Kanoniske søkefasetter
--
-- Kjernen i tverrkommunalt søk. Hver kommune har sitt eget kodeverk der samme
-- ID betyr ulike ting: kategori 13 er "Overnatting" i Bergen og "Skateanlegg" i
-- Stavanger, og 58 av 63 ID-er kolliderer slik. Master eier derfor ett kuratert
-- kodeverk, og de lokale kodene oversettes inn mot det i seksjon 6.
-- =============================================================================

CREATE TABLE IF NOT EXISTS lokaletype
(
    id         BIGSERIAL PRIMARY KEY,
    kode       TEXT UNIQUE NOT NULL,
    navn       TEXT NOT NULL,
    -- Selvreferanse for hierarki (IDRETT -> GYMSAL). Heter "parent_id", ikke
    -- "lokaletype_id", for å skille den tydelig fra en referanse til en annen
    -- tabell.
    parent_id  BIGINT REFERENCES lokaletype(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS aktivitet
(
    id         BIGSERIAL PRIMARY KEY,
    kode       TEXT UNIQUE NOT NULL,
    navn       TEXT NOT NULL,
    parent_id  BIGINT REFERENCES aktivitet(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fasilitet
(
    id         BIGSERIAL PRIMARY KEY,
    kode       TEXT UNIQUE NOT NULL,
    navn       TEXT NOT NULL,
    gruppe     TEXT NOT NULL CHECK (gruppe IN
                   ('tilgjengelighet','sanitaer','teknisk','kjokken','sport','moblering','uteareal','annet')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- =============================================================================
-- 7. Lokale kildekoder og oversettelse
-- =============================================================================

-- Kommunens egen kode, lagret uendret for sporbarhet. Instansen er med i
-- nøkkelen så Bergens 13 og Stavangers 13 kan ligge side om side.
CREATE TABLE IF NOT EXISTS kildekode
(
    id                   BIGSERIAL PRIMARY KEY,
    fagsystem_instans_id BIGINT NOT NULL REFERENCES fagsystem_instans(id) ON DELETE CASCADE,
    kodetype             TEXT NOT NULL CHECK (kodetype IN ('lokaletype','aktivitet','fasilitet')),
    kode                 TEXT NOT NULL,
    navn                 TEXT NOT NULL,
    sist_sett            TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uniq_kildekode UNIQUE (fagsystem_instans_id, kodetype, kode)
);

CREATE INDEX IF NOT EXISTS ix_kildekode_navn ON kildekode (lower(navn));

-- Oversettelsen er en menneskelig vurdering, ikke en beregning. Derfor bærer
-- den status og hvem som bestemte den.
-- 'ikke_relevant' finnes fordi kategorilistene inneholder verdier som ikke er
-- lokaletyper: "Stengt", "Fiktivt rom", "Streaming", og stedsnavn som
-- "Judaberg innbyggertorg".
--
-- Egen "id" pluss en UNIQUE "kildekode_id", i stedet for å la kildekode_id
-- være primærnøkkel direkte: det holder mønsteret "PK heter id, FK heter
-- <tabell>_id" konsekvent, selv om denne tabellen i praksis er en ett-til-én
-- utvidelse av kildekode.
CREATE TABLE IF NOT EXISTS kildekode_mapping
(
    id            BIGSERIAL PRIMARY KEY,
    kildekode_id  BIGINT UNIQUE NOT NULL REFERENCES kildekode(id) ON DELETE CASCADE,
    lokaletype_id BIGINT REFERENCES lokaletype(id) ON DELETE CASCADE,
    aktivitet_id  BIGINT REFERENCES aktivitet(id) ON DELETE CASCADE,
    fasilitet_id  BIGINT REFERENCES fasilitet(id) ON DELETE CASCADE,
    status        TEXT NOT NULL DEFAULT 'foreslatt'
                      CHECK (status IN ('foreslatt','godkjent','ikke_relevant')),
    kartlagt_av   TEXT,
    merknad       TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_mapping_ett_mal
        CHECK (
            (CASE WHEN lokaletype_id IS NOT NULL THEN 1 ELSE 0 END)
          + (CASE WHEN aktivitet_id IS NOT NULL THEN 1 ELSE 0 END)
          + (CASE WHEN fasilitet_id IS NOT NULL THEN 1 ELSE 0 END)
          = CASE WHEN status = 'ikke_relevant' THEN 0 ELSE 1 END
        )
);

CREATE INDEX IF NOT EXISTS ix_mapping_lokaletype ON kildekode_mapping (lokaletype_id);
CREATE INDEX IF NOT EXISTS ix_mapping_status ON kildekode_mapping (status);


-- =============================================================================
-- 8. Ressurs: det søkbare og bookbare
--
-- fagsystem_instans_id og ekstern_id gir både identitet og ruting: base_url
-- fra instansen pluss ekstern_id gir bookinglenken. Ingen egen rutingtabell
-- trengs så lenge det finnes én bookingleverandør og én kontekst.
-- =============================================================================

CREATE TABLE IF NOT EXISTS ressurs
(
    id                   BIGSERIAL PRIMARY KEY,
    fagsystem_instans_id BIGINT NOT NULL REFERENCES fagsystem_instans(id) ON DELETE CASCADE,
    ekstern_id           TEXT NOT NULL,
    -- kommune_id er ikke utledbar fra instansen alene, siden én instans kan
    -- betjene flere kommuner. Den må settes fra adressen ved innlasting.
    kommune_id           BIGINT NOT NULL REFERENCES kommune(id) ON DELETE CASCADE,
    bygning_id           BIGINT,
    navn                 TEXT NOT NULL,
    lokaletype_id        BIGINT REFERENCES lokaletype(id) ON DELETE SET NULL,

    areal_m2        NUMERIC(10,2) CHECK (areal_m2 IS NULL OR areal_m2 >= 0),
    beskrivelse     TEXT,

    aktiv          BOOLEAN NOT NULL DEFAULT TRUE,
    bookbar        BOOLEAN NOT NULL DEFAULT TRUE,
    sist_oppdatert TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    sokevektor     tsvector GENERATED ALWAYS AS (
                       to_tsvector('norwegian',
                           coalesce(navn,'') || ' ' || coalesce(beskrivelse,''))
                   ) STORED,

    -- Sammensatt fremmednøkkel: hindrer at en ressurs havner i et bygg som
    -- ligger i en annen kommune enn ressursen selv.
    CONSTRAINT fk_ressurs_bygning FOREIGN KEY (bygning_id, kommune_id)
        REFERENCES bygning (id, kommune_id),
    -- Ressursen kan bare høre til en kommune instansen faktisk betjener.
    CONSTRAINT fk_ressurs_fagsystem_instans_kommune FOREIGN KEY (kommune_id, fagsystem_instans_id)
        REFERENCES kommune_fagsystem_instans (kommune_id, fagsystem_instans_id),
    CONSTRAINT uniq_ressurs_ekstern UNIQUE (fagsystem_instans_id, ekstern_id)
);

CREATE INDEX IF NOT EXISTS ix_ressurs_kommune ON ressurs (kommune_id);
CREATE INDEX IF NOT EXISTS ix_ressurs_bygning ON ressurs (bygning_id);
CREATE INDEX IF NOT EXISTS ix_ressurs_sokevektor ON ressurs USING GIN (sokevektor);
-- Trigram-indeks på navn, for substreng-/fuzzy-søk som sokevektor ikke
-- fanger opp (sammensatte ord, stavefeil) - se kommentar ved pg_trgm over.
CREATE INDEX IF NOT EXISTS ix_ressurs_navn_trgm ON ressurs USING GIN (navn gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_ressurs_sok
    ON ressurs (lokaletype_id, kommune_id) WHERE aktiv AND bookbar;

CREATE TABLE IF NOT EXISTS ressurs_aktivitet
(
    ressurs_id   BIGINT NOT NULL REFERENCES ressurs(id) ON DELETE CASCADE,
    aktivitet_id BIGINT NOT NULL REFERENCES aktivitet(id) ON DELETE CASCADE,
    PRIMARY KEY (ressurs_id, aktivitet_id)
);

CREATE INDEX IF NOT EXISTS ix_ressurs_aktivitet_akt ON ressurs_aktivitet (aktivitet_id);

CREATE TABLE IF NOT EXISTS ressurs_fasilitet
(
    ressurs_id   BIGINT NOT NULL REFERENCES ressurs(id) ON DELETE CASCADE,
    fasilitet_id BIGINT NOT NULL REFERENCES fasilitet(id) ON DELETE CASCADE,
    PRIMARY KEY (ressurs_id, fasilitet_id)
);

CREATE INDEX IF NOT EXISTS ix_ressurs_fasilitet_fas ON ressurs_fasilitet (fasilitet_id);


-- =============================================================================
-- 9. Innlasting og sporbarhet
-- =============================================================================

-- Metadata om én henting fra en kilde (kilde, endepunkt, tidspunkt,
-- HTTP-status). payload er valgfri og brukes ikke lenger til å lagre hele
-- kildens retur — den aktuelle posten bak et avvik lagres i stedet direkte på
-- avviket selv (synk_avvik.rapost), se der for begrunnelse.
CREATE TABLE IF NOT EXISTS kildeuttrekk
(
    id          BIGSERIAL PRIMARY KEY,
    kilde       TEXT NOT NULL,
    endepunkt   TEXT NOT NULL,
    hentet_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    http_status INTEGER,
    payload     JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_kildeuttrekk_kilde ON kildeuttrekk (kilde, hentet_at DESC);

-- searchdataall er et delvis uttrekk: koblingstabellene eksporteres komplett
-- mens bygg- og ressurslistene er filtrert. I Bergen peker 388 av 980
-- koblingsrader på ressurser som ikke finnes i uttrekket. De må filtreres bort,
-- men skal loggføres — hvis andelen endrer seg, har noe skjedd hos kommunen.
--
-- rapost er posten (eller postene) som utløste avviket, lagret direkte her av
-- innlastingsskriptet idet avviket oppdages — ikke hele kildens retur lagret
-- et annet sted og gravd ut igjen i ettertid. Det holder avviksbevis uavhengig
-- av hvor lenge det tilhørende kildeuttrekket beholdes, og lar kildeuttrekk
-- forbli ren metadata. SET NULL, ikke RESTRICT: et gammelt uttrekk skal kunne
-- ryddes bort uten at det blokkeres av avvik som uansett bærer sitt eget bevis.
CREATE TABLE IF NOT EXISTS synk_avvik
(
    id               BIGSERIAL PRIMARY KEY,
    kildeuttrekk_id  BIGINT REFERENCES kildeuttrekk(id) ON DELETE SET NULL,
    kilde            TEXT NOT NULL,
    samling          TEXT NOT NULL,
    avvikstype       TEXT NOT NULL CHECK (avvikstype IN
                          ('manglende_forelder','ikke_kartlagt','geokoding_feilet',
                           'ugyldig_verdi','db_feil','annet')),
    ekstern_id       TEXT,
    -- Feltet i posten som var galt (f.eks. 'zip_code'). NULL når hele posten er
    -- problemet.
    felt             TEXT,
    -- Hvilket felt i rapost som ekstern_id er verdien av. 'id' for bygg og
    -- ressurser; 'resource_id' / 'building_id' for koblingsradene, som ikke
    -- har noen egen id.
    nokkelfelt       TEXT NOT NULL DEFAULT 'id',
    detalj           TEXT,
    rapost           JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_synk_avvik_kilde ON synk_avvik (kilde, avvikstype);
CREATE INDEX IF NOT EXISTS ix_synk_avvik_uttrekk ON synk_avvik (kildeuttrekk_id);

-- Innlastingsskriptene skriver bare SQL og vet ikke hvilken id et uttrekk får.
-- Derfor registrerer første setning i hver fil uttrekket og husker id-en i en
-- transaksjonslokal innstilling, og alle avvik i samme transaksjon henter den
-- derfra. Virker også inne i DO-blokker, der psql-variabler ikke kan brukes.
CREATE OR REPLACE PROCEDURE registrer_kildeuttrekk(
    p_kilde TEXT, p_endepunkt TEXT, p_http_status INTEGER, p_payload JSONB,
    p_hentet_at TIMESTAMPTZ DEFAULT now())
LANGUAGE plpgsql AS $$
DECLARE
    ny_id BIGINT;
BEGIN
    INSERT INTO kildeuttrekk (kilde, endepunkt, hentet_at, http_status, payload)
    VALUES (p_kilde, p_endepunkt, p_hentet_at, p_http_status, p_payload)
    RETURNING id INTO ny_id;
    PERFORM set_config('masterdb.kildeuttrekk_id', ny_id::text, true);
END;
$$;

CREATE OR REPLACE PROCEDURE logg_avvik(
    p_kilde TEXT, p_samling TEXT, p_avvikstype TEXT, p_ekstern_id TEXT,
    p_detalj TEXT, p_felt TEXT DEFAULT NULL, p_nokkelfelt TEXT DEFAULT 'id',
    p_rapost JSONB DEFAULT NULL)
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO synk_avvik (kildeuttrekk_id, kilde, samling, avvikstype,
                            ekstern_id, felt, nokkelfelt, detalj, rapost)
    VALUES (NULLIF(current_setting('masterdb.kildeuttrekk_id', true), '')::bigint,
            p_kilde, p_samling, p_avvikstype, p_ekstern_id, p_felt,
            p_nokkelfelt, p_detalj, p_rapost);
END;
$$;

-- Beholder de p_behold nyeste uttrekkene per kilde, uforbeholdent - bevis for
-- avvik bor nå på selve avviket (synk_avvik.rapost), ikke i uttrekket, så
-- rydding trenger ikke lenger ta hensyn til avvik. Returnerer antall slettede
-- uttrekk. p_kilde = NULL rydder alle kilder.
CREATE OR REPLACE FUNCTION rydd_kildeuttrekk(p_kilde TEXT DEFAULT NULL, p_behold INTEGER DEFAULT 2)
RETURNS BIGINT LANGUAGE plpgsql AS $$
DECLARE
    antall BIGINT;
BEGIN
    DELETE FROM kildeuttrekk u
    WHERE (p_kilde IS NULL OR u.kilde = p_kilde)
      AND u.id NOT IN (SELECT n.id
                         FROM (SELECT id, row_number() OVER (
                                          PARTITION BY kilde ORDER BY hentet_at DESC, id DESC) AS rn
                                 FROM kildeuttrekk) n
                        WHERE n.rn <= p_behold);
    GET DIAGNOSTICS antall = ROW_COUNT;
    RETURN antall;
END;
$$;


-- =============================================================================
-- 10. Søkevisninger
-- =============================================================================

-- Alt et søk trenger i én flat rad per bookbar ressurs. Basetabellene bruker
-- bare "id" internt; visningen gir hver id et beskrivende navn i output, slik
-- at resultatet er lesbart uten å kjenne navnekonvensjonen i skjemaet.
CREATE OR REPLACE VIEW v_ressurs_sok AS
SELECT
    r.id                           AS ressurs_id,
    r.navn,
    r.beskrivelse,
    k.id                           AS kommune_id,
    k.kommunenr,
    k.navn                         AS kommune_navn,
    lt.kode                        AS lokaletype_kode,
    lt.navn                        AS lokaletype_navn,
    p.kode                         AS lokaletype_hovedgruppe,
    b.id                           AS bygg_id,
    b.navn                         AS bygg_navn,
    b.bydel_navn,
    -- Geografi til bruk i nærhetssøk (ST_DWithin, <-> mot et gitt punkt), samt
    -- lat/lon som vanlige tall for enkel visning uten PostGIS-funksjoner.
    COALESCE(a.posisjon, b.posisjon)                AS posisjon,
    ST_Y(COALESCE(a.posisjon, b.posisjon)::geometry) AS lat,
    ST_X(COALESCE(a.posisjon, b.posisjon)::geometry) AS lon,
    a.adressetekst,
    a.postnummer,
    a.poststed,
    fi.base_url || '/bookingfrontend/resource/' || r.ekstern_id AS booking_url,
    (SELECT array_agg(ak.kode ORDER BY ak.kode)
       FROM ressurs_aktivitet ra
       JOIN aktivitet ak ON ak.id = ra.aktivitet_id
      WHERE ra.ressurs_id = r.id) AS aktivitet_koder,
    (SELECT array_agg(f.kode ORDER BY f.kode)
       FROM ressurs_fasilitet rf
       JOIN fasilitet f ON f.id = rf.fasilitet_id
      WHERE rf.ressurs_id = r.id) AS fasilitet_koder,
    r.sokevektor,
    r.sist_oppdatert
FROM ressurs r
JOIN kommune k             ON k.id = r.kommune_id
JOIN fagsystem_instans fi  ON fi.id = r.fagsystem_instans_id
LEFT JOIN lokaletype lt    ON lt.id = r.lokaletype_id
LEFT JOIN lokaletype p     ON p.id = lt.parent_id
LEFT JOIN bygning b        ON b.id = r.bygning_id
LEFT JOIN adresse a        ON a.bygning_id = b.id AND a.er_hovedadresse
WHERE r.aktiv AND r.bookbar;

-- Arbeidslisten for kuratering. Hver rad er en lokal kode som ennå ikke kan
-- søkes på tvers av kommuner. Kildekoden hører til instansen, ikke til én
-- kommune, siden en instans kan betjene flere - kommunene listes derfor
-- sammenslått via oppslag i kommune_fagsystem_instans.
CREATE OR REPLACE VIEW v_ukartlagte_kildekoder AS
SELECT kk.id AS kildekode_id, fi.kildenokkel,
       (SELECT string_agg(k.navn, ', ' ORDER BY k.navn)
          FROM kommune_fagsystem_instans kfi
          JOIN kommune k ON k.id = kfi.kommune_id
         WHERE kfi.fagsystem_instans_id = fi.id) AS kommuner,
       kk.kodetype, kk.kode, kk.navn, kk.sist_sett
FROM kildekode kk
JOIN fagsystem_instans fi ON fi.id = kk.fagsystem_instans_id
LEFT JOIN kildekode_mapping m ON m.kildekode_id = kk.id
WHERE m.id IS NULL OR m.status = 'foreslatt';

-- Avvikene fra den siste kjøringen per kilde. Eldre avvik ligger fortsatt i
-- synk_avvik som historikk, men er ikke lenger "åpne": hvis feilen fortsatt
-- finnes, er den logget på nytt i den nyeste kjøringen.
CREATE OR REPLACE VIEW v_synk_avvik_gjeldende AS
SELECT a.*
FROM synk_avvik a
WHERE a.kildeuttrekk_id IN (
    SELECT DISTINCT ON (kilde) id
    FROM kildeuttrekk
    ORDER BY kilde, hentet_at DESC, id DESC);

-- Arbeidslisten for den som går gjennom avvik: avviket sammen med posten som
-- utløste det. "post" er rapost, lagret direkte på avviket idet det oppstod -
-- krever ikke lenger at kildeuttrekket det skjedde i fortsatt finnes.
CREATE OR REPLACE VIEW v_synk_avvik_detalj AS
SELECT a.id AS avvik_id, a.kilde, a.samling, a.avvikstype, a.ekstern_id, a.felt,
       a.detalj, a.rapost AS post, a.created_at,
       u.id AS kildeuttrekk_id, u.endepunkt, u.hentet_at
FROM synk_avvik a
LEFT JOIN kildeuttrekk u ON u.id = a.kildeuttrekk_id;


-- =============================================================================
-- 11. Kanonisk kodeverk (startsett)
--
-- Utledet fra de 142 distinkte kategorinavnene i de 12 Aktiv kommune-instansene,
-- slått sammen på tvers av målform, skrivefeil og synonymer.
-- =============================================================================

INSERT INTO lokaletype (kode, navn)
VALUES
    ('IDRETT','Idrett og fysisk aktivitet'),
    ('KULTUR','Kultur og scene'),
    ('UNDERVISNING','Undervisning og møte'),
    ('VERKSTED','Verksted og produksjon'),
    ('ARRANGEMENT','Selskap og arrangement'),
    ('BEVERTNING','Mat og bevertning'),
    ('NAERMILJO','Aktivitets- og nærmiljøhus'),
    ('UTEAREAL','Utendørs areal'),
    ('OVERNATTING','Overnatting og bolig'),
    ('ANNET_LOKALE','Kontor og andre lokaler'),
    ('UTSTYR','Utstyr')
ON CONFLICT (kode) DO NOTHING;

INSERT INTO lokaletype (kode, navn, parent_id)
SELECT v.kode, v.navn, p.id
FROM (VALUES
    ('IDRETTSHALL','Idrettshall','IDRETT'),
    ('GYMSAL','Gymsal','IDRETT'),
    ('SVOMMEANLEGG','Svømmeanlegg','IDRETT'),
    ('ISHALL','Ishall og isbane','IDRETT'),
    ('FRIIDRETTSANLEGG','Friidrettsanlegg','IDRETT'),
    ('FOTBALLBANE','Fotballbane','IDRETT'),
    ('BALLBANE','Ballbane og ballbinge','IDRETT'),
    ('TENNISANLEGG','Tennisanlegg','IDRETT'),
    ('STYRKEROM','Styrke- og treningsrom','IDRETT'),
    ('KAMPSPORTROM','Kampsportrom','IDRETT'),
    ('KLATREANLEGG','Klatreanlegg','IDRETT'),
    ('TURNANLEGG','Turnanlegg','IDRETT'),
    ('SKATEANLEGG','Skateanlegg','IDRETT'),
    ('SKYTEBANE','Skytebane','IDRETT'),
    ('SJOSPORTANLEGG','Sjøsportanlegg','IDRETT'),
    ('GARDEROBE','Garderobe','IDRETT'),

    ('KONSERTSAL','Konsertsal og kultursal','KULTUR'),
    ('SCENE','Scene','KULTUR'),
    ('AUDITORIUM','Auditorium og foredragssal','KULTUR'),
    ('OVINGSROM','Øvingsrom og musikkrom','KULTUR'),
    ('DANSESAL','Dansesal','KULTUR'),
    ('LYDSTUDIO','Lydstudio','KULTUR'),
    ('UTSTILLINGSLOKALE','Utstillingslokale og atelier','KULTUR'),
    ('BIBLIOTEK','Bibliotek','KULTUR'),
    ('FOAJE','Foajé','KULTUR'),

('KLASSEROM','Klasserom og undervisningsrom','UNDERVISNING'),
('GRUPPEROM','Grupperom og prosjektrom','UNDERVISNING'),
('MOTEROM','Møterom og konferanserom','UNDERVISNING'),
('DATAROM','Datarom','UNDERVISNING'),
('AULA','Aula','UNDERVISNING'),

('SLOYDSAL','Sløydsal','VERKSTED'),
('KUNSTVERKSTED','Kunst- og håndverksverksted','VERKSTED'),
('SYSTUE','Systue','VERKSTED'),
('MEDIEVERKSTED','Multimedia- og streamingverksted','VERKSTED'),
('FRISORSALONG','Frisørsalong','VERKSTED'),

('SELSKAPSLOKALE','Selskapslokale','ARRANGEMENT'),
('FORSAMLINGSLOKALE','Forsamlingslokale','ARRANGEMENT'),
('SEREMONIROM','Seremonirom','ARRANGEMENT'),
('BURSDAGSLOKALE','Bursdagslokale','ARRANGEMENT'),
('ARRANGEMENTSARENA','Arrangementsarena','ARRANGEMENT'),
('TORGPLASS','Torg og møteplass','ARRANGEMENT'),

('KJOKKEN','Kjøkken','BEVERTNING'),
('KANTINE','Kantine','BEVERTNING'),
('KAFE','Kafé og kiosk','BEVERTNING'),

('ALLAKTIVITETSHUS','Allaktivitetshus','NAERMILJO'),
('AKTIVITETSROM','Aktivitetsrom og flerbruksrom','NAERMILJO'),
('UNGDOMSLOKALE','Ungdomslokale','NAERMILJO'),
('DAGSENTER','Dagsenter og miljøstue','NAERMILJO'),
('INNBYGGERTORG','Innbyggertorg','NAERMILJO'),

('FRILUFTSOMRAADE','Friluftsområde','UTEAREAL'),
('UTEOMRAADE','Uteområde','UTEAREAL'),
('TURVEI','Turvei og løype','UTEAREAL'),
('GAPAHUK','Gapahuk og bålplass','UTEAREAL'),
('UTESCENE','Utendørsscene','UTEAREAL'),

('OVERNATTINGSROM','Overnattingsrom','OVERNATTING'),
('BEBOERROM','Beboerrom','OVERNATTING'),
('OVINGSLEILIGHET','Øvingsleilighet','OVERNATTING'),

('KONTOR','Kontor og arbeidsplass','ANNET_LOKALE'),
('BUTIKKLOKALE','Butikklokale','ANNET_LOKALE'),
('LAGER','Lager','ANNET_LOKALE'),
('GENERELT_LOKALE','Generelt lokale','ANNET_LOKALE'),

('SYKKEL','Sykkel og el-sykkel','UTSTYR'),
('KANO_KAJAKK','Kano og kajakk','UTSTYR'),
('FISKEUTSTYR','Fiskeutstyr','UTSTYR'),
('REDNINGSVEST','Redningsvest','UTSTYR'),
('LYDANLEGG','Lyd- og lysanlegg','UTSTYR'),
('ANNET_UTSTYR','Annet utstyr','UTSTYR')
) AS v(kode, navn, parent_kode)
JOIN lokaletype p ON p.kode = v.parent_kode
ON CONFLICT (kode) DO NOTHING;

INSERT INTO aktivitet (kode, navn)
VALUES
    ('IDRETT','Idrett'),
    ('KULTUR','Kultur'),
    ('OPPLARING','Opplæring og kurs'),
    ('MOTE','Møte og konferanse'),
    ('PRIVAT','Privat arrangement'),
    ('FRIVILLIGHET','Frivillighet og lag'),
    ('FRILUFT','Friluftsliv'),
    ('INTERNT','Internt kommunalt')
ON CONFLICT (kode) DO NOTHING;

INSERT INTO aktivitet (kode, navn, parent_id)
SELECT v.kode, v.navn, p.id
FROM (VALUES
    ('FOTBALL','Fotball','IDRETT'),
    ('HANDBALL','Håndball','IDRETT'),
    ('BASKETBALL','Basketball','IDRETT'),
    ('VOLLEYBALL','Volleyball','IDRETT'),
    ('TURN','Turn','IDRETT'),
    ('KAMPSPORT','Kampsport','IDRETT'),
    ('SVOMMING','Svømming','IDRETT'),
    ('FRIIDRETT','Friidrett','IDRETT'),
    ('ISHOCKEY','Ishockey og skøyter','IDRETT'),
    ('KLATRING','Klatring','IDRETT'),
    ('STYRKETRENING','Styrketrening','IDRETT'),
    ('TENNIS','Tennis','IDRETT'),
    ('SKYTING','Skyting','IDRETT'),
    ('DANS','Dans','KULTUR'),
    ('MUSIKK','Musikk og korps','KULTUR'),
    ('KOR','Kor og sang','KULTUR'),
    ('TEATER','Teater og revy','KULTUR'),
    ('KUNST_HANDVERK','Kunst, håndverk og media','KULTUR'),
    ('SPEIDER','Speider','FRILUFT'),
    ('SYKLING','Sykling','FRILUFT')
) AS v(kode, navn, parent_kode)
JOIN aktivitet p ON p.kode = v.parent_kode
ON CONFLICT (kode) DO NOTHING;

INSERT INTO fasilitet (kode, navn, gruppe)
VALUES
    ('HC_TILGANG','Rullestoltilgang','tilgjengelighet'),
    ('HC_TOALETT','HC-toalett','tilgjengelighet'),
    ('TELESLYNGE','Teleslynge','tilgjengelighet'),
    ('HEIS','Heis','tilgjengelighet'),
    ('GARDEROBE','Garderobe','sanitaer'),
    ('DUSJ','Dusj','sanitaer'),
    ('TOALETT','Toalett','sanitaer'),
    ('PROSJEKTOR','Prosjektor','teknisk'),
    ('SKJERM','Skjerm','teknisk'),
    ('LYDANLEGG','Lydanlegg','teknisk'),
    ('MIKROFON','Mikrofon','teknisk'),
    ('WIFI','Trådløst nett','teknisk'),
    ('STREAMING','Streamingutstyr','teknisk'),
    ('FLYGEL','Flygel eller piano','teknisk'),
    ('SCENELYS','Scenelys','teknisk'),
    ('KJOKKEN','Kjøkken','kjokken'),
    ('KJOLESKAP','Kjøleskap','kjokken'),
    ('OPPVASKMASKIN','Oppvaskmaskin','kjokken'),
    ('KIOSK','Kiosk','kjokken'),
    ('TRIBUNE','Tribune','sport'),
    ('MAALBUR','Målbur','sport'),
    ('TIDTAKING','Tidtakingsanlegg','sport'),
    ('BANEDELING','Delbar bane','sport'),
    ('BORD_STOLER','Bord og stoler','moblering'),
    ('WHITEBOARD','Whiteboard','moblering'),
    ('PARKETTGULV','Parkettgulv','moblering'),
    ('PARKERING','Parkering','uteareal'),
    ('HC_PARKERING','HC-parkering','uteareal'),
    ('SYKKELPARKERING','Sykkelparkering','uteareal'),
    ('BAALPLASS','Bålplass','uteareal'),
    ('FLOMLYS','Flomlys','uteareal'),
    ('ELEKTRONISK_LAS','Elektronisk låssystem','annet')
ON CONFLICT (kode) DO NOTHING;

-- =============================================================================
-- 12. updated_at-triggere
-- =============================================================================

DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'kommune','fagsystem_instans', 'matrikkelinfo','bygning','gate','adresse',
        'lokaletype','aktivitet','fasilitet','kildekode','kildekode_mapping','ressurs'
    ]
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_%1$s_updated_at ON %1$I', t);
        EXECUTE format(
            'CREATE TRIGGER trg_%1$s_updated_at BEFORE UPDATE ON %1$I
             FOR EACH ROW EXECUTE FUNCTION sett_updated_at()', t);
    END LOOP;
END
$$;
