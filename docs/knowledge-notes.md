# ナレッジのノートとINDEX

コード固有のナレッジは、対象repoの作業コピーにノートとして置く。探すときはノートのヘッダーからINDEXを生成し、必要な範囲だけを読む。INDEXのファイルや手書きのノート一覧は保存しない。ノートはコードと同じブランチにあるため、生成したINDEXはそのブランチの現在の知識を示す。

採用基準・保存先の分担・引渡しは [ナレッジの配置と更新](knowledge-maintenance.md) に従う。この文書はノートの形式、参照経路、機械的な検査、人がマージする範囲を定める。

## 参照経路

1. DevSpaceの `AGENTS.md`（`CLAUDE.md` は同じ本文）から、依頼内容で対象repoと作業コピーを決める。
2. その作業コピーの `docs/knowledge/README.md` で領域と横断参照を確認する。
3. `python3 scripts/knowledge/index.py <作業コピー>` でINDEXを生成し、`description` から読む領域文書とノートを選ぶ。
4. 選んだ本文と、そこが指す依存先の契約を読む。API契約は提供側repoのナレッジと現行コードで確認する。
5. 該当が無ければ領域を広げてINDEXを読み直し、コードと提供側の契約を確認してから知識の有無を判断する。

スクリプトはDevSpaceにあり、`<作業コピー>` には対象repoのrepo直下を渡す。DevSpaceと対象作業コピーの場所は引渡し情報または実際の配置で確認し、固定の親相対パスを仮定しない。ブランチを切り替えた後と、別の作業コピーへ移った後は、その作業コピーでINDEXを生成し直す。領域を絞るときは `--area <領域>`、ノートだけを見るときは `--notes-only` を使う。INDEXは索引であり、`description` だけで実装を判断しない。

## ノートの形式

ファイルは `docs/knowledge/notes/<領域>/<slug>.md` に置く。`<slug>` は英小文字・数字・ハイフンにする。先頭に `---` で囲んだヘッダーを置き、続けて本文を書く。

| キー | 必須 | 内容 |
| --- | --- | --- |
| `title` | 必須 | ノートの題。本文の `#` 見出しと同じ文にする（60文字以内） |
| `description` | 必須 | どの作業で読むかを示す一文（120文字以内） |
| `area` | 任意 | INDEXでまとめる領域名。省略すると `notes/` 配下のディレクトリ名を使う。ディレクトリに置いたノートで明示する場合は、そのディレクトリ名と揃える |
| `paths` | 任意 | 発見に役立つ対象パス。repo直下からの相対パス |
| `ids` | 任意 | 神器・Mob・Objectの4桁IDなど、検索に使う識別子 |
| `related` | 任意 | 関連する契約・領域文書への参照 |

`paths`・`ids`・`related` は、発見や照合に役立つノートだけに付ける。`verified_at` や主観的な `confidence` は必須項目にしない。上記以外のキーは検査で落ちる。

本文には根拠、適用条件、適用外の条件、関連する契約への参照を残す。原則は一つの判断を一つのノートで扱う。ただし前提・結果・後始末を一緒に理解する必要がある契約は分断しない。機能固有の値や演出はその機能のノートへ置き、コードを言い換えただけの説明は残さない。

```markdown
---
title: 移動の慣性だけを消すtpの往復
description: 移動を止める実装で、視点の慣性を残すか判断するときに読む
area: motion
paths:
  - Asset/data/asset/functions/artifact/0745.blade_of_whirlwind/trigger/3.main.mcfunction
related:
  - DevSpace:docs/mcfunction-idioms.md#実行位置を移動前の値として保持する
---

# 移動の慣性だけを消すtpの往復

（根拠・適用条件・適用外の条件）
```

参照先は次のように書く。

- 本文のリンクは、そのファイルからの相対パスにする。既存の領域文書と同じ書き方である。
- `paths` と `related` はrepo直下からの相対パスにする。ノートを移動してもヘッダーを書き換えずに済む。
- 依存repoの文書は `TheSkyBlessing:docs/knowledge/api-and-storage.md#節` の形式で書く。作業コピーごとに配置が違うため、repoをまたぐ固定の相対パスは書かない。
- 外部資料はURLで書く。

領域文書（`docs/knowledge/*.md`）は領域の全体像と入口、ノートは個別の判断を扱う。重要なAPI契約や構造の概要は領域文書から辿れる状態を保ち、INDEXの検索結果だけに依存させない。領域文書にも `title` と `description` のヘッダーを付け、同じINDEXから選べるようにする。

## 機械的な検査

ノートを変更したら、commit前とPR作成前に `python3 scripts/knowledge/check.py <作業コピー>` を実行する。公開前は `--base origin/<既定ブランチ>` を付けて、そのブランチの差分全体を対象にする。

検査するのはヘッダーの形式と必須キー、`title` と本文見出しの一致、`area` と置き場所の一致、同じ作業コピー内での `title` の重複、`paths`・`related`・本文リンクの参照先、ノートの置き場所とファイル名、保護対象の変更である。`--base` のrefを解決できない場合は、差分なしと区別して終了コード2で止まる。

根拠の妥当性、適用条件の説明、同じ判断を別の書き方で重複させていないか、実機の挙動は検査しない。重複は `title` が一致する場合しか機械的に分からないため、節をノートへ移したときは元の記述を消したかを差分で確認する。検査の成功を内容の正しさと扱わない。

## 既存文書からの移行

既存の領域文書を一括して細分化しない。次の条件がそろう単位で移す。

1. 一つの判断として読める範囲で、根拠と適用条件がその範囲に収まっている。
2. 移した後も領域文書・sources・依存repoからの参照経路が保てる。
3. 移す前に、その節の見出しへのリンクをDevSpaceと両repoから検索し、移動先へ更新できる。

節の見出しが他repoやDevSpaceから参照されている場合は、参照元を同時に更新できないかぎり移さない。移動で本文を書き換えるときは、根拠・適用条件・出典を落とさない。

## 人がマージする範囲

以後のAI全体の行動を変える文書・設定は、通常のPRを完成させて人がマージする。AIは自分でマージせず、自動マージも設定しない。

| repo | 保護対象 |
| --- | --- |
| DevSpace | `AGENTS.md`、`CLAUDE.md`、`docs/knowledge-maintenance.md`、`docs/knowledge-notes.md`、`scripts/knowledge/`、`tests/knowledge.py` |
| Asset・TheSkyBlessing | `AGENTS.md`、`docs/knowledge/README.md`、`.github/workflows/auto-merge-docs-tests.yml`、`.github/tests/auto-merge-docs-tests.test.cjs` |

保護するのはナレッジ運用の仕組み自体、つまり参照経路、採用・配置規則、検査、自動マージ条件である。全セッションの必読でも、[用語と表記](terminology.md)・[共通イディオム](mcfunction-idioms.md)・[Issue・PR本文の書き方](issue-pr-descriptions.md)・[開発用スクリプトの作成と保存](script-development.md) のような技術文書は仕組みを変えないため、保護対象に含めず逐次反映を続ける。保護対象を増減するときは、この表、`scripts/knowledge/notes.py` の一覧、両子repoの `.github/workflows/auto-merge-docs-tests.yml` を同時に更新する。

個別ノートの追加・訂正・削除と、そのヘッダーの更新は承認待ちにしない。既存の公開経路と上記の検査に従う。保護対象の内容を普通のノートへ移して人のマージを回避しない。Asset・TheSkyBlessingの `docs/`・`tests/` の自動マージは、この保護対象を含むPRを対象から外す。判定は各repoの `.github/workflows/auto-merge-docs-tests.yml` にあり、この表と同じ一覧を持つ。
