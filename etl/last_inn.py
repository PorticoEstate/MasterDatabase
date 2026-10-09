#!/usr/bin/env python3
"""
Laster data fra Aktiv kommune inn i masterdatabasen.

Bruker bare Pythons innebygde bibliotek (urllib, json, re) - ingen "pip install"
er nødvendig. Skriptet gjør ingenting mot databasen selv; det skriver SQL-tekst
til standard-ut, som du deretter sender til Postgres. Det gjør at du kan se
nøyaktig hva som skal skje før noe faktisk endres.

Bruk:
    python3 etl/last_inn.py bergen > etl/ut/bergen.sql
    docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/bergen.sql

    python3 etl/last_inn.py alle > etl/ut/alle.sql
    docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/alle.sql

Se etl/README.md for full forklaring.

Hver kjøring registrerer et kildeuttrekk (metadata: kilde, endepunkt,
tidspunkt, HTTP-status - ikke hele svaret). Ethvert avvik - ugyldige verdier,
brutte referanser, databasefeil - loggføres i synk_avvik sammen med den
konkrete posten (renset for personopplysninger) som utløste det, ikke bare en
feiltekst. Se db/schema_kjerne_dokumentasjon.md, "Innlasting og sporbarhet".

Kjent forenkling: kommune_id settes her fra hvilken Aktiv kommune-instans
ressursen kommer fra (f.eks. "bergen" -> kommunenr 4601). Det er riktig for
alle de 12 instansene vi kjenner i dag, som hver betjener nøyaktig én kommune.
Skjemaet (schema_kjerne.sql) tillater at en instans betjener flere kommuner
via kommune_fagsystem_instans; den dagen det faktisk skjer, må kommune_id i
stedet utledes fra en geokodet adresse. Se db/schema_kjerne_dokumentasjon.md.
"""
import html
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone

KOMMUNER = {
    "bergen": ("4601", "Bergen", "Vestland"),
    "stavanger": ("1103", "Stavanger", "Rogaland"),
    "baerum": ("3201", "Bærum", "Akershus"),
    "oygarden": ("4626", "Øygarden", "Vestland"),
    "narvik": ("1806", "Narvik", "Nordland"),
    "afjord": ("5058", "Åfjord", "Trøndelag"),
    "averoy": ("1554", "Averøy", "Møre og Romsdal"),
    "gamvik": ("5628", "Gamvik", "Finnmark"),
    "inderoy": ("5053", "Inderøy", "Trøndelag"),
    "nordreisa": ("5540", "Nordreisa", "Troms"),
    "oksnes": ("1868", "Øksnes", "Nordland"),
    "sogndal": ("4640", "Sogndal", "Vestland"),
}

# Normalisert kildenavn -> kode i vårt eget kodeverk (lokaletype/aktivitet/
# fasilitet, seedet i schema_kjerne.sql). Navn som ikke finnes her, lastes inn
# i kildekode uendret, men får ingen kartlegging - de dukker opp i
# v_ukartlagte_kildekoder og må kobles manuelt.
LOKALETYPE = {
    "gymsal": "GYMSAL", "idrettshall": "IDRETTSHALL", "idrettshall privateid": "IDRETTSHALL",
    "idrettsanlegg": "IDRETTSHALL", "idrettsanlegg privateid": "IDRETTSHALL",
    "svommehall": "SVOMMEANLEGG", "svommeanlegg": "SVOMMEANLEGG", "basseng": "SVOMMEANLEGG",
    "basseng symjehall": "SVOMMEANLEGG",
    "ishall": "ISHALL", "utendors isbane": "ISHALL", "kunstisbane": "ISHALL",
    "friidrettsanlegg": "FRIIDRETTSANLEGG", "friidrettsbane": "FRIIDRETTSANLEGG",
    "friidrettshall": "FRIIDRETTSANLEGG", "kastfelt grus": "FRIIDRETTSANLEGG",
    "kastfelt gress": "FRIIDRETTSANLEGG", "sprintstripe": "FRIIDRETTSANLEGG",
    "kunstgressbane": "FOTBALLBANE", "kunstgrasbane": "FOTBALLBANE",
    "gressbane": "FOTBALLBANE", "grasbane": "FOTBALLBANE", "grusbane": "FOTBALLBANE",
    "ballbinger": "BALLBANE", "sandvolleyballbane": "BALLBANE", "bordtennis": "BALLBANE",
    "tennisbane": "TENNISANLEGG", "tennishall": "TENNISANLEGG",
    "styrkerom": "STYRKEROM", "vektlofterlokale": "STYRKEROM",
    "styrkeloftlokale": "STYRKEROM", "apparatsal": "STYRKEROM", "oppvarmingsrom": "STYRKEROM",
    "kampsportrom": "KAMPSPORTROM", "kampsportmatte": "KAMPSPORTROM",
    "klatrevegg": "KLATREANLEGG", "turnomrade": "TURNANLEGG",
    "skateanlegg": "SKATEANLEGG", "skatepark": "SKATEANLEGG",
    "skytebane skytehall": "SKYTEBANE", "standplass": "SKYTEBANE",
    "sjosportsanlegg": "SJOSPORTANLEGG", "garderobe": "GARDEROBE",

    "konsertsal": "KONSERTSAL", "kultursal": "KONSERTSAL",
    "scene": "SCENE", "utendorsscene": "UTESCENE",
    "auditorium": "AUDITORIUM", "foredragssal": "AUDITORIUM",
    "ovingsrom": "OVINGSROM", "ovingslokale": "OVINGSROM", "musikkrom": "OVINGSROM",
    "musikk og danserom": "OVINGSROM",
    "dansesal": "DANSESAL", "lydstudio": "LYDSTUDIO",
    "utstillingslokale": "UTSTILLINGSLOKALE", "ateliet": "UTSTILLINGSLOKALE",
    "bibliotek": "BIBLIOTEK", "foaje": "FOAJE",

    "klasserom": "KLASSEROM", "lite undervisningsrom": "KLASSEROM",
    "stort undervisningsrom": "KLASSEROM", "kursrom": "KLASSEROM",
    "grupperom": "GRUPPEROM", "prosjektrom": "GRUPPEROM",
    "moterom": "MOTEROM", "motelokale": "MOTEROM", "konferanserom": "MOTEROM",
    "samhandlingslab": "MOTEROM", "datarom": "DATAROM", "aula": "AULA",

    "sloydsal": "SLOYDSAL", "kunst og designverksted": "KUNSTVERKSTED",
    "kunst og handverk": "KUNSTVERKSTED", "kreativt verksted": "KUNSTVERKSTED",
    "systue": "SYSTUE", "multimediaverksted": "MEDIEVERKSTED",
    "streaming": "MEDIEVERKSTED", "frisorsalong": "FRISORSALONG",

    "selskapslokale": "SELSKAPSLOKALE", "selskapslokale storsal": "SELSKAPSLOKALE",
    "forsamlingslokale": "FORSAMLINGSLOKALE",
    "forsamlingslokale privateid": "FORSAMLINGSLOKALE",
    "seremonirom": "SEREMONIROM", "sermonirom": "SEREMONIROM",
    "bursdagslokale": "BURSDAGSLOKALE", "barnebursdag": "BURSDAGSLOKALE",
    "arrangementsarena": "ARRANGEMENTSARENA", "arrangementslokale": "ARRANGEMENTSARENA",
    "torgplass": "TORGPLASS", "moteplass": "TORGPLASS",

    "kjokken": "KJOKKEN", "kantine": "KANTINE",
    "kantine kunnskapshjornet": "KANTINE", "kantine kunnskapshjorne": "KANTINE",
    "kafe": "KAFE", "kiosk minkjokken": "KAFE", "sondagskafe": "KAFE",
    "bevertning": "KAFE",

    "allaktivitetshus": "ALLAKTIVITETSHUS", "aktivitetshus": "ALLAKTIVITETSHUS",
    "aktivitetsrom": "AKTIVITETSROM", "aktivitetssal": "AKTIVITETSROM",
    "flerbruksrom": "AKTIVITETSROM", "fellesrom": "AKTIVITETSROM",
    "ungdomslokale": "UNGDOMSLOKALE", "dagsenter": "DAGSENTER", "miljostue": "DAGSENTER",

    "friluftsomrade": "FRILUFTSOMRAADE", "utendorsomrade": "UTEOMRAADE",
    "uterom uteomrade": "UTEOMRAADE", "turveier": "TURVEI",
    "gapahuk": "GAPAHUK", "balpanne": "GAPAHUK",

    "overnatting": "OVERNATTINGSROM", "beboerrom": "BEBOERROM",
    "ovingsleilighet": "OVINGSLEILIGHET",

    "kontor": "KONTOR", "arbeidsplasser": "KONTOR", "butikklokale": "BUTIKKLOKALE",
    "frilager": "LAGER", "lokale": "GENERELT_LOKALE", "ovrige lokalar": "GENERELT_LOKALE",
    "anlegg": "GENERELT_LOKALE",

    "sykler": "SYKKEL", "el sykler": "SYKKEL", "kano kajakk": "KANO_KAJAKK",
    "kano": "KANO_KAJAKK", "kajakk": "KANO_KAJAKK", "fiskestengar": "FISKEUTSTYR",
    "redningsvestar": "REDNINGSVEST", "lydanlegg": "LYDANLEGG", "utstyr": "ANNET_UTSTYR",
}

# Junk uansett kodetype: adresser, stedsnavn og driftsstatus som aldri kan
# være en ekte lokaletype, aktivitet eller fasilitet.
IKKE_RELEVANT_UNIVERSELT = {
    "stengt", "fiktivt rom", "kantinebidrag",
    "kvitsoygata 3", "judaberg innbyggertorg", "mostun natursenter",
}

# Junk KUN i én kodetype-kontekst - kan være en ekte verdi i en annen. F.eks.
# er "Inkludering" ikke en stedstype, men er en fullt plausibel aktivitet
# (inkluderingstiltak er en vanlig kommunal kategori). Tidligere lå alt i én
# delt mengde, som feilaktig avviste "Stengt" og "Inkludering" som AKTIVITET
# med forklaringen "Ikke en lokaletype" - bekreftet mot ekte data fra
# Bergen/Stavanger/Bærum, der begge faktisk finnes i activities-listen.
IKKE_RELEVANT_PER_TYPE = {
    "lokaletype": {"inkludering", "sosial aktivitet", "wc toalett"},
    "aktivitet": set(),
    "fasilitet": set(),
}


def er_ikke_relevant(kodetype: str, navn_normalisert: str) -> bool:
    return (navn_normalisert in IKKE_RELEVANT_UNIVERSELT
            or navn_normalisert in IKKE_RELEVANT_PER_TYPE.get(kodetype, set()))

FASILITET = {
    "garderobe": "GARDEROBE", "dusj": "DUSJ", "toalett": "TOALETT", "wc": "TOALETT",
    "hc toalett": "HC_TOALETT", "teleslynge": "TELESLYNGE", "heis": "HEIS",
    "projektor": "PROSJEKTOR", "prosjektor": "PROSJEKTOR", "lydanlegg": "LYDANLEGG",
    "musikkanlegg m blatann": "LYDANLEGG", "mikrofon": "MIKROFON",
    "flygel": "FLYGEL", "piano": "FLYGEL", "parkettgulv": "PARKETTGULV",
    "tribune": "TRIBUNE", "kiosk": "KIOSK", "kjokken": "KJOKKEN",
    "parkering": "PARKERING", "balpanne": "BAALPLASS", "whiteboard": "WHITEBOARD",
    "flomlys": "FLOMLYS", "wifi": "WIFI",
}

AKTIVITET = {
    "fotball": "FOTBALL", "handball": "HANDBALL", "basketball": "BASKETBALL",
    "volleyball": "VOLLEYBALL", "turn": "TURN", "kampsport": "KAMPSPORT",
    "svomming": "SVOMMING", "friidrett": "FRIIDRETT", "klatring": "KLATRING",
    "tennis": "TENNIS", "skyting": "SKYTING", "dans": "DANS", "speider": "SPEIDER",
    "sykling": "SYKLING", "idrett": "IDRETT", "kultur": "KULTUR",
    "privat arrangement": "PRIVAT", "kor og sang": "KOR", "teater og revy": "TEATER",
    "kunst handtverk media": "KUNST_HANDVERK", "kunst handverk og media": "KUNST_HANDVERK",
}


def er_persondatafelt(felt: str) -> bool:
    """Felt som kan inneholde navngitte personer (tilsynsperson, kontaktinfo-
    fritekst) eller en kopi av dem (json_representation), og som derfor ikke
    tas med i en post som lagres som rapost på et avvik. "organizations"
    (privatpersoner som søkere) brukes aldri i det hele tatt av dette
    skriptet. Se "Personvern" i db/schema_kjerne_dokumentasjon.md."""
    return felt.startswith("tilsyn") or felt in ("contact_info", "json_representation",
                                                "organizations_ids")


def rens_post(d: dict) -> dict:
    """Fjerner persondatafelt fra én enkelt post før den limes inn som rapost
    på et avvik - se er_persondatafelt."""
    return {k: v for k, v in d.items() if not er_persondatafelt(k)}


def hent_json(url: str) -> tuple[int, dict]:
    """Henter JSON fra url med Pythons innebygde urllib. Krever at Capgeminis
    CA-sertifikat er installert i systemets tillitslager (se etl/README.md).
    Prøver to ganger: enkelte instanser (Stavanger) svarer av og til tregere
    enn tidsavbruddet. Returnerer (http_status, innhold)."""
    for forsok in (1, 2):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except (TimeoutError, urllib.error.URLError):
            if forsok == 2:
                raise


def rens(s):
    """Dobbel HTML-avkoding; kilden er escapet en gang for mye
    (f.eks. 'Rom 19 &amp;#40;219&amp;#41;' skal bli 'Rom 19 (219)')."""
    if s is None:
        return None
    s = html.unescape(html.unescape(str(s)))
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def norm(s):
    """Normaliserer et navn for oppslag i kartleggingstabellene ovenfor:
    små bokstaver, norske bokstaver til ascii, tegnsetting bort."""
    s = rens(s) or ""
    s = s.lower().replace("ø", "o").replace("æ", "a").replace("å", "a")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def q(v):
    """Gjør en Python-verdi til en trygg SQL-literal. NULL for tomme verdier,
    og escaper enkeltfnutter slik at f.eks. navn med apostrof ikke knekker SQL-en."""
    if v is None or v == "":
        return "NULL"
    return "'" + str(v).replace("'", "''").replace("\x00", "") + "'"


def q_json(obj) -> str:
    """JSON-literal. jsonb avviser \\u0000, så den escapen fjernes."""
    tekst = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("\\u0000", "")
    return q(tekst) + "::jsonb"


def logg(kn, samling, avvikstype, ekstern_id, detalj, felt=None, nokkelfelt="id", rapost=None) -> str:
    """Setning som loggfører et avvik mot kildeuttrekket som er registrert
    først i samme transaksjon (se registrer_kildeuttrekk i schema_kjerne.sql).
    rapost er posten som utløste avviket - lagres direkte på avviket (renset
    for personopplysninger), ikke i et delt uttrekk som må graves ut igjen."""
    rapost_sql = q_json(rens_post(rapost)) if rapost is not None else "NULL"
    return (f"CALL logg_avvik({q(kn)},{q(samling)},{q(avvikstype)},{q(ekstern_id)},"
            f"{q(detalj)},{q(felt)},{q(nokkelfelt)},{rapost_sql});\n")


def i_blokk(kn, samling, ekstern_id, sql, rapost=None) -> str:
    """Pakker setningene for én post i en DO-blokk. Feiler noe i databasen
    (f.eks. et CHECK-brudd vi ikke har forutsett), rulles bare denne posten
    tilbake og feilen loggføres som db_feil - resten av lasten fortsetter i
    stedet for at hele transaksjonen stopper."""
    rapost_sql = q_json(rens_post(rapost)) if rapost is not None else "NULL"
    return ("DO $blk$ BEGIN\n" + sql + "EXCEPTION WHEN OTHERS THEN\n"
            f"CALL logg_avvik({q(kn)},{q(samling)},'db_feil',{q(ekstern_id)},"
            f"SQLSTATE || ': ' || SQLERRM,NULL,'id',{rapost_sql});\nEND $blk$;\n")


def som_heltall(v):
    """(verdi, feilmelding). Tom/0 gir (None, None); ugyldig gir (None, melding)."""
    if v in (None, "", 0):
        return None, None
    try:
        n = int(v)
    except (ValueError, TypeError):
        return None, f"ikke et heltall: {str(v)[:60]}"
    if n < 0:
        return None, f"negativt tall: {n}"
    return n, None


def generer_sql(slug: str, ut) -> bool:
    """Skriver SQL for én kommune. Returnerer False hvis henting feilet."""
    knr, knavn, fylke = KOMMUNER[slug]
    kn = f"aktiv-kommune:{slug}"
    url = f"https://{slug}.aktiv-kommune.no/bookingfrontend/searchdataall"
    hentet = datetime.now(timezone.utc).isoformat()
    w = ut.write

    print(f"henter {url} ...", file=sys.stderr)
    try:
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
    # kildeuttrekk i schema_kjerne.sql.
    w(f"CALL registrer_kildeuttrekk({q(kn)},{q(url)},{status},NULL,{q(hentet)});\n\n")

    w(f"-- {knavn}\n")
    w(f"INSERT INTO kommune (kommunenr,navn,fylkesnavn) "
      f"VALUES ({q(knr)},{q(knavn)},{q(fylke)}) ON CONFLICT (kommunenr) DO NOTHING;\n")
    w(f"INSERT INTO fagsystem_instans (kildenokkel,type,navn,base_url) "
      f"VALUES ({q(kn)},'booking',{q('Aktiv kommune ' + knavn)},{q('https://' + slug + '.aktiv-kommune.no')}) "
      f"ON CONFLICT (kildenokkel) DO NOTHING;\n")
    # Ekte mange-til-mange: en kommune kan ha flere instanser (booking, fdv,
    # sensor, ...), én instans kan betjene flere kommuner. uniq_kommune_
    # fagsystem_type hindrer to instanser av samme type for samme kommune.
    w(f"INSERT INTO kommune_fagsystem_instans (kommune_id,fagsystem_instans_id,type) "
      f"SELECT k.id, fi.id, fi.type FROM kommune k, fagsystem_instans fi "
      f"WHERE k.kommunenr={q(knr)} AND fi.kildenokkel={q(kn)} "
      f"ON CONFLICT (kommune_id,fagsystem_instans_id) DO NOTHING;\n\n")

    # --- kildekoder + automatisk forslag til kartlegging ---
    for kodetype, samling, tabell in [
        ("lokaletype", "resource_categories", LOKALETYPE),
        ("aktivitet", "activities", AKTIVITET),
        ("fasilitet", "facilities", FASILITET),
    ]:
        for rad in d.get(samling, []):
            if rad.get("id") is None:
                w(logg(kn, samling, "ugyldig_verdi", None, "posten mangler id", "id", rapost=rad))
                continue
            navn = rens(rad.get("name"))
            if not navn:
                continue
            w(f"INSERT INTO kildekode (fagsystem_instans_id,kodetype,kode,navn) "
              f"SELECT id,{q(kodetype)},{q(rad['id'])},{q(navn)} "
              f"FROM fagsystem_instans WHERE kildenokkel={q(kn)} "
              f"ON CONFLICT (fagsystem_instans_id,kodetype,kode) DO UPDATE SET navn=EXCLUDED.navn, sist_sett=now();\n")
            n = norm(navn)
            if er_ikke_relevant(kodetype, n):
                w(f"INSERT INTO kildekode_mapping (kildekode_id,status,merknad,kartlagt_av) "
                  f"SELECT kk.id,'ikke_relevant',{q(f'Ikke en gyldig {kodetype}')},'etl' "
                  f"FROM kildekode kk JOIN fagsystem_instans fi ON fi.id=kk.fagsystem_instans_id "
                  f"WHERE fi.kildenokkel={q(kn)} AND kk.kodetype={q(kodetype)} AND kk.kode={q(rad['id'])} "
                  f"ON CONFLICT (kildekode_id) DO NOTHING;\n")
            elif n in tabell:
                maalkol = {"lokaletype": "lokaletype_id", "aktivitet": "aktivitet_id",
                           "fasilitet": "fasilitet_id"}[kodetype]
                w(f"INSERT INTO kildekode_mapping (kildekode_id,{maalkol},status,kartlagt_av) "
                  f"SELECT kk.id,t.id,'godkjent','etl' "
                  f"FROM kildekode kk JOIN fagsystem_instans fi ON fi.id=kk.fagsystem_instans_id, {kodetype} t "
                  f"WHERE fi.kildenokkel={q(kn)} AND kk.kodetype={q(kodetype)} "
                  f"AND kk.kode={q(rad['id'])} AND t.kode={q(tabell[n])} "
                  f"ON CONFLICT (kildekode_id) DO NOTHING;\n")
    w("\n")

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
        # den; gate_id/husnr/posisjon fylles av geokod.py/matrikkel_adresse.py.
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
        bookbar = "FALSE" if r.get("deactivate_application") else "TRUE"
        aktiv = "TRUE" if r.get("active") else "FALSE"

        bygg_sel = (f"(SELECT b.id FROM bygning b JOIN fagsystem_instans f2 ON f2.id=b.fagsystem_instans_id "
                    f"WHERE f2.kildenokkel={q(kn)} AND b.ekstern_id={q(bid)})") if bid else "NULL"
        lt_sel = (f"(SELECT m.lokaletype_id FROM kildekode kk "
                  f"JOIN fagsystem_instans f3 ON f3.id=kk.fagsystem_instans_id "
                  f"JOIN kildekode_mapping m ON m.kildekode_id=kk.id AND m.status='godkjent' "
                  f"WHERE f3.kildenokkel={q(kn)} AND kk.kodetype='lokaletype' "
                  f"AND kk.kode={q(r.get('rescategory_id'))})")

        w(f"INSERT INTO ressurs (fagsystem_instans_id,ekstern_id,kommune_id,bygning_id,navn,lokaletype_id,"
          f"beskrivelse,aktiv,bookbar) "
          f"SELECT fi.id,{q(r['id'])},k.id,{bygg_sel},{q(navn)},{lt_sel},"
          f"{q(beskr)},{aktiv},{bookbar} "
          f"FROM kommune k, fagsystem_instans fi "
          f"WHERE k.kommunenr={q(knr)} AND fi.kildenokkel={q(kn)} "
          f"ON CONFLICT (fagsystem_instans_id,ekstern_id) DO UPDATE SET navn=EXCLUDED.navn;\n")
    w("\n")

    # --- koblinger, med avviksloggføring for brutte referanser ---
    # searchdataall er et delvis uttrekk: koblingstabellene eksporteres
    # komplett, mens bygg- og ressurslistene er filtrert. Rader som peker på
    # noe utenfor uttrekket kan ikke lastes, og loggføres i stedet for å
    # forkastes stille.
    kjente_ressurser = {r["id"] for r in d.get("resources", [])}
    for samling, kodetype, koblingstabell, maalkol, idfelt in [
        ("resource_activities", "aktivitet", "ressurs_aktivitet", "aktivitet_id", "activity_id"),
        ("resource_facilities", "fasilitet", "ressurs_fasilitet", "fasilitet_id", "facility_id"),
    ]:
        for rad in d.get(samling, []):
            if rad["resource_id"] not in kjente_ressurser:
                w(logg(kn, samling, "manglende_forelder", rad["resource_id"],
                       "resource_id finnes ikke i uttrekket", "resource_id", "resource_id", rapost=rad))
                continue
            w(f"INSERT INTO {koblingstabell} (ressurs_id,{maalkol}) "
              f"SELECT r.id,m.{maalkol} "
              f"FROM ressurs r JOIN fagsystem_instans fi ON fi.id=r.fagsystem_instans_id "
              f"JOIN kildekode kk ON kk.fagsystem_instans_id=fi.id AND kk.kodetype={q(kodetype)} "
              f"AND kk.kode={q(rad[idfelt])} "
              f"JOIN kildekode_mapping m ON m.kildekode_id=kk.id "
              f"AND m.status='godkjent' AND m.{maalkol} IS NOT NULL "
              f"WHERE fi.kildenokkel={q(kn)} AND r.ekstern_id={q(rad['resource_id'])} "
              f"ON CONFLICT DO NOTHING;\n")

    for br in d.get("building_resources", []):
        if br["building_id"] not in kjente_bygg:
            w(logg(kn, "building_resources", "manglende_forelder", br["building_id"],
                   "building_id finnes ikke i uttrekket", "building_id", "building_id", rapost=br))
        if br["resource_id"] not in kjente_ressurser:
            w(logg(kn, "building_resources", "manglende_forelder", br["resource_id"],
                   "resource_id finnes ikke i uttrekket", "resource_id", "resource_id", rapost=br))

    # Beholder de to siste uttrekkene per kilde, uforbeholdent.
    w(f"\nDO $$ BEGIN PERFORM rydd_kildeuttrekk({q(kn)}); END $$;\n")
    w("COMMIT;\n")
    print(f"  {len(d.get('buildings', []))} bygg, {len(d.get('resources', []))} ressurser", file=sys.stderr)
    return True


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in (*KOMMUNER, "alle"):
        navn = ", ".join(KOMMUNER)
        print(f"Bruk: python3 {sys.argv[0]} <kommune|alle>\n\nKjente kommuner: {navn}", file=sys.stderr)
        sys.exit(1)

    valg = list(KOMMUNER) if sys.argv[1] == "alle" else [sys.argv[1]]
    feilet = [slug for slug in valg if not generer_sql(slug, sys.stdout)]
    if feilet:
        print(f"\nHenting feilet for: {', '.join(feilet)} (loggført i synk_avvik)", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
