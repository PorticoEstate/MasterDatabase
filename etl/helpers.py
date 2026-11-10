"""
Hjelpefunksjoner delt av last_inn.py og synk.py: kommunetabellen, henting av
JSON, rensing av kildetekst, SQL-literaler og avviksloggføring.
"""
import argparse
import html
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

KOMMUNER = {
    "afjord": ("5058", "Åfjord", "Trøndelag"),
    "alesund": ("1508", "Ålesund", "Møre og Romsdal"),
    "alver": ("4631", "Alver", "Vestland"),
    "averoy": ("1554", "Averøy", "Møre og Romsdal"),
    "baerum": ("3201", "Bærum", "Akershus"),
    "bergen": ("4601", "Bergen", "Vestland"),
    "eigersund": ("1101", "Eigersund", "Rogaland"),
    "gamvik": ("5626", "Gamvik", "Finnmark"),
    "inderoy": ("5053", "Inderøy", "Trøndelag"),
    "kristiansand": ("4204", "Kristiansand", "Agder"),
    "kvam": ("4622", "Kvam", "Vestland"),
    "larvik": ("3909", "Larvik", "Vestfold"),
    "narvik": ("1806", "Narvik", "Nordland"),
    "nordreisa": ("5544", "Nordreisa", "Troms"),
    "oksnes": ("1868", "Øksnes", "Nordland"),
    "oygarden": ("4626", "Øygarden", "Vestland"),
    "sandnes": ("1108", "Sandnes", "Rogaland"),
    "sogndal": ("4640", "Sogndal", "Vestland"),
    "sola": ("1124", "Sola", "Rogaland"),
    "stavanger": ("1103", "Stavanger", "Rogaland"),
    "sunnfjord": ("4647", "Sunnfjord", "Vestland"),
    "time": ("1121", "Time", "Rogaland"),
}
#Kommuner som ligger i aktiviteetsanalysen men som er helt tomme og mangler endepunkt:
# "bardu": ("5520", "Bardu", "Troms"),
# "drammen": ("3301", "Drammen", "Buskerud"),
# "suldal": ("1134", "Suldal", "Rogaland"),

# A slug is the Aktiv kommune subdomain and ends up in a URL and in
# fagsystem_instans.kildenokkel, so only plain characters are accepted.
SLUG_MONSTER = re.compile(r"^[a-z0-9-]+$")


def les_kommuner(fil: Path | None) -> dict:
    """Kommunene som skal behandles, som slug -> (kommunenr, navn, fylke).

    Uten fil: den innebygde KOMMUNER (last_inn.py bruker alltid den).
    Med fil: kommunene som er registrert i databasen, én linje per kommune som
    slug|kommunenr|navn|fylke (utdata fra kommuner_query.sql; synk.py bruker
    alltid denne). En ugyldig linje hoppes over med en advarsel, så én dårlig
    rad ikke stopper hele kjøringen."""
    if fil is None:
        return KOMMUNER
    try:
        linjer = fil.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        sys.exit(f"kan ikke lese kommunelisten: {e}")
    kommuner = {}
    for nr, linje in enumerate(linjer, 1):
        if not linje.strip():
            continue
        deler = [d.strip() for d in linje.split("|")]
        if (len(deler) != 4 or not SLUG_MONSTER.match(deler[0])
                or not re.fullmatch(r"[0-9]{4}", deler[1]) or not deler[2]):
            print(f"  advarsel: {fil.name} linje {nr} ignorert: {linje!r}", file=sys.stderr)
            continue
        slug, knr, navn, fylke = deler
        kommuner[slug] = (knr, navn, fylke or None)
    return kommuner


def kommuner_fra_kommandolinje(paakrevd: bool = False, argv=None) -> dict:
    """Leser --kommuner-fil før den egentlige argumentparseren, som trenger
    listen til valgene for kommune-argumentet. Med paakrevd=True avvises et kall
    uten flagget (unntatt --help), så synk.py aldri faller tilbake på den
    innebygde listen."""
    args_liste = sys.argv[1:] if argv is None else argv
    forelopig = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    forelopig.add_argument("--kommuner-fil", type=Path)
    args, _ = forelopig.parse_known_args(args_liste)
    if paakrevd and args.kommuner_fil is None and not {"-h", "--help"} & set(args_liste):
        print("feil: --kommuner-fil er påkrevd. Lag filen med: "
              "psql -tA -F'|' -f etl/kommuner_query.sql > etl/ut/kommuner.txt", file=sys.stderr)
        sys.exit(2)
    return les_kommuner(args.kommuner_fil)


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
    først i samme transaksjon (se registrer_kildeuttrekk i V1__masterdatabase__skjema.sql).
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
    """(verdi, feilmelding). Tom verdi gir (None, None); ugyldig gir (None, melding)."""
    if v is None or v == "":
        return None, None
    try:
        n = int(v)
    except (ValueError, TypeError):
        return None, f"ikke et heltall: {str(v)[:60]}"
    if n < 0:
        return None, f"negativt tall: {n}"
    return n, None
