#!/bin/sh
# INDEX of a working copy's knowledge; options are in index.py.
exec sh "$(dirname -- "$0")/../python.sh" "$(dirname -- "$0")/index.py" "$@"
