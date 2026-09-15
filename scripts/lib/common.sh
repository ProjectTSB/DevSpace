#!/bin/sh
: "${DEVSPACE_ROOT:=${PWD}}"; export DEVSPACE_ROOT
ds_die() { printf '%s\n' "setup: $*" >&2; return 1; }
ds_log() { printf '%s\n' "setup: $*"; }
ds_has_control() {
  ds_check_nl='
'
  case $1 in *"$ds_check_nl"*) return 0;; esac
  printf '%s' "$1" | LC_ALL=C grep '[[:cntrl:]]' >/dev/null 2>&1
}
ds_resolve_path() {
  ds_path=$1
  if ds_has_control "$ds_path"; then ds_die "path contains a control character"; return 1; fi
  case $ds_path in
    /*) printf '%s\n' "$ds_path";;
    [A-Za-z]:[\\/]*) case $(uname -s 2>/dev/null || printf unknown) in CYGWIN*|MINGW*|MSYS*) command -v cygpath >/dev/null 2>&1 || { ds_die "cygpath is required for Windows paths"; return 1; }; cygpath -u "$ds_path";; *) ds_die "Windows drive path is not valid on this platform: $ds_path"; return 1;; esac;;
    *) printf '%s/%s\n' "$DEVSPACE_ROOT" "$ds_path";;
  esac
}
ds_repo_path() {
  case $1 in TheSkyBlessing) ds_value=${THE_SKY_BLESSING_PATH:-TheSkyBlessing};; Asset) ds_value=${ASSET_PATH:-Asset};; Asset-AnimatedJava) ds_value=${ANIMATED_JAVA_PATH:-Asset-AnimatedJava};; *) ds_die "unknown repository: $1"; return 1;; esac
  ds_resolve_path "$ds_value"
}
ds_config_load() {
  ds_file=${1:-${DEVSPACE_CONFIG:-$DEVSPACE_ROOT/devspace.local.conf}}; [ -f "$ds_file" ] || return 0
  ds_seen='|'; ds_number=0; ds_cr=$(printf '\r')
  while IFS= read -r ds_line || [ -n "$ds_line" ]; do
    ds_number=$((ds_number + 1)); case $ds_line in *"$ds_cr") ds_line=${ds_line%"$ds_cr"};; esac
    case $ds_line in ''|'#'*) continue;; esac
    if ds_has_control "$ds_line"; then ds_die "$ds_file:$ds_number: control character in config"; return 1; fi
    case $ds_line in *=*) :;; *) ds_die "$ds_file:$ds_number: expected KEY=value"; return 1;; esac
    ds_key=${ds_line%%=*}; ds_value=${ds_line#*=}
    case $ds_key in WORLD_PATH|THE_SKY_BLESSING_PATH|ASSET_PATH|ANIMATED_JAVA_PATH|RESOURCEPACK_URI|JAVA_BIN|JAVA_XMS|JAVA_XMX|SERVER_PORT|ACCEPT_EULA) :;; '') ds_die "$ds_file:$ds_number: empty config key"; return 1;; *) ds_die "$ds_file:$ds_number: unknown config key: $ds_key"; return 1;; esac
    case $ds_seen in *"|$ds_key|"*) ds_die "$ds_file:$ds_number: duplicate config key: $ds_key"; return 1;; esac; ds_seen=$ds_seen$ds_key'|'
    case $ds_key in WORLD_PATH) WORLD_PATH=$ds_value; export WORLD_PATH;; THE_SKY_BLESSING_PATH) THE_SKY_BLESSING_PATH=$ds_value; export THE_SKY_BLESSING_PATH;; ASSET_PATH) ASSET_PATH=$ds_value; export ASSET_PATH;; ANIMATED_JAVA_PATH) ANIMATED_JAVA_PATH=$ds_value; export ANIMATED_JAVA_PATH;; RESOURCEPACK_URI) RESOURCEPACK_URI=$ds_value; export RESOURCEPACK_URI;; JAVA_BIN) JAVA_BIN=$ds_value; export JAVA_BIN;; JAVA_XMS) JAVA_XMS=$ds_value; export JAVA_XMS;; JAVA_XMX) JAVA_XMX=$ds_value; export JAVA_XMX;; SERVER_PORT) SERVER_PORT=$ds_value; export SERVER_PORT;; ACCEPT_EULA) ACCEPT_EULA=$ds_value; export ACCEPT_EULA;; esac
  done < "$ds_file"
}
ds_dir_is_empty() {
  [ -d "$1" ] || return 1
  for ds_item in "$1"/* "$1"/.[!.]* "$1"/..?*; do [ -e "$ds_item" ] || [ -L "$ds_item" ] || continue; return 1; done
  return 0
}
ds_clone_repo() {
  ds_name=$1; ds_url=$2; ds_branch=${3-}
  case $ds_name in TheSkyBlessing|Asset|Asset-AnimatedJava) :;; *) ds_die "unknown repository: $ds_name"; return 1;; esac
  ds_dest=$DEVSPACE_ROOT/$ds_name
  if [ -e "$ds_dest" ] || [ -L "$ds_dest" ]; then
    [ -d "$ds_dest" ] || { ds_die "destination exists and is not a directory: $ds_dest"; return 1; }
    ds_top=$(git -C "$ds_dest" rev-parse --show-toplevel 2>/dev/null || :)
    if [ -n "$ds_top" ]; then
      ds_dest_real=$(CDPATH='' cd -P -- "$ds_dest" 2>/dev/null && pwd) || { ds_die "cannot resolve repository destination: $ds_dest"; return 1; }
      ds_top_real=$(CDPATH='' cd -P -- "$ds_top" 2>/dev/null && pwd) || { ds_die "cannot resolve repository root: $ds_top"; return 1; }
      [ "$ds_top_real" = "$ds_dest_real" ] && return 0
    fi
    ds_dir_is_empty "$ds_dest" || { ds_die "destination exists and is not an independent repository or empty directory: $ds_dest"; return 1; }
  fi
  ds_parent=${ds_dest%/*}; [ "$ds_parent" = "$ds_dest" ] && ds_parent=.; mkdir -p "$ds_parent"
  if [ -n "$ds_branch" ]; then git clone --branch "$ds_branch" "$ds_url" "$ds_dest"; else git clone "$ds_url" "$ds_dest"; fi
}
ds_quote_env() {
  if ds_has_control "$1"; then ds_die "dotenv value contains a control character"; return 1; fi
  printf "'%s'" "$(printf '%s' "$1" | sed "s/'/\\\\'/g")"
}
ds_write_compose_env() (
  ds_env_file=$1; ds_env_mount=$2; ds_env_config=$3; ds_env_dir=${ds_env_file%/*}; mkdir -p "$ds_env_dir"; ds_env_tmp=$ds_env_file.tmp.$$
  trap 'rm -f "$ds_env_tmp"' EXIT HUP INT TERM
  { printf 'TSB_WORLD_MOUNT='; ds_quote_env "$ds_env_mount"; printf '\nTSB_WORLD_CONFIG='; ds_quote_env "$ds_env_config"; printf '\n'; } > "$ds_env_tmp"
  mv "$ds_env_tmp" "$ds_env_file"; trap - EXIT HUP INT TERM
)
