"""
The kommune table of the ETL: the built-in seed list, the format of the
kommune list file, and its validation. Used by jobs/build.py, jobs/sync.py and the
demo normaliser.
"""
import argparse
import re
import sys
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


# The only base URL the ETL fetches from: https://<slug>.aktiv-kommune.no. The
# backend validates the same rule before it stores a URL (AktivKommuneUrl.java);
# the ETL checks again so a bad row in the database cannot make it fetch from
# another host. Keep the two in step.
BASE_URL_MONSTER = re.compile(r"^https://([a-z0-9][a-z0-9-]*)\.aktiv-kommune\.no$")


def les_kommuner(fil: Path | None) -> dict:
    """Kommunene som skal behandles, som slug -> (kommunenr, navn, fylke, base_url).

    Uten fil: den innebygde KOMMUNER, med base_url utledet fra slug (jobs/build.py
    bruker KOMMUNER direkte; dette er bare standard for demo-normaliseringen).
    Med fil: kommunene som er registrert i databasen, én linje per kommune som
    slug|kommunenr|navn|fylke|base_url (utdata fra kommuner_query.sql; jobs/sync.py
    bruker alltid denne). En ugyldig linje hoppes over med en advarsel, så én
    dårlig rad ikke stopper hele kjøringen."""
    if fil is None:
        return {slug: (*verdi, f"https://{slug}.aktiv-kommune.no") for slug, verdi in KOMMUNER.items()}
    try:
        linjer = fil.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        sys.exit(f"kan ikke lese kommunelisten: {e}")
    kommuner = {}
    for nr, linje in enumerate(linjer, 1):
        if not linje.strip():
            continue
        deler = [d.strip() for d in linje.split("|")]
        if (len(deler) != 5 or not SLUG_MONSTER.match(deler[0])
                or not re.fullmatch(r"[0-9]{4}", deler[1]) or not deler[2]):
            print(f"  advarsel: {fil.name} linje {nr} ignorert: {linje!r}", file=sys.stderr)
            continue
        slug, knr, navn, fylke, base_url = deler
        base_url = base_url.rstrip("/")
        m = BASE_URL_MONSTER.match(base_url)
        if not m or m.group(1) != slug:
            print(f"  advarsel: {fil.name} linje {nr} ignorert: base_url {base_url!r} er ikke "
                  f"https://{slug}.aktiv-kommune.no", file=sys.stderr)
            continue
        kommuner[slug] = (knr, navn, fylke or None, base_url)
    return kommuner


def kommuner_fra_kommandolinje(paakrevd: bool = False, argv=None) -> dict:
    """Leser --kommuner-fil før den egentlige argumentparseren, som trenger
    listen til valgene for kommune-argumentet. Med paakrevd=True avvises et kall
    uten flagget (unntatt --help), så jobs/sync.py aldri faller tilbake på den
    innebygde listen."""
    args_liste = sys.argv[1:] if argv is None else argv
    forelopig = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    forelopig.add_argument("--kommuner-fil", type=Path)
    args, _ = forelopig.parse_known_args(args_liste)
    if paakrevd and args.kommuner_fil is None and not {"-h", "--help"} & set(args_liste):
        print("feil: --kommuner-fil er påkrevd. Lag filen med: "
              "psql -tA -F'|' -f etl/sql/kommuner_query.sql > etl/ut/kommuner.txt", file=sys.stderr)
        sys.exit(2)
    return les_kommuner(args.kommuner_fil)
