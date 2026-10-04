# Source this file from Bash to start AI sessions at the DevSpace entrypoint.
# Resolve once while sourcing so later calls can run from any directory.
_DEVSPACE_AI_ROOT=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P) || return

# Remove the previous container aliases before Bash parses the functions.
unalias codex claude 2>/dev/null || :

_devspace_ai_run() (
    local repo_root
    repo_root=$(command git rev-parse --show-toplevel 2>/dev/null) || repo_root=''
    case "$repo_root" in
        "$_DEVSPACE_AI_ROOT/TheSkyBlessing"|"$_DEVSPACE_AI_ROOT/Asset")
            # Linked worktrees have a .git file and keep their assigned root.
            if [[ -d "$repo_root/.git" ]]; then
                cd -- "$_DEVSPACE_AI_ROOT" || return
            fi
            ;;
    esac
    command "$@"
)

codex() {
    local daemon_args=(--no-daemon)
    if [[ ${DEVSPACE_CODEX_DAEMON:-0} == 1 ]]; then
        daemon_args=()
    fi
    _devspace_ai_run codex --dangerously-bypass-approvals-and-sandbox "${daemon_args[@]}" "$@"
}

claude() {
    _devspace_ai_run claude --dangerously-skip-permissions "$@"
}
