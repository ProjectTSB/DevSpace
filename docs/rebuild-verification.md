# rebuild 後の検証記録

実施日: 2026-09-14。対象は再構築後の Linux DevContainer。Minecraft クライアントのゲーム画面ではなく、実 Vanilla サーバーのコンソールから `reload` 等を実行した。

## DevSpaceを入口とする運用

現在の標準は、AIの開始位置とコンテナの初期 `workspaceFolder` を `/workspaces/DevSpace` にし、コード補完が必要な場合だけ対象repoを別ウィンドウで開く構成。通常の端末・サーバーtaskはDevSpaceを基準にし、並列担当は個別worktreeを使う。DevSpaceの `.vscode/settings.json` にDHP 3.4.19向けの自動索引除外を設定している。

DevSpace起点の運用について、初期フォルダー・端末・サーバーtaskの設定、各 `CLAUDE.md` から同じ場所の `AGENTS.md` への参照、関連文書のリンク先、子repoでのナレッジ検索・Gitルートを確認した。共通規約はDevSpaceに集約し、子repoのAGENTSは開始位置の案内だけとした。通常の参照経路はDevSpaceから対象作業コピーのナレッジREADMEへ直接進む。共通規約の複製指示と子AGENTSの旧見出しへの参照が残っていないことを静的に確認した。これらは設定と案内経路の確認であり、新しいAIセッションによる自発的な参照・実装の実測ではない。

setupテストとruntimeの13テストは成功した。

初期フォルダー変更後のコンテナ再作成、DHP 3.4.19での索引除外・表示・補完、新しいAIセッションでの規約参照は今回未確認。下表のAsset単独ウィンドウの検証は以前の条件の記録である。既存コンテナでは `code -n /workspaces/DevSpace` から新しいAIセッションを開始できる。

## 2026-09-26: GitHub CLI の標準導入と認証保存

GitHub CLI Feature と専用の設定ボリュームを追加し、Dev Containers CLI で lockfile を更新した。既存 Node Feature の解決先は変更していない。JSON と Feature の lockfile の整合、`git diff --check`、setup テスト、runtime の13テストが成功した。初回認証の手順は [README](../README.md#github-cli-と認証の保存) を参照。

このセッションでは Docker CLI・socket を利用できないため、新構成のビルド、初回ボリュームの所有権、rebuild を挟んだ認証再利用は未検証。受入確認は、新構成で `gh --version` と `test -w "$GH_CONFIG_DIR"` を実行し、初回ログインした後に、同じ DevContainer を再度 rebuild して `gh auth status` が成功すること。

## 2026-10-01: DHP 3.4.19 の固定とキャッシュ保存

DevContainer の拡張指定を `SPGoding.datapack-language-server@3.4.19` に固定し、DHP の共通保存先と VS Code の `workspaceStorage` に名前付きボリュームを設定した。Dockerfile で保存先と親ディレクトリを `vscode` 所有で作成する。対象範囲と初回適用手順は [README](../README.md#dhp-のバージョン固定とキャッシュ保存) を参照。

保存先は Marketplace からインストールした 3.4.19 の `dist/extension.js` と `dist/server.js` で確認した。拡張は VS Code の `ExtensionContext.globalStoragePath` と `storagePath` をサーバーへ渡し、サーバーは前者に共通データと `plugins`、後者に `cache.json` を保存する。したがって DHP 4.x の `~/.cache/spyglassmc-nodejs` だけを保存しても、3.4.19 のキャッシュは保持できない。API 上の保存範囲は [VS Code ExtensionContext](https://code.visualstudio.com/api/references/vscode-api#ExtensionContext)、バージョン付き ID の形式は [VS Code の DevContainer schema](https://github.com/microsoft/vscode/blob/main/extensions/configuration-editing/schemas/devContainer.vscode.schema.json) を参照。

現在のコンテナでは `code --install-extension SPGoding.datapack-language-server@3.4.19 --force` が成功し、インストール情報の `version: 3.4.19` と `metadata.pinned: true` を確認した。設定の JSON、公式 schema の拡張 ID 形式、マウント先と Dockerfile の作成先の一致、`git diff --check`、setup テスト、runtime の13テストが成功した。

Docker CLI・socket がないため、新構成のビルド、マウント後の書込権限、rebuild を挟んだキャッシュ再利用は未検証。現在のウィンドウでの 3.4.19 の再読込と補完動作も未確認。受入確認は次の手順で行う。

1. `Dev Containers: Rebuild Container` 後、拡張の表示が 3.4.19 であることと、上記2つの保存先に `vscode` で書き込めることを確認する。
2. 対象repoを別ウィンドウで開いて mcfunction を表示し、DHP の出力の `globalStoragePath` と `cachePath` がボリューム配下であること、共通データと `cache.json` が生成されることを確認する。
3. 保存されたファイルのパスとハッシュを記録し、同じ DevContainer を rebuild する。対象repoを開く前にファイルの保持を照合し、そのrepoを開いて DHP のキャッシュ読込と補完・診断を確認する。初回導入時は旧コンテナのキャッシュを引き継がず、生成後の次回 rebuild から保持する。

## 2026-10-03: AI CLI の開始位置の自動切替

`scripts/ai-shell.bash` にBash関数を追加し、Dockerfileの既存aliasを、このファイルの読込へ置き換えた。現在のコンテナの `/etc/bash.bashrc` にも同じ読込行を反映した。利用方法と適用範囲は [READMEの起動手順](../README.md#起動) を参照。

`bash tests/ai-shell.bash` で両CLIをスタブに置き換え、通常の2 repoと配下からの移動、DevSpace・別ディレクトリ・類似名・AnimatedJava・linked worktree・入れ子の別repoの除外を確認した。空白・日本語・symlinkを含むパス、既存aliasの置換、再読込、引数・標準入力・終了コード・親シェルの位置の保持も成功した。setupテスト、runtimeの13テスト、Bash構文検査、`git diff --check` も成功した。

現在のコンテナで新規の対話Bashを起動し、実際のAsset・TheSkyBlessingを開始位置として、PATH上の両CLIスタブがDevSpaceで呼ばれ、親シェルは元のrepoに留まることを確認した。AIの実セッションによる規約読取と、Dockerfile変更後のrebuildは未検証。rebuild後は新しいBashで `type codex claude` が関数を示すことと、両repoから開始した新規CLIセッションの作業位置を確認する。

## 2026-10-03: 個人用AIスキルの保存

Dockerfileで `~/.agents` を `~/.codex/agent-data` への相対リンクとして作成し、既存のCodex用ボリュームで個人スキルとインストーラーの管理情報を保存する構成にした。既存ボリュームには新しいディレクトリがない場合があるため、`postCreateCommand` でもリンク先を作成する。任意スキルの導入・更新・削除手順は [README](../README.md#個人用のai設定と任意スキル) に記載した。スキル本体をイメージへ組み込む処理は追加していない。

現在のコンテナにも同じディレクトリとリンクを作成した。`findmnt` でリンク先が既存のCodex用ボリュームに含まれることを確認した。`skills` CLI 1.7.0でユーザー領域へ導入し、Claude Codeのスキルディレクトリから同じ実体へのリンクと、`~/.agents/.skill-lock.json` の取得元情報を確認した。個人の導入状態はGit管理外に置いている。

最初のrepo直下からの導入では、配布物に同じスキルの入れ子があり、Codexの `skills/list` が `yomiyasu:yomiyasu` を2件返した。`yomiyasu` 1件を期待した確認は失敗した。配布repoの `skills/yomiyasu` を指定して再導入後、Codex CLI 0.157.1のapp-serverが `scope=user`、`enabled=true` の1件を返し、読込エラーがないことを確認した。導入例にもこのサブディレクトリ指定を使用する。

設定JSON、`postCreateCommand` のシェル構文、`git diff --check`、setupテスト、runtimeの13テストが成功した。既存ボリュームにリンク先がない状況を一時ディレクトリで再現し、初期化後に書き込めることと、ホーム側のリンクを作り直してもデータを参照できることを確認した。これはファイルシステム上の模擬確認であり、コンテナrebuildの実測ではない。

Docker CLI・socketがないため、新構成のビルドとrebuildを挟んだ保存は未検証。Claude Code 2.1.288については配置とリンク先の照合までで、新しい対話セッションからの呼出は未確認。受入確認は、同じDevContainerをrebuildして `readlink -f ~/.agents` と `npx skills list --global` を確認し、両ツールの新しいセッションでスキル一覧から選択して短文を推敲すること。実体と管理情報の保存確認はボリュームを維持した条件で行う。現在のCodex検出結果はGit管理外の `.runtime/verification/personal-skills/codex-discovery.json` に保存した。

## 2026-10-03: ネイティブ環境の対話セットアップ

Windows の Git Bash と macOS 向けに `scripts/setup-native.sh` を追加した。ツールの検出・選択・導入後の確認、VS Code 拡張機能の個別導入、既存 `setup.sh` へのワールド指定の受け渡し、任意の GitHub 認証を行う。VS Code 本体は導入対象に含めない。操作手順は [README](../README.md#devcontainer-を使わない場合の対話セットアップ)、既存の起動処理と分ける理由は [環境設計](development-environment-design.md#既存の起動操作と-optional-の範囲) に記載した。

Linux 上で `sh tests/setup-native.sh` を実行し、OS と外部コマンドを模擬して次を確認した。実際のパッケージ導入や認証は行っていない。

- 両 OS のパッケージ指定、導入済みツールの維持、個別スキップ、確認専用モード、未対応 OS と不正な引数の拒否。
- Java の最低版と `JAVA_BIN` の参照、導入コマンドの失敗、成功を返してもツールが使えない場合の未完了判定。
- 入力終了・終了選択での中断、不正な回答の再入力、Homebrew 導入の選択と中断、取得失敗時にインストーラーを実行しないこと、winget 不在時の案内。
- Windows の PATH を文字列として変換する処理、VS Code CLI 不在時の案内、DHP の指定版への変更と事後確認、DevContainer の拡張一覧との一致。
- 空欄・既定・空白や日本語とシェル記号を含むワールド指定の受け渡し、GitHub 認証で平文保存や同意の省略を指定しないこと。

新規テスト、`sh tests/setup.sh`、`sh tests/runtime.sh` の13項目、シェル構文検査、`git diff --check` が成功した。新規テストの結果は Git 管理外の `.runtime/verification/native-setup/tests.log` に保存した。

導入方法は [winget install](https://learn.microsoft.com/en-us/windows/package-manager/winget/install)、[Homebrew の導入](https://docs.brew.sh/Installation)と[コマンド仕様](https://docs.brew.sh/Manpage)、[VS Code CLI](https://code.visualstudio.com/docs/configure/command-line)で確認した。パッケージ名は [WinGet の配布定義](https://github.com/microsoft/winget-pkgs/tree/master/manifests)、[Temurin 17](https://formulae.brew.sh/cask/temurin@17)、[Codex](https://formulae.brew.sh/cask/codex)、[Claude Code の導入手順](https://code.claude.com/docs/en/setup)と照合した。Codex の初回認証は [公式 CLI ドキュメント](https://learn.chatgpt.com/docs/codex/cli)を参照した。

Windows / macOS の実機でのインストール、管理者認証、実際の PATH 反映、Homebrew の初回導入、ブラウザーでの認証、拡張機能の動作は未検証。受入確認では、各 OS の通常ユーザーで必要な項目を導入し、VS Code と端末を開き直して `--check` の結果を確認する。DHP の版を確認後に再実行し、既存ツールが再導入されないことと、ワールド指定が既存の設定へ保存されることを照合する。機能検証 runner の対応環境は引き続き Linux / DevContainer。

## 確認できたこと

| 対象 | 結果・根拠 |
| --- | --- |
| コンテナ | `DEVSPACE_CONTAINER=1`、OpenJDK 17.0.20、DevSpace 全体と `/workspaces/.tsb-world` の bind mount を確認。外部ワールド未指定なので後者の実体はホストの `.runtime`。Docker CLI はコンテナ内にない。 |
| オフライン検証 | `sh tests/setup.sh` 成功、`sh tests/runtime.sh` 13項目成功。コンテナ環境変数を引き継いでテストが失敗する問題を修正し、再構築後の既定ワールド受入・古いマウント設定拒否・コンテナからのホスト設定書換拒否を追加確認。 |
| EULA | ユーザーの明示同意により Git 管理外の `devspace.local.conf` に `ACCEPT_EULA=true` を保存。runtime に `eula=true` が生成された。 |
| jar | Minecraft 1.20.4 の SHA-1 は `8dd1a28015f51b1803213892b50b7b4fc76e594d`。実サーバーの起動と TCP 25565 の Minecraft status 応答（1.20.4 / protocol 765）を確認。 |
| リソースパック | 既定 GitHub URL から取得成功。取得ファイルと設定された SHA-1 は `3b8c06620694d83a9f6672566781ff0a303fc409` で一致。この値は検証時点の取得結果であり固定値ではない。 |
| 新規ワールド | `.runtime/world` に新規生成。`active-world` と各 pack のリンクが Minecraft の許可検査を通過。本体 storage の `GameVersion="v1.0.6"`、`IsDatapackDeficient=0b` を確認。 |
| dist | 23個の pack を自動検出・有効化。`datapack list` は Vanilla を加えて24個、有効化待ちなし。 |
| 保存 → reload | Asset 内に一時 namespace `devspace_verify` を作成。関数・function tag の追加後に storage 値1、関数編集・タグへの別関数追加後に値2と追加値3を確認。関数削除後は `Unknown function`、タグから削除した関数は実行されず、タグ自体の削除後は `Can't find any functions`。リンク準備の再実行やコピーは挟んでいない。一時ファイルと storage フィールドは除去済み。 |
| master と overlay | サーバー停止後に AJ を通常の `git switch master` で切替。旧16個のモデルリンクが除去され、7個の pack（Vanilla 込み8個）で起動。overlay 内に一時関数を追加し、`reload` 後に storage 値4を確認。一時ファイルは除去済み。互換性の制約は次節参照。 |
| ワールド再利用・dist 復帰 | 同じワールドで dist → master → dist と切替。復帰時に23 pack が自動有効化され、`IsDatapackDeficient=0b`、`GameVersion="v1.0.6"` を確認。新規ワールドへの置換は行われていない。 |
| 停止・後始末 | 初回と master は `stop` により全 dimension 保存ログ・終了コード0を確認。dist 復帰後は Ctrl-C により終了コード130、Java 終了、`level.dat` の停止時更新、両ロック除去を確認。最終状態は AJ dist、23個のリンクが正しい参照先を指し、サーバー停止済み。子 repo のコミットと作業差分は検証前の状態に戻っている。 |
| VS Code | Asset を `code -n /workspaces/DevSpace/Asset` で別ウィンドウに開いて mcfunction を表示。`SPGoding.datapack-language-server` 4.12.0 が起動し、ログで `projectRoots = file:///workspaces/DevSpace/Asset/` と pack format 26 → 1.20.4 の選択を確認。本体・AJ・runtime・worktree がプロジェクトルートに含まれていない。 |
| 独立 Git / worktree | 3 repo の Git 管理領域がそれぞれの `.git` 内にあることを確認。Asset の一時 detached worktree を `.worktrees/rebuild-verification/Asset` に作成して Git 参照と clean 状態を確認後、通常の `git worktree remove` で除去。 |

## 判明した制約

- 本体の `core:load_once` は `ExpectedDatapackCount=23` を設定し、`core:check_datapack_deficient` は個数で判定する。AJ master は構造上7 pack なので `IsDatapackDeficient=1b` になる。pack の検出・overlay 読込は成功しているが、現在の本体と AJ master のゲーム上の完全互換性を合格とは扱わない。本体の判定方式変更は行っていない。
- dist → master の最初の起動では、ワールドの前回有効 pack 記録に対する `Missing data pack file/AJ_*` 警告と、初回 `datapack list` の汎用エラー表示を確認。`reload` 後の一覧は8個・追加候補なしで正常。古い管理リンクは残っていなかった。
- 実行中に既存 pack の `minecraft:empty` loot table 再定義警告、再起動時に既存 UUID の重複警告、起動・reload 前後に `Can't keep up` 警告が出た。ゲーム機能全体の正常性や性能を保証する検証ではない。AJ 性能比較は実施していない。

## この環境だけでは完了扱いにできない項目

- Windows Git Bash / NTFS junction と macOS ネイティブの実機検証。
- ホストの別ワールドを指定して W1 マウントを再作成する検証。今回は外部ワールド未指定。外部パス・衝突保護・設定不一致の拒否はオフライン検証の範囲。
- Minecraft クライアントからの接続、リソースパック適用、配布ワールド固有の地形・保存データを使うゲーム機能確認。
- エディタでの外部宣言の補完内容の確認。言語サーバーの起動・対象範囲・版選択は確認済み。
- 当初は後工程だった本体・Asset の PR レビュー由来の知識整理と入口作成は、その後の依頼で実施。[知識の検証記録](knowledge-verification.md) に検証範囲を記載する。

生ログは Git 管理外の `.runtime/verification/` に保存している。

## 2026-09-19: 検証失敗からの復旧と共通手順

神器1412の元検証では、使い捨てruntimeの初回起動を最大ヒープ2GBで実行し、約2GBのヒープ使用とGCスレッド高負荷、TERMへの応答遅延を観測した。検証JavaをKILLした後、4GBかつTTYで再起動して機能検証と正常停止に成功した。条件を2つ変えているため、メモリだけ、またはTTYだけが原因だったと断定しない。根拠は `docs/knowledge-verification.md` の元セッション監査とローカルログ。

この試行錯誤を繰り返さないため、[共通の機能検証手順](runtime-verification.md) と `scripts/verify.sh` を追加した。最大ヒープ4GB、専用world、プロトコルクライアント、操作と期待値のシナリオ、実測したtick数、失敗を含む各試行と停止方法の記録を共通化した。通常起動の方式やW1マウントを変更するものではない。コンテナのPython 3依存をDockerfileへ追加したが、今回の実行確認は現在のコンテナにあるPython 3を使用する。Dockerfile変更後のrebuildは別の確認になる。

## 2026-09-15: 並列作業からの実行確認

Asset の別 worktree で作成した2つの検証用関数を統合し、参照元を統合 worktree に指定して実 Vanilla 1.20.4 サーバーを起動した。3ケースすべてが成功し、reload 後の再実行でも成功3・失敗0だった。既定 world は事前退避して一時 world を使用し、正常停止後に元のファイル・リンク・設定を照合して復元した。W1 の変更や再作成はしていない。小規模な別ファイル実装の検証であり、競合解消やゲーム機能全体の検証ではない。詳細は [並列実装の検証記録](knowledge-verification.md) を参照する。
