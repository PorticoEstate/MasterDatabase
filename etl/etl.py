#!/usr/bin/env python3
"""Runs the ETL pipeline inside the etl container (Python port of the old run.sh).

  etl.py daemon     (default) initial build if the master has no vocabulary
                    yet (build, then gater, then geocode), then a nightly
                    sync, geocode and prune at SYNK_TID
  etl.py build      last_inn.py: seeds the vocabulary and loads everything
  etl.py sync       synk.py: loads buildings, resources and links
  etl.py geocode    Matrikkel geocoding and building enrichment
  etl.py gater [<kommunenr>...]
                    fetch every street of a kommune from Matrikkel into gate,
                    so gate matches Matrikkel. No argument: every kommune in
                    the database. The daemon runs it once, after the initial
                    build; otherwise it only runs when started by hand.
  etl.py prune      delete old synk_avvik rows (also done after each nightly run)
  etl.py status     row counts, geocoding status and latest extracts (read-only)

run.sh is a thin shim over this file, so `./run.sh status` etc. still work.

The Python scripts only write SQL; this script pipes it to psql. The SQL is
kept in $UT (a volume) so the last run can be reviewed afterwards.

Settings (environment, all optional except the PG* connection and, for
geocoding, the Matrikkel credentials):
  KOMMUNER=alle           "alle" or one kommune slug, e.g. bergen
  SYNK_TID=03:00          time of the nightly sync, in TZ
  NORMALISER_DEMO=true    run the demo normaliser before loading
  DRY_RUN=false           write the SQL but do not apply it
  AVVIK_RETENTION_DAYS=30 synk_avvik rows older than this are deleted nightly
  MATRIKKEL_BRUKER / MATRIKKEL_PASSORD / MATRIKKEL_MILJO   see etl/README.md

Networks that inspect TLS re-sign HTTPS traffic with their own certificate
authority. Put its certificate (PEM, *.crt or *.pem) in ./certs on the host;
it is mounted at /extra-ca and added to the trust store at startup.
"""

import datetime
import glob
import os
import re
import shutil
import signal
import subprocess
import sys
import time

KOMMUNER = os.environ.get("KOMMUNER") or "alle"
SYNK_TID = os.environ.get("SYNK_TID") or "03:00"
NORMALISER_DEMO = os.environ.get("NORMALISER_DEMO") or "true"
DRY_RUN = os.environ.get("DRY_RUN") or "false"
AVVIK_RETENTION_DAYS = os.environ.get("AVVIK_RETENTION_DAYS") or "30"

HER = os.path.dirname(os.path.abspath(__file__))
UT = os.environ.get("UT") or os.path.join(HER, "ut")

USAGE = "usage: run.sh [daemon|build|sync|geocode|gater [kommunenr...]|prune|status]"


def log(msg):
    print("%s [etl] %s" % (time.strftime("%Y-%m-%d %H:%M:%S %Z"), msg), flush=True)


def is_true(value):
    return value.lower() in ("true", "1", "yes")


def py(script, *args):
    """Command line for one of the sibling Python scripts."""
    return [sys.executable, script] + list(args)


def psql_query(sql):
    """Runs a read query with psql -tA. Returns the stripped output, or None on failure."""
    res = subprocess.run(["psql", "-tA", "-c", sql], stdout=subprocess.PIPE, text=True)
    if res.returncode != 0:
        return None
    return res.stdout.strip()


def install_extra_ca():
    """Adds the certificates in $EXTRA_CA_DIR (default /extra-ca) to the system
    trust store, which Python's urllib uses. Does nothing if the folder is empty."""
    directory = os.environ.get("EXTRA_CA_DIR") or "/extra-ca"
    if not os.path.isdir(directory):
        return
    found = 0
    files = sorted(glob.glob(os.path.join(directory, "*.crt")) + glob.glob(os.path.join(directory, "*.pem")))
    for fil in files:
        if not os.path.isfile(fil):
            continue
        name = os.path.splitext(os.path.basename(fil))[0]
        shutil.copyfile(fil, "/usr/local/share/ca-certificates/extra-%s.crt" % name)
        found += 1
    if found == 0:
        return
    log("adding %d extra CA certificate(s) from %s" % (found, directory))
    res = subprocess.run(["update-ca-certificates"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if res.returncode != 0:
        log("update-ca-certificates failed")


def apply(fil):
    """Applies a SQL file. Errors inside a kommune's transaction roll that kommune
    back and the next one still runs (same as piping the file to psql by hand),
    so ERROR lines are logged rather than stopping the run."""
    feil = os.path.join(UT, "psql.err")
    if is_true(DRY_RUN):
        log("DRY_RUN: not applying %s" % fil)
        return True
    with open(feil, "w") as err:
        res = subprocess.run(["psql", "-q", "-f", fil], stdout=subprocess.DEVNULL, stderr=err)
    with open(feil, errors="replace") as err:
        lines = err.read().splitlines()
    if res.returncode != 0:
        log("psql failed for %s:" % fil)
        print("\n".join(lines[:5]), flush=True)
        return False
    errors = [line for line in lines if "ERROR" in line]
    if errors:
        log("psql reported errors for %s (%d lines), first ones:" % (fil, len(errors)))
        print("\n".join(errors[:5]), flush=True)
    return True


def wait_for_schema():
    for _ in range(120):
        out = psql_query("SELECT 1 FROM flyway_schema_history WHERE version = '1' AND success")
        if out == "1":
            return True
        log("waiting for the schema (Flyway V1)...")
        time.sleep(5)
    log("the schema did not appear within 10 minutes")
    return False


def vocabulary_empty():
    """True if all three code lists are empty, False if not, None if the query fails."""
    out = psql_query("""SELECT NOT EXISTS (SELECT 1 FROM lokaletype)
                          AND NOT EXISTS (SELECT 1 FROM aktivitet)
                          AND NOT EXISTS (SELECT 1 FROM fasilitet)""")
    if out is None:
        return None
    return out == "t"


def generate(modus):
    """generate build|sync: writes $UT/<modus>.sql. A partial fetch failure (exit
    code 2) still yields complete SQL, with the failure logged in synk_avvik, so
    it is a warning and not an error."""
    skript = "synk.py" if modus == "sync" else "last_inn.py"
    args = [KOMMUNER]

    if is_true(NORMALISER_DEMO):
        res = subprocess.run(py("demo_normalisering/normaliser.py", KOMMUNER, "--ut", os.path.join(UT, "normalisert")))
        if res.returncode != 0:
            log("demo normaliser exited with %d (see messages above)" % res.returncode)
        args += ["--fra-fil", os.path.join(UT, "normalisert")]

    with open(os.path.join(UT, modus + ".sql"), "w") as out:
        res = subprocess.run(py(skript, *args), stdout=out)
    if res.returncode == 2:
        log("%s: some fetches failed (logged in synk_avvik); continuing with the rest" % skript)
    elif res.returncode != 0:
        log("%s failed with exit code %d" % (skript, res.returncode))
        return False
    return True


def do_build():
    log("build: loading %s with last_inn.py" % KOMMUNER)
    return generate("build") and apply(os.path.join(UT, "build.sql"))


def do_sync():
    log("sync: loading %s with synk.py" % KOMMUNER)
    return generate("sync") and apply(os.path.join(UT, "sync.sql"))


def have_matrikkel_credentials():
    return bool(os.environ.get("MATRIKKEL_BRUKER")) and bool(os.environ.get("MATRIKKEL_PASSORD"))


def do_geocode():
    if not have_matrikkel_credentials():
        log("geocode: skipped, MATRIKKEL_BRUKER / MATRIKKEL_PASSORD are not set")
        return True
    log("geocode: querying addresses to look up (MATRIKKEL_MILJO=%s)" % (os.environ.get("MATRIKKEL_MILJO") or "test"))
    adresser = os.path.join(UT, "adresser.txt")
    with open(adresser, "w") as out:
        res = subprocess.run(["psql", "-tA", "-F|", "-f", "geocode_query.sql"], stdout=out)
    if res.returncode != 0:
        log("geocode: the address query failed")
        return False
    if os.path.getsize(adresser) == 0:
        log("geocode: nothing to look up")
        return True
    # The output is one transaction that commits at the very end, so a failed
    # run leaves a truncated file that must not be applied.
    with open(adresser) as inp, open(os.path.join(UT, "matrikkel.sql"), "w") as out:
        res = subprocess.run(py("matrikkel_adresse.py"), stdin=inp, stdout=out)
    if res.returncode != 0:
        log("geocode: matrikkel_adresse.py failed; nothing applied")
        return False
    return apply(os.path.join(UT, "matrikkel.sql"))


def do_gater(kommunenr=()):
    """Fetches all streets from Matrikkel for kommuner in the kommune table, so
    that gate matches Matrikkel for every kommune in the database.
      (no argument)  every kommune in the table (new ones, and a refresh of the rest)
      <kommunenr>... exactly those
    Streets are added and renamed, never deleted: adresse.gate_id points at them.
    A kommune that fails (unknown in Matrikkel, network) is logged in synk_avvik
    and tried again by the next run."""
    if not have_matrikkel_credentials():
        log("gater: skipped, MATRIKKEL_BRUKER / MATRIKKEL_PASSORD are not set")
        return True
    if not kommunenr:
        out = psql_query("SELECT kommunenr FROM kommune ORDER BY kommunenr")
        if out is None:
            log("gater: the kommune query failed")
            return False
        liste = out.split()
    else:
        liste = list(kommunenr)
    if not liste:
        log("gater: no kommuner in the database")
        return True
    log("gater: fetching streets for: %s" % " ".join(liste))
    with open(os.path.join(UT, "gater.sql"), "w") as out:
        res = subprocess.run(py("hent_gater.py", *liste), stdout=out)
    if res.returncode == 2:
        log("gater: some kommuner failed (logged in synk_avvik); continuing with the rest")
    elif res.returncode != 0:
        log("gater: hent_gater.py failed with exit code %d" % res.returncode)
        return False
    return apply(os.path.join(UT, "gater.sql"))


def retention_valid():
    return re.fullmatch(r"[1-9][0-9]*", AVVIK_RETENTION_DAYS) is not None


def prune_avvik():
    """Deletes synk_avvik rows older than AVVIK_RETENTION_DAYS, except those in
    v_synk_avvik_gjeldende (the latest run per source), so a source that stops
    running keeps its current problems visible. Every run adds avvik rows and
    nothing else removes them."""
    if not retention_valid():
        log("prune: AVVIK_RETENTION_DAYS must be a positive whole number, got '%s'" % AVVIK_RETENTION_DAYS)
        return False
    if is_true(DRY_RUN):
        log("DRY_RUN: not pruning synk_avvik")
        return True
    antall = psql_query("""WITH slettet AS (
            DELETE FROM synk_avvik
            WHERE created_at < now() - make_interval(days => %s)
              AND id NOT IN (SELECT id FROM v_synk_avvik_gjeldende)
            RETURNING 1)
        SELECT count(*) FROM slettet""" % AVVIK_RETENTION_DAYS)
    if antall is None:
        log("prune: the delete failed")
        return False
    log("prune: deleted %s synk_avvik row(s) older than %s days" % (antall, AVVIK_RETENTION_DAYS))
    return True


def seconds_until_sync():
    hh, mm = (int(x) for x in SYNK_TID.split(":"))
    naa = datetime.datetime.now()
    maal = naa.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if maal <= naa:
        maal += datetime.timedelta(days=1)
    return int((maal - naa).total_seconds())


def daemon():
    def stop(signum, frame):
        log("stopping")
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    if re.fullmatch(r"([01][0-9]|2[0-3]):[0-5][0-9]", SYNK_TID) is None:
        log("SYNK_TID must be HH:MM, got '%s'" % SYNK_TID)
        return 1
    if not retention_valid():
        log("AVVIK_RETENTION_DAYS must be a positive whole number, got '%s'" % AVVIK_RETENTION_DAYS)
        return 1
    if not wait_for_schema():
        return 1

    tom = vocabulary_empty()
    if tom is None:
        log("could not query the vocabulary tables")
        return 1
    if tom:
        log("no vocabulary in the master yet: initial build")
        if not do_build():
            log("initial build failed; the next start or the nightly run retries if the vocabulary is still empty")
        # Streets for every kommune the build loaded
        do_gater()
        do_geocode()
    else:
        log("vocabulary present: skipping the initial build")

    while True:
        venting = seconds_until_sync()
        log("next sync at %s (in %ds)" % (SYNK_TID, venting))
        time.sleep(venting)

        # Seeds the vocabulary if an earlier build left it empty.
        if vocabulary_empty():
            if not do_build():
                log("build failed")
            do_gater()
        elif not do_sync():
            log("sync failed")
        do_geocode()
        prune_avvik()


def main(argv):
    os.chdir(HER)
    os.makedirs(UT, exist_ok=True)
    if hasattr(time, "tzset"):
        time.tzset()

    install_extra_ca()

    cmd = argv[0] if argv else "daemon"
    if cmd == "daemon":
        return daemon()
    if cmd == "build":
        return 0 if do_build() else 1
    if cmd == "sync":
        return 0 if do_sync() else 1
    if cmd == "geocode":
        return 0 if do_geocode() else 1
    if cmd == "gater":
        return 0 if do_gater(argv[1:]) else 1
    if cmd == "prune":
        return 0 if prune_avvik() else 1
    if cmd == "status":
        return subprocess.run(["psql", "-f", "status.sql"]).returncode
    print(USAGE, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
