-- V3: én mappingtabell per kodetype
--
-- aktivitet_mapping finnes fra før. Lokaletype og fasilitet får hver sin tabell
-- med samme oppbygning, og kildekode_mapping (én tabell med to nullbare
-- målkolonner og en CHECK som teller dem) flyttes dit og fjernes. Da gjelder
-- samme regler for alle tre kodetyper.
--
-- Fremmednøklene til kodeverket er RESTRICT, ikke CASCADE: et konsept som er i
-- bruk skal ikke kunne slettes slik at mappingene forsvinner stille.

-- Lokaletype: høyst én rad per kildekode, siden en ressurs har én lokaletype.
-- Skal en ressurs få flere, fjernes ux_lokaletype_mapping og erstattes av to
-- partielle unike indekser slik som i aktivitet_mapping.
CREATE TABLE lokaletype_mapping
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

CREATE UNIQUE INDEX ux_lokaletype_mapping ON lokaletype_mapping (kildekode_id);
CREATE INDEX ix_lokaletype_mapping_lokaletype ON lokaletype_mapping (lokaletype_id);

-- Fasilitet: én rad per konsept, som aktivitet_mapping, siden ett kildenavn kan
-- bære flere fasiliteter. 'ikke_relevant' ligger her med fasilitet_id = NULL.
CREATE TABLE fasilitet_mapping
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

CREATE UNIQUE INDEX ux_fasilitet_mapping
    ON fasilitet_mapping (kildekode_id, fasilitet_id) WHERE fasilitet_id IS NOT NULL;
CREATE UNIQUE INDEX ux_fasilitet_mapping_ikke_relevant
    ON fasilitet_mapping (kildekode_id) WHERE fasilitet_id IS NULL;
CREATE INDEX ix_fasilitet_mapping_fasilitet ON fasilitet_mapping (fasilitet_id);

-- Flytter eksisterende rader fra kildekode_mapping, på kodetype.
INSERT INTO lokaletype_mapping (kildekode_id, lokaletype_id, status, kartlagt_av, merknad,
                                created_at, updated_at)
SELECT m.kildekode_id, m.lokaletype_id, m.status, m.kartlagt_av, m.merknad,
       m.created_at, m.updated_at
FROM kildekode_mapping m JOIN kildekode kk ON kk.id = m.kildekode_id
WHERE kk.kodetype = 'lokaletype';

INSERT INTO fasilitet_mapping (kildekode_id, fasilitet_id, status, kartlagt_av, merknad,
                               created_at, updated_at)
SELECT m.kildekode_id, m.fasilitet_id, m.status, m.kartlagt_av, m.merknad,
       m.created_at, m.updated_at
FROM kildekode_mapping m JOIN kildekode kk ON kk.id = m.kildekode_id
WHERE kk.kodetype = 'fasilitet';

DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['lokaletype_mapping','fasilitet_mapping']
    LOOP
        EXECUTE format(
            'CREATE TRIGGER trg_%1$s_updated_at BEFORE UPDATE ON %1$I
             FOR EACH ROW EXECUTE FUNCTION sett_updated_at()', t);
    END LOOP;
END
$$;

-- Fjerner den gamle tabellen. v_ukartlagte_kildekoder leser den, så den går
-- først og lages på nytt under. Ingen CASCADE: en uventet avhengighet skal gi
-- feil, ikke slettes.
DROP VIEW v_ukartlagte_kildekoder;
DROP TABLE kildekode_mapping;

-- Arbeidslisten for kuratering. Hver rad er en lokal kode som ennå ikke kan
-- søkes på tvers av kommuner. Kildekoden hører til instansen, ikke til én
-- kommune, siden en instans kan betjene flere - kommunene listes derfor
-- sammenslått via oppslag i kommune_fagsystem_instans.
CREATE VIEW v_ukartlagte_kildekoder AS
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

-- aktivitet_mapping: RESTRICT i stedet for CASCADE, som i de nye tabellene.
-- Constraint-navnet er Postgres' standardnavn for en kolonne-FK.
ALTER TABLE aktivitet_mapping DROP CONSTRAINT aktivitet_mapping_aktivitet_id_fkey;
ALTER TABLE aktivitet_mapping ADD CONSTRAINT aktivitet_mapping_aktivitet_id_fkey
    FOREIGN KEY (aktivitet_id) REFERENCES aktivitet(id) ON DELETE RESTRICT;
