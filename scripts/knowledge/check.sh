#!/bin/sh
# Check of a working copy's knowledge documents; options are in check.py.
exec sh "$(dirname -- "$0")/../python.sh" "$(dirname -- "$0")/check.py" "$@"
