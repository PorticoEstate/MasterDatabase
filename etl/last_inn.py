#!/usr/bin/env python3
"""
Laster data fra Aktiv kommune inn i masterdatabasen.

Bruker bare Pythons innebygde bibliotek (urllib, json, re) - ingen "pip install"
er nødvendig. Skriptet gjør ingenting mot databasen selv; det skriver SQL-tekst
til standard-ut, som du deretter sender til Postgres. Det gjør at du kan se
nøyaktig hva som skal skje før noe faktisk endres.

Bruk:
    python3 etl/last_inn.py bergen > etl/ut/bergen.sql
    docker exec -i portico_masterdb psql -U postgres -d OppdatertDatabase < etl/ut/bergen.sql

    python3 etl/last_inn.py alle > etl/ut/alle.sql
    docker exec -i portico_masterdb psql -U postgres -d OppdatertDatabase < etl/ut/alle.sql

Se etl/README.md for full forklaring.

Kjent forenkling: kommune_id settes her fra hvilken Aktiv kommune-instans
ressursen kommer fra (f.eks. "bergen" -> kommunenr 4601). Det er riktig for
alle de 12 instansene vi kjenner i dag, som hver betjener nøyaktig én kommune.
Skjemaet (schema_kjerne.sql) tillater at en instans betjener flere kommuner
via instans_kommune-tabellen; den dagen det faktisk skjer, må kommune_id i
stedet utledes fra en geokodet adresse. Se db/schema_kjerne_dokumentasjon.md.
"""
import html
import json
import re
import sys
import unicodedata
import urllib.request

KOMMUNER = {
    "bergen": ("4601", "Bergen", "Vestland"),
    "stavanger": ("1103", "Stavanger", "Rogaland"),
    "baerum": ("3201", "Bærum", "Akershus"),
    "oygarden": ("4626", "Øygarden", "Vestland"),
    "narvik": ("1806", "Narvik", "Nordland"),
    "afjord": ("5058", "Åfjord", "Trøndelag"),
    "averoy": ("1554", "Averøy", "Møre og Romsdal"),
    "gamvik": ("5628", "Gamvik", "Finnmark"),
    "inderoy": ("5053", "Inderøy", "Trøndelag"),
    "nordreisa": ("5540", "Nordreisa", "Troms"),
    "oksnes": ("1868", "Øksnes", "Nordland"),
    "sogndal": ("4640", "Sogndal", "Vestland"),
}

# Normalisert kildenavn -> kode i vårt eget kodeverk (lokaletype/aktivitet/
# fasilitet, seedet i schema_kjerne.sql). Navn som ikke finnes her, lastes inn
# i kildekode uendret, men får ingen kartlegging - de dukker opp i
# v_ukartlagte_kildekoder og må kobles manuelt.
LOKALETYPE = {
    "gymsal": "GYMSAL", "idrettshall": "IDRETTSHALL", "idrettshall privateid": "IDRETTSHALL",
    "idrettsanlegg": "IDRETTSHALL", "idrettsanlegg privateid": "IDRETTSHALL",
    "svommehall": "SVOMMEANLEGG", "svommeanlegg": "SVOMMEANLEGG", "basseng": "SVOMMEANLEGG",
    "basseng symjehall": "SVOMMEANLEGG",
    "ishall": "ISHALL", "utendors isbane": "ISHALL", "kunstisbane": "ISHALL",
    "friidrettsanlegg": "FRIIDRETTSANLEGG", "friidrettsbane": "FRIIDRETTSANLEGG",
    "friidrettshall": "FRIIDRETTSANLEGG", "kastfelt grus": "FRIIDRETTSANLEGG",
    "kastfelt gress": "FRIIDRETTSANLEGG", "sprintstripe": "FRIIDRETTSANLEGG",
    "kunstgressbane": "FOTBALLBANE", "kunstgrasbane": "FOTBALLBANE",
    "gressbane": "FOTBALLBANE", "grasbane": "FOTBALLBANE", "grusbane": "FOTBALLBANE",
    "ballbinger": "BALLBANE", "sandvolleyballbane": "BALLBANE", "bordtennis": "BALLBANE",
    "tennisbane": "TENNISANLEGG", "tennishall": "TENNISANLEGG",
    "styrkerom": "STYRKEROM", "vektlofterlokale": "STYRKEROM",
    "styrkeloftlokale": "STYRKEROM", "apparatsal": "STYRKEROM", "oppvarmingsrom": "STYRKEROM",
    "kampsportrom": "KAMPSPORTROM", "kampsportmatte": "KAMPSPORTROM",
    "klatrevegg": "KLATREANLEGG", "turnomrade": "TURNANLEGG",
    "skateanlegg": "SKATEANLEGG", "skatepark": "SKATEANLEGG",
    "skytebane skytehall": "SKYTEBANE", "standplass": "SKYTEBANE",
    "sjosportsanlegg": "SJOSPORTANLEGG", "garderobe": "GARDEROBE",

    "konsertsal": "KONSERTSAL", "kultursal": "KONSERTSAL",
    "scene": "SCENE", "utendorsscene": "UTESCENE",
    "auditorium": "AUDITORIUM", "foredragssal": "AUDITORIUM",
    "ovingsrom": "OVINGSROM", "ovingslokale": "OVINGSROM", "musikkrom": "OVINGSROM",
    "musikk og danserom": "OVINGSROM",
    "dansesal": "DANSESAL", "lydstudio": "LYDSTUDIO",
    "utstillingslokale": "UTSTILLINGSLOKALE", "ateliet": "UTSTILLINGSLOKALE",
    "bibliotek": "BIBLIOTEK", "foaje": "FOAJE",

    "klasserom": "KLASSEROM", "lite undervisningsrom": "KLASSEROM",
    "stort undervisningsrom": "KLASSEROM", "kursrom": "KLASSEROM",
    "grupperom": "GRUPPEROM", "prosjektrom": "GRUPPEROM",
    "moterom": "MOTEROM", "motelokale": "MOTEROM", "konferanserom": "MOTEROM",
    "samhandlingslab": "MOTEROM", "datarom": "DATAROM", "aula": "AULA",

    "sloydsal": "SLOYDSAL", "kunst og designverksted": "KUNSTVERKSTED",
    "kunst og handverk": "KUNSTVERKSTED", "kreativt verksted": "KUNSTVERKSTED",
    "systue": "SYSTUE", "multimediaverksted": "MEDIEVERKSTED",
    "streaming": "MEDIEVERKSTED", "frisorsalong": "FRISORSALONG",

    "selskapslokale": "SELSKAPSLOKALE", "selskapslokale storsal": "SELSKAPSLOKALE",
    "forsamlingslokale": "FORSAMLINGSLOKALE",
    "forsamlingslokale privateid": "FORSAMLINGSLOKALE",
    "seremonirom": "SEREMONIROM", "sermonirom": "SEREMONIROM",
    "bursdagslokale": "BURSDAGSLOKALE", "barnebursdag": "BURSDAGSLOKALE",
    "arrangementsarena": "ARRANGEMENTSARENA", "arrangementslokale": "ARRANGEMENTSARENA",
    "torgplass": "TORGPLASS", "moteplass": "TORGPLASS",

    "kjokken": "KJOKKEN", "kantine": "KANTINE",
    "kantine kunnskapshjornet": "KANTINE", "kantine kunnskapshjorne": "KANTINE",
    "kafe": "KAFE", "kiosk minkjokken": "KAFE", "sondagskafe": "KAFE",
    "bevertning": "KAFE",

    "allaktivitetshus": "ALLAKTIVITETSHUS", "aktivitetshus": "ALLAKTIVITETSHUS",
    "aktivitetsrom": "AKTIVITETSROM", "aktivitetssal": "AKTIVITETSROM",
    "flerbruksrom": "AKTIVITETSROM", "fellesrom": "AKTIVITETSROM",
    "ungdomslokale": "UNGDOMSLOKALE", "dagsenter": "DAGSENTER", "miljostue": "DAGSENTER",

    "friluftsomrade": "FRILUFTSOMRAADE", "utendorsomrade": "UTEOMRAADE",
    "uterom uteomrade": "UTEOMRAADE", "turveier": "TURVEI",
    "gapahuk": "GAPAHUK", "balpanne": "GAPAHUK",

    "overnatting": "OVERNATTINGSROM", "beboerrom": "BEBOERROM",
    "ovingsleilighet": "OVINGSLEILIGHET",

    "kontor": "KONTOR", "arbeidsplasser": "KONTOR", "butikklokale": "BUTIKKLOKALE",
    "frilager": "LAGER", "lokale": "GENERELT_LOKALE", "ovrige lokalar": "GENERELT_LOKALE",
    "anlegg": "GENERELT_LOKALE",

    "sykler": "SYKKEL", "el sykler": "SYKKEL", "kano kajakk": "KANO_KAJAKK",
    "kano": "KANO_KAJAKK", "kajakk": "KANO_KAJAKK", "fiskestengar": "FISKEUTSTYR",
    "redningsvestar": "REDNINGSVEST", "lydanlegg": "LYDANLEGG", "utstyr": "ANNET_UTSTYR",
}

IKKE_RELEVANT = {
    "stengt", "fiktivt rom", "kantinebidrag", "inkludering", "sosial aktivitet",
    "kvitsoygata 3", "judaberg innbyggertorg", "mostun natursenter",
    # Uspesifiserte samlekategorier og administrative tilstander fra
    # aktivitetslistene. NB: ordboken deles av alle kodetyper, så bare navn
    # som ikke er gyldige i noen kodetype hører hjemme her.
    "annet", "x annet", "andre", "generelt", "forslag", "gi bort",
    "slettet utgatt", "vedlikehold", "stengt pga ferie eller arrangement",
    "stengt pga vedlikehold reperasjon av utstyr", "sommerstengt sommertrening",
    "utlansordningen er ikke apen",
    "tiden er ledig sykkelen reserveres fra forrige ledige torsdag",
    "walk and talk test",
}

FASILITET = {
    "garderobe": "GARDEROBE", "dusj": "DUSJ", "toalett": "TOALETT", "wc": "TOALETT",
    "wc toalett": "TOALETT",
    "hc toalett": "HC_TOALETT", "teleslynge": "TELESLYNGE", "heis": "HEIS",
    "projektor": "PROSJEKTOR", "prosjektor": "PROSJEKTOR", "lydanlegg": "LYDANLEGG",
    "musikkanlegg m blatann": "LYDANLEGG", "mikrofon": "MIKROFON",
    "flygel": "FLYGEL", "piano": "FLYGEL", "parkettgulv": "PARKETTGULV",
    "tribune": "TRIBUNE", "kiosk": "KIOSK", "kjokken": "KJOKKEN",
    "parkering": "PARKERING", "balpanne": "BAALPLASS", "whiteboard": "WHITEBOARD",
    "flomlys": "FLOMLYS", "wifi": "WIFI",
}

# Kartleggingsregel: mest spesifikke kode vi har, ellers rotkategorien
# (IDRETT, KULTUR, ...). Nettsiden filtrerer på kategoriene, aldri på
# rånavnene, så en grov plassering er mye bedre enn ingen. Navn som
# fortsatt mangler her forblir ukartlagt og dukker opp i
# v_ukartlagte_kildekoder for manuell vurdering.
AKTIVITET = {
    # --- Idrett: spesifikke grener ---
    "fotball": "FOTBALL", "fotballbane": "FOTBALL", "futsal": "FOTBALL",
    "innefotball": "FOTBALL",
    "handball": "HANDBALL", "minihandball": "HANDBALL", "sandhandball": "HANDBALL",
    "basketball": "BASKETBALL",
    "volleyball": "VOLLEYBALL", "sandvolleyball": "VOLLEYBALL",
    "turn": "TURN", "gymnastikk": "TURN", "gymnastikk og turn": "TURN",
    "kampsport": "KAMPSPORT", "boksing": "KAMPSPORT", "bryting": "KAMPSPORT",
    "judo": "KAMPSPORT", "ju jitsu": "KAMPSPORT", "karate": "KAMPSPORT",
    "kickboksing": "KAMPSPORT", "taekwondo": "KAMPSPORT", "fekting": "KAMPSPORT",
    "svomming": "SVOMMING", "svommehall": "SVOMMING", "symjehall": "SVOMMING",
    "stuping": "SVOMMING", "vannpolo": "SVOMMING", "undervannsrugby": "SVOMMING",
    "dykking": "SVOMMING",
    "friidrett": "FRIIDRETT",
    "ishockey": "ISHOCKEY", "bandy": "ISHOCKEY", "skoyter": "ISHOCKEY",
    "kunstlop": "ISHOCKEY", "hurtiglop": "ISHOCKEY", "curling": "ISHOCKEY",
    "klatring": "KLATRING", "klartring": "KLATRING",
    "styrketrening": "STYRKETRENING", "vektlofting": "STYRKETRENING",
    "styrkelofting": "STYRKETRENING", "styrkeloft": "STYRKETRENING",
    "tennis": "TENNIS",
    "skyting": "SKYTING", "bueskyting": "SKYTING", "leirdueskyting": "SKYTING",
    "sykling": "SYKLING", "leie av lastesykkel": "SYKLING",

    # --- Idrett: rotnivå (ingen egen kode ennå) ---
    "idrett": "IDRETT", "annen idrett": "IDRETT", "andre idretter": "IDRETT",
    "idrettsaktiviteter": "IDRETT", "sport og idrett": "IDRETT",
    "ballsport": "IDRETT", "egenorganisert": "IDRETT",
    "badminton": "IDRETT", "bordtennis": "IDRETT", "innebandy": "IDRETT",
    "bandy inne": "IDRETT", "squash": "IDRETT", "orientering": "IDRETT",
    "cheerleading": "IDRETT", "drill": "IDRETT", "sportsdrill": "IDRETT",
    "skisport": "IDRETT", "ski": "IDRETT", "amerikansk fotball": "IDRETT",
    "rugby": "IDRETT", "lacrosse": "IDRETT", "cricket": "IDRETT",
    "baseball": "IDRETT", "baseball softball": "IDRETT", "golf": "IDRETT",
    "boccia": "IDRETT", "bowls": "IDRETT", "e sport": "IDRETT",
    "hestesport": "IDRETT", "riding": "IDRETT", "motorsport": "IDRETT",
    "luftsport": "IDRETT", "hundesport": "IDRETT", "rollerderby": "IDRETT",
    "skating": "IDRETT", "paintball": "IDRETT",
    "roing": "IDRETT", "seiling": "IDRETT", "seilsport": "IDRETT",
    "sjosport": "IDRETT", "vannsport": "IDRETT",
    "trim": "IDRETT", "yoga": "IDRETT",
    "bedriftsidrett": "IDRETT", "fleridrettslag": "IDRETT",
    "fleiridrettslag": "IDRETT", "idrettskrets sarforbund": "IDRETT",
    "apen hall": "IDRETT", "gymsal": "IDRETT", "idrettshall": "IDRETT",

    # --- Kultur: spesifikke grener ---
    "dans": "DANS", "dansing": "DANS", "dans trening": "DANS",
    "musikk": "MUSIKK", "musikk korps": "MUSIKK", "korps": "MUSIKK",
    "korps og orkester": "MUSIKK", "band": "MUSIKK", "musikk og dans": "MUSIKK",
    "kor": "KOR", "kor og sang": "KOR",
    "teater": "TEATER", "teater og revy": "TEATER",
    "teaterforestilling": "TEATER", "teater og scenekunst": "TEATER",
    "kunst handtverk media": "KUNST_HANDVERK", "kunst handverk og media": "KUNST_HANDVERK",
    "kunst og handverk": "KUNST_HANDVERK", "kreativt verksted": "KUNST_HANDVERK",
    "kreativt verksted og prosesser": "KUNST_HANDVERK",
    "malegruppe": "KUNST_HANDVERK", "foto": "KUNST_HANDVERK", "video": "KUNST_HANDVERK",

    # --- Kultur: rotnivå ---
    "kultur": "KULTUR", "kulturlokaler": "KULTUR",
    "kulturlokaler formidling og oving": "KULTUR",
    "kulturlokaler oving og verksteder": "KULTUR",
    "kulturaktiviteter": "KULTUR", "kulturarrangement": "KULTUR",
    "kulturhus": "KULTUR", "kulturskolen": "KULTUR", "kino": "KULTUR",
    "konsert": "KULTUR", "galleri": "KULTUR", "museum": "KULTUR",
    "utstilling": "KULTUR", "litteratur litteraturformidling": "KULTUR",
    "bibliotek": "KULTUR", "ovingsrom": "KULTUR",
    "ovingslokaler og verksteder": "KULTUR",
    "formidlingsarena og forsamlingslokaler": "KULTUR",
    "kulturvern og sogelag": "KULTUR", "kulturvern og historie": "KULTUR",
    "kulturvern og historielag": "KULTUR", "buekorps": "KULTUR",
    "festival": "KULTUR", "festivaler monstringer": "KULTUR",
    "festivaler og monstringer": "KULTUR", "festivaler monstringar": "KULTUR",
    "disko": "KULTUR",

    # --- Opplæring og kurs ---
    "skole": "OPPLARING", "skular": "OPPLARING", "skule": "OPPLARING",
    "skule oppvekst": "OPPLARING", "vgs": "OPPLARING", "ntnu": "OPPLARING",
    "barnehage": "OPPLARING", "barnehager": "OPPLARING",
    "undervisning": "OPPLARING", "undervisning opplaring": "OPPLARING",
    "kurs": "OPPLARING", "dataundervisning": "OPPLARING",
    "klasseromsundervisning": "OPPLARING", "leksegruppe": "OPPLARING",
    "studiegrupper": "OPPLARING", "sprakcafe": "OPPLARING",
    "forelesning": "OPPLARING", "foredrag": "OPPLARING",
    "naturskole": "OPPLARING", "voksenopplaringssenteret": "OPPLARING",

    # --- Møte og konferanse ---
    "moterom": "MOTE", "moter": "MOTE", "mote": "MOTE", "sma moter": "MOTE",
    "apne moter": "MOTE", "styremoter": "MOTE", "motevirksomhet": "MOTE",
    "moteaktivitet": "MOTE", "mote presentasjon": "MOTE",
    "presentasjoner": "MOTE", "informasjons moter": "MOTE",
    "samlinger": "MOTE", "gruppearbeid": "MOTE", "samtaler": "MOTE",
    "annet idrett moterom": "MOTE", "annet kultur moterom": "MOTE",
    "idrett moterom": "MOTE", "kulturlokalar moterom": "MOTE",
    "drop in arbeidsplasser": "MOTE",

    # --- Privat arrangement ---
    "privat arrangement": "PRIVAT", "privat lukket arrangement": "PRIVAT",
    "barnebursdag": "PRIVAT", "barnebursdag 3 12 ar": "PRIVAT",
    "barnebursdag 3 16 ar": "PRIVAT", "bryllup": "PRIVAT", "dap": "PRIVAT",
    "konfirmasjon": "PRIVAT", "vielser": "PRIVAT", "seremonier": "PRIVAT",
    "livsnoytral seremonirom": "PRIVAT", "personlig markering": "PRIVAT",
    "annet personlig markering": "PRIVAT", "familiefest": "PRIVAT",
    "klassefest": "PRIVAT", "selskapsarrangement": "PRIVAT",

    # --- Frivillighet og lag (leietakerkategorier fra kilden) ---
    "grendalag": "FRIVILLIGHET", "grendalag velforening": "FRIVILLIGHET",
    "humanitare organiasjoner": "FRIVILLIGHET",
    "humanitare organisasjoner": "FRIVILLIGHET",
    "humanitare organisasjonar": "FRIVILLIGHET",
    "interesseorganiasjonar": "FRIVILLIGHET",
    "interesseorganisasjon": "FRIVILLIGHET",
    "interesseorganisasjonar": "FRIVILLIGHET",
    "interesseorganisasjoner": "FRIVILLIGHET",
    "meningheter og trossamfunn": "FRIVILLIGHET",
    "menigheter og trossamfunn": "FRIVILLIGHET",
    "menigheter og trosamfunn": "FRIVILLIGHET",
    "pensjonistforening": "FRIVILLIGHET", "politisk organisasjon": "FRIVILLIGHET",
    "frivillighet og organisasjonsaktiviteter": "FRIVILLIGHET",
    "frivilligsentral": "FRIVILLIGHET", "utenlandsk forening": "FRIVILLIGHET",
    "batforeingar": "FRIVILLIGHET", "vennelag gruppe": "FRIVILLIGHET",
    "hobbygrupper": "FRIVILLIGHET", "ungdomsklubb": "FRIVILLIGHET",
    "sosiale moteplassar": "FRIVILLIGHET", "sosiale moteplasser": "FRIVILLIGHET",
    "moteplass": "FRIVILLIGHET", "spedbarnsgruppe": "FRIVILLIGHET",
    "bil mc klubb": "FRIVILLIGHET", "foreldreutval": "FRIVILLIGHET",
    "sameie": "FRIVILLIGHET", "klesinnsamling": "FRIVILLIGHET",
    "sondagskafe": "FRIVILLIGHET",

    # --- Friluftsliv ---
    "speider": "SPEIDER", "speidar": "SPEIDER", "speidarar": "SPEIDER",
    "speider og friluftsliv": "SPEIDER",
    "friluftsliv": "FRILUFT", "tur": "FRILUFT", "turar": "FRILUFT",
    "turgruppe": "FRILUFT", "fisketurer": "FRILUFT", "jakt": "FRILUFT",
    "gapahuk": "FRILUFT", "grill balpanne": "FRILUFT", "teltplass": "FRILUFT",
    "sommerleir": "FRILUFT", "uteomrade": "FRILUFT", "overnatting": "FRILUFT",
    "kajakk": "FRILUFT", "kano kajakk": "FRILUFT", "kanopadling": "FRILUFT",

    # --- Arrangement og marked ---
    "arrangement": "ARRANGEMENT", "alle typer arrangement": "ARRANGEMENT",
    "off arrangement": "ARRANGEMENT", "annet offentlig arrangement": "ARRANGEMENT",
    "sirkus": "ARRANGEMENT", "tivoli": "ARRANGEMENT", "marked": "ARRANGEMENT",

    # --- Næring og kommersiell utleie ---
    "kommersiell utleie": "NAERING", "kommersiell utleige": "NAERING",
    "naring og kommersiell virksomhet": "NAERING", "bedrifter o l": "NAERING",
    "promotering": "NAERING", "profilering": "NAERING",
    "stand": "NAERING", "stand 2mx3m": "NAERING", "lokalmat": "NAERING",
    "torg": "NAERING", "pub": "NAERING", "kafe": "NAERING",

    # --- Internt kommunalt ---
    "internt bergen kommune": "INTERNT", "internt stavanger kommune": "INTERNT",
    "internt kommune": "INTERNT", "internt bruk kommune": "INTERNT",
    "kommune eige bruk": "INTERNT", "kommunal aktivitet": "INTERNT",
    "intern aktivitet": "INTERNT", "interne avdelinger": "INTERNT",
    "intern avdeling flyk": "INTERNT", "intern avdeling kulturskolen": "INTERNT",
    "intern avdeling voks": "INTERNT", "flykningekontoret": "INTERNT",
    "innbyggertorg": "INTERNT", "innbyggerbussen": "INTERNT",
    "administrasjonslokale": "INTERNT", "sykehjem": "INTERNT",
    "helsebygg": "INTERNT", "valg": "INTERNT", "politikk valgdag": "INTERNT",
    "annet internt i kommunen": "INTERNT",
}


def hent_json(url: str) -> dict:
    """Henter JSON fra url med Pythons innebygde urllib. Krever at Capgeminis
    CA-sertifikat er installert i systemets tillitslager (se etl/README.md)."""
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def rens(s):
    """Dobbel HTML-avkoding; kilden er escapet en gang for mye
    (f.eks. 'Rom 19 &amp;#40;219&amp;#41;' skal bli 'Rom 19 (219)')."""
    if s is None:
        return None
    s = html.unescape(html.unescape(str(s)))
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def norm(s):
    """Normaliserer et navn for oppslag i kartleggingstabellene ovenfor:
    små bokstaver, norske bokstaver til ascii, tegnsetting bort."""
    s = rens(s) or ""
    s = s.lower().replace("ø", "o").replace("æ", "a").replace("å", "a")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def q(v):
    """Gjør en Python-verdi til en trygg SQL-literal. NULL for tomme verdier,
    og escaper enkeltfnutter slik at f.eks. navn med apostrof ikke knekker SQL-en."""
    if v is None or v == "":
        return "NULL"
    return "'" + str(v).replace("'", "''").replace("\x00", "") + "'"


def generer_sql(slug: str, ut) -> None:
    knr, knavn, fylke = KOMMUNER[slug]
    kn = f"aktiv-kommune:{slug}"
    url = f"https://{slug}.aktiv-kommune.no/bookingfrontend/searchdataall"

    print(f"henter {url} ...", file=sys.stderr)
    d = hent_json(url)

    w = ut.write
    w("BEGIN;\n\n")

    w(f"-- {knavn}\n")
    w(f"INSERT INTO kommune (kommunenr,navn,fylkesnavn) "
      f"VALUES ({q(knr)},{q(knavn)},{q(fylke)}) ON CONFLICT (kommunenr) DO NOTHING;\n")
    w(f"INSERT INTO fagsystem_instans (kildenokkel,type,navn,base_url) "
      f"VALUES ({q(kn)},'booking',{q('Aktiv kommune ' + knavn)},{q('https://' + slug + '.aktiv-kommune.no')}) "
      f"ON CONFLICT (kildenokkel) DO NOTHING;\n")
    # Ekte mange-til-mange: en kommune kan ha flere instanser (booking, fdv,
    # sensor, ...), én instans kan betjene flere kommuner. uniq_kommune_
    # fagsystem_type hindrer to instanser av samme type for samme kommune.
    w(f"INSERT INTO kommune_fagsystem_instans (kommune_id,fagsystem_instans_id,type) "
      f"SELECT k.id, fi.id, fi.type FROM kommune k, fagsystem_instans fi "
      f"WHERE k.kommunenr={q(knr)} AND fi.kildenokkel={q(kn)} "
      f"ON CONFLICT (kommune_id,fagsystem_instans_id) DO NOTHING;\n\n")

    # --- kildekoder + automatisk forslag til kartlegging ---
    for kodetype, samling, tabell in [
        ("lokaletype", "resource_categories", LOKALETYPE),
        ("aktivitet", "activities", AKTIVITET),
        ("fasilitet", "facilities", FASILITET),
    ]:
        for rad in d.get(samling, []):
            navn = rens(rad["name"])
            if not navn:
                continue
            w(f"INSERT INTO kildekode (fagsystem_instans_id,kodetype,kode,navn) "
              f"SELECT id,{q(kodetype)},{q(rad['id'])},{q(navn)} "
              f"FROM fagsystem_instans WHERE kildenokkel={q(kn)} "
              f"ON CONFLICT (fagsystem_instans_id,kodetype,kode) DO UPDATE SET navn=EXCLUDED.navn, sist_sett=now();\n")
            n = norm(navn)
            if n in IKKE_RELEVANT:
                w(f"INSERT INTO kildekode_mapping (kildekode_id,status,merknad,kartlagt_av) "
                  f"SELECT kk.id,'ikke_relevant','Ikke en lokaletype','etl' "
                  f"FROM kildekode kk JOIN fagsystem_instans fi ON fi.id=kk.fagsystem_instans_id "
                  f"WHERE fi.kildenokkel={q(kn)} AND kk.kodetype={q(kodetype)} AND kk.kode={q(rad['id'])} "
                  f"ON CONFLICT (kildekode_id) DO NOTHING;\n")
            elif n in tabell:
                maalkol = {"lokaletype": "lokaletype_id", "aktivitet": "aktivitet_id",
                           "fasilitet": "fasilitet_id"}[kodetype]
                w(f"INSERT INTO kildekode_mapping (kildekode_id,{maalkol},status,kartlagt_av) "
                  f"SELECT kk.id,t.id,'godkjent','etl' "
                  f"FROM kildekode kk JOIN fagsystem_instans fi ON fi.id=kk.fagsystem_instans_id, {kodetype} t "
                  f"WHERE fi.kildenokkel={q(kn)} AND kk.kodetype={q(kodetype)} "
                  f"AND kk.kode={q(rad['id'])} AND t.kode={q(tabell[n])} "
                  f"ON CONFLICT (kildekode_id) DO NOTHING;\n")
    w("\n")

    # --- bygg + adresse ---
    bydel_per_bygg = {t["b_id"]: rens(t["name"]) for t in d.get("towns", [])}
    for b in d.get("buildings", []):
        navn = rens(b["name"]) or f"Bygg {b['id']}"
        w(f"INSERT INTO bygning (kommune_id,navn,bydel_navn,fagsystem_instans_id,ekstern_id,"
          f"hjemmeside,epost,telefon,apningstid_tekst) "
          f"SELECT k.id,{q(navn)},{q(bydel_per_bygg.get(b['id']))},fi.id,{q(b['id'])},"
          f"{q(rens(b.get('homepage')))},{q(rens(b.get('email')))},{q(rens(b.get('phone')))},"
          f"{q(rens(b.get('opening_hours')))} "
          f"FROM kommune k, fagsystem_instans fi "
          f"WHERE k.kommunenr={q(knr)} AND fi.kildenokkel={q(kn)} "
          f"ON CONFLICT DO NOTHING;\n")

        # Aktiv kommune gir ikke gatenavn og husnummer separat, bare hele
        # gateadressen i ett felt ("Breimyra 68 A"). adressetekst fylles fra
        # den; gatenavn/husnr/lat/lon står tomme til geokoding (et senere,
        # separat steg) fyller dem fra Kartverkets Adresse-API.
        gate = rens(b.get("street"))
        if gate:
            postnr = (b.get("zip_code") or "").strip()
            if postnr and not re.fullmatch(r"[0-9]{4}", postnr):
                w(f"INSERT INTO synk_avvik (kilde,samling,avvikstype,ekstern_id,detalj) "
                  f"VALUES ({q(kn)},'buildings','ugyldig_verdi',{q(b['id'])},"
                  f"{q('zip_code er ikke fire siffer: ' + postnr[:60])});\n")
                postnr = None
            w(f"INSERT INTO adresse (bygning_id,adressetekst,postnummer,poststed,"
              f"geokoding,er_hovedadresse) "
              f"SELECT b.id,{q(gate)},{q(postnr)},{q(rens(b.get('city')))},'ukjent',TRUE "
              f"FROM bygning b JOIN fagsystem_instans fi ON fi.id=b.fagsystem_instans_id "
              f"WHERE fi.kildenokkel={q(kn)} AND b.ekstern_id={q(b['id'])} "
              f"ON CONFLICT DO NOTHING;\n")
    w("\n")

    # --- ressurser ---
    kjente_bygg = {b["id"] for b in d.get("buildings", [])}
    bygg_for_ressurs = {}
    for br in d.get("building_resources", []):
        if br["building_id"] in kjente_bygg:
            bygg_for_ressurs.setdefault(br["resource_id"], br["building_id"])

    for r in d.get("resources", []):
        navn = rens(r["name"]) or f"Ressurs {r['id']}"
        beskr = None
        try:
            dj = json.loads(r.get("description_json") or "{}")
            beskr = rens(dj.get("no") or dj.get("nn") or dj.get("en"))
        except (ValueError, TypeError):
            pass
        bid = bygg_for_ressurs.get(r["id"])
        kap = r.get("capacity") or None
        bookbar = "FALSE" if r.get("deactivate_application") else "TRUE"
        aktiv = "TRUE" if r.get("active") else "FALSE"

        bygg_sel = (f"(SELECT b.id FROM bygning b JOIN fagsystem_instans f2 ON f2.id=b.fagsystem_instans_id "
                    f"WHERE f2.kildenokkel={q(kn)} AND b.ekstern_id={q(bid)})") if bid else "NULL"
        lt_sel = (f"(SELECT m.lokaletype_id FROM kildekode kk "
                  f"JOIN fagsystem_instans f3 ON f3.id=kk.fagsystem_instans_id "
                  f"JOIN kildekode_mapping m ON m.kildekode_id=kk.id AND m.status='godkjent' "
                  f"WHERE f3.kildenokkel={q(kn)} AND kk.kodetype='lokaletype' "
                  f"AND kk.kode={q(r.get('rescategory_id'))})")

        w(f"INSERT INTO ressurs (fagsystem_instans_id,ekstern_id,kommune_id,bygning_id,navn,lokaletype_id,"
          f"kapasitet,kapasitet_kilde,beskrivelse,apningstid_tekst,aktiv,bookbar) "
          f"SELECT fi.id,{q(r['id'])},k.id,{bygg_sel},{q(navn)},{lt_sel},"
          f"{kap or 'NULL'},{q('kilde') if kap else 'NULL'},{q(beskr)},{q(rens(r.get('opening_hours')))},"
          f"{aktiv},{bookbar} "
          f"FROM kommune k, fagsystem_instans fi "
          f"WHERE k.kommunenr={q(knr)} AND fi.kildenokkel={q(kn)} "
          f"ON CONFLICT (fagsystem_instans_id,ekstern_id) DO UPDATE SET navn=EXCLUDED.navn;\n")
    w("\n")

    # --- koblinger, med avviksloggføring for brutte referanser ---
    # searchdataall er et delvis uttrekk: koblingstabellene eksporteres
    # komplett, mens bygg- og ressurslistene er filtrert. Rader som peker på
    # noe utenfor uttrekket kan ikke lastes, og loggføres i stedet for å
    # forkastes stille.
    kjente_ressurser = {r["id"] for r in d.get("resources", [])}
    for samling, kodetype, koblingstabell, maalkol, idfelt in [
        ("resource_activities", "aktivitet", "ressurs_aktivitet", "aktivitet_id", "activity_id"),
        ("resource_facilities", "fasilitet", "ressurs_fasilitet", "fasilitet_id", "facility_id"),
    ]:
        for rad in d.get(samling, []):
            if rad["resource_id"] not in kjente_ressurser:
                w(f"INSERT INTO synk_avvik (kilde,samling,avvikstype,ekstern_id,detalj) "
                  f"VALUES ({q(kn)},{q(samling)},'manglende_forelder',{q(rad['resource_id'])},"
                  f"'resource_id finnes ikke i uttrekket');\n")
                continue
            w(f"INSERT INTO {koblingstabell} (ressurs_id,{maalkol}) "
              f"SELECT r.id,m.{maalkol} "
              f"FROM ressurs r JOIN fagsystem_instans fi ON fi.id=r.fagsystem_instans_id "
              f"JOIN kildekode kk ON kk.fagsystem_instans_id=fi.id AND kk.kodetype={q(kodetype)} "
              f"AND kk.kode={q(rad[idfelt])} "
              f"JOIN kildekode_mapping m ON m.kildekode_id=kk.id "
              f"AND m.status='godkjent' AND m.{maalkol} IS NOT NULL "
              f"WHERE fi.kildenokkel={q(kn)} AND r.ekstern_id={q(rad['resource_id'])} "
              f"ON CONFLICT DO NOTHING;\n")

    for br in d.get("building_resources", []):
        if br["building_id"] not in kjente_bygg:
            w(f"INSERT INTO synk_avvik (kilde,samling,avvikstype,ekstern_id,detalj) "
              f"VALUES ({q(kn)},'building_resources','manglende_forelder',{q(br['building_id'])},"
              f"'building_id finnes ikke i uttrekket');\n")
        if br["resource_id"] not in kjente_ressurser:
            w(f"INSERT INTO synk_avvik (kilde,samling,avvikstype,ekstern_id,detalj) "
              f"VALUES ({q(kn)},'building_resources','manglende_forelder',{q(br['resource_id'])},"
              f"'resource_id finnes ikke i uttrekket');\n")

    w("\nCOMMIT;\n")
    print(f"  {len(d.get('buildings', []))} bygg, {len(d.get('resources', []))} ressurser", file=sys.stderr)


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in (*KOMMUNER, "alle"):
        navn = ", ".join(KOMMUNER)
        print(f"Bruk: python3 {sys.argv[0]} <kommune|alle>\n\nKjente kommuner: {navn}", file=sys.stderr)
        sys.exit(1)

    valg = list(KOMMUNER) if sys.argv[1] == "alle" else [sys.argv[1]]
    for slug in valg:
        generer_sql(slug, sys.stdout)


if __name__ == "__main__":
    main()
