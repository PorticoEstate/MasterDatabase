#!/usr/bin/env bash
# Runs the ETL pipeline inside the etl container.
#
#   run.sh daemon     (default) initial build if the master has no vocabulary
#                     yet, then a nightly sync at SYNK_TID
#   run.sh build      last_inn.py: seeds the vocabulary and loads everything
#   run.sh sync       synk.py: loads buildings, resources and links
#   run.sh geocode    Matrikkel geocoding and building enrichment
#   run.sh prune      delete old synk_avvik rows (also done after each nightly run)
#   run.sh status     row counts, geocoding status and latest extracts (read-only)
#
# The Python scripts only write SQL; this script pipes it to psql. The SQL is
# kept in $UT (a volume) so the last run can be reviewed afterwards.
#
# Settings (environment, all optional except the PG* connection and, for
# geocoding, the Matrikkel credentials):
#   KOMMUNER=alle           "alle" or one kommune slug, e.g. bergen. For sync, "alle" means
#                           every kommune with an active Aktiv kommune instance in the
#                           database (kommuner_query.sql); the first build uses the built-in list.
#   SYNK_TID=03:00          time of the nightly sync, in TZ
#   NORMALISER_DEMO=true    run the demo normaliser before loading
#   DRY_RUN=false           write the SQL but do not apply it
#   AVVIK_RETENTION_DAYS=30 synk_avvik rows older than this are deleted nightly
#   MATRIKKEL_BRUKER / MATRIKKEL_PASSORD / MATRIKKEL_MILJO   see etl/README.md
#
# Networks that inspect TLS re-sign HTTPS traffic with their own certificate
# authority. Put its certificate (PEM, *.crt or *.pem) in ./certs on the host;
# it is mounted at /extra-ca and added to the trust store at startup.
set -u

KOMMUNER="${KOMMUNER:-alle}"
SYNK_TID="${SYNK_TID:-03:00}"
NORMALISER_DEMO="${NORMALISER_DEMO:-true}"
DRY_RUN="${DRY_RUN:-false}"
AVVIK_RETENTION_DAYS="${AVVIK_RETENTION_DAYS:-30}"

HER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UT="${UT:-$HER/ut}"
cd "$HER" || exit 1
mkdir -p "$UT"

log()
{
	printf '%s [etl] %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$*"
}

# Adds the certificates in $EXTRA_CA_DIR (default /extra-ca) to the system
# trust store, which Python's urllib uses. Does nothing if the folder is empty.
install_extra_ca()
{
	local dir="${EXTRA_CA_DIR:-/extra-ca}" fil funnet=0
	[ -d "$dir" ] || return 0
	for fil in "$dir"/*.crt "$dir"/*.pem; do
		[ -f "$fil" ] || continue
		cp "$fil" "/usr/local/share/ca-certificates/extra-$(basename "${fil%.*}").crt"
		funnet=$((funnet + 1))
	done
	[ "$funnet" -eq 0 ] && return 0
	log "adding $funnet extra CA certificate(s) from $dir"
	update-ca-certificates >/dev/null 2>&1 || log "update-ca-certificates failed"
}

is_true()
{
	case "${1,,}" in
		true|1|yes) return 0 ;;
		*) return 1 ;;
	esac
}

# Applies a SQL file. Errors inside a kommune's transaction roll that kommune
# back and the next one still runs (same as piping the file to psql by hand),
# so ERROR lines are logged rather than stopping the run.
apply()
{
	local fil="$1" feil="$UT/psql.err"
	if is_true "$DRY_RUN"; then
		log "DRY_RUN: not applying $fil"
		return 0
	fi
	if ! psql -q -f "$fil" >/dev/null 2>"$feil"; then
		log "psql failed for $fil:"
		head -n 5 "$feil"
		return 1
	fi
	if grep -q 'ERROR' "$feil"; then
		log "psql reported errors for $fil ($(grep -c 'ERROR' "$feil") lines), first ones:"
		grep 'ERROR' "$feil" | head -n 5
	fi
	return 0
}

wait_for_schema()
{
	local forsok
	for forsok in $(seq 1 120); do
		if [ "$(psql -tAc "SELECT 1 FROM flyway_schema_history WHERE version = '1' AND success" 2>/dev/null)" = "1" ]; then
			return 0
		fi
		log "waiting for the schema (Flyway V1)..."
		sleep 5
	done
	log "the schema did not appear within 10 minutes"
	return 1
}

# Prints "t" if all three code lists are empty. Returns 1 if the query fails.
vocabulary_empty()
{
	psql -tAc "SELECT NOT EXISTS (SELECT 1 FROM lokaletype)
	             AND NOT EXISTS (SELECT 1 FROM aktivitet)
	             AND NOT EXISTS (SELECT 1 FROM fasilitet)"
}

# Writes $UT/kommuner.txt: the kommuner registered in the database with an
# active Aktiv kommune instance (slug|kommunenr|navn|fylke|base_url), so a kommune added
# there is synced without any change to the code. If the query fails nothing is
# synced: falling back to the built-in list could sync the wrong set.
registered_kommuner()
{
	if ! psql -tA -F'|' -f kommuner_query.sql >"$UT/kommuner.txt"; then
		log "sync: the kommune query failed"
		return 1
	fi
	log "sync: $(grep -c . "$UT/kommuner.txt") kommune(r) with an active Aktiv kommune instance"
}

# generate build|sync: writes $UT/<modus>.sql. A partial fetch failure (exit
# code 2) still yields complete SQL, with the failure logged in synk_avvik, so
# it is a warning and not an error.
generate()
{
	local modus="$1" skript="last_inn.py" rc
	local args=("$KOMMUNER") kommuner_arg=()
	if [ "$modus" = "sync" ]; then
		skript="synk.py"
		registered_kommuner || return 1
		kommuner_arg=(--kommuner-fil "$UT/kommuner.txt")
	fi

	if is_true "$NORMALISER_DEMO"; then
		python3 demo_normalisering/normaliser.py "$KOMMUNER" --ut "$UT/normalisert" ${kommuner_arg[@]+"${kommuner_arg[@]}"}
		rc=$?
		[ "$rc" -ne 0 ] && log "demo normaliser exited with $rc (see messages above)"
		args+=(--fra-fil "$UT/normalisert")
	fi

	python3 "$skript" "${args[@]}" ${kommuner_arg[@]+"${kommuner_arg[@]}"} >"$UT/$modus.sql"
	rc=$?
	if [ "$rc" -eq 2 ]; then
		log "$skript: some fetches failed (logged in synk_avvik); continuing with the rest"
	elif [ "$rc" -ne 0 ]; then
		log "$skript failed with exit code $rc"
		return 1
	fi
	return 0
}

do_build()
{
	log "build: loading $KOMMUNER with last_inn.py"
	generate build && apply "$UT/build.sql"
}

do_sync()
{
	log "sync: loading $KOMMUNER with synk.py"
	generate sync && apply "$UT/sync.sql"
}

do_geocode()
{
	if [ -z "${MATRIKKEL_BRUKER:-}" ] || [ -z "${MATRIKKEL_PASSORD:-}" ]; then
		log "geocode: skipped, MATRIKKEL_BRUKER / MATRIKKEL_PASSORD are not set"
		return 0
	fi
	log "geocode: querying addresses to look up (MATRIKKEL_MILJO=${MATRIKKEL_MILJO:-test})"
	if ! psql -tA -F'|' -f geocode_query.sql >"$UT/adresser.txt"; then
		log "geocode: the address query failed"
		return 1
	fi
	if [ ! -s "$UT/adresser.txt" ]; then
		log "geocode: nothing to look up"
		return 0
	fi
	# The output is one transaction that commits at the very end, so a failed
	# run leaves a truncated file that must not be applied.
	if ! python3 matrikkel_adresse.py <"$UT/adresser.txt" >"$UT/matrikkel.sql"; then
		log "geocode: matrikkel_adresse.py failed; nothing applied"
		return 1
	fi
	apply "$UT/matrikkel.sql"
}

# Deletes synk_avvik rows older than AVVIK_RETENTION_DAYS, except those in
# v_synk_avvik_gjeldende (the latest run per source), so a source that stops
# running keeps its current problems visible. Every run adds avvik rows and
# nothing else removes them.
prune_avvik()
{
	local antall
	if ! [[ "$AVVIK_RETENTION_DAYS" =~ ^[1-9][0-9]*$ ]]; then
		log "prune: AVVIK_RETENTION_DAYS must be a positive whole number, got '$AVVIK_RETENTION_DAYS'"
		return 1
	fi
	if is_true "$DRY_RUN"; then
		log "DRY_RUN: not pruning synk_avvik"
		return 0
	fi
	antall=$(psql -tA -c "WITH slettet AS (
			DELETE FROM synk_avvik
			WHERE created_at < now() - make_interval(days => $AVVIK_RETENTION_DAYS)
			  AND id NOT IN (SELECT id FROM v_synk_avvik_gjeldende)
			RETURNING 1)
		SELECT count(*) FROM slettet") || { log "prune: the delete failed"; return 1; }
	log "prune: deleted $antall synk_avvik row(s) older than $AVVIK_RETENTION_DAYS days"
}

seconds_until_sync()
{
	local naa maal
	naa=$(date +%s)
	maal=$(date -d "today $SYNK_TID" +%s)
	[ "$maal" -le "$naa" ] && maal=$(date -d "tomorrow $SYNK_TID" +%s)
	echo $((maal - naa))
}

daemon()
{
	trap 'log "stopping"; exit 0' TERM INT

	if ! [[ "$SYNK_TID" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]]; then
		log "SYNK_TID must be HH:MM, got '$SYNK_TID'"
		exit 1
	fi
	if ! [[ "$AVVIK_RETENTION_DAYS" =~ ^[1-9][0-9]*$ ]]; then
		log "AVVIK_RETENTION_DAYS must be a positive whole number, got '$AVVIK_RETENTION_DAYS'"
		exit 1
	fi
	wait_for_schema || exit 1

	local tom
	tom=$(vocabulary_empty) || { log "could not query the vocabulary tables"; exit 1; }
	if [ "$tom" = "t" ]; then
		log "no vocabulary in the master yet: initial build"
		do_build || log "initial build failed; the next start or the nightly run retries if the vocabulary is still empty"
		do_geocode || true
	else
		log "vocabulary present: skipping the initial build"
	fi

	local venting
	while true; do
		venting=$(seconds_until_sync)
		log "next sync at $SYNK_TID (in ${venting}s)"
		sleep "$venting" &
		wait $!

		# Seeds the vocabulary if an earlier build left it empty.
		tom=$(vocabulary_empty) || tom=""
		if [ "$tom" = "t" ]; then
			do_build || log "build failed"
		else
			do_sync || log "sync failed"
		fi
		do_geocode || true
		prune_avvik || true
	done
}

install_extra_ca

case "${1:-daemon}" in
	daemon) daemon ;;
	build) do_build ;;
	sync) do_sync ;;
	geocode) do_geocode ;;
	prune) prune_avvik ;;
	status) psql -f status.sql ;;
	*)
		echo "usage: run.sh [daemon|build|sync|geocode|prune|status]" >&2
		exit 1
		;;
esac
