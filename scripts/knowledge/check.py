"""Check changed knowledge documents of a working copy against the note conventions.

Reports header shape, the correspondence between header and body, reference targets,
links left pointing at deleted or renamed files, area documents missing from the entry's
guide, and any change to a protected file that a person has to merge. Reading only: the
working tree and the Git index stay as they are.

    python3 scripts/knowledge/check.py <作業コピー> [<path> ...] [--base <ref>] [--all]
"""
import argparse
import sys
from pathlib import Path

import notes


class OutsideWorkcopy(Exception):
    """A requested path that does not belong to the working copy."""


class MissingPath(Exception):
    """A requested path that names no file, such as a mistyped name."""


def main(argv=None):
    parser = argparse.ArgumentParser(description='変更したノートのヘッダー・参照先を検査する')
    parser.add_argument('workcopy', help='対象repoの作業コピー（repo直下）')
    parser.add_argument('paths', nargs='*', help='検査するファイル（既定は未コミットの変更）')
    parser.add_argument('--base', help='このrefからの差分も対象に加える（例: origin/master）')
    parser.add_argument('--all', action='store_true', help='ナレッジ文書をすべて検査する')
    arguments = parser.parse_intermixed_args(argv)

    root = Path(arguments.workcopy).resolve()
    # A failing git would read as "no changes", so the working copy must resolve to itself.
    problem = notes.git_problem(root)
    if problem:
        print(problem, file=sys.stderr)
        return 2

    try:
        targets, changes, removed = collect(root, arguments)
    except OutsideWorkcopy as outside:
        print(f'作業コピーの外のパスは検査できない: {outside}', file=sys.stderr)
        return 2
    except MissingPath as missing_path:
        print(f'指定したファイルがない: {missing_path}', file=sys.stderr)
        return 2
    except LookupError as base:
        print(f'--base を差分の基準にできない: {base}。fetch済みで、HEADと共通の祖先を持つrefを渡す',
              file=sys.stderr)
        return 2
    knowledge = [path for path in targets if path.startswith(notes.KNOWLEDGE_DIR + '/')
                 and path.endswith('.md') and path != notes.ENTRY_DOC]
    findings, unreadable = {}, []
    for path in knowledge:
        document = read(root, path)
        messages = notes.validate(document) if document else ['UTF-8 として読めない']
        if messages:
            findings[path] = messages
    for path, messages in duplicate_titles(root, knowledge).items():
        findings.setdefault(path, []).extend(messages)
    entry_messages, reported = entry_findings(root, targets, removed, arguments.all)
    for path, messages in entry_messages.items():
        findings.setdefault(path, []).extend(messages)
    for path, messages in stale_references(root, removed, unreadable, reported, knowledge).items():
        findings.setdefault(path, []).extend(messages)

    report(root, changes, targets, removed, knowledge, unreadable, sorted(findings.items()))
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


def entry_findings(root, targets, removed, everything):
    """Check the entry's links and guide table; also name the links already reported."""
    touched = [path for path in targets + removed
               if path == notes.ENTRY_DOC or notes.is_area_document(path)]
    if not (everything or touched) or not (root / notes.ENTRY_DOC).is_file():
        return {}, set()
    entry = read(root, notes.ENTRY_DOC)
    if entry is None:
        return {notes.ENTRY_DOC: ['UTF-8 として読めない']}, set()
    messages = list(notes.check_links(entry))
    messages.extend(f'領域文書が入口の案内表にない: `{path}`'
                    for path in notes.unrouted_area_documents(root))
    reported = {(notes.ENTRY_DOC, link) for link in notes.broken_links(entry)}
    return ({notes.ENTRY_DOC: messages} if messages else {}), reported


def stale_references(root, removed, unreadable, reported, validated):
    """Find Markdown in the working copy that still points at a deleted or renamed path."""
    if not removed:
        return {}
    gone = set(removed)
    listing = notes.git_output(root, '-c', 'core.quotePath=false', 'ls-files', '--cached',
                               '--others', '--exclude-standard', '--', '*.md')
    found = {}
    for path in sorted({line for line in listing.split('\n') if line}):
        if path in gone or not (root / path).is_file():
            continue
        document = read(root, path)
        if document is None:
            unreadable.append(path)
            continue
        for link, target in notes.link_targets(document):
            # A directory reference breaks once no file is left under it; Git drops
            # empty directories, so an empty one left on disk counts as gone too.
            # Missing targets of validated documents are already reported by their checks.
            if path in validated and not (root / target).exists():
                continue
            if (path, link) not in reported and missing(root / target) and (
                    target in gone or any(lost.startswith(target + '/') for lost in gone)):
                found.setdefault(path, []).append(f'削除・移動したファイルを参照している: {link}')
    return found


def missing(path):
    if path.is_dir():
        return not any(child.is_file() for child in path.rglob('*'))
    return not path.exists()


def read(root, path):
    try:
        return notes.Document(root, path)
    except UnicodeDecodeError:
        return None


def collect(root, arguments):
    """Choose the files to inspect, the changed files, and the paths the change removed."""
    chosen, removed = changed(root)
    if arguments.base:
        # An unresolvable ref, or one without a common ancestor, would otherwise look
        # like an empty difference.
        if not notes.git_output(root, 'rev-parse', '--verify', '--quiet',
                                f'{arguments.base}^{{commit}}') \
                or not notes.git_output(root, 'merge-base', arguments.base, 'HEAD'):
            raise LookupError(arguments.base)
        # Unquoted paths keep non-ASCII names readable, like the status listing.
        diff = notes.git_output(root, '-c', 'core.quotePath=false', 'diff', '--name-status',
                                f'{arguments.base}...HEAD')
        for line in diff.split('\n'):
            fields = line.split('\t')
            if len(fields) < 2:
                continue
            if fields[0].startswith(('D', 'R')):
                removed.append(fields[1])
            if not fields[0].startswith('D'):
                chosen.append(fields[-1])
    changes = sorted({path for path in chosen if (root / path).is_file()})
    removed = sorted({path for path in removed if not (root / path).exists()})
    if arguments.paths:
        # A named file set is inspected on its own, without the rest of the working tree.
        targets = []
        for path in arguments.paths:
            found = relative(root, path)
            if found is None:
                raise OutsideWorkcopy(path)
            if not (root / found).is_file():
                raise MissingPath(path)
            targets.append(found)
        targets = sorted(set(targets))
        return targets, sorted(set(targets) & set(changes)), []
    if arguments.all:
        return notes.knowledge_paths(root), changes, removed
    return changes, changes, removed


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
    """List working-tree and staged changes, and the paths those changes removed."""
    status = notes.git_output(root, '-c', 'core.quotePath=false', 'status', '--porcelain=v1',
                              '--untracked-files=all', strip=False)
    paths, removed = [], []
    for line in status.split('\n'):
        if len(line) < 4:
            continue
        # A rename reports `old -> new`: the new path is read, the old one is gone.
        names = [name.strip('"') for name in line[3:].split(' -> ')]
        paths.append(names[-1])
        if len(names) > 1 or 'D' in line[:2]:
            removed.append(names[0])
    return paths, removed


def report(root, changes, targets, removed, knowledge, unreadable, findings):
    print(f'# ノート検査: {notes.repository_name(root)}（ブランチ {notes.branch_name(root)}）')
    print()
    print(f'- 対象ファイル {len(targets)}件、検査したナレッジ文書 {len(knowledge)}件')
    if removed:
        print(f'- 削除・移動したファイル {len(removed)}件。作業コピー内のMarkdownから参照が残っていないか確認した')
    if unreadable:
        print('- UTF-8 として読めず、参照を確認できなかったファイル: '
              + ', '.join(f'`{path}`' for path in unreadable))
    print()

    hits = notes.protected_hits(root, sorted(set(changes + removed)))
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
