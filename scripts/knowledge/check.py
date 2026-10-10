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

    try:
        targets = collect(root, arguments)
    except ValueError as outside:
        print(f'作業コピーの外のパスは検査できない: {outside}', file=sys.stderr)
        return 2
    except LookupError as base:
        print(f'--base のrefを解決できない: {base}。fetch済みのrefを渡す', file=sys.stderr)
        return 2
    knowledge = [path for path in targets
                 if path.startswith(notes.KNOWLEDGE_DIR + '/') and path != notes.ENTRY_DOC]
    findings = {}
    for path in knowledge:
        messages = notes.validate(notes.Document(root, path))
        if messages:
            findings[path] = messages
    for path, messages in duplicate_titles(root, knowledge).items():
        findings.setdefault(path, []).extend(messages)

    report(root, targets, knowledge, sorted(findings.items()))
    return 1 if findings else 0


def duplicate_titles(root, knowledge):
    """Report titles that another document of the same working copy already uses."""
    titles = {}
    for document in notes.documents(root):
        if document.header.get('title'):
            titles.setdefault(document.header['title'], []).append(document.relative)
    found = {}
    for paths in titles.values():
        for path in paths if len(paths) > 1 else ():
            others = ', '.join(f'`{other}`' for other in paths if other != path)
            if path in knowledge:
                found.setdefault(path, []).append(f'title が他の文書と重複している: {others}')
    return found


def collect(root, arguments):
    """Choose the files to inspect: the request, the whole knowledge set, or the diff."""
    if arguments.paths:
        chosen = []
        for path in arguments.paths:
            found = relative(root, path)
            if found is None:
                raise ValueError(path)
            chosen.append(found)
    elif arguments.all:
        chosen = [document.relative for document in notes.documents(root)]
    else:
        chosen = changed(root)
    if arguments.base:
        # An unresolvable ref would otherwise look like an empty difference.
        if not notes.git_output(root, 'rev-parse', '--verify', '--quiet',
                                f'{arguments.base}^{{commit}}'):
            raise LookupError(arguments.base)
        diff = notes.git_output(root, 'diff', '--name-only', '--diff-filter=ACMR',
                                f'{arguments.base}...HEAD')
        chosen += [line for line in diff.split('\n') if line]
    return sorted({path for path in chosen if (root / path).is_file()})


def relative(root, path):
    """Name a requested path relative to the working copy, or None if it falls outside."""
    candidate = Path(path)
    for base in (Path.cwd(), root):
        resolved = (candidate if candidate.is_absolute() else base / candidate).resolve()
        try:
            return resolved.relative_to(root).as_posix()
        except ValueError:
            continue
    return None


def changed(root):
    """List working-tree and staged changes, including untracked files."""
    status = notes.git_output(root, '-c', 'core.quotePath=false', 'status', '--porcelain=v1',
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
