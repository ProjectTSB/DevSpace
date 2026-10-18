#!/bin/sh
set -eu
BASE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd -P)
exec sh "$BASE/python.sh" "$BASE/verification/run.py" "$@"
