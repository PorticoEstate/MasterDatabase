-- The kommuner that synk.py (and the demo normaliser) should fetch: every
-- kommune with an active Aktiv kommune booking instance in the database.
-- Run with: psql -tA -F'|' -f kommuner_query.sql
-- Output, one line per kommune: slug|kommunenr|navn|fylkesnavn
--
-- The slug is the part of fagsystem_instans.kildenokkel after 'aktiv-kommune:',
-- the same key last_inn.py and synk.py write. A kommune without such an instance
-- is not listed, and so is not synced. Set fagsystem_instans.aktiv = false to
-- stop syncing one.
SELECT substr(fi.kildenokkel, length('aktiv-kommune:') + 1) AS slug,
       k.kommunenr, k.navn, COALESCE(k.fylkesnavn, '')
FROM kommune k
JOIN kommune_fagsystem_instans kfi ON kfi.kommune_id = k.id
JOIN fagsystem_instans fi ON fi.id = kfi.fagsystem_instans_id
WHERE fi.type = 'booking'
  AND fi.aktiv
  AND fi.kildenokkel LIKE 'aktiv-kommune:%'
ORDER BY slug;
