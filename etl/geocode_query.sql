-- Addresses that matrikkel_adresse.py should look up in the Matrikkel.
-- Run with: psql -tA -F'|' -f geocode_query.sql
-- Same query as in etl/README.md ("Geokoding og bygningsberikelse"). The three
-- OR terms make it safe to re-run: a row only appears while geocoding, the
-- building number or the matrikkelinfo link is still missing.
SELECT a.id, a.adressetekst, a.postnummer, a.poststed, k.kommunenr,
       a.bygning_id, a.geokoding, a.gate_id, a.husnr, a.bokstav, g.adressekode
FROM adresse a
JOIN bygning b ON b.id = a.bygning_id
JOIN kommune k ON k.id = b.kommune_id
LEFT JOIN gate g ON g.id = a.gate_id
WHERE a.er_hovedadresse AND a.geokoding <> 'manuell' AND a.adressetekst IS NOT NULL
  AND (a.geokoding IN ('ukjent','feilet') OR b.bygningsnr IS NULL
       OR NOT EXISTS (SELECT 1 FROM matrikkelinfo m WHERE m.bygning_id = b.id));
