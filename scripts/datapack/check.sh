#!/bin/sh
# Check of a working copy's mcfunction; rules and options are in check.py.
exec sh "$(dirname -- "$0")/../python.sh" "$(dirname -- "$0")/check.py" "$@"
