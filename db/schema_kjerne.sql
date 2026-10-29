-- Masterdatabase for kommunale lokaler — kjernemodell
-- PostgreSQL 12+ med PostGIS 3.x. Testet mot PostgreSQL 18 / PostGIS 3.6.
--
-- LESBAR KOPI. Skjemaet eies av Flyway-migrasjonene i
-- backend/src/main/resources/db/migration, som backenden kjører når den
-- starter. Denne filen viser hele skjemaet samlet slik det er etter siste
-- migrasjon (nå V5), og oppdateres sammen med hver ny migrasjon. Ikke kjør den
-- mot en database som Flyway styrer.
--
-- 19 tabeller og 7 visninger. 18 får data i dag, enten fra Aktiv kommune-endepunktene eller
-- fra matrikkelen - unntaket er ressurslenke, som forblir tom til et andre
-- fagsystem (fdv/sensor/...) faktisk kobles på. Se db/schema_kjerne_dokumentasjon.md.
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
-- 2. Bygning
--
-- Holder både bygg og utendørs anlegg. Aktiv kommune har bare ett stedsbegrep:
-- "Paradis kunstgressbane" er registrert som et bygg der, på linje med ekte
-- bygninger. Vi skiller dem ikke på bygningsnivå - kildedata har ingen felt
-- som sier "dette er utendørs", og et bygg kan i praksis romme både en hall
-- og en utendørs kunstgressbane under samme adresse. Innendørs/utendørs
-- avgjøres derfor per ressurs, via ressurs_lokaletype (se fasettene sportsOutdoor
-- og outdoor i lokaletype).
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
-- 3. Matrikkelinfo
-- =============================================================================

CREATE TABLE IF NOT EXISTS matrikkelinfo
(
    id             BIGSERIAL PRIMARY KEY,
	bygning_id     BIGINT NOT NULL REFERENCES bygning(id) ON DELETE CASCADE,
    kommunenr      CHAR(4) NOT NULL CHECK (kommunenr ~ '^[0-9]{4}$'),
    gardsnr        INTEGER NOT NULL,
    bruksnr        INTEGER NOT NULL,
    festenr        INTEGER,
    seksjonsnr     INTEGER,
    sist_oppdatert TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Ett bygg kan ha flere matrikkelinfo (en-til-mange). bygning_id er med i den
-- unike indeksen, så samme gnr/bnr lagres én gang per bygg: en hall og en bane
-- på samme eiendom får hver sin rad.
-- COALESCE fordi festenr og seksjonsnr er NULL for vanlige grunneiendommer, og
-- NULL regnes ikke som lik NULL i en unik indeks. Uten dette ville samme
-- eiendom kunne lagres mange ganger for samme bygg.
CREATE UNIQUE INDEX IF NOT EXISTS ux_matrikkelinfo
    ON matrikkelinfo (bygning_id,kommunenr, gardsnr, bruksnr,
                       COALESCE(festenr, 0), COALESCE(seksjonsnr, 0));
-- Oppslag på eiendommen på tvers av bygg ("hvilket bygg står på gnr/bnr?").
CREATE INDEX IF NOT EXISTS ix_matrikkelinfo_eiendom
ON matrikkelinfo(kommunenr,gardsnr,bruksnr);

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
    -- Selvreferanse for hierarki (Idrettshall -> Gymsal, "broader" i
    -- vokabularfilen). Heter "parent_id", ikke "lokaletype_id", for å skille den
    -- tydelig fra en referanse til en annen tabell.
    parent_id  BIGINT REFERENCES lokaletype(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Fasetten fra venue_types.json (sportsIndoor, culture ...), brukt som
    -- lokaletype_hovedgruppe i søket. Ikke begrenset i databasen: en ny fasett i
    -- filen skal ikke kreve en migrasjon. Sist i tabellen fordi kolonnen kom med V5.
    fasett     TEXT NOT NULL,
    CONSTRAINT chk_lokaletype_kode CHECK (kode ~ '^LOK-[A-Z]{2}-[0-9]{3}$')
);

-- Holder mer enn rene aktiviteter: alle fasettene i etl/activity_mapping/
-- activities.json unntatt "exclude" (aktivitet, arrangement, organisasjon,
-- målgruppe, lokale, tjeneste). Fasetten bæres av prefikset i kode (ACT-,
-- EVT-, ORG-, GRP-, VEN-, SRV-), ikke av en egen kolonne. Vokabularet eies av
-- JSON-filen og lastes av etl/last_mapping.py - det seedes ikke her.
--
-- Noen få konsepter har to foreldre i vokabularet (Dans under både Kultur og
-- Idrett); parent_id får den første.
CREATE TABLE IF NOT EXISTS aktivitet
(
    id         BIGSERIAL PRIMARY KEY,
    kode       TEXT UNIQUE NOT NULL
                   CHECK (kode ~ '^(ACT|EVT|ORG|GRP|VEN|SRV)-[0-9]{3}$'),
    navn       TEXT NOT NULL,
    parent_id  BIGINT REFERENCES aktivitet(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Gruppen er fasetten fra facilities.json (av, sanitary, kitchen ...), ikke
-- begrenset i databasen av samme grunn som lokaletype.fasett.
CREATE TABLE IF NOT EXISTS fasilitet
(
    id         BIGSERIAL PRIMARY KEY,
    kode       TEXT UNIQUE NOT NULL,
    navn       TEXT NOT NULL,
    gruppe     TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_fasilitet_kode CHECK (kode ~ '^FAC-[A-Z]{2}-[0-9]{3}$')
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
-- den status og hvem som bestemte den. Én mappingtabell per kodetype, med lik
-- oppbygning, så samme regler gjelder for alle tre. Fylles av
-- etl/last_mapping.py fra fasitfilene i etl/*_mapping/ (kartlagt_av = 'etl');
-- rader med annen kartlagt_av er manuelle og overskrives aldri.
-- 'ikke_relevant' finnes fordi kategorilistene inneholder verdier som ikke er
-- lokaletyper: "Stengt", "Fiktivt rom", "Streaming", og stedsnavn som
-- "Judaberg innbyggertorg". Den ligger i samme tabell med mål = NULL.
--
-- Fremmednøklene til kodeverket er RESTRICT, ikke CASCADE: et konsept som er i
-- bruk skal ikke kunne slettes slik at mappingene forsvinner stille.

-- Lokaletype: høyst én rad per kildekode, siden en ressurs har én lokaletype.
-- Skal en ressurs få flere, fjernes ux_lokaletype_mapping og erstattes av to
-- partielle unike indekser slik som i aktivitet_mapping.
CREATE TABLE IF NOT EXISTS lokaletype_mapping
(
    id            BIGSERIAL PRIMARY KEY,
    kildekode_id  BIGINT NOT NULL REFERENCES kildekode(id) ON DELETE CASCADE,
    lokaletype_id BIGINT REFERENCES lokaletype(id) ON DELETE RESTRICT,
    status        TEXT NOT NULL DEFAULT 'foreslatt'
                      CHECK (status IN ('foreslatt','godkjent','ikke_relevant')),
    kartlagt_av   TEXT,
    merknad       TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_lokaletype_mapping_mal CHECK ((lokaletype_id IS NULL) = (status = 'ikke_relevant'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_lokaletype_mapping ON lokaletype_mapping (kildekode_id);
CREATE INDEX IF NOT EXISTS ix_lokaletype_mapping_lokaletype ON lokaletype_mapping (lokaletype_id);

-- Fasilitet: én rad per konsept, som aktivitet_mapping, siden ett kildenavn kan
-- bære flere fasiliteter.
CREATE TABLE IF NOT EXISTS fasilitet_mapping
(
    id           BIGSERIAL PRIMARY KEY,
    kildekode_id BIGINT NOT NULL REFERENCES kildekode(id) ON DELETE CASCADE,
    fasilitet_id BIGINT REFERENCES fasilitet(id) ON DELETE RESTRICT,
    status       TEXT NOT NULL DEFAULT 'foreslatt'
                     CHECK (status IN ('foreslatt','godkjent','ikke_relevant')),
    kartlagt_av  TEXT,
    merknad      TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_fasilitet_mapping_mal CHECK ((fasilitet_id IS NULL) = (status = 'ikke_relevant'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_fasilitet_mapping
    ON fasilitet_mapping (kildekode_id, fasilitet_id) WHERE fasilitet_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_fasilitet_mapping_ikke_relevant
    ON fasilitet_mapping (kildekode_id) WHERE fasilitet_id IS NULL;
CREATE INDEX IF NOT EXISTS ix_fasilitet_mapping_fasilitet ON fasilitet_mapping (fasilitet_id);

-- Aktivitet: én rad per konsept, fordi ett kildenavn kan bære flere konsepter
-- ("Barnebursdag 3 - 12 år" -> Barnebursdag + Barn). 'ikke_relevant'
-- (EXC-konsepter i activity_mapping) ligger her med aktivitet_id = NULL, slik at
-- all aktivitetskartlegging finnes på ett sted.
CREATE TABLE IF NOT EXISTS aktivitet_mapping
(
    id           BIGSERIAL PRIMARY KEY,
    kildekode_id BIGINT NOT NULL REFERENCES kildekode(id) ON DELETE CASCADE,
    aktivitet_id BIGINT REFERENCES aktivitet(id) ON DELETE RESTRICT,
    status       TEXT NOT NULL DEFAULT 'foreslatt'
                     CHECK (status IN ('foreslatt','godkjent','ikke_relevant')),
    kartlagt_av  TEXT,
    merknad      TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_aktivitet_mapping_mal
        CHECK ((aktivitet_id IS NULL) = (status = 'ikke_relevant'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_aktivitet_mapping
    ON aktivitet_mapping (kildekode_id, aktivitet_id) WHERE aktivitet_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_aktivitet_mapping_ikke_relevant
    ON aktivitet_mapping (kildekode_id) WHERE aktivitet_id IS NULL;
CREATE INDEX IF NOT EXISTS ix_aktivitet_mapping_aktivitet ON aktivitet_mapping (aktivitet_id);


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
    -- Lokaletype er ingen kolonne her, men utledes: se ressurs_lokaletype under.

    -- Kapasitet er utfylt på under 1 % av ressursene i kilden.
    kapasitet       INTEGER CHECK (kapasitet IS NULL OR kapasitet >= 0),
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
CREATE INDEX IF NOT EXISTS ix_ressurs_sok ON ressurs (kommune_id) WHERE aktiv AND bookbar;

-- Hvilke lokale koder kilden ga hver ressurs: aktivitet, fasilitet og lokaletype
-- (kodetypen ligger på kildekode.kodetype). Dette er det kilden faktisk sa, uten
-- tolkning. Skrives av etl/last_inn.py.
CREATE TABLE IF NOT EXISTS ressurs_kildekode
(
    ressurs_id   BIGINT NOT NULL REFERENCES ressurs(id) ON DELETE CASCADE,
    kildekode_id BIGINT NOT NULL REFERENCES kildekode(id) ON DELETE CASCADE,
    PRIMARY KEY (ressurs_id, kildekode_id)
);

-- Omvendt oppslag: hvilke ressurser har denne kildekoden.
CREATE INDEX IF NOT EXISTS ix_ressurs_kildekode_kode ON ressurs_kildekode (kildekode_id);

-- Avledede koblinger: visninger, regnet ut fra ressurs_kildekode og godkjent
-- mapping hver gang de leses. En endret mapping slår derfor inn umiddelbart,
-- enten den kommer fra fasitfil via etl/last_mapping.py eller legges inn manuelt.
CREATE OR REPLACE VIEW ressurs_aktivitet AS
SELECT DISTINCT rk.ressurs_id, m.aktivitet_id
FROM ressurs_kildekode rk
JOIN kildekode kk ON kk.id = rk.kildekode_id AND kk.kodetype = 'aktivitet'
JOIN aktivitet_mapping m ON m.kildekode_id = kk.id
                        AND m.status = 'godkjent' AND m.aktivitet_id IS NOT NULL;

CREATE OR REPLACE VIEW ressurs_fasilitet AS
SELECT DISTINCT rk.ressurs_id, m.fasilitet_id
FROM ressurs_kildekode rk
JOIN kildekode kk ON kk.id = rk.kildekode_id AND kk.kodetype = 'fasilitet'
JOIN fasilitet_mapping m ON m.kildekode_id = kk.id
                        AND m.status = 'godkjent' AND m.fasilitet_id IS NOT NULL;

-- Én lokaletype per ressurs. DISTINCT ON sikrer det også om en ressurs mot
-- formodning skulle ha flere lokaletype-kildekoder (laveste kildekode vinner).
CREATE OR REPLACE VIEW ressurs_lokaletype AS
SELECT DISTINCT ON (rk.ressurs_id) rk.ressurs_id, m.lokaletype_id
FROM ressurs_kildekode rk
JOIN kildekode kk ON kk.id = rk.kildekode_id AND kk.kodetype = 'lokaletype'
JOIN lokaletype_mapping m ON m.kildekode_id = kk.id
                         AND m.status = 'godkjent' AND m.lokaletype_id IS NOT NULL
ORDER BY rk.ressurs_id, kk.id;


-- =============================================================================
-- 9. Ressurslenke: samme fysiske ting, kjent av flere fagsystemer
--
-- ressurs.fagsystem_instans_id + ekstern_id er allerede identitet+ruting for
-- EN instans (se kommentar ved ressurs). Denne tabellen er for når en ANNEN
-- instans (fdv, sensor, ...) også kjenner samme fysiske bygg/ressurs, under
-- sin egen ekstern_id - uten at det tvinger frem en duplikatrad i ressurs.
--
-- "Exclusive arc": nøyaktig én av bygning_id/ressurs_id er fylt ut per rad -
-- én tabell dekker begge de fysiske ankrene vi har i dag, uten at bygning/
-- ressurs selv trenger flere fagsystem-FK-er. Se db/ressurslenke.md.
--
-- Bevisst INGEN egen "kontekst"/type-kolonne her: hvilken TYPE fagsystem
-- (booking/fdv/sensor/annet) en lenke tilhører er allerede
-- fagsystem_instans.type, hentet via fagsystem_instans_id. Å kopiere den inn
-- her ville vært ren duplisering (se kommune_fagsystem_instans for det ene
-- unntaket der en slik kopi faktisk trengs - en UNIQUE som ikke kan krysse
-- tabellgrenser). Det betyr også at et helt nytt fagsystem (nummer 3, 4, ...)
-- ikke krever noen endring i DENNE tabellen, bare en ny fagsystem_instans-rad.
-- =============================================================================

CREATE TABLE IF NOT EXISTS ressurslenke
(
    id                   BIGSERIAL PRIMARY KEY,
    fagsystem_instans_id BIGINT NOT NULL REFERENCES fagsystem_instans(id) ON DELETE CASCADE,
    bygning_id           BIGINT REFERENCES bygning(id) ON DELETE CASCADE,
    ressurs_id           BIGINT REFERENCES ressurs(id) ON DELETE CASCADE,
    ekstern_id           TEXT NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_ressurslenke_exactly_one CHECK (
        (bygning_id IS NOT NULL)::int + (ressurs_id IS NOT NULL)::int = 1),
    CONSTRAINT uniq_ressurslenke_ekstern UNIQUE (fagsystem_instans_id, ekstern_id)
);

-- Én partiell unik indeks per fysisk type: hindrer at samme instans lenker
-- samme bygg/ressurs inn to ganger. Kan ikke være én vanlig UNIQUE over begge
-- kolonnene, siden nøyaktig én av dem alltid er NULL (se CHECK over).
CREATE UNIQUE INDEX IF NOT EXISTS ux_ressurslenke_bygning
    ON ressurslenke (fagsystem_instans_id, bygning_id) WHERE bygning_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_ressurslenke_ressurs
    ON ressurslenke (fagsystem_instans_id, ressurs_id) WHERE ressurs_id IS NOT NULL;

-- Omvendt oppslag: "hvilke fagsystemer kjenner dette bygget/denne ressursen".
CREATE INDEX IF NOT EXISTS ix_ressurslenke_bygning ON ressurslenke (bygning_id) WHERE bygning_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_ressurslenke_ressurs ON ressurslenke (ressurs_id) WHERE ressurs_id IS NOT NULL;


-- =============================================================================
-- 10. Innlasting og sporbarhet
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
-- 11. Søkevisninger
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
    lt.fasett                      AS lokaletype_hovedgruppe,
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
LEFT JOIN ressurs_lokaletype rl ON rl.ressurs_id = r.id
LEFT JOIN lokaletype lt    ON lt.id = rl.lokaletype_id
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
WHERE CASE kk.kodetype
          WHEN 'aktivitet'  THEN NOT EXISTS (SELECT 1 FROM aktivitet_mapping m
                                              WHERE m.kildekode_id = kk.id AND m.status <> 'foreslatt')
          WHEN 'lokaletype' THEN NOT EXISTS (SELECT 1 FROM lokaletype_mapping m
                                              WHERE m.kildekode_id = kk.id AND m.status <> 'foreslatt')
          ELSE                   NOT EXISTS (SELECT 1 FROM fasilitet_mapping m
                                              WHERE m.kildekode_id = kk.id AND m.status <> 'foreslatt')
      END;

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
-- 12. Kodeverk
--
-- Ingen seed-data her. Vokabularet for aktivitet, lokaletype og fasilitet eies av
-- JSON-filene i etl/*_mapping/ (activities.json, venue_types.json,
-- facilities.json) og lastes av etl/last_mapping.py. Tabellene er tomme til det
-- skriptet er kjørt.
-- =============================================================================

-- =============================================================================
-- 13. updated_at-triggere
-- =============================================================================

DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'kommune','fagsystem_instans', 'matrikkelinfo','bygning','gate','adresse',
        'lokaletype','aktivitet','fasilitet','kildekode','lokaletype_mapping',
        'fasilitet_mapping','aktivitet_mapping','ressurs'
    ]
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_%1$s_updated_at ON %1$I', t);
        EXECUTE format(
            'CREATE TRIGGER trg_%1$s_updated_at BEFORE UPDATE ON %1$I
             FOR EACH ROW EXECUTE FUNCTION sett_updated_at()', t);
    END LOOP;
END
$$;
