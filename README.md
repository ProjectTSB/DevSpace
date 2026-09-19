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

メモリ量などの詳細設定が必要な場合は、`devspace.local.conf.example` を参考に `devspace.local.conf` を編集できます。すでに保存された設定を上書きしないようにしてください。

設定ファイルはシェルとして実行せず、1行1項目の `key=value` です。利用できるキーは `WORLD_PATH`、`THE_SKY_BLESSING_PATH`、`ASSET_PATH`、`ANIMATED_JAVA_PATH`、`RESOURCEPACK_URI`、`JAVA_BIN`、`JAVA_XMS`、`JAVA_XMX`、`SERVER_PORT`、`ACCEPT_EULA` です。EULA に同意した後、`ACCEPT_EULA=true` を設定するか、runtime の `eula.txt` に `eula=true` を置きます。

## 起動

DevContainer は空の VS Code ウィンドウで `Dev Containers: Open Folder in Container...` を選び、DevSpace を指定して開きます。初期ワークスペースは Asset です。別リポジトリはコンテナ端末から `code -n /workspaces/DevSpace/TheSkyBlessing` のように開くか、既存コンテナへ attach します。`shutdownAction` は `none` なので全ウィンドウを閉じても停止しません。停止は Remote Explorer の `Stop Container` を使います。

各リポジトリを単独の VS Code ウィンドウで開き、`Open SkyBlock Server` タスクを実行します。端末からは `sh scripts/server.sh`、確認だけなら `sh scripts/server.sh --check`、pack の準備だけなら `sh scripts/server.sh --prepare` を使います。Windows の Git が標準場所以外にある場合は、タスクの `windows.command` を実際の `bash.exe` のパスへ変更してください。

保存後、Minecraft が対応する変更は `/reload` で反映します。サーバー停止は端末で Ctrl-C です。リソースパックは `RESOURCEPACK_URI` を使い、起動時に hash を更新します。

リソースパックは既定で TSB-ResourcePack の `dev` リリースを使います。起動スクリプトが URL と SHA-1 を `server.properties` に設定するため、クライアント側でサーバーリソースパックを許可すると接続時に取得・適用されます。ローカルで編集したリソースパックを自動配信する仕組みではありません。起動時の取得と設定は検証済みですが、ゲームクライアントでの適用は未確認です。

ポートを変える場合は、サーバー停止後に `devspace.local.conf` の `SERVER_PORT=25566` のような設定を追加・変更し、再起動します。DevContainer の明示的な自動転送設定は `.devcontainer/devcontainer.json` の `25565` 固定で、`SERVER_PORT` とは連動しません。変更後のポートは VS Code の「ポート」欄から転送を追加し、表示された転送先へ接続してください。この設定経路は `scripts/lib/runtime.sh` とコンテナ設定のコードで確認したもので、変更ポートでのクライアント接続は未検証です。

並列作業には各リポジトリの通常の worktree を使います。例えば DevSpace ルートから Asset の worktree を作る場合は次の通りです。

```sh
git -C Asset worktree add -b feature-name ../.worktrees/feature-name/Asset
```

worktree を別ウィンドウで開き、そこで編集したコードをサーバーで使う場合はローカル設定の `ASSET_PATH` 等をそのパスにします。起動したウィンドウの worktree が自動選択される仕組みではありません。サーバーを停止してから参照先を変更し、再起動時に表示される参照元を確認します。

並列に分離されるのは作業ツリーです。サーバーとワールドは共通の1組を順番に使い、設定変更・起動停止・`/reload` の担当を揃えます。runtime/world のロックは二重使用を防ぎますが、設定ファイルの編集や作業者間の検証順序は調整しません。別 feature の同時実機検証用の環境は用意していません。

新しい worktree に元の作業ツリーの未コミット変更・未追跡ファイルは引き継がれません。ナレッジや起動設定を含め、必要な開始状態が新しい作業コピーにあることを確認してください。[ナレッジの共有と検証](docs/knowledge-maintenance.md#共有と検証) を参照します。AnimatedJava の生成環境と性能評価は今回のセットアップ対象外です。

## Agent の開発ナレッジ

TheSkyBlessing と Asset の各 repo に `AGENTS.md` と `docs/knowledge/` を配置しています。毎回の規約と、API・神器・Mob など実装・レビュー・調査の対象に応じて Agent が選んで読む文書を定義しています。`CLAUDE.md` も同じ規約を参照します。

レビューの根拠・採用状況は各 repo の `docs/knowledge/sources.md`、知識の更新と共有方法は [ナレッジの配置と更新](docs/knowledge-maintenance.md) を参照してください。子 repo の文書は各 repo 側の変更として管理します。

## 検証

セットアップと runtime のオフライン検証は次で実行できます。

```sh
sh tests/setup.sh
sh tests/runtime.sh
```

独立 clone の変更は親 DevSpace の `git status` には表示されないため、各リポジトリで `git status` を確認してください。child 側の `.vscode/`、`.gitattributes`、Agent の入口とナレッジは各リポジトリの履歴で管理します。他環境への共有には各リポジトリの push が必要です。

rebuild 後の Java 17、実 Minecraft 起動、新規ワールド生成、コンソールの `reload` による関数・タグの追加／編集／削除反映、Asset 単独ウィンドウの言語サーバー、worktree の Git 参照まで検証済みです。加えて、コミット済みの Asset から別 worktree で2つの小さな関数を並列実装し、統合後に共有サーバーで実行・reload、元ワールドへ復元する流れを確認しました。範囲は [並列実装の検証記録](docs/knowledge-verification.md) を参照してください。通常利用の AnimatedJava `dist` では23 pack が有効になります。

AnimatedJava `master` はリンク・overlay 読込に成功しますが、本体の既存「23 pack 未満なら欠損」判定により欠損フラグが立ちます。Windows/macOS 実機、外部ワールドの W1 マウント変更、ゲームクライアントでの確認は未完了です。本体・Asset の知識整理は [知識の検証記録](docs/knowledge-verification.md) に記載しています。結果と制約は [rebuild 後の検証記録](docs/rebuild-verification.md) を参照してください。
