# DevSpace で作業する Agent へ

## 最初に読むもの

DevSpace は開発環境のリポジトリです。コードは次の独立した Git リポジトリにあります。実装・レビュー・不具合調査では、依頼内容と対象コードから repo を判断し、その入口と案内が指定する文書を読んでから設計・修正・レビューの判断を行ってください。ユーザーがナレッジや文書名を指定する必要はありません。

| 対象 | 入口・案内 |
| --- | --- |
| TheSkyBlessing 本体・共通 API | `TheSkyBlessing/AGENTS.md` → `TheSkyBlessing/docs/knowledge/README.md` |
| Asset の神器・Mob・Object 等 | `Asset/AGENTS.md` → `Asset/docs/knowledge/README.md` |
| 環境設定・setup・起動処理 | `README.md`、`docs/rebuild-verification.md`。設計理由が必要なら `docs/development-environment-design.md` の対象節 |

- 必要な文書は Agent が選ぶ。参照するかをユーザーに確認せず、対象 repo の README の案内から該当領域へ進む。レビューのみ・調査のみでも同じ入口を使い、編集禁止の指示は維持する。
- 開発対象が増えたときやブランチ変更後は、対象 repo の入口を読み直す。詳細文書はリンクされているだけで読み込み済みとは扱わない。
- 読取結果に `truncated`・省略があれば、その範囲は未読として扱い、対象ファイルを行範囲・節ごとに分けて取り直す。コマンドの成功だけを読了の根拠にしない。設計判断前に、依頼から選んだ関連領域と取得済みの本文を照合する。
- 他の Agent に作業を委譲するときは、対象 repo のパスと必読文書を伝える。
- `Asset-AnimatedJava` は生成物を含む独立 repo。調査は入口と必要なモデルに絞る。この repo の体系的な知識整理は今回の2 repo の整理対象に含まれない。

## Git とファイルの扱い

- Asset／TheSkyBlessing の `master` へ直接コミットしない。コミット前に対象 repo のブランチを確認し、`master` 上なら作業用ブランチを作成・切替してからコミットする。

- 子 repo は親の `.gitignore` 対象。コード検索と `git status` / `git diff` は対象 repo を作業ディレクトリにして行う。親の検索結果や差分だけで判断しない。
- 各 repo のブランチ・未コミット変更を保持する。環境のセットアップで pull / checkout / reset を自動実行しない。
- `.runtime/`、`.cache/`、`.worktrees/`、`devspace.local.conf`、`.devcontainer/.env` はローカル領域。ワールドや個人設定を共有文書へ埋め込まない。
- 子 repo のナレッジを共有するには、その repo 側の変更として扱う。親 DevSpace のコミットだけでは子 repo の変更は保存されない。

## 環境変更時の確認

- Minecraft 1.20.4 / Vanilla、基準 Java 17。通常利用は AJ `dist`。AJ `master` の pack 個数判定の制約は検証記録を参照する。
- 起動は `sh scripts/server.sh`。既存 pack 内の通常編集は保存 → `/reload`。独立 pack の追加・削除や参照 repo の切替はサーバーを停止してから再起動する。
- ワールド指定はホストで `sh scripts/setup.sh --container "ワールドのパス"`。設定は保存され、W1 マウントの変更にはコンテナの再作成が必要。ネイティブでは `--container` を省く。
- 指定ワールドには直接保存される。リンクの整理で利用者の実フォルダや独自リンクを削除しない。ロックは実プロセスの停止を確認せず手動削除しない。
- 実サーバーでの機能検証は `docs/runtime-verification.md` を読み、`sh scripts/verify.sh <シナリオ.json>` を使う。通常worldの設定を変更せず、期待値・実測値・失敗・再試行を保存する。新しい機能のシナリオは対象repo側へ置く。
- setup/runtime のロジック変更時は `sh tests/setup.sh` と `sh tests/runtime.sh` を実行する。これらの成功とゲーム内検証の成功を区別する。文書だけの変更にはサーバー再起動を必須にしない。

## 知識の更新

実装、レビューのみの作業、不具合調査、ユーザーからの訂正で、次の開発に使える知見を得たら、別途の記録依頼を待たず、その作業内で対象 repo のナレッジを更新する。理由・適用範囲・現行の実例・出典・確認方法と実施範囲を残し、既存の誤記は元の説明から訂正する。ユーザーの方針、現行コードの事実、未確定の提案を区別する。

完了報告前に記録漏れと文書間の矛盾を確認し、更新先、または更新不要の理由を短く報告する。明示的な読み取り専用・編集禁止の作業では編集せず、記録候補と保存先を報告する。知見や未確認事項を記録のために作らない。詳細は [ナレッジの配置と更新](docs/knowledge-maintenance.md) を参照する。子 repo の記録はそれぞれの repo の変更として扱い、commit／push の権限は別途の指示に従う。環境の検証状況は、実施済みの範囲と実機未検証を区別する。
