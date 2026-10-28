#!/usr/bin/env python3
"""
Tolker det kilden sa: laster vokabularet og mappingen fra filene i
etl/*_mapping/ til databasen, og bygger koblingene mellom ressurs og kodeverk fra
ressurs_kildekode og mappingen. Henter ingenting fra kommunene, så skriptet kan
kjøres alene når en mappingfil er endret. Kjør etl/last_inn.py først.

Bruker bare Pythons innebygde bibliotek. Som last_inn.py gjør skriptet
ingenting mot databasen selv; det leser kildekodene fra standard-inn og skriver
SQL-tekst til standard-ut, som du deretter sender til Postgres. Kildekodene må
leses inn fordi navnene normaliseres i Python.

Bruk:
    # 1. Hent kildekodene fra databasen
    docker exec portico_masterdb psql -q -tA -F$'\\t' -U postgres -d masterdb -c "
        SELECT fi.kildenokkel, kk.kodetype, kk.kode, kk.navn
        FROM kildekode kk JOIN fagsystem_instans fi ON fi.id = kk.fagsystem_instans_id
        ORDER BY 1, 2, 3" > etl/ut/kildekoder.tsv

    # 2. Tørrkjøring: kjører alt, skriver rapporten og ruller tilbake.
    python3 etl/last_mapping.py --dry-run < etl/ut/kildekoder.tsv > etl/ut/mapping.sql
    docker exec -i portico_masterdb psql -q -U postgres -d masterdb < etl/ut/mapping.sql

    # 3. Ekte kjøring:
    python3 etl/last_mapping.py < etl/ut/kildekoder.tsv > etl/ut/mapping.sql
    docker exec -i portico_masterdb psql -q -U postgres -d masterdb < etl/ut/mapping.sql

-q gjør psql stille (ingen kommandokoder som "DELETE 3" eller "SELECT 1234");
rapporten og eventuelle feil vises fortsatt. Utelat -q for å se hver setning.

Hva SQL-en gjør, i én transaksjon:
  aktivitet           vokabularet fra activity_mapping/activities.json
  aktivitet_mapping   aktivitetskoder kartlagt via activity_mapping/mapping.json
  kildekode_mapping   lokaletype- og fasilitetskoder kartlagt via
                      lokaletype_mapping/ og fasilitet_mapping/. Rader med
                      kartlagt_av <> 'etl' (manuelle) overskrives aldri.
  ressurs_aktivitet   alle (ressurs, aktivitet) der ressursen har en kildekode som er
                      godkjent mappet til aktiviteten (aktivitet_mapping)
  ressurs_fasilitet   det samme for fasilitet (kildekode_mapping)
  ressurs.lokaletype_id  ressursens lokaletype fra dens lokaletype-kildekode
                      (kildekode_mapping); NULL uten godkjent mapping

Koblingene synkroniseres som diff: bare det som endres, skrives. Til slutt skrives
en rapport over hva som ble lagt til og fjernet per konsept.

Omfang for koblingene: bare instanser som har rader i ressurs_kildekode (for
lokaletype: av kodetypen lokaletype). Uten det ville en tabell som ikke er fylt
ennå, tømt koblingene til alle ressurser.
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

# SQL-literaler og HTML-rensing deles med last_inn.py, så et kildenavn renses
# likt begge steder.
from last_inn import q, rens


def les_mapping(mappe: str) -> dict:
    with open(Path(__file__).parent / mappe / "mapping.json", encoding="utf-8") as f:
        return json.load(f)["values"]


# Normalisert kildenavn -> kode i vårt eget kodeverk (lokaletype/fasilitet,
# seedet i Flyway V1; aktivitet, se under). Navn som ikke finnes her, får ingen
# kartlegging - de dukker opp i v_ukartlagte_kildekoder og må kobles manuelt.
LOKALETYPE = les_mapping("lokaletype_mapping")
FASILITET = les_mapping("fasilitet_mapping")
TABELL = {"lokaletype": LOKALETYPE, "fasilitet": FASILITET}

# Aktivitet har et eget, rikere format (se activity_mapping/
# AktivKommune_activity_normalisation.md): mapping.json har under "values"
# ett oppslag per normalisert kildenavn (norm_aktivitet), med konsept-ID-ene
# i "activities", og activities.json er vokabularet de peker på, gruppert per
# fasett. Øvrige felt (confidence, status, attributes, reason, sourceNames)
# brukes ikke foreløpig. Alle fasetter unntatt "exclude" lastes inn i tabellen
# aktivitet; EXC-konsepter gir status 'ikke_relevant'. Kartleggingen skrives
# til tabellen aktivitet_mapping, ikke kildekode_mapping.
with open(Path(__file__).parent / "activity_mapping" / "mapping.json", encoding="utf-8") as f:
    _aktivitet_mapping = json.load(f)
AKTIVITET = {navn: v["activities"] for navn, v in _aktivitet_mapping["values"].items()}
with open(Path(__file__).parent / "activity_mapping" / "activities.json", encoding="utf-8") as f:
    VOKABULAR = json.load(f)["facets"]
EKSKLUDER = {kode: k["label"]["nb"] for kode, k in VOKABULAR["exclude"].items()}
# F.eks. "AktivKommune_activity_mapping_v0.3" - følger versjonen i mapping.json.
AKTIVITET_MERKNAD = Path(_aktivitet_mapping.get("source", "activity_mapping")).stem

# Junk uansett kodetype: adresser, stedsnavn og driftsstatus som aldri kan
# være en ekte lokaletype, aktivitet eller fasilitet.
IKKE_RELEVANT_UNIVERSELT = {
    "stengt", "fiktivt rom", "kantinebidrag",
    "kvitsoygata 3", "judaberg innbyggertorg", "mostun natursenter",
}

# Junk KUN i én kodetype-kontekst - kan være en ekte verdi i en annen. F.eks.
# er "Inkludering" ikke en stedstype, men er en fullt plausibel aktivitet
# (inkluderingstiltak er en vanlig kommunal kategori). For aktivitet avgjør
# mapping.json selv hva som er junk (EXC-konsepter); IKKE_RELEVANT_UNIVERSELT
# brukes der bare som reserve for navn som mangler i mapping.json.
IKKE_RELEVANT_PER_TYPE = {
    "lokaletype": {"inkludering", "sosial aktivitet", "wc toalett"},
    "fasilitet": set(),
}


def er_ikke_relevant(kodetype: str, navn_normalisert: str) -> bool:
    return (navn_normalisert in IKKE_RELEVANT_UNIVERSELT
            or navn_normalisert in IKKE_RELEVANT_PER_TYPE.get(kodetype, set()))


def norm(s):
    """Normaliserer et navn for oppslag i kartleggingstabellene ovenfor:
    små bokstaver, norske bokstaver til ascii, tegnsetting bort."""
    s = rens(s) or ""
    s = s.lower().replace("ø", "o").replace("æ", "a").replace("å", "a")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def norm_aktivitet(s):
    """Normaliserer et aktivitetsnavn for oppslag i activity_mapping/
    mapping.json. Mildere enn norm(): beholder æ/ø/å og tegnsetting, og må
    være identisk med reglene i AktivKommune_activity_normalisation.md §4.4
    (dobbel HTML-avkoding, trim, sammenslåtte mellomrom, små bokstaver)."""
    return (rens(s) or "").lower()


def vokabular_sql() -> str:
    """Upsert av aktivitetsvokabularet fra activities.json - alle fasetter
    unntatt "exclude". Foreldre settes i et eget steg, siden rekkefølgen i
    filen ikke garanterer at forelderen kommer før barnet. Konsepter med to
    foreldre (f.eks. Dans) får den første, se aktivitet i schema_kjerne.sql."""
    konsepter = [(kode, k) for fasett, ks in VOKABULAR.items() if fasett != "exclude"
                 for kode, k in ks.items()]
    verdier = ",\n".join(f"({q(kode)},{q(k['label']['nb'])})" for kode, k in konsepter)
    foreldre = ",\n".join(f"({q(kode)},{q(k['broader'][0])})" for kode, k in konsepter if k.get("broader"))
    rotter = ",".join(q(kode) for kode, k in konsepter if not k.get("broader"))
    return (f"INSERT INTO aktivitet (kode,navn) VALUES\n{verdier}\n"
            f"ON CONFLICT (kode) DO UPDATE SET navn=EXCLUDED.navn;\n"
            f"UPDATE aktivitet a SET parent_id=p.id FROM (VALUES\n{foreldre}\n) AS v(kode,forelder) "
            f"JOIN aktivitet p ON p.kode=v.forelder "
            f"WHERE a.kode=v.kode AND a.parent_id IS DISTINCT FROM p.id;\n"
            f"UPDATE aktivitet SET parent_id=NULL WHERE kode IN ({rotter}) AND parent_id IS NOT NULL;\n\n")


def aktivitet_mapping_sql(kn, kode, navn) -> str:
    """Kartlegging av én aktivitetskode via activity_mapping/mapping.json, til
    tabellen aktivitet_mapping. Ett navn kan gi flere konsepter, og da én rad
    per konsept. Tidligere
    ETL-rader for koden fjernes først, slik at endringer i mapping.json slår
    igjennom - men bare når koden ikke har noen manuell mapping, som aldri
    overskrives."""
    kk = (f"FROM kildekode kk JOIN fagsystem_instans fi ON fi.id=kk.fagsystem_instans_id "
          f"WHERE fi.kildenokkel={q(kn)} AND kk.kodetype='aktivitet' AND kk.kode={q(kode)} ")
    uten_manuell = ("AND NOT EXISTS (SELECT 1 FROM aktivitet_mapping m2 WHERE m2.kildekode_id=kk.id "
                    "AND m2.kartlagt_av IS DISTINCT FROM 'etl')")
    sql = (f"DELETE FROM aktivitet_mapping m USING kildekode kk "
           f"JOIN fagsystem_instans fi ON fi.id=kk.fagsystem_instans_id "
           f"WHERE m.kildekode_id=kk.id AND m.kartlagt_av='etl' AND fi.kildenokkel={q(kn)} "
           f"AND kk.kodetype='aktivitet' AND kk.kode={q(kode)} {uten_manuell};\n")

    konsepter = AKTIVITET.get(norm_aktivitet(navn))
    if konsepter is None:
        if not er_ikke_relevant("aktivitet", norm(navn)):
            return sql  # ukartlagt - dukker opp i v_ukartlagte_kildekoder
        merknad = "Ikke en gyldig aktivitet"
    else:
        ekte = [c for c in konsepter if c not in EKSKLUDER]
        if ekte:
            return sql + (
                f"INSERT INTO aktivitet_mapping (kildekode_id,aktivitet_id,status,merknad,kartlagt_av) "
                f"SELECT kk.id,t.id,'godkjent',{q(AKTIVITET_MERKNAD)},'etl' "
                f"FROM kildekode kk JOIN fagsystem_instans fi ON fi.id=kk.fagsystem_instans_id, aktivitet t "
                f"WHERE fi.kildenokkel={q(kn)} AND kk.kodetype='aktivitet' AND kk.kode={q(kode)} "
                f"AND t.kode IN ({','.join(q(c) for c in ekte)}) {uten_manuell} "
                f"ON CONFLICT (kildekode_id,aktivitet_id) WHERE aktivitet_id IS NOT NULL DO NOTHING;\n")
        merknad = f"{EKSKLUDER[konsepter[0]]} ({AKTIVITET_MERKNAD})"
    return sql + (
        f"INSERT INTO aktivitet_mapping (kildekode_id,status,merknad,kartlagt_av) "
        f"SELECT kk.id,'ikke_relevant',{q(merknad)},'etl' {kk}{uten_manuell} "
        f"ON CONFLICT (kildekode_id) WHERE aktivitet_id IS NULL DO NOTHING;\n")


def kildekode_mapping_sql(kn, kodetype, kode, navn) -> str:
    """Kartlegging av én lokaletype- eller fasilitetskode til kildekode_mapping.
    Raden settes bare inn hvis koden ikke har en fra før (ON CONFLICT DO
    NOTHING), så en eksisterende mapping, også en manuell, røres aldri."""
    n = norm(navn)
    if er_ikke_relevant(kodetype, n):
        return (f"INSERT INTO kildekode_mapping (kildekode_id,status,merknad,kartlagt_av) "
                f"SELECT kk.id,'ikke_relevant',{q(f'Ikke en gyldig {kodetype}')},'etl' "
                f"FROM kildekode kk JOIN fagsystem_instans fi ON fi.id=kk.fagsystem_instans_id "
                f"WHERE fi.kildenokkel={q(kn)} AND kk.kodetype={q(kodetype)} AND kk.kode={q(kode)} "
                f"ON CONFLICT (kildekode_id) DO NOTHING;\n")
    if n in TABELL[kodetype]:
        maalkol = {"lokaletype": "lokaletype_id", "fasilitet": "fasilitet_id"}[kodetype]
        return (f"INSERT INTO kildekode_mapping (kildekode_id,{maalkol},status,kartlagt_av) "
                f"SELECT kk.id,t.id,'godkjent','etl' "
                f"FROM kildekode kk JOIN fagsystem_instans fi ON fi.id=kk.fagsystem_instans_id, {kodetype} t "
                f"WHERE fi.kildenokkel={q(kn)} AND kk.kodetype={q(kodetype)} "
                f"AND kk.kode={q(kode)} AND t.kode={q(TABELL[kodetype][n])} "
                f"ON CONFLICT (kildekode_id) DO NOTHING;\n")
    return ""  # ukartlagt - dukker opp i v_ukartlagte_kildekoder


def les_kildekoder(inn) -> list:
    """Leser tabulatorseparerte linjer: kildenokkel, kodetype, kode, navn.
    Navnet er alltid renset for tabulator og linjeskift av last_inn.py (rens())."""
    rader = []
    for nr, linje in enumerate(inn, 1):
        linje = linje.rstrip("\r\n")
        if not linje:
            continue
        deler = linje.split("\t", 3)
        if len(deler) < 4 or deler[1] not in ("lokaletype", "aktivitet", "fasilitet"):
            print(f"  hopper over linje {nr}: uventet format", file=sys.stderr)
            continue
        rader.append(tuple(deler))
    return rader


# Koblingene bygges etter at mappingradene er skrevet, i samme transaksjon.
KOBLINGER = r"""
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
        description="Laster vokabular og mapping, og bygger koblingene mellom ressurs og kodeverk "
                    "(kildekoder fra stdin, SQL til stdout).")
    ap.add_argument("--dry-run", action="store_true",
                    help="skriv rapporten, men rull tilbake alle endringer")
    args = ap.parse_args()

    if sys.stdin.isatty():
        print("Leser kildekoder fra standard-inn (kildenokkel<TAB>kodetype<TAB>kode<TAB>navn). "
              "Se bruk i toppen av filen.", file=sys.stderr)
        sys.exit(1)
    kildekoder = les_kildekoder(sys.stdin)
    if not kildekoder:
        print("Ingen kildekoder på standard-inn - ingenting å gjøre. Kjør etl/last_inn.py først.",
              file=sys.stderr)
        sys.exit(1)
    print(f"  {len(kildekoder)} kildekoder", file=sys.stderr)

    ut = sys.stdout
    ut.write("\\set ON_ERROR_STOP on\nBEGIN;\n\n")
    # Vokabularet først: mappingradene peker på det.
    ut.write(vokabular_sql())
    for kn, kodetype, kode, navn in kildekoder:
        if kodetype == "aktivitet":
            ut.write(aktivitet_mapping_sql(kn, kode, navn))
        else:
            ut.write(kildekode_mapping_sql(kn, kodetype, kode, navn))
    ut.write("\n")
    ut.write(KOBLINGER)
    ut.write("\\echo TØRRKJØRING: alt rulles tilbake\nROLLBACK;\n" if args.dry_run else "COMMIT;\n")


if __name__ == "__main__":
    main()
