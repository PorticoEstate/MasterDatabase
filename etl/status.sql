-- Read-only overview for checking a deployment.
-- Run with: docker compose exec etl ./run.sh status
\echo '== Row counts'
SELECT 'kommune' AS tabell, count(*) AS antall FROM kommune
UNION ALL SELECT 'fagsystem_instans', count(*) FROM fagsystem_instans
UNION ALL SELECT 'bygning', count(*) FROM bygning
UNION ALL SELECT 'adresse', count(*) FROM adresse
UNION ALL SELECT 'gate', count(*) FROM gate
UNION ALL SELECT 'ressurs', count(*) FROM ressurs
UNION ALL SELECT 'lokaletype', count(*) FROM lokaletype
UNION ALL SELECT 'aktivitet', count(*) FROM aktivitet
UNION ALL SELECT 'fasilitet', count(*) FROM fasilitet
UNION ALL SELECT 'ressurs_aktivitet', count(*) FROM ressurs_aktivitet
UNION ALL SELECT 'ressurs_fasilitet', count(*) FROM ressurs_fasilitet
UNION ALL SELECT 'synk_avvik', count(*) FROM synk_avvik;

\echo '== Addresses by geocoding status'
SELECT geokoding, count(*) AS antall FROM adresse GROUP BY geokoding ORDER BY geokoding;

\echo '== Buildings with a building number from Matrikkel'
SELECT count(*) FILTER (WHERE bygningsnr IS NOT NULL) AS med_bygningsnr, count(*) AS totalt FROM bygning;

\echo '== Latest extract per source'
SELECT DISTINCT ON (kilde) kilde, hentet_at, http_status FROM kildeuttrekk ORDER BY kilde, hentet_at DESC;

\echo '== Deviations (synk_avvik), largest groups first'
SELECT kilde, avvikstype, count(*) AS antall FROM synk_avvik GROUP BY kilde, avvikstype ORDER BY antall DESC, kilde LIMIT 15;
