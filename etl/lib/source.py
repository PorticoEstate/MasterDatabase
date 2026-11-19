"""
Reading and cleaning source data from Aktiv kommune: fetching JSON, HTML
cleanup, number parsing, and removing personal data from records.
"""
import html
import json
import re
import urllib.error
import urllib.request


def er_persondatafelt(felt: str) -> bool:
    """Felt som kan inneholde navngitte personer (tilsynsperson, kontaktinfo-
    fritekst) eller en kopi av dem (json_representation), og som derfor ikke
    tas med i en post som lagres som rapost på et avvik. "organizations"
    (privatpersoner som søkere) brukes aldri i det hele tatt av dette
    skriptet. Se "Personvern" i db/schema_kjerne_dokumentasjon.md."""
    return felt.startswith("tilsyn") or felt in ("contact_info", "json_representation",
                                                "organizations_ids")


def rens_post(d: dict) -> dict:
    """Fjerner persondatafelt fra én enkelt post før den limes inn som rapost
    på et avvik - se er_persondatafelt."""
    return {k: v for k, v in d.items() if not er_persondatafelt(k)}


def hent_json(url: str) -> tuple[int, dict]:
    """Henter JSON fra url med Pythons innebygde urllib. Krever at Capgeminis
    CA-sertifikat er installert i systemets tillitslager (se etl/docs/running.md).
    Prøver to ganger: enkelte instanser (Stavanger) svarer av og til tregere
    enn tidsavbruddet. Returnerer (http_status, innhold)."""
    for forsok in (1, 2):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except (TimeoutError, urllib.error.URLError):
            if forsok == 2:
                raise


def rens(s):
    """Dobbel HTML-avkoding; kilden er escapet en gang for mye
    (f.eks. 'Rom 19 &amp;#40;219&amp;#41;' skal bli 'Rom 19 (219)')."""
    if s is None:
        return None
    s = html.unescape(html.unescape(str(s)))
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def som_heltall(v):
    """(verdi, feilmelding). Tom verdi gir (None, None); ugyldig gir (None, melding)."""
    if v is None or v == "":
        return None, None
    try:
        n = int(v)
    except (ValueError, TypeError):
        return None, f"ikke et heltall: {str(v)[:60]}"
    if n < 0:
        return None, f"negativt tall: {n}"
    return n, None
