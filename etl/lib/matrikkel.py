"""
Client for MatrikkelAPI (SOAP): authentication, the generic call, and one
function per service call used by the ETL. Shared by jobs/geocode.py and
jobs/gater.py. The environment (test or prod) is chosen with MATRIKKEL_MILJO;
the credentials are read from MATRIKKEL_BRUKER / MATRIKKEL_PASSORD and are
never printed.
"""
import base64
import http.client
import os
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

# Environment is chosen with MATRIKKEL_MILJO; the default is the test environment.
MILJOER = {"test": "https://prodtest.matrikkel.no", "prod": "https://matrikkel.no"}
MILJO = os.environ.get("MATRIKKEL_MILJO", "test")
if MILJO not in MILJOER:
    sys.exit(f"Ugyldig MATRIKKEL_MILJO '{MILJO}'; bruk 'test' eller 'prod'.")
BASE_URL = MILJOER[MILJO]
NS_DOM = "http://matrikkel.statkart.no/matrikkelapi/wsapi/v1/domain"
NS_DOMKOM = "http://matrikkel.statkart.no/matrikkelapi/wsapi/v1/domain/kommune"
NS_DOMADR = "http://matrikkel.statkart.no/matrikkelapi/wsapi/v1/domain/adresse"
NS_DOMME = "http://matrikkel.statkart.no/matrikkelapi/wsapi/v1/domain/matrikkelenhet"
NS_DOMBYG = "http://matrikkel.statkart.no/matrikkelapi/wsapi/v1/domain/bygning"

# EUREF89 Geografisk = EPSG:4326 (lon/lat), bekreftet mot kodelisten
# KoordinatsystemKodeId=24 - se etl/ut/siste_svar.xml. Samme SRID som
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
    except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
        # Tilkoblingsfeil (timeout, reset, avbrutt lesing, DNS) - ikke et
        # SOAP-svar å tolke. Skal logges som avvik for nettopp denne raden,
        # ikke stoppe hele kjøringen - se "en enkelt dårlig post stopper
        # aldri hele lasten". OSError dekker TimeoutError/ConnectionResetError
        # som kastes under resp.read() (URLError wrapper bare feil under connect).
        raise MatrikkelFeil(f"Tilkoblingsfeil mot {service}: {e}") from e
    time.sleep(0.15)

    try:
        root = ET.fromstring(svar)
    except ET.ParseError as e:
        raise MatrikkelFeil(f"Ugyldig XML fra {service}: {svar[:100]!r}") from e
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
    """Direkte barn (ikke rekursivt, i motsetning til _forste) med dette
    lokale navnet. Må være direkte barn: hvert MatrikkelBubbleObject har sin
    egen <metadata><item>feltnavn</item>...</metadata> - et rekursivt søk ville
    telt disse feltnavn-radene som om de var elementer i listen vi faktisk
    leter i (dette var årsaken til urealistisk høye antall_etasjer-tall)."""
    if elem is None:
        return []
    return [e for e in elem if _lokalt_navn(e.tag) == navn]


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
    return [int(_tekst(item, "value")) for item in _alle(_forste(svar, "return"), "item")]


def finn_veg_ider_for_kommune(matrikkel_kommune_id: int) -> list[int]:
    """Alle veger i kommunen (brukes av jobs/gater.py)."""
    svar = _kall("AdresseService", f"""
        <adr:findVegerForKommune xmlns:adr="http://matrikkel.statkart.no/matrikkelapi/wsapi/v1/service/adresse"
            xmlns:dom="{NS_DOM}">
            <adr:kommuneId><dom:value>{matrikkel_kommune_id}</dom:value></adr:kommuneId>
            <adr:matrikkelContext>{MATRIKKEL_CONTEXT}</adr:matrikkelContext>
        </adr:findVegerForKommune>""")
    return [int(_tekst(item, "value")) for item in _alle(_forste(svar, "return"), "item")]


def hent_veger(veg_ider: list[int], batch: int = 500) -> list[dict]:
    """Henter adressekode og adressenavn for mange veger, `batch` om gangen."""
    resultat = []
    for start in range(0, len(veg_ider), batch):
        items = "".join(
            f'<dom:item xsi:type="domadr:VegId"><dom:value>{i}</dom:value></dom:item>'
            for i in veg_ider[start:start + batch]
        )
        svar = _kall("StoreService", f"""
            <store:getObjects xmlns:store="http://matrikkel.statkart.no/matrikkelapi/wsapi/v1/service/store"
                xmlns:dom="{NS_DOM}" xmlns:domadr="{NS_DOMADR}" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
                <store:ids>{items}</store:ids>
                <store:matrikkelContext>{MATRIKKEL_CONTEXT}</store:matrikkelContext>
            </store:getObjects>""")
        for item in _alle(_forste(svar, "return"), "item"):
            kode = _tekst(item, "adressekode")
            resultat.append({
                "adressekode": int(kode) if kode else None,
                "adressenavn": _tekst(item, "adressenavn"),
            })
    return resultat


def finn_vegadresse_direkte(matrikkel_kommune_id: int, adressekode: int,
                            nummer: int, bokstav: str | None) -> int | None:
    """Rask vei når adressekoden allerede er kjent (fra en tidligere kjøring,
    lagret i gate.adressekode): ett kall i stedet for navnesøk+kandidatliste."""
    svar = _kall("AdresseService", f"""
        <adr:findVegadresse xmlns:adr="http://matrikkel.statkart.no/matrikkelapi/wsapi/v1/service/adresse"
            xmlns:dom="{NS_DOM}">
            <adr:kommuneId><dom:value>{matrikkel_kommune_id}</dom:value></adr:kommuneId>
            <adr:adressekode>{adressekode}</adr:adressekode>
            <adr:nummer>{nummer}</adr:nummer>
            <adr:bokstav>{bokstav or ''}</adr:bokstav>
            <adr:matrikkelContext>{MATRIKKEL_CONTEXT}</adr:matrikkelContext>
        </adr:findVegadresse>""")
    return _id_verdi(svar, "return")


def finn_adresse_ider_for_veg(veg_id: int) -> list[int]:
    svar = _kall("AdresseService", f"""
        <adr:findAdresserForVeg xmlns:adr="http://matrikkel.statkart.no/matrikkelapi/wsapi/v1/service/adresse"
            xmlns:dom="{NS_DOM}">
            <adr:vegId><dom:value>{veg_id}</dom:value></adr:vegId>
            <adr:matrikkelContext>{MATRIKKEL_CONTEXT}</adr:matrikkelContext>
        </adr:findAdresserForVeg>""")
    return [int(_tekst(item, "value")) for item in _alle(_forste(svar, "return"), "item")]


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
    for item in _alle(_forste(svar, "return"), "item"):
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


def finn_bygg_ider_for_adresse(vegadresse_id: int) -> list[int]:
    svar = _kall("BygningService", f"""
        <byg:findByggForAdresse xmlns:byg="http://matrikkel.statkart.no/matrikkelapi/wsapi/v1/service/bygning"
            xmlns:dom="{NS_DOM}" xmlns:domadr="{NS_DOMADR}" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            <byg:adresseId xsi:type="domadr:VegadresseId"><dom:value>{vegadresse_id}</dom:value></byg:adresseId>
            <byg:matrikkelContext>{MATRIKKEL_CONTEXT}</byg:matrikkelContext>
        </byg:findByggForAdresse>""")
    return [int(_tekst(item, "value")) for item in _alle(_forste(svar, "return"), "item")]


def hent_bygning(bygg_id: int) -> dict:
    """Henter bygningsnummer + de få andre faktafeltene vi lagrer
    (bygningstype som rå kode - se kommentar ved bruk - bruksareal og antall
    etasjer). antall_etasjer telles fra etasjelisten (én rad per etasjeplan i
    Matrikkelen), ikke et eget enkelttall - se db/schema_kjerne_dokumentasjon.md."""
    svar = _kall("StoreService", f"""
        <store:getObject xmlns:store="http://matrikkel.statkart.no/matrikkelapi/wsapi/v1/service/store"
            xmlns:dom="{NS_DOM}" xmlns:dombyg="{NS_DOMBYG}" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            <store:id xsi:type="dombyg:BygningId"><dom:value>{bygg_id}</dom:value></store:id>
            <store:matrikkelContext>{MATRIKKEL_CONTEXT}</store:matrikkelContext>
        </store:getObject>""")
    rp = _forste(svar, "representasjonspunkt")
    posisjon = _forste(rp, "position") if rp is not None else None
    etasjedata = _forste(svar, "etasjedata")
    etasjer_elem = _forste(svar, "etasjer")
    antall_etasjer = len(_alle(etasjer_elem, "item")) if etasjer_elem is not None else 0
    bra = _tekst(etasjedata, "bruksarealTotalt") if etasjedata is not None else None
    bygningsnr = _tekst(svar, "bygningsnummer")

    return {
        "bygningsnr": int(bygningsnr) if bygningsnr else None,
        "bygningstype_kode": _id_verdi(svar, "bygningstypeKodeId"),
        "bra_m2": float(bra) if bra and float(bra) > 0 else None,
        "antall_etasjer": antall_etasjer or None,
        "lon": float(_tekst(posisjon, "x")) if posisjon is not None else None,
        "lat": float(_tekst(posisjon, "y")) if posisjon is not None else None,
    }


def _xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
