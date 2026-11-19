"""
Innlasting fra Aktiv kommune til masterdatabasen: SQL for én kommune. Delt av
jobs/build.py (bygging, én gang) og jobs/sync.py (jevnlig synk); forskjellen er
bare flagget initial_build. En rettelse her gjelder derfor begge.
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from lib.source import hent_json, rens, som_heltall
from lib.sqlgen import i_blokk, logg, q, ressurslenke_sql


# Kodeverkene i kilden: (tabell i masteren, samling i searchdataall). Masteren
# eier vokabularet og hierarkiet; instansene er normalisert mot det og bruker
# samme id-er. Ved bygging (initial_build) opprettes konsepter masteren ikke
# har; et eksisterende konsept røres aldri. Synk skriver aldri i kodeverkene.
# Kildens samlinger (id, name, parent_id) sammenlignes med masteren, og avvik
# logges. Koblingene (ressurs -> lokaletype, aktivitet, fasilitet) eies av
# kommunen og lastes i begge moduser.
KODEVERK = (
    ("lokaletype", "resource_categories"),
    ("aktivitet", "activities"),
    ("fasilitet", "facilities"),
)


def kodeverk_sql(kn, tabell, samling, rader, initial_build):
    """SQL for ett kodeverk fra kildens samling: ved initial_build opprettelse
    av konsepter som mangler i masteren, og alltid en sammenligning mot
    masterens kodeverk som loggfører avvik. Masteren eier navn og hierarki, så
    et eksisterende konsept endres aldri, og uten initial_build skrives ingenting
    i kodeverkstabellen. Avvik: en id som ikke finnes (ved initial_build: ikke
    ble opprettet), samme id med et annet navn eller en annen forelder, og
    poster som ikke kan sammenlignes (manglende eller ugyldig id, tomt navn, id
    som går igjen)."""
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
        if initial_build:
            # Opprett konsepter som mangler. Første kilde som bruker en id eller et
            # navn vinner; at en id ikke ble opprettet (navnet er tatt av en annen
            # id) fanges av sjekkene under. Forelder settes bare for konsepter som
            # ble opprettet nå, og bare når forelderen finnes i masteren.
            sql += (
                "DO $bygg$ DECLARE ny bigint[]; BEGIN\n"
                f"WITH ins AS (INSERT INTO {tabell} (id,navn) SELECT id,navn FROM {v} "
                f"ON CONFLICT DO NOTHING RETURNING id) SELECT array_agg(id) INTO ny FROM ins;\n"
                f"UPDATE {tabell} t SET parent_id=v.forelder::bigint FROM {v} "
                f"WHERE t.id=v.id AND t.id=ANY(ny) AND EXISTS (SELECT 1 FROM {tabell} p WHERE p.id=v.forelder::bigint);\n"
                "END $bygg$;\n")
            mangler = "id kunne ikke opprettes i masteren (navnet brukes av en annen id)"
        else:
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


MAKS_BYGNINGSNR = 999_999_999_999   # bygning.bygningsnr is BIGINT; real numbers have ~7-9 digits


def bygningsnr_fra_kilde(kn, knr, b):
    """(bygningsnr eller None, avviks-SQL) fra `cadastral_references` på ett bygg.

    Bare entries med cadastral_type 'BUILDING' og et positivt heltall i
    building_number teller. En entry der building_id/municipality_id ikke
    stemmer med bygget/kommunen, og en ugyldig verdi, gir avvik og brukes ikke.
    Flere forskjellige numre gir ett avvik og ingen verdi. Tallet er en
    påstand fra kilden, ikke en bekreftet matrikkelverdi: jobs/geocode.py
    bekrefter det mot Matrikkelen. Feltet er foreløpig tynt fylt i kildene."""
    refs = b.get("cadastral_references")
    if not refs:
        return None, ""
    if not isinstance(refs, list):
        return None, logg(kn, "buildings", "ugyldig_verdi", b["id"],
                          "cadastral_references er ikke en liste", "cadastral_references", rapost=b)
    avvik = ""
    numre = set()
    for ref in refs:
        if not isinstance(ref, dict) or ref.get("cadastral_type") != "BUILDING":
            continue
        raa = ref.get("building_number")
        if raa is None or raa == "":
            continue
        nr, feil = som_heltall(raa)
        if not feil and (isinstance(raa, bool) or not nr or nr > MAKS_BYGNINGSNR):
            feil = f"ikke et gyldig bygningsnummer: {str(raa)[:60]}"
        if feil:
            avvik += logg(kn, "buildings", "ugyldig_verdi", b["id"],
                          "cadastral_references.building_number " + feil, "cadastral_references", rapost=b)
            continue
        if ref.get("building_id") is not None and str(ref["building_id"]) != str(b["id"]):
            avvik += logg(kn, "buildings", "ugyldig_verdi", b["id"],
                          f"cadastral_references.building_id {str(ref['building_id'])[:20]} er ikke bygget selv; "
                          f"entry ignorert", "cadastral_references", rapost=b)
            continue
        if ref.get("municipality_id") is not None and str(ref["municipality_id"]) != str(knr):
            avvik += logg(kn, "buildings", "ugyldig_verdi", b["id"],
                          f"cadastral_references.municipality_id {str(ref['municipality_id'])[:20]} "
                          f"er ikke kommunenr {knr}; entry ignorert", "cadastral_references", rapost=b)
            continue
        numre.add(nr)
    if len(numre) > 1:
        avvik += logg(kn, "buildings", "ugyldig_verdi", b["id"],
                      "cadastral_references har flere forskjellige bygningsnumre: "
                      + ", ".join(str(n) for n in sorted(numre)) + "; ingen brukt",
                      "cadastral_references", rapost=b)
        return None, avvik
    return (next(iter(numre)) if numre else None), avvik


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


def deaktiver_forsvunne_sql(kn, tabell, samling, ider):
    """Setter aktiv=FALSE på instansens rader i `tabell` (bygning eller ressurs)
    som ikke lenger finnes i uttrekket. Raden slettes ikke; kommer den tilbake
    i et senere uttrekk, aktiveres den igjen av innlastingen. Bygg uten instans
    (bare kjent fra matrikkelen) berøres ikke. Et uttrekk helt uten poster
    tolkes som en feil i kilden, ikke som at alt er borte: da deaktiveres
    ingenting, og det loggføres."""
    if not ider:
        return logg(kn, samling, "annet", None,
                    f"uttrekket har ingen poster i {samling}; deaktivering hoppet over")
    liste = ",".join(q(i) for i in sorted(ider, key=str))
    return (f"UPDATE {tabell} x SET aktiv=FALSE FROM fagsystem_instans fi "
            f"WHERE fi.id=x.fagsystem_instans_id AND fi.kildenokkel={q(kn)} AND x.aktiv "
            f"AND x.ekstern_id <> ALL (ARRAY[{liste}]::text[]);\n")


def generer_sql(slug: str, kommune: tuple, ut, fra_fil: Path | None = None, *,
                initial_build: bool) -> bool:
    """Skriver SQL for én kommune. kommune er (kommunenr, navn, fylke, base_url).
    Returnerer False hvis henting feilet. Med fra_fil leses <fra_fil>/<slug>.json
    i stedet for endepunktet; svaret skal ha samme form som searchdataall.

    initial_build=True (jobs/build.py): oppretter kodeverkskonsepter masteren
    mangler, og registrerer instansen som aktiv. False (jobs/sync.py): skriver
    aldri i kodeverkene, og lar instansen få databasens standard for aktiv."""
    knr, knavn, fylke, base_url = kommune
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
        w(f"BEGIN;\nCALL registrer_kildeuttrekk({q(kn)},{q(url)},{status or 'NULL'},{q(hentet)});\n")
        w(logg(kn, "searchdataall", "annet", None, f"Henting feilet: {type(e).__name__}: {str(e)[:200]}"))
        w("COMMIT;\n")
        print(f"  FEILET: {e}", file=sys.stderr)
        return False

    w("BEGIN;\n\n")
    # Må være første setning: alle avvik under henter uttrekk-id-en herfra.
    # Hele svaret lagres ikke - se kommentar ved kildeuttrekk i skjemaet
    # (V1__masterdatabase__skjema.sql).
    w(f"CALL registrer_kildeuttrekk({q(kn)},{q(url)},{status or 'NULL'},{q(hentet)});\n\n")

    w(f"-- {knavn}\n")
    w(f"INSERT INTO kommune (kommunenr,navn,fylkesnavn) "
      f"VALUES ({q(knr)},{q(knavn)},{q(fylke)}) ON CONFLICT (kommunenr) DO NOTHING;\n")
    # Bare bygging setter aktiv eksplisitt; ved synk gjelder databasens standard.
    w(f"INSERT INTO fagsystem_instans (kildenokkel,type,navn,base_url{',aktiv' if initial_build else ''}) "
      f"VALUES ({q(kn)},'booking',{q('Aktiv kommune ' + knavn)},{q(base_url)}{',TRUE' if initial_build else ''}) "
      f"ON CONFLICT (kildenokkel) DO NOTHING;\n")
    # Ekte mange-til-mange: en kommune kan ha flere instanser (booking, fdv,
    # sensor, ...), én instans kan betjene flere kommuner. uniq_kommune_
    # fagsystem_type hindrer to instanser av samme type for samme kommune.
    w(f"INSERT INTO kommune_fagsystem_instans (kommune_id,fagsystem_instans_id,type) "
      f"SELECT k.id, fi.id, fi.type FROM kommune k, fagsystem_instans fi "
      f"WHERE k.kommunenr={q(knr)} AND fi.kildenokkel={q(kn)} "
      f"ON CONFLICT (kommune_id,fagsystem_instans_id) DO NOTHING;\n\n")

    # --- kodeverk: masterens vokabular (opprettes ved bygging, sjekkes alltid) ---
    for tabell, samling in KODEVERK:
        w(kodeverk_sql(kn, tabell, samling, d.get(samling, []), initial_build))
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
        # den; gate_id/husnr/posisjon fylles av jobs/geocode.py.
        # Bygningsnummer fra cadastral_references: en påstand fra kilden som
        # geocode bekrefter mot Matrikkelen (matrikkel_match røres ikke her,
        # bortsett fra det som er forklart under).
        kilde_bnr, bnr_avvik = bygningsnr_fra_kilde(kn, knr, b)
        avvik += bnr_avvik
        sql = (
            f"INSERT INTO bygning (kommune_id,navn,bydel_navn,fagsystem_instans_id,ekstern_id,bygningsnr) "
            f"SELECT k.id,{q(navn)},{q(bydel_per_bygg.get(b['id']))},fi.id,{q(b['id'])},"
            f"{kilde_bnr if kilde_bnr is not None else 'NULL'} "
            f"FROM kommune k, fagsystem_instans fi "
            f"WHERE k.kommunenr={q(knr)} AND fi.kildenokkel={q(kn)} "
            # Aktiv kommune vinner på disse feltene (se "Autoritet" i dokumentasjonen).
            # bygningsnr: Matrikkelen vinner på identitet, så kildens tall settes bare
            # når kolonnen er NULL (COALESCE beholder en eksisterende verdi). Når et
            # tall settes på et bygg som geocode har sett uten å få bygningsnr
            # ('adresse'/'ikke_funnet'), tilbakestilles matrikkel_match til
            # 'ikke_forsokt' så tallet blir verifisert av neste geocode-kjøring.
            f"ON CONFLICT (fagsystem_instans_id,ekstern_id) "
            f"WHERE fagsystem_instans_id IS NOT NULL AND ekstern_id IS NOT NULL "
            # Et bygg som er i uttrekket er aktivt (også et som var borte og er tilbake).
            f"DO UPDATE SET navn=EXCLUDED.navn, bydel_navn=EXCLUDED.bydel_navn, aktiv=TRUE;\n"
            f"bygningsnr=COALESCE(bygning.bygningsnr, EXCLUDED.bygningsnr), "
            f"matrikkel_match=CASE WHEN bygning.bygningsnr IS NULL AND EXCLUDED.bygningsnr IS NOT NULL "
            f"AND bygning.matrikkel_match IN ('adresse','ikke_funnet') "
            f"THEN 'ikke_forsokt' ELSE bygning.matrikkel_match END;\n"
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
                f"poststed=EXCLUDED.poststed WHERE adresse.geokoding = 'ukjent';\n"
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
          f"bygning_id=EXCLUDED.bygning_id, aktiv=EXCLUDED.aktiv;\n")
    # Bygg og ressurser som var i et tidligere uttrekk, men ikke i dette.
    w(deaktiver_forsvunne_sql(kn, "bygning", "buildings",
                              {b["id"] for b in d.get("buildings", []) if b.get("id") is not None}))
    w(deaktiver_forsvunne_sql(kn, "ressurs", "resources",
                              {r["id"] for r in d.get("resources", []) if r.get("id") is not None}))
    # Link to the resource in its own booking system (ressurslenke).
    w(ressurslenke_sql(kn))
    w("\n")

    # --- koblinger ---
    # Koblingstabellene i searchdataall har også rader for bygg og ressurser
    # som ikke er med i uttrekket. De hoppes over uten avvik: bygg- og
    # ressurslistene er fasiten på hva som finnes.
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

    # Kommunen eier koblingene, men ikke vokabularet: en kobling til en id
    # masteren ikke kjenner lastes ikke, og avviket logges én gang per id.
    for (tabell, samling, felt), ider in brukte_ider.items():
        w(ukjente_id_er_sql(kn, tabell, samling, felt, ider))

    # Beholder de to siste uttrekkene per kilde, uforbeholdent.
    w(f"\nDO $$ BEGIN PERFORM rydd_kildeuttrekk({q(kn)}); END $$;\n")
    w("COMMIT;\n")
    print(f"  {len(d.get('buildings', []))} bygg, {len(d.get('resources', []))} ressurser", file=sys.stderr)
    return True
