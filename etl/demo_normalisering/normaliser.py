#!/usr/bin/env python3
"""
DEMO: gjør en rå Aktiv kommune-instans om til det en normalisert instans ville
levere. Skal slettes (sammen med mappene med mapping og vokabular) når
instansene er normalisert - last_inn.py trenger ingen endring.

Skriptet leser searchdataall (fra nettet, eller fra en fil) og skriver samme
JSON-form tilbake, men med kodeverkene erstattet:

    resource_categories, activities, facilities  - masterens vokabular, hver
        rad med id, name og parent_id (facilities får parent_id; det har ikke
        kilden i dag)
    resources.rescategory_id                     - én lokaletype, eller null
    resource_activities, resource_facilities     - én rad per masterkonsept

Alt annet i svaret (buildings, towns, ...) beholdes uendret. Kildenavn som
ikke finnes i mapping.json, eller som er exclude-konsepter, får ingen kobling;
de skrives til standard-feil så mappingen kan utvides.

Bruk:
    python3 etl/demo_normalisering/normaliser.py bergen
    python3 etl/demo_normalisering/normaliser.py alle --ut etl/ut/normalisert
    python3 etl/demo_normalisering/normaliser.py bergen --fra-fil etl/ut/ra

    python3 etl/last_inn.py bergen --fra-fil etl/ut/normalisert > etl/ut/bergen.sql
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

HER = Path(__file__).resolve().parent
ETL = HER.parent
sys.path.insert(0, str(ETL))
from felles import KOMMUNER, hent_json, rens  # noqa: E402

# Mapping og vokabular per kodetype, i samme format for alle tre (se
# activity_mapping/AktivKommune_activity_normalisation.md): mapping.json har
# under "values" ett oppslag per normalisert kildenavn (norm_navn) med
# konseptnavnene i målfeltet, og vokabularfilen har konseptene gruppert per
# fasett, nøklet på navn, med "broader" (forelderens navn) og et fast "id".
# Id-en er den delte id-en på tvers av instanser, og skal aldri endres eller
# gjenbrukes; et nytt konsept får neste ledige tall. Alle fasetter unntatt
# "exclude" blir med i vokabularet; exclude-konsepter betyr at kildenavnet ikke
# er relevant.
#
# kodetype: (mappe, vokabularfil, målfelt i mapping.json, samling i kilden)
KODEVERK = {
    "lokaletype": ("lokaletype_mapping", "venue_types.json", "venueType", "resource_categories"),
    "aktivitet": ("activity_mapping", "activities.json", "activities", "activities"),
    "fasilitet": ("fasilitet_mapping", "facilities.json", "facilities", "facilities"),
}
MAPPING, VOKABULAR = {}, {}
for _kodetype, (_mappe, _vokabularfil, _malfelt, _) in KODEVERK.items():
    with open(HER / _mappe / "mapping.json", encoding="utf-8") as f:
        # Lokaletype er én-til-én og har ett navn som streng; de andre en liste.
        MAPPING[_kodetype] = {navn: [v[_malfelt]] if isinstance(v[_malfelt], str) else v[_malfelt]
                              for navn, v in json.load(f)["values"].items()}
    with open(HER / _mappe / _vokabularfil, encoding="utf-8") as f:
        VOKABULAR[_kodetype] = json.load(f)["facets"]
    _ider = [k["id"] for ks in VOKABULAR[_kodetype].values() for k in ks.values()]
    assert len(set(_ider)) == len(_ider), f"{_vokabularfil}: id-er som går igjen"
EKSKLUDER = {navn for v in VOKABULAR.values() for navn in v.get("exclude", {})}

# Junk uansett kodetype: adresser, stedsnavn og driftsstatus som aldri kan
# være en ekte lokaletype, aktivitet eller fasilitet.
IKKE_RELEVANT_UNIVERSELT = {
    "stengt", "fiktivt rom", "kantinebidrag",
    "kvitsoygata 3", "judaberg innbyggertorg", "mostun natursenter",
}

# Junk KUN i én kodetype-kontekst - kan være en ekte verdi i en annen. F.eks.
# er "Inkludering" ikke en stedstype, men er en fullt plausibel aktivitet
# (inkluderingstiltak er en vanlig kommunal kategori). mapping.json avgjør
# selv hva som er junk (exclude-konsepter); disse listene brukes bare som
# reserve for navn som mangler i mapping.json.
IKKE_RELEVANT_PER_TYPE = {
    "lokaletype": {"inkludering", "sosial aktivitet", "wc toalett"},
    "fasilitet": set(),
}


def er_ikke_relevant(kodetype: str, navn_normalisert: str) -> bool:
    return (navn_normalisert in IKKE_RELEVANT_UNIVERSELT
            or navn_normalisert in IKKE_RELEVANT_PER_TYPE.get(kodetype, set()))


def norm(s):
    """Normaliserer et navn for oppslag i junk-listene ovenfor: små bokstaver,
    norske bokstaver til ascii, tegnsetting bort."""
    s = rens(s) or ""
    s = s.lower().replace("ø", "o").replace("æ", "a").replace("å", "a")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def norm_navn(s):
    """Normaliserer et kildenavn for oppslag i mapping.json (alle tre
    kodetyper). Mildere enn norm(): beholder æ/ø/å og tegnsetting, og må være
    identisk med "normalisation" i mapping-filene (dobbel HTML-avkoding,
    unicode NFC, trim, sammenslåtte mellomrom, små bokstaver)."""
    return unicodedata.normalize("NFC", rens(s) or "").lower()


def oversett(kodetype: str, navn: str):
    """Kildenavn -> liste med konseptnavn i masterens kodeverk. Tom liste betyr
    ikke relevant (bevisst uten mål, f.eks. "Stengt" eller et exclude-konsept);
    None betyr ukartlagt. Lokaletype gir høyst ett navn, mens ett aktivitets-
    eller fasilitetsnavn kan gi flere ("Barnebursdag 3 - 12 år" ->
    Barnebursdag + Barn)."""
    konsepter = MAPPING[kodetype].get(norm_navn(navn))
    if konsepter is None:
        # Reserve for navn som mangler i mapping.json.
        return [] if er_ikke_relevant(kodetype, norm(navn)) else None
    return [c for c in konsepter if c not in EKSKLUDER]


def normaliser(d: dict, ukartlagt: dict) -> dict:
    """Returnerer d i normalisert form. Ukartlagte kildenavn samles i
    ukartlagt[kodetype]."""
    ut = dict(d)
    # kart[kodetype][kilde-id] = id-ene til masterkonseptene den oversettes til
    kart = {}
    for kodetype, (_, _, _, samling) in KODEVERK.items():
        konsepter = [(navn, k) for fasett, ks in VOKABULAR[kodetype].items() if fasett != "exclude"
                     for navn, k in ks.items()]
        ider = {navn: k["id"] for navn, k in konsepter}
        ut[samling] = [{"id": ider[navn], "name": navn, "parent_id": ider.get(k.get("broader")), "active": 1}
                       for navn, k in konsepter]

        kart[kodetype] = {}
        for rad in d.get(samling, []):
            navn = rens(rad.get("name"))
            if rad.get("id") is None or not navn:
                continue
            master = oversett(kodetype, navn)
            if master is None:
                ukartlagt.setdefault(kodetype, set()).add(navn)
                master = []
            kart[kodetype][rad["id"]] = [ider[n] for n in master]

    ut["resources"] = []
    for r in d.get("resources", []):
        # activity_id er en kilde-id i det gamle kodeverket og gir ikke lenger mening.
        r = {k: v for k, v in r.items() if k != "activity_id"}
        lokaletyper = kart["lokaletype"].get(r.get("rescategory_id"), [])
        r["rescategory_id"] = lokaletyper[0] if lokaletyper else None
        ut["resources"].append(r)

    for samling, kodetype, idfelt in [("resource_activities", "aktivitet", "activity_id"),
                                      ("resource_facilities", "fasilitet", "facility_id")]:
        sett = {}
        for rad in d.get(samling, []):
            for ny in kart[kodetype].get(rad[idfelt], []):
                sett[(rad["resource_id"], ny)] = {"resource_id": rad["resource_id"], idfelt: ny}
        ut[samling] = list(sett.values())
    return ut


def main():
    parser = argparse.ArgumentParser(description="DEMO: skriver en normalisert kopi av searchdataall per kommune.",
                                     epilog="Kjente kommuner: " + ", ".join(KOMMUNER))
    parser.add_argument("kommune", choices=(*KOMMUNER, "alle"), metavar="kommune|alle")
    parser.add_argument("--fra-fil", type=Path, metavar="MAPPE",
                        help="les MAPPE/<kommune>.json i stedet for å hente fra nettet")
    parser.add_argument("--ut", type=Path, default=ETL / "ut" / "normalisert", metavar="MAPPE",
                        help="skriv MAPPE/<kommune>.json (standard: etl/ut/normalisert)")
    args = parser.parse_args()

    args.ut.mkdir(parents=True, exist_ok=True)
    valg = list(KOMMUNER) if args.kommune == "alle" else [args.kommune]
    feilet = []
    for slug in valg:
        try:
            if args.fra_fil:
                d = json.loads((args.fra_fil / f"{slug}.json").read_text(encoding="utf-8"))
            else:
                url = f"https://{slug}.aktiv-kommune.no/bookingfrontend/searchdataall"
                print(f"henter {url} ...", file=sys.stderr)
                d = hent_json(url)[1]
            if not isinstance(d, dict):
                raise ValueError("svaret er ikke et JSON-objekt")
        except Exception as e:
            print(f"  FEILET: {slug}: {e}", file=sys.stderr)
            feilet.append(slug)
            continue
        ukartlagt = {}
        ut = normaliser(d, ukartlagt)
        (args.ut / f"{slug}.json").write_text(json.dumps(ut, ensure_ascii=False), encoding="utf-8")
        print(f"  {slug}: {len(ut['resources'])} ressurser, "
              f"{len(ut['resource_activities'])} aktivitets- og {len(ut['resource_facilities'])} fasilitetskoblinger",
              file=sys.stderr)
        for kodetype, navn in ukartlagt.items():
            print(f"    ukartlagt {kodetype}: {', '.join(sorted(navn))}", file=sys.stderr)
    if feilet:
        sys.exit(2)


if __name__ == "__main__":
    main()
