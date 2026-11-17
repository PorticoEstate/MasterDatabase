"""
Building blocks for the generated SQL: literals, deviation logging, the
per-record DO block and the ressurslenke statement.
"""
import json

from lib.source import rens_post


def q(v):
    """Gjør en Python-verdi til en trygg SQL-literal. NULL for tomme verdier,
    og escaper enkeltfnutter slik at f.eks. navn med apostrof ikke knekker SQL-en."""
    if v is None or v == "":
        return "NULL"
    return "'" + str(v).replace("'", "''").replace("\x00", "") + "'"


def q_json(obj) -> str:
    """JSON-literal. jsonb avviser \\u0000, så den escapen fjernes."""
    tekst = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("\\u0000", "")
    return q(tekst) + "::jsonb"


def logg(kn, samling, avvikstype, ekstern_id, detalj, felt=None, nokkelfelt="id", rapost=None) -> str:
    """Setning som loggfører et avvik mot kildeuttrekket som er registrert
    først i samme transaksjon (se registrer_kildeuttrekk i V1__masterdatabase__skjema.sql).
    rapost er posten som utløste avviket - lagres direkte på avviket (renset
    for personopplysninger), ikke i et delt uttrekk som må graves ut igjen."""
    rapost_sql = q_json(rens_post(rapost)) if rapost is not None else "NULL"
    return (f"CALL logg_avvik({q(kn)},{q(samling)},{q(avvikstype)},{q(ekstern_id)},"
            f"{q(detalj)},{q(felt)},{q(nokkelfelt)},{rapost_sql});\n")


def i_blokk(kn, samling, ekstern_id, sql, rapost=None) -> str:
    """Pakker setningene for én post i en DO-blokk. Feiler noe i databasen
    (f.eks. et CHECK-brudd vi ikke har forutsett), rulles bare denne posten
    tilbake og feilen loggføres som db_feil - resten av lasten fortsetter i
    stedet for at hele transaksjonen stopper."""
    rapost_sql = q_json(rens_post(rapost)) if rapost is not None else "NULL"
    return ("DO $blk$ BEGIN\n" + sql + "EXCEPTION WHEN OTHERS THEN\n"
            f"CALL logg_avvik({q(kn)},{q(samling)},'db_feil',{q(ekstern_id)},"
            f"SQLSTATE || ': ' || SQLERRM,NULL,'id',{rapost_sql});\nEND $blk$;\n")


# Path of a resource in an Aktiv kommune booking system, appended to the
# instance's base_url. Stored in ressurslenke.url.
RESSURS_URL_MONSTER = "/bookingfrontend/resource/client/"


def ressurslenke_sql(kn: str) -> str:
    """SQL that gives every resource of the instance `kn` its link in ressurslenke.

    Set-based and idempotent: one row per (instance, resource), updated in place.
    Links to other fagsystem instances are not touched.
    """
    return (
        f"INSERT INTO ressurslenke (fagsystem_instans_id,ressurs_id,ekstern_id,url) "
        f"SELECT r.fagsystem_instans_id,r.id,r.ekstern_id,"
        f"fi.base_url || {q(RESSURS_URL_MONSTER)} || r.ekstern_id "
        f"FROM ressurs r JOIN fagsystem_instans fi ON fi.id=r.fagsystem_instans_id "
        f"WHERE fi.kildenokkel={q(kn)} "
        f"ON CONFLICT (fagsystem_instans_id,ressurs_id) "
        f"DO UPDATE SET url=EXCLUDED.url, ekstern_id=EXCLUDED.ekstern_id;\n"
    )


# Deviation logging for the jobs that read Matrikkel (geocode, gater): the source
# is "matrikkel-*" and the record is the lookup key, not an Aktiv kommune record.
# Different signatures from logg/i_blokk above, hence the separate names.
def logg_matrikkel(ekstern_id, detalj, rapost, kilde="matrikkel-adresse", samling="adresse",
                   avvikstype="geokoding_feilet", nokkelfelt="adresse_id") -> str:
    return (f"CALL logg_avvik({q(kilde)},{q(samling)},{q(avvikstype)},{q(ekstern_id)},"
            f"{q(detalj)},NULL,{q(nokkelfelt)},{q_json(rapost)});\n")


def i_blokk_matrikkel(ekstern_id, sql, rapost, kilde="matrikkel-adresse", samling="adresse",
                      nokkelfelt="adresse_id") -> str:
    return ("DO $blk$ BEGIN\n" + sql + "EXCEPTION WHEN OTHERS THEN\n"
            f"CALL logg_avvik({q(kilde)},{q(samling)},'db_feil',{q(ekstern_id)},"
            f"SQLSTATE || ': ' || SQLERRM,NULL,{q(nokkelfelt)},{q_json(rapost)});\nEND $blk$;\n")
