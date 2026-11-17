#!/usr/bin/env python3
"""
Geokoding + bygningsberikelse: finner adresser via Matrikkelen (MatrikkelAPI)
for alt jobs/build.py og jobs/sync.py har lastet inn - ingen av Aktiv kommune sine 12 instanser
leverer koordinater selv. I tillegg - for enhver bygning som fortsatt mangler
bygningsnummer - hentes selve bygningsobjektet fra Matrikkelen.

Eneste geokodingssteg i pipelinen. Et tidligere forsteg mot Kartverkets åpne
Adresse-API (etl/geokod.py) er bevisst fjernet til fordel for denne ene
kilden: enklere å forstå og vedlikeholde, mot en målt kostnad på ca. 3
prosentpoeng lavere automatisk treffrate (69,7 % mot 73,1 % i en nasjonal
test av alle 12 kommunene) - et bevisst valg, ikke en forglemmelse. De
adressene det gjelder havner i synk_avvik som før og rettes manuelt.

Vi kjenner allerede kommunen hver bygning tilhører (satt av jobs/build.py/jobs/sync.py), så
søket gjøres *innenfor riktig kommune* i stedet for fritekst nasjonalt. Se
db/schema_kjerne_dokumentasjon.md, avsnittet om "gate", for hvorfor denne
tabellen "må fylles av matrikkelsteget".

Kjeden per adresse (alt via MatrikkelAPI, SOAP):
    KommuneService.findKommuneIdForIdent   kommunenummer -> intern KommuneId
    Har vi fra før en kjent adressekode (gate.adressekode, satt av en
    tidligere kjøring av dette skriptet)?
      ja:  AdresseService.findVegadresse       (KommuneId, adressekode, nummer,
                                                 bokstav) -> VegadresseId direkte
      nei: AdresseService.findVegerMedNavn     (KommuneId, gatenavn) -> VegId-er
           AdresseService.findAdresserForVeg   VegId -> VegadresseId-er
           - filtrer lokalt på husnummer+bokstav fra kildeteksten; ett treff
             kreves.
    StoreService.getObject(-s)             VegadresseId(-er) -> Vegadresse-
                                            objekt(er) (nummer, bokstav, punkt)
    StoreService.getObject(vegId)          -> Veg (adressekode, adressenavn)
    StoreService.getObject(matrikkelenhetId) -> Matrikkelenhet (gnr/bnr/fnr/snr)
    BygningService.findByggForAdresse      VegadresseId -> ByggId-er
    - ett treff kreves, samme prinsipp som over.
    StoreService.getObject(byggId)         -> Bygning (bygningsnummer,
                                               bygningstype, bruksareal, etasjer)

Skriver matrikkelinfo (upsert, knyttet til adressens bygg via bygning_id,
gnr/bnr/fnr/snr) uansett geokodingsstatus - billig og idempotent, så det
forsøkes for enhver adresse vi klarer å slå opp. Skriver ved adresse-treff
som fortsatt mangler geokoding: i tillegg gate (upsert) og adresse (gate_id,
husnr, bokstav, posisjon, geokoding='matrikkel' - den autoritative statusen,
se schema_kjerne_dokumentasjon.md). Skriver ved bygningstreff (uavhengig av
om adressen var løst fra før): bygning.bygningsnr/bygningstype/bra_m2/
antall_etasjer/posisjon.

Bruker bare Pythons innebygde bibliotek. Leser brukernavn/passord fra
miljøvariablene MATRIKKEL_BRUKER / MATRIKKEL_PASSORD (se etl/dev/check_matrikkel_auth.py)
- ALDRI skriv disse verdiene til skjerm, logg eller fil. MATRIKKEL_MILJO velger
miljø: "test" (prodtest.matrikkel.no, standard) eller "prod" (matrikkel.no).

Bruk (kjøres etter jobs/build.py, og etter hver kjøring av jobs/sync.py, så nye bygg
får posisjon):

    docker exec portico_masterdb psql -U postgres -d masterdb -tA -F'|' -c "
        SELECT a.id, a.adressetekst, a.postnummer, a.poststed, k.kommunenr,
               a.bygning_id, a.geokoding, a.gate_id, a.husnr, a.bokstav, g.adressekode
        FROM adresse a
        JOIN bygning b ON b.id = a.bygning_id
        JOIN kommune k ON k.id = b.kommune_id
        LEFT JOIN gate g ON g.id = a.gate_id
        WHERE a.er_hovedadresse AND a.geokoding <> 'manuell' AND a.adressetekst IS NOT NULL
          AND (a.geokoding IN ('ukjent','feilet') OR b.bygningsnr IS NULL
               OR NOT EXISTS (SELECT 1 FROM matrikkelinfo m WHERE m.bygning_id = b.id));
    " > etl/ut/adresser_a_matrikkelsoke.txt

    (cd etl && python3 -m jobs.geocode) < etl/ut/adresser_a_matrikkelsoke.txt > etl/ut/matrikkel.sql

    docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/matrikkel.sql

De tre OR-leddene gjør skriptet trygt å kjøre på nytt: et bygg som allerede
har bygningsnummer, en adresse som allerede er løst, og et bygg som allerede
har en matrikkelinfo-lenke, hentes ikke på nytt for akkurat den grunnen - men
raden kan likevel dukke opp igjen så lenge én av de andre tingene fortsatt
mangler. Prinsipp: ett eksakt treff brukes - på husnummer for adresse, og på
bygg-id for bygning. Null treff, flere treff, eller manglende husnummer i
kildedata logges som avvik og gjettes ikke på.
"""
import re
import sys

from lib.matrikkel import (
    BASE_URL, MatrikkelFeil, finn_adresse_ider_for_veg, finn_bygg_ider_for_adresse,
    finn_kommune_id, finn_veg_ider, finn_vegadresse_direkte, hent_bygning,
    hent_matrikkelenhet, hent_veg, hent_vegadresser,
)
from lib.sqlgen import i_blokk_matrikkel, logg_matrikkel, q


# ---------------------------------------------------------------------------
# Adressetekst-parsing
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


def main():
    out = sys.stdout
    out.write("BEGIN;\n\n")
    out.write(f"CALL registrer_kildeuttrekk('matrikkel',{q(BASE_URL)},NULL);\n\n")

    kommune_id_cache: dict[str, int] = {}
    veg_cache: dict[int, dict] = {}
    adresser_for_veg_cache: dict[int, list[dict]] = {}

    antall_ok = antall_feilet = antall_bygg_ok = antall_bygg_feilet = antall_matrikkelinfo_ok = 0

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
            # sikrere enn å tolke adressetekst-strengen på nytt. 'geokodet'
            # finnes bare på databaser som ble lastet før etl/geokod.py ble
            # fjernet; nye kjøringer produserer ikke denne statusen lenger.
            nummer = int(husnr_db)
            bokstav = (bokstav_db or "").strip().upper() or None

        spor = {"adresse_id": adresse_id, "adressetekst": adressetekst,
                "kommunenummer": kommunenummer, "gatenavn_tolket": gatenavn,
                "husnr_tolket": nummer, "bokstav_tolket": bokstav}

        if nummer is None:
            out.write(logg_matrikkel(adresse_id, f"mangler husnummer i kildedata for {gatenavn!r}", spor))
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
            out.write(logg_matrikkel(adresse_id, "MatrikkelAPI-kall feilet: " + str(e)[:200], spor))
            antall_feilet += 1
            continue

        if v is None:
            grunn = ("ingen veg funnet" if not spor.get("veg_ider_funnet") else
                     "ingen treff på husnummer" if spor.get("antall_treff") == 0 else
                     f"{spor.get('antall_treff')} treff, ingen valgt automatisk")
            out.write(logg_matrikkel(adresse_id, f"matrikkel: {grunn} for {adressetekst}", spor))
            antall_feilet += 1
            continue

        # Matrikkelinfo (gnr/bnr/fnr/snr) hentes og lenkes uansett
        # geokodingsstatus - billig (ett kall) og idempotent (ON CONFLICT DO
        # NOTHING), så det er ikke verdt å holde styr på om lenken allerede
        # finnes fra før av. Dekker både adresser som løses her og adresser
        # som var løst fra før (en tidligere kjøring) men mangler matrikkelinfo-lenken.
        matrikkelenhet = None
        if v["matrikkelenhet_id"]:
            try:
                matrikkelenhet = hent_matrikkelenhet(v["matrikkelenhet_id"])
            except MatrikkelFeil as e:
                spor["feil"] = str(e)
                out.write(logg_matrikkel(bygning_id, "MatrikkelAPI-kall feilet (matrikkelenhet): " + str(e)[:200], spor,
                               avvikstype="annet", nokkelfelt="bygning_id"))

        if matrikkelenhet is not None:
            # Hører til adressens bygg: samme gnr/bnr lagres én gang per bygg
            # (bygning_id er med i UNIQUE-indeksen på matrikkelinfo).
            spor["matrikkelenhet"] = matrikkelenhet
            mi_sql = (
                f"INSERT INTO matrikkelinfo (bygning_id, kommunenr, gardsnr, bruksnr, festenr, seksjonsnr) "
                f"VALUES ({int(bygning_id)},{q(kommunenummer)},{matrikkelenhet['gardsnr']},{matrikkelenhet['bruksnr']},"
                f"{matrikkelenhet['festenr'] or 'NULL'},{matrikkelenhet['seksjonsnr'] or 'NULL'}) "
                f"ON CONFLICT (bygning_id, kommunenr, gardsnr, bruksnr, COALESCE(festenr,0), COALESCE(seksjonsnr,0)) "
                f"DO NOTHING;\n"
            )
            out.write(i_blokk_matrikkel(bygning_id, mi_sql, spor, nokkelfelt="bygning_id"))
            antall_matrikkelinfo_ok += 1

        # Full adresse-berikelse (gate/posisjon/geokodingsstatus) gjøres bare
        # om adressen ikke allerede er løst - ellers er dette allerede gjort.
        if geokoding in ("ukjent", "feilet"):
            try:
                veg = veg_cache.get(v["veg_id"])
                if veg is None:
                    veg = hent_veg(v["veg_id"])
                    veg_cache[v["veg_id"]] = veg
            except MatrikkelFeil as e:
                spor["feil"] = str(e)
                out.write(logg_matrikkel(adresse_id, "MatrikkelAPI-kall feilet (berikelse): " + str(e)[:200], spor))
                antall_feilet += 1
                continue

            spor["veg"] = veg
            lon, lat = v["lon"], v["lat"]

            sql = (
                f"INSERT INTO gate (kommune_id, adressekode, gatenavn) "
                f"SELECT k.id, {veg['adressekode']}, {q(veg['adressenavn'])} "
                f"FROM kommune k WHERE k.kommunenr = {q(kommunenummer)} "
                f"ON CONFLICT (kommune_id, adressekode) DO UPDATE SET gatenavn = EXCLUDED.gatenavn;\n"
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

            out.write(i_blokk_matrikkel(adresse_id, sql, spor))
            antall_ok += 1

        # Bygningsoppslag - uavhengig av om adressen ble løst her eller var
        # løst fra før (en tidligere kjøring av dette skriptet).
        # Et mislykket forsøk markeres 'ikke_funnet' (men overskriver aldri en
        # 'adresse'-match som adressesteget over nettopp satte for samme bygg) -
        # ellers ser et forsøkt-men-mislykket oppslag identisk ut som et som
        # aldri ble forsøkt, selv om beviset ligger i synk_avvik.
        ikke_funnet_sql = (f"UPDATE bygning SET matrikkel_match='ikke_funnet' "
                           f"WHERE id={int(bygning_id)} AND matrikkel_match='ikke_forsokt';\n")

        try:
            bygg_ider = finn_bygg_ider_for_adresse(v["id"])
        except MatrikkelFeil as e:
            out.write(logg_matrikkel(bygning_id, "MatrikkelAPI-kall feilet (bygningsoppslag): " + str(e)[:200], spor,
                           kilde="matrikkel-bygning", samling="bygning", avvikstype="annet",
                           nokkelfelt="bygning_id"))
            out.write(ikke_funnet_sql)
            antall_bygg_feilet += 1
            continue

        if len(bygg_ider) != 1:
            grunn = "ingen bygg funnet" if not bygg_ider else f"{len(bygg_ider)} bygg funnet, ingen valgt automatisk"
            out.write(logg_matrikkel(bygning_id, f"matrikkel: {grunn} for adresse {adressetekst}", spor,
                           kilde="matrikkel-bygning", samling="bygning", avvikstype="annet",
                           nokkelfelt="bygning_id"))
            out.write(ikke_funnet_sql)
            antall_bygg_feilet += 1
            continue

        try:
            info = hent_bygning(bygg_ider[0])
        except MatrikkelFeil as e:
            out.write(logg_matrikkel(bygning_id, "MatrikkelAPI-kall feilet (bygningsobjekt): " + str(e)[:200], spor,
                           kilde="matrikkel-bygning", samling="bygning", avvikstype="annet",
                           nokkelfelt="bygning_id"))
            out.write(ikke_funnet_sql)
            antall_bygg_feilet += 1
            continue

        if info["bygningsnr"] is None:
            out.write(logg_matrikkel(bygning_id, "bygg funnet i Matrikkelen, men uten bygningsnummer", spor,
                           kilde="matrikkel-bygning", samling="bygning", avvikstype="annet",
                           nokkelfelt="bygning_id"))
            out.write(ikke_funnet_sql)
            antall_bygg_feilet += 1
            continue

        spor["bygning"] = info
        bygg_lon = info["lon"] if info["lon"] is not None else v["lon"]
        bygg_lat = info["lat"] if info["lat"] is not None else v["lat"]
        # bygningstype lagres som Matrikkelens rå kodeverdi (f.eks. "181"), ikke
        # oversatt til tekst ennå - se KodelisteService/etl/ut/siste_svar.xml
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
        out.write(i_blokk_matrikkel(bygning_id, bygg_sql, spor, kilde="matrikkel-bygning", samling="bygning",
                          nokkelfelt="bygning_id"))
        antall_bygg_ok += 1

    out.write("\nDO $$ BEGIN PERFORM rydd_kildeuttrekk('matrikkel'); END $$;\n")
    out.write("COMMIT;\n")
    print(f"\nadresse - matrikkel-geokodet: {antall_ok}, feilet: {antall_feilet}", file=sys.stderr)
    print(f"bygning - bygningsnr funnet: {antall_bygg_ok}, feilet: {antall_bygg_feilet}", file=sys.stderr)
    print(f"bygning - matrikkelinfo (gnr/bnr) lenket: {antall_matrikkelinfo_ok}", file=sys.stderr)


if __name__ == "__main__":
    main()
