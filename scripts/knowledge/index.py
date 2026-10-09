"""Print a knowledge INDEX built from the note headers on a working copy's branch.

Input is the checked-out `docs/knowledge/` of the given working copy plus read-only
Git queries for its repository and branch. Nothing is written: no INDEX file is kept,
so the result always matches the branch that is checked out right now.

    python3 scripts/knowledge/index.py <作業コピー> [--area <領域>] [--notes-only]
"""
import argparse
import sys
from pathlib import Path

import notes


def main(argv=None):
    parser = argparse.ArgumentParser(description='対象作業コピーのノートからINDEXを生成する')
    parser.add_argument('workcopy', help='対象repoの作業コピー（repo直下）')
    parser.add_argument('--area', help='この領域のノートだけを出力する')
    parser.add_argument('--notes-only', action='store_true', help='領域文書を省く')
    arguments = parser.parse_args(argv)

    root = Path(arguments.workcopy).resolve()
    if not (root / notes.KNOWLEDGE_DIR).is_dir():
        hint = 'DevSpaceの共通規約は docs/ の既存文書から読む' if notes.is_devspace(root) else \
            'ブランチを確認する。このブランチにナレッジがなければ既定ブランチのナレッジを読む'
        print(f'{root} に {notes.KNOWLEDGE_DIR}/ がない: {hint}', file=sys.stderr)
        return 2

    found = notes.documents(root, area=arguments.area, notes_only=arguments.notes_only)
    print('\n'.join(render(root, found, arguments)))
    return 0


def render(root, found, arguments):
    """Lay out the INDEX: the working copy it describes, then areas and their notes."""
    note_count = len([document for document in found if document.is_note])
    lines = [f'# ナレッジINDEX: {notes.repository_name(root)}', '']
    lines.append(f'- 作業コピー: `{root}`（ブランチ {notes.branch_name(root)}）')
    lines.append(f'- 領域文書 {len(found) - note_count}件、ノート {note_count}件')
    if arguments.area:
        lines.append(f'- 領域の絞り込み: {arguments.area}')
    lines.append(f'- 入口と更新規約: `{notes.ENTRY_DOC}`')
    lines.append('- 該当が無いときは探索範囲を広げ、コードと提供側の契約から知識の有無を判断する')
    lines.append('')

    unheadered = [document for document in found if not document.header.get('title')]
    for area in sorted({document.area for document in found}, key=area_order):
        group = [document for document in found
                 if document.area == area and document.header.get('title')]
        if not group:
            continue
        label = area if area == '領域文書' else f'ノート: {area}'
        lines.append(f'## {label}（{len(group)}件）')
        lines.append('')
        for document in group:
            lines.extend(entry(document))
        lines.append('')

    if unheadered:
        lines.append('## ヘッダー未整備（タイトルは本文の見出し）')
        lines.append('')
        for document in unheadered:
            lines.append(f'- `{document.relative}` — {document.title}')
        lines.append('')
        lines.append('ヘッダーは `docs/knowledge-notes.md` の規約に合わせて補う。')
        lines.append('')
    return lines


def entry(document):
    lines = [f'- **{document.title}** — {document.description}',
             f'  - path: `{document.relative}`']
    if document.header.get('paths'):
        lines.append('  - 対象: ' + ', '.join(f'`{value}`' for value in document.header['paths']))
    if document.header.get('ids'):
        lines.append('  - ID: ' + ', '.join(document.header['ids']))
    if document.header.get('related'):
        lines.append('  - 関連: ' + ', '.join(f'`{value}`' for value in document.header['related']))
    return lines


def area_order(area):
    # Area documents carry the overview, so they stay ahead of the individual notes.
    return (0, '') if area == '領域文書' else (1, area)


if __name__ == '__main__':
    raise SystemExit(main())
