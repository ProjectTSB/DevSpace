#!/bin/sh
# Exercise the wizard without installing host software or accessing the network.
set -eu
unset DEVSPACE_ROOT DEVSPACE_CONFIG DEVSPACE_CONTAINER DEVSPACE_NATIVE_LIBRARY JAVA_BIN
root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' 0
trap 'exit 130' 1 2 3 15
fail() { printf 'native setup test failed: %s\n' "$*" >&2; exit 1; }
fixture="$tmp/日本語 space"
mkdir -p "$fixture/scripts/lib" "$tmp/bin" "$tmp/state"
cp "$root/scripts/setup-native.sh" "$fixture/scripts/"
cp "$root/scripts/lib/common.sh" "$fixture/scripts/lib/"
export NATIVE_TEST_STATE="$tmp/state" NATIVE_TEST_LOG="$tmp/actions" NATIVE_TEST_OS=Darwin

cat > "$tmp/bin/mock" <<'MOCK'
#!/bin/sh
set -eu
tool=${0##*/}
case $tool in
  uname) printf '%s\n' "$NATIVE_TEST_OS";;
  git) [ "$1" = --version ] || exit 99;;
  curl)
    [ "$1" != --version ] || exit 0
    printf '%s\n' "curl $*" >> "$NATIVE_TEST_LOG"
    [ "${NATIVE_TEST_DOWNLOAD:-ok}" = ok ] || exit 22
    [ "$1" = -fSL ] && [ "$3" = -o ] || exit 99
    if [ "$2" = https://chatgpt.com/codex/install.ps1 ]; then
      cat > "$4" <<'CODEX_INSTALLER'
printf 'codex-installer\n' >> "$NATIVE_TEST_LOG"
[ "${NATIVE_TEST_FAIL:-}" != codex ] || exit 42
[ "${NATIVE_TEST_INVISIBLE:-}" = codex ] || : > "$NATIVE_TEST_STATE/codex"
CODEX_INSTALLER
    else
      cat > "$4" <<'BOOTSTRAP'
printf 'bootstrap\n' >> "$NATIVE_TEST_LOG"
rm "$NATIVE_TEST_STATE/no-manager"
BOOTSTRAP
    fi
    ;;
  java)
    [ -f "$NATIVE_TEST_STATE/java" ] || exit 1
    printf 'openjdk version "%s.0.1"\n' "${NATIVE_TEST_JAVA:-17}" >&2;;
  node) [ -f "$NATIVE_TEST_STATE/node" ] || exit 1; printf '%s\n' v24.0.0;;
  python|python3) [ -f "$NATIVE_TEST_STATE/python" ] || exit 1;;
  npm) [ -f "$NATIVE_TEST_STATE/node" ] || exit 1; printf '%s\n' 11.0.0;;
  gh)
    [ -f "$NATIVE_TEST_STATE/gh" ] || exit 1
    if [ "$1" = auth ]; then
      printf '%s\n' "gh $*" >> "$NATIVE_TEST_LOG"
      [ "$2" != status ] || exit 1
    fi;;
  jq|rg|codex|claude) [ -f "$NATIVE_TEST_STATE/$tool" ] || exit 1;;
  codex-x86_64-pc-windows-msvc|codex-aarch64-pc-windows-msvc)
    [ -f "$NATIVE_TEST_STATE/$tool" ] || exit 1;;
  brew|winget)
    [ ! -f "$NATIVE_TEST_STATE/no-manager" ] || exit 1
    case $1 in
      --version) printf '%s\n' 'test-manager 1';;
      list) exit 1;;
      install)
        printf '%s\n' "$tool $*" >> "$NATIVE_TEST_LOG"
        case $* in
          *temurin*|*Temurin*) package=java;;
          *GitHub.cli*|*' gh') package=gh;;
          *NodeJS*|*' node') package=node;;
          *Python*|*' python') package=python;;
          *jq*) package=jq;;
          *ripgrep*) package=rg;;
          *Codex*|*' codex') package=codex;;
          *ClaudeCode*|*claude-code*) package=claude;;
          *) exit 99;;
        esac
        [ "$package" != "${NATIVE_TEST_FAIL:-}" ] || exit 42
        [ "$package" = "${NATIVE_TEST_INVISIBLE:-}" ] || : > "$NATIVE_TEST_STATE/$package";;
      *) exit 99;;
    esac;;
  code)
    [ ! -f "$NATIVE_TEST_STATE/no-code" ] || exit 1
    case $1 in
      --list-extensions) cat "$NATIVE_TEST_STATE/extensions";;
      --install-extension)
        printf '%s\n' "code $*" >> "$NATIVE_TEST_LOG"
        [ ! -f "$NATIVE_TEST_STATE/extension-fails" ] || exit 42
        [ ! -f "$NATIVE_TEST_STATE/extension-invisible" ] || exit 0
        id=${2%@*}
        awk -F@ -v id="$id" 'tolower($1) != tolower(id)' "$NATIVE_TEST_STATE/extensions" > "$NATIVE_TEST_STATE/ext.tmp"
        mv "$NATIVE_TEST_STATE/ext.tmp" "$NATIVE_TEST_STATE/extensions"
        case $2 in *@*) printf '%s\n' "$2";; *) printf '%s@1.0.0\n' "$2";; esac >> "$NATIVE_TEST_STATE/extensions";;
      *) exit 99;;
    esac;;
  powershell.exe)
    if [ "$2" = -ExecutionPolicy ]; then
      [ "$#" -eq 5 ] && [ "$1" = -NoProfile ] && [ "$3" = Bypass ] && [ "$4" = -File ] || exit 99
      [ "$MSYS2_ARG_CONV_EXCL" = '*' ] || exit 99
      printf 'powershell-installer <%s>\n' "$5" >> "$NATIVE_TEST_LOG"
      # Execute the fixture written by mock curl; no PowerShell installer runs.
      sh "$5"
    else
      printf '%s\r\n' 'C:\New Tools;C:\日本語' 'C:\Users\tester\bin'
    fi;;
  cygpath)
    if [ "$1" = -w ]; then
      printf '%s\n' "$2"
    else
      printf '%s\n' "$*" >> "$NATIVE_TEST_LOG"
      printf '%s\n' '/nonexistent/new tools:/nonexistent/日本語'
    fi;;
  *) exit 99;;
esac
MOCK
chmod +x "$tmp/bin/mock"
for tool in uname git curl java node npm python python3 gh jq rg codex claude brew winget code powershell.exe cygpath codex-x86_64-pc-windows-msvc codex-aarch64-pc-windows-msvc; do
  ln -s mock "$tmp/bin/$tool"
done
cat > "$fixture/scripts/setup.sh" <<'MOCK'
#!/bin/sh
printf 'setup\n' >> "$NATIVE_TEST_LOG"
for arg do printf '<%s>\n' "$arg" >> "$NATIVE_TEST_LOG"; done
MOCK

# Source functions for fixtures and contract checks, then run actual CLI processes.
DEVSPACE_NATIVE_LIBRARY=1 . "$root/scripts/setup-native.sh"
native_extensions > "$tmp/extensions"
python3 - "$root/.devcontainer/devcontainer.json" "$tmp/extensions" <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    expected = json.load(f)['customizations']['vscode']['extensions']
with open(sys.argv[2]) as f:
    actual = f.read().splitlines()
assert actual == expected, (actual, expected)
PY
unset DEVSPACE_NATIVE_LIBRARY

reset_fixture() {
  rm -f "$tmp/state/"* "$fixture/devspace.local.conf"
  : > "$NATIVE_TEST_LOG"
  for tool in java gh node python jq rg codex claude; do : > "$tmp/state/$tool"; done
  sed '/@/!s/$/@1.0.0/' "$tmp/extensions" > "$tmp/state/extensions"
  unset NATIVE_TEST_FAIL NATIVE_TEST_INVISIBLE NATIVE_TEST_JAVA NATIVE_TEST_DOWNLOAD
  NATIVE_TEST_OS=Darwin; export NATIVE_TEST_OS
}
run_wizard() {
  PATH="$tmp/bin:$PATH" sh "$fixture/scripts/setup-native.sh" "$@" > "$tmp/output" 2>&1
}
expect_failure() {
  if "$@"; then fail 'command unexpectedly succeeded'; fi
}

# Check mode and a complete installation neither prompt nor mutate.
reset_fixture
run_wizard --check </dev/null || fail 'check with existing tools'
[ ! -s "$NATIVE_TEST_LOG" ] || fail 'check performed a mutation'
printf 'n\nn\n' | run_wizard || fail 'all installed'
[ ! -s "$NATIVE_TEST_LOG" ] || fail 'reinstalled existing tools'
expect_failure run_wizard --unknown
expect_failure run_wizard --check extra
NATIVE_TEST_OS=Linux; export NATIVE_TEST_OS
expect_failure run_wizard
run_wizard --help || fail 'help on unsupported platform'

# Missing optional tools appear without turning check mode into installation.
reset_fixture
rm "$tmp/state/jq"
run_wizard --check </dev/null || fail 'optional missing in check'
[ ! -s "$NATIVE_TEST_LOG" ] || fail 'check installed missing tool'
printf 'n\nn\nn\n' | run_wizard || fail 'optional skip'
[ ! -s "$NATIVE_TEST_LOG" ] || fail 'skip installed tool'

# Real selection loop installs the correct packages on both platforms.
for os in Darwin MINGW64_NT-10.0; do
  reset_fixture
  NATIVE_TEST_OS=$os; export NATIVE_TEST_OS
  rm "$tmp/state/java" "$tmp/state/gh" "$tmp/state/node" "$tmp/state/python" "$tmp/state/jq" "$tmp/state/rg" "$tmp/state/codex" "$tmp/state/claude"
  printf 'y\ny\ny\ny\ny\ny\ny\ny\nn\nn\n' | run_wizard || { cat "$tmp/output"; fail "$os install"; }
  case $os in
    Darwin)
       [ "$(grep -c ' install ' "$NATIVE_TEST_LOG")" -eq 8 ] || fail 'wrong number of brew installs'
       grep -Fx 'brew install --cask temurin@17' "$NATIVE_TEST_LOG" >/dev/null || fail 'brew Java';;
    *) grep -Fx 'winget install --id EclipseAdoptium.Temurin.17.JDK --exact --source winget --no-upgrade' "$NATIVE_TEST_LOG" >/dev/null || fail 'winget Java'
       grep -Fx -- '-u -p C:\New Tools;C:\日本語;C:\Users\tester\bin' "$NATIVE_TEST_LOG" >/dev/null || fail 'Windows PATH conversion'
       [ "$(grep -c ' install ' "$NATIVE_TEST_LOG")" -eq 7 ] || fail 'wrong number of winget installs'
       grep -Fx codex-installer "$NATIVE_TEST_LOG" >/dev/null || fail 'Codex official installer not used'
       if grep 'winget install --id OpenAI.Codex' "$NATIVE_TEST_LOG"; then fail 'Codex used winget'; fi;;
  esac
  grep -E 'visual-studio-code|Microsoft.VisualStudioCode|npm install|insecure-storage|accept-.*agreements' "$NATIVE_TEST_LOG" && fail 'unexpected installer or agreement flag'
done

# A long-name-only installation is diagnosed without treating it as usable codex.
for legacy in codex-x86_64-pc-windows-msvc codex-aarch64-pc-windows-msvc; do
  reset_fixture; rm "$tmp/state/codex"
  NATIVE_TEST_OS=MINGW64_NT-10.0; export NATIVE_TEST_OS
  : > "$tmp/state/$legacy"
  : > "$tmp/state/no-manager"
  run_wizard --check </dev/null || fail 'check legacy Codex'
  grep "$legacy は実行できますが、codex コマンドは使えません" "$tmp/output" >/dev/null || fail 'legacy diagnosis missing'
  if grep -E 'curl |codex-installer|powershell-installer' "$NATIVE_TEST_LOG"; then fail 'check mutated legacy installation'; fi
  printf 'n\nn\nn\n' | run_wizard || fail 'decline Codex repair'
  if grep 'codex の認証は' "$tmp/output"; then fail 'unavailable Codex advertised'; fi
  if grep -E 'curl |codex-installer|powershell-installer' "$NATIVE_TEST_LOG"; then fail 'declined repair ran'; fi
  # Windows Codex must not depend on winget, nor remove the existing installation.
  mkdir -p "$tmp/日本語 temp"
  printf 'y\nn\nn\n' | TMPDIR="$tmp/日本語 temp" run_wizard || { cat "$tmp/output"; fail 'repair legacy Codex'; }
  [ -f "$tmp/state/$legacy" ] || fail 'legacy installation removed'
  grep -Fx codex-installer "$NATIVE_TEST_LOG" >/dev/null || fail 'repair did not invoke official installer'
  grep 'VS Code と端末を開き直してください' "$tmp/output" >/dev/null || fail 'success omitted restart guidance'
  [ -z "$(ls -A "$tmp/日本語 temp")" ] || fail 'installer temporary directory remained'
  : > "$NATIVE_TEST_LOG"
  printf 'n\nn\n' | run_wizard || fail 'rerun after repair'
  if grep -E 'curl |codex-installer|powershell-installer' "$NATIVE_TEST_LOG"; then fail 'working Codex reinstalled'; fi
done

for problem in download installer invisible; do
  reset_fixture; rm "$tmp/state/codex"
  NATIVE_TEST_OS=MINGW64_NT-10.0; export NATIVE_TEST_OS
  case $problem in
    download) export NATIVE_TEST_DOWNLOAD=fail;;
    installer) export NATIVE_TEST_FAIL=codex;;
    invisible) export NATIVE_TEST_INVISIBLE=codex;;
  esac
  printf 'y\nn\nn\n' | expect_failure run_wizard
  if [ "$problem" = download ]; then
    if grep 'powershell-installer' "$NATIVE_TEST_LOG"; then fail 'incomplete download was executed'; fi
  fi
  if grep 'codex の認証は' "$tmp/output"; then fail 'failed Codex advertised'; fi
done

# Failure and a successful installer with an unusable binary both remain incomplete.
for problem in failure invisible; do
  reset_fixture; rm "$tmp/state/jq"
  if [ "$problem" = failure ]; then export NATIVE_TEST_FAIL=jq; else export NATIVE_TEST_INVISIBLE=jq; fi
  printf 'y\nn\nn\n' | expect_failure run_wizard
  grep '未完了' "$tmp/output" >/dev/null || fail 'failure was not reported'
done

# EOF, explicit quit and invalid answers cannot accidentally approve an install.
reset_fixture; rm "$tmp/state/jq"
if run_wizard </dev/null; then fail 'EOF succeeded'; else [ "$?" -eq 130 ] || fail 'EOF status'; fi
printf 'q\n' | expect_failure run_wizard
[ ! -s "$NATIVE_TEST_LOG" ] || fail 'EOF/quit installed tool'
printf 'invalid\nn\nn\nn\n' | run_wizard || fail 'invalid answer retry'
[ ! -s "$NATIVE_TEST_LOG" ] || fail 'invalid answer approved install'

# Java version and explicit config are honored, including literal shell characters.
reset_fixture
export NATIVE_TEST_JAVA=8
expect_failure run_wizard --check
unset NATIVE_TEST_JAVA
printf 'JAVA_BIN=$(touch should-not-exist)\n' > "$fixture/devspace.local.conf"
printf 'n\nn\n' | expect_failure run_wizard
[ ! -s "$NATIVE_TEST_LOG" ] || fail 'invalid JAVA_BIN caused installation'
grep 'JAVA_BIN=' "$tmp/output" >/dev/null || fail 'JAVA_BIN guidance missing'
printf 'JAVA_BIN=%s/bin/java\n' "$tmp" > "$fixture/devspace.local.conf"
run_wizard --check || fail 'configured Java path'

# Pinned extensions require consent, and successful exit alone does not prove installation.
for problem in none failure invisible; do
  reset_fixture
  sed 's/3.4.19/4.0.0/' "$tmp/state/extensions" > "$tmp/ext.old"
  cp "$tmp/ext.old" "$tmp/state/extensions"
  printf 'n\nn\nn\n' | run_wizard || fail 'extension skip'
  cmp "$tmp/ext.old" "$tmp/state/extensions" || fail 'unselected version changed'
  case $problem in
    failure) : > "$tmp/state/extension-fails";;
    invisible) : > "$tmp/state/extension-invisible";;
  esac
  if [ "$problem" = none ]; then
    printf 'y\nn\nn\n' | run_wizard || fail 'extension installation'
    grep -Fx 'SPGoding.datapack-language-server@3.4.19' "$tmp/state/extensions" >/dev/null || fail 'extension version'
  else
    printf 'y\nn\nn\n' | expect_failure run_wizard
  fi
done
reset_fixture; : > "$tmp/state/no-code"
printf 'n\nn\n' | run_wizard || fail 'missing code CLI should give guidance'
grep 'PATH' "$tmp/output" >/dev/null || fail 'code PATH guidance'

# Homebrew bootstrap is never downloaded without its separate prompt.
reset_fixture; rm "$tmp/state/jq"; : > "$tmp/state/no-manager"
printf 'y\nn\nn\nn\n' | expect_failure run_wizard
[ ! -s "$NATIVE_TEST_LOG" ] || fail 'declined Homebrew bootstrap ran commands'
if printf 'y\nq\n' | run_wizard; then fail 'bootstrap quit succeeded'; else [ "$?" -eq 130 ] || fail 'bootstrap quit did not exit wizard'; fi

# Bootstrap runs only after a complete download; subsequent tool checks still apply.
printf 'y\ny\nn\nn\n' | run_wizard || fail 'Homebrew bootstrap'
grep -Fx bootstrap "$NATIVE_TEST_LOG" >/dev/null || fail 'bootstrap not invoked'
reset_fixture; rm "$tmp/state/jq"; : > "$tmp/state/no-manager"
export NATIVE_TEST_DOWNLOAD=fail
printf 'y\ny\nn\nn\n' | expect_failure run_wizard
if grep -Fx bootstrap "$NATIVE_TEST_LOG" >/dev/null; then fail 'failed download was executed'; fi
reset_fixture; rm "$tmp/state/jq"; : > "$tmp/state/no-manager"
NATIVE_TEST_OS=MINGW64_NT-10.0; export NATIVE_TEST_OS
printf 'y\nn\nn\n' | expect_failure run_wizard
grep 'アプリ インストーラー' "$tmp/output" >/dev/null || fail 'winget guidance missing'
if grep ' install ' "$NATIVE_TEST_LOG" >/dev/null; then fail 'missing manager attempted install'; fi

# Workspace arguments preserve spaces, Unicode and literal metacharacters.
for world in '' default '世界 space/$(literal)'; do
  reset_fixture
  printf 'y\n%s\nn\n' "$world" | run_wizard || fail 'workspace handoff'
  case $world in
    '') printf 'setup\n' > "$tmp/expected";;
    default) printf 'setup\n<--default-world>\n' > "$tmp/expected";;
    *) printf 'setup\n<-->\n<%s>\n' "$world" > "$tmp/expected";;
  esac
  cmp "$tmp/expected" "$NATIVE_TEST_LOG" || fail 'workspace arguments changed'
done
reset_fixture
printf 'n\ny\n' | run_wizard || fail 'GitHub login'
grep -Fx 'gh auth login --web --git-protocol https' "$NATIVE_TEST_LOG" >/dev/null || fail 'login arguments'

printf '%s\n' 'native setup tests: ok'
