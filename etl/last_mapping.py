#!/usr/bin/env python3
r"""
Tolker det kilden sa: laster vokabularet og mappingen fra filene i
etl/*_mapping/ til databasen. Koblingene mellom ressurs og kodeverk følger av
seg selv (se under). Henter ingenting fra kommunene, så skriptet kan kjøres
alene når en mappingfil er endret. Kjør etl/last_inn.py først.

Bruker bare Pythons innebygde bibliotek. Som last_inn.py gjør skriptet
ingenting mot databasen selv; det leser kildekodene fra standard-inn og skriver
SQL-tekst til standard-ut, som du deretter sender til Postgres. Kildekodene må
leses inn fordi navnene normaliseres i Python.

Bruk (etl/kjor_alt.sh mapping [--dry-run] gjør dette for deg):
    # 1. Hent kildekodene fra databasen og send dem rett inn i skriptet.
    #    Tørrkjøring: kjører alt, skriver rapporten og ruller tilbake.
    docker exec portico_masterdb psql -q -tA -F$'\t' -U postgres -d masterdb -c "
        SELECT fi.kildenokkel, kk.kodetype, kk.kode, kk.navn
        FROM kildekode kk JOIN fagsystem_instans fi ON fi.id = kk.fagsystem_instans_id
        ORDER BY 1, 2, 3" | python3 etl/last_mapping.py --dry-run > etl/ut/mapping.sql

    # 2. Kjør SQL-en. For en ekte kjøring: utelat --dry-run over og kjør på nytt.
    docker exec -i portico_masterdb psql -q -U postgres -d masterdb < etl/ut/mapping.sql

-q gjør psql stille (ingen kommandokoder som "DELETE 3" eller "SELECT 1234");
rapporten og eventuelle feil vises fortsatt. Utelat -q for å se hver setning.

Hva SQL-en gjør, i én transaksjon:
  aktivitet           vokabularet fra activity_mapping/activities.json
  lokaletype          vokabularet fra lokaletype_mapping/venue_types.json
  fasilitet           vokabularet fra fasilitet_mapping/facilities.json
  aktivitet_mapping   aktivitetskoder kartlagt via activity_mapping/mapping.json
  lokaletype_mapping  lokaletypekoder kartlagt via lokaletype_mapping/mapping.json
  fasilitet_mapping   fasilitetskoder kartlagt via fasilitet_mapping/mapping.json
                      I alle tre fornyes ETL-radene hver kjøring, mens rader med
                      kartlagt_av <> 'etl' (manuelle) overskrives aldri.
                      En kildekode som mangler i mapping.json får ingen rad og
                      vises i v_ukartlagte_kildekoder. Konsepter i fasetten
                      "exclude" gir status 'ikke_relevant'.

Koblingene mellom ressurs og kodeverk (ressurs_aktivitet, ressurs_fasilitet og
ressurs_lokaletype) er visninger som regnes ut fra ressurs_kildekode og godkjent
mapping, så de følger mappingen av seg selv. Skriptet skriver derfor ikke til dem,
men tar et øyeblikksbilde før mappingen endres og skriver til slutt en rapport over
hva som ble lagt til og fjernet per konsept.
"""
import argparse
import json
import sys
import unicodedata
from pathlib import Path

# SQL-literaler og HTML-rensing deles med last_inn.py, så et kildenavn renses
# likt begge steder.
from last_inn import q, rens


def les_json(mappe: str, fil: str) -> dict:
    with open(Path(__file__).parent / mappe / fil, encoding="utf-8") as f:
        return json.load(f)


# Mappingfilen og vokabularfilen per kodetype. mapping.json har under "values"
# ett oppslag per normalisert kildenavn (norm), med kodene i vokabularet i
# feltet "felt". Vokabularfilen er gruppert per fasett. Fasetten "exclude"
# lastes ikke inn som vokabular: kodene i den gir status 'ikke_relevant'.
# Øvrige felt (confidence, status, attributes, reason, sourceNames) brukes ikke
# foreløpig. Navn som ikke finnes i mapping.json får ingen kartlegging - de
# dukker opp i v_ukartlagte_kildekoder og må kobles manuelt.
KODETYPER = {
    "aktivitet":  {"mappe": "activity_mapping",   "vokabular": "activities.json",  "felt": "activities"},
    "lokaletype": {"mappe": "lokaletype_mapping", "vokabular": "venue_types.json", "felt": "venueType"},
    "fasilitet":  {"mappe": "fasilitet_mapping",  "vokabular": "facilities.json",  "felt": "facilities"},
}


def som_liste(kode):
    """Lokaletype har én kode per navn (tekst), de andre en liste med koder."""
    return [kode] if isinstance(kode, str) else kode


def les_kodetype(k: dict) -> dict:
    mapping = les_json(k["mappe"], "mapping.json")
    vokabular = les_json(k["mappe"], k["vokabular"])["facets"]
    return {
        "mapping": {navn: som_liste(v[k["felt"]]) for navn, v in mapping["values"].items()},
        "vokabular": vokabular,
        "ekskluder": {kode: x["label"]["nb"] for kode, x in vokabular["exclude"].items()},
        # F.eks. "AktivKommune_activity_mapping_v0.3" - følger versjonen i mapping.json.
        "merknad": Path(mapping.get("source", k["mappe"])).stem,
    }


DATA = {kodetype: les_kodetype(k) for kodetype, k in KODETYPER.items()}


def norm(s):
    """Normaliserer et kildenavn for oppslag i mapping.json. Må være identisk med
    normaliseringen filene oppgir: dobbel HTML-avkoding, unicode NFC, trim,
    sammenslåtte mellomrom og små bokstaver (se activity_mapping/
    AktivKommune_activity_normalisation.md §4.4)."""
    return unicodedata.normalize("NFC", rens(s) or "").lower()


# Mappingtabell, målkolonne og kodeverkstabell per kodetype. Alle tre tabellene har
# samme oppbygning.
MAPPINGTABELL = {
    "aktivitet": ("aktivitet_mapping", "aktivitet_id", "aktivitet"),
    "lokaletype": ("lokaletype_mapping", "lokaletype_id", "lokaletype"),
    "fasilitet": ("fasilitet_mapping", "fasilitet_id", "fasilitet"),
}

# Per kodeverkstabell: kolonnen som holder fasetten (ingen for aktivitet, der
# kodeprefikset bærer den), og om konseptene har foreldre (broader -> parent_id).
VOKABULARKOLONNER = {
    "aktivitet": (None, True),
    "lokaletype": ("fasett", True),
    "fasilitet": ("gruppe", False),
}


def vokabular_sql(kodetype) -> str:
    """Upsert av vokabularet fra vokabularfilen - alle fasetter unntatt "exclude".
    Foreldre settes i et eget steg, siden rekkefølgen i filen ikke garanterer at
    forelderen kommer før barnet. Konsepter med to foreldre (f.eks. Dans) får
    den første, se aktivitet i schema_kjerne.sql."""
    tabell = MAPPINGTABELL[kodetype][2]
    fasettkolonne, har_foreldre = VOKABULARKOLONNER[kodetype]
    konsepter = [(kode, k, fasett) for fasett, ks in DATA[kodetype]["vokabular"].items()
                 if fasett != "exclude" for kode, k in ks.items()]
    kolonner = "kode,navn" + (f",{fasettkolonne}" if fasettkolonne else "")
    oppdater = "navn=EXCLUDED.navn" + (f",{fasettkolonne}=EXCLUDED.{fasettkolonne}" if fasettkolonne else "")
    verdier = ",\n".join(
        f"({q(kode)},{q(k['label']['nb'])}" + (f",{q(fasett)}" if fasettkolonne else "") + ")"
        for kode, k, fasett in konsepter)
    sql = (f"INSERT INTO {tabell} ({kolonner}) VALUES\n{verdier}\n"
           f"ON CONFLICT (kode) DO UPDATE SET {oppdater};\n")
    if har_foreldre:
        foreldre = ",\n".join(f"({q(kode)},{q(k['broader'][0])})" for kode, k, _ in konsepter if k.get("broader"))
        rotter = ",".join(q(kode) for kode, k, _ in konsepter if not k.get("broader"))
        sql += (f"UPDATE {tabell} a SET parent_id=p.id FROM (VALUES\n{foreldre}\n) AS v(kode,forelder) "
                f"JOIN {tabell} p ON p.kode=v.forelder "
                f"WHERE a.kode=v.kode AND a.parent_id IS DISTINCT FROM p.id;\n"
                f"UPDATE {tabell} SET parent_id=NULL WHERE kode IN ({rotter}) AND parent_id IS NOT NULL;\n")
    return sql + "\n"


def onsket(kodetype, navn):
    """Ønsket mapping for én kildekode: (status, målkoder, merknad), eller None
    hvis koden er ukartlagt (den dukker da opp i v_ukartlagte_kildekoder).
    status er 'godkjent' (med én eller flere målkoder) eller 'ikke_relevant'."""
    d = DATA[kodetype]
    koder = d["mapping"].get(norm(navn))
    if koder is None:
        return None
    ekte = [c for c in koder if c not in d["ekskluder"]]
    if ekte:
        return ("godkjent", ekte, d["merknad"])
    return ("ikke_relevant", [], f"{d['ekskluder'][koder[0]]} ({d['merknad']})")


def mapping_sql(kn, kodetype, kode, navn) -> str:
    """Kartlegging av én kildekode til mappingtabellen for kodetypen. Ett navn
    kan gi flere konsepter, og da én rad per konsept. Tidligere ETL-rader for
    koden fjernes først, slik at endringer i mappingfilene slår igjennom - men
    bare når koden ikke har noen manuell mapping (kartlagt_av <> 'etl'), som
    aldri overskrives."""
    tabell, maalkol, maal = MAPPINGTABELL[kodetype]
    kk = (f"FROM kildekode kk JOIN fagsystem_instans fi ON fi.id=kk.fagsystem_instans_id "
          f"WHERE fi.kildenokkel={q(kn)} AND kk.kodetype={q(kodetype)} AND kk.kode={q(kode)} ")
    uten_manuell = (f"AND NOT EXISTS (SELECT 1 FROM {tabell} m2 WHERE m2.kildekode_id=kk.id "
                    f"AND m2.kartlagt_av IS DISTINCT FROM 'etl')")
    sql = (f"DELETE FROM {tabell} m USING kildekode kk "
           f"JOIN fagsystem_instans fi ON fi.id=kk.fagsystem_instans_id "
           f"WHERE m.kildekode_id=kk.id AND m.kartlagt_av='etl' AND fi.kildenokkel={q(kn)} "
           f"AND kk.kodetype={q(kodetype)} AND kk.kode={q(kode)} {uten_manuell};\n")

    mal = onsket(kodetype, navn)
    if mal is None:
        return sql
    status, koder, merknad = mal
    if status == "godkjent":
        return sql + (
            f"INSERT INTO {tabell} (kildekode_id,{maalkol},status,merknad,kartlagt_av) "
            f"SELECT kk.id,t.id,'godkjent',{q(merknad)},'etl' "
            f"FROM kildekode kk JOIN fagsystem_instans fi ON fi.id=kk.fagsystem_instans_id, {maal} t "
            f"WHERE fi.kildenokkel={q(kn)} AND kk.kodetype={q(kodetype)} AND kk.kode={q(kode)} "
            f"AND t.kode IN ({','.join(q(c) for c in koder)}) {uten_manuell} "
            f"ON CONFLICT DO NOTHING;\n")
    return sql + (
        f"INSERT INTO {tabell} (kildekode_id,status,merknad,kartlagt_av) "
        f"SELECT kk.id,'ikke_relevant',{q(merknad)},'etl' {kk}{uten_manuell} "
        f"ON CONFLICT DO NOTHING;\n")


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


# Koblingene (ressurs_aktivitet, ressurs_fasilitet, ressurs_lokaletype) er visninger
# som regnes ut fra ressurs_kildekode og godkjent mapping, så de følger mappingen
# av seg selv. Øyeblikksbildet tas før mappingen endres, slik at rapporten kan
# vise hva endringen gjorde.
FOR_ENDRING = r"""
CREATE TEMP TABLE _for_ra ON COMMIT DROP AS SELECT ressurs_id, aktivitet_id FROM ressurs_aktivitet;
CREATE TEMP TABLE _for_rf ON COMMIT DROP AS SELECT ressurs_id, fasilitet_id FROM ressurs_fasilitet;
CREATE TEMP TABLE _for_lt ON COMMIT DROP AS SELECT ressurs_id, lokaletype_id FROM ressurs_lokaletype;

"""

RAPPORT = r"""
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

\echo == Endring i lokaletype per ressurs (fra, til, antall ressurser) ==
SELECT o.kode AS fra, n.kode AS til, count(*) AS antall
FROM _for_lt s
FULL JOIN ressurs_lokaletype rl ON rl.ressurs_id = s.ressurs_id
LEFT JOIN lokaletype o ON o.id = s.lokaletype_id
LEFT JOIN lokaletype n ON n.id = rl.lokaletype_id
WHERE s.lokaletype_id IS DISTINCT FROM rl.lokaletype_id
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
    ut.write("\\set ON_ERROR_STOP on\nBEGIN;\n")
    # Øyeblikksbildet av koblingene må tas før noe endres.
    ut.write(FOR_ENDRING)
    # Vokabularet først: mappingradene peker på det.
    for kodetype in KODETYPER:
        ut.write(vokabular_sql(kodetype))
    for kn, kodetype, kode, navn in kildekoder:
        ut.write(mapping_sql(kn, kodetype, kode, navn))
    ut.write("\n")
    ut.write(RAPPORT)
    ut.write("\\echo TØRRKJØRING: alt rulles tilbake\nROLLBACK;\n" if args.dry_run else "COMMIT;\n")


if __name__ == "__main__":
    main()
