#!/bin/sh
# Interactive host setup; ordinary setup/server commands remain dependency-free.
set -eu
NATIVE_SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)

native_say() { printf '%s\n' "$*"; }
native_ask() {
  while :; do
    printf '%s [y/N/q] ' "$1"
    if ! IFS= read -r native_answer; then
      native_say '入力が終了したため中断しました。再実行できます。' >&2
      exit 130
    fi
    case $native_answer in
      y|Y|yes|YES) return 0;;
      ''|n|N|no|NO) return 1;;
      q|Q) exit 130;;
      *) native_say 'y は実行、n はスキップ、q は終了です。';;
    esac
  done
}

native_platform() {
  case $(uname -s) in
    Darwin) native_os=macos;;
    MINGW*|MSYS*) native_os=windows;;
    *) native_say '対応環境は macOS と Windows の Git Bash です。' >&2; return 1;;
  esac
  if [ "${DEVSPACE_CONTAINER:-}" = 1 ]; then
    native_say 'DevContainer の外で実行してください。' >&2
    return 1
  fi
}

# Only extend this process's PATH. Never rewrite shell profiles or registry values.
native_refresh_path() {
  if [ "$native_os" = macos ]; then
    for native_dir in /opt/homebrew/bin /usr/local/bin; do
      [ ! -d "$native_dir" ] || PATH="$PATH:$native_dir"
    done
  elif command -v powershell.exe >/dev/null 2>&1; then
    native_win_path=$(powershell.exe -NoProfile -NonInteractive -Command \
      '[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); [Environment]::GetEnvironmentVariable("Path", "Machine"); [Environment]::GetEnvironmentVariable("Path", "User")' 2>/dev/null | tr -d '\r' | tr '\n' ';' | sed 's/;*$//')
    if [ -n "$native_win_path" ]; then
      native_extra_path=$(cygpath -u -p "$native_win_path" 2>/dev/null) || native_extra_path=
      [ -z "$native_extra_path" ] || PATH="$PATH:$native_extra_path"
    fi
  fi
  export PATH
  hash -r 2>/dev/null || :
}

native_probe() {
  case $1 in
    java)
      native_version=$("${JAVA_BIN:-java}" -version 2>&1) || return 1
      native_major=$(printf '%s\n' "$native_version" | sed -n '1{s/^[^0-9]*//; s/^1\.//; s/[^0-9].*$//; p;}')
      case $native_major in ''|*[!0-9]*) return 1;; esac
      [ "$native_major" -ge 17 ]; return;;
    node)
      node --version >/dev/null 2>&1 && npm --version >/dev/null 2>&1; return;;
    python)
      for native_python in python3 python; do
        if "$native_python" -c 'import sys; sys.exit(sys.version_info.major != 3)' >/dev/null 2>&1; then return 0; fi
      done
      return 1;;
    *) "$1" --version >/dev/null 2>&1;;
  esac
}

native_package() {
  native_kind=formula
  case $1 in
    java) native_label='Java 17 以上 / Minecraft サーバー'; native_brew=temurin@17; native_kind=cask; native_winget=EclipseAdoptium.Temurin.17.JDK;;
    gh) native_label='GitHub CLI / PR・Issue と認証'; native_brew=gh; native_winget=GitHub.cli;;
    node) native_label='Node.js と npm / 個人用スキルなどの補助処理'; native_brew=node; native_winget=OpenJS.NodeJS.LTS;;
    python) native_label='Python 3 / lint などの補助処理'; native_brew=python; native_winget=Python.Python.3.13;;
    jq) native_label='jq / JSON の加工'; native_brew=jq; native_winget=jqlang.jq;;
    rg) native_label='ripgrep / コード検索'; native_brew=ripgrep; native_winget=BurntSushi.ripgrep.MSVC;;
    codex) native_label='Codex CLI / AI 開発'; native_brew=codex; native_kind=cask; native_winget=;;
    claude) native_label='Claude Code CLI / AI 開発'; native_brew=claude-code; native_kind=cask; native_winget=Anthropic.ClaudeCode;;
    *) return 1;;
  esac
}

native_brew_bootstrap() (
  native_tmp=$(mktemp -d) || return 1
  trap 'rm -rf "$native_tmp"' 0
  trap 'exit 130' 1 2 3 15
  curl -fSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh -o "$native_tmp/install.sh" || return 1
  /bin/bash "$native_tmp/install.sh"
)

# Use the Windows installer documented by OpenAI. WinGet's portable alias may
# be absent even when its architecture-qualified Codex executable is usable.
native_codex_windows_install() (
  native_tmp=$(mktemp -d) || return 1
  trap 'rm -rf "$native_tmp"' 0
  trap 'exit 130' 1 2 3 15
  curl -fSL https://chatgpt.com/codex/install.ps1 -o "$native_tmp/install.ps1" || return 1
  native_windows_script=$(cygpath -w "$native_tmp/install.ps1") || return 1
  MSYS2_ARG_CONV_EXCL='*' powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$native_windows_script"
)

native_codex_legacy_command() {
  for native_legacy in codex-x86_64-pc-windows-msvc codex-aarch64-pc-windows-msvc; do
    if native_probe "$native_legacy"; then
      printf '%s\n' "$native_legacy"
      return 0
    fi
  done
  return 1
}

native_manager() {
  if [ "$native_os" = windows ]; then
    if [ "$native_tool" = codex ]; then
      command -v powershell.exe >/dev/null 2>&1 || {
        native_say 'Codex の公式インストーラーには Windows PowerShell が必要です。' >&2
        return 1
      }
      return 0
    fi
    if ! winget --version >/dev/null 2>&1; then
      native_say 'winget が使えません。Microsoft の「アプリ インストーラー」を導入・更新して再実行してください。' >&2
      native_say 'https://learn.microsoft.com/windows/package-manager/winget/' >&2
      return 1
    fi
  elif ! brew --version >/dev/null 2>&1; then
    native_say 'Homebrew を公式インストーラーで導入します。管理者パスワードを求められる場合があります。'
    native_say '取得元 https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh'
    native_ask 'Homebrew を導入しますか？' || return 1
    native_brew_bootstrap || return 1
    native_refresh_path
    brew --version >/dev/null 2>&1 || return 1
    native_say 'Homebrew が示す Next steps に従って PATH を設定してください。'
  fi
}

native_install() {
  if [ "$native_os" = windows ]; then
    if [ "$native_tool" = codex ]; then
      native_codex_windows_install
      return
    fi
    # Keep source/package agreement prompts in winget's own UI.
    winget install --id "$native_winget" --exact --source winget --no-upgrade
  else
    # An unusable command may still have a package installed. Avoid implicit upgrades.
    if brew list "--$native_kind" "$native_brew" >/dev/null 2>&1; then
      native_say "$native_brew は導入済みです。PATH または既存の版を確認してください。"
      return 0
    fi
    HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_UPGRADE=1 brew install "--$native_kind" "$native_brew"
  fi
}

native_tools() {
  for native_tool in java gh node python jq rg codex claude; do
    native_package "$native_tool"
    if native_probe "$native_tool"; then
      native_say "利用可能  $native_label"
      continue
    fi
    native_say "未準備    $native_label"
    if [ "$native_os" = windows ] && [ "$native_tool" = codex ]; then
      if native_legacy_command=$(native_codex_legacy_command); then
        native_say "$native_legacy_command は実行できますが、codex コマンドは使えません。"
        native_say 'winget 版で短いコマンド名が登録されない場合があります。公式インストーラーで導入できます。'
        native_say '既存の winget 版は自動削除しません。公式版の動作確認後に winget uninstall --id OpenAI.Codex --exact --source winget で削除できます。'
      fi
    fi
    [ "$native_mode" != check ] || continue
    if [ "$native_tool" = java ] && [ -n "${JAVA_BIN:-}" ]; then
      native_say "JAVA_BIN=$JAVA_BIN が Java 17 以上を実行できません。ローカル設定を確認してください。"
      continue
    fi
    if [ "$native_os" = windows ]; then
      if [ "$native_tool" = codex ]; then
        native_say '取得元  https://chatgpt.com/codex/install.ps1'
        native_say '実行予定  ダウンロードした公式スクリプトを Windows PowerShell で実行します。'
        native_say '公式インストーラーがユーザー領域へ Codex を配置し、PATH を登録します。'
      else
        native_say "実行予定  winget install --id $native_winget --exact --source winget --no-upgrade"
      fi
    else
      native_say "実行予定  brew install --$native_kind $native_brew"
    fi
    native_ask "$native_label を導入しますか？" || continue
    if native_manager && native_install; then
      native_refresh_path
      if native_probe "$native_tool"; then
        native_say "利用確認済み  $native_tool"
        native_say '導入したコマンドを使う前に、VS Code と端末を開き直してください。'
      else
        native_say "要確認  $native_tool はまだ実行できません。VS Code と端末を開き直し、--check で確認してください。"
        native_failed=1
      fi
    else
      native_say "導入未完了  $native_tool。上のエラーを確認して再実行してください。" >&2
      native_failed=1
    fi
  done
}

# Keep aligned with .devcontainer/devcontainer.json; covered by tests/setup-native.sh.
native_extensions() {
  printf '%s\n' \
    streetsidesoftware.code-spell-checker \
    mechatroner.rainbow-csv \
    Anthropic.claude-code \
    openai.chatgpt \
    MinecraftCommands.syntax-mcfunction \
    SPGoding.datapack-language-server@3.4.19
}

native_editor() {
  native_say 'VS Code 拡張機能。本体はインストール済みを前提にします。'
  if ! native_installed=$(code --list-extensions --show-versions 2>/dev/null); then
    native_say 'code コマンドを利用できないため、拡張機能の確認・導入をスキップします。'
    native_say "macOS は VS Code のコマンドパレットで Shell Command: Install 'code' command in PATH を実行してください。"
    native_say 'Windows は VS Code の bin フォルダーを PATH に追加し、VS Code と端末を開き直してください。'
    return 0
  fi
  for native_extension in $(native_extensions); do
    native_id=${native_extension%@*}
    native_current=$(printf '%s\n' "$native_installed" | tr -d '\r' | awk -F@ -v id="$native_id" 'tolower($1) == tolower(id) {print $2; exit}')
    case $native_extension in
      *@*) [ "$native_current" != "${native_extension##*@}" ] || { native_say "導入済み  $native_extension"; continue; };;
      *) [ -z "$native_current" ] || { native_say "導入済み  $native_id@$native_current"; continue; };;
    esac
    native_say "導入候補  $native_extension（現在 ${native_current:-未導入}）"
    [ "$native_mode" != check ] || continue
    native_say "実行予定  code --install-extension $native_extension --force"
    native_ask 'この拡張機能を導入しますか？ 指定版がある場合はその版へ変更します。' || continue
    if code --install-extension "$native_extension" --force; then
      if ! native_after=$(code --list-extensions --show-versions); then
        native_failed=1
        continue
      fi
      native_actual=$(printf '%s\n' "$native_after" | tr -d '\r' | awk -F@ -v id="$native_id" 'tolower($1) == tolower(id) {print $2; exit}')
      case $native_extension in
        *@*) [ "$native_actual" = "${native_extension##*@}" ] || { native_say "指定版を確認できませんでした: $native_extension"; native_failed=1; };;
        *) [ -n "$native_actual" ] || { native_say "導入を確認できませんでした: $native_extension"; native_failed=1; };;
      esac
    else
      native_failed=1
    fi
  done
}

native_workspace() {
  native_ask 'リポジトリの取得とワールド設定へ進みますか？' || return 0
  native_say 'ワールドは、空欄で現在の設定を維持、default で既定に戻します。'
  native_say '既存ワールドを使う場合はパスを入力してください。そのワールドに直接保存されます。'
  printf '> '
  IFS= read -r native_world || exit 130
  case $native_world in
    '') sh "$NATIVE_SCRIPT_DIR/setup.sh";;
    default) sh "$NATIVE_SCRIPT_DIR/setup.sh" --default-world;;
    *) sh "$NATIVE_SCRIPT_DIR/setup.sh" -- "$native_world";;
  esac
}

native_main() {
  native_mode=interactive; native_failed=0
  case $# in
    0) :;;
    1) case $1 in
      --check) native_mode=check;;
      --help|-h) native_say 'Usage: sh scripts/setup-native.sh [--check]'; native_say 'Windows の Git Bash / macOS 用。--check は導入状況の確認だけを行います。'; return 0;;
      *) native_say "不明な引数: $1" >&2; return 2;;
    esac;;
    *) native_say 'Usage: sh scripts/setup-native.sh [--check]' >&2; return 2;;
  esac
  native_platform || return 1
  DEVSPACE_ROOT=$(CDPATH='' cd -- "$NATIVE_SCRIPT_DIR/.." && pwd); export DEVSPACE_ROOT
  # shellcheck source=scripts/lib/common.sh
  . "$NATIVE_SCRIPT_DIR/lib/common.sh"
  ds_config_load || return 1
  native_refresh_path
  if ! native_probe git || ! native_probe curl; then
    native_say 'Git と curl が必要です。Windows は Git for Windows、macOS は Command Line Tools を先に導入してください。' >&2
    return 1
  fi
  native_say "DevSpace のネイティブセットアップ / $native_os"
  native_say 'Java はサーバー用、その他のツールと拡張機能は任意です。Enter でスキップできます。'
  native_tools
  native_editor
  if [ "$native_mode" = interactive ]; then
    native_workspace || native_failed=1
    if native_probe gh && native_ask 'GitHub CLI の認証状況を確認し、未認証ならログインしますか？'; then
      if ! gh auth status; then
        gh auth login --web --git-protocol https || native_failed=1
      fi
    fi
    for native_ai in codex claude; do
      if native_probe "$native_ai"; then
        native_say "$native_ai の認証は、端末を開き直して DevSpace で $native_ai を起動して行います。"
      fi
    done
    native_say 'サーバーは Minecraft EULA に同意後、sh scripts/server.sh で起動します。'
  fi
  if ! native_probe java; then
    native_say 'サーバー用の Java 17 以上が未準備です。JAVA_BIN または PATH を確認してください。'
    native_failed=1
  fi
  if [ "$native_failed" -ne 0 ]; then
    native_say '未完了の項目があります。表示したエラーを解消し、再実行してください。' >&2
    return 1
  fi
  native_say '確認を終了しました。任意項目の導入状況は上の表示を確認してください。'
}

if [ "${DEVSPACE_NATIVE_LIBRARY:-0}" != 1 ]; then native_main "$@"; fi
