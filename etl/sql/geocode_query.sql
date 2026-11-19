-- Addresses that jobs/geocode.py should look up in the Matrikkel.
-- Run with: psql -tA -F'|' -f etl/sql/geocode_query.sql
-- Same query as in etl/docs/jobs/geocode.md. The four
-- OR terms make it safe to re-run: a row only appears while geocoding, the
-- building number or the matrikkelinfo link is still missing, or while a
-- building number from the source (cadastral_references) is not yet verified.
SELECT a.id, a.adressetekst, a.postnummer, a.poststed, k.kommunenr,
       a.bygning_id, a.geokoding, a.gate_id, a.husnr, a.bokstav, g.adressekode,
       b.bygningsnr
FROM adresse a
JOIN bygning b ON b.id = a.bygning_id
JOIN kommune k ON k.id = b.kommune_id
LEFT JOIN gate g ON g.id = a.gate_id
WHERE a.er_hovedadresse AND a.geokoding <> 'manuell' AND a.adressetekst IS NOT NULL
  AND (a.geokoding = 'ukjent' OR b.bygningsnr IS NULL
       OR NOT EXISTS (SELECT 1 FROM matrikkelinfo m WHERE m.bygning_id = b.id)
       OR (b.bygningsnr IS NOT NULL AND b.matrikkel_match IN ('ikke_forsokt','ikke_funnet')));
