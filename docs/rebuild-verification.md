# rebuild 後の検証記録

実施日: 2026-09-14。対象は再構築後の Linux DevContainer。Minecraft クライアントのゲーム画面ではなく、実 Vanilla サーバーのコンソールから `reload` 等を実行した。

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
