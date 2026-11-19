#!/usr/bin/env python3
"""
Geokoding + bygningsberikelse: finner adresser via Matrikkelen (MatrikkelAPI)
for det jobs/build.py og jobs/sync.py har lastet inn og som fortsatt mangler noe
(ved første kjøring i praksis alt, siden ingen av Aktiv kommune sine 12 instanser
leverer koordinater selv; senere bare restmengden, se nederst). I tillegg hentes
selve bygningsobjektet fra Matrikkelen for bygninger som mangler bygningsnummer.
Har bygget et bygningsnummer fra kilden (cadastral_references), brukes det først:
bygget slås opp direkte på nummeret, og adressen hentes fra det bygget (se
"Kildens bygningsnr" under). Adresseteksten søkes bare når det ikke gir noe.

Eneste geokodingssteg i pipelinen. Et tidligere forsteg mot Kartverkets åpne
Adresse-API (etl/geokod.py) er bevisst fjernet til fordel for denne ene
kilden: enklere å forstå og vedlikeholde, mot en målt kostnad på ca. 3
prosentpoeng lavere automatisk treffrate (69,7 % mot 73,1 % i en nasjonal
test av alle 12 kommunene) - et bevisst valg, ikke en forglemmelse. De
adressene det gjelder havner i synk_avvik som før og rettes manuelt.

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
    - ett treff kreves, samme prinsipp som over. Har bygget et bygningsnr
      fra kildens cadastral_references (se under) og adressen gir flere
      bygg, hentes alle kandidatene og det med samme bygningsnummer velges
      (bare ved nøyaktig ett treff). Dette er reserveveien: har bygget et
      kildenummer, forsøkes det først direkte (neste avsnitt).
    StoreService.getObject(byggId)         -> Bygning (bygningsnummer,
                                               bygningstype, bruksareal, etasjer)

Kildens bygningsnr: jobs/build.py og jobs/sync.py legger et bygningsnummer fra
cadastral_references i bygning.bygningsnr (bare når kolonnen er NULL). Det er en
påstand til dette skriptet har bekreftet det: spørringen under tar med bygg med
bygningsnr og matrikkel_match 'ikke_forsokt'/'ikke_funnet'. Per rad med
kildenummer gjøres dette først, før adressen:
  1. Direkte bygningsoppslag:
       BygningService.findBygning          bygningsnummer -> BygningId (uten kommune)
       StoreService.getObject(byggId)      -> Bygning; bygningsnummeret må være det
                                              vi spurte om
     Ved bekreftelse skrives bygningsnr/bygningstype/bra_m2/antall_etasjer med
     matrikkel_match='bygningsnr', også når adressen ikke lar seg løse, og
     bygningsoppslaget via adressen (kjeden over) hoppes over. Posisjon skrives
     ikke her (den kommer fra adressen): et feil kildetall kunne ellers satt
     bygget et annet sted i landet. Finnes ikke nummeret, eller svaret ikke
     stemmer, logges avvik og raden går videre til adressekjeden over.
  2. Adressen fra det bekreftede bygget:
       AdresseService.findAdresserForBygg  ByggId -> AdresseId-er (Vegadresse eller
                                              Matrikkeladresse, via Bruksenhet)
     Bare den Vegadressen som har samme gatenavn, husnummer og bokstav som
     kildens adresse brukes (nøyaktig ett treff); resten kastes. MatrikkelAPI har
     ingen markering av hovedadresse, så kildens adresse avgjør. Gir det ikke ett
     treff (eller kallet feiler), slås adresseteksten opp som før; årsaken følger
     med avviket hvis adressen til slutt ikke lar seg løse. Matrikkelenheten og
     resten av adresseberikelsen (gate, husnr, bokstav, posisjon,
     geokoding='matrikkel') bruker samme steg som ved tekstsøk.
adresse.adressetekst er fortsatt kildens tekst. Det finnes ennå ingen kolonne som
sier at adressen ble funnet via bygget; geokoding='matrikkel' sier bare at gate,
husnr og posisjon kommer fra Matrikkelen.

Reserveveien i adressekjeden (når steg 1 ikke bekreftet nummeret): gir adressen
flere bygg, og raden har et kildenummer, velges det kandidatbygget som har samme
bygningsnummer (nøyaktig ett treff). Gir adressen ett bygg med et annet nummer
enn kildens, logges avviket med begge verdier og Matrikkelens verdi skrives
('adresse'; Matrikkelen vinner på identitet).

Rekkefølgen bygningsnr -> gnr/bnr -> adresse er delvis implementert: gnr/bnr fra
kilden brukes ikke ennå. findBygning og findAdresserForBygg er lest fra
Kartverkets dokumentasjon og skjema, ikke kjørt mot MatrikkelAPI. Feltet er
foreløpig tynt fylt i kildene.

Skriver matrikkelinfo (upsert, knyttet til adressens bygg via bygning_id,
gnr/bnr/fnr/snr) uansett geokodingsstatus - billig og idempotent, så det
forsøkes for enhver adresse vi klarer å slå opp. Skriver ved adresse-treff
som fortsatt mangler geokoding: i tillegg gate (upsert) og adresse (gate_id,
husnr, bokstav, posisjon, geokoding='matrikkel' - den autoritative statusen,
se schema_kjerne_dokumentasjon.md). Skriver ved bygningstreff (uavhengig av
om adressen var løst fra før): bygning.bygningsnr/bygningstype/bra_m2/
antall_etasjer/posisjon (via adressen) eller, ved direkte treff på kildens
bygningsnr, de samme feltene uten posisjon og med matrikkel_match='bygningsnr'.

Bruker bare Pythons innebygde bibliotek. Leser brukernavn/passord fra
miljøvariablene MATRIKKEL_BRUKER / MATRIKKEL_PASSORD (se etl/dev/check_matrikkel_auth.py)
- ALDRI skriv disse verdiene til skjerm, logg eller fil. MATRIKKEL_MILJO velger
miljø: "test" (prodtest.matrikkel.no, standard) eller "prod" (matrikkel.no).

Bruk (kjøres etter jobs/build.py, og etter hver kjøring av jobs/sync.py, så nye bygg
får posisjon):

    docker exec portico_masterdb psql -U postgres -d masterdb -tA -F'|' -c "
        SELECT a.id, a.adressetekst, a.postnummer, a.poststed, k.kommunenr,
               a.bygning_id, a.geokoding, a.gate_id, a.husnr, a.bokstav, g.adressekode,
               b.bygningsnr
        FROM adresse a
        JOIN bygning b ON b.id = a.bygning_id
        JOIN kommune k ON k.id = b.kommune_id
        LEFT JOIN gate g ON g.id = a.gate_id
        WHERE a.er_hovedadresse AND a.geokoding <> 'manuell' AND a.adressetekst IS NOT NULL
          AND (a.geokoding = 'ukjent' OR b.bygningsnr IS NULL
               OR NOT EXISTS (SELECT 1 FROM matrikkelinfo m WHERE m.bygning_id = b.id)
               OR (b.bygningsnr IS NOT NULL AND b.matrikkel_match IN ('ikke_forsokt','ikke_funnet')));
    " > etl/ut/adresser_a_matrikkelsoke.txt

    (cd etl && python3 -m jobs.geocode) < etl/ut/adresser_a_matrikkelsoke.txt > etl/ut/matrikkel.sql

    docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/matrikkel.sql

De fire OR-leddene gjør skriptet trygt å kjøre på nytt: en rad som har
bygningsnummer (bekreftet), løst adresse og matrikkelinfo-lenke er ikke med i spørringen.
Men utvalget gjøres per rad, ikke per ledd, og skriptet vet ikke hvilket ledd
som utløste raden. Kommer en rad med, gjøres derfor alltid adresseoppslaget,
matrikkelinfo-steget og bygningsoppslaget; bare adresseberikelsen (gate,
posisjon, geokoding='matrikkel') er betinget av at adressen er 'ukjent'.
Et bygg som kom med bare fordi matrikkelinfo mangler, får altså også
bygningsnr/bygningstype/bra_m2/antall_etasjer oppdatert på nytt.

En adresse som ikke lar seg løse logges i synk_avvik og blir stående som
'ukjent' (og er med i neste kjøring). Det finnes ingen egen 'feilet'-status.

Prinsipp: ett eksakt treff brukes - på husnummer for adresse, på bygg-id for
bygning, og på gatenavn+husnummer+bokstav for en adresse hentet via bygget.
Null treff, flere treff, eller manglende husnummer i kildedata logges som
avvik og gjettes ikke på.

Skriptet inngår ikke i jobs/sync.py: den nattlige kjøringen trigger geocode som
en egen jobb etter synk, og en synk trigget alene geokoder ikke.
"""
import re
import sys

from lib.matrikkel import (
    BASE_URL, MatrikkelFeil, finn_adresse_ider_for_veg, finn_adresser_for_bygg,
    finn_bygg_id_for_bygningsnr, finn_bygg_ider_for_adresse, finn_kommune_id,
    finn_veg_ider, finn_vegadresse_direkte, hent_bygning, hent_matrikkelenhet,
    hent_veg, hent_vegadresser,
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


def _norm(s):
    return " ".join((s or "").casefold().split())


def adresse_fra_bygg(bygg_id, gatenavn, nummer, bokstav, spor, veg_cache):
    """Adressene Matrikkelen har for et bekreftet bygg (findAdresserForBygg), filtrert
    på kildens adresse: samme gatenavn, husnummer og bokstav. Returnerer
    Vegadresse-objektet ved nøyaktig ett treff, ellers None (ingenting gjettes;
    MatrikkelAPI har ingen markering av hovedadresse). Årsaken legges i spor, som
    følger med avviket hvis adressen til slutt ikke lar seg løse. Kan kaste
    MatrikkelFeil."""
    adresser = finn_adresser_for_bygg(bygg_id)
    spor["adresser_for_bygg"] = adresser
    ider = [a["id"] for a in adresser if a["type"] in (None, "VegadresseId")]
    kandidater = [v for v in hent_vegadresser(ider) if v["veg_id"] and v["nummer"] is not None]
    treff = []
    for v in kandidater:
        if v["nummer"] != nummer or v["bokstav"] != bokstav:
            continue
        veg = veg_cache.get(v["veg_id"])
        if veg is None:
            veg = veg_cache[v["veg_id"]] = hent_veg(v["veg_id"])
        if _norm(veg["adressenavn"]) == _norm(gatenavn):
            treff.append(v)
    spor["antall_vegadresser_for_bygg"] = len(kandidater)
    spor["antall_treff_pa_bygg"] = len(treff)
    return treff[0] if len(treff) == 1 else None


def bygning_fra_bygningsnr(bygning_id, kilde_bnr, adressetekst, spor):
    """Direkte oppslag av kildens bygningsnr i Matrikkelen (findBygning). Returnerer
    (SQL, ByggId eller None). ByggId satt = bekreftet = nøyaktig ett bygg, og hent_bygning gir samme
    bygningsnummer: da skrives faktaene med matrikkel_match='bygningsnr'. Ellers
    logges et avvik og kjeden går videre (adresse). Posisjon skrives ikke her: et
    feil tall fra kilden kunne ellers satt bygget et helt annet sted i landet; den
    kommer fra adressen."""
    nokler = dict(kilde="matrikkel-bygning", samling="bygning", avvikstype="annet", nokkelfelt="bygning_id")
    try:
        bid = finn_bygg_id_for_bygningsnr(kilde_bnr)
        info = hent_bygning(bid) if bid else None
    except MatrikkelFeil as e:
        return logg_matrikkel(bygning_id, f"source bygningsnr {kilde_bnr}: MatrikkelAPI lookup failed: " + str(e)[:200],
                              spor, **nokler), None
    if info is None:
        return logg_matrikkel(bygning_id, f"source bygningsnr {kilde_bnr} not found in the Matrikkel for {adressetekst}",
                              spor, **nokler), None
    if info["bygningsnr"] != kilde_bnr:
        spor["bygningsnr_matrikkel"] = info["bygningsnr"]
        return logg_matrikkel(bygning_id, f"source bygningsnr {kilde_bnr}: the Matrikkel returned a building numbered "
                              f"{info['bygningsnr']}; not used", spor, **nokler), None
    spor["bygning_via_bygningsnr"] = info
    sql = (
        f"UPDATE bygning SET "
        f"bygningsnr = {info['bygningsnr']}, "
        f"bygningstype = {q(info['bygningstype_kode'])}, "
        f"bra_m2 = {info['bra_m2'] if info['bra_m2'] is not None else 'NULL'}, "
        f"antall_etasjer = {info['antall_etasjer'] if info['antall_etasjer'] is not None else 'NULL'}, "
        f"matrikkel_match = 'bygningsnr' "
        f"WHERE id = {int(bygning_id)};\n"
    )
    return i_blokk_matrikkel(bygning_id, sql, spor, kilde=nokler["kilde"], samling=nokler["samling"],
                              nokkelfelt=nokler["nokkelfelt"]), bid


def main():
    out = sys.stdout
    out.write("BEGIN;\n\n")
    out.write(f"CALL registrer_kildeuttrekk('matrikkel',{q(BASE_URL)},NULL);\n\n")

    kommune_id_cache: dict[str, int] = {}
    veg_cache: dict[int, dict] = {}
    adresser_for_veg_cache: dict[int, list[dict]] = {}

    antall_ok = antall_feilet = antall_bygg_ok = antall_bygg_feilet = antall_matrikkelinfo_ok = 0
    antall_bygningsnr_treff = 0

    for rad in sys.stdin:
        rad = rad.rstrip("\n")
        if not rad:
            continue
        felt = rad.split("|", 11)
        if len(felt) != 12:
            continue
        (adresse_id, adressetekst, postnummer, poststed, kommunenummer,
         bygning_id, geokoding, gate_id, husnr_db, bokstav_db, adressekode_db, bygningsnr_db) = felt
        adressetekst = adressetekst.strip()
        # bygning.bygningsnr as the database has it: a source claim (cadastral_references)
        # still waiting for verification, or a number the Matrikkel gave earlier.
        kilde_bnr = int(bygningsnr_db) if bygningsnr_db.strip().isdigit() else None
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

        # First level of the cascade: the source's bygningsnr, resolved directly. Done
        # before the address, so a building with an unresolvable address still gets it.
        bygg_via_nr = None   # ByggId when the source number was confirmed
        if kilde_bnr is not None:
            bnr_sql, bygg_via_nr = bygning_fra_bygningsnr(bygning_id, kilde_bnr, adressetekst, spor)
            out.write(bnr_sql)
            if bygg_via_nr:
                antall_bygningsnr_treff += 1
                antall_bygg_ok += 1

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

            if bygg_via_nr and nummer is not None:
                # The building is confirmed: take its address from the Matrikkel, but only the
                # one that matches the source's address (street, number, letter).
                try:
                    v = adresse_fra_bygg(bygg_via_nr, gatenavn, nummer, bokstav, spor, veg_cache)
                except MatrikkelFeil as e:
                    spor["feil_adresser_for_bygg"] = str(e)[:200]
                if v is not None:
                    spor["via"] = "bygningsnr"

            if v is None and adressekode_db:
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
        if geokoding == "ukjent":
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
                # A source bygningsnr still waiting for verification keeps matrikkel_match
                # ('ikke_forsokt'), so the building step below verifies it; a confirmed
                # 'bygningsnr' match is never downgraded.
                f"matrikkel_match = CASE WHEN matrikkel_match = 'bygningsnr' "
                f"OR (matrikkel_match = 'ikke_forsokt' AND bygningsnr IS NOT NULL) "
                f"THEN matrikkel_match ELSE 'adresse' END, "
                f"posisjon = COALESCE(posisjon, ST_SetSRID(ST_MakePoint({lon},{lat}),4326)::geography) "
                f"WHERE id = {int(bygning_id)};\n"
            )

            out.write(i_blokk_matrikkel(adresse_id, sql, spor))
            antall_ok += 1

        if bygg_via_nr:
            continue   # building already confirmed through its bygningsnr

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

        match = "adresse"
        if kilde_bnr is not None and len(bygg_ider) > 1:
            # Several buildings at the address: pick the one whose bygningsnummer equals
            # the source's number. Exactly one match is used; anything else is not guessed.
            spor["bygningsnr_kilde"] = kilde_bnr
            try:
                kandidat_info = [hent_bygning(bid) for bid in bygg_ider]
            except MatrikkelFeil as e:
                out.write(logg_matrikkel(bygning_id, "MatrikkelAPI-kall feilet (bygningsobjekt, kandidater): " + str(e)[:200], spor,
                               kilde="matrikkel-bygning", samling="bygning", avvikstype="annet",
                               nokkelfelt="bygning_id"))
                out.write(ikke_funnet_sql)
                antall_bygg_feilet += 1
                continue
            spor["kandidat_bygningsnr"] = [k["bygningsnr"] for k in kandidat_info]
            treff = [k for k in kandidat_info if k["bygningsnr"] == kilde_bnr]
            if len(treff) != 1:
                grunn = ("matches none of" if not treff else f"matches {len(treff)} of")
                out.write(logg_matrikkel(bygning_id, f"source bygningsnr {kilde_bnr} {grunn} the {len(bygg_ider)} "
                               f"candidate buildings for adresse {adressetekst}", spor,
                               kilde="matrikkel-bygning", samling="bygning", avvikstype="annet",
                               nokkelfelt="bygning_id"))
                out.write(ikke_funnet_sql)
                antall_bygg_feilet += 1
                continue
            info = treff[0]
            match = "bygningsnr"
            antall_bygningsnr_treff += 1
        else:
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

            if kilde_bnr is not None:
                if info["bygningsnr"] == kilde_bnr:
                    match = "bygningsnr"
                    antall_bygningsnr_treff += 1
                else:
                    # Matrikkel wins on identity: its number is written below, the
                    # disagreement is logged with both values.
                    spor["bygningsnr_kilde"] = kilde_bnr
                    spor["bygningsnr_matrikkel"] = info["bygningsnr"]
                    out.write(logg_matrikkel(bygning_id, f"source bygningsnr {kilde_bnr} differs from the Matrikkel's "
                                   f"{info['bygningsnr']} for adresse {adressetekst}; Matrikkel value written", spor,
                                   kilde="matrikkel-bygning", samling="bygning", avvikstype="annet",
                                   nokkelfelt="bygning_id"))

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
            f"matrikkel_match = {q(match)}, "
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
    print(f"bygning - bygningsnr bekreftet mot kildens cadastral_references: {antall_bygningsnr_treff}", file=sys.stderr)
    print(f"bygning - matrikkelinfo (gnr/bnr) lenket: {antall_matrikkelinfo_ok}", file=sys.stderr)


if __name__ == "__main__":
    main()
