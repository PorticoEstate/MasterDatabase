#!/usr/bin/env python3
"""
Løpende synkronisering fra Aktiv kommune til masterdatabasen (til cron).

Samme innlasting som last_inn.py, men uten å skrive i kodeverkene
(lokaletype, aktivitet, fasilitet): masteren eier vokabularet og hierarkiet.
Alt kilden har som viker fra masteren (ukjent id, annet navn, annen forelder)
loggføres i synk_avvik. Det kommunen eier lastes derimot, og endringer slår
inn i masteren: bygg og ressurser (også nye), og koblingene ressurs -> bygg,
lokaletype, aktivitet og fasilitet. En kobling til en id masteren ikke kjenner
lastes ikke, og loggføres.

last_inn.py brukes én gang, når databasen bygges; dette skriptet brukes
etterpå. Begge forutsetter normaliserte instanser (se "Kildekontrakt" i
etl/README.md).

Bruk:
    python3 etl/synk.py alle > etl/ut/synk.sql
    docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/synk.sql

    # Les <mappe>/<kommune>.json i stedet for å hente fra nettet:
    python3 etl/synk.py alle --fra-fil etl/ut/normalisert > etl/ut/synk.sql

Skriptet gjør ingenting mot databasen selv; det skriver SQL-tekst til
standard-ut. Se etl/README.md for full forklaring.

Hver kjøring registrerer et kildeuttrekk (metadata: kilde, endepunkt,
tidspunkt, HTTP-status - ikke hele svaret). Ethvert avvik - ugyldige verdier,
brutte referanser, databasefeil - loggføres i synk_avvik sammen med den
konkrete posten (renset for personopplysninger) som utløste det, ikke bare en
feiltekst. Se db/schema_kjerne_dokumentasjon.md, "Innlasting og sporbarhet".

Kjent forenkling: kommune_id settes her fra hvilken Aktiv kommune-instans
ressursen kommer fra (f.eks. "bergen" -> kommunenr 4601). Det er riktig for
alle de 12 instansene vi kjenner i dag, som hver betjener nøyaktig én kommune.
Skjemaet (Flyway-migrasjonene i backend) tillater at en instans betjener flere kommuner
via kommune_fagsystem_instans; den dagen det faktisk skjer, må kommune_id i
stedet utledes fra en geokodet adresse. Se db/schema_kjerne_dokumentasjon.md.
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from helpers import ressurslenke_sql, hent_json, i_blokk, kommuner_fra_kommandolinje, logg, q, rens, som_heltall


# Kodeverkene i kilden: (tabell i masteren, samling i searchdataall). Masteren
# eier vokabularet og hierarkiet; instansene er normalisert mot det og bruker
# samme id-er. Synk skriver aldri i kodeverkstabellene: kildens samlinger (id,
# name, parent_id) sammenlignes med masteren, og avvik logges. Koblingene
# (ressurs -> lokaletype, aktivitet, fasilitet) eies av kommunen og lastes.
KODEVERK = (
    ("lokaletype", "resource_categories"),
    ("aktivitet", "activities"),
    ("fasilitet", "facilities"),
)


def kodeverk_sql(kn, tabell, samling, rader):
    """SQL for ett kodeverk fra kildens samling: en sammenligning mot masterens
    kodeverk som loggfører avvik. Masteren eier navn og hierarki, så ingenting
    skrives i kodeverkstabellen. Avvik: en id som ikke finnes i masteren, samme
    id med et annet navn eller en annen forelder, og poster som ikke kan
    sammenlignes (manglende eller ugyldig id, tomt navn, id som går igjen)."""
    sql = ""
    konsepter = {}   # id -> (navn, forelderens id eller None)
    for rad in rader:
        if rad.get("id") is None:
            sql += logg(kn, samling, "ugyldig_verdi", None, "posten mangler id", "id", rapost=rad)
            continue
        nr, feil = som_heltall(rad["id"])
        if feil:
            sql += logg(kn, samling, "ugyldig_verdi", rad["id"], "id " + feil, "id", rapost=rad)
            continue
        n = rens(rad.get("name"))
        if not n:
            sql += logg(kn, samling, "ugyldig_verdi", rad["id"], "name er tomt", "name", rapost=rad)
            continue
        if nr in konsepter:
            sql += logg(kn, samling, "ugyldig_verdi", rad["id"], "id finnes flere ganger", "id", rapost=rad)
            continue
        # En parent_id som ikke er et heltall sammenlignes som "ingen forelder", og blir et avvik mot masteren.
        konsepter[nr] = (n, som_heltall(rad.get("parent_id"))[0])

    if konsepter:
        v = ("(VALUES " + ",".join(f"({nr},{q(n)},{'NULL' if f is None else f})" for nr, (n, f) in konsepter.items())
             + ") AS v(id,navn,forelder)")
        mangler = "id finnes ikke i masteren"
        # Egen DO-blokk, siden løkkevariabelen må deklareres. Avvik mot masteren
        # er sjekker, ikke en grunn til å stoppe lastingen.
        sql += (
            "DO $chk$ DECLARE r record; BEGIN\n"
            f"FOR r IN SELECT v.id FROM {v} WHERE NOT EXISTS (SELECT 1 FROM {tabell} t WHERE t.id=v.id) LOOP\n"
            f"CALL logg_avvik({q(kn)},{q(samling)},'manglende_forelder',r.id::text,"
            f"{q(mangler)},'id','id',NULL);\n"
            "END LOOP;\n"
            f"FOR r IN SELECT v.id, v.navn AS nytt, t.navn AS master FROM {v} "
            f"JOIN {tabell} t ON t.id=v.id WHERE t.navn<>v.navn LOOP\n"
            f"CALL logg_avvik({q(kn)},{q(samling)},'ugyldig_verdi',r.id::text,"
            f"'masteren har navnet ' || r.master || '; kilden har ' || r.nytt,'name','id',NULL);\n"
            "END LOOP;\n"
            f"FOR r IN SELECT v.id, v.forelder::bigint AS nytt, t.parent_id AS master FROM {v} "
            f"JOIN {tabell} t ON t.id=v.id WHERE v.forelder::bigint IS DISTINCT FROM t.parent_id LOOP\n"
            f"CALL logg_avvik({q(kn)},{q(samling)},'ugyldig_verdi',r.id::text,"
            f"'masteren har forelder ' || COALESCE(r.master::text,'ingen') || '; kilden har ' || "
            f"COALESCE(r.nytt::text,'ingen'),'parent_id','id',NULL);\n"
            "END LOOP;\nEND $chk$;\n")
    return sql


def ukjente_id_er_sql(kn, tabell, samling, felt, ider):
    """Loggfører de id-ene i koblingene som masteren ikke kjenner. Koblingen
    lastes ikke (den peker på ingenting), og avviket logges én gang per id."""
    if not ider:
        return ""
    v = "(VALUES " + ",".join(f"({nr})" for nr in sorted(ider)) + ") AS v(id)"
    return ("DO $chk$ DECLARE r record; BEGIN\n"
            f"FOR r IN SELECT v.id FROM {v} WHERE NOT EXISTS (SELECT 1 FROM {tabell} t WHERE t.id=v.id) LOOP\n"
            f"CALL logg_avvik({q(kn)},{q(samling)},'manglende_forelder',r.id::text,"
            f"'{felt} finnes ikke i masteren','{felt}','{felt}',NULL);\n"
            "END LOOP;\nEND $chk$;\n")


def generer_sql(slug: str, kommuner: dict, ut, fra_fil: Path | None = None) -> bool:
    """Skriver SQL for én kommune. Returnerer False hvis henting feilet. Med
    fra_fil leses <fra_fil>/<slug>.json i stedet for endepunktet; svaret skal ha
    samme form som searchdataall."""
    knr, knavn, fylke, base_url = kommuner[slug]
    kn = f"aktiv-kommune:{slug}"
    url = f"{base_url}/bookingfrontend/searchdataall"
    if fra_fil:
        fil = fra_fil / f"{slug}.json"
        url = fil.resolve().as_uri()
    hentet = datetime.now(timezone.utc).isoformat()
    w = ut.write

    print(f"henter {url} ...", file=sys.stderr)
    try:
        if fra_fil:
            # Ingen HTTP-forespørsel, derfor ingen status.
            status, d = None, json.loads(fil.read_text(encoding="utf-8"))
        else:
            status, d = hent_json(url)
        if not isinstance(d, dict):
            raise ValueError("svaret er ikke et JSON-objekt")
    except Exception as e:
        # Ingenting å laste, men feilen skal fortsatt kunne ses i basen.
        status = getattr(e, "code", None)
        w(f"BEGIN;\nCALL registrer_kildeuttrekk({q(kn)},{q(url)},{status or 'NULL'},NULL,{q(hentet)});\n")
        w(logg(kn, "searchdataall", "annet", None, f"Henting feilet: {type(e).__name__}: {str(e)[:200]}"))
        w("COMMIT;\n")
        print(f"  FEILET: {e}", file=sys.stderr)
        return False

    w("BEGIN;\n\n")
    # Må være første setning: alle avvik under henter uttrekk-id-en herfra.
    # payload=NULL: hele svaret lagres ikke lenger - se kommentar ved
    # kildeuttrekk i skjemaet (V1__masterdatabase__skjema.sql).
    w(f"CALL registrer_kildeuttrekk({q(kn)},{q(url)},{status or 'NULL'},NULL,{q(hentet)});\n\n")

    w(f"-- {knavn}\n")
    w(f"INSERT INTO kommune (kommunenr,navn,fylkesnavn) "
      f"VALUES ({q(knr)},{q(knavn)},{q(fylke)}) ON CONFLICT (kommunenr) DO NOTHING;\n")
    w(f"INSERT INTO fagsystem_instans (kildenokkel,type,navn,base_url) "
      f"VALUES ({q(kn)},'booking',{q('Aktiv kommune ' + knavn)},{q(base_url)}) "
      f"ON CONFLICT (kildenokkel) DO NOTHING;\n")
    # Ekte mange-til-mange: en kommune kan ha flere instanser (booking, fdv,
    # sensor, ...), én instans kan betjene flere kommuner. uniq_kommune_
    # fagsystem_type hindrer to instanser av samme type for samme kommune.
    w(f"INSERT INTO kommune_fagsystem_instans (kommune_id,fagsystem_instans_id,type) "
      f"SELECT k.id, fi.id, fi.type FROM kommune k, fagsystem_instans fi "
      f"WHERE k.kommunenr={q(knr)} AND fi.kildenokkel={q(kn)} "
      f"ON CONFLICT (kommune_id,fagsystem_instans_id) DO NOTHING;\n\n")

    # --- kodeverk: sjekk mot masterens vokabular ---
    for tabell, samling in KODEVERK:
        w(kodeverk_sql(kn, tabell, samling, d.get(samling, [])))
    w("\n")
    # id-er i koblingene som masteren må kjenne; sjekkes samlet etter at
    # koblingene er skrevet. Nøkkel: (tabell, samling, felt i kilden).
    brukte_ider = {}

    # --- bygg + adresse ---
    bydel_per_bygg = {t["b_id"]: rens(t["name"]) for t in d.get("towns", [])}
    for b in d.get("buildings", []):
        if b.get("id") is None:
            w(logg(kn, "buildings", "ugyldig_verdi", None, "posten mangler id", "id", rapost=b))
            continue
        navn = rens(b.get("name"))
        if not navn:
            w(logg(kn, "buildings", "ugyldig_verdi", b["id"], "name er tomt; erstattet med plassholder",
                   "name", rapost=b))
            navn = f"Bygg {b['id']}"

        # Mykt avvik: feltet settes til NULL, resten av raden lastes.
        gate = rens(b.get("street"))
        postnr = (b.get("zip_code") or "").strip()
        avvik = ""
        if postnr and not re.fullmatch(r"[0-9]{4}", postnr):
            avvik = logg(kn, "buildings", "ugyldig_verdi", b["id"],
                         "zip_code er ikke fire siffer: " + postnr[:60], "zip_code", rapost=b)
            postnr = None

        # Kildedata gir ikke gatenavn og husnummer separat, bare hele
        # gateadressen i ett felt ("Breimyra 68 A"). adressetekst fylles fra
        # den; gate_id/husnr/posisjon fylles av matrikkel_adresse.py.
        sql = (
            f"INSERT INTO bygning (kommune_id,navn,bydel_navn,fagsystem_instans_id,ekstern_id) "
            f"SELECT k.id,{q(navn)},{q(bydel_per_bygg.get(b['id']))},fi.id,{q(b['id'])} "
            f"FROM kommune k, fagsystem_instans fi "
            f"WHERE k.kommunenr={q(knr)} AND fi.kildenokkel={q(kn)} "
            # Aktiv kommune vinner på disse feltene (se "Autoritet" i dokumentasjonen).
            f"ON CONFLICT (fagsystem_instans_id,ekstern_id) "
            f"WHERE fagsystem_instans_id IS NOT NULL AND ekstern_id IS NOT NULL "
            f"DO UPDATE SET navn=EXCLUDED.navn, bydel_navn=EXCLUDED.bydel_navn;\n"
        )
        if gate:
            sql += (
                f"INSERT INTO adresse (bygning_id,adressetekst,postnummer,poststed,"
                f"geokoding,er_hovedadresse) "
                f"SELECT b.id,{q(gate)},{q(postnr)},{q(rens(b.get('city')))},'ukjent',TRUE "
                f"FROM bygning b JOIN fagsystem_instans fi ON fi.id=b.fagsystem_instans_id "
                f"WHERE fi.kildenokkel={q(kn)} AND b.ekstern_id={q(b['id'])} "
                # Rører ikke en adresse som allerede er geokodet eller satt manuelt.
                f"ON CONFLICT (bygning_id) WHERE er_hovedadresse "
                f"DO UPDATE SET adressetekst=EXCLUDED.adressetekst, postnummer=EXCLUDED.postnummer, "
                f"poststed=EXCLUDED.poststed WHERE adresse.geokoding IN ('ukjent','feilet');\n"
            )
        w(avvik)
        w(i_blokk(kn, "buildings", b["id"], sql, rapost=b))
    w("\n")

    # --- ressurser ---
    kjente_bygg = {b["id"] for b in d.get("buildings", [])}
    bygg_for_ressurs = {}
    for br in d.get("building_resources", []):
        if br["building_id"] in kjente_bygg:
            bygg_for_ressurs.setdefault(br["resource_id"], br["building_id"])

    for r in d.get("resources", []):
        if r.get("id") is None:
            w(logg(kn, "resources", "ugyldig_verdi", None, "posten mangler id", "id", rapost=r))
            continue
        navn = rens(r.get("name"))
        if not navn:
            w(logg(kn, "resources", "ugyldig_verdi", r["id"], "name er tomt; erstattet med plassholder",
                   "name", rapost=r))
            navn = f"Ressurs {r['id']}"
        beskr = None
        try:
            dj = json.loads(r.get("description_json") or "{}")
            beskr = rens(dj.get("no") or dj.get("nn") or dj.get("en"))
        except (ValueError, TypeError, AttributeError):
            pass
        bid = bygg_for_ressurs.get(r["id"])
        kap, kap_feil = som_heltall(r.get("capacity"))
        if kap_feil:
            w(logg(kn, "resources", "ugyldig_verdi", r["id"], "capacity " + kap_feil, "capacity", rapost=r))
        bookbar = "FALSE" if r.get("deactivate_application") else "TRUE"
        aktiv = "TRUE" if r.get("active") else "FALSE"

        bygg_sel = (f"(SELECT b.id FROM bygning b JOIN fagsystem_instans f2 ON f2.id=b.fagsystem_instans_id "
                    f"WHERE f2.kildenokkel={q(kn)} AND b.ekstern_id={q(bid)})") if bid else "NULL"
        # Én lokaletype per ressurs, på id mot masteren; NULL når den mangler eller masteren ikke kjenner den.
        lt_id, lt_feil = som_heltall(r.get("rescategory_id"))
        if lt_feil:
            w(logg(kn, "resources", "ugyldig_verdi", r["id"], "rescategory_id " + lt_feil, "rescategory_id", rapost=r))
        elif lt_id is not None:
            brukte_ider.setdefault(("lokaletype", "resources", "rescategory_id"), set()).add(lt_id)
        lt_sel = f"(SELECT id FROM lokaletype WHERE id={lt_id})" if lt_id is not None else "NULL"

        w(f"INSERT INTO ressurs (fagsystem_instans_id,ekstern_id,kommune_id,bygning_id,navn,lokaletype_id,"
          f"kapasitet,beskrivelse,aktiv,bookbar) "
          f"SELECT fi.id,{q(r['id'])},k.id,{bygg_sel},{q(navn)},{lt_sel},"
          f"{kap if kap is not None else 'NULL'},"
          f"{q(beskr)},{aktiv},{bookbar} "
          f"FROM kommune k, fagsystem_instans fi "
          f"WHERE k.kommunenr={q(knr)} AND fi.kildenokkel={q(kn)} "
          f"ON CONFLICT (fagsystem_instans_id,ekstern_id) DO UPDATE SET navn=EXCLUDED.navn, "
          # Aktiv kommune har fasiten på hvilket bygg en ressurs hører til.
          f"kapasitet=EXCLUDED.kapasitet, lokaletype_id=EXCLUDED.lokaletype_id, "
          f"bygning_id=EXCLUDED.bygning_id;\n")
    # Link to the resource in its own booking system (ressurslenke).
    w(ressurslenke_sql(kn))
    w("\n")

    # --- koblinger, med avviksloggføring for brutte referanser ---
    # searchdataall er et delvis uttrekk: koblingstabellene eksporteres
    # komplett, mens bygg- og ressurslistene er filtrert. Rader som peker på
    # noe utenfor uttrekket kan ikke lastes, og loggføres i stedet for å
    # forkastes stille.
    kjente_ressurser = {r["id"] for r in d.get("resources", [])}
    # Koblingene er helt avledet av kilden, så de bygges på nytt hver gang -
    # ellers ville koblinger fra en tidligere versjon av kilden bli liggende.
    for koblingstabell in ("ressurs_aktivitet", "ressurs_fasilitet"):
        w(f"DELETE FROM {koblingstabell} x USING ressurs r JOIN fagsystem_instans fi "
          f"ON fi.id=r.fagsystem_instans_id WHERE x.ressurs_id=r.id AND fi.kildenokkel={q(kn)};\n")

    for samling, kodetype, koblingstabell, maalkol, idfelt in [
        ("resource_activities", "aktivitet", "ressurs_aktivitet", "aktivitet_id", "activity_id"),
        ("resource_facilities", "fasilitet", "ressurs_fasilitet", "fasilitet_id", "facility_id"),
    ]:
        for rad in d.get(samling, []):
            if rad["resource_id"] not in kjente_ressurser:
                w(logg(kn, samling, "manglende_forelder", rad["resource_id"],
                       "resource_id finnes ikke i uttrekket", "resource_id", "resource_id", rapost=rad))
                continue
            nr, feil = som_heltall(rad[idfelt])
            if nr is None:
                w(logg(kn, samling, "ugyldig_verdi", rad[idfelt], f"{idfelt} " + (feil or "mangler"),
                       idfelt, idfelt, rapost=rad))
                continue
            brukte_ider.setdefault((kodetype, samling, idfelt), set()).add(nr)
            w(f"INSERT INTO {koblingstabell} (ressurs_id,{maalkol}) "
              f"SELECT r.id,t.id "
              f"FROM ressurs r JOIN fagsystem_instans fi ON fi.id=r.fagsystem_instans_id, {kodetype} t "
              f"WHERE fi.kildenokkel={q(kn)} AND r.ekstern_id={q(rad['resource_id'])} "
              f"AND t.id={nr} "
              f"ON CONFLICT DO NOTHING;\n")

    for br in d.get("building_resources", []):
        if br["building_id"] not in kjente_bygg:
            w(logg(kn, "building_resources", "manglende_forelder", br["building_id"],
                   "building_id finnes ikke i uttrekket", "building_id", "building_id", rapost=br))
        if br["resource_id"] not in kjente_ressurser:
            w(logg(kn, "building_resources", "manglende_forelder", br["resource_id"],
                   "resource_id finnes ikke i uttrekket", "resource_id", "resource_id", rapost=br))

    # Kommunen eier koblingene, men ikke vokabularet: en kobling til en id
    # masteren ikke kjenner lastes ikke, og avviket logges én gang per id.
    for (tabell, samling, felt), ider in brukte_ider.items():
        w(ukjente_id_er_sql(kn, tabell, samling, felt, ider))

    # Beholder de to siste uttrekkene per kilde, uforbeholdent.
    w(f"\nDO $$ BEGIN PERFORM rydd_kildeuttrekk({q(kn)}); END $$;\n")
    w("COMMIT;\n")
    print(f"  {len(d.get('buildings', []))} bygg, {len(d.get('resources', []))} ressurser", file=sys.stderr)
    return True


def main():
    kommuner = kommuner_fra_kommandolinje(paakrevd=True)
    parser = argparse.ArgumentParser(description="Synkroniserer fra Aktiv kommune; skriver SQL til standard-ut.",
                                     epilog="Kjente kommuner: " + ", ".join(kommuner))
    parser.add_argument("kommune", choices=(*kommuner, "alle"), metavar="kommune|alle")
    parser.add_argument("--fra-fil", type=Path, metavar="MAPPE",
                        help="les MAPPE/<kommune>.json i stedet for å hente fra nettet")
    parser.add_argument("--kommuner-fil", type=Path, metavar="FIL", required=True,
                        help="kommunene som skal synkroniseres, fra databasen (slug|kommunenr|navn|fylke "
                             "per linje, laget av kommuner_query.sql)")
    args = parser.parse_args()

    valg = list(kommuner) if args.kommune == "alle" else [args.kommune]
    if not valg:
        print("ingen kommuner å synkronisere", file=sys.stderr)
    feilet = [slug for slug in valg if not generer_sql(slug, kommuner, sys.stdout, args.fra_fil)]
    if feilet:
        print(f"\nHenting feilet for: {', '.join(feilet)} (loggført i synk_avvik)", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
