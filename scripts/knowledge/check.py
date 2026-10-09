"""Check changed knowledge documents of a working copy against the note conventions.

Reports header shape, the correspondence between header and body, reference targets,
and any change to a protected file that a person has to merge. Reading only: the
working tree and the Git index stay as they are.

    python3 scripts/knowledge/check.py <作業コピー> [--base <ref>] [--all] [<path> ...]
"""
import argparse
import sys
from pathlib import Path

import notes


def main(argv=None):
    parser = argparse.ArgumentParser(description='変更したノートのヘッダー・参照先を検査する')
    parser.add_argument('workcopy', help='対象repoの作業コピー（repo直下）')
    parser.add_argument('paths', nargs='*', help='検査するファイル（既定は未コミットの変更）')
    parser.add_argument('--base', help='このrefからの差分も対象に加える（例: origin/master）')
    parser.add_argument('--all', action='store_true', help='ナレッジ文書をすべて検査する')
    arguments = parser.parse_args(argv)

    root = Path(arguments.workcopy).resolve()
    if not (root / '.git').exists() and not notes.git_output(root, 'rev-parse', '--git-dir'):
        print(f'{root} はGitの作業コピーではない', file=sys.stderr)
        return 2

    targets = collect(root, arguments)
    knowledge = [path for path in targets
                 if path.startswith(notes.KNOWLEDGE_DIR + '/') and path != notes.ENTRY_DOC]
    findings = [(path, notes.validate(notes.Document(root, path))) for path in knowledge]
    findings = [(path, messages) for path, messages in findings if messages]

    report(root, targets, knowledge, findings)
    return 1 if findings else 0


def collect(root, arguments):
    """Choose the files to inspect: the request, the whole knowledge set, or the diff."""
    if arguments.paths:
        chosen = [relative(root, path) for path in arguments.paths]
    elif arguments.all:
        chosen = [document.relative for document in notes.documents(root)]
    else:
        chosen = changed(root)
    if arguments.base:
        diff = notes.git_output(root, 'diff', '--name-only', '--diff-filter=ACMR',
                                f'{arguments.base}...HEAD')
        chosen += [line for line in diff.split('\n') if line]
    return sorted({path for path in chosen if (root / path).is_file()})


def relative(root, path):
    candidate = Path(path)
    resolved = candidate if candidate.is_absolute() else Path.cwd() / candidate
    try:
        return resolved.resolve().relative_to(root).as_posix()
    except ValueError:
        return (root / path).resolve().relative_to(root).as_posix() if (root / path).exists() \
            else path.replace('\\', '/')


def changed(root):
    """List working-tree and staged changes, including untracked files."""
    status = notes.git_output(root, 'status', '--porcelain=v1',
                              '--untracked-files=all', strip=False)
    paths = []
    for line in status.split('\n'):
        if len(line) < 4:
            continue
        entry = line[3:]
        # A rename reports `old -> new`; only the current path can be read.
        paths.append(entry.split(' -> ')[-1].strip('"'))
    return paths


def report(root, targets, knowledge, findings):
    print(f'# ノート検査: {notes.repository_name(root)}（ブランチ {notes.branch_name(root)}）')
    print()
    print(f'- 対象ファイル {len(targets)}件、検査したナレッジ文書 {len(knowledge)}件')
    print()

    hits = notes.protected_hits(root, targets)
    if hits:
        print('## 保護対象の変更')
        print()
        for path in hits:
            print(f'- `{path}`')
        print()
        print('作業ブランチからPRを作り、人のマージを待つ。docs/tests の自動マージには載せない。')
        print()

    if not findings:
        print('## 指摘なし')
        return
    print('## 指摘')
    print()
    for path, messages in findings:
        print(f'- `{path}`')
        for message in messages:
            print(f'  - {message}')
    print()
    print(f'合計 {sum(len(messages) for _, messages in findings)}件の指摘がある。')


if __name__ == '__main__':
    raise SystemExit(main())
