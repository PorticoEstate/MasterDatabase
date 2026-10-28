#!/bin/bash
# Kjører ETL-stegene i riktig rekkefølge mot databasen i Docker.
#
# Bruk:
#   etl/kjor_alt.sh last <kommune|alle>   henter fra Aktiv kommune, laster inn og kjører mapping
#   etl/kjor_alt.sh mapping [--dry-run]   kjører bare mappingen (etter endring i etl/*_mapping/)
#   etl/kjor_alt.sh matrikkel             geokoder og beriker fra Matrikkelen
#   etl/kjor_alt.sh alle                  last alle + mapping + matrikkel
#
# Python-skriptene gjør fortsatt ingenting mot databasen selv. Dette skriptet
# henter det de trenger fra databasen, sender det inn på standard-inn, lagrer
# SQL-en de skriver i etl/ut/ og kjører den med psql. Filene i etl/ut/ viser
# derfor i ettertid hva som ble kjørt.
#
# Innloggingen til Matrikkelen leses fra etl/.env (kopier etl/.env.example).
# Den filen skal aldri inn i git.

set -euo pipefail

cd "$(dirname "$0")/.."
UT=etl/ut
mkdir -p "$UT"

if [ -f etl/.env ]; then
	set -a
	. etl/.env
	set +a
fi

psql_db()
{
	docker exec -i portico_masterdb psql -q -U postgres -d masterdb "$@"
}

bruk()
{
	sed -n '4,8p' "$0" | sed 's/^# \{0,1\}//' >&2
	exit 1
}

# Stopper hvis backenden ikke har kjørt alle Flyway-migrasjonene i repoet.
# Migrasjonene ligger i JAR-en, så en ny migrasjonsfil krever --build.
sjekk_flyway()
{
	local forventet kjort
	forventet=$(ls backend/src/main/resources/db/migration | sed -n 's/^V\([0-9]*\)__.*/\1/p' | sort -n | tail -1)
	kjort=$(psql_db -tA -c "SELECT coalesce(max(version::int), 0) FROM flyway_schema_history WHERE success" 2>/dev/null || echo 0)
	if [ "$kjort" -lt "$forventet" ]; then
		echo "Databasen er på Flyway-versjon $kjort, repoet har V$forventet (eller databasen kjører ikke)." >&2
		echo "Bygg og start backenden først: docker compose up -d --build backend" >&2
		exit 1
	fi
}

# Sjekkes før noe kjører, så 'alle' ikke stopper først etter innlastingen.
krev_matrikkel_innlogging()
{
	if [ -z "${MATRIKKELAPI_LOGIN:-}" ] || [ -z "${MATRIKKELAPI_PASSWORD:-}" ]; then
		echo "Mangler MATRIKKELAPI_LOGIN eller MATRIKKELAPI_PASSWORD." >&2
		echo "Kopier etl/.env.example til etl/.env og fyll inn." >&2
		exit 1
	fi
}

last()
{
	python3 etl/last_inn.py "$1" > "$UT/$1.sql"
	psql_db < "$UT/$1.sql"
}

mapping()
{
	psql_db -tA -F$'\t' -c "
		SELECT fi.kildenokkel, kk.kodetype, kk.kode, kk.navn
		FROM kildekode kk JOIN fagsystem_instans fi ON fi.id = kk.fagsystem_instans_id
		ORDER BY 1, 2, 3" \
		| python3 etl/last_mapping.py "$@" > "$UT/mapping.sql"
	psql_db < "$UT/mapping.sql"
}

# Spørringen henter bare det som fortsatt mangler, så en ny kjøring er billig.
# Se docstringen i etl/matrikkel_adresse.py.
matrikkel()
{
	psql_db -tA -F'|' -c "
		SELECT a.id, a.adressetekst, a.postnummer, a.poststed, k.kommunenr,
		       a.bygning_id, a.geokoding, a.gate_id, a.husnr, a.bokstav, g.adressekode
		FROM adresse a
		JOIN bygning b ON b.id = a.bygning_id
		JOIN kommune k ON k.id = b.kommune_id
		LEFT JOIN gate g ON g.id = a.gate_id
		WHERE a.er_hovedadresse AND a.geokoding <> 'manuell' AND a.adressetekst IS NOT NULL
		  AND (a.geokoding IN ('ukjent','feilet') OR b.bygningsnr IS NULL
		       OR NOT EXISTS (SELECT 1 FROM matrikkelinfo m WHERE m.bygning_id = b.id))" \
		| python3 etl/matrikkel_adresse.py > "$UT/matrikkel.sql"
	psql_db < "$UT/matrikkel.sql"
}

case "${1:-}" in
	last)
		[ $# -eq 2 ] || bruk
		sjekk_flyway
		last "$2"
		mapping
		;;
	mapping)
		shift
		sjekk_flyway
		mapping "$@"
		;;
	matrikkel)
		krev_matrikkel_innlogging
		sjekk_flyway
		matrikkel
		;;
	alle)
		krev_matrikkel_innlogging
		sjekk_flyway
		last alle
		mapping
		matrikkel
		;;
	*)
		bruk
		;;
esac
