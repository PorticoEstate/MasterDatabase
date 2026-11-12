#!/usr/bin/env python3
"""
Henter ALLE gater (veger) for de oppgitte kommunene fra Matrikkelen og skriver
SQL som legger dem i tabellen gate. Skriver bare SQL til standard-ut, som de
andre skriptene; run.sh sender den til psql.

    python3 hent_gater.py 4601 5601 > ut/gater.sql

Kjeden (MatrikkelAPI, SOAP):
    KommuneService.findKommuneIdForIdent   kommunenummer -> intern KommuneId
    AdresseService.findVegerForKommune     KommuneId -> alle VegId-er
    StoreService.getObjects                VegId-er -> adressekode + adressenavn

Ikke avhengig av Aktiv kommune: det eneste som trengs er at kommunen finnes i
tabellen kommune. Trygt å kjøre på nytt: gate har UNIQUE (kommune_id,
adressekode), og en eksisterende gate beholder id-en sin (bare gatenavnet
oppdateres hvis Matrikkelen har endret det), så adresse.gate_id peker fortsatt
riktig.

Hver kommune er sin egen transaksjon. Feiler en kommune (ukjent i Matrikkelen,
nettverk), logges det i synk_avvik og de andre kommunene fortsetter; exit-kode 2
betyr at minst én feilet. Leser MATRIKKEL_BRUKER / MATRIKKEL_PASSORD /
MATRIKKEL_MILJO som matrikkel_adresse.py - verdiene skrives aldri ut.
"""
import sys

import matrikkel_adresse as m

RADER_PER_INSERT = 1000


def sql_for_kommune(kommunenr: str, veger: list[dict]) -> str:
    # Duplikat adressekode i samme INSERT gir databasefeil, så dedupliser først.
    per_kode = {v["adressekode"]: v["adressenavn"] for v in veger
                if v["adressekode"] is not None and v["adressenavn"]}
    rader = [f"({kode},{m.q(navn)})" for kode, navn in sorted(per_kode.items())]
    sql = "BEGIN;\n"
    for start in range(0, len(rader), RADER_PER_INSERT):
        verdier = ",".join(rader[start:start + RADER_PER_INSERT])
        sql += (
            "INSERT INTO gate (kommune_id, adressekode, gatenavn)\n"
            f"SELECT k.id, v.kode, v.navn FROM kommune k\n"
            f"CROSS JOIN (VALUES {verdier}) AS v(kode, navn)\n"
            f"WHERE k.kommunenr = {m.q(kommunenr)}\n"
            "ON CONFLICT (kommune_id, adressekode) DO UPDATE SET gatenavn = EXCLUDED.gatenavn\n"
            "WHERE gate.gatenavn IS DISTINCT FROM EXCLUDED.gatenavn;\n"
        )
    return sql + "COMMIT;\n"


def main() -> int:
    kommunenr_liste = sys.argv[1:]
    if not kommunenr_liste:
        print("bruk: hent_gater.py <kommunenr> [<kommunenr> ...]", file=sys.stderr)
        return 1

    antall_feilet = 0
    for nr in kommunenr_liste:
        try:
            kommune_id = m.finn_kommune_id(nr)
            veg_ider = m.finn_veg_ider_for_kommune(kommune_id)
            veger = m.hent_veger(veg_ider)
            if not veger:
                raise m.MatrikkelFeil("Matrikkelen returnerte ingen veger")
        except (m.MatrikkelFeil, KeyError) as e:
            antall_feilet += 1
            print(f"gater {nr}: FEILET: {e}", file=sys.stderr)
            sys.stdout.write(m.logg(nr, f"henting av gater feilet: {str(e)[:200]}", {"kommunenr": nr},
                                    kilde="matrikkel-gate", samling="gate", avvikstype="annet",
                                    nokkelfelt="kommunenr"))
            continue
        sys.stdout.write(sql_for_kommune(nr, veger))
        print(f"gater {nr}: {len(veger)} veger fra Matrikkelen", file=sys.stderr)

    return 2 if antall_feilet else 0


if __name__ == "__main__":
    sys.exit(main())
