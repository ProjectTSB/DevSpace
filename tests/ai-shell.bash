#!/usr/bin/env bash
set -euo pipefail
unset DEVSPACE_CODEX_DAEMON
root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd -P)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
fail() { printf 'AI shell test failed: %s\n' "$*" >&2; exit 1; }

fixture="$tmp/DevSpace 日本語 space"
mkdir -p "$fixture/scripts" "$tmp/bin" "$tmp/outside" "$fixture/Asset-other"
cp "$root/scripts/ai-shell.bash" "$fixture/scripts/ai-shell.bash"
for repo in Asset TheSkyBlessing Asset-AnimatedJava; do
    git init -q "$fixture/$repo"
    mkdir -p "$fixture/$repo/deep folder/data"
done
git -C "$fixture/Asset" -c user.name=test -c user.email=test@example.invalid \
    commit -q --allow-empty -m initial
git -C "$fixture/Asset" worktree add -q --detach "$fixture/.worktrees/feature/Asset"
git -C "$fixture/Asset" worktree add -q --detach "$fixture/Asset/linked-worktree"
git init -q "$fixture/Asset/nested-repo"
ln -s "$fixture/Asset/deep folder" "$tmp/asset-link"
ln -s "$tmp/outside" "$fixture/Asset/outside-link"

cat > "$tmp/bin/codex" <<'EOF'
#!/usr/bin/env bash
printf '%s\0' "$PWD" "$@" > "$AI_TEST_LOG"
cat >> "$AI_TEST_LOG"
exit "${AI_TEST_EXIT:-0}"
EOF
cp "$tmp/bin/codex" "$tmp/bin/claude"
chmod +x "$tmp/bin/codex" "$tmp/bin/claude"
export PATH="$tmp/bin:$PATH" AI_TEST_LOG="$tmp/actual"

# Exercise parsing with the previous interactive aliases and repeated sourcing.
shopt -s expand_aliases
alias codex='codex --dangerously-bypass-approvals-and-sandbox'
alias claude='claude --dangerously-skip-permissions'
source "$fixture/scripts/ai-shell.bash"
source "$fixture/scripts/ai-shell.bash"
alias codex claude &>/dev/null && fail 'old aliases remain'

check() (
    local cli=$1 flag=$2 start=$3 expected=$4 status=0 original
    shift 4
    cd -- "$start"
    original=$PWD
    export AI_TEST_EXIT=23
    "$cli" 'two words' '' $'line\nbreak' 'literal * $(false)' <<< 'stdin survives' || status=$?
    [[ $status == 23 ]] || fail "$cli exit status changed"
    [[ $PWD == "$original" ]] || fail "$cli changed the parent shell directory"
    printf '%s\0' "$expected" "$flag" "$@" 'two words' '' $'line\nbreak' 'literal * $(false)' > "$tmp/expected"
    printf 'stdin survives\n' >> "$tmp/expected"
    cmp "$tmp/expected" "$AI_TEST_LOG" || fail "$cli launch differs at $start"
)

for cli in codex claude; do
    flag=--dangerously-skip-permissions
    extra=()
    if [[ $cli == codex ]]; then
        flag=--dangerously-bypass-approvals-and-sandbox
        extra=(--no-daemon)
    fi
    for repo in Asset TheSkyBlessing; do
        check "$cli" "$flag" "$fixture/$repo" "$fixture" "${extra[@]}"
        check "$cli" "$flag" "$fixture/$repo/deep folder/data" "$fixture" "${extra[@]}"
    done
    check "$cli" "$flag" "$tmp/asset-link" "$fixture" "${extra[@]}"
    for start in "$fixture" "$tmp/outside" "$fixture/Asset-other" \
        "$fixture/Asset-AnimatedJava" "$fixture/.worktrees/feature/Asset" \
        "$fixture/Asset/linked-worktree" "$fixture/Asset/nested-repo" \
        "$fixture/Asset/outside-link"; do
        check "$cli" "$flag" "$start" "$start" "${extra[@]}"
    done
done

DEVSPACE_CODEX_DAEMON=1 check codex --dangerously-bypass-approvals-and-sandbox "$fixture/Asset" "$fixture"
check codex --dangerously-bypass-approvals-and-sandbox "$fixture/Asset" "$fixture" --no-daemon
DEVSPACE_CODEX_DAEMON=0 check codex --dangerously-bypass-approvals-and-sandbox "$fixture" "$fixture" --no-daemon
DEVSPACE_CODEX_DAEMON= check codex --dangerously-bypass-approvals-and-sandbox "$fixture" "$fixture" --no-daemon
DEVSPACE_CODEX_DAEMON=1 check claude --dangerously-skip-permissions "$fixture/Asset" "$fixture"
printf 'AI shell tests passed\n'
