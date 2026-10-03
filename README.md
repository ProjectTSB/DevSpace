# DevSpace

TheSkyBlessing、Asset、Asset-AnimatedJava の3リポジトリを使う Minecraft Java Edition 1.20.4 開発環境です。サーバーは Vanilla、Java 17 以上を対象にします。

## 初回セットアップ

必要なのは Git と、ネイティブ実行時の Java 17 以上です。Windows は Git Bash を使います。DevContainer を使う場合、Java はコンテナ内に入るためホストへの Java インストールは不要です。

DevSpace を clone し、Git Bash または macOS/Linux のシェルで次を実行してください。

```sh
sh scripts/setup.sh
```

3つのリポジトリが存在しない場合は自動で clone されます。AnimatedJava は初回 `dist` ブランチを取得します。既存の clone の remote、branch、未コミット変更は変更しません。DevContainer を使う場合は、フォルダーを開く前に次を実行します。

```sh
sh scripts/setup.sh --container
```

既存ワールドを使うときは、ホストの端末でフォルダーのパスを引数に渡します。環境変数や設定ファイルの手動編集は不要です。

```sh
# DevContainer 用（ホスト側で実行）
sh scripts/setup.sh --container "/path/to/My World"

# ネイティブ用
sh scripts/setup.sh "/path/to/My World"
```

空白を含むパスは引用符で囲みます。相対パスはコマンドを実行したディレクトリが基準です。指定は Git 管理外の `devspace.local.conf` に絶対パスで保存され、次回から省略できます。対象は既存ワールドのフォルダーで、サーバーの保存もそのワールドへ直接反映されます。

指定履歴がなければ `.runtime/world` が初回に自動生成され、以後再利用されます。既定ワールドに戻すときは `sh scripts/setup.sh --container --default-world`（ネイティブでは `--container` を省略）を実行します。元のワールドは削除されません。

DevContainer 用のマウント設定も setup が自動生成します。ワールドの場所を変更したら、コンテナを再作成してください。コンテナ内からのワールド指定は受け付けません。

### GitHub CLI と認証の保存

DevContainer は GitHub CLI (`gh`) を標準でインストールします。初回はコンテナ内で次を実行します。

```sh
gh auth login --web --git-protocol https --insecure-storage
gh auth status
```

設定と認証情報は専用の名前付きボリュームに保存され、同じ DevContainer の rebuild 後も再利用します。`--insecure-storage` は、トークンを OS の credential store ではなく、このボリューム内のファイルへ平文で保存する指定です。[GitHub CLI の認証仕様](https://cli.github.com/manual/gh_auth_login)

ボリュームを削除した場合や、DevSpace の配置変更などで `devcontainerId` が変わった場合は再ログインしてください。環境変数 `GH_TOKEN` 等で渡す認証情報は、この仕組みでは保存しません。

### 個人用のAI設定と任意スキル

文体の好みや任意スキルは、各ツールのユーザー領域へ設定します。チームの開発規約は `AGENTS.md` で共有し、個人用スキルの導入は各自で選びます。個人用スキルを使う場合も、コミットのGitmojiなど成果物に指定された形式を維持してください。

DevContainerは `~/.claude` と `~/.codex` を名前付きボリュームに保存します。Codexの個人スキル配置先 `~/.agents/skills` とインストーラーの管理情報も保存するため、`~/.agents` は `~/.codex/agent-data` へのリンクにしています。同じ `devcontainerId` のrebuildでは再利用できますが、ボリュームを削除した場合や別環境では再導入が必要です。共有する設定には保存先だけを定義し、個人が選んだスキル本体や認証情報は含めません。

例えば、日本語の推敲用スキル [yomiyasu](https://github.com/nanaism/yomiyasu) を使う人は、コンテナ内の端末で次を実行します。ネイティブ環境でもNode.jsとnpmがあれば同じコマンドを使えます。

```sh
# 自分のClaude CodeとCodexへ導入
npx skills add https://github.com/nanaism/yomiyasu/tree/main/skills/yomiyasu --global --agent claude-code codex

# 個人用スキルの確認・更新・削除
npx skills list --global
npx skills update yomiyasu --global
npx skills remove yomiyasu --global --agent claude-code codex
```

`--global` はその環境のユーザー領域への導入を指定します。省略するとプロジェクト内への導入になるため、個人用では必ず付けてください。上の例では同名スキルの重複読込を避けるため、配布repo内の `skills/yomiyasu` を指定しています。

導入後はClaude Codeの `/` メニューやCodexの `/skills` からyomiyasuを選び、推敲する文章を渡します。プラグイン名を含む `yomiyasu:yomiyasu` として表示される場合があります。表示されない場合は新しいセッションを開始します。

配置先と操作の仕様は [Codexのスキル](https://learn.chatgpt.com/docs/build-skills)、[Claude Codeのスキル](https://code.claude.com/docs/en/skills)、[skills CLI](https://github.com/vercel-labs/skills) を参照してください。別環境でも同じ構成を再現したい場合は、導入コマンドを個人のdotfiles repo等へ保存します。検証範囲は [検証記録](docs/rebuild-verification.md#2026-10-03-個人用aiスキルの保存) を参照してください。

### DHP のバージョン固定とキャッシュ保存

DevContainer の Data-pack Helper Plus は、`.devcontainer/devcontainer.json` の `SPGoding.datapack-language-server@3.4.19` で固定します。版を更新するときはこの指定を変更し、索引除外設定との互換性も確認してください。特定バージョンのインストールは DHP の自動更新を抑止します。

DHP 3.4.19 の保存先を、`devcontainerId` ごとの名前付きボリュームで永続化します。

| 保存対象 | コンテナ内のパス |
| --- | --- |
| Minecraft の定義などの共通データと DHP プラグイン | `/home/vscode/.vscode-server/data/User/globalStorage/spgoding.datapack-language-server` |
| ワークスペース別の解析キャッシュ | `/home/vscode/.vscode-server/data/User/workspaceStorage` 内の `<workspace-id>/spgoding.datapack-language-server/cache.json` |

ワークスペースの ID は VS Code が管理するため、後者は `workspaceStorage` 全体を保存し、他の拡張機能のワークスペース状態も含みます。同じ DevContainer とワークスペースを開けば rebuild 後も再利用できます。ボリュームの削除や `devcontainerId` の変更時は再生成され、別の worktree は別の解析キャッシュになります。DHP 4.x の `~/.cache/spyglassmc-nodejs` は 3.4.19 の保存先ではありません。

保存先の根拠と rebuild 後の確認手順は [検証記録](docs/rebuild-verification.md#2026-10-01-dhp-3419-の固定とキャッシュ保存) を参照してください。

### 詳細設定

メモリ量などの詳細設定が必要な場合は、`devspace.local.conf.example` を参考に `devspace.local.conf` を編集できます。すでに保存された設定を上書きしないようにしてください。

設定ファイルはシェルとして実行せず、1行1項目の `key=value` です。利用できるキーは `WORLD_PATH`、`THE_SKY_BLESSING_PATH`、`ASSET_PATH`、`ANIMATED_JAVA_PATH`、`RESOURCEPACK_URI`、`JAVA_BIN`、`JAVA_XMS`、`JAVA_XMX`、`SERVER_PORT`、`ACCEPT_EULA` です。EULA に同意した後、`ACCEPT_EULA=true` を設定するか、runtime の `eula.txt` に `eula=true` を置きます。

## 起動

DevContainer は空の VS Code ウィンドウで `Dev Containers: Open Folder in Container...` を選び、DevSpace を指定して開きます。初期ワークスペースと端末の開始位置は `/workspaces/DevSpace` です。ネイティブでもDevSpaceのフォルダーを開きます。`shutdownAction` は `none` なので全ウィンドウを閉じても停止しません。停止は Remote Explorer の `Stop Container` を使います。

DevSpaceのウィンドウで `Open SkyBlock Server` タスクを実行します。DevSpaceの端末からは `sh scripts/server.sh`、確認だけなら `sh scripts/server.sh --check`、pack の準備だけなら `sh scripts/server.sh --prepare` を使います。Windows の Git が標準場所以外にある場合は、タスクの `windows.command` を実際の `bash.exe` のパスへ変更してください。

AIの拡張機能はDevSpaceのウィンドウで新しいセッションを開始します。AIセッション開始後にシェルだけを `cd` しても、開始時の規約読込を切り替えたことにはしません。

DevContainer の対話 Bash では、`TheSkyBlessing`・`Asset` とそのサブディレクトリから `codex` / `claude` を実行すると、自動で DevSpace を開始位置にします。終了後の端末位置は変わりません。DevSpace直下の通常の2 repoだけが対象で、別repo・入れ子のrepo・並列担当のworktreeは元の位置で起動します。既存の承認省略オプションと渡した引数は維持しますが、相対パスの引数は移動後のDevSpaceが基準になるため、ファイル指定には絶対パスを使ってください。明示的な作業場所の指定や既存セッションの再開はCLI側の指定に従います。

起動処理は `scripts/ai-shell.bash` にあり、DevContainerの対話Bashで自動読込されます。ネイティブの Bash で同じ動作を使う場合は、実際のDevSpaceの `scripts/ai-shell.bash` を絶対パスで `source` する設定を `~/.bashrc` に追加します。関数を読み込まないシェル、非対話実行、VS Code拡張機能は自動移動の対象外なので、DevSpaceから開始します。

### AIへの依頼とコード補完

**通常のAIへの依頼は、神器・本体・環境変更のいずれもDevSpaceから始めます。** AIがDevSpaceの共通規約に従って対象repoのナレッジを読み、検索・編集・Git操作はそのrepoで行います。例えばAssetの差分は `git -C Asset diff` で確認します。DevSpaceでの `git status` だけでは子repoの変更は分かりません。

DevSpaceのウィンドウはAIへの依頼・環境操作・検証に使い、DHP 3.4.19向けの `.vscode/settings.json` で全packを自動索引から除外する設定にしています。補完・診断が必要なときは `code -n /workspaces/DevSpace/Asset` などで対象repoだけを別ウィンドウに開きます。そこではrepo自身の設定を使います。通常のAIセッションはDevSpace側で続けます。動作確認の範囲は [検証記録](docs/rebuild-verification.md) を参照してください。

保存後、Minecraft が対応する変更は `/reload` で反映します。サーバー停止は端末で Ctrl-C です。リソースパックは `RESOURCEPACK_URI` を使い、起動時に hash を更新します。

リソースパックは既定で TSB-ResourcePack の `dev` リリースを使います。起動スクリプトが URL と SHA-1 を `server.properties` に設定するため、クライアント側でサーバーリソースパックを許可すると接続時に取得・適用されます。ローカルで編集したリソースパックを自動配信する仕組みではありません。起動時の取得と設定は検証済みですが、ゲームクライアントでの適用は未確認です。

ポートを変える場合は、サーバー停止後に `devspace.local.conf` の `SERVER_PORT=25566` のような設定を追加・変更し、再起動します。DevContainer の明示的な自動転送設定は `.devcontainer/devcontainer.json` の `25565` 固定で、`SERVER_PORT` とは連動しません。変更後のポートは VS Code の「ポート」欄から転送を追加し、表示された転送先へ接続してください。この設定経路は `scripts/lib/runtime.sh` とコンテナ設定のコードで確認したもので、変更ポートでのクライアント接続は未検証です。

### 並列開発

並列作業の個別担当は、割り当てたrepoのworktreeから開始します。通常の依頼・分担・統合・共通検証はDevSpace側で管理します。例えばDevSpaceルートからAssetのworktreeを作る場合は次の通りです。

```sh
git -C Asset worktree add -b feature-name ../.worktrees/feature-name/Asset
```

個別担当にはDevSpaceの場所と環境規約、worktreeのパス、変更対象、依存repoの参照先、読む規約を渡します。複数の担当で同じ作業ツリーを同時編集しません。そこで編集したコードをサーバーで使う場合は、DevSpace側でローカル設定の `ASSET_PATH` 等をそのパスにします。起動したウィンドウのworktreeが自動選択される仕組みではありません。サーバーを停止してから参照先を変更し、再起動時に表示される参照元を確認します。

共有DevSpaceの編集・Git操作は一人の統合担当に集約し、開始時に各担当へ知らせます。子repoの担当はコード固有の知識を自分のworktreeへ残し、共通知見は根拠・適用条件・修正案を統合担当へ渡します。統合担当が未マージの子repo変更に依存しないと確認した共通知識は、DevSpaceの `main` へ逐次commit・pushします。引渡しから公開までの手順は [共通知識の逐次反映](docs/knowledge-maintenance.md#共通知識の逐次反映) を参照してください。

知識更新だけを目的にDevSpaceを担当ごとに分離する必要はありません。DevSpaceのスクリプト・環境構成そのものを並列変更する場合は、その実装用worktreeを用意します。

並列に分離されるのは作業ツリーです。通常のサーバーとワールドは共通の1組を使い、設定変更・起動停止・`/reload` の担当を揃えます。自動検証の `scripts/verify.sh` は専用worldを試行ごとに作り、同時実行は1件です。DevSpace側で順序と参照repoを揃え、検証中の参照コードは編集しません。runtime/worldやrunnerのロックは、設定編集や作業者間の順序を調整するものではありません。

新しい worktree に元の作業ツリーの未コミット変更・未追跡ファイルは引き継がれません。ナレッジや起動設定を含め、必要な開始状態が新しい作業コピーにあることを確認してください。[ナレッジの共有と検証](docs/knowledge-maintenance.md#共有と検証) を参照します。AnimatedJava の生成環境と性能評価は今回のセットアップ対象外です。

## Agent の開発ナレッジ

共通規約・ナレッジ参照・更新方針はDevSpaceで一元管理します。TheSkyBlessingとAssetの `AGENTS.md` は、子repoを開始位置とする通常のAI利用を推奨せず、DevSpaceへ案内するために残します。子repoの `docs/knowledge/` にはコード固有の構造・契約・実例を置き、コードと同じブランチで更新します。AIはDevSpaceの案内から必要な本文を読みます。並列担当にはDevSpaceの規約を引き渡し、共通ルールを子repoへ複製しません。各 `CLAUDE.md` は同じ場所の `AGENTS.md` を参照します。

レビューの根拠・採用状況は各 repo の `docs/knowledge/sources.md`、知識の更新と共有方法は [ナレッジの配置と更新](docs/knowledge-maintenance.md) を参照してください。子 repo の文書は各 repo 側の変更として管理します。

## 検証

セットアップと runtime のオフライン検証は次で実行できます。

```sh
sh tests/setup.sh
sh tests/runtime.sh
```

実サーバーでの機能検証は、対象repoに保存したシナリオを共通runnerへ渡すと再実行できます。専用worldで実行し、入力・期待値・実測値・失敗と終了結果を試行ごとに保存します。Linux / DevContainer向けの手順と前提は [機能検証](docs/runtime-verification.md) を参照してください。

```sh
sh scripts/verify.sh Asset/tests/scenarios/dual-rhythm.json
```

独立 clone の変更は親 DevSpace の `git status` には表示されないため、各リポジトリで `git status` を確認してください。child 側の `.vscode/`、`.gitattributes`、Agent の入口とナレッジは各リポジトリの履歴で管理します。他環境への共有には各リポジトリの push が必要です。

rebuild 後の Java 17、実 Minecraft 起動、新規ワールド生成、コンソールの `reload` による関数・タグの追加／編集／削除反映、Asset 単独ウィンドウの言語サーバー、worktree の Git 参照まで検証済みです。加えて、コミット済みの Asset から別 worktree で2つの小さな関数を並列実装し、統合後に共有サーバーで実行・reload、元ワールドへ復元する流れを確認しました。範囲は [並列実装の検証記録](docs/knowledge-verification.md) を参照してください。通常利用の AnimatedJava `dist` では23 pack が有効になります。

AnimatedJava `master` はリンク・overlay 読込に成功しますが、本体の既存「23 pack 未満なら欠損」判定により欠損フラグが立ちます。Windows/macOS 実機、外部ワールドの W1 マウント変更、ゲームクライアントでの確認は未完了です。本体・Asset の知識整理は [知識の検証記録](docs/knowledge-verification.md) に記載しています。結果と制約は [rebuild 後の検証記録](docs/rebuild-verification.md) を参照してください。
