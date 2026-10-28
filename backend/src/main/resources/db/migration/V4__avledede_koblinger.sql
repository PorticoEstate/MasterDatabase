-- V4: avledede koblinger
--
-- ressurs_aktivitet, ressurs_fasilitet og ressurs_lokaletype blir visninger. De
-- regnes ut fra ressurs_kildekode (det kilden sa om ressursen) og godkjent
-- mapping hver gang de leses, så en endret mapping slår inn umiddelbart, enten
-- den kommer fra JSON via etl/last_mapping.py eller legges inn manuelt.
-- ressurs.lokaletype_id fjernes, siden lokaletype nå utledes på samme måte.
--
-- Backenden må oppdateres sammen med denne migrasjonen (Ressurs.lokaletype leses
-- fra visningen, og de to koblingsentitetene er skrivebeskyttede), ellers feiler
-- ddl-auto=validate.

-- Vakt: stopp hvis noe ville gått tapt. Før denne migrasjonen er koblingene
-- lagrede rader, og visningene har bare noe å regne ut fra hvis ressurs_kildekode
-- er fylt. Er den ikke det, ville søk miste aktiviteter, fasiliteter og
-- lokaletype til etl/last_inn.py og etl/last_mapping.py har kjørt. Stopper
-- migrasjonen, rulles alt tilbake og backenden starter ikke. Kjør da
-- last_inn.py og last_mapping.py (mot databasen på forrige versjon), og start
-- backenden på nytt.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM ressurs_aktivitet ra
                WHERE NOT EXISTS (SELECT 1 FROM ressurs_kildekode rk
                                    JOIN kildekode kk ON kk.id = rk.kildekode_id AND kk.kodetype = 'aktivitet'
                                   WHERE rk.ressurs_id = ra.ressurs_id))
    OR EXISTS (SELECT 1 FROM ressurs_fasilitet rf
                WHERE NOT EXISTS (SELECT 1 FROM ressurs_kildekode rk
                                    JOIN kildekode kk ON kk.id = rk.kildekode_id AND kk.kodetype = 'fasilitet'
                                   WHERE rk.ressurs_id = rf.ressurs_id))
    OR EXISTS (SELECT 1 FROM ressurs r
                WHERE r.lokaletype_id IS NOT NULL
                  AND NOT EXISTS (SELECT 1 FROM ressurs_kildekode rk
                                    JOIN kildekode kk ON kk.id = rk.kildekode_id AND kk.kodetype = 'lokaletype'
                                   WHERE rk.ressurs_id = r.id))
    THEN
        RAISE EXCEPTION 'V4 avbrutt: noen ressurser har koblinger uten tilhørende rader i ressurs_kildekode, og de ville gått tapt. Kjør etl/last_inn.py og etl/last_mapping.py først.';
    END IF;
END
$$;

-- Fjerner det som erstattes. v_ressurs_sok leser koblingstabellene og
-- lokaletype-kolonnen, så den går først og lages på nytt under. Ingen CASCADE:
-- en uventet avhengighet skal gi feil, ikke slettes.
DROP VIEW v_ressurs_sok;
DROP TABLE ressurs_aktivitet;
DROP TABLE ressurs_fasilitet;
ALTER TABLE ressurs DROP COLUMN lokaletype_id;

-- Erstatter indeksen som lå på (lokaletype_id, kommune_id) og forsvant med kolonnen.
CREATE INDEX ix_ressurs_sok ON ressurs (kommune_id) WHERE aktiv AND bookbar;

-- Avledede koblinger: alle par der ressursen har en kildekode som er godkjent
-- mappet til målet. Samme navn som tabellene de erstatter.
CREATE VIEW ressurs_aktivitet AS
SELECT DISTINCT rk.ressurs_id, m.aktivitet_id
FROM ressurs_kildekode rk
JOIN kildekode kk ON kk.id = rk.kildekode_id AND kk.kodetype = 'aktivitet'
JOIN aktivitet_mapping m ON m.kildekode_id = kk.id
                        AND m.status = 'godkjent' AND m.aktivitet_id IS NOT NULL;

CREATE VIEW ressurs_fasilitet AS
SELECT DISTINCT rk.ressurs_id, m.fasilitet_id
FROM ressurs_kildekode rk
JOIN kildekode kk ON kk.id = rk.kildekode_id AND kk.kodetype = 'fasilitet'
JOIN fasilitet_mapping m ON m.kildekode_id = kk.id
                        AND m.status = 'godkjent' AND m.fasilitet_id IS NOT NULL;

-- Én lokaletype per ressurs. DISTINCT ON sikrer det også om en ressurs mot
-- formodning skulle ha flere lokaletype-kildekoder (laveste kildekode vinner).
CREATE VIEW ressurs_lokaletype AS
SELECT DISTINCT ON (rk.ressurs_id) rk.ressurs_id, m.lokaletype_id
FROM ressurs_kildekode rk
JOIN kildekode kk ON kk.id = rk.kildekode_id AND kk.kodetype = 'lokaletype'
JOIN lokaletype_mapping m ON m.kildekode_id = kk.id
                         AND m.status = 'godkjent' AND m.lokaletype_id IS NOT NULL
ORDER BY rk.ressurs_id, kk.id;

-- Alt et søk trenger i én flat rad per bookbar ressurs. Uendret utad; lokaletype
-- hentes nå fra ressurs_lokaletype i stedet for kolonnen på ressurs.
CREATE VIEW v_ressurs_sok AS
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
LEFT JOIN ressurs_lokaletype rl ON rl.ressurs_id = r.id
LEFT JOIN lokaletype lt    ON lt.id = rl.lokaletype_id
LEFT JOIN lokaletype p     ON p.id = lt.parent_id
LEFT JOIN bygning b        ON b.id = r.bygning_id
LEFT JOIN adresse a        ON a.bygning_id = b.id AND a.er_hovedadresse
WHERE r.aktiv AND r.bookbar;
