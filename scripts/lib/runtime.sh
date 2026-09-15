#!/bin/sh
# POSIX runtime helpers; Windows junction handling is isolated below.
runtime_die() { printf 'runtime: %s\n' "$*" >&2; return 1; }
runtime_log() { printf 'runtime: %s\n' "$*" >&2; }

runtime_init() {
 R_ROOT=${DEVSPACE_ROOT:-}; [ -n "$R_ROOT" ] || R_ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd -P) || return 1
 DEVSPACE_ROOT=$R_ROOT; export DEVSPACE_ROOT
 . "$R_ROOT/scripts/lib/common.sh" || return 1
 ds_config_load "${DEVSPACE_CONFIG:-$R_ROOT/devspace.local.conf}" || return 1
 R_RUNTIME=$R_ROOT/.runtime; R_CACHE=$R_ROOT/.cache
 R_PACKS_FILE=$R_RUNTIME/.packs.$$; R_WORLD_RECORD=$R_RUNTIME/managed-active-world.txt
}
runtime_abs_dir() { (CDPATH='' cd -- "$1" 2>/dev/null && pwd -P); }
runtime_discover() {
 out=$1; : > "$out" || return 1
 for repo_name in TheSkyBlessing Asset Asset-AnimatedJava; do
  repo=$(ds_repo_path "$repo_name") || return 1
  [ -d "$repo" ] || { runtime_die "repository is missing: $repo"; return 1; }
  found=false
  for pack in "$repo"/*; do
   [ -d "$pack" ] && [ -f "$pack/pack.mcmeta" ] || continue
   [ -r "$pack/pack.mcmeta" ] || { runtime_die "pack metadata is not readable: $pack/pack.mcmeta"; return 1; }
   target=$(runtime_abs_dir "$pack") || return 1; name=${pack##*/}
   ds_has_control "$name$target" && { runtime_die "pack name or path contains a control character: $name"; return 1; }
   case $name in .|..) runtime_die "invalid pack directory name: $name"; return 1;; esac
   if awk -F '\t' -v n="$name" '$1==n {x=1} END {exit !x}' "$out"; then runtime_die "duplicate pack name: $name"; return 1; fi
   printf '%s\t%s\n' "$name" "$target" >> "$out" || return 1; found=true
  done
  [ "$found" = true ] || { runtime_die "no immediate pack directories found in: $repo"; return 1; }
 done
}
runtime_is_windows() { case $(uname -s 2>/dev/null) in MINGW*|MSYS*|CYGWIN*) return 0;; *) return 1;; esac; }
runtime_link_target() {
 link=$1
 if [ -L "$link" ]; then readlink "$link"; return; fi
 if runtime_is_windows && [ -e "$link" ]; then
  win=$(cygpath -w "$link") || return 1
  DEVSPACE_LINK_PATH=$win MSYS2_ARG_CONV_EXCL='*' powershell.exe -NoProfile -NonInteractive -Command '$ErrorActionPreference = "Stop"; (Get-Item -LiteralPath $env:DEVSPACE_LINK_PATH).Target' 2>/dev/null | tr -d '\r'; return
 fi
 return 1
}
runtime_raw_target() {
 link=$1; raw=$(runtime_link_target "$link") || return 1
 case $raw in /*) printf '%s\n' "$raw";; [A-Za-z]:\\*) cygpath -u "$raw";; *) printf '%s/%s\n' "${link%/*}" "$raw";; esac
}
runtime_link_matches() { [ "$(runtime_raw_target "$1" 2>/dev/null)" = "$2" ]; }
runtime_make_link() {
 target=$1 link=$2
 if runtime_is_windows; then
  command -v cygpath >/dev/null 2>&1 || { runtime_die "cygpath is required for Windows junctions"; return 1; }
  DEVSPACE_LINK_PATH=$(cygpath -w "$link") DEVSPACE_LINK_TARGET=$(cygpath -w "$target") MSYS2_ARG_CONV_EXCL='*' powershell.exe -NoProfile -NonInteractive -Command '$ErrorActionPreference = "Stop"; New-Item -ItemType Junction -Path $env:DEVSPACE_LINK_PATH -Target $env:DEVSPACE_LINK_TARGET | Out-Null' || { runtime_die "could not create junction: $link"; return 1; }
 else ln -s "$target" "$link" || { runtime_die "could not create symlink: $link"; return 1; }; fi
}
runtime_remove_link() {
 if [ -L "$1" ]; then rm -f -- "$1"
 elif runtime_is_windows; then DEVSPACE_LINK_PATH=$(cygpath -w "$1") MSYS2_ARG_CONV_EXCL='*' powershell.exe -NoProfile -NonInteractive -Command '$ErrorActionPreference = "Stop"; [System.IO.Directory]::Delete($env:DEVSPACE_LINK_PATH, $false)'
 else return 1; fi
}
runtime_select_world() {
 configured=${WORLD_PATH-}
 if [ "${DEVSPACE_CONTAINER:-0}" = 1 ] && [ "${DEVSPACE_WORLD_CONFIG-}" != "$configured" ]; then
  runtime_die "container world mount identity does not match WORLD_PATH; rebuild the container"; return 1
 fi
 if [ -n "$configured" ]; then
  if [ "${DEVSPACE_CONTAINER:-0}" = 1 ]; then
   [ -d /workspaces/.tsb-world ] || { runtime_die "container world mount is missing"; return 1; }; R_WORLD=/workspaces/.tsb-world
  else
   configured_abs=$(ds_resolve_path "$configured") || return 1
   [ -d "$configured_abs" ] || { runtime_die "WORLD_PATH is not an existing directory: $configured_abs"; return 1; }
   R_WORLD=$(runtime_abs_dir "$configured_abs") || return 1
  fi
  R_WORLD_EXTERNAL=true
 else R_WORLD=$R_RUNTIME/world; R_WORLD_EXTERNAL=false; fi
 R_INVENTORY=$R_WORLD/.devspace-managed-packs.tsv
}
runtime_validate_world_link() {
 rw=$R_RUNTIME/active-world
 if [ -e "$rw" ] || [ -L "$rw" ]; then
  [ -f "$R_WORLD_RECORD" ] || { runtime_die "$rw exists and is not managed"; return 1; }
  old=$(sed -n '1p' "$R_WORLD_RECORD"); runtime_link_matches "$rw" "$old" || { runtime_die "$rw was changed outside DevSpace"; return 1; }
 fi
}
runtime_old_target() {
 name=$1
 [ -f "$R_INVENTORY" ] || return 1
 awk -F '\t' -v n="$name" '$1==n {print $2; exit}' "$R_INVENTORY"
}
runtime_validate_conflicts() {
 dp=$R_WORLD/datapacks
 while IFS="$(printf '\t')" read -r name target; do
  path=$dp/$name; [ -e "$path" ] || [ -L "$path" ] || continue
  runtime_link_matches "$path" "$target" && continue
  old=$(runtime_old_target "$name" 2>/dev/null || :)
  [ -n "$old" ] && runtime_link_matches "$path" "$old" || { runtime_die "unmanaged datapack conflict: $path"; return 1; }
 done < "$R_PACKS_FILE"
}
runtime_write_property() {
 key=$1 value=$2 file=$R_RUNTIME/server.properties tmp=$R_RUNTIME/server.properties.tmp.$$
 if [ -f "$file" ]; then awk -F= -v k="$key" '$1 != k {print}' "$file" > "$tmp" || return 1; else : > "$tmp" || return 1; fi
 printf '%s=%s\n' "$key" "$value" >> "$tmp" && mv -f "$tmp" "$file"
}
runtime_write_allowed() {
 file=$R_RUNTIME/allowed_symlinks.txt tmp=$file.tmp.$$
 : > "$tmp" || return 1
 if [ -f "$file" ]; then
  skip=false
  while IFS= read -r line || [ -n "$line" ]; do
   if [ "$skip" = true ]; then skip=false; continue; fi
   case $line in '# DevSpace managed:'*) skip=true;; *) printf '%s\n' "$line" >> "$tmp";; esac
  done < "$file"
 fi
 while IFS="$(printf '\t')" read -r name target; do
  allowed=$target; runtime_is_windows && allowed=$(cygpath -w "$target")
  printf '# DevSpace managed: %s\n[prefix]%s\n' "$allowed" "$allowed" >> "$tmp"
 done < "$R_PACKS_FILE"
 allowed=$R_WORLD; runtime_is_windows && allowed=$(cygpath -w "$R_WORLD")
 printf '# DevSpace managed: %s\n[prefix]%s\n' "$allowed" "$allowed" >> "$tmp"
 mv -f "$tmp" "$file"
}
runtime_prepare() {
 mkdir -p "$R_RUNTIME" "$R_CACHE" || return 1
 runtime_select_world && runtime_discover "$R_PACKS_FILE" && runtime_validate_world_link && runtime_validate_conflicts || return 1
 [ -d "$R_WORLD" ] || mkdir -p "$R_WORLD" || return 1
 R_WORLD=$(runtime_abs_dir "$R_WORLD") || return 1; R_INVENTORY=$R_WORLD/.devspace-managed-packs.tsv
 rw=$R_RUNTIME/active-world
 if [ -e "$rw" ] || [ -L "$rw" ]; then runtime_link_matches "$rw" "$R_WORLD" || { runtime_remove_link "$rw" && runtime_make_link "$R_WORLD" "$rw" || return 1; }; else runtime_make_link "$R_WORLD" "$rw" || return 1; fi
 printf '%s\n' "$R_WORLD" > "$R_WORLD_RECORD" || return 1
 dp=$R_WORLD/datapacks; mkdir -p "$dp" || return 1
 if [ -f "$R_INVENTORY" ]; then
  while IFS="$(printf '\t')" read -r name old; do
   new=$(awk -F '\t' -v n="$name" '$1==n {print $2; exit}' "$R_PACKS_FILE")
   if [ -z "$new" ] || [ "$new" != "$old" ]; then
    if runtime_link_matches "$dp/$name" "$old"; then runtime_remove_link "$dp/$name" || return 1; fi
   fi
  done <<EOF
$(sed -n '1,$p' "$R_INVENTORY")
EOF
 fi
 inv=$R_WORLD/.devspace-managed-packs.tsv.tmp.$$
 : > "$inv" || return 1
 while IFS="$(printf '\t')" read -r name target; do
  old=$(runtime_old_target "$name" 2>/dev/null || :)
  if runtime_link_matches "$dp/$name" "$target"; then [ "$old" = "$target" ] && printf '%s\t%s\n' "$name" "$target" >> "$inv"; continue; fi
  [ -e "$dp/$name" ] || [ -L "$dp/$name" ] || { runtime_make_link "$target" "$dp/$name" || return 1; printf '%s\t%s\n' "$name" "$target" >> "$inv"; }
 done < "$R_PACKS_FILE"
 mv -f "$inv" "$R_INVENTORY" || return 1
 runtime_write_allowed && runtime_write_property level-name active-world && runtime_write_property server-port "${SERVER_PORT:-25565}" || return 1
 rm -f "$R_PACKS_FILE"
}
runtime_sha1() {
 if command -v sha1sum >/dev/null 2>&1; then raw=$(sha1sum "$1") || return 1
 elif command -v shasum >/dev/null 2>&1; then raw=$(shasum -a 1 "$1") || return 1
 else runtime_die "sha1sum or shasum is required"; return 1; fi
 sum=${raw%% *}
 [ "${#sum}" -eq 40 ] || { runtime_die "invalid SHA-1 output"; return 1; }
 case $sum in *[!0123456789abcdefABCDEF]*) runtime_die "invalid SHA-1 output"; return 1;; esac
 printf '%s\n' "$sum" | tr 'A-F' 'a-f'
}
runtime_fetch_resourcepack() {
 uri=${RESOURCEPACK_URI:-https://github.com/ProjectTSB/TSB-ResourcePack/releases/download/dev/resources.zip}; tmp=$R_CACHE/resources.zip.tmp.$$
 command -v curl >/dev/null 2>&1 || { runtime_die "curl is required to fetch the resource pack"; return 1; }
 curl -fL -o "$tmp" "$uri" || { rm -f "$tmp"; runtime_die "resource pack download failed: $uri"; return 1; }
 sum=$(runtime_sha1 "$tmp") || { rm -f "$tmp"; return 1; }; mv -f "$tmp" "$R_CACHE/resources.zip" || return 1
 file=$R_RUNTIME/server.properties prop_tmp=$R_RUNTIME/server.properties.tmp.$$
 if [ -f "$file" ]; then awk -F= '$1!="resource-pack" && $1!="resource-pack-sha1" {print}' "$file" > "$prop_tmp" || return 1; else : > "$prop_tmp" || return 1; fi
 printf 'resource-pack=%s\nresource-pack-sha1=%s\n' "$uri" "$sum" >> "$prop_tmp" && mv -f "$prop_tmp" "$file" || return 1
}
runtime_ensure_jar() {
 jar=$R_CACHE/server-1.20.4.jar expected=8dd1a28015f51b1803213892b50b7b4fc76e594d
 [ -f "$jar" ] && [ "$(runtime_sha1 "$jar")" = "$expected" ] && return 0
 command -v curl >/dev/null 2>&1 || { runtime_die "download Minecraft 1.20.4 server.jar manually to $jar"; return 1; }
 tmp=$jar.tmp.$$
 curl -fL -o "$tmp" https://piston-data.mojang.com/v1/objects/8dd1a28015f51b1803213892b50b7b4fc76e594d/server.jar || { rm -f "$tmp"; runtime_die "server jar download failed; download it manually to $jar"; return 1; }
 [ "$(runtime_sha1 "$tmp")" = "$expected" ] || { rm -f "$tmp"; runtime_die "downloaded server jar checksum mismatch"; return 1; }
 mv -f "$tmp" "$jar"
}
runtime_check_java() {
 j=${JAVA_BIN:-java}; command -v "$j" >/dev/null 2>&1 || [ -x "$j" ] || { runtime_die "Java was not found: $j"; return 1; }
 v=$("$j" -version 2>&1 | sed -n '1p') || { runtime_die "Java could not be executed: $j"; return 1; }
 major=$(printf '%s\n' "$v" | sed 's/^[^0-9]*//; s/^1\.//; s/[^0-9].*$//')
 case $major in ''|*[!0-9]*) runtime_die "could not determine Java version: $v"; return 1;; esac
 [ "$major" -ge 17 ] || { runtime_die "Java 17 or newer is required (found $major)"; return 1; }
}
runtime_check_eula() {
 if [ "${ACCEPT_EULA:-false}" = true ]; then tmp=$R_RUNTIME/eula.txt.tmp.$$; printf 'eula=true\n' > "$tmp" && mv -f "$tmp" "$R_RUNTIME/eula.txt"; return; fi
 [ -f "$R_RUNTIME/eula.txt" ] && awk -F= '$1=="eula"&&$2=="true" {x=1} END {exit !x}' "$R_RUNTIME/eula.txt" && return 0
 runtime_die "accept the Minecraft EULA, then set ACCEPT_EULA=true or eula=true in .runtime/eula.txt"
}
runtime_acquire_locks() {
 R_RUNTIME_LOCK=$R_RUNTIME/server.lock; R_WORLD_LOCK=$R_WORLD/.devspace-server.lock
 R_RUNTIME_LOCK_HELD=false; R_WORLD_LOCK_HELD=false
 for lock_kind in runtime world; do
  case $lock_kind in runtime) lock=$R_RUNTIME_LOCK;; world) lock=$R_WORLD_LOCK;; esac
  if ! mkdir "$lock" 2>/dev/null; then
   runtime_die "server lock is occupied: $lock (remove it manually only after verifying no server is running)"; runtime_release_locks; return 1
  fi
  printf '%s\n' "$$" > "$lock/pid" || { runtime_release_locks; return 1; }
  case $lock_kind in runtime) R_RUNTIME_LOCK_HELD=true;; world) R_WORLD_LOCK_HELD=true;; esac
 done
}
runtime_release_one_lock() { lock=$1; [ "$(sed -n '1p' "$lock/pid" 2>/dev/null || :)" = "$$" ] && { rm -f "$lock/pid"; rmdir "$lock" 2>/dev/null || :; }; }
runtime_release_locks() {
 [ "${R_WORLD_LOCK_HELD:-false}" = true ] && runtime_release_one_lock "$R_WORLD_LOCK"
 [ "${R_RUNTIME_LOCK_HELD:-false}" = true ] && runtime_release_one_lock "$R_RUNTIME_LOCK"
 R_WORLD_LOCK_HELD=false; R_RUNTIME_LOCK_HELD=false
}
runtime_cleanup() {
 runtime_release_locks
 rm -f "$R_PACKS_FILE" "$R_CACHE/resources.zip.tmp.$$" "$R_CACHE/server-1.20.4.jar.tmp.$$" "$R_RUNTIME/server.properties.tmp.$$" "$R_RUNTIME/allowed_symlinks.txt.tmp.$$" 2>/dev/null || :
}
runtime_prepare_locked() {
 keep=${1:-false}; port=${SERVER_PORT:-25565}
 case $port in ''|*[!0-9]*|??????*) runtime_die "SERVER_PORT must be an integer from 1 to 65535"; return 1;; esac
 [ "$port" -ge 1 ] && [ "$port" -le 65535 ] || { runtime_die "SERVER_PORT must be an integer from 1 to 65535"; return 1; }
 mkdir -p "$R_RUNTIME" "$R_CACHE" || return 1
 runtime_select_world && runtime_validate_world_link || return 1
 [ -d "$R_WORLD" ] || { [ "$R_WORLD_EXTERNAL" = false ] && mkdir -p "$R_WORLD"; } || return 1
 R_WORLD=$(runtime_abs_dir "$R_WORLD") || return 1; R_INVENTORY=$R_WORLD/.devspace-managed-packs.tsv
 runtime_acquire_locks || return 1
 runtime_prepare || { runtime_release_locks; return 1; }
 [ "$keep" = true ] || runtime_release_locks
}
runtime_check() {
 runtime_select_world || return 1; tmp=${TMPDIR:-/tmp}/devspace-packs.$$
 runtime_discover "$tmp" || { rm -f "$tmp"; return 1; }
 runtime_log "root=$R_ROOT"; runtime_log "world=$R_WORLD"
 for repo_name in TheSkyBlessing Asset Asset-AnimatedJava; do runtime_log "repo.$repo_name=$(ds_repo_path "$repo_name")"; done
 runtime_log "packs=$(wc -l < "$tmp" | tr -d ' ')"; runtime_log "server-port=${SERVER_PORT:-25565}"
 rm -f "$tmp"
}
