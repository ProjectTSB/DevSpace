# 初期ナレッジの調査・検証記録

実施日: 2026-09-14。対象は TheSkyBlessing と Asset、および DevSpace から両 repo へ案内する入口。

2026-09-15 更新: ユーザー指示により datapack-linter ワークフローのローカル実行・再現を求める記述を削除した。以下のセッション検証とサイズ・ハッシュ確認は更新前の文書に対する記録。

同日、Asset の [型・インスタンス・継承モデル](../Asset/docs/knowledge/object-model.md) と本体の [Asset の実行モデル](../TheSkyBlessing/docs/knowledge/asset-runtime.md) を追加し、両 repo の AGENTS.md・案内・関連文書を更新した。追加のコード読解・照合には `gpt-5.6-sol` / low を使用した。基底型と派生型の実例、Field の保存、親探索の順序、Effect との差異をコードと照合し、文書の参照先と空白エラーを確認した。新しい文面に対する新規 Agent セッションの読込検証やゲーム内動作検証は実施していない。

同日、[ProjectTSB Wiki](https://github.com/ProjectTSB/TheSkyBlessing/wiki) の公開16ページとサイドバーを取得し、`gpt-5.6-sol` / low で全本文を読解した。Wiki HEAD は `3a5ede8625a713382dca0e96f46b2a8ed75218c5`（最終コミット 2026-05-25）。既存の両コード HEAD と重要な契約を照合し、両 repo の `wiki-crosscheck.md`、領域別文書、AGENTS.md を更新した。同じ低コストモデルの別セッションで出典の帰属と主要契約を監査し、Wiki の訂正と実装からの補足を区別する表現へ修正した。AJ の JSON 運用はその後、ユーザーが示した `global/root/on_load.json` と関連する tag・Karmic の関数を `gpt-5.6-sol` / low で確認し、`required:false` が現行でも使われていると訂正した（AJ HEAD `e48a116501b931a6688d5bd77e8f60c82de27ffa`）。確認ログは `.runtime/knowledge-research/aj-confirmation/` に保存した。Wiki の全機能を実機検証したものではなく、外部リンク先と添付画像は対象外。取得ファイル一覧・ハッシュ、本文読取ログと対応確認、文書検査の記録は `.runtime/knowledge-research/wiki-review/` に保存した。

2026-09-15 再照合: AJ の指摘を受け、既存ナレッジの断定を `gpt-5.6-sol` / low で再監査した。継承・dispatch・Field 保存・Effect・Artifact・API の代表経路を追い、schedule probe の目的、永続状態の保存先、call.m の呼出前提、現行 Mob event tag、Wiki への帰属、解除経路の適用範囲を修正した。コードの静的確認であり、実機検証を追加したものではない。根拠は両 repo の sources.md、読取ログと監査結果は `.runtime/knowledge-research/knowledge-recheck/` に記録した。

## 小規模な並列実装・統合・実サーバー検証（2026-09-15）

コミット済みの Asset 作業ブランチを開始点に、2人の Agent が別 worktree で実装し、第三の worktree へ統合して実 Vanilla 1.20.4 サーバーで確認した。元の作業ブランチと master は変更していない。

| 役割 | 作業ブランチ | 作成した変更 |
| --- | --- | --- |
| 計算処理 | `verify/parallel-compute` | `devspace_parallel_verify:compute`。storage の整数 Input を2倍にして Result に書く |
| 呼出・検査 | `verify/parallel-runner` | `devspace_parallel_verify:run`。3ケースを実行し Passed／Failed を記録する |
| 統合 | `verify/parallel-integration` | 両コミットをそれぞれ通常の merge で取り込む |

Asset の開始点は `959bd690ac39a110e3a3ed5c2c30d9e1aaab76ad`。計算処理のコミットは `c0abb5e8d565a5d3ec0c1955d6e70c4e255129e5`、呼出・検査は `71ec39e103c90b9c9b330141844913eb35c19df0`、統合結果は `ea795603e0dcddf688a61ea911812c990985bb34`。変更は `Asset/data/devspace_parallel_verify/functions/` 内の2ファイルに限定し、自動 load/tick 登録や既存ゲーム機能の変更は行っていない。本体は `5d6799ed16578e8c6a7c61593bcf3d0ef22c1ff1`、AJ は `e48a116501b931a6688d5bd77e8f60c82de27ffa` を参照した。

両実装と別担当の静的レビューは `gpt-5.6-sol` / low。入口・ナレッジはコミットから worktree に入り、手動コピーは不要だった。分担時は通常の委譲規約に従って対象 repo と必読文書を伝えているため、この検証を「文書指定なしの自律参照」の追加証拠としては扱わない。その確認は後述の独立した6セッションで行っている。

入力と期待値は 21→42、0→0、-7→-14。統合した Asset の worktree を一時設定の ASSET_PATH に指定し、23 pack の検出と参照元を確認した。実サーバーで run を実行した結果は `{Passed: 3, Failed: 0}`、最後の入出力は `{Input: -7, Result: -14}`。reload 完了後に再実行しても同じ結果となり、前回の集計が混ざらないことを確認した。起動・reload では既存検証でも観測した minecraft:empty の再定義と Can't keep up 警告が出ている。性能評価を合格としたものではない。

既定ワールド利用のコンテナで、Java と runtime/world ロックがないことを確認して元の world ディレクトリをローカル領域へ退避し、同じ既定パスに一時 world を生成した。WORLD_PATH は空のままとし、一時 config を DEVSPACE_CONFIG で渡したので、W1 マウント変更やコンテナ再作成は不要だった。これは既定 world の分岐での確認であり、任意の外部 W1 world に同じ手順を適用する説明ではない。

stop 後、全 dimension の保存と終了コード0、Java の終了、両ロックの解除を確認した。一時 world を退避して元を戻し、元 world の120ファイルの SHA-256・サイズと23リンクの参照文字列が一致すること、個人 config が不変であること、runtime 直下の保存済み9ファイルを復元したことを確認した。子 repo の元ブランチ・HEAD・master と作業ツリーも変更なし。一時 worktree は通常の git worktree remove で除去し、検証コードを保持する上記3ブランチは一旦ローカルに残したが、検証後にユーザーの指示で削除した。検証コードの差分とログは下記のローカル領域に残している。push はしていない。

確認できたのは、同一 repo の別ファイルに対する小規模な並列実装、コミット、競合のない統合、参照先の選択、共有サーバーでの実行・reload、元環境への復元である。同一ファイルや共通 ID の競合解消、複数 repo を同時変更する機能、複雑な Mob/Object/Effect の実装品質、複数サーバーの同時実行まで検証済みとしない。

根拠はローカル領域 `.runtime/parallel-verification/` の `integration.json`、`integration.patch`、`server.log`、`world-before.json`、`result.json` と検証ブランチのコミット。実装・読解は分担した Agent の報告、実行結果は Minecraft コンソールのログ、復元はファイルと Git の照合で確認した。

## コミット先の訂正（2026-09-15）

ユーザーの指定により Asset／TheSkyBlessing の master への直接コミットを禁止した。上記2 repo の作業コミットはそれぞれ `chore/devspace-environment-and-knowledge` に保持し、現在の checkout も同ブランチへ切り替えた。ローカル master は Asset `8f661ea1003a0e519d9825c55e1dde0ce6edaf80`、TheSkyBlessing `f88cdd5bcb2216d24b26e48684f4a7951a686c94` へ戻した。コミット内容を失わず、push は行っていない。親と両子 repo の AGENTS.md にこの方針を記録した。以降の worktree は作業ブランチを開始点として指定する。以下の引継ぎ確認は記載したコミットに対して有効で、master へ変更を取り込んだという意味ではない。

## コミットと新規 worktree への引継ぎ確認（2026-09-15）

ユーザーのコミット指示を受け、本体・Asset の起動設定、AGENTS.md／CLAUDE.md、ナレッジを、それぞれの repo のローカルコミットへ保存した。

| repo | コミット | 新規 worktree で確認した共有ファイル |
| --- | --- | --- |
| TheSkyBlessing | `04c8987505ee1817b557c43c91641be7043ee319` | 15ファイル（入口、10知識文書、起動設定、改行設定） |
| Asset | `4ad0c2fc9fd1a1a058c37d96618b587aa90fad25` | 12ファイル（入口、7知識文書、起動設定、改行設定） |

各コミットから一時 detached worktree を作り、ファイルを手動コピーせずに入口・本文・起動設定が存在すること、内容が commit と一致すること、起動シェルが LF であること、worktree が clean であることを確認した。Git の改行変換による CRLF/LF 差は本文比較時に正規化した。確認後は通常の `git worktree remove` で除去した。これにより、従来の「未追跡のナレッジが新規 worktree に入らない」状態は、上記コミットを開始点にする作業コピーでは解消した。古いコミットや未更新の remote から作るコピーは別である。

コミット前に `sh tests/setup.sh` と `sh tests/runtime.sh` を再実行し、setup 成功、runtime 13項目成功を確認した。両 repo の文書リンクと差分の空白検査も成功した。設定・起動コードの限定的な静的レビューには `gpt-5.6-sol` / low を使い、重大な問題は報告されなかった。実サーバーの追加検証や、新しい worktree での Agent セッションの再実行はしていない。

DevSpace の環境実装・手順・検証記録は、この節を含む親 repo のコミットに保存する。個人設定、ワールド、キャッシュ、worktree、調査ログ、独立子 repo 本体は親の commit 対象外。push はしていない。レビューと worktree の確認結果はローカル領域 `.runtime/commit-verification/` に保存した。

## 読む指示を含めない依頼での自律参照確認

2026-09-15、ユーザーが毎回ナレッジを読むよう指示せずに使えることを確認するため、前の文書適用確認とは別に実施した。`gpt-5.6-sol` / low、`codex exec --ignore-user-config --ephemeral` の新規セッションを使い、会話履歴や既存レポートをプロンプトへ添付せず、開始位置だけを指定した。AGENTS.md は通常の起動時の指示として扱った。

各依頼には次の本文と「今回は調査のみで、ファイル変更・外部通信・サーバー起動は行わないでください。」だけを渡した。文書名、ナレッジ、読む指示、必読文書の列挙、検証であるという説明は含めていない。

| 開始位置 | 依頼本文 | 修正前／修正後に本文の読取を確認した文書 |
| --- | --- | --- |
| DevSpace | TheSkyBlessing の商人の品目や価格を変更したとき、既に配置してある商人にも反映させたいです。現在どう更新されるか、どの処理を変更する必要があるか調べてください。 | 本体 README、world-components.md（両方で参照） |
| TheSkyBlessing | 死亡時の墓を、同じプレイヤーについて2個まで残せるようにしたいです。必要な変更箇所と、既存の回収処理への影響を調べてください。 | README、runtime-components.md（両方で参照） |
| Asset | 親の動作を引き継いだ Object に、tick ごとにパーティクルを出す処理を追加したいです。既存の実例を使って、追加する場所と親の動作を保つための実装方法を説明してください。 | README、object-model.md、runtime-and-tools.md（両方で参照） |

修正前も3件すべてで自律的に参照できた。そのうえで、親と両子 repo の AGENTS.md の「変更時」中心の案内を、実装・レビュー・調査全体に適用する文面へ改めた。ユーザーの文書指定や参照許可を待たずに必要な本文を選び、依存領域が増えれば参照を追加することも明記した。調査中に repo 直下の `data/` を検索して失敗した例があったため、両 repo の実際の datapack root も入口で明示し、本体 load/tick の参照パスを訂正した。

修正後、同一の依頼文で3つの新規セッションを再実行し、すべて関連本文の読取と回答まで完了した。商人では定義 snapshot と Offers の更新、墓では所有者側保存内容の世代別管理、Object では子の tick と親呼出しの関係を現行コードと結び付けて説明した。これらは仮の変更相談であり、機能を実装した記録ではない。修正前後とも参照できているため、成功率向上やあらゆる依頼での遵守を実証したものではない。

確認は自己申告だけでなく、CLI の tool ログにある読取コマンドと返された文書本文で行った。各セッション群の実行前後で、対象 AGENTS.md とナレッジ等の SHA-256 に変化がないことも確認した。結果記録は全セッション終了後に追記した。検証ログは `.runtime/knowledge-research/autonomous-reference/` の `cases.json`、各 `*-prompt.txt`、`*-baseline-events.jsonl`／`*-revised-events.jsonl` とレポート、`evidence.json`、`baseline-integrity.json`／`revised-integrity.json`。ローカル文書のリンク・空白も確認した。

## 並列開発性の確認（2026-09-15）

README、設計の P1、既存の rebuild 検証記録、各 repo の `git status --short`／`git worktree list`／`git ls-tree HEAD` を照合した。本体・Asset とも、この時点の HEAD に AGENTS.md・CLAUDE.md・docs/knowledge は含まれず、通常 checkout の未追跡ファイルだった。親の環境実装にも未コミット変更があった。したがって、この確認時点の通常 checkout での自律参照成功を、未準備の新規 worktree や新規 clone の成功として扱わない。

起動経路と排他の静的読解には `gpt-5.6-sol` / low を使用した。子 repo の起動 shim は共通 DevSpace の server.sh へ接続し、参照 repo はローカル設定か既定配置から決まる。起動した worktree の自動選択はない。runtime/world ロックは二重使用を防ぐが、設定ファイル編集や `/reload` の担当を調整する機構ではない。根拠は `scripts/lib/runtime.sh` の設定解決・`runtime_acquire_locks`、`scripts/lib/common.sh`、`scripts/server.sh` と子 repo の `.vscode/server-start.sh`。読取ログは `.runtime/knowledge-research/parallel-readiness/`。

既存の確認範囲は worktree の Git 参照、文書を明示コピーした worktree の指示読込、共有サーバーでの起動・reload 等である。この静的確認時点では並列実装から統合・実機検証までの確認は未実施だった。その後の小規模な別ファイル実装の確認は本書の「小規模な並列実装・統合・実サーバー検証」に記載した。共通 ID や文書の競合解消は引き続き確認対象外である。別 feature の同時実機検証環境も現行 P1 の提供範囲に含まれない。今回の作業は評価と README・共有手順への反映であり、追加の worktree 作成、コード変更、commit/push、実機検証はしていない。

## 調査範囲

他コンポーネントの追補（2026-09-15）: 本体の Island、Teleporter、Trader、Container、Artifact 生成と inventory、墓と LostItems、Mob 初期化と ForwardTarget、幾何・散布・移動・ROM を `gpt-5.6-sol` / low で読解した。別セッションでも DPR の保存期間、Island の phase と callback、Teleporter の選択 snapshot、Trader の二つの version と uses、墓の回収、Mob の ID と適用集合を照合した。結果を本体の [world-components.md](../TheSkyBlessing/docs/knowledge/world-components.md) と [runtime-components.md](../TheSkyBlessing/docs/knowledge/runtime-components.md) に記録し、AGENTS.md、README、architecture.md、sources.md と親の案内を更新した。コード読解レポートの112箇所のパス・行参照と、両 repo の21文書の相対リンク251件・固定 commit のコードリンク18件、空白を検査し、参照先の欠落はなかった。コード本文との照合と、リンク先の存在確認は別の確認である。検証プロンプトで開始時の規約に基づく必読文書の列挙と「README と指定された関連ナレッジを実際に読んでください」を明示し、後半では world-components.md と runtime-components.md も名指しした。その条件で新しい本体 repo のセッションが新規文書を必読と回答し、本文を読んだ後、商人の価格更新、複数墓、全経路の重複抑制、開封時抽選という4つの仮の変更案の問題と変更境界を指摘できることを確認した。同セッションが UUID、墓の所有、motion、ROM、散布・幾何の説明を現行コードへ逆引きし、重大な誤りや追加の記録候補は報告されなかった。文書の適用確認であり、実際の変更実装の検証ではない。読解・照合ログは `.runtime/knowledge-research/components-reading/`。今回コード変更やゲーム内実行検証はしていない。

抽象構造の追補（2026-09-15）: 本体の定義・管理処理・呼出側を `gpt-5.6-sol` / low で読解し、別セッションで主要契約と player_manager の緩衝体力を照合した。装備 modifier の ID はさらに対象関数と直近呼出元で確認した。結果を `TheSkyBlessing/docs/knowledge/architecture.md` と関連文書へ反映し、AGENTS.md から機能追加・領域間変更の必読にした。検証プロンプトで README.md、architecture.md、api-and-storage.md を読むよう明示した新規セッションが、装備 Value の直接増減、防壁の同 UUID 追加と期限、Damage reaction の直接呼出しという3つの仮の変更について、既存の抽象と呼出契約に沿ってレビューできることを確認した。これは文書からの判断の確認であり、実際の変更実装・ゲーム内検証ではない。読取・照合・文書適用のログは `.runtime/knowledge-research/architecture-reading/`。

運用ルールの追補（2026-09-15）: 両 repo と DevSpace の AGENTS.md に、実装・レビューのみ・不具合調査・ユーザー訂正を契機とする記録、作業完了前の確認、更新先または不要理由の報告を明記した。両子 repo を開始位置とする新しい `gpt-5.6-sol` / low セッションで、開始時の指示だけから4ケース（レビューでの発見、ユーザー訂正、明示的な編集禁止、新規知見なし）への対応を回答させ、期待する記録先・期限・例外・報告を確認した。ツール利用とファイル編集はなかった。これはルール読込と解釈の確認であり、将来の記録漏れを機械的に防止する検証ではない。ログは `.runtime/knowledge-research/recording-policy/`。

| 対象 | ローカル HEAD | inline review comment の取得範囲 |
| --- | --- | --- |
| TheSkyBlessing | `f88cdd5bcb2216d24b26e48684f4a7951a686c94` | 更新日時降順300件、104 PR。コメント更新日時 2024-10-18〜2026-07-17 |
| Asset | `8f661ea1003a0e519d9825c55e1dde0ce6edaf80` | 更新日時降順300件、30 PR。コメント更新日時 2026-06-01〜2026-09-09 |

一覧から代表 PR を選び、必要な過去 PR も追加して、inline コメント本文・対象差分・PR 状態・現行コードとの対応を確認した。全履歴の全コメントを精読したという意味ではない。個別の採否と出典は [TheSkyBlessing](../TheSkyBlessing/docs/knowledge/sources.md)、[Asset](../Asset/docs/knowledge/sources.md) の記録を参照する。issue は躓きの文脈として扱い、報告だけで確定規約にしていない。

コード・PR の読み取りと初稿は `gpt-5.6-luna` / low、追加の独立監査・最終修正は `gpt-5.6-sol` / low を使用した。高コストモデルへのエスカレーションは行っていない。読込確認は `gpt-5.6-luna` / low と `gpt-5.6-sol` / low を使用した。

## 確認方法

2026-09-15、ユーザーの指摘を受けて上記2回の検証条件を明記した。両回ともプロンプトに読むよう指示があり、文書を読ませた後の判断を確認したものである。AGENTS.md が開始時に渡されること、そこから通常の作業依頼だけで詳細ナレッジを自発的に読むこと、読んだ内容を実装・レビューへ適用できることは別の確認として扱う。この2回では、読むよう促さない条件で詳細文書へ到達することは検証していない。

文書の相対リンクが存在すること、レビューコメント ID が取得した実コメントに対応すること、各 repo の文書が Git の ignore 対象外であることを確認する。API の storage ID と NBT path、結果の保持責務、実行 context、生成物と手書きマクロの区別はコードと照合する。

新規セッションは `codex exec --ignore-user-config --ephemeral` に対象モデル・low 推論・`-C <対象repo>` を指定して起動する。repo 側の指示の読み込みと、必読文書の参照を確認し、コード・文書の編集はさせない。個人の config による上書きを避けた CLI での検証であり、すべての利用者の個人設定やアプリセッションを検証するものではない。

初回は `-s read-only` で起動したが、このコンテナでは bwrap の非特権 namespace 作成が拒否され、詳細文書の読込に失敗した。再検証ではこの作業環境と同等の権限（`--dangerously-bypass-approvals-and-sandbox`）を使い、閲覧だけを指示した。ホストやコンテナの設定は変更していない。

最初はツールを使わず、開始時から見えている規約と必読文書を答えさせる。次にその案内に沿って詳細文書を実際に読ませ、仮の開発作業で注意する点をまとめさせる。単にファイルの存在を調べる方法とは分けて記録する。

## 結果

| 新規セッションの開始位置 | 結果 |
| --- | --- |
| DevSpace | ツール使用前に両 repo の入口、子 repo 単位での Git 差分確認、W1 の指定操作を回答。 |
| TheSkyBlessing | ツール使用前に API 契約・実行主体・戻り値保持の規約を回答し、その後 README と api-and-storage.md を実際に読んだ。 |
| TheSkyBlessing の一時 worktree | 独立 repo と同じ入口・詳細文書の読み込みを確認。 |
| Asset | ツール使用前に Mob/context/生成物の規約を回答し、その後 README・sources.md・mob.md を実際に読んだ。 |
| Asset の一時 worktree | 独立 repo と同じ入口・詳細文書の読み込みを確認。 |

worktree は各 repo から detached で作成し、まだ未コミットの入口とナレッジを検証用にコピーした。これは配置・相対参照・指示探索の確認であり、未コミット文書が Git により自動伝播したという意味ではない。検証後に一時 worktree を除去した。

両 repo それぞれ7文書を検査し、相対リンク切れ・引用した review comment ID の不一致なし。AGENTS.md は本体2,371 bytes、Asset3,083 bytes。CLAUDE.md の参照と Git ignore 対象外であることを確認した。各 repo の git diff --check は成功し、検証セッション前後で入口・ナレッジの SHA-256 が変わっていないことも確認した。

詳細な CLI イベント、最終回答、取得した GitHub API 結果は Git 管理外の `.runtime/knowledge-research/` に保存している。共有用の規約と根拠は各 repo の永続文書に記載している。

`CLAUDE.md` は各入口の `@AGENTS.md` 参照を確認した。Claude Code の新規実行セッションによる読込検証は今回実施していない。この初期検証時点では知識文書と入口は未コミットであり、worktree へ明示コピーしていた。その後の保存と追加コピーなしの引継ぎ確認は、本書の「コミットと新規 worktree への引継ぎ確認」に記載した。
