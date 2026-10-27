-- V2: ressurs_kildekode
--
-- Hvilke lokale koder kilden ga hver ressurs: aktivitet, fasilitet og lokaletype
-- (kodetypen ligger på kildekode.kodetype). Dette er det kilden faktisk sa, uten
-- tolkning. Mappingen fra lokal kode til vårt eget kodeverk ligger i de egne
-- mappingtabellene.
--
-- Tabellen gjør at en endret mapping senere kan slå inn uten ny henting fra
-- kommunene: koblingene mellom ressurs og kodeverk kan regnes ut fra denne og
-- mappingen. Skrives av etl/last_inn.py.
--
-- Rent tilføyende: ingenting leser tabellen ennå.
CREATE TABLE ressurs_kildekode
(
    ressurs_id   BIGINT NOT NULL REFERENCES ressurs(id) ON DELETE CASCADE,
    kildekode_id BIGINT NOT NULL REFERENCES kildekode(id) ON DELETE CASCADE,
    PRIMARY KEY (ressurs_id, kildekode_id)
);

-- Omvendt oppslag: hvilke ressurser har denne kildekoden.
CREATE INDEX ix_ressurs_kildekode_kode ON ressurs_kildekode (kildekode_id);
