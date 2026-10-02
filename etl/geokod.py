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

Hver kjøring registrerer et kildeuttrekk (metadata, ikke hele svaret). Hvert
geokodingsavvik - ingen eller flere treff, API-feil, avvikende kommunenummer,
databasefeil - lagrer selve oppslaget og Kartverkets svar direkte på avviket
(synk_avvik.rapost), uavhengig av hvor lenge kildeuttrekket beholdes.

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


def sok_adresse(adressetekst: str, postnummer: str | None) -> tuple[list[dict], list[dict]]:
    """Slår opp en adresse. sok (fritekst) er brukt i stedet for det strengere
    adressetekst-parameteret, fordi Aktiv kommune sine adresser ikke alltid er
    skrevet nøyaktig som i det offisielle registeret (mellomrom, bokstav).

    Når postnummer er kjent, kreves det at nettopp ett av treffene har det
    postnummeret - finner filtreringen null treff, regnes søket som mislykket,
    IKKE som "bruk det ufiltrerte enkelttreffet". Uten denne regelen matchet
    f.eks. "Festplassen" (Bergen) mot den eneste "Festplassen" i hele landet
    som har husnummer - som ligger i Lørenskog, ikke Bergen.

    Returnerer (godkjente treff, alle treff fra API-et). De ufiltrerte treffene
    lagres i kildeuttrekk så den som går gjennom et avvik ser hva API-et svarte."""
    params = {"sok": adressetekst, "treffPerSide": 5}
    url = f"{API}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=15) as resp:
        d = json.loads(resp.read().decode("utf-8"))
    treff = d.get("adresser", [])
    if postnummer:
        return [a for a in treff if a.get("postnummer") == postnummer], treff
    return treff, treff


def q(v):
    if v is None or v == "":
        return "NULL"
    return "'" + str(v).replace("'", "''").replace("\x00", "") + "'"


def q_json(obj) -> str:
    """JSON-literal. jsonb avviser \\u0000, så den escapen fjernes."""
    tekst = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("\\u0000", "")
    return q(tekst) + "::jsonb"


def logg(adresse_id, avvikstype, detalj, rapost=None) -> str:
    """rapost er oppslaget og Kartverkets svar for nettopp denne adressen -
    lagres direkte på avviket, ikke i et delt kildeuttrekk."""
    rapost_sql = q_json(rapost) if rapost is not None else "NULL"
    return (f"CALL logg_avvik('kartverket-adresse','adresse',{q(avvikstype)},{q(adresse_id)},"
            f"{q(detalj)},NULL,'adresse_id',{rapost_sql});\n")


def i_blokk(adresse_id, sql, rapost=None) -> str:
    """Én DO-blokk per adresse: feiler en UPDATE i databasen, rulles bare den
    adressen tilbake og feilen loggføres som db_feil."""
    rapost_sql = q_json(rapost) if rapost is not None else "NULL"
    return ("DO $blk$ BEGIN\n" + sql + "EXCEPTION WHEN OTHERS THEN\n"
            f"CALL logg_avvik('kartverket-adresse','adresse','db_feil',{q(adresse_id)},"
            f"SQLSTATE || ': ' || SQLERRM,NULL,'adresse_id',{rapost_sql});\nEND $blk$;\n")


def main():
    out = sys.stdout
    # Trenger ikke lenger vente til alle adressene er slått opp: payload=NULL,
    # så registreringen kan skje først igjen, slik FK-en krever.
    out.write("BEGIN;\n\n")
    out.write(f"CALL registrer_kildeuttrekk('kartverket-adresse',{q(API)},NULL,NULL);\n\n")
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
        post = {"adresse_id": adresse_id, "sok": adressetekst, "postnummer": postnummer or None,
                "forventet_kommunenr": forventet_kommunenr or None}

        try:
            treff, alle_treff = sok_adresse(adressetekst, postnummer or None)
            post["svar"] = alle_treff
        except Exception as e:
            post["svar"] = {"feil": f"{type(e).__name__}: {str(e)[:200]}"}
            out.write(logg(adresse_id, "geokoding_feilet", "API-kall feilet: " + str(e)[:200], rapost=post)
                       + f"UPDATE adresse SET geokoding='feilet' WHERE id={int(adresse_id)};\n")
            antall_feilet += 1
            time.sleep(0.2)
            continue

        if len(treff) != 1:
            grunn = "ingen treff" if not treff else f"{len(treff)} treff, ingen valgt automatisk"
            out.write(logg(adresse_id, "geokoding_feilet", grunn + " for " + adressetekst, rapost=post)
                       + f"UPDATE adresse SET geokoding='feilet' WHERE id={int(adresse_id)};\n")
            antall_feilet += 1
            time.sleep(0.2)
            continue

        a = treff[0]
        punkt = a["representasjonspunkt"]
        lon, lat = punkt["lon"], punkt["lat"]
        funnet_kommunenr = a.get("kommunenummer")

        sql = (
            f"UPDATE adresse SET "
            f"posisjon = ST_SetSRID(ST_MakePoint({lon},{lat}),4326)::geography,"
            f"adressetekst = {q(a['adressetekst'])}, "
            f"gatenavn = {q(a['adressenavn'])}, "
            f"husnr = {q(a['nummer'])}, "
            f"bokstav = {q(a['bokstav'])}, "
            f"poststed = {q(a['poststed'])}, "
            f"postnummer = {q(a['postnummer'])}, "
            f"geokoding = 'geokodet' "
            f"WHERE id = {int(adresse_id)};\n"
            # Speil samme punkt til bygningen selv, som fallback der en ressurs
            # ikke har egen adresse men bygget den ligger i har fått et punkt.
            f"UPDATE bygning SET posisjon = ST_SetSRID(ST_MakePoint({lon},{lat}),4326)::geography "
            f"WHERE id = (SELECT bygning_id FROM adresse WHERE id={int(adresse_id)}) "
            f"AND posisjon IS NULL;\n"
        )
        antall_ok += 1

        if forventet_kommunenr and funnet_kommunenr and forventet_kommunenr != funnet_kommunenr:
            # Flagges, endres ikke: kommune_id er identitetsdata satt av
            # innlastingen, og skal ikke overskrives stille av et geokodings-
            # oppslag. Dette er nettopp scenarioet der en instans kan tenkes
            # å betjene en annen kommune enn vi antok.
            sql += logg(adresse_id, "annet",
                        f"Geokodet kommunenr {funnet_kommunenr} stemmer ikke med antatt {forventet_kommunenr}",
                        rapost=post)
            antall_mismatch += 1

        out.write(i_blokk(adresse_id, sql, rapost=post))
        time.sleep(0.2)

    out.write("\nDO $$ BEGIN PERFORM rydd_kildeuttrekk('kartverket-adresse'); END $$;\n")
    out.write("COMMIT;\n")
    print(f"\ngeokodet: {antall_ok}, feilet: {antall_feilet}, kommune-mismatch: {antall_mismatch}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
