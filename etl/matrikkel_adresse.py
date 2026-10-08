#!/usr/bin/env python3
"""
Andrepass-geokoding: finner adresser via Matrikkelen (MatrikkelAPI) for de
adressene Kartverkets åpne Adresse-API (etl/geokod.py) ikke klarte å slå opp -
enten fordi det ikke var noe treff der (stavemåte/format), eller fordi det var
flere treff og ingen kunne velges automatisk (ofte fordi husnummer manglet
helt i kildedata).

Matrikkelen gir oss noe det åpne API-et ikke gjør: vi kjenner allerede
kommunen hver bygning tilhører (satt av last_inn.py), så søket kan gjøres
*innenfor riktig kommune* i stedet for fritekst nasjonalt - det er nettopp
det som løser begge feiltypene over. Se db/schema_kjerne_dokumentasjon.md,
avsnittet om "gate", for hvorfor denne tabellen "må fylles av matrikkelsteget".

Kjeden per adresse (alt via MatrikkelAPI, SOAP):
    KommuneService.findKommuneIdForIdent   kommunenummer -> intern KommuneId
    AdresseService.findVegerMedNavn        (KommuneId, gatenavn) -> VegId-er
    AdresseService.findAdresserForVeg      VegId -> VegadresseId-er
    StoreService.getObjects                VegadresseId-er -> Vegadresse-objekter
                                            (nummer, bokstav, representasjonspunkt)
    - filtrer lokalt på husnummer+bokstav fra kildeteksten; ett treff kreves,
      akkurat som i geokod.py.
    StoreService.getObject(vegId)          -> Veg (adressekode, adressenavn)
    StoreService.getObject(matrikkelenhetId) -> Matrikkelenhet (gnr/bnr/fnr/snr)

Skriver tre ting ved treff: gate (upsert), matrikkelinfo+bygning_matrikkelinfo
(upsert/link) og adresse (gate_id, husnr, bokstav, posisjon, geokoding=
'matrikkel' - den autoritative statusen, se schema_kjerne_dokumentasjon.md).

Bruker bare Pythons innebygde bibliotek. Leser brukernavn/passord fra
miljøvariablene MATRIKKEL_BRUKER / MATRIKKEL_PASSORD (se matrikkel/test_auth.py)
- ALDRI skriv disse verdiene til skjerm, logg eller fil.

Bruk (kjøres etter geokod.py, på det som fortsatt mangler posisjon):

    docker exec portico_masterdb psql -U postgres -d masterdb -tA -F'|' -c "
        SELECT a.id, a.adressetekst, a.postnummer, a.poststed, k.kommunenr
        FROM adresse a
        JOIN bygning b ON b.id = a.bygning_id
        JOIN kommune k ON k.id = b.kommune_id
        WHERE a.geokoding IN ('ukjent','feilet') AND a.adressetekst IS NOT NULL;
    " > etl/ut/adresser_a_matrikkelsoke.txt

    python3 etl/matrikkel_adresse.py < etl/ut/adresser_a_matrikkelsoke.txt > etl/ut/matrikkel.sql

    docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/matrikkel.sql

Prinsipp, som i geokod.py: ett eksakt treff på husnummer+bokstav brukes.
Null treff, flere treff, eller manglende husnummer i kildedata logges som
avvik og gjettes ikke på.
"""
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

BASE_URL = "https://prodtest.matrikkel.no"
NS_DOM = "http://matrikkel.statkart.no/matrikkelapi/wsapi/v1/domain"
NS_DOMKOM = "http://matrikkel.statkart.no/matrikkelapi/wsapi/v1/domain/kommune"
NS_DOMADR = "http://matrikkel.statkart.no/matrikkelapi/wsapi/v1/domain/adresse"
NS_DOMME = "http://matrikkel.statkart.no/matrikkelapi/wsapi/v1/domain/matrikkelenhet"

# EUREF89 Geografisk = EPSG:4326 (lon/lat), bekreftet mot kodelisten
# KoordinatsystemKodeId=24 - se matrikkel/ut/siste_svar.xml. Samme SRID som
# adresse.posisjon/bygning.posisjon i masterdb, så ingen omregning trengs.
MATRIKKEL_CONTEXT = """<dom:locale>no_NO</dom:locale>
<dom:brukOriginaleKoordinater>false</dom:brukOriginaleKoordinater>
<dom:koordinatsystemKodeId><dom:value>24</dom:value></dom:koordinatsystemKodeId>
<dom:systemVersion>trunk</dom:systemVersion>
<dom:klientIdentifikasjon>bergen-masterdb</dom:klientIdentifikasjon>"""


class MatrikkelFeil(Exception):
    pass


def _auth_header() -> str:
    bruker = os.environ["MATRIKKEL_BRUKER"]
    passord = os.environ["MATRIKKEL_PASSORD"]
    return "Basic " + base64.b64encode(f"{bruker}:{passord}".encode()).decode()


def _kall(service: str, body_xml: str) -> ET.Element:
    """Sender en SOAP-forespørsel og returnerer <soap:Body>'s første barn
    (selve svar-elementet), uansett navnerom. Kaster MatrikkelFeil på HTTP-feil
    eller SOAP Fault."""
    envelope = (
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
        f"<soapenv:Header/><soapenv:Body>{body_xml}</soapenv:Body></soapenv:Envelope>"
    )
    req = urllib.request.Request(
        f"{BASE_URL}/matrikkelapi/wsapi/v1/{service}WS",
        data=envelope.encode("utf-8"),
        headers={"Content-Type": "text/xml", "Authorization": _auth_header()},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            svar = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        svar = e.read().decode("utf-8", errors="replace")
    time.sleep(0.15)

    root = ET.fromstring(svar)
    kropp = next(iter(root), None)
    if kropp is None:
        raise MatrikkelFeil("Tomt SOAP-svar")
    svarelement = next(iter(kropp), None)
    if svarelement is not None and _lokalt_navn(svarelement.tag) == "Fault":
        feilstreng = _tekst(svarelement, "faultstring") or "ukjent SOAP-feil"
        raise MatrikkelFeil(feilstreng)
    return svarelement


def _lokalt_navn(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _forste(elem: ET.Element, navn: str):
    """Første etterkommer (dybde-først, inkludert elem selv) med dette lokale
    navnet - navnerom-agnostisk, siden MatrikkelAPI blander navnerom friere
    enn det er verdt å spore nøyaktig her."""
    if elem is None:
        return None
    for e in elem.iter():
        if _lokalt_navn(e.tag) == navn:
            return e
    return None

def _alle(elem: ET.Element, navn: str):
    if elem is None:
        return []
    return [e for e in elem.iter() if _lokalt_navn(e.tag) == navn]


def _tekst(elem: ET.Element, navn: str):
    e = _forste(elem, navn)
    return e.text.strip() if e is not None and e.text else None


def _id_verdi(elem: ET.Element, feltnavn: str):
    """Henter <feltnavn><value>N</value></feltnavn> -> N (int), eller None."""
    felt = _forste(elem, feltnavn)
    v = _tekst(felt, "value")
    return int(v) if v is not None else None


# ---------------------------------------------------------------------------
# Matrikkelen - ett kall per operasjon
# ---------------------------------------------------------------------------

def finn_kommune_id(kommunenummer: str) -> int:
    svar = _kall("KommuneService", f"""
        <kom:findKommuneIdForIdent xmlns:kom="http://matrikkel.statkart.no/matrikkelapi/wsapi/v1/service/kommune"
            xmlns:dom="{NS_DOM}" xmlns:domkom="{NS_DOMKOM}">
            <kom:kommuneIdent><domkom:kommunenummer>{kommunenummer}</domkom:kommunenummer></kom:kommuneIdent>
            <kom:matrikkelContext>{MATRIKKEL_CONTEXT}</kom:matrikkelContext>
        </kom:findKommuneIdForIdent>""")
    kid = _id_verdi(svar, "return")
    if kid is None:
        raise MatrikkelFeil(f"Fant ikke KommuneId for kommunenummer {kommunenummer}")
    return kid


def finn_veg_ider(matrikkel_kommune_id: int, gatenavn: str) -> list[int]:
    gatenavn_xml = _xml_escape(gatenavn)
    svar = _kall("AdresseService", f"""
        <adr:findVegerMedNavn xmlns:adr="http://matrikkel.statkart.no/matrikkelapi/wsapi/v1/service/adresse"
            xmlns:dom="{NS_DOM}">
            <adr:kommuneId><dom:value>{matrikkel_kommune_id}</dom:value></adr:kommuneId>
            <adr:adressekode>0</adr:adressekode>
            <adr:adressenavn>{gatenavn_xml}</adr:adressenavn>
            <adr:adressenavnFonetisk>false</adr:adressenavnFonetisk>
            <adr:matrikkelContext>{MATRIKKEL_CONTEXT}</adr:matrikkelContext>
        </adr:findVegerMedNavn>""")
    return [int(_tekst(item, "value")) for item in _alle(svar, "item")]


def finn_adresse_ider_for_veg(veg_id: int) -> list[int]:
    svar = _kall("AdresseService", f"""
        <adr:findAdresserForVeg xmlns:adr="http://matrikkel.statkart.no/matrikkelapi/wsapi/v1/service/adresse"
            xmlns:dom="{NS_DOM}">
            <adr:vegId><dom:value>{veg_id}</dom:value></adr:vegId>
            <adr:matrikkelContext>{MATRIKKEL_CONTEXT}</adr:matrikkelContext>
        </adr:findAdresserForVeg>""")
    return [int(_tekst(item, "value")) for item in _alle(svar, "item")]


def hent_vegadresser(vegadresse_ider: list[int]) -> list[dict]:
    """Henter fulle Vegadresse-objekter (nummer, bokstav, punkt, vegId,
    matrikkelenhetId) for en liste med VegadresseId, i ett batch-kall."""
    if not vegadresse_ider:
        return []
    items = "".join(
        f'<dom:item xsi:type="domadr:VegadresseId"><dom:value>{i}</dom:value></dom:item>'
        for i in vegadresse_ider
    )
    svar = _kall("StoreService", f"""
        <store:getObjects xmlns:store="http://matrikkel.statkart.no/matrikkelapi/wsapi/v1/service/store"
            xmlns:dom="{NS_DOM}" xmlns:domadr="{NS_DOMADR}" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            <store:ids>{items}</store:ids>
            <store:matrikkelContext>{MATRIKKEL_CONTEXT}</store:matrikkelContext>
        </store:getObjects>""")
    resultat = []
    for item in _alle(svar, "item"):
        posisjon = _forste(item, "position")
        resultat.append({
            "id": _id_verdi(item, "id"),
            "nummer": int(_tekst(item, "nummer")) if _tekst(item, "nummer") else None,
            "bokstav": (_tekst(item, "bokstav") or "").upper() or None,
            "veg_id": _id_verdi(item, "vegId"),
            "matrikkelenhet_id": _id_verdi(item, "matrikkelenhetId"),
            "lon": float(_tekst(posisjon, "x")) if posisjon is not None else None,
            "lat": float(_tekst(posisjon, "y")) if posisjon is not None else None,
        })
    return resultat


def hent_veg(veg_id: int) -> dict:
    svar = _kall("StoreService", f"""
        <store:getObject xmlns:store="http://matrikkel.statkart.no/matrikkelapi/wsapi/v1/service/store"
            xmlns:dom="{NS_DOM}" xmlns:domadr="{NS_DOMADR}" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            <store:id xsi:type="domadr:VegId"><dom:value>{veg_id}</dom:value></store:id>
            <store:matrikkelContext>{MATRIKKEL_CONTEXT}</store:matrikkelContext>
        </store:getObject>""")
    return {
        "adressekode": int(_tekst(svar, "adressekode")) if _tekst(svar, "adressekode") else None,
        "adressenavn": _tekst(svar, "adressenavn"),
    }


def hent_matrikkelenhet(matrikkelenhet_id: int) -> dict:
    svar = _kall("StoreService", f"""
        <store:getObject xmlns:store="http://matrikkel.statkart.no/matrikkelapi/wsapi/v1/service/store"
            xmlns:dom="{NS_DOM}" xmlns:domme="{NS_DOMME}" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            <store:id xsi:type="domme:MatrikkelenhetId"><dom:value>{matrikkelenhet_id}</dom:value></store:id>
            <store:matrikkelContext>{MATRIKKEL_CONTEXT}</store:matrikkelContext>
        </store:getObject>""")
    mnr = _forste(svar, "matrikkelnummer")

    def nullbar(navn):
        v = _tekst(mnr, navn)
        n = int(v) if v is not None else None
        return n if n else None  # 0 betyr "ikke relevant" - lagres som NULL

    return {
        "gardsnr": int(_tekst(mnr, "gardsnummer")),
        "bruksnr": int(_tekst(mnr, "bruksnummer")),
        "festenr": nullbar("festenummer"),
        "seksjonsnr": nullbar("seksjonsnummer"),
    }


def _xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ---------------------------------------------------------------------------
# Resten: adressetekst-parsing og SQL-generering, som i geokod.py
# ---------------------------------------------------------------------------

_HUSNR_RE = re.compile(r"^(.*?)\s*(\d+)\s*([A-Za-z]?)\s*$")


def del_opp_adressetekst(adressetekst: str) -> tuple[str, int | None, str | None]:
    """"Breimyra 68 A" -> ("Breimyra", 68, "A"). Uten husnummer i teksten
    ("Ryfylkegata") returneres (gatenavn, None, None) - se modulens docstring
    om hvorfor dette ikke kan løses videre her."""
    m = _HUSNR_RE.match(adressetekst.strip())
    if not m:
        return adressetekst.strip(), None, None
    gate, nummer, bokstav = m.group(1).strip(), int(m.group(2)), m.group(3).upper() or None
    return gate, nummer, bokstav


def q(v):
    if v is None or v == "":
        return "NULL"
    return "'" + str(v).replace("'", "''").replace("\x00", "") + "'"


def q_json(obj) -> str:
    tekst = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("\\u0000", "")
    return q(tekst) + "::jsonb"


def logg(adresse_id, detalj, rapost) -> str:
    return (f"CALL logg_avvik('matrikkel-adresse','adresse','geokoding_feilet',{q(adresse_id)},"
            f"{q(detalj)},NULL,'adresse_id',{q_json(rapost)});\n")


def i_blokk(adresse_id, sql, rapost) -> str:
    return ("DO $blk$ BEGIN\n" + sql + "EXCEPTION WHEN OTHERS THEN\n"
            f"CALL logg_avvik('matrikkel-adresse','adresse','db_feil',{q(adresse_id)},"
            f"SQLSTATE || ': ' || SQLERRM,NULL,'adresse_id',{q_json(rapost)});\nEND $blk$;\n")


def main():
    out = sys.stdout
    out.write("BEGIN;\n\n")
    out.write(f"CALL registrer_kildeuttrekk('matrikkel-adresse',{q(BASE_URL)},NULL,NULL);\n\n")

    kommune_id_cache: dict[str, int] = {}
    veg_cache: dict[int, dict] = {}
    adresser_for_veg_cache: dict[int, list[dict]] = {}

    antall_ok = antall_feilet = 0

    for rad in sys.stdin:
        rad = rad.rstrip("\n")
        if not rad:
            continue
        felt = rad.split("|", 4)
        if len(felt) != 5:
            continue
        adresse_id, adressetekst, postnummer, poststed, kommunenummer = felt
        adressetekst = adressetekst.strip()
        if not adressetekst or not kommunenummer:
            continue

        print(f"matrikkelsøker [{adresse_id}] {adressetekst!r} (kommune {kommunenummer})...",
              file=sys.stderr)
        gatenavn, nummer, bokstav = del_opp_adressetekst(adressetekst)
        spor = {"adresse_id": adresse_id, "adressetekst": adressetekst,
                "kommunenummer": kommunenummer, "gatenavn_tolket": gatenavn,
                "husnr_tolket": nummer, "bokstav_tolket": bokstav}

        if nummer is None:
            out.write(logg(adresse_id, f"mangler husnummer i kildedata for {gatenavn!r}", spor))
            antall_feilet += 1
            continue

        try:
            matrikkel_kommune_id = kommune_id_cache.get(kommunenummer)
            if matrikkel_kommune_id is None:
                matrikkel_kommune_id = finn_kommune_id(kommunenummer)
                kommune_id_cache[kommunenummer] = matrikkel_kommune_id

            veg_ider = finn_veg_ider(matrikkel_kommune_id, gatenavn)
            spor["veg_ider_funnet"] = veg_ider

            kandidater = []
            for veg_id in veg_ider:
                if veg_id not in adresser_for_veg_cache:
                    vegadresse_ider = finn_adresse_ider_for_veg(veg_id)
                    adresser_for_veg_cache[veg_id] = hent_vegadresser(vegadresse_ider)
                kandidater.extend(adresser_for_veg_cache[veg_id])

            treff = [c for c in kandidater if c["nummer"] == nummer and c["bokstav"] == bokstav]
            spor["antall_kandidater_pa_veg"] = len(kandidater)
            spor["antall_treff"] = len(treff)
        except MatrikkelFeil as e:
            spor["feil"] = str(e)
            out.write(logg(adresse_id, "MatrikkelAPI-kall feilet: " + str(e)[:200], spor))
            antall_feilet += 1
            continue

        if len(treff) != 1:
            grunn = ("ingen veg funnet" if not veg_ider else
                     "ingen treff på husnummer" if not treff else
                     f"{len(treff)} treff, ingen valgt automatisk")
            out.write(logg(adresse_id, f"matrikkel: {grunn} for {adressetekst}", spor))
            antall_feilet += 1
            continue

        v = treff[0]
        try:
            veg = veg_cache.get(v["veg_id"])
            if veg is None:
                veg = hent_veg(v["veg_id"])
                veg_cache[v["veg_id"]] = veg
            matrikkelenhet = hent_matrikkelenhet(v["matrikkelenhet_id"]) if v["matrikkelenhet_id"] else None
        except MatrikkelFeil as e:
            spor["feil"] = str(e)
            out.write(logg(adresse_id, "MatrikkelAPI-kall feilet (berikelse): " + str(e)[:200], spor))
            antall_feilet += 1
            continue

        spor["veg"] = veg
        spor["matrikkelenhet"] = matrikkelenhet
        lon, lat = v["lon"], v["lat"]

        sql = (
            f"INSERT INTO gate (kommune_id, adressekode, gatenavn) "
            f"SELECT k.id, {veg['adressekode']}, {q(veg['adressenavn'])} "
            f"FROM kommune k WHERE k.kommunenr = {q(kommunenummer)} "
            f"ON CONFLICT (kommune_id, adressekode) DO UPDATE SET gatenavn = EXCLUDED.gatenavn;\n"
        )
        if matrikkelenhet is not None:
            sql += (
                f"INSERT INTO matrikkelinfo (kommunenr, gardsnr, bruksnr, festenr, seksjonsnr) "
                f"VALUES ({q(kommunenummer)},{matrikkelenhet['gardsnr']},{matrikkelenhet['bruksnr']},"
                f"{matrikkelenhet['festenr'] or 'NULL'},{matrikkelenhet['seksjonsnr'] or 'NULL'}) "
                f"ON CONFLICT (kommunenr, gardsnr, bruksnr, COALESCE(festenr,0), COALESCE(seksjonsnr,0)) "
                f"DO NOTHING;\n"
            )
        sql += (
            f"UPDATE adresse SET "
            f"gate_id = (SELECT g.id FROM gate g JOIN kommune k ON k.id = g.kommune_id "
            f"            WHERE k.kommunenr = {q(kommunenummer)} AND g.adressekode = {veg['adressekode']}), "
            f"husnr = {nummer}, bokstav = {q(bokstav)}, "
            f"posisjon = ST_SetSRID(ST_MakePoint({lon},{lat}),4326)::geography, "
            f"geokoding = 'matrikkel' "
            f"WHERE id = {int(adresse_id)};\n"
            f"UPDATE bygning SET "
            f"matrikkel_match = 'adresse', "
            f"posisjon = COALESCE(posisjon, ST_SetSRID(ST_MakePoint({lon},{lat}),4326)::geography) "
            f"WHERE id = (SELECT bygning_id FROM adresse WHERE id = {int(adresse_id)});\n"
        )
        if matrikkelenhet is not None:
            sql += (
                f"INSERT INTO bygning_matrikkelinfo (bygning_id, matrikkelinfo_id) "
                f"SELECT a.bygning_id, m.id FROM adresse a, matrikkelinfo m "
                f"WHERE a.id = {int(adresse_id)} AND m.kommunenr = {q(kommunenummer)} "
                f"AND m.gardsnr = {matrikkelenhet['gardsnr']} AND m.bruksnr = {matrikkelenhet['bruksnr']} "
                f"AND COALESCE(m.festenr,0) = COALESCE({matrikkelenhet['festenr'] or 'NULL'},0) "
                f"AND COALESCE(m.seksjonsnr,0) = COALESCE({matrikkelenhet['seksjonsnr'] or 'NULL'},0) "
                f"ON CONFLICT DO NOTHING;\n"
            )

        out.write(i_blokk(adresse_id, sql, spor))
        antall_ok += 1

    out.write("\nDO $$ BEGIN PERFORM rydd_kildeuttrekk('matrikkel-adresse'); END $$;\n")
    out.write("COMMIT;\n")
    print(f"\nmatrikkel-geokodet: {antall_ok}, feilet: {antall_feilet}", file=sys.stderr)


if __name__ == "__main__":
    main()
