-- V5: vokabularet for lokaletype og fasilitet kommer fra JSON
--
-- Aktivitet har hele tiden hatt vokabularet i en JSON-fil som etl/last_mapping.py
-- laster. Lokaletype og fasilitet gjør det nå også (etl/lokaletype_mapping/
-- venue_types.json og etl/fasilitet_mapping/facilities.json), med nye koder
-- (LOK-SI-004, FAC-SN-002 ...). Det som ble seedet i V1 (GYMSAL, GARDEROBE ...)
-- erstattes derfor og fjernes her.
--
-- Etter denne migrasjonen er lokaletype og fasilitet tomme, og ressursene har
-- ingen lokaletype eller fasiliteter i søket, til etl/last_mapping.py er kjørt:
--   etl/kjor_alt.sh mapping
-- Kildekodene og koblingene til ressursene (ressurs_kildekode) berøres ikke.
--
-- Backenden må ikke oppdateres sammen med denne: Lokaletype og Fasilitet er
-- uendret utad.

-- Vakt: mappingrader som er lagt inn manuelt og peker på de gamle kodene ville
-- ikke overlevd, og kan ikke regnes ut på nytt av skriptet. ETL-radene fornyes
-- av last_mapping.py og slettes under.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM lokaletype_mapping
                WHERE kartlagt_av IS DISTINCT FROM 'etl' AND lokaletype_id IS NOT NULL)
    OR EXISTS (SELECT 1 FROM fasilitet_mapping
                WHERE kartlagt_av IS DISTINCT FROM 'etl' AND fasilitet_id IS NOT NULL)
    THEN
        RAISE EXCEPTION 'V5 avbrutt: manuelle mappingrader peker på lokaletyper eller fasiliteter som erstattes. Lag dem på nytt mot de nye kodene i fasitfilene først.';
    END IF;
END
$$;

-- Fjerner det gamle vokabularet. Mappingradene som peker på det går først,
-- siden fremmednøklene er RESTRICT.
DELETE FROM lokaletype_mapping WHERE kartlagt_av = 'etl';
DELETE FROM fasilitet_mapping  WHERE kartlagt_av = 'etl';
DELETE FROM lokaletype;
DELETE FROM fasilitet;

-- Lokaletype får fasetten (sportsIndoor, culture ...) som gruppering, slik
-- fasilitet har gruppe. Den brukes som lokaletype_hovedgruppe i søket, mens
-- hierarkiet (Gymsal under Idrettshall) ligger i parent_id som før. Tabellen er
-- tom, så NOT NULL går an uten standardverdi. Verdiene er ikke begrenset i
-- databasen: en ny fasett i JSON-filen skal ikke kreve en migrasjon.
ALTER TABLE lokaletype ADD COLUMN fasett TEXT NOT NULL;

-- Kodeformatet fra vokabularfilene, som for aktivitet. Fasilitet beholder
-- gruppe-kolonnen, men CHECK-en med de gamle gruppene fjernes: gruppene er nå
-- fasettene i facilities.json.
ALTER TABLE lokaletype ADD CONSTRAINT chk_lokaletype_kode
    CHECK (kode ~ '^LOK-[A-Z]{2}-[0-9]{3}$');
ALTER TABLE fasilitet DROP CONSTRAINT fasilitet_gruppe_check;
ALTER TABLE fasilitet ADD CONSTRAINT chk_fasilitet_kode
    CHECK (kode ~ '^FAC-[A-Z]{2}-[0-9]{3}$');

-- lokaletype_hovedgruppe er nå fasetten i stedet for forelderens kode. Samme
-- kolonner og typer som før, så visningen kan erstattes uten å droppes.
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
