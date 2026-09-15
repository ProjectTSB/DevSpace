#!/bin/sh
# shellcheck disable=SC1090,SC1091,SC2016,SC2030
set -eu
# Fixtures model host and container environments explicitly, independent of the caller.
unset DEVSPACE_ROOT DEVSPACE_CONFIG DEVSPACE_CONTAINER DEVSPACE_WORLD_CONFIG \
  WORLD_PATH THE_SKY_BLESSING_PATH ASSET_PATH ANIMATED_JAVA_PATH \
  RESOURCEPACK_URI JAVA_BIN JAVA_XMS JAVA_XMX SERVER_PORT ACCEPT_EULA
root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT HUP INT TERM
fail() { printf '%s\n' "setup test failed: $*" >&2; exit 1; }
expect_fail() { "$@" >/dev/null 2>&1 && fail "command unexpectedly succeeded: $*"; return 0; }
new_repo() {
  git init -q "$1"
  (CDPATH='' cd "$1" && git config user.email test@example.invalid && git config user.name test && printf x > tracked && git add tracked && git commit -qm initial)
}

# Config values are literal, CRLF is accepted, and input is never evaluated.
(
  DEVSPACE_ROOT=$tmp/config; export DEVSPACE_ROOT; mkdir -p "$DEVSPACE_ROOT"; . "$root/scripts/lib/common.sh"
  printf 'ASSET_PATH=folder with spaces\r\nJAVA_BIN=$(touch %s) # literal\r\n' "$tmp/injected" > "$DEVSPACE_ROOT/devspace.local.conf"
  ds_config_load
  [ "$ASSET_PATH" = 'folder with spaces' ] || fail 'space-containing value changed'
  [ "$JAVA_BIN" = "\$(touch $tmp/injected) # literal" ] || fail 'literal shell text changed'
  [ ! -e "$tmp/injected" ] || fail 'config executed shell syntax'
)
for bad in 'ASSET_PATH=x
ASSET_PATH=y' 'NOT_A_KEY=x' 'malformed'; do
  printf '%s\n' "$bad" > "$tmp/bad.conf"
  expect_fail sh -c 'DEVSPACE_ROOT=$1; export DEVSPACE_ROOT; . "$2/scripts/lib/common.sh"; ds_config_load "$3"' sh "$tmp" "$root" "$tmp/bad.conf"
done
printf 'ASSET_PATH=x\tbad\n' > "$tmp/bad.conf"
expect_fail sh -c 'DEVSPACE_ROOT=$1; export DEVSPACE_ROOT; . "$2/scripts/lib/common.sh"; ds_config_load "$3"' sh "$tmp" "$root" "$tmp/bad.conf"

# An empty target nested inside another repository is still cloneable.
new_repo "$tmp/source"
git init -q "$tmp/parent"; mkdir "$tmp/parent/Asset"
(
  DEVSPACE_ROOT=$tmp/parent; ASSET_PATH='debug override'; export DEVSPACE_ROOT ASSET_PATH; . "$root/scripts/lib/common.sh"
  ds_clone_repo Asset "$tmp/source"
  [ "$(git -C "$tmp/parent/Asset" rev-parse --show-toplevel)" = "$tmp/parent/Asset" ] || fail 'nested empty directory was not cloned'
  [ ! -e "$tmp/parent/debug override" ] || fail 'debug override was used as clone destination'
)

# Existing independent repos, including linked worktrees, are accepted untouched.
preserve=$tmp/preserve; mkdir "$preserve"; new_repo "$preserve/Asset"; git -C "$preserve/Asset" checkout -qb custom; git -C "$preserve/Asset" remote add upstream https://example.invalid/custom.git; printf dirty >> "$preserve/Asset/tracked"
before_status=$(git -C "$preserve/Asset" status --porcelain); before_branch=$(git -C "$preserve/Asset" branch --show-current); before_remotes=$(git -C "$preserve/Asset" remote -v)
(
  DEVSPACE_ROOT=$preserve; ASSET_PATH='elsewhere'; export DEVSPACE_ROOT ASSET_PATH; . "$root/scripts/lib/common.sh"; ds_clone_repo Asset nowhere.invalid
)
[ "$(git -C "$preserve/Asset" status --porcelain)" = "$before_status" ] || fail 'existing repo edits changed'
[ "$(git -C "$preserve/Asset" branch --show-current)" = "$before_branch" ] || fail 'existing repo branch changed'
[ "$(git -C "$preserve/Asset" remote -v)" = "$before_remotes" ] || fail 'existing repo remotes changed'
worktree_root=$tmp/worktree-root; mkdir "$worktree_root"; git -C "$preserve/Asset" worktree add -q "$worktree_root/Asset"
(
  DEVSPACE_ROOT=$worktree_root; export DEVSPACE_ROOT; . "$root/scripts/lib/common.sh"; ds_clone_repo Asset nowhere.invalid
)

# Nonempty plain directories, hidden-only directories, and dangling links are refused.
mkdir "$tmp/plain" "$tmp/hidden"; printf x > "$tmp/plain/file"; printf x > "$tmp/hidden/.dot"; ln -s "$tmp/missing" "$tmp/dangling"
for target in plain hidden dangling; do
  reject_root=$tmp/reject-$target; mkdir "$reject_root"; mv "$tmp/$target" "$reject_root/Asset"
  expect_fail sh -c 'DEVSPACE_ROOT=$1; export DEVSPACE_ROOT; . "$2/scripts/lib/common.sh"; ds_clone_repo Asset nowhere.invalid' sh "$reject_root" "$root"
done

# Dotenv output is atomic and preserves punctuation and Unicode in Compose syntax.
(
  DEVSPACE_ROOT=$tmp; export DEVSPACE_ROOT; . "$root/scripts/lib/common.sh"
  mount="$tmp/world space/日本語/\$cash/it's\\here #1"; config="relative/日本語/\$cash/it's\\here #1"
  ds_write_compose_env "$tmp/generated/.env" "$mount" "$config"
  grep -F "TSB_WORLD_MOUNT='$tmp/world space/日本語/\$cash/it\\'s\\here #1'" "$tmp/generated/.env" >/dev/null || fail 'mount dotenv value changed'
  grep -F "TSB_WORLD_CONFIG='relative/日本語/\$cash/it\\'s\\here #1'" "$tmp/generated/.env" >/dev/null || fail 'config dotenv value changed'
  [ ! -e "$tmp/generated/.env.tmp.$$" ] || fail 'dotenv temporary file remained'
)

# Full setup refuses a missing explicit world and does not touch an old default-world link.
fixture=$tmp/fixture; mkdir -p "$fixture/scripts/lib" "$fixture/.devcontainer"; cp "$root/scripts/setup.sh" "$fixture/scripts/setup.sh"; cp "$root/scripts/lib/common.sh" "$fixture/scripts/lib/common.sh"
for repo in TheSkyBlessing Asset Asset-AnimatedJava; do new_repo "$fixture/$repo"; done
printf 'WORLD_PATH=missing world\n' > "$fixture/devspace.local.conf"
expect_fail "$fixture/scripts/setup.sh" --container
[ ! -e "$fixture/missing world" ] || fail 'missing explicit world was created'
mkdir -p "$tmp/external" "$fixture/.runtime"; ln -s "$tmp/external" "$fixture/.runtime/world"; : > "$tmp/external/sentinel"; : > "$fixture/devspace.local.conf"
"$fixture/scripts/setup.sh" --container >/dev/null
[ -L "$fixture/.runtime/world" ] && [ -e "$tmp/external/sentinel" ] || fail 'old world link was changed'
grep -Fx "TSB_WORLD_MOUNT='$fixture/.runtime'" "$fixture/.devcontainer/.env" >/dev/null || fail 'unset world mount is wrong'
grep -Fx "TSB_WORLD_CONFIG=''" "$fixture/.devcontainer/.env" >/dev/null || fail 'unset world config is wrong'
cp "$fixture/.devcontainer/.env" "$tmp/before.env"
expect_fail env DEVSPACE_CONTAINER=1 "$fixture/scripts/setup.sh" --container
cmp "$tmp/before.env" "$fixture/.devcontainer/.env" || fail 'container rewrote host mount config'

# CLI world selection is relative to the caller, persists, and preserves other settings.
cli_world="世界 space/\$cash/it's\\here #1"
mkdir -p "$tmp/caller/$cli_world"
printf '# personal settings\r\nACCEPT_EULA=true\r\nWORLD_PATH=old\r\nJAVA_XMX=3G' > "$fixture/devspace.local.conf"
(
  cd "$tmp/caller"
  "$fixture/scripts/setup.sh" --container "$cli_world" >/dev/null
)
(
  DEVSPACE_ROOT=$fixture; export DEVSPACE_ROOT; . "$root/scripts/lib/common.sh"; ds_config_load
  [ "$WORLD_PATH" = "$tmp/caller/$cli_world" ] || fail 'CLI path not resolved from caller directory'
  [ "$ACCEPT_EULA" = true ] && [ "$JAVA_XMX" = 3G ] || fail 'other config settings changed'
  ds_write_compose_env "$tmp/expected.env" "$WORLD_PATH" "$WORLD_PATH"
)
cmp "$tmp/expected.env" "$fixture/.devcontainer/.env" || fail 'CLI config and mount differ'
[ "$(grep -c '^WORLD_PATH=' "$fixture/devspace.local.conf")" -eq 1 ] || fail 'duplicate world key'
grep -q '^# personal settings' "$fixture/devspace.local.conf" || fail 'config comment lost'
cp "$fixture/devspace.local.conf" "$tmp/cli.conf"
"$fixture/scripts/setup.sh" --container >/dev/null
cmp "$tmp/cli.conf" "$fixture/devspace.local.conf" || fail 'omitted argument changed selection'
cp "$fixture/.devcontainer/.env" "$tmp/cli.env"
expect_fail "$fixture/scripts/setup.sh" --container "$tmp/missing-world"
expect_fail "$fixture/scripts/setup.sh" "$tmp/external" "$tmp/external"
expect_fail "$fixture/scripts/setup.sh" --default-world "$tmp/external"
expect_fail "$fixture/scripts/setup.sh" ''
expect_fail "$fixture/scripts/setup.sh" --invalid
expect_fail env DEVSPACE_CONTAINER=1 "$fixture/scripts/setup.sh" "$tmp/external"
expect_fail env DEVSPACE_CONTAINER=1 "$fixture/scripts/setup.sh" --default-world
cmp "$tmp/cli.conf" "$fixture/devspace.local.conf" || fail 'invalid arguments changed selection'
cmp "$tmp/cli.env" "$fixture/.devcontainer/.env" || fail 'invalid arguments changed mount'
"$fixture/scripts/setup.sh" --container --default-world >/dev/null
grep -Fx 'WORLD_PATH=' "$fixture/devspace.local.conf" >/dev/null || fail 'default world not saved'
grep -Fx "TSB_WORLD_MOUNT='$fixture/.runtime'" "$fixture/.devcontainer/.env" >/dev/null || fail 'default mount not restored'

# Native invocation works with no config yet, and -- permits dash-prefixed paths.
mkdir "$tmp/caller/-world"
(
  cd "$tmp/caller"
  DEVSPACE_CONFIG=$fixture/native.conf "$fixture/scripts/setup.sh" -- -world >/dev/null
)
grep -Fx "WORLD_PATH=$tmp/caller/-world" "$fixture/native.conf" >/dev/null || fail 'native selection not saved'
"$fixture/scripts/setup.sh" --help >/dev/null

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  docker compose --env-file "$tmp/generated/.env" -f "$root/.devcontainer/compose.yaml" config >/dev/null
  docker compose --env-file "$fixture/.devcontainer/.env" -f "$root/.devcontainer/compose.yaml" config >/dev/null
fi
printf '%s\n' 'setup tests: ok'
