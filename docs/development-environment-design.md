# TheSkyBlessing 開発環境の検討

> 実装進行状況: 独立 clone 移行・起動処理を実装済み。2026-09-14 に rebuild 後の Java 17、setup/runtime 検証、実 Minecraft 起動、コンソールの reload による編集反映、Asset 単独ウィンドウの言語サーバーを確認した。AJ master の本体側 pack 個数判定に制約あり。詳細・未検証項目は [rebuild 後の検証記録](rebuild-verification.md) を参照。本体・Asset の初期ナレッジと各 repo の入口を作成した。知識の検証範囲は [知識の検証記録](knowledge-verification.md) を参照。

調査日: 2026-09-13。ワールド指定・起動時の pack 自動検出・既存操作維持・AJ 性能評価の対象外指定・開発時の必須ナレッジ読み込み・リポジトリ単位の VS Code ワークスペース・submodule から独立 clone への設計変更を反映: 2026-09-14。この文書は設計経緯を含む。現在の実装状況は冒頭のステータスと README を参照し、本体・Asset の初期ナレッジは実装済みで、詳細は各 repo の `docs/knowledge/` を参照する。

## 結論

Minecraft が編集対象の datapack を直接読む構成を採用する。起動時に pack ごとのディレクトリリンクと許可設定を整え、通常の mcfunction / function tag 編集は保存 → `/reload` で反映する。コピー同期、常駐 watcher、通常編集のビルドを必須にしない。

開発体験が大きく改善する場合を除き、既存の操作を維持する。開発者は普段の Git 操作でブランチを選び、サーバーを起動し、編集後に `/reload` する。起動時の準備を自動化し、この流れに同期操作やモード選択を追加しない。

共通の起動処理をネイティブ OS と任意の DevContainer で使う。サーバーは起動処理を実行した環境の Java プロセスとして動かす。AnimatedJava のブランチ名ではなく、現在の作業ツリーにある pack を起動時に自動検出してリンクする。将来追加されたモデルの pack も同じ検出規則で扱う。並列開発は任意の追加機能とする。

DevContainer を利用する場合のワークスペース構成は A を採用する。共通コンテナにDevSpace全体をマウントし、通常のAI開発はDevSpaceを開いて始める。対象repoだけを開くウィンドウはコード補完用、個別worktreeは並列担当用とし、依頼・統合・共通検証はDevSpace側で管理する。

外部ワールドの接続は W1（指定したワールド単体を追加マウント）、任意の並列 feature 開発は P1（同じ環境内で repo ごとの worktree）を採用する。DevContainer 利用時は共通コンテナ内で worktree を別ウィンドウとして開く。

リポジトリの配置は、DevSpace の Git 管理外に通常の独立 clone を置く方式を推奨する。親で3リポジトリのコミットの組み合わせを固定する要件はないため、submodule の gitlink 更新を日常作業に持ち込まない。初回取得後は各リポジトリで普段の Git 操作を行う。

## 調査対象と submodule の修復

当初は `.gitmodules` の定義だけが存在し、親の index に mode `160000` の gitlink がなかった。3ディレクトリは空で、`git submodule status` も出力なしだった。

空ディレクトリを除去して `git submodule add` で登録を補い、各リポジトリのリモート HEAD が指す `master` を取得した。履歴を省略しない通常 clone。各作業ツリーは clean。

| リポジトリ | 調査コミット |
| --- | --- |
| TheSkyBlessing | `f88cdd5bcb2216d24b26e48684f4a7951a686c94` |
| Asset | `8f661ea1003a0e519d9825c55e1dde0ce6edaf80` |
| Asset-AnimatedJava | `5b72dbbccfcc877d1dd08aaed5729595bcf916fa` |

追加調査した `Asset-AnimatedJava` の `origin/dist` は `e48a116501b931a6688d5bd77e8f60c82de27ffa`（2025-12-27T00:27:43+09:00、`v1.0.5 の変更を反映`）。2026-09-14 にリモート HEAD を確認した。当時の調査では checkout を変更せず、作業ブランチとステージ済み gitlink は上表の `master` 側を指していた。

この修復時点では gitlink の追加はステージ済みで、コミット・push はしていなかった。既存の `.devcontainer` 3ファイルのユーザー変更は保持した。上記3コミットの組み合わせのゲーム内互換性は未検証。

この節は調査を可能にした修復の記録であり、今後も submodule を使う方針ではない。現在は全 refs を保持した独立 clone へ移行済みで、移行バックアップは `.git/devspace-migration-backup` にある。

## リポジトリの取得と管理

DevSpace は環境設定・起動処理を管理し、datapack のコードと履歴は各リポジトリで管理する。現在と同じ配置先を使うため、pack の検出やリンクの設計は変わらない。

```text
DevSpace/
  .git/                       # 環境用リポジトリ
  .gitignore
  .devcontainer/
  TheSkyBlessing/.git/         # 通常 clone の独立した Git 管理領域
  Asset/.git/
  Asset-AnimatedJava/.git/
  .runtime/
  .cache/
```

親の `.gitignore` には `/TheSkyBlessing/`、`/Asset/`、`/Asset-AnimatedJava/` と実行時領域を登録する。親で無視しても、各リポジトリ内では通常通りコードを追跡・コミットできる。submodule が親へ記録するものはタグではなく子コミットへの参照であり、この固定が不要な今回の用途では独立 clone のほうが管理項目を減らせる。[Git の submodule 仕様](https://git-scm.com/docs/gitsubmodules)

共有する取得情報は URL・配置先・必要な初回ブランチだけとし、コミット固定の一覧は設けない。初期セットアップでは存在しないリポジトリだけを clone する。本体と Asset はリモートの既定ブランチ、AJ は通常開発向けに `dist` を初回候補とする。初回取得後のブランチは通常の Git 操作で自由に変更できる。

セットアップの再実行で、既存 clone のブランチ、remote、ローカル変更を変更しない。fork 等を使った既存 clone も尊重する。配置先が空でない非リポジトリの場合は理由を示して停止し、上書きしない。サーバー起動は現在の作業ツリーを読むだけで、pull や checkout を自動実行しない。独自の Git 操作体系や開発モードは追加しない。

この方式では親のコミットだけから当時の3リポジトリの組み合わせを再現できず、親の `git status` にも各リポジトリの変更は出ない。各 repo の履歴・タグ・ブランチは従来通り使える。問題調査では各 repo のコミットと変更有無を確認するが、それを親へコミットする必須工程にはしない。

実体を移行する際には `.gitignore` の追加だけでは不十分。現在は gitlink がステージ済みで、各 `.git` は親の `.git/modules/` を参照しているため、ローカル履歴・ブランチ・変更を保持して Git 管理領域を独立させ、親の gitlink と `.gitmodules` の登録を外す必要がある。この段落は移行前の注意事項であり、現在は移行済み。

## 実際に配置する datapack

下記は調査した `master` の作業ツリーから検出できる7 pack と、DevSpace からの相対パス。これは調査時点の構造例であり、起動処理に固定する一覧ではない。各 pack のルートに `pack.mcmeta` があるため、リポジトリのルートを一律にリンクせず、pack ごとにリンクする。`dist` の構造は後述の通り異なる。

| サーバー内の配置名（案） | ソース |
| --- | --- |
| TheSkyBlessing | `TheSkyBlessing/TheSkyBlessing` |
| NaturalMergeSort | `TheSkyBlessing/NaturalMergeSort` |
| OhMyDat | `TheSkyBlessing/OhMyDat` |
| PlayerMotion | `TheSkyBlessing/PlayerMotion` |
| ScoreToHealth | `TheSkyBlessing/ScoreToHealth` |
| Asset | `Asset/Asset` |
| AnimatedJava | `Asset-AnimatedJava/AnimatedJava` |

本体の `data/core/functions/load.mcfunction` が初期化・migration・Asset の登録を行い、`data/core/functions/tick/.mcfunction` が処理順を統括する。Asset は分類別の function tag を公開し、本体から呼ばれる。Asset 単体のサーバー起動を標準の検証環境にはしない。

本体 `data/player_manager/functions/version_check.mcfunction` は DataVersion 3700 / 1.20.4 を検査する。`pack_format: 26` だけで版を推定したものではない。ユーザー指定により Minecraft Java Edition 1.20.4 / Java 17 以上 / Vanilla server を採用する。DevContainer に用意する基準版は Java 17 とし、ネイティブ利用者の Java は17への完全一致を要求しない。Java 17 は [Mojang の当該版メタデータ](https://piston-meta.mojang.com/v1/packages/3bd23e4608a613b0cc4fa30dd26d4aa32b366181/1.20.4.json) でも確認した。17以上を受け付ける方針と、将来の全 Java 版で動作検証済みであることは区別する。

## AnimatedJava の生成物と調査の境界

Asset-AnimatedJava の `master` の Git 管理ファイルは8,448件、そのうち mcfunction は8,325件。モデル単位のディレクトリは27個ある。これは27個の Minecraft namespace という意味ではない。Asset 側も mcfunction が16,494件あるため、構造と代表例を先に見る調査が必要だった。コード調査は3つの `gpt-5.6-luna` / low Effort sub-agent に分担した。

`Asset-AnimatedJava/AnimatedJava/pack.mcmeta` は `directory: animated_java`、`formats: 26` の overlay を指定する。内側の `animated_java/data/` だけをリンクすると、この設定とベースの入口を失う。配置単位は表の通り `AnimatedJava/` 全体にする。

ベースの `AnimatedJava/data/` は67ファイルあり、共通処理と Minecraft の load / tick 入口を含む。overlay の `AnimatedJava/animated_java/` は8,371ファイルある。代表例ではベースも overlay も Animated Java / MC-Build による生成物と明記されている。ベースの load / tick タグは、それぞれ `animated_java:global/on_load` 等と `animated_java:global/on_tick` を呼ぶ。通常の Agent 探索では大量の生成関数を外し、連携調査時には入口と対象モデルだけを読む。

README は Animated Java と MC-Build を案内するが、モデルの生成元、bbmodel、再生成用プロジェクトやビルド設定はこのリポジトリに見つからなかった。`data.ajmeta` は生成ファイル一覧のメタデータで、モデルの編集元ではない。ユーザー指定により AJ の制作環境は対象外とする。生成元の探索や制作ツールの導入を今回の未解決事項に含めず、既存出力の利用・連携と pack 配置を扱う。

このリポジトリにリソースパックの `assets/` や画像・モデル配布物は確認できなかった。リソースパックはユーザー指定により `TheSkyBlessing/.vscode/server-start.sh` の方式を引き継ぐ。既定 URL は `https://github.com/ProjectTSB/TSB-ResourcePack/releases/download/dev/resources.zip`。既存処理は起動ごとにその URL の内容を取得して SHA-1 を計算し、`server.properties` の `resource-pack` と `resource-pack-sha1` へ設定している。`RESOURCEPACK_URI` による個人の URL 指定も維持する。新たな版選択・固定の仕組みは追加しない。共通 sh への移植では取得失敗を検出し、失敗した内容のハッシュで設定を更新しない。

## 起動時の pack 自動検出

`dist` は zip 化されたブランチではなく、共通基盤とモデル群を独立した17 pack に分割したブランチである。リポジトリ直下の `AnimatedJava/` は17ファイルの共通基盤になり、モデル処理は以下の16ディレクトリへ分かれる。それぞれ直下に `pack.mcmeta` がある。

```text
AnimatedJava/
AJ_blazing_inferno/       AJ_convict/
AJ_corundum_twins/        AJ_eclael/
AJ_frestchika/            AJ_haruclaire_v3/
AJ_heiloang/              AJ_karmic/
AJ_lawless_iron_doll/      AJ_lexiel/
AJ_louvert/               AJ_redknight/
AJ_terrible_sonic_bomber/ AJ_triple_rabbits/
AJ_tultaria/              AJ_tutankhamen/
```

例えば `AJ_blazing_inferno/pack.mcmeta` は `pack_format: 26` の独立 pack で、master のような overlay 指定はない。共通の Minecraft load / tick 入口は `AnimatedJava/data/minecraft/tags/functions/` に残る。固定された `AnimatedJava/` だけをリンクする処理では dist のモデル群を失うため、現在の作業ツリーから pack 一覧を検出する。

| 起動時の作業ツリー | 自動検出される AnimatedJava の配置 | 主な用途 |
| --- | --- | --- |
| 調査時の `dist` | 共通 `AnimatedJava/` と16個の `AJ_*/` をそれぞれリンク | AnimatedJava を直接開発しない通常開発 |
| 調査時の `master` | `AnimatedJava/` 全体をリンク | AnimatedJava 関連の開発・内部調査 |
| 将来のブランチ・モデル追加後 | その作業ツリーで検出された全 pack をリンク | ブランチ名・モデル名・個数の追加設定なしで対応 |

調査時の dist は本体・Asset 側6 pack と合わせて23 pack になるが、個数も実装に固定しない。`origin/dist:AnimatedJava/data/animated_java/tags/functions/global/on_load.json` は27モデルの `on_load` を全て列挙している。リンク配置では検出した一式を揃え、名前から使用モデルを推測して省略しない。配置することと実行時に全モデルをロードし続けることは区別し、既存の一部 unload の運用を妨げない。

起動時の検出規則は以下とする。

1. 対象は既存3リポジトリの pack 配置領域。現在は各リポジトリ直下の子ディレクトリを列挙し、直下の `pack.mcmeta` を調べれば全 pack を検出できる。
2. ブランチ名、`AJ_*` の接頭辞、モデルの固定一覧には依存しない。Git の追跡一覧ではなく作業ツリーを見るので、未コミットの新規 pack も対象になる。
3. `pack.mcmeta` が存在し読み取り可能なディレクトリを一つの pack として扱う。JSON/schema の検証は Minecraft に任せ、独自 parser は持たない。pack 内の `data/` や overlay、生成関数へは再帰探索しない。
4. 全候補と配置名の衝突を確認してからリンクを整える。新規 pack は追加し、前回の起動処理が作成したリンクのうち不要になったものは、そのリンクであることを確認して除去する。利用者が置いた実フォルダ・zip・別のリンクは自動削除しない。
5. 現在の検出結果に合わせてリンク許可設定も更新する。繰り返し起動しても重複したリンクや古い pack が残らないようにする。

新しいモデルが同じ配置領域に独立 pack として追加された場合は、次回のサーバー起動時に自動で反映される。既存 pack 内に追加されたモデル・関数は、その pack へのリンクを通じて見えるため通常の `/reload` で反映できる。独立 pack の追加・削除やブランチ間の構造変更は起動時に検出する範囲とし、常駐監視や専用の同期操作は設けない。

ブランチは各独立 clone で通常の Git 操作により選ぶ。起動処理は checkout、pull、reset、stage を実行せず、現在の作業ツリーを使用する。別のモード設定やブランチ別の基準コミット管理を追加しない。今回確認した master と dist の先端が同じ内容を別形式で表す保証はなく、両構造での実行互換性は検証する。

AJ 関連の性能評価はユーザー指定により作業範囲外とする。分割と一部 unload による性能上の利点を設計の前提として扱い、master / dist の優劣を確かめる比較測定は行わない。起動処理は現在の構造に追従し、既存の読み込み・unload の運用を維持する。確認対象は pack の自動検出、リンク配置、通常編集の反映が正しく機能することとする。

## 起動とリンク

実行時ファイルは Git 管理外の `.runtime/`、jar キャッシュは `.cache/` に置く案とする。ワールドを含む実行場所はローカル設定で変更できるようにする。

ワールドは開発者ごとに自由に指定できる。指定は Git 管理外のローカル設定に保存し、共有設定には設定例だけを置く。

| ワールド設定 | 起動時の動作 |
| --- | --- |
| パスを指定 | 指定された既存ワールドを直接使用する。サーバーによる保存もそのワールドに反映する。 |
| 未指定・初回 | `.runtime/world/` に検出した pack 一式のリンクを準備し、Minecraft サーバーの初回起動で新規ワールドを自動生成する。 |
| 未指定・作成済み | 前回作成した `.runtime/world/` を再利用する。 |

相対パスはローカル設定ファイルのあるディレクトリを基準に解決する。明示されたパスが存在しない場合は設定誤りとして表示し、別の新規ワールドへ黙って切り替えない。DevContainer から外部ワールドを指定する場合は、そのワールドもマウントしてコンテナ内で見えるパスを設定する。サーバーの実行ディレクトリとワールドの保存先は分け、外部ワールドには実行ディレクトリからのリンク等で接続する。ワールドへのリンクも許可検証の対象として扱い、OS ごとの動作を検証する。

### 外部ワールドの接続方法（W1 採用）

ワールド指定の操作は `sh scripts/setup.sh --container "/path/to/world"` とする（ホスト側で実行）。ネイティブでは `--container` を省く。パス引数は実行時のカレントディレクトリから解決し、絶対パスをローカル設定へ保存する。引数省略時は前回の指定を維持し、`--default-world` で既定ワールドへ戻す。他のローカル設定を保持して `WORLD_PATH` だけを更新するため、環境変数や設定ファイルの手動編集は必須ではない。ワールドのマウント先変更には引き続きコンテナの再作成が必要。

ユーザー選択により W1 を採用する。未指定時の `.runtime/world/` は既存の DevSpace マウント内にあるため、追加マウントは不要。Compose は未指定時に `.runtime` を bind するが、runtime の既定 world はその配下を使うため追加の外部 world は unused である。ネイティブ実行時も通常のローカルパス指定でよい。以下は比較の記録として残し、W2 は実装対象に追加しない。ワールドをコピー・同期せず指定先へ直接保存する。

| 案 | 個人設定と利用方法 | 切り替えの負担 |
| --- | --- | --- |
| W1: 選択したワールドだけを追加マウント（採用） | ホスト上の任意のワールドをコンテナの固定パスへマウントする。普段使う一つを指定するだけで済む | マウント元を別ワールドに変える場合はコンテナの再作成が必要。共用中のエディタ・Agent にも影響する |
| W2: ワールドを置く親フォルダを追加マウント | 個人が指定したフォルダをコンテナへマウントし、その配下から使うワールドをローカル設定で選ぶ | 同じ親フォルダ内の切り替えはサーバーの停止・起動だけで済む。別の親フォルダを追加・変更する場合はコンテナの再作成が必要 |

W1 のホストパスを共有設定に書き込ませず、個人設定からコンテナ作成時に反映する入口を用意する。指定の追加・変更・解除でマウント構成が変わる場合は、コンテナを再作成して反映する。通常のコード編集や、同じワールドを使った feature 切り替えには、このマウント変更は不要。[VS Code の追加マウント仕様](https://code.visualstudio.com/remote/advancedcontainers/add-local-file-mount)

setup がローカル設定から `.devcontainer/.env` を生成し、Compose がこれを読み込む。`devcontainer.json` が任意のローカル設定ファイルを自動的に合成する構成ではない。必要なマウントはコンテナ作成前に確定させる。コンテナ内のサーバー起動スクリプトだけでホスト側のマウントを追加する構成にはしない。

起動 CLI は次の処理を行う。

1. 現在の作業ツリーから pack を自動検出し、Java の版、利用ポート、既存プロセスを確認する。ワールドはローカル設定から選び、未指定なら既定の保存先を準備する。指定済みの場合はパスと利用可能なワールドであることを検査する。
2. 固定した版の jar をキャッシュから使う。未取得なら公式配布元から取得し、期待するハッシュと照合する。
3. `world/datapacks/<pack名>` から検出したソースへリンクを作成・確認し、以前作成した不要なリンクを除去する。
4. 実行環境で解決されるリンク先を `allowed_symlinks.txt` に許可する。
5. 配置の重複・欠落とワールドの既存 pack 選択状態を確認し、同じ実行ディレクトリで Java を起動する。利用者が無効化した pack を起動のたびに一律で再有効化しない。

Linux / macOS はディレクトリ symlink、Windows のローカル NTFS は junction を第一候補にする。[Microsoft の mklink 文書](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/mklink) は `/j` を directory junction と定義する。Minecraft 1.20.4 からの読込を Windows 上で検証し、未対応の保存先では理由を示す。コピーへの暗黙の切り替えは行わない。

Minecraft にはリンク先の許可検証がある。[1.20 Pre-release 7 の仕様](https://feedback.minecraft.net/hc/en-us/articles/16224502352141-Minecraft-Java-Edition-1-20-Pre-release-7) と [1.20.2 の pack への拡張](https://feedback.minecraft.net/hc/en-us/articles/19703470383757-Minecraft-Java-Edition-1-20-2) に従い、サーバーの実行ディレクトリに許可ファイルを用意する。全パス許可にせず、選択した pack の実体パスを許可する。

リンクは実行する OS / コンテナ内で生成し、Git へ入れない。ホストで作った絶対パスのリンクを、そのままコンテナへ持ち込む方式にはしない。既存ワールドに実フォルダや zip の同名 pack がある場合は上書き・削除せず検出する。初回導入時にバックアップを伴う移行が必要になる。

通常のファイル編集でリンクを張り直す必要はない。新規ファイル、削除、改名も同じ pack 内であれば直接見える。`/reload` で再読込される種類の datapack データが対象であり、クライアントのリソースパックや再起動が必要な Minecraft データまで `/reload` だけで反映されるとは扱わない。

既存の `TheSkyBlessing/.vscode/server-start.sh` は `server-env.sh` にある jar の場所を読み、既定 `-Xms2G -Xmx4G` で起動する。jar の版固定・取得、ワールドの選択・未指定時の初期化、リンク作成は実装されていない。リソースパックの URL と起動時の SHA-1 更新は前述の既存方式を引き継ぐ。EULA の状態はローカルで管理し、初回セットアップで利用者の同意を扱う。

## 既存の起動操作と Optional の範囲

開発者が共通のセットアップ・起動処理を利用するためだけに、追加の言語ランタイムやパッケージ管理ツールを導入する構成は避ける。現在の DevContainer に Node.js があることを、全開発者の前提にはしない。OS 標準の道具を優先し、Git と Minecraft サーバー用 Java は用途上必要な前提として別に扱う。

初期取得・サーバー起動は共通の `sh` スクリプトで実装する方針とする。ユーザー指定により Windows は既存の Git Bash を前提にできる。macOS / Linux / DevContainer は `/bin/sh` を使い、共通部分は POSIX sh の範囲に揃える。Windows 用の別の PowerShell 起動スクリプトは設けない。Node.js、Python、jq、PowerShell 7 や GNU 固有のコマンドを共通の必須依存にしない。

共通スクリプトをリポジトリに同梱し、設定項目・取得情報・検出規則・振る舞いを共有する。Windows の junction 作成やネイティブコマンドへ渡すパスの変換など、必要な OS 差だけを内部の処理へまとめる。VS Code の task も同じスクリプトを呼び、Windows では Git Bash の `sh` を利用する。ローカル設定をコードとして実行する方式は避ける。HTTP 取得、ハッシュ照合、リンク先確認、pack メタデータの検査などは OS 標準または Git Bash に同梱された機能で実現できる範囲を実装時に確認する。追加の外部コマンドを黙って増やさない。シェルスクリプトは LF で共有し、空白・日本語を含むパスと Windows のパス変換も検証する。

共通処理の複雑さから Java を使う場合も、サーバー用の既存 Java ランタイムで動く配布済み jar 等を候補とし、利用者にビルドを要求しない。Java ソース直接実行を安易に標準案にするとコンパイラを含む JDK が必要になるため、サーバーが動く Java だけで十分とは扱わない。共通 sh 実装を採用済みのため、この候補段落は過去の検討記録である。

VS Code では既存の「Open SkyBlock Server」に相当する起動 task から共通処理を呼び、端末からも同じ処理を実行できるようにする。必要な検出・リンク準備は起動に含め、日常操作として新しいコマンド体系を覚える必要をなくす。版やパスの問題は起動時に説明し、詳細診断は補助機能として扱う。独立した setup や並列作業用の操作は、手順を実際に減らせる範囲で追加する。

コード開発の取得・更新に必要なのは Git、サーバーを動かす場合は対応する Java。環境の補助処理専用のランタイムは必須にしない。エディタ、Agent、Docker は利用者の選択とする。DevContainer を選ぶ場合は必要な道具をイメージ側に用意する。ネイティブ利用でも、コンテナ内だけにあるコマンドへ依存しない。

Windows の Git Bash と macOS には、任意の導入入口として `scripts/setup-native.sh` を用意する。Git と VS Code 本体は導入済みを前提にし、ツール導入には winget / Homebrew を使う。通常の `setup.sh` と `server.sh` にはパッケージ管理の依存や対話を加えない。対話セットアップは選ばれたツールだけを導入し、リポジトリ取得・ワールド設定は既存の `setup.sh` に委ねる。

ツールの準備完了はパッケージ管理コマンドの成功だけで判断せず、実行できることと必要な版を確認する。Windows では導入後の PATH を現在の処理にも追加するが、古い実行ファイルが優先される場合や、別プロセスの PATH 更新には利用者の対応が必要。シェル設定と既存の `JAVA_BIN` は書き換えず、更新や設定修正を案内する。DHP の指定版への変更も対話で選ぶ。実際のインストーラーと各 OS での動作は、コマンドを模擬した検証とは区別する。

Asset の補助処理には `scripts/extract.sh` の SQLite → CSV、Scala スクリプトの加工、`scripts/update_register.sh` の登録関数更新がある。Scala 3.6.3 等は `scripts/project.scala` に定義される。通常の mcfunction 編集にこれらを実行する必須工程は確認できなかった。SQLite / Scala CLI / bash はその生成処理を使う場合の追加ツールとする。これら既存補助スクリプト自体の Windows / macOS 互換性は未検証なので、全補助処理のネイティブ対応が完了したとは扱わない。

## DevContainer と性能

基本は Agent と必要時の Java サーバーを同一 DevContainer 内で動かす。ネイティブ利用時は同じ CLI をホストで実行する。これにより、標準構成でコンテナ内から別コンテナを起動する必要はない。

DevContainer は Java 17 を追加し、Docker-in-Docker を外す設定変更を実施済みである。DevContainer は rebuild 済みで、Java 17 と実サーバーの起動・reload を確認した。

隔離を選んだ利用者の Agent には、必要な作業コピーと認証用領域だけを渡す。ホストの Docker ソケットを標準で渡さず、不要な privileged 実行もしない。[Docker のセキュリティ文書](https://docs.docker.com/engine/security/) が示す通り、daemon の操作権限はホストへのアクセスにつながり得る。書込可能な作業コピーの変更やネットワーク通信は可能であり、DevContainer を完全な隔離と表現しない。

現在の `/workspaces/DevSpace` は WSL の ext4 上にある。これは [Docker の WSL 推奨配置](https://docs.docker.com/desktop/features/wsl/best-practices/) と一致する。この保存場所を維持し、環境構築による不要なファイルシステム境界の往復や重複索引を避ける。

macOS 等の Docker Desktop 利用では、多数の小ファイルのホスト共有が遅い場合に、ソースと runtime を Linux volume 内へまとめ、コンテナで編集する方式を用意する。手動同期は導入しない。ネイティブ利用者はローカルファイルシステム上で直接動かす。

検索、VS Code の監視、language server の索引は別々に設定する。`.runtime/`、ログ、キャッシュ、他 feature の作業コピー、AnimatedJava の大量生成物を通常探索から外す。Asset 本体は多数の手書き実装なので全体除外せず、対象 ID / 機能へ探索を絞る。生成物の除外で補完が壊れないよう、公開宣言や必要な呼出窓口は残す。

全datapackを一つのVS Codeワークスペースで同時解析する構成は標準にしない。AIの入口はDevSpaceに統一し、そのウィンドウではDHPの自動索引対象を除外する。補完・診断は対象repoだけを別ウィンドウで開いて行う。Explorerの非表示設定や親の `.gitignore` だけでDHPの解析対象も除外できるとは扱わない。

## AIの入口とコード補完のワークスペース

コンテナから見えるファイル、VS Code で開くワークスペース、Minecraft が読む pack は別々に選べる。コンテナには全リポジトリをマウントしつつ、VS Code は `Asset/` だけを開き、サーバーは全 pack を読む構成が可能。`workspaceMount` と `workspaceFolder` は別設定である。[VS Code のマウント設定](https://code.visualstudio.com/remote/advancedcontainers/change-default-source-mount)

共通コンテナのAを採用し、通常のAI開発の開始位置はDevSpaceに統一する。コード補完用のrepo別ウィンドウと、並列担当のworktreeは用途を分ける。以下のB / Cは比較候補であり標準構成には追加しない。DevContainerの利用は任意で、ネイティブ利用でもAIはDevSpaceから開始する。過去のrebuild検証と今回の初期フォルダー変更の確認範囲は [検証記録](rebuild-verification.md) で区別する。

| 案 | 構成 | 日常操作と利点 | 主な負担 |
| --- | --- | --- | --- |
| A: 共通コンテナでDevSpaceを入口にする（採用） | DevSpace全体をマウントし、初期フォルダーもDevSpace。コード補完用に対象repoを別ウィンドウで開く | AIの依頼・統合・検証の入口を固定し、必要なrepoの規約とAPIへ進める | AIの開始位置とコード操作先を区別し、DevSpaceでDHPが全packを索引化しない設定が必要 |
| B: repo ごとのコンテナ | 各 repo の VS Code ウィンドウがそれぞれのコンテナへ接続。共通イメージを使う | 独立 clone なので、その repo だけのマウントで Git が動く。repo ごとの環境・プロセス分離ができる | 各 repo の DevContainer 入口、複数コンテナの管理、サーバーの集約が必要 |
| C: VS Code はネイティブ、Agent はコンテナ | ホストで対象 repo を開き、Agent は同じソースをマウントしたコンテナで実行 | 既存の DHP とエディタ操作を維持しやすい | コンテナ内 Agent とホストのエディタを接続する手順が必要。拡張機能との一体的な操作は方式ごとに確認 |

### A: DevSpaceからのAI開発とrepo単位のコード補完

コンテナ内には `/workspaces/DevSpace` 一式を置き、初期 `workspaceFolder` も `/workspaces/DevSpace` にする。通常のAIセッションはここから開始する。既存のDevSpaceのtaskと `scripts/server.sh`・`scripts/verify.sh` を使い、検索・編集・Git操作は対象repoで行う。DevSpaceの指示で子repoのナレッジREADMEと対象領域の本文を読む。開始位置だけで子repoの全文が自動読込される前提にはしない。

初回は空のウィンドウから `Dev Containers: Open Folder in Container...` でDevSpaceを開く。既存コンテナでAsset等を開いている場合は `code -n /workspaces/DevSpace` で入口を開ける。新しいAIセッションをDevSpaceで始め、既存セッション内のシェルのcdだけで規約の読込を切り替えたと扱わない。

コード補完・診断が必要ならコンテナ内の `code -n /workspaces/DevSpace/Asset` 等で対象repoだけを別ウィンドウに開く。通常のAIセッションはDevSpace側で続ける。複数repoを一つのmulti-rootへ追加する必要はない。並列作業の個別担当は割り当てたworktreeから開始し、依存repoの参照先と規約も渡す。現在のコンテナ内フォルダを `code` から開く操作は [Dev Containers の標準機能](https://code.visualstudio.com/docs/devcontainers/containers#_opening-a-terminal) である。

既存コンテナへ新しいウィンドウを接続する手段には `Dev Containers: Attach to Running Container...` がある。ただし attach 用の設定はローカルに保存され、通常の `devcontainer.json` と同じ全設定・初期化処理を使うものではない。チーム向けの構築・ツール導入は共有の DevContainer 定義へ残す。[Attach の公式仕様](https://code.visualstudio.com/docs/devcontainers/attach-container)

複数ウィンドウで共用するため、一つのウィンドウを閉じた際に他の作業やサーバーも停止しないよう、`shutdownAction: "none"` を設定する方針とする。不要になったコンテナの停止は明示的に行う。再接続・コンテナ再構築後に同じフォルダを開けることも確認する。[コンテナの管理](https://code.visualstudio.com/docs/devcontainers/containers#_managing-containers)

repo ごとに「Reopen in Container」から直接入ることまで求める場合は、共通 Compose サービスを参照する軽量な DevContainer 定義を複数用意する拡張案がある。共通 Compose ファイル・同じプロジェクト名・同じ service を使い、開くフォルダだけを変える。ただし、複数の設定が意図せず別コンテナを作らないこと、再構築時の共有設定が一致することの検証が必要になる。最初からこの管理を追加せず、標準のフォルダオープンで十分かを判断する。

### B: repo ごとのコンテナで注意すること

現在の submodule は `.git` ファイルから親の `.git/modules/` を参照しているが、提案する通常の独立 clone では Git 管理領域も各 repo 内に収まる。これにより、その repo だけをマウントして Git を使えるようになり、B の負担が減る。これは独立 clone への移行後の利点であり、現状態の `.gitignore` を変えるだけでは得られない。

DevSpace 外での単独 clone にも対応した DevContainer を提供する場合は、親 DevSpace の Dockerfile や Compose への固定相対パスだけに依存できない。独立 clone にしても親の DevContainer 設定が自動的に継承されるわけではない。共通イメージを使用する等の形で共有し、各 repo 自身にも入口となる設定を置く。共通イメージの配布・更新はこの案を選ぶ場合の追加管理になる。

コンテナを複数作っても、同じ作業コピーを共有すればブランチと編集内容は共有される。feature の並列開発には、別途作業コピーの分離が必要。コンテナごとのアクセス分離を求める場合は、全ソースを全コンテナに書込可能でマウントする構成とは区別する。

### DHP・サーバー・知識への接続

Asset と TheSkyBlessing は各 repo の `.vscode/settings.json` に `datapack.env.detectionDepth: 1` 等を持つ。repo ルートをそのままワークスペースにすると、これら既存設定を利用できる。Asset では `Asset/data/minecraft/functions/declares.d.mcfunction` が本体の API 等を外部宣言しており、本体の実装全体をワークスペースへ追加せずに補完・検査を補える。API を変更した場合は宣言の更新が必要で、宣言が実装の理解や検証を代替するものではない。

使用する言語サーバーはDHP 3.4.19を前提とする。DevSpaceの `.vscode/settings.json` は `datapack.env.exclude` を設定して全packを自動索引から外す。これはDevSpaceのウィンドウの設定であり、単独で開いた子repoの設定を変更しない。サーバーのpack自動検出はエディタの範囲に連動せず、ローカル設定で選んだrepoを参照する。DevSpaceと両子repoの「Open SkyBlock Server」taskは同じ共通起動処理を使う。

共通規約はDevSpaceの `AGENTS.md`、コード固有の知識は各repoの `docs/knowledge/` を参照する。ワークスペースを絞ることはファイルアクセスの隔離ではなく、Agent はマウントされた他 repo を必要に応じて参照できる。DHP にはそれらを一括でワークスペース登録する必要がない。

検証は DHP の対象が開いた repo に限定されること、外部宣言が利用できること、Git が動くこと、Agent の知識が読み込まれること、サーバーが全 pack を参照できることに絞る。AJ の性能比較は行わない。

## 並列 feature

### 作業コピーの配置（P1 採用）

A の共通コンテナを通常構成とし、並列 feature を使う場合はユーザー選択により P1 を採用する。worktree は `DevSpace/.worktrees/<feature>/<repo>/` に置く案とし、親の Git 管理外にして通常ワークスペースの索引へ追加しない。以下の P2 / P3 は比較の記録として残し、専用の構築処理は今回追加しない。

| 案 | 作業コピーと Agent の使い方 | 利点と負担 |
| --- | --- | --- |
| P1: 共通コンテナ内で repo ごとの worktree（採用） | 例: `DevSpace/.worktrees/feature-a/Asset/`。通常の `git worktree add` で用意し、そのフォルダを別ウィンドウで開いて Agent を使う | 履歴を共有し、作業ツリーを分離できる。ブランチ名や一部 Git 設定は共有する。元 repo と worktree が既存マウント内に収まる |
| P2: 共通コンテナ内で repo ごとの別 clone | 例: `DevSpace/.features/feature-a/Asset/`。通常の clone を別ウィンドウで開いて Agent を使う | Git 管理領域も分離でき、worktree の外部参照がない。履歴の保存容量と clone ごとの更新管理が増える |
| P3: feature ごとに DevSpace とコンテナを分ける | 別配置した DevSpace に必要 repo を取得し、それぞれ A の構成で開く | プロセス・環境も分けたい場合に向く。環境構築・更新とメモリ等の負担が増えるため、通常の並列コーディングには必須にしない |

P1 は同じ実行環境内で作成・利用する運用を基本にする。DevContainer 利用者はコンテナ内、ネイティブ利用者はホスト側で worktree を作成・利用する。worktree の Git 管理情報はパスを参照するため、ホストとコンテナで同じ配置を異なる絶対パスから使う場合やコンテナ再作成時には、参照が成立することを確認し、必要な修復を行う。[Git の worktree 仕様](https://git-scm.com/docs/git-worktree)

デバッグ先の切り替えは、選んだ方式の作業コピーをサーバーの参照元に指定する案とする。ローカル設定で repo ごとの参照パスを指定でき、未指定の repo は通常配置を使う。例えば Asset だけ feature のコピー、本体と AJ は通常配置という組み合わせにできる。起動時に解決した参照元を表示し、その repo ごとに pack を自動検出してリンクする。マウント済みの作業コピー間なら、コンテナの再構築や Git の checkout は不要で、サーバーを停止・参照元を変更・再起動する。以後の通常編集は `/reload` で反映する。共有コンテナ内で Agent 同士のファイルアクセスまで分離する構成ではない。

単一 repo の feature 開発なら、その repo の通常の `git worktree` で作業コピーを分ける。コーディングだけの Agent 環境にサーバーや3リポジトリ一式のコピーを必須にしない。DevSpaceの共通規約と対象作業コピーの固有知識を参照できるようにし、他repoのコード参照が必要な場合には参照先も渡す。

共通知識の蓄積のためにDevSpace全体をfeatureごとに分離しない。共有DevSpaceの編集・Git操作は一人の統合担当へ集約する。子repoの未マージ変更に依存しない知見は、子repoの統合を待たずDevSpaceの `main` へ逐次反映・公開する。コード固有の知識は子repoのworktreeで管理する。DevSpaceのスクリプト・環境構成を並列実装する場合だけ、その実装用worktreeも分ける。

複数 repo にまたがる feature では、変更する repo ごとに作業コピーを用意する。環境一式を分離したい場合は DevSpace を別配置し、初期セットアップで各 repo を取得する方式も選べる。親への `git worktree` だけでは Git 管理外の clone は複製されず、各 repo のブランチも連動しない。

各 repo の worktree をコンテナへ渡す場合は、worktree 外にある共通 Git 管理領域も参照可能にする必要がある。単独ディレクトリのマウントで完結させたい場合は独立 clone のほうが単純。submodule 固有の制約は減るが、同じ作業コピーを複数 Agent で共有するだけでは編集を分離できない。[Git の worktree 仕様](https://git-scm.com/docs/git-worktree)

通常開発のサーバーは共通の1組を使い、起動時に選択した作業コピーからpack一式を自動検出してリンクする。自動検証は共通runnerが専用worldで1件ずつ実行する。参照repoの切替と検証順序はDevSpace側が調整し、検証中の参照コードは編集しない。P1の元repoとworktreeは同じDevSpaceマウント内に置くため、デバッグ先を切り替えるたびにマウントを組み直す必要はない。独自のブランチ操作を必須にしない。

通常編集の `/reload` と、feature の切り替えは区別する。feature 切り替え時は旧コードの schedule や storage が残ることがあるため停止を基本にする。停止・再起動でも永続データは戻らない。テスト用ワールドの復元は必要に応じて明示的に行い、切り替えだけで自動消去しない。

## Agent の知識の蓄積

実装時点の runtime は `.runtime/world` を既定保存先とし、managed `.runtime/active-world` 経由で `level-name=active-world` を使う。外部 world と既定 world の切替は world をコピーせず指定先へ接続する。managed pack の所有情報は `.devspace-managed-packs.tsv`、ロックは `.runtime/server.lock` と `world/.devspace-server.lock` に記録する。stale lock の削除はサーバー停止を確認した後だけ手動で行う復旧手順とする。

開発時に常に知識を読むことを要件とする。必須知識を Agent の標準指示ファイルから毎セッション読み込ませ、対象に応じた詳細知識を編集前に読む手順もそこに定義する。利用者が毎回「ナレッジを読んで」と指示したり、専用の Agent 起動コマンドを使ったりする必要はない。

当初は別工程としていた初期ナレッジを、2026-09-14 のユーザー指示により TheSkyBlessing と Asset を対象に作成した。PR の inline レビュー、対象差分、PR 状態、現行コードを照合し、規約と未採用・未確定の提案を区別して各 repo の `docs/knowledge/` に記録した。取得範囲・出典と検証は [知識の検証記録](knowledge-verification.md)、継続的な更新方法は [ナレッジの配置と更新](knowledge-maintenance.md) を参照する。Asset-AnimatedJava 自体の体系的整理は今回の指定対象外。

### 自動読み込みの入口

Codex は開始時にプロジェクトルートから作業ディレクトリまでの `AGENTS.md` 等を集める。子ディレクトリの全指示ファイルを起動時に一括収集する仕組みではなく、通常は Git ルートが探索の境界になる。[OpenAI の AGENTS.md 仕様](https://learn.chatgpt.com/docs/agent-configuration/agents-md)

Claude Code では `CLAUDE.md` が読み込まれるため、各リポジトリの `CLAUDE.md` に `@AGENTS.md` を記述して同じ本文を読み込ませる。これは Claude Code の import 機能を使い、Windows のファイル symlink を要求しない。[Claude Code のメモリ・import 仕様](https://code.claude.com/docs/en/memory)

共通規約とAIへの参照・更新指示はDevSpaceに集約する。子repoのAGENTS.mdは、ここをpwdにした通常のAI開発を推奨せずDevSpaceへ案内するためだけに置く。コード固有の知識は、コードと同じブランチで管理するため子repoに残す。

対話BashのCLI起動は [ai-shell.bash](../scripts/ai-shell.bash) で包み、通常の2 repoからDevSpaceへ移動して開始する。Gitルートを照合して入れ子の別repoを除き、`.git` がファイルのlinked worktreeも除くことで、並列担当の作業場所を保持する。移動はサブシェル内に限定し、終了後も利用者が元のrepoで作業を続けられるようにする。対象範囲・相対パス引数・通常の起動方法は [READMEの起動手順](../README.md#起動) を参照。

```text
DevSpace/
  AGENTS.md                    # 共通規約・対象repoのナレッジを読む指示
  CLAUDE.md                    # @AGENTS.md
  docs/knowledge-maintenance.md # 知識の採用・配置・更新方針
  TheSkyBlessing/
    AGENTS.md                  # DevSpaceからの開始を案内
    CLAUDE.md                  # @AGENTS.md
    docs/knowledge/...         # 本体コード固有の構造・契約
  Asset/
    AGENTS.md                  # DevSpaceからの開始を案内
    CLAUDE.md                  # @AGENTS.md
    docs/knowledge/...         # Assetコード固有の構造・契約
```

DevSpaceから対象repoのナレッジREADMEへ直接進み、関連領域を読む。並列担当にはDevSpaceのAGENTS.mdの所在と依存repoの参照先を渡し、担当worktreeのナレッジを使わせる。共通規約をworktreeや子repoのAGENTS.mdへ複製せず、子repo単体で規約を完結させることは保証しない。

親の `.gitignore` により、DevSpace からの通常検索では各 repo が対象外になり得る。ルートの入口に repo の配置を明記し、コード検索・差分確認は対象 repo を作業ディレクトリにして行うよう定める。親の検索や `git status` の結果だけでコードや変更がないと判断しない。

共通規約とコード固有の知識はそれぞれのrepoでGit管理し、並列担当にはDevSpaceの規約と対象ブランチのナレッジを渡す。未コミット文書はworktreeへ自動で引き継がれないため、必要な本文が利用できることを確認する。Asset-AnimatedJava自体の体系的な知識整理は今回の対象外。

### 毎回読む内容と、変更対象に応じて読む内容

常に必要な共通規約は短く保ってDevSpaceの `AGENTS.md` の本文に置く。リンク集だけにせず、生成物の扱い、API・一時状態に関する基本ルール、登録漏れの防止、既存の検証方法などを直接含める。Codex 側で Markdown リンク先まで自動展開されるとは仮定しない。

詳細文書には「神器を追加する」「Mob の挙動を変更する」「公開 API を変更する」などの手順、理由、実例へのリンクを置く。DevSpaceの指示と各repoのナレッジREADMEで、変更対象のパス・作業内容ごとに必読文書を明示する。たとえば神器の変更では神器の登録・イベント手順と使用する API の契約、Mob と AJ の連携変更では Mob のライフサイクルとアニメーション連携の規約を読む。

入口に定める作業手順は次の通り。

1. DevSpaceの共通規約から対象repoを選び、その作業コピーのナレッジREADMEを確認する。
2. 編集前に、対応表で指定された文書と関係する API の契約を読む。未読の場合は、先にその確認を行う。
3. 対象領域が広がったとき、ブランチが変わったとき、長い中断・コンテキスト圧縮後の再開で情報が不足するときは、対象の知識を再確認する。
4. 完了前に、読んだ規約と実際の変更を照合し、今回得た再利用可能な知識を更新する。

規約の適用範囲を明示することで、蓄積した詳細文書が増えても、毎回すべての生成コードや無関係な文書を読む必要をなくす。初回読み込みのサイズ制限や優先される override の影響も確認し、重要規約が読み落とされるほど入口を肥大化させない。

### 蓄積と確認

レビューで判明した知見は理由・実例・適用範囲を確認し、コード固有の契約は対象repoでコードと一緒に記録する。共通知識は統合担当へ引き渡し、[共通知識の逐次反映](knowledge-maintenance.md#共通知識の逐次反映) に従ってDevSpaceの既存文書へ統合する。仮説は確定規約と区別し、廃止された知識も変更時に整理する。

標準指示ファイルの読み込みは、知識をコンテキストへ渡す仕組みであり、LLM がすべての指示を必ず守ることを強制するものではない。機械判定できる規約は既存 DHP / linter 等でも検査する。読込の検証は通常のDevSpace開始と、共通規約を引き渡したworktree担当を対象とする。子repoから直接開始した場合はDevSpaceへの案内が伝わることを確認する。文書の存在だけで仕組みが完成したとはしない。

今回の代表例から、最初に文書化する価値がある内容は以下。

1. `api:` storage の `Argument` / `Return`、scoreboard の一時状態、呼出前提と後始末。例: 本体 `data/api/functions/artifact/give/from_rarity.mcfunction` と `data/api/functions/damage/core/attack.mcfunction`。
2. `core:tick/` が統括する処理順と context の寿命。通常の追加処理は対応する機能やイベントへ接続する。
3. `Asset/Asset/data/asset/functions/artifact/1043.gamma_ray/trigger/` のような段階化と共通 API 利用。似た形の別種要素を無条件にテンプレートとしてコピーしない。
4. 新規要素の `register` と、必要な `load` / `tick` / `use` / `enroll_pool` 等のタグへの接続。関数作成だけでは登録にならない。
5. IMPDoc の `#>`、`# @within`、`#declare` と `*.d.mcfunction`。宣言・補完用情報は実行時登録の代替ではない。既存 CI の宣言生成を毎回の起動に混ぜない。
6. Asset の Mob 側が AnimatedJava の `aj.<animation>.frame` を見てイベントを発火する接続。生成コードの再出力時には呼出契約も確認する。

## 実装時の検証と未確定事項

以下は設計時の受入条件。実装後および rebuild 後の検証を実施済みで、最新結果は [rebuild 後の検証記録](rebuild-verification.md) に記載する。Windows junction・macOS の実機検証は未実施。

独立 clone の初期セットアップでは、未取得 repo のみを作成し、再実行で既存 repo のブランチ・remote・変更を保持することを確認する。移行後は親の gitlink がなく、各 repo の Git 管理領域がその repo 内で完結し、repo 単独のマウントでも Git 操作ができることを確認する。

実装の受入条件は、初回起動で必要 pack が有効になり、mcfunction / function tag の編集・追加・削除が手動同期なしの `/reload` で反映されること。既存ワールドの datapack を破壊しないこと、版不一致を説明できること、feature 切り替えで選択した repo ごとの参照元に正しく切り替わり、旧リンクが残らないことも確認する。

ワールドについては、開発者ごとの指定が共有設定へ混入しないこと、指定先を使用すること、未指定なら新規作成すること、次回起動では再利用することを確認する。ネイティブ環境と DevContainer の双方で、外部ワールドへの接続と pack の読込を検証する。新規ワールドでの本体 load / 初期化も検証対象とし、配布ワールド固有の地形・建築・保存データを必要とする機能の検証には、それらを備えた指定ワールドを使う。

AnimatedJava を通常の Git 操作で master → dist → master と切り替え、各回の起動だけで必要 pack が自動検出され、欠落や二重読込がなく、通常編集の `/reload` が維持されることを確認する。未知の名前の pack を追加しても設定変更なしで次回起動時にリンクされること、pack を削除・改名すると古い管理リンクが残らないこと、overlay が独立 pack と誤認されないことも検証する。起動処理が Git のブランチ・index・編集内容を変更しないことを確認する。

AJ の master / dist 比較やモデル数別のベンチマークは実施しない。開発環境が追加する負荷については、自動検出で生成ファイルを全走査しないこと、runtime や別作業コピーを重複索引しないことを確認し、問題が生じた場合に該当箇所を調査する。

サーバー条件は Minecraft 1.20.4 / Java 17 以上 / Vanilla、リソースパックは既存起動スクリプト準拠で確定した。ワールドの選択方式も「開発者ごとの任意指定、未指定なら新規自動作成」で確定している。外部ワールドのコンテナへの接続は W1、並列 feature の作業コピー配置は P1 を採用する。独立 clone 移行と起動処理は実装済みで、setup/runtime の offline 検証も完了した。DevContainer rebuild、ユーザーの EULA 同意設定、実 Minecraft 起動とコンソールの `reload` 検証は完了。Windows/macOS 実機、外部ワールドの W1 マウント変更、ゲームクライアントを使う確認等は未検証。AJ master の本体側 pack 個数判定にも制約がある。詳細は [rebuild 後の検証記録](rebuild-verification.md) を参照。本体・Asset の初期ナレッジは作成済み。知識の検証状況は [知識の検証記録](knowledge-verification.md) を参照。AJ 自体の知識整理と制作環境は今回の対象外。
