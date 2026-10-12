#!/usr/bin/env python3
"""
Andrepass-geokoding + bygningsberikelse: finner adresser via Matrikkelen
(MatrikkelAPI) for de adressene Kartverkets åpne Adresse-API (etl/geokod.py)
ikke klarte å slå opp - enten fordi det ikke var noe treff der (stavemåte/
format), eller fordi det var flere treff og ingen kunne velges automatisk
(ofte fordi husnummer manglet helt i kildedata). I tillegg - for enhver
bygning som fortsatt mangler bygningsnummer, uansett om adressen over ble
løst her eller av geokod.py - hentes selve bygningsobjektet fra Matrikkelen.

Matrikkelen gir oss noe det åpne API-et ikke gjør: vi kjenner allerede
kommunen hver bygning tilhører (satt av last_inn.py), så søket kan gjøres
*innenfor riktig kommune* i stedet for fritekst nasjonalt - det er nettopp
det som løser begge feiltypene over. Se db/schema_kjerne_dokumentasjon.md,
avsnittet om "gate", for hvorfor denne tabellen "må fylles av matrikkelsteget".

Kjeden per adresse (alt via MatrikkelAPI, SOAP):
    KommuneService.findKommuneIdForIdent   kommunenummer -> intern KommuneId
    Har vi fra før en kjent adressekode (gate.adressekode, satt av et
    tidligere kjøring av dette skriptet)?
      ja:  AdresseService.findVegadresse       (KommuneId, adressekode, nummer,
                                                 bokstav) -> VegadresseId direkte
      nei: AdresseService.findVegerMedNavn     (KommuneId, gatenavn) -> VegId-er
           AdresseService.findAdresserForVeg   VegId -> VegadresseId-er
           - filtrer lokalt på husnummer+bokstav fra kildeteksten; ett treff
             kreves, akkurat som i geokod.py.
    StoreService.getObject(-s)             VegadresseId(-er) -> Vegadresse-
                                            objekt(er) (nummer, bokstav, punkt)
    StoreService.getObject(vegId)          -> Veg (adressekode, adressenavn)
    StoreService.getObject(matrikkelenhetId) -> Matrikkelenhet (gnr/bnr/fnr/snr)
    BygningService.findByggForAdresse      VegadresseId -> ByggId-er
    - ett treff kreves, samme prinsipp som over.
    StoreService.getObject(byggId)         -> Bygning (bygningsnummer,
                                               bygningstype, bruksareal, etasjer)

Skriver ved adresse-treff: gate (upsert), matrikkelinfo+bygning_matrikkelinfo
(upsert/link) og adresse (gate_id, husnr, bokstav, posisjon, geokoding=
'matrikkel' - den autoritative statusen, se schema_kjerne_dokumentasjon.md).
Skriver ved bygningstreff (uavhengig av om adressen var løst fra før):
bygning.bygningsnr/bygningstype/bra_m2/antall_etasjer/posisjon.

Bruker bare Pythons innebygde bibliotek. Leser brukernavn/passord fra
miljøvariablene MATRIKKEL_BRUKER / MATRIKKEL_PASSORD (se matrikkel/test_auth.py)
- ALDRI skriv disse verdiene til skjerm, logg eller fil.

Bruk (kjøres etter geokod.py):

    docker exec portico_masterdb psql -U postgres -d masterdb -tA -F'|' -c "
        SELECT a.id, a.adressetekst, a.postnummer, a.poststed, k.kommunenr,
               a.bygning_id, a.geokoding, a.gate_id, a.husnr, a.bokstav, g.adressekode
        FROM adresse a
        JOIN bygning b ON b.id = a.bygning_id
        JOIN kommune k ON k.id = b.kommune_id
        LEFT JOIN gate g ON g.id = a.gate_id
        WHERE a.er_hovedadresse AND a.geokoding <> 'manuell' AND a.adressetekst IS NOT NULL
          AND (a.geokoding IN ('ukjent','feilet') OR b.bygningsnr IS NULL);
    " > etl/ut/adresser_a_matrikkelsoke.txt

    python3 etl/matrikkel_adresse.py < etl/ut/adresser_a_matrikkelsoke.txt > etl/ut/matrikkel.sql

    docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/matrikkel.sql

`WHERE ... OR b.bygningsnr IS NULL` gjør skriptet trygt å kjøre på nytt: bygg
som allerede har bygningsnummer og adresser som allerede er løst, hentes ikke
på nytt. Prinsipp, som i geokod.py: ett eksakt treff brukes - på husnummer for
adresse, og på bygg-id for bygning. Null treff, flere treff, eller manglende
husnummer i kildedata logges som avvik og gjettes ikke på.
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
NS_DOMBYG = "http://matrikkel.statkart.no/matrikkelapi/wsapi/v1/domain/bygning"

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
    except urllib.error.URLError as e:
        # Tilkoblingsfeil (timeout, reset, DNS) - ikke et SOAP-svar å tolke.
        # Skal logges som avvik for nettopp denne raden, ikke stoppe hele
        # kjøringen - se "en enkelt dårlig post stopper aldri hele lasten".
        raise MatrikkelFeil(f"Tilkoblingsfeil mot {service}: {e}") from e
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


def logg(ekstern_id, detalj, rapost, kilde="matrikkel-adresse", samling="adresse",
          avvikstype="geokoding_feilet", nokkelfelt="adresse_id") -> str:
    return (f"CALL logg_avvik({q(kilde)},{q(samling)},{q(avvikstype)},{q(ekstern_id)},"
            f"{q(detalj)},NULL,{q(nokkelfelt)},{q_json(rapost)});\n")


def i_blokk(ekstern_id, sql, rapost, kilde="matrikkel-adresse", samling="adresse",
            nokkelfelt="adresse_id") -> str:
    return ("DO $blk$ BEGIN\n" + sql + "EXCEPTION WHEN OTHERS THEN\n"
            f"CALL logg_avvik({q(kilde)},{q(samling)},'db_feil',{q(ekstern_id)},"
            f"SQLSTATE || ': ' || SQLERRM,NULL,{q(nokkelfelt)},{q_json(rapost)});\nEND $blk$;\n")


def main():
    out = sys.stdout
    out.write("BEGIN;\n\n")
    out.write(f"CALL registrer_kildeuttrekk('matrikkel',{q(BASE_URL)},NULL,NULL);\n\n")

    kommune_id_cache: dict[str, int] = {}
    veg_cache: dict[int, dict] = {}
    adresser_for_veg_cache: dict[int, list[dict]] = {}

    antall_ok = antall_feilet = antall_bygg_ok = antall_bygg_feilet = 0

    for rad in sys.stdin:
        rad = rad.rstrip("\n")
        if not rad:
            continue
        felt = rad.split("|", 10)
        if len(felt) != 11:
            continue
        (adresse_id, adressetekst, postnummer, poststed, kommunenummer,
         bygning_id, geokoding, gate_id, husnr_db, bokstav_db, adressekode_db) = felt
        adressetekst = adressetekst.strip()
        if not adressetekst or not kommunenummer:
            continue

        print(f"matrikkelsøker [{adresse_id}] {adressetekst!r} (kommune {kommunenummer})...",
              file=sys.stderr)
        gatenavn, nummer, bokstav = del_opp_adressetekst(adressetekst)
        if geokoding in ("geokodet", "matrikkel") and husnr_db:
            # Adressen er allerede posisjonert fra før - de lagrede feltene er
            # sikrere enn å tolke adressetekst-strengen på nytt.
            nummer = int(husnr_db)
            bokstav = (bokstav_db or "").strip().upper() or None

        spor = {"adresse_id": adresse_id, "adressetekst": adressetekst,
                "kommunenummer": kommunenummer, "gatenavn_tolket": gatenavn,
                "husnr_tolket": nummer, "bokstav_tolket": bokstav}

        if nummer is None:
            out.write(logg(adresse_id, f"mangler husnummer i kildedata for {gatenavn!r}", spor))
            antall_feilet += 1
            continue

        v = None
        try:
            matrikkel_kommune_id = kommune_id_cache.get(kommunenummer)
            if matrikkel_kommune_id is None:
                matrikkel_kommune_id = finn_kommune_id(kommunenummer)
                kommune_id_cache[kommunenummer] = matrikkel_kommune_id

            if adressekode_db:
                # Rask vei: adressekoden er allerede kjent fra en tidligere kjøring.
                vid = finn_vegadresse_direkte(matrikkel_kommune_id, int(adressekode_db), nummer, bokstav)
                if vid:
                    v = hent_vegadresser([vid])[0]
                    spor["via"] = "adressekode_direkte"

            if v is None:
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
                if len(treff) == 1:
                    v = treff[0]
        except MatrikkelFeil as e:
            spor["feil"] = str(e)
            out.write(logg(adresse_id, "MatrikkelAPI-kall feilet: " + str(e)[:200], spor))
            antall_feilet += 1
            continue

        if v is None:
            grunn = ("ingen veg funnet" if not spor.get("veg_ider_funnet") else
                     "ingen treff på husnummer" if spor.get("antall_treff") == 0 else
                     f"{spor.get('antall_treff')} treff, ingen valgt automatisk")
            out.write(logg(adresse_id, f"matrikkel: {grunn} for {adressetekst}", spor))
            antall_feilet += 1
            continue

        # Full adresse-berikelse (gate/matrikkelinfo/posisjon) gjøres bare om
        # adressen ikke allerede er løst - ellers er dette allerede gjort.
        if geokoding in ("ukjent", "feilet"):
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
                f"WHERE id = {int(bygning_id)};\n"
            )
            if matrikkelenhet is not None:
                sql += (
                    f"INSERT INTO bygning_matrikkelinfo (bygning_id, matrikkelinfo_id) "
                    f"SELECT {int(bygning_id)}, m.id FROM matrikkelinfo m "
                    f"WHERE m.kommunenr = {q(kommunenummer)} "
                    f"AND m.gardsnr = {matrikkelenhet['gardsnr']} AND m.bruksnr = {matrikkelenhet['bruksnr']} "
                    f"AND COALESCE(m.festenr,0) = COALESCE({matrikkelenhet['festenr'] or 'NULL'},0) "
                    f"AND COALESCE(m.seksjonsnr,0) = COALESCE({matrikkelenhet['seksjonsnr'] or 'NULL'},0) "
                    f"ON CONFLICT DO NOTHING;\n"
                )

            out.write(i_blokk(adresse_id, sql, spor))
            antall_ok += 1

        # Bygningsoppslag - uavhengig av om adressen ble løst her eller var
        # løst fra før (geokod.py eller en tidligere kjøring av dette skriptet).
        try:
            bygg_ider = finn_bygg_ider_for_adresse(v["id"])
        except MatrikkelFeil as e:
            out.write(logg(bygning_id, "MatrikkelAPI-kall feilet (bygningsoppslag): " + str(e)[:200], spor,
                           kilde="matrikkel-bygning", samling="bygning", avvikstype="annet",
                           nokkelfelt="bygning_id"))
            antall_bygg_feilet += 1
            continue

        if len(bygg_ider) != 1:
            grunn = "ingen bygg funnet" if not bygg_ider else f"{len(bygg_ider)} bygg funnet, ingen valgt automatisk"
            out.write(logg(bygning_id, f"matrikkel: {grunn} for adresse {adressetekst}", spor,
                           kilde="matrikkel-bygning", samling="bygning", avvikstype="annet",
                           nokkelfelt="bygning_id"))
            antall_bygg_feilet += 1
            continue

        try:
            info = hent_bygning(bygg_ider[0])
        except MatrikkelFeil as e:
            out.write(logg(bygning_id, "MatrikkelAPI-kall feilet (bygningsobjekt): " + str(e)[:200], spor,
                           kilde="matrikkel-bygning", samling="bygning", avvikstype="annet",
                           nokkelfelt="bygning_id"))
            antall_bygg_feilet += 1
            continue

        if info["bygningsnr"] is None:
            out.write(logg(bygning_id, "bygg funnet i Matrikkelen, men uten bygningsnummer", spor,
                           kilde="matrikkel-bygning", samling="bygning", avvikstype="annet",
                           nokkelfelt="bygning_id"))
            antall_bygg_feilet += 1
            continue

        spor["bygning"] = info
        bygg_lon = info["lon"] if info["lon"] is not None else v["lon"]
        bygg_lat = info["lat"] if info["lat"] is not None else v["lat"]
        # bygningstype lagres som Matrikkelens rå kodeverdi (f.eks. "181"), ikke
        # oversatt til tekst ennå - se KodelisteService/matrikkel/ut/siste_svar.xml
        # for å slå opp navnet senere.
        bygg_sql = (
            f"UPDATE bygning SET "
            f"bygningsnr = {info['bygningsnr']}, "
            f"bygningstype = {q(info['bygningstype_kode'])}, "
            f"bra_m2 = {info['bra_m2'] if info['bra_m2'] is not None else 'NULL'}, "
            f"antall_etasjer = {info['antall_etasjer'] if info['antall_etasjer'] is not None else 'NULL'}, "
            f"matrikkel_match = 'adresse', "
            f"posisjon = COALESCE(posisjon, ST_SetSRID(ST_MakePoint({bygg_lon},{bygg_lat}),4326)::geography) "
            f"WHERE id = {int(bygning_id)};\n"
        )
        out.write(i_blokk(bygning_id, bygg_sql, spor, kilde="matrikkel-bygning", samling="bygning",
                          nokkelfelt="bygning_id"))
        antall_bygg_ok += 1

    out.write("\nDO $$ BEGIN PERFORM rydd_kildeuttrekk('matrikkel'); END $$;\n")
    out.write("COMMIT;\n")
    print(f"\nadresse - matrikkel-geokodet: {antall_ok}, feilet: {antall_feilet}", file=sys.stderr)
    print(f"bygning - bygningsnr funnet: {antall_bygg_ok}, feilet: {antall_bygg_feilet}", file=sys.stderr)


if __name__ == "__main__":
    main()
