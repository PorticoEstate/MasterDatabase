#!/usr/bin/env bash
# Thin shim over etl.py, which holds the ETL orchestration (see its header for
# the commands and settings):
#
#   run.sh [daemon|build|sync|geocode|gater [kommunenr...]|prune|status]
#
# The default command is daemon.
exec python3 "$(dirname "${BASH_SOURCE[0]}")/etl.py" "$@"
