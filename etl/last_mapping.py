#!/usr/bin/env python3
"""
Bygger koblingene mellom ressurs og kodeverk på nytt fra det kilden sa
(ressurs_kildekode) og mappingen som ligger i databasen. Henter ingenting fra
kommunene, så skriptet kan kjøres alene når mappingen er endret.

Bruker bare Pythons innebygde bibliotek. Som last_inn.py gjør skriptet
ingenting mot databasen selv; det skriver SQL-tekst til standard-ut, som du
deretter sender til Postgres.

Bruk:
    # Tørrkjøring: kjører alt, skriver rapporten og ruller tilbake.
    python3 etl/last_mapping.py --dry-run > etl/ut/mapping.sql
    docker exec -i portico_masterdb psql -q -U postgres -d masterdb < etl/ut/mapping.sql

    # Ekte kjøring:
    python3 etl/last_mapping.py > etl/ut/mapping.sql
    docker exec -i portico_masterdb psql -q -U postgres -d masterdb < etl/ut/mapping.sql

-q gjør psql stille (ingen kommandokoder som "DELETE 3" eller "SELECT 1234");
rapporten og eventuelle feil vises fortsatt. Utelat -q for å se hver setning.

Hva SQL-en gjør, i én transaksjon:
  ressurs_aktivitet   alle (ressurs, aktivitet) der ressursen har en kildekode som er
                      godkjent mappet til aktiviteten (aktivitet_mapping)
  ressurs_fasilitet   det samme for fasilitet (kildekode_mapping)
  ressurs.lokaletype_id  ressursens lokaletype fra dens lokaletype-kildekode
                      (kildekode_mapping); NULL uten godkjent mapping

Koblingene synkroniseres som diff: bare det som endres, skrives. Til slutt skrives
en rapport over hva som ble lagt til og fjernet per konsept.

Omfang: bare instanser som har rader i ressurs_kildekode (for lokaletype: av
kodetypen lokaletype). Uten det ville en tabell som ikke er fylt ennå, tømt
koblingene til alle ressurser. Kjør derfor etl/last_inn.py først.
"""
import argparse
import sys

SQL = r"""
\set ON_ERROR_STOP on
BEGIN;

CREATE TEMP TABLE _omfang ON COMMIT DROP AS
SELECT DISTINCT r.fagsystem_instans_id AS instans_id, kk.kodetype
FROM ressurs_kildekode rk
JOIN ressurs r ON r.id = rk.ressurs_id
JOIN kildekode kk ON kk.id = rk.kildekode_id;

-- Øyeblikksbilde av tilstanden før endringene, til rapporten.
CREATE TEMP TABLE _for_ra ON COMMIT DROP AS SELECT ressurs_id, aktivitet_id FROM ressurs_aktivitet;
CREATE TEMP TABLE _for_rf ON COMMIT DROP AS SELECT ressurs_id, fasilitet_id FROM ressurs_fasilitet;
CREATE TEMP TABLE _for_lt ON COMMIT DROP AS SELECT id AS ressurs_id, lokaletype_id FROM ressurs;

-- Ønsket tilstand: godkjent mapping fra kildekodene ressursen har.
CREATE TEMP TABLE _ra ON COMMIT DROP AS
SELECT DISTINCT rk.ressurs_id, m.aktivitet_id
FROM ressurs_kildekode rk
JOIN kildekode kk ON kk.id = rk.kildekode_id AND kk.kodetype = 'aktivitet'
JOIN aktivitet_mapping m ON m.kildekode_id = kk.id AND m.status = 'godkjent' AND m.aktivitet_id IS NOT NULL;

CREATE TEMP TABLE _rf ON COMMIT DROP AS
SELECT DISTINCT rk.ressurs_id, m.fasilitet_id
FROM ressurs_kildekode rk
JOIN kildekode kk ON kk.id = rk.kildekode_id AND kk.kodetype = 'fasilitet'
JOIN kildekode_mapping m ON m.kildekode_id = kk.id AND m.status = 'godkjent' AND m.fasilitet_id IS NOT NULL;

\echo -- ressurs_aktivitet: slettet
DELETE FROM ressurs_aktivitet ra USING ressurs r
WHERE ra.ressurs_id = r.id
  AND EXISTS (SELECT 1 FROM _omfang o WHERE o.instans_id = r.fagsystem_instans_id AND o.kodetype = 'aktivitet')
  AND NOT EXISTS (SELECT 1 FROM _ra x WHERE x.ressurs_id = ra.ressurs_id AND x.aktivitet_id = ra.aktivitet_id);
\echo -- ressurs_aktivitet: satt inn
INSERT INTO ressurs_aktivitet (ressurs_id, aktivitet_id)
SELECT ressurs_id, aktivitet_id FROM _ra ON CONFLICT DO NOTHING;

\echo -- ressurs_fasilitet: slettet
DELETE FROM ressurs_fasilitet rf USING ressurs r
WHERE rf.ressurs_id = r.id
  AND EXISTS (SELECT 1 FROM _omfang o WHERE o.instans_id = r.fagsystem_instans_id AND o.kodetype = 'fasilitet')
  AND NOT EXISTS (SELECT 1 FROM _rf x WHERE x.ressurs_id = rf.ressurs_id AND x.fasilitet_id = rf.fasilitet_id);
\echo -- ressurs_fasilitet: satt inn
INSERT INTO ressurs_fasilitet (ressurs_id, fasilitet_id)
SELECT ressurs_id, fasilitet_id FROM _rf ON CONFLICT DO NOTHING;

-- Ressursen har én lokaletype (rescategory_id). Uten godkjent mapping blir den NULL.
CREATE TEMP TABLE _lt ON COMMIT DROP AS
SELECT r.id AS ressurs_id,
       (SELECT m.lokaletype_id
          FROM ressurs_kildekode rk
          JOIN kildekode kk ON kk.id = rk.kildekode_id AND kk.kodetype = 'lokaletype'
          JOIN kildekode_mapping m ON m.kildekode_id = kk.id AND m.status = 'godkjent' AND m.lokaletype_id IS NOT NULL
         WHERE rk.ressurs_id = r.id
         ORDER BY kk.id LIMIT 1) AS lokaletype_id
FROM ressurs r
WHERE EXISTS (SELECT 1 FROM _omfang o WHERE o.instans_id = r.fagsystem_instans_id AND o.kodetype = 'lokaletype');

\echo -- ressurs.lokaletype_id: oppdatert
UPDATE ressurs r SET lokaletype_id = t.lokaletype_id
FROM _lt t WHERE t.ressurs_id = r.id AND r.lokaletype_id IS DISTINCT FROM t.lokaletype_id;

\echo
\echo == Endring i ressurs_aktivitet per aktivitet ==
SELECT a.kode, a.navn, coalesce(n.antall, 0) AS lagt_til, coalesce(b.antall, 0) AS fjernet
FROM aktivitet a
LEFT JOIN (SELECT aktivitet_id, count(*) AS antall FROM
              (SELECT ressurs_id, aktivitet_id FROM ressurs_aktivitet
               EXCEPT SELECT ressurs_id, aktivitet_id FROM _for_ra) x GROUP BY 1) n ON n.aktivitet_id = a.id
LEFT JOIN (SELECT aktivitet_id, count(*) AS antall FROM
              (SELECT ressurs_id, aktivitet_id FROM _for_ra
               EXCEPT SELECT ressurs_id, aktivitet_id FROM ressurs_aktivitet) x GROUP BY 1) b ON b.aktivitet_id = a.id
WHERE n.antall IS NOT NULL OR b.antall IS NOT NULL
ORDER BY a.kode;

\echo == Endring i ressurs_fasilitet per fasilitet ==
SELECT f.kode, f.navn, coalesce(n.antall, 0) AS lagt_til, coalesce(b.antall, 0) AS fjernet
FROM fasilitet f
LEFT JOIN (SELECT fasilitet_id, count(*) AS antall FROM
              (SELECT ressurs_id, fasilitet_id FROM ressurs_fasilitet
               EXCEPT SELECT ressurs_id, fasilitet_id FROM _for_rf) x GROUP BY 1) n ON n.fasilitet_id = f.id
LEFT JOIN (SELECT fasilitet_id, count(*) AS antall FROM
              (SELECT ressurs_id, fasilitet_id FROM _for_rf
               EXCEPT SELECT ressurs_id, fasilitet_id FROM ressurs_fasilitet) x GROUP BY 1) b ON b.fasilitet_id = f.id
WHERE n.antall IS NOT NULL OR b.antall IS NOT NULL
ORDER BY f.kode;

\echo == Endring i ressurs.lokaletype_id (fra, til, antall ressurser) ==
SELECT o.kode AS fra, n.kode AS til, count(*) AS antall
FROM _for_lt s
JOIN ressurs r ON r.id = s.ressurs_id
LEFT JOIN lokaletype o ON o.id = s.lokaletype_id
LEFT JOIN lokaletype n ON n.id = r.lokaletype_id
WHERE s.lokaletype_id IS DISTINCT FROM r.lokaletype_id
GROUP BY 1, 2
ORDER BY 1, 2;

"""


def main():
    ap = argparse.ArgumentParser(
        description="Bygger ressurs_aktivitet, ressurs_fasilitet og ressurs.lokaletype_id på nytt (SQL til stdout).")
    ap.add_argument("--dry-run", action="store_true",
                    help="skriv rapporten, men rull tilbake alle endringer")
    args = ap.parse_args()

    slutt = "\\echo TØRRKJØRING: alt rulles tilbake\nROLLBACK;\n" if args.dry_run else "COMMIT;\n"
    sys.stdout.write(SQL + slutt)


if __name__ == "__main__":
    main()
