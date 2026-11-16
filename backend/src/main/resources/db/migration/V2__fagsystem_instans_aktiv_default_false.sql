-- A new fagsystem_instans starts inactive, so the nightly sync does not fetch from a
-- kommune before its booking system is up and running. Activate it with
-- PATCH /masterdb/kommune/{id}/booking {"aktiv": true}. Existing rows are not changed.
-- etl/last_inn.py sets aktiv = TRUE explicitly for the seed kommuner.
ALTER TABLE fagsystem_instans ALTER COLUMN aktiv SET DEFAULT FALSE;
