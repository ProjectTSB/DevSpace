#!/bin/sh
set -eu
BASE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd -P)
exec python3 "$BASE/verification/run.py" "$@"
