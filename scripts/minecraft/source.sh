#!/bin/sh
# Readable Minecraft source for one version; details are in source.py.
exec sh "$(dirname -- "$0")/../python.sh" "$(dirname -- "$0")/source.py" "$@"
