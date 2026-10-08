#!/usr/bin/env python3
"""Minimalt sjekk-skript: bekrefter at Basic Auth mot MatrikkelAPI virker.
Kaller KodelisteService.getKodelisterEnkel - den enkleste tjenesten som finnes,
krever ingen søkeparametre. Leser brukernavn/passord fra miljøvariablene
MATRIKKEL_BRUKER / MATRIKKEL_PASSORD - se etl/README.md-tilsvarende for Matrikkel.
"""
import base64
import os
import urllib.error
import urllib.request
import xml.dom.minidom

UT_FIL = os.path.join(os.path.dirname(__file__), "ut", "siste_svar.xml")

BASE_URL = "https://prodtest.matrikkel.no"  # testmiljø - matcher strukturen i produksjon

ENVELOPE = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:kod="http://matrikkel.statkart.no/matrikkelapi/wsapi/v1/service/kodeliste"
    xmlns:dom="http://matrikkel.statkart.no/matrikkelapi/wsapi/v1/domain">
    <soapenv:Header/>
    <soapenv:Body>
        <kod:getKodelisterEnkel>
            <kod:matrikkelContext>
                <dom:locale>no_NO</dom:locale>
                <dom:brukOriginaleKoordinater>true</dom:brukOriginaleKoordinater>
                <dom:koordinatsystemKodeId><dom:value>22</dom:value></dom:koordinatsystemKodeId>
                <dom:systemVersion>trunk</dom:systemVersion>
                <dom:klientIdentifikasjon>bergen-masterdb</dom:klientIdentifikasjon>
            </kod:matrikkelContext>
        </kod:getKodelisterEnkel>
    </soapenv:Body>
</soapenv:Envelope>"""


def main():
    bruker = os.environ["MATRIKKEL_BRUKER"]
    passord = os.environ["MATRIKKEL_PASSORD"]
    auth = base64.b64encode(f"{bruker}:{passord}".encode()).decode()

    req = urllib.request.Request(
        f"{BASE_URL}/matrikkelapi/wsapi/v1/KodelisteServiceWS",
        data=ENVELOPE.encode("utf-8"),
        headers={"Content-Type": "text/xml", "Authorization": f"Basic {auth}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status, svar = resp.status, resp.read().decode("utf-8")
            print(f"HTTP {status} - innlogging virker.\n")
    except urllib.error.HTTPError as e:
        status, svar = e.code, e.read().decode("utf-8", errors="replace")
        print(f"HTTP {status} - innlogging feilet eller tjenesten avviste kallet.")

    try:
        pen = xml.dom.minidom.parseString(svar).toprettyxml(indent="  ")
        # toprettyxml legger inn mange tomme linjer for tekstnoder - luk dem bort.
        pen = "\n".join(l for l in pen.splitlines() if l.strip())
    except Exception:
        pen = svar  # ikke gyldig XML (f.eks. en HTML-feilside) - vis rått i stedet

    os.makedirs(os.path.dirname(UT_FIL), exist_ok=True)
    with open(UT_FIL, "w", encoding="utf-8") as f:
        f.write(pen)
    print(f"Fullt svar (formatert) lagret i {UT_FIL} - åpne den i VS Code for oversikt.\n")
    print(pen[:1500])


if __name__ == "__main__":
    main()
