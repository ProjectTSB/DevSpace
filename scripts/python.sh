#!/bin/sh
# Run a DevSpace Python script or test with the first `python3` or `python` that starts
# Python 3.9 or newer (the scripts use str.removeprefix), in UTF-8 mode so that output and
# git's UTF-8 are read the same on every OS.
# On native Windows (Git Bash) `python3` can be the Microsoft Store alias, which exits with
# 126; scripts/setup-native.sh accepts either name in the same way.
#
#   sh scripts/python.sh <script.py> [args...]
set -eu
for ds_python in python3 python; do
  if "$ds_python" -c 'import sys; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1; then
    PYTHONUTF8=1 exec "$ds_python" "$@"
  fi
done
printf '%s\n' 'python: Python 3.9 以上を python3 か python で起動できない' >&2
exit 127
