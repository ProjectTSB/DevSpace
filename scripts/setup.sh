#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd); DEVSPACE_ROOT=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd); export DEVSPACE_ROOT
# shellcheck source=scripts/lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"
setup_main() {
  setup_container=0; setup_world_given=0; setup_options=1; setup_world_arg=
  for setup_arg in "$@"; do
    if [ "$setup_options" -eq 1 ]; then
      case $setup_arg in
        --container) setup_container=1; continue;;
        --) setup_options=0; continue;;
        --help|-h) printf '%s\n' 'Usage: sh scripts/setup.sh [--container] [WORLD_PATH | --default-world]' 'WORLD_PATH is an existing directory, relative to your current directory.' 'The selection is saved; omit it to reuse it. Use --default-world to reset.'; return 0;;
        --default-world) [ "$setup_world_given" -eq 0 ] || { ds_die 'specify only one world'; return 1; }; setup_world_given=1; continue;;
        -*) ds_die "unknown option: $setup_arg (use -- before a path starting with -)"; return 1;;
      esac
    fi
    [ "$setup_world_given" -eq 0 ] || { ds_die 'specify only one world'; return 1; }
    [ -n "$setup_arg" ] || { ds_die 'world path is empty; use --default-world to reset'; return 1; }
    setup_world_given=1; setup_world_arg=$setup_arg
  done
  if [ "$setup_container" -eq 1 ] && [ "${DEVSPACE_CONTAINER:-}" = 1 ]; then ds_die "--container must be run on the host before opening the Dev Container"; return 1; fi
  if [ "$setup_world_given" -eq 1 ] && [ "${DEVSPACE_CONTAINER:-}" = 1 ]; then ds_die 'select the world on the host, then rebuild the Dev Container'; return 1; fi
  ds_config_load
  if [ "$setup_world_given" -eq 1 ]; then
    WORLD_PATH=
    if [ -n "$setup_world_arg" ]; then
      ds_has_control "$setup_world_arg" && { ds_die 'world path contains a control character'; return 1; }
      WORLD_PATH=$(CDPATH='' cd -- "$setup_world_arg" 2>/dev/null && pwd -P) || { ds_die "world path is not an existing directory: $setup_world_arg"; return 1; }
      case $(uname -s) in CYGWIN*|MINGW*|MSYS*) WORLD_PATH=$(cygpath -m "$WORLD_PATH");; esac
      ds_has_control "$WORLD_PATH" && { ds_die 'resolved world path contains a control character'; return 1; }
    fi
    export WORLD_PATH
  fi
  ds_clone_repo TheSkyBlessing https://github.com/ProjectTSB/TheSkyBlessing.git
  ds_clone_repo Asset https://github.com/ProjectTSB/Asset.git
  ds_clone_repo Asset-AnimatedJava https://github.com/ProjectTSB/Asset-AnimatedJava.git dist
  mkdir -p "$DEVSPACE_ROOT/.runtime" "$DEVSPACE_ROOT/.cache"
  if [ "$setup_world_given" -eq 1 ]; then
    setup_save_world || return 1
    ds_log "saved world: ${WORLD_PATH:-default (.runtime/world)}"
  fi
  if [ "$setup_container" -eq 1 ]; then
    if [ -n "${WORLD_PATH:-}" ]; then setup_world=$(ds_resolve_path "$WORLD_PATH") || return 1; [ -d "$setup_world" ] || { ds_die "configured world path is not an existing directory: $setup_world"; return 1; }; else setup_world=$DEVSPACE_ROOT/.runtime; fi
    setup_mount=$setup_world; case $(uname -s 2>/dev/null || printf unknown) in CYGWIN*|MINGW*|MSYS*) setup_mount=$(cygpath -m "$setup_world");; esac
    ds_write_compose_env "$DEVSPACE_ROOT/.devcontainer/.env" "$setup_mount" "${WORLD_PATH:-}"; ds_log "wrote .devcontainer/.env"
  fi
  ds_log "setup complete"
}
setup_save_world() (
  setup_config=${DEVSPACE_CONFIG:-$DEVSPACE_ROOT/devspace.local.conf}
  setup_tmp=$(mktemp "$setup_config.tmp.XXXXXX") || return 1
  trap 'rm -f "$setup_tmp"' 0 1 2 3 15
  if [ -f "$setup_config" ]; then
    awk -F= '$1 != "WORLD_PATH" {print}' "$setup_config" > "$setup_tmp" || return 1
  fi
  printf 'WORLD_PATH=%s\n' "$WORLD_PATH" >> "$setup_tmp" || return 1
  mv -f "$setup_tmp" "$setup_config"
)
if [ "${DEVSPACE_SETUP_LIBRARY:-0}" != 1 ]; then setup_main "$@"; fi
