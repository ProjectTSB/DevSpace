#!/bin/sh
set -eu
# Fixtures model host and container environments explicitly, independent of the caller.
unset DEVSPACE_ROOT DEVSPACE_CONFIG DEVSPACE_CONTAINER DEVSPACE_WORLD_CONFIG \
  WORLD_PATH THE_SKY_BLESSING_PATH ASSET_PATH ANIMATED_JAVA_PATH \
  RESOURCEPACK_URI JAVA_BIN JAVA_XMS JAVA_XMX SERVER_PORT ACCEPT_EULA
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd -P)
T=$(mktemp -d); trap 'rm -rf "$T"' 0 1 2 3 15
passed=0
fail(){ echo "FAIL: $*" >&2; exit 1; }
fixture(){
 F=$T/$1; mkdir -p "$F/scripts/lib" "$F/TheSkyBlessing/Core Pack" "$F/Asset/Asset" "$F/Asset-AnimatedJava/AnimatedJava"
 cp "$ROOT/scripts/lib/common.sh" "$F/scripts/lib/common.sh"; cp "$ROOT/scripts/lib/runtime.sh" "$F/scripts/lib/runtime.sh"; cp "$ROOT/scripts/server.sh" "$F/scripts/server.sh"
 : > "$F/TheSkyBlessing/Core Pack/pack.mcmeta"; : > "$F/Asset/Asset/pack.mcmeta"; : > "$F/Asset-AnimatedJava/AnimatedJava/pack.mcmeta"
}
run(){ DEVSPACE_ROOT=$F DEVSPACE_CONFIG=$F/devspace.local.conf sh "$F/scripts/server.sh" "$@"; }
fails(){ "$@" >/dev/null 2>&1 && fail "unexpected success: $*" || :; }
link(){ [ -L "$1" ] || fail "missing link: $1"; }
pass(){ passed=$((passed+1)); }

fixture check; run --check >/dev/null; [ ! -e "$F/.runtime" ] || fail 'check mutated runtime'
rm -rf "$F/Asset"; fails run --check; [ ! -e "$F/.runtime" ] || fail 'failed check mutated runtime'; pass

# Rebuilt containers accept the matching default world and reject stale mount identity.
fixture container
DEVSPACE_CONTAINER=1 DEVSPACE_WORLD_CONFIG= run --prepare
link "$F/.runtime/active-world"
printf 'WORLD_PATH=host world\n' > "$F/devspace.local.conf"
fails env DEVSPACE_CONTAINER=1 DEVSPACE_WORLD_CONFIG=old DEVSPACE_ROOT="$F" DEVSPACE_CONFIG="$F/devspace.local.conf" sh "$F/scripts/server.sh" --prepare
[ "$(readlink "$F/.runtime/active-world")" = "$F/.runtime/world" ] || fail 'stale mount changed active world'
[ ! -e "$F/.runtime/server.lock" ] || fail 'stale mount leaked lock'; pass

fixture names; mv "$F/Asset/Asset" "$F/Asset/資産 dollar\$'s"; mkdir -p "$F/.runtime"
printf 'motd=keep\nserver-port=1\n' > "$F/.runtime/server.properties"; run --prepare
link "$F/.runtime/world/datapacks/Core Pack"; link "$F/.runtime/world/datapacks/資産 dollar\$'s"
grep -q '^motd=keep$' "$F/.runtime/server.properties" || fail 'property lost'
[ "$(grep '^server-port=' "$F/.runtime/server.properties")" = server-port=25565 ] || fail 'port wrong'; pass

# Add/delete/rename; nested overlay is not separately scanned.
mkdir -p "$F/Asset-AnimatedJava/New Model/overlay/data"; : > "$F/Asset-AnimatedJava/New Model/pack.mcmeta"; run --prepare; link "$F/.runtime/world/datapacks/New Model"
rm -rf "$F/Asset-AnimatedJava/New Model"; run --prepare; [ ! -e "$F/.runtime/world/datapacks/New Model" ] || fail 'removed link remains'
mv "$F/TheSkyBlessing/Core Pack" "$F/TheSkyBlessing/Renamed"; run --prepare
[ ! -e "$F/.runtime/world/datapacks/Core Pack" ] || fail 'renamed link remains'; link "$F/.runtime/world/datapacks/Renamed"
[ ! -e "$F/.runtime/world/datapacks/overlay" ] || fail 'overlay separately linked'; pass

# Conflict validation happens before any link is created.
fixture conflict; mkdir -p "$F/.runtime/world/datapacks/Asset"; : > "$F/.runtime/world/datapacks/Asset/user"
fails run --prepare; [ ! -e "$F/.runtime/world/datapacks/Core Pack" ] || fail 'partial mutation'; [ -f "$F/.runtime/world/datapacks/Asset/user" ] || fail 'user data removed'; pass

# Broken managed targets can be removed; custom links remain unmanaged.
fixture retarget; run --prepare; mv "$F/Asset-AnimatedJava/AnimatedJava" "$F/Asset-AnimatedJava/AJBase"
mkdir "$F/custom"; ln -s "$F/custom" "$F/.runtime/world/datapacks/UserLink"; run --prepare
[ ! -e "$F/.runtime/world/datapacks/AnimatedJava" ] || fail 'broken link remains'; link "$F/.runtime/world/datapacks/AJBase"; link "$F/.runtime/world/datapacks/UserLink"; pass

fixture precondition; mkdir -p "$F/Asset/Same" "$F/TheSkyBlessing/Same"; : > "$F/Asset/Same/pack.mcmeta"; : > "$F/TheSkyBlessing/Same/pack.mcmeta"
fails run --prepare; [ ! -e "$F/.runtime/world/datapacks" ] || fail 'duplicate created datapacks'; rm -rf "$F/TheSkyBlessing/Same" "$F/Asset-AnimatedJava"; fails run --prepare; pass

# Switching external worlds cannot apply an old world's ownership to the new one.
fixture worlds; mkdir "$F/world one" "$F/world two"; printf 'WORLD_PATH=world one\n' > "$F/devspace.local.conf"; run --prepare; link "$F/world one/datapacks/Core Pack"
mkdir -p "$F/world two/datapacks"; ln -s "$F/TheSkyBlessing/Core Pack" "$F/world two/datapacks/Core Pack"
printf 'WORLD_PATH=world two\n' > "$F/devspace.local.conf"; run --prepare; link "$F/world one/datapacks/Core Pack"; link "$F/world two/datapacks/Core Pack"
rm "$F/.runtime/active-world"; ln -s "$F/world one" "$F/.runtime/active-world"; fails run --prepare; pass

# A same-target user link is reused without being adopted, and held locks/invalid ports block preparation.
fixture ownership; mkdir -p "$F/.runtime/world/datapacks"; ln -s "$F/TheSkyBlessing/Core Pack" "$F/.runtime/world/datapacks/Core Pack"
run --prepare; grep -q '^Core Pack' "$F/.runtime/world/.devspace-managed-packs.tsv" && fail 'user link was adopted'
mkdir "$F/TheSkyBlessing/Spare"; : > "$F/TheSkyBlessing/Spare/pack.mcmeta"; rm -rf "$F/TheSkyBlessing/Core Pack"; run --prepare
link "$F/.runtime/world/datapacks/Core Pack"
mkdir "$F/.runtime/server.lock"; fails run --prepare; rmdir "$F/.runtime/server.lock"
printf 'SERVER_PORT=70000\n' > "$F/devspace.local.conf"; fails run --prepare; pass

# Keep unrelated allow rules across regeneration.
fixture allowed; mkdir "$F/.runtime"; printf '[regex].*/mine/.*\n# personal\n' > "$F/.runtime/allowed_symlinks.txt"; run --prepare; run --prepare
[ "$(grep -c '^\[regex\]' "$F/.runtime/allowed_symlinks.txt")" = 1 ] || fail 'regex changed'; grep -q '^# personal$' "$F/.runtime/allowed_symlinks.txt" || fail 'comment lost'; pass

# Failed resource download leaves both properties intact.
fixture resource; mkdir -p "$F/.runtime" "$F/.cache" "$F/bin"; printf 'resource-pack=old\nresource-pack-sha1=oldhash\n' > "$F/.runtime/server.properties"
printf '#!/bin/sh\nexit 22\n' > "$F/bin/curl"; chmod +x "$F/bin/curl"
fails env PATH=$F/bin:$PATH DEVSPACE_ROOT=$F DEVSPACE_CONFIG=$F/devspace.local.conf sh -c '. "$1/scripts/lib/runtime.sh"; runtime_init; runtime_fetch_resourcepack' sh "$F"
grep -q '^resource-pack=old$' "$F/.runtime/server.properties" || fail 'resource uri corrupted'; grep -q '^resource-pack-sha1=oldhash$' "$F/.runtime/server.properties" || fail 'resource hash corrupted'; pass

# A successful transfer with a broken checksum command is equally non-destructive.
printf '#!/bin/sh\nwhile [ "$#" -gt 0 ]; do [ "$1" = -o ] && { shift; out=$1; }; shift; done\nprintf bytes > "$out"\n' > "$F/bin/curl"
printf '#!/bin/sh\nexit 1\n' > "$F/bin/sha1sum"; chmod +x "$F/bin/"*
fails env PATH=$F/bin:/bin DEVSPACE_ROOT=$F DEVSPACE_CONFIG=$F/devspace.local.conf sh -c '. "$1/scripts/lib/runtime.sh"; runtime_init; runtime_fetch_resourcepack' sh "$F"
grep -q '^resource-pack=old$' "$F/.runtime/server.properties" || fail 'checksum failure changed uri'; grep -q '^resource-pack-sha1=oldhash$' "$F/.runtime/server.properties" || fail 'checksum failure changed hash'

# Fully mocked normal start verifies preconditions, args, cleanup, and no network/Java use in test.
fixture start; mkdir -p "$F/bin" "$F/.cache"; printf jar > "$F/.cache/server-1.20.4.jar"
printf 'ACCEPT_EULA=true\nJAVA_BIN=%s/bin/java\nJAVA_XMS=3G\nJAVA_XMX=5G\nSERVER_PORT=25570\n' "$F" > "$F/devspace.local.conf"
cat > "$F/bin/sha1sum" <<'EOF'
#!/bin/sh
case $1 in *server-1.20.4.jar) echo '8dd1a28015f51b1803213892b50b7b4fc76e594d  x';; *) echo '1111111111111111111111111111111111111111  x';; esac
EOF
cat > "$F/bin/curl" <<'EOF'
#!/bin/sh
while [ "$#" -gt 0 ]; do [ "$1" = -o ] && { shift; out=$1; }; shift; done
printf resource > "$out"
EOF
cat > "$F/bin/java" <<'EOF'
#!/bin/sh
[ "${1-}" = -version ] && { echo 'openjdk version "17.0.1"' >&2; exit; }
echo "$*" > "$DEVSPACE_ROOT/java.args"
IFS= read -r console_line || console_line=
echo "$console_line" > "$DEVSPACE_ROOT/java.stdin"
EOF
chmod +x "$F/bin/"*; printf 'stop\n' | PATH=$F/bin:$PATH run
grep -q -- '-Xms3G -Xmx5G' "$F/java.args" || fail 'JVM args wrong'; grep -q '^server-port=25570$' "$F/.runtime/server.properties" || fail 'custom port absent'
[ "$(sed -n '1p' "$F/java.stdin")" = stop ] || fail 'console input did not reach Java'
[ ! -e "$F/.runtime/server.lock" ] && [ ! -e "$F/.runtime/world/.devspace-server.lock" ] || fail 'lock leaked'
[ -f "$F/.runtime/eula.txt" ] && grep -q '^eula=true$' "$F/.runtime/eula.txt" || fail 'accepted EULA file not written'

# TERM is forwarded to Java and both locks are released.
cat > "$F/bin/java" <<'EOF'
#!/bin/sh
if [ "${1-}" = -version ]; then echo 'openjdk version "17.0.1"' >&2; exit; fi
trap 'echo term > "$DEVSPACE_ROOT/java.term"; exit 143' TERM
echo started > "$DEVSPACE_ROOT/java.started"
while :; do sleep 1; done
EOF
chmod +x "$F/bin/java"
env PATH=$F/bin:$PATH DEVSPACE_ROOT=$F DEVSPACE_CONFIG=$F/devspace.local.conf sh "$F/scripts/server.sh" >/dev/null 2>&1 & server_pid=$!
tries=0; while [ ! -f "$F/java.started" ] && [ "$tries" -lt 50 ]; do sleep 0.1; tries=$((tries+1)); done
[ -f "$F/java.started" ] || fail 'mock Java did not start'
kill -TERM "$server_pid"; wait "$server_pid" 2>/dev/null || :
[ -f "$F/java.term" ] || fail 'TERM was not forwarded'; [ ! -e "$F/.runtime/server.lock" ] || fail 'signal leaked lock'

printf 'ACCEPT_EULA=false\nJAVA_BIN=%s/bin/java\n' "$F" > "$F/devspace.local.conf"; rm -f "$F/.runtime/eula.txt"; fails env PATH=$F/bin:$PATH DEVSPACE_ROOT=$F DEVSPACE_CONFIG=$F/devspace.local.conf sh "$F/scripts/server.sh"; pass

# Java 16 and an invalid downloaded jar checksum are rejected.
fixture invalid; mkdir -p "$F/bin" "$F/.runtime" "$F/.cache"
printf '#!/bin/sh\necho '\''openjdk version "16.0.2"'\'' >&2\n' > "$F/bin/java16"; chmod +x "$F/bin/java16"
fails env DEVSPACE_ROOT=$F DEVSPACE_CONFIG=$F/devspace.local.conf JAVA_BIN=$F/bin/java16 sh -c '. "$1/scripts/lib/runtime.sh"; runtime_init; runtime_check_java' sh "$F"
cat > "$F/bin/curl" <<'EOF'
#!/bin/sh
while [ "$#" -gt 0 ]; do [ "$1" = -o ] && { shift; out=$1; }; shift; done
printf badjar > "$out"
EOF
printf '#!/bin/sh\necho '\''0000000000000000000000000000000000000000  x'\''\n' > "$F/bin/sha1sum"; chmod +x "$F/bin/"*
fails env PATH=$F/bin:/bin DEVSPACE_ROOT=$F DEVSPACE_CONFIG=$F/devspace.local.conf sh -c '. "$1/scripts/lib/runtime.sh"; runtime_init; mkdir -p "$R_CACHE"; runtime_ensure_jar' sh "$F"
[ ! -f "$F/.cache/server-1.20.4.jar" ] || fail 'invalid jar installed'; pass

echo "runtime tests: $passed passed"
