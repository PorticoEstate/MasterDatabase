#!/usr/bin/env python3
"""
Bygger masterdatabasen fra Aktiv kommune. Kjøres én gang, når databasen
bygges; deretter brukes jobs/sync.py.

Forutsetter normaliserte instanser (se "Kildekontrakt" i etl/README.md). Mot
en tom database opprettes kodeverkene (lokaletype, aktivitet, fasilitet) fra
instansenes samlinger, med id, navn og forelder, sammen med bygg, ressurser og
koblinger. Et konsept som allerede finnes røres aldri: masteren eier
vokabularet, og forskjeller (samme id med annet navn eller annen forelder)
loggføres i synk_avvik.

Bruker bare Pythons innebygde bibliotek (urllib, json, re) - ingen "pip install"
er nødvendig. Skriptet gjør ingenting mot databasen selv; det skriver SQL-tekst
til standard-ut, som du deretter sender til Postgres. Det gjør at du kan se
nøyaktig hva som skal skje før noe faktisk endres.

Bruk:
    (cd etl && python3 -m jobs.build bergen) > etl/ut/bergen.sql
    docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/bergen.sql

    (cd etl && python3 -m jobs.build alle) > etl/ut/alle.sql
    docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/alle.sql

    # Les <mappe>/<kommune>.json i stedet for å hente fra nettet:
    (cd etl && python3 -m jobs.build alle --fra-fil ut/normalisert) > etl/ut/alle.sql
    docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/alle.sql

Se etl/README.md for full forklaring.

Hver kjøring registrerer et kildeuttrekk (metadata: kilde, endepunkt,
tidspunkt, HTTP-status - ikke hele svaret). Ethvert avvik - ugyldige verdier,
brutte referanser, databasefeil - loggføres i synk_avvik sammen med den
konkrete posten (renset for personopplysninger) som utløste det, ikke bare en
feiltekst. Se "9. Innlasting og sporbarhet" i Flyway-migrasjonen V1.

Kjent forenkling: kommune_id settes her fra hvilken Aktiv kommune-instans
ressursen kommer fra (f.eks. "bergen" -> kommunenr 4601). Det er riktig for
alle de 12 instansene vi kjenner i dag, som hver betjener nøyaktig én kommune.
Skjemaet (Flyway-migrasjonene i backend) tillater at en instans betjener flere kommuner
via kommune_fagsystem_instans; den dagen det faktisk skjer, må kommune_id i
stedet utledes fra en geokodet adresse.
"""
import argparse
import sys
from pathlib import Path

from lib.kommuner import les_kommuner
from lib.load import generer_sql


def main():
    kommuner = les_kommuner(None)   # den innebygde listen
    parser = argparse.ArgumentParser(description="Bygger masterdatabasen fra Aktiv kommune; skriver SQL til standard-ut.",
                                     epilog="Kjente kommuner: " + ", ".join(kommuner))
    parser.add_argument("kommune", choices=(*kommuner, "alle"), metavar="kommune|alle")
    parser.add_argument("--fra-fil", type=Path, metavar="MAPPE",
                        help="les MAPPE/<kommune>.json i stedet for å hente fra nettet")
    args = parser.parse_args()

    valg = list(kommuner) if args.kommune == "alle" else [args.kommune]
    feilet = [slug for slug in valg
              if not generer_sql(slug, kommuner[slug], sys.stdout, args.fra_fil, initial_build=True)]
    if feilet:
        print(f"\nHenting feilet for: {', '.join(feilet)} (loggført i synk_avvik)", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
