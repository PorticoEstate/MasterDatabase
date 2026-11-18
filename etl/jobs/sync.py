#!/usr/bin/env python3
"""
Løpende synkronisering fra Aktiv kommune til masterdatabasen (til cron).

Samme innlasting som jobs/build.py, men uten å skrive i kodeverkene
(lokaletype, aktivitet, fasilitet): masteren eier vokabularet og hierarkiet.
Alt kilden har som viker fra masteren (ukjent id, annet navn, annen forelder)
loggføres i synk_avvik. Det kommunen eier lastes derimot, og endringer slår
inn i masteren: bygg og ressurser (også nye), og koblingene ressurs -> bygg,
lokaletype, aktivitet og fasilitet. En kobling til en id masteren ikke kjenner
lastes ikke, og loggføres.

jobs/build.py brukes én gang, når databasen bygges; dette skriptet brukes
etterpå. Begge forutsetter normaliserte instanser (se "Kildekontrakt" i
etl/README.md).

Bruk:
    (cd etl && python3 -m jobs.sync alle) > etl/ut/synk.sql
    docker exec -i portico_masterdb psql -U postgres -d masterdb < etl/ut/synk.sql

    # Les <mappe>/<kommune>.json i stedet for å hente fra nettet:
    (cd etl && python3 -m jobs.sync alle --fra-fil ut/normalisert) > etl/ut/synk.sql

Skriptet gjør ingenting mot databasen selv; det skriver SQL-tekst til
standard-ut. Se etl/README.md for full forklaring.

Hver kjøring registrerer et kildeuttrekk (metadata: kilde, endepunkt,
tidspunkt, HTTP-status - ikke hele svaret). Ethvert avvik - ugyldige verdier,
brutte referanser, databasefeil - loggføres i synk_avvik sammen med den
konkrete posten (renset for personopplysninger) som utløste det, ikke bare en
feiltekst. Se db/schema_kjerne_dokumentasjon.md, "Innlasting og sporbarhet".

Kjent forenkling: kommune_id settes her fra hvilken Aktiv kommune-instans
ressursen kommer fra (f.eks. "bergen" -> kommunenr 4601). Det er riktig for
alle de 12 instansene vi kjenner i dag, som hver betjener nøyaktig én kommune.
Skjemaet (Flyway-migrasjonene i backend) tillater at en instans betjener flere kommuner
via kommune_fagsystem_instans; den dagen det faktisk skjer, må kommune_id i
stedet utledes fra en geokodet adresse. Se db/schema_kjerne_dokumentasjon.md.
"""
import argparse
import sys
from pathlib import Path

from lib.kommuner import kommuner_fra_kommandolinje
from lib.load import generer_sql


def main():
    kommuner = kommuner_fra_kommandolinje(paakrevd=True)
    parser = argparse.ArgumentParser(description="Synkroniserer fra Aktiv kommune; skriver SQL til standard-ut.",
                                     epilog="Kjente kommuner: " + ", ".join(kommuner))
    parser.add_argument("kommune", choices=(*kommuner, "alle"), metavar="kommune|alle")
    parser.add_argument("--fra-fil", type=Path, metavar="MAPPE",
                        help="les MAPPE/<kommune>.json i stedet for å hente fra nettet")
    parser.add_argument("--kommuner-fil", type=Path, metavar="FIL", required=True,
                        help="kommunene som skal synkroniseres, fra databasen (slug|kommunenr|navn|fylke "
                             "per linje, laget av sql/kommuner_query.sql)")
    args = parser.parse_args()

    valg = list(kommuner) if args.kommune == "alle" else [args.kommune]
    if not valg:
        print("ingen kommuner å synkronisere", file=sys.stderr)
    feilet = [slug for slug in valg if not generer_sql(slug, kommuner[slug], sys.stdout, args.fra_fil, initial_build=False)]
    if feilet:
        print(f"\nHenting feilet for: {', '.join(feilet)} (loggført i synk_avvik)", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
