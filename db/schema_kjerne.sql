-- Masterdatabase for kommunale lokaler — kjernemodell
-- PostgreSQL 12+ med PostGIS 3.x. Testet mot PostgreSQL 18 / PostGIS 3.6.
--
-- 17 tabeller. Alle får data, enten fra Aktiv kommune-endepunktene eller fra
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

CREATE TABLE IF NOT EXISTS matrikkelenhet
(
    id             BIGSERIAL PRIMARY KEY,
    kommunenr      CHAR(4) NOT NULL CHECK (kommunenr ~ '^[0-9]{4}$'),
    gardsnr        INTEGER NOT NULL,
    bruksnr        INTEGER NOT NULL,
    festenr        INTEGER,
    seksjonsnr     INTEGER,
    enhetstype     TEXT CHECK (enhetstype IS NULL OR enhetstype IN
                       ('grunneiendom','festegrunn','seksjon','anleggseiendom','jordsameie')),
    areal_m2       NUMERIC(12,2) CHECK (areal_m2 IS NULL OR areal_m2 >= 0),
    geom_wkt       TEXT,
    ekstern_id     TEXT,
    sist_oppdatert TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- COALESCE fordi festenr og seksjonsnr er NULL for vanlige grunneiendommer, og
-- NULL regnes ikke som lik NULL i en unik indeks. Uten dette ville samme
-- eiendom kunne lagres mange ganger.
CREATE UNIQUE INDEX IF NOT EXISTS ux_matrikkelenhet
    ON matrikkelenhet (kommunenr, gardsnr, bruksnr,
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
-- Raden bærer to identiteter samtidig:
--   (fagsystem_instans_id, ekstern_id)  identiteten i kommunens bookingsystem
--   bygningsnr                          identiteten i matrikkelen
-- Derfor trengs ingen egen tabell for identitetskobling.
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
    hjemmeside     TEXT,
    -- Kun funksjonelle adresser. Navngitte kontaktpersoner (tilsyn_name m.fl.)
    -- er personopplysninger og lastes ikke inn.
    epost          TEXT,
    telefon        TEXT,
    apningstid_tekst TEXT,

    -- Fra matrikkelen
    bygningsnr     BIGINT,
    bygningstype   TEXT,
    byggeaar       INTEGER CHECK (byggeaar IS NULL OR byggeaar BETWEEN 800 AND 2200),
    bra_m2         NUMERIC(12,2) CHECK (bra_m2 IS NULL OR bra_m2 >= 0),
    geom_wkt       TEXT,
    -- Aktiv kommune oppgir ikke bygningsnummer, bare gateadresse. Kobling mot
    -- matrikkelen er derfor en kvalifisert gjetning som må kunne overprøves.
    matrikkel_match TEXT NOT NULL DEFAULT 'ikke_forsokt'
                       CHECK (matrikkel_match IN
                           ('ikke_forsokt','bekreftet','sannsynlig','usikker','ikke_funnet')),
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

-- Identitet fra matrikkelen, unik der den finnes. Partiell fordi de fleste bygg
-- mangler bygningsnr til matrikkelen er koblet på.
CREATE UNIQUE INDEX IF NOT EXISTS ux_bygning_bygningsnr
    ON bygning (bygningsnr)
    WHERE bygningsnr IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_bygning_kommune ON bygning (kommune_id);
-- GiST, ikke btree: nødvendig for ST_DWithin/<-> (nærhetssøk) skal kunne
-- bruke indeksen. En vanlig btree-indeks kan ikke svare på "innenfor 5 km".
CREATE INDEX IF NOT EXISTS ix_bygning_posisjon ON bygning USING GIST (posisjon);

-- Et bygg kan stå på flere eiendommer, og en eiendom kan ha flere bygg.
CREATE TABLE IF NOT EXISTS bygning_matrikkelenhet
(
    bygning_id       BIGINT NOT NULL REFERENCES bygning(id) ON DELETE CASCADE,
    matrikkelenhet_id BIGINT NOT NULL REFERENCES matrikkelenhet(id) ON DELETE CASCADE,
    rolle            TEXT,
    PRIMARY KEY (bygning_id, matrikkelenhet_id)
);

CREATE INDEX IF NOT EXISTS ix_bygning_matrikkelenhet_enhet
    ON bygning_matrikkelenhet (matrikkelenhet_id);


-- =============================================================================
-- 4. Adresse
--
-- Egen tabell, ikke kolonner på bygning, fordi matrikkelen gir flere adresser
-- per bygg (flere innganger) og fordi representasjonspunktet hører til adressen.
-- Gatenavn ligger som tekst; en egen gate-tabell tjener lite før noen skal
-- vedlikeholde gatenavn som eget register.
-- =============================================================================

CREATE TABLE IF NOT EXISTS adresse
(
    id             BIGSERIAL PRIMARY KEY,
    bygning_id     BIGINT NOT NULL REFERENCES bygning(id) ON DELETE CASCADE,
    adressetekst   TEXT,
    gatenavn       TEXT,
    husnr          TEXT,
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

CREATE INDEX IF NOT EXISTS ix_adresse_bygning ON adresse (bygning_id);
CREATE INDEX IF NOT EXISTS ix_adresse_postnummer ON adresse (postnummer);
CREATE INDEX IF NOT EXISTS ix_adresse_posisjon ON adresse USING GIST (posisjon);


-- =============================================================================
-- 5. Kanoniske søkefasetter
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
    sortering  INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS aktivitet
(
    id         BIGSERIAL PRIMARY KEY,
    kode       TEXT UNIQUE NOT NULL,
    navn       TEXT NOT NULL,
    parent_id  BIGINT REFERENCES aktivitet(id) ON DELETE SET NULL,
    sortering  INTEGER,
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
    sortering  INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- =============================================================================
-- 6. Lokale kildekoder og oversettelse
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
-- 7. Ressurs: det søkbare og bookbare
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

    -- Kapasitet er utfylt på under 1 % av ressursene i kilden, og Stavanger
    -- koder den som fasilitet ("Kapasitet 1-20"). Opphavet må følge verdien.
    kapasitet       INTEGER CHECK (kapasitet IS NULL OR kapasitet >= 0),
    kapasitet_kilde TEXT CHECK (kapasitet_kilde IS NULL OR kapasitet_kilde IN
                        ('kilde','utledet','manuell')),
    areal_m2        NUMERIC(10,2) CHECK (areal_m2 IS NULL OR areal_m2 >= 0),
    beskrivelse     TEXT,
    apningstid_tekst TEXT,

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
        REFERENCES bygning (id, kommune_id) ON DELETE SET NULL,
    -- Ressursen kan bare høre til en kommune instansen faktisk betjener.
    CONSTRAINT fk_ressurs_fagsystem_instans_kommune FOREIGN KEY (kommune_id, fagsystem_instans_id)
        REFERENCES kommune_fagsystem_instans (kommune_id, fagsystem_instans_id),
    CONSTRAINT uniq_ressurs_ekstern UNIQUE (fagsystem_instans_id, ekstern_id)
);

CREATE INDEX IF NOT EXISTS ix_ressurs_kommune ON ressurs (kommune_id);
CREATE INDEX IF NOT EXISTS ix_ressurs_bygning ON ressurs (bygning_id);
CREATE INDEX IF NOT EXISTS ix_ressurs_sokevektor ON ressurs USING GIN (sokevektor);
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
-- 8. Innlasting og sporbarhet
-- =============================================================================

-- Rått JSON-svar, lagret før transformasjon. Gjør at en last kan kjøres om igjen
-- uten nye kall mot kommunens system.
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
CREATE TABLE IF NOT EXISTS synk_avvik
(
    id               BIGSERIAL PRIMARY KEY,
    kildeuttrekk_id  BIGINT REFERENCES kildeuttrekk(id) ON DELETE CASCADE,
    kilde            TEXT NOT NULL,
    samling          TEXT NOT NULL,
    avvikstype       TEXT NOT NULL CHECK (avvikstype IN
                          ('manglende_forelder','ikke_kartlagt','geokoding_feilet',
                           'ugyldig_verdi','annet')),
    ekstern_id       TEXT,
    detalj           TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_synk_avvik_kilde ON synk_avvik (kilde, avvikstype);


-- =============================================================================
-- 9. Søkevisninger
-- =============================================================================

-- Alt et søk trenger i én flat rad per bookbar ressurs. Basetabellene bruker
-- bare "id" internt; visningen gir hver id et beskrivende navn i output, slik
-- at resultatet er lesbart uten å kjenne navnekonvensjonen i skjemaet.
CREATE OR REPLACE VIEW v_ressurs_sok AS
SELECT
    r.id                           AS ressurs_id,
    r.navn,
    r.kapasitet,
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


-- =============================================================================
-- 10. Kanonisk kodeverk (startsett)
--
-- Utledet fra de 142 distinkte kategorinavnene i de 12 Aktiv kommune-instansene,
-- slått sammen på tvers av målform, skrivefeil og synonymer.
-- =============================================================================

INSERT INTO lokaletype (kode, navn, sortering) VALUES
    ('IDRETT','Idrett og fysisk aktivitet',10),
    ('KULTUR','Kultur og scene',20),
    ('UNDERVISNING','Undervisning og møte',30),
    ('VERKSTED','Verksted og produksjon',40),
    ('ARRANGEMENT','Selskap og arrangement',50),
    ('BEVERTNING','Mat og bevertning',60),
    ('NAERMILJO','Aktivitets- og nærmiljøhus',70),
    ('UTEAREAL','Utendørs areal',80),
    ('OVERNATTING','Overnatting og bolig',90),
    ('ANNET_LOKALE','Kontor og andre lokaler',100),
    ('UTSTYR','Utstyr',110)
ON CONFLICT (kode) DO NOTHING;

INSERT INTO lokaletype (kode, navn, parent_id, sortering)
SELECT v.kode, v.navn, p.id, v.sortering
FROM (VALUES
    ('IDRETTSHALL','Idrettshall','IDRETT',11),
    ('GYMSAL','Gymsal','IDRETT',12),
    ('SVOMMEANLEGG','Svømmeanlegg','IDRETT',13),
    ('ISHALL','Ishall og isbane','IDRETT',14),
    ('FRIIDRETTSANLEGG','Friidrettsanlegg','IDRETT',15),
    ('FOTBALLBANE','Fotballbane','IDRETT',16),
    ('BALLBANE','Ballbane og ballbinge','IDRETT',17),
    ('TENNISANLEGG','Tennisanlegg','IDRETT',18),
    ('STYRKEROM','Styrke- og treningsrom','IDRETT',19),
    ('KAMPSPORTROM','Kampsportrom','IDRETT',20),
    ('KLATREANLEGG','Klatreanlegg','IDRETT',21),
    ('TURNANLEGG','Turnanlegg','IDRETT',22),
    ('SKATEANLEGG','Skateanlegg','IDRETT',23),
    ('SKYTEBANE','Skytebane','IDRETT',24),
    ('SJOSPORTANLEGG','Sjøsportanlegg','IDRETT',25),
    ('GARDEROBE','Garderobe','IDRETT',26),

    ('KONSERTSAL','Konsertsal og kultursal','KULTUR',21),
    ('SCENE','Scene','KULTUR',22),
    ('AUDITORIUM','Auditorium og foredragssal','KULTUR',23),
    ('OVINGSROM','Øvingsrom og musikkrom','KULTUR',24),
    ('DANSESAL','Dansesal','KULTUR',25),
    ('LYDSTUDIO','Lydstudio','KULTUR',26),
    ('UTSTILLINGSLOKALE','Utstillingslokale og atelier','KULTUR',27),
    ('BIBLIOTEK','Bibliotek','KULTUR',28),
    ('FOAJE','Foajé','KULTUR',29),

    ('KLASSEROM','Klasserom og undervisningsrom','UNDERVISNING',31),
    ('GRUPPEROM','Grupperom og prosjektrom','UNDERVISNING',32),
    ('MOTEROM','Møterom og konferanserom','UNDERVISNING',33),
    ('DATAROM','Datarom','UNDERVISNING',34),
    ('AULA','Aula','UNDERVISNING',35),

    ('SLOYDSAL','Sløydsal','VERKSTED',41),
    ('KUNSTVERKSTED','Kunst- og håndverksverksted','VERKSTED',42),
    ('SYSTUE','Systue','VERKSTED',43),
    ('MEDIEVERKSTED','Multimedia- og streamingverksted','VERKSTED',44),
    ('FRISORSALONG','Frisørsalong','VERKSTED',45),

    ('SELSKAPSLOKALE','Selskapslokale','ARRANGEMENT',51),
    ('FORSAMLINGSLOKALE','Forsamlingslokale','ARRANGEMENT',52),
    ('SEREMONIROM','Seremonirom','ARRANGEMENT',53),
    ('BURSDAGSLOKALE','Bursdagslokale','ARRANGEMENT',54),
    ('ARRANGEMENTSARENA','Arrangementsarena','ARRANGEMENT',55),
    ('TORGPLASS','Torg og møteplass','ARRANGEMENT',56),

    ('KJOKKEN','Kjøkken','BEVERTNING',61),
    ('KANTINE','Kantine','BEVERTNING',62),
    ('KAFE','Kafé og kiosk','BEVERTNING',63),

    ('ALLAKTIVITETSHUS','Allaktivitetshus','NAERMILJO',71),
    ('AKTIVITETSROM','Aktivitetsrom og flerbruksrom','NAERMILJO',72),
    ('UNGDOMSLOKALE','Ungdomslokale','NAERMILJO',73),
    ('DAGSENTER','Dagsenter og miljøstue','NAERMILJO',74),
    ('INNBYGGERTORG','Innbyggertorg','NAERMILJO',75),

    ('FRILUFTSOMRAADE','Friluftsområde','UTEAREAL',81),
    ('UTEOMRAADE','Uteområde','UTEAREAL',82),
    ('TURVEI','Turvei og løype','UTEAREAL',83),
    ('GAPAHUK','Gapahuk og bålplass','UTEAREAL',84),
    ('UTESCENE','Utendørsscene','UTEAREAL',85),

    ('OVERNATTINGSROM','Overnattingsrom','OVERNATTING',91),
    ('BEBOERROM','Beboerrom','OVERNATTING',92),
    ('OVINGSLEILIGHET','Øvingsleilighet','OVERNATTING',93),

    ('KONTOR','Kontor og arbeidsplass','ANNET_LOKALE',101),
    ('BUTIKKLOKALE','Butikklokale','ANNET_LOKALE',102),
    ('LAGER','Lager','ANNET_LOKALE',103),
    ('GENERELT_LOKALE','Generelt lokale','ANNET_LOKALE',104),

    ('SYKKEL','Sykkel og el-sykkel','UTSTYR',111),
    ('KANO_KAJAKK','Kano og kajakk','UTSTYR',112),
    ('FISKEUTSTYR','Fiskeutstyr','UTSTYR',113),
    ('REDNINGSVEST','Redningsvest','UTSTYR',114),
    ('LYDANLEGG','Lyd- og lysanlegg','UTSTYR',115),
    ('ANNET_UTSTYR','Annet utstyr','UTSTYR',116)
) AS v(kode, navn, parent_kode, sortering)
JOIN lokaletype p ON p.kode = v.parent_kode
ON CONFLICT (kode) DO NOTHING;

INSERT INTO aktivitet (kode, navn, sortering) VALUES
    ('IDRETT','Idrett',10),
    ('KULTUR','Kultur',20),
    ('OPPLARING','Opplæring og kurs',30),
    ('MOTE','Møte og konferanse',40),
    ('PRIVAT','Privat arrangement',50),
    ('FRIVILLIGHET','Frivillighet og lag',60),
    ('FRILUFT','Friluftsliv',70),
    ('INTERNT','Internt kommunalt',80)
ON CONFLICT (kode) DO NOTHING;

INSERT INTO aktivitet (kode, navn, parent_id, sortering)
SELECT v.kode, v.navn, p.id, v.sortering
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
    ('KIOSK','Kiosk','kjokken',43),
    ('TRIBUNE','Tribune','sport',50),
    ('MAALBUR','Målbur','sport',51),
    ('TIDTAKING','Tidtakingsanlegg','sport',52),
    ('BANEDELING','Delbar bane','sport',53),
    ('BORD_STOLER','Bord og stoler','moblering',60),
    ('WHITEBOARD','Whiteboard','moblering',61),
    ('PARKETTGULV','Parkettgulv','moblering',62),
    ('PARKERING','Parkering','uteareal',70),
    ('HC_PARKERING','HC-parkering','uteareal',71),
    ('SYKKELPARKERING','Sykkelparkering','uteareal',72),
    ('BAALPLASS','Bålplass','uteareal',73),
    ('FLOMLYS','Flomlys','uteareal',74),
    ('ELEKTRONISK_LAS','Elektronisk låssystem','annet',80)
ON CONFLICT (kode) DO NOTHING;


-- =============================================================================
-- 11. updated_at-triggere
-- =============================================================================

DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'kommune','fagsystem_instans','matrikkelenhet','bygning','adresse',
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
