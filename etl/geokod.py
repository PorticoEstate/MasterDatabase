#!/usr/bin/env python3
"""
Geokoder adresser mot Kartverkets åpne Adresse-API og skriver SQL som fyller
adresse.posisjon (og bygning.antall_etasjer forblir urørt - dette skriptet
rører bare posisjon).

Bruker bare Pythons innebygde bibliotek - ingen "pip install" nødvendig.
Leser en enkel pipe-delimited liste fra standard-inn (id|adressetekst|
postnummer|poststed|forventet_kommunenr) og skriver SQL til standard-ut,
akkurat som last_inn.py - ingenting skjer mot databasen i dette steget selv.

Bruk (tre kommandoer, ingen av dem gjør noe før den tredje):

    docker exec portico_masterdb psql -U postgres -d masterdb -tA -F'|' -c "
        SELECT a.id, a.adressetekst, a.postnummer, a.poststed, k.kommunenr
        FROM adresse a
        JOIN bygning b ON b.id = a.bygning_id
        JOIN kommune k ON k.id = b.kommune_id
        WHERE a.posisjon IS NULL AND a.adressetekst IS NOT NULL;
    " > etl/ut/adresser_a_geokode.txt

    python3 etl/geokod.py < etl/ut/adresser_a_geokode.txt > etl/ut/geokoding.sql

    docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/geokoding.sql

Se etl/README.md for full forklaring.

Prinsipp: ett eksakt treff brukes. Null treff eller flere enn ett treff
logges som avvik og gjettes IKKE på - et geokodet punkt som er feil er verre
enn ingen punkt, siden det gir falsk trygghet i et nærhetssøk.
"""
import json
import sys
import time
import urllib.parse
import urllib.request

API = "https://ws.geonorge.no/adresser/v1/sok"


def sok_adresse(adressetekst: str, postnummer: str | None) -> list[dict]:
    """Slår opp en adresse. sok (fritekst) er brukt i stedet for det strengere
    adressetekst-parameteret, fordi Aktiv kommune sine adresser ikke alltid er
    skrevet nøyaktig som i det offisielle registeret (mellomrom, bokstav).

    Når postnummer er kjent, kreves det at nettopp ett av treffene har det
    postnummeret - finner filtreringen null treff, regnes søket som mislykket,
    IKKE som "bruk det ufiltrerte enkelttreffet". Uten denne regelen matchet
    f.eks. "Festplassen" (Bergen) mot den eneste "Festplassen" i hele landet
    som har husnummer - som ligger i Lørenskog, ikke Bergen."""
    params = {"sok": adressetekst, "treffPerSide": 5}
    url = f"{API}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=15) as resp:
        d = json.loads(resp.read().decode("utf-8"))
    treff = d.get("adresser", [])
    if postnummer:
        return [a for a in treff if a.get("postnummer") == postnummer]
    return treff


def q(v):
    if v is None or v == "":
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


def main():
    out = sys.stdout
    out.write("BEGIN;\n\n")

    antall_ok = antall_feilet = antall_mismatch = 0

    for rad in sys.stdin:
        rad = rad.rstrip("\n")
        if not rad:
            continue
        felt = rad.split("|", 4)
        if len(felt) != 5:
            continue
        adresse_id, adressetekst, postnummer, poststed, forventet_kommunenr = felt
        adressetekst = adressetekst.strip()
        if not adressetekst:
            continue

        print(f"geokoder [{adresse_id}] {adressetekst!r} ({postnummer or '?'})...", file=sys.stderr)

        try:
            treff = sok_adresse(adressetekst, postnummer or None)
        except Exception as e:
            treff = []
            out.write(f"INSERT INTO synk_avvik (samling,avvikstype,ekstern_id,detalj,kilde) "
                      f"VALUES ('adresse','geokoding_feilet',{q(adresse_id)},"
                      f"{q('API-kall feilet: ' + str(e)[:200])},'kartverket-adresse');\n")
            out.write(f"UPDATE adresse SET geokoding='feilet' WHERE id={adresse_id};\n")
            antall_feilet += 1
            time.sleep(0.2)
            continue

        if len(treff) != 1:
            grunn = "ingen treff" if not treff else f"{len(treff)} treff, ingen valgt automatisk"
            out.write(f"INSERT INTO synk_avvik (samling,avvikstype,ekstern_id,detalj,kilde) "
                      f"VALUES ('adresse','geokoding_feilet',{q(adresse_id)},"
                      f"{q(grunn + ' for ' + adressetekst)},'kartverket-adresse');\n")
            out.write(f"UPDATE adresse SET geokoding='feilet' WHERE id={adresse_id};\n")
            antall_feilet += 1
            time.sleep(0.2)
            continue

        a = treff[0]
        punkt = a["representasjonspunkt"]
        lon, lat = punkt["lon"], punkt["lat"]
        funnet_kommunenr = a.get("kommunenummer")

        out.write(
            f"UPDATE adresse SET "
            f"posisjon = ST_SetSRID(ST_MakePoint({lon},{lat}),4326)::geography, "
            f"geokoding = 'geokodet' "
            f"WHERE id = {adresse_id};\n"
        )
        # Speil samme punkt til bygningen selv, som fallback der en ressurs
        # ikke har egen adresse men bygget den ligger i har fått et punkt.
        out.write(
            f"UPDATE bygning SET posisjon = ST_SetSRID(ST_MakePoint({lon},{lat}),4326)::geography "
            f"WHERE id = (SELECT bygning_id FROM adresse WHERE id={adresse_id}) "
            f"AND posisjon IS NULL;\n"
        )
        antall_ok += 1

        if forventet_kommunenr and funnet_kommunenr and forventet_kommunenr != funnet_kommunenr:
            # Flagges, endres ikke: kommune_id er identitetsdata satt av
            # innlastingen, og skal ikke overskrives stille av et geokodings-
            # oppslag. Dette er nettopp scenarioet der en instans kan tenkes
            # å betjene en annen kommune enn vi antok.
            out.write(f"INSERT INTO synk_avvik (samling,avvikstype,ekstern_id,detalj,kilde) "
                      f"VALUES ('adresse','annet',{q(adresse_id)},"
                      f"{q(f'Geokodet kommunenr {funnet_kommunenr} stemmer ikke med antatt {forventet_kommunenr}')},"
                      f"'kartverket-adresse');\n")
            antall_mismatch += 1

        time.sleep(0.2)

    out.write("\nCOMMIT;\n")
    print(f"\ngeokodet: {antall_ok}, feilet: {antall_feilet}, kommune-mismatch: {antall_mismatch}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
