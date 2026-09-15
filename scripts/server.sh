#!/bin/sh
set -eu
BASE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd -P)
. "$BASE/lib/runtime.sh"
runtime_init
case ${1-} in
 --check) [ "$#" -eq 1 ] || { runtime_die "usage: server.sh [--check|--prepare]"; exit 2; }; runtime_check; exit;;
 --prepare) [ "$#" -eq 1 ] || { runtime_die "usage: server.sh [--check|--prepare]"; exit 2; }; trap 'runtime_cleanup' 0 1 2 3 15; runtime_prepare_locked false; trap - 0 1 2 3 15; exit;;
 '') ;;
 *) runtime_die "usage: server.sh [--check|--prepare]"; exit 2;;
esac
trap 'runtime_cleanup' 0 1 2 3 15
runtime_prepare_locked true
runtime_check_eula; runtime_check_java; runtime_ensure_jar; runtime_fetch_resourcepack
cd "$R_RUNTIME"
exec 3<&0
"${JAVA_BIN:-java}" "-Xms${JAVA_XMS:-2G}" "-Xmx${JAVA_XMX:-4G}" -jar "$R_CACHE/server-1.20.4.jar" nogui <&3 &
R_SERVER_PID=$!
exec 3<&-
trap 'kill -HUP "$R_SERVER_PID" 2>/dev/null || :; wait "$R_SERVER_PID" 2>/dev/null || :; runtime_cleanup; exit 129' 1
trap 'kill -TERM "$R_SERVER_PID" 2>/dev/null || :; wait "$R_SERVER_PID" 2>/dev/null || :; runtime_cleanup; exit 130' 2
trap 'kill -TERM "$R_SERVER_PID" 2>/dev/null || :; wait "$R_SERVER_PID" 2>/dev/null || :; runtime_cleanup; exit 143' 15
set +e; wait "$R_SERVER_PID"; status=$?; set -e
runtime_cleanup; trap - 0 1 2 3 15; exit "$status"
