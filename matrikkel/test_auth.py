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
            print(f"HTTP {resp.status} - innlogging virker.\n")
            print(resp.read().decode("utf-8")[:1500])
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} - innlogging feilet eller tjenesten avviste kallet.")
        print(e.read().decode("utf-8", errors="replace")[:1500])


if __name__ == "__main__":
    main()
