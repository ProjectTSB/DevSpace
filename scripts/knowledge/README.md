# ナレッジINDEXとノート検査

対象repoの作業コピーにあるナレッジのヘッダーからINDEXを生成し、変更したノートを検査する処理をまとめる。ノートの形式・参照先・保護対象の規約は [ナレッジのノートとINDEX](../../docs/knowledge-notes.md) が正本で、ここでは実行方法と作用先を説明する。

## 実行

```sh
python3 scripts/knowledge/index.py <作業コピー> [--area <領域>] [--notes-only]
python3 scripts/knowledge/check.py <作業コピー> [--base <ref>] [--all] [<path> ...]
```

`<作業コピー>` は対象repoのrepo直下を指す。DevSpaceからの相対パスでも絶対パスでもよく、worktreeを渡した場合はそのブランチのナレッジだけを読む。固定の親相対パスは仮定しない。

- 入力: `<作業コピー>/docs/knowledge/` のMarkdownと、repo名・ブランチ名を得るための読取専用のGit問合せ。
- 出力: 標準出力へのMarkdown。INDEXファイルは保存しない。追跡ファイル・Git index・作業ツリーは変更しない。
- 環境: Python 3（追加パッケージなし）。DevSpaceのコンテナとネイティブ環境の両方で同じ結果になる。

`index.py` は `docs/knowledge/` が無い作業コピーでは終了コード2で理由を示す。`check.py` は指摘が1件以上あれば終了コード1を返す。保護対象の変更は指摘ではなく、人のマージが必要な変更として一覧に出す。

`check.py` の既定の対象は未コミットの変更（staged・未staged・未追跡）で、`--base` を足すとそのrefからの差分も検査する。公開前の確認は `--base origin/<既定ブランチ>` を使う。

## 変更するとき

ヘッダーのキー・上限・保護対象の一覧は `notes.py` が持つ。規約を変える場合は `docs/knowledge-notes.md` と、子repoの `.github/workflows/auto-merge-docs-tests.yml` の保護対象を併せて更新する。回帰確認は `python3 tests/knowledge.py`。
