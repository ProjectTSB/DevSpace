"""Check changed knowledge documents of a working copy against the note conventions.

Reports header shape, the correspondence between header and body, reference targets,
links left pointing at deleted or renamed files, area documents missing from the entry's
guide, and any change to a protected file that a person has to merge. Changes are counted
from the merge base with --base, or by default with the remote default branch
(`origin/HEAD`). Reading only: the working tree and the Git index stay as they are.

    sh scripts/knowledge/check.sh <作業コピー> [<path> ...] [--base <ref>] [--all]
"""
import argparse
import ast
import re
import sys
from pathlib import Path

import notes


UNREADABLE = '開けないか、UTF-8 として読めない'


# Files holding a protected list; a change to one of them is compared with the others.
DRIFT_SOURCES = ('docs/knowledge-notes.md', 'scripts/knowledge/notes.py',
                 '.github/workflows/auto-merge-docs-tests.yml')


class OutsideWorkcopy(Exception):
    """A requested path that does not belong to the working copy."""


class MissingPath(Exception):
    """A requested path that names no file, such as a mistyped name."""


def main(argv=None):
    parser = argparse.ArgumentParser(description='変更したノートのヘッダー・参照先を検査する')
    parser.add_argument('workcopy', help='対象repoの作業コピー（repo直下）')
    parser.add_argument('paths', nargs='*', help='検査するファイル（既定は既定ブランチからの変更）')
    parser.add_argument('--base', help='差分の基準にするref（既定は origin/HEAD、なければ origin/main か origin/master）')
    parser.add_argument('--all', action='store_true', help='ナレッジ文書をすべて検査する')
    arguments = parser.parse_intermixed_args(argv)
    notes.utf8_console()

    root = Path(arguments.workcopy).resolve()
    # A failing git would read as "no changes", so the working copy must resolve to itself.
    problem = notes.git_problem(root)
    if problem:
        print(problem, file=sys.stderr)
        return 2
    try:
        return inspect(root, arguments)
    except notes.GitFailure as failure:
        print(f'gitで変更やファイルの一覧を読めない: {failure}', file=sys.stderr)
        return 2
    except OSError as error:
        # A traceback would exit with 1, the status that means findings.
        print(f'ファイルやディレクトリを読めず、検査を続けられない: {error}', file=sys.stderr)
        return 2


def inspect(root, arguments):
    """Report the findings for the chosen files and return the exit status."""
    try:
        targets, changes, removed, base = collect(root, arguments)
    except OutsideWorkcopy as outside:
        print(f'作業コピーの外のパスは検査できない: {outside}', file=sys.stderr)
        return 2
    except MissingPath as missing_path:
        print(f'指定したファイルがない: {missing_path}', file=sys.stderr)
        return 2
    except LookupError as base:
        if base.args[0] is None:
            print('差分の基準にする既定ブランチ（origin/HEAD・origin/main・origin/master）がない。'
                  '--base <ref> を渡す', file=sys.stderr)
        else:
            print(f'差分の基準 {base} を使えない。fetch済みで、HEADと共通の祖先を持つrefを渡す',
                  file=sys.stderr)
        return 2
    knowledge = [path for path in targets if path.startswith(notes.KNOWLEDGE_DIR + '/')
                 and path.endswith('.md') and path != notes.ENTRY_DOC]
    findings = {}
    for path in knowledge:
        document = read(root, path)
        messages = notes.validate(document) if document else [UNREADABLE]
        if messages:
            findings[path] = messages
    for path, messages in duplicate_titles(root, knowledge).items():
        findings.setdefault(path, []).extend(messages)
    entry_messages, reported = entry_findings(root, targets, removed, arguments.all)
    for path, messages in entry_messages.items():
        findings.setdefault(path, []).extend(messages)
    unread = {path for path, messages in findings.items() if UNREADABLE in messages}
    for path, messages in stale_references(root, removed, reported, knowledge, unread).items():
        findings.setdefault(path, []).extend(messages)
    # The lists are compared only when one of them is part of the change: a branch made
    # before the other side changed must not be asked to edit a file it never touched.
    if arguments.all or set(targets + removed) & set(DRIFT_SOURCES):
        for path, messages in protected_list_drift(root).items():
            findings.setdefault(path, []).extend(messages)

    hits = notes.protected_hits(root, sorted(set(changes + removed)))
    if base and notes.branch_name(root) == notes.default_branch(root):
        for path, message in default_branch_findings(root, base):
            findings.setdefault(path, []).append(message)
    report(root, base, targets, removed, knowledge, hits, sorted(findings.items()))
    return 1 if findings else 0


def assigned_tuples(path):
    """Read the string tuples a Python file assigns at module level, without running it."""
    if not path.is_file():
        return {}
    found = {}
    for node in ast.parse(path.read_text(encoding='utf-8')).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Tuple):
            values = [element.value for element in node.value.elts
                      if isinstance(element, ast.Constant) and isinstance(element.value, str)]
            found[node.targets[0].id] = tuple(values)
    return found


def default_branch_findings(root, base):
    """On the default branch, name what may not be committed there.

    Nothing else stops a change pushed straight to the default branch. Only staged changes
    and commits not yet in the base count; unstaged and untracked files may belong to
    someone else working in the same copy.
    """
    branch = notes.branch_name(root)
    # Without rename detection a move lists its source too, such as AGENTS.md moved to docs/.
    staged = notes.git_output(root, '-c', 'core.quotePath=false', 'diff', '--cached', '--name-only',
                              '--no-renames', required=True)
    committed = notes.git_output(root, '-c', 'core.quotePath=false', 'diff', '--name-only',
                                 '--no-renames', f'{base}...HEAD', required=True)
    paths = sorted(set(filter(None, f'{staged}\n{committed}'.split('\n'))))
    protected = set(notes.protected_hits(root, paths))
    for path in paths:
        if not notes.is_devspace(root):
            yield path, f'既定ブランチ {branch} の上で変更をstage・commitしている。作業用ブランチを作って移す'
        elif path in protected:
            yield path, f'既定ブランチ {branch} の上で保護対象を変更している。作業用ブランチへ移してPRにする'
        elif not path.endswith('.md') or not (path.startswith('docs/') or '/' not in path):
            # The integrator publishes shared knowledge on main; scripts and settings are not.
            yield path, (f'既定ブランチ {branch} の上で共通知識の文書以外を変更している。'
                         'スクリプト・環境設定は作業用ブランチからPRにする')


def protected_list_drift(root):
    """Compare the protected lists kept outside notes.py with the ones in notes.py.

    In DevSpace the lists come from the checked working copy's own notes.py, so a branch
    that changes both the table and notes.py agrees with itself even when the script run is
    the default branch's, as in a review.
    """
    found = {}
    try:
        return drift(root, found)
    except (UnicodeDecodeError, OSError):
        found.setdefault('(保護対象の一覧)', []).append(f'一覧を持つファイルを読めない。{UNREADABLE}')
        return found


def drift(root, found):
    if notes.is_devspace(root):
        table = (root / 'docs/knowledge-notes.md')
        rows = {}
        if table.is_file():
            for line in table.read_text(encoding='utf-8-sig').split('\n'):
                cells = [cell.strip() for cell in line.split('|')]
                if len(cells) > 3:
                    rows[cells[1]] = set(re.findall(r'`([^`]+)`', cells[2]))
        own = assigned_tuples(root / 'scripts/knowledge/notes.py')
        lists = (('DevSpace', own.get('DEVSPACE_PROTECTED', notes.DEVSPACE_PROTECTED)),
                 ('Asset・TheSkyBlessing', own.get('CHILD_PROTECTED', notes.CHILD_PROTECTED)))
        for name, listed in lists:
            if rows.get(name) != set(listed):
                found.setdefault('docs/knowledge-notes.md', []).append(
                    f'人がマージする範囲の表の {name} の行が scripts/knowledge/notes.py の一覧と違う')
        return found
    workflow = root / '.github/workflows/auto-merge-docs-tests.yml'
    if workflow.is_file():
        text = workflow.read_text(encoding='utf-8')
        for pattern, expected, label in (
                (r'const protectedPaths = \[(.*?)\];', notes.CHILD_PROTECTED, '`protectedPaths`'),
                (r'\[([^\]]*)\]\.includes\(parts\.at\(-1\)\)', notes.INSTRUCTION_NAMES,
                 '指示ファイルの名前の一覧')):
            match = re.search(pattern, text, re.S)
            listed = set(re.findall(r"'([^']+)'", match.group(1))) if match else set()
            if listed != set(expected):
                found.setdefault('.github/workflows/auto-merge-docs-tests.yml', []).append(
                    f'{label} が DevSpace の scripts/knowledge/notes.py の一覧と違う')
    return found


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
    if not (everything or touched):
        return {}, set()
    if not (root / notes.ENTRY_DOC).is_file():
        # Without the entry the area documents left behind are not routed from anywhere.
        if any(notes.is_area_document(path) for path in notes.knowledge_paths(root)):
            return {notes.ENTRY_DOC: ['入口がなく、領域文書を案内表から辿れない']}, set()
        return {}, set()
    entry = read(root, notes.ENTRY_DOC)
    if entry is None:
        return {notes.ENTRY_DOC: [UNREADABLE]}, set()
    messages = list(notes.check_links(entry))
    messages.extend(f'領域文書が入口の案内表にない: `{path}`'
                    for path in notes.unrouted_area_documents(root))
    reported = {(notes.ENTRY_DOC, link) for link in notes.broken_links(entry)}
    return ({notes.ENTRY_DOC: messages} if messages else {}), reported


def stale_references(root, removed, reported, validated, unread):
    """Find `.md` files in the working copy that still point at a deleted or renamed path."""
    if not removed:
        return {}
    gone = set(removed)
    listing = notes.git_output(root, '-c', 'core.quotePath=false', 'ls-files', '--cached',
                               '--others', '--exclude-standard', '--', '*.md', required=True)
    found = {}
    for path in sorted({line for line in listing.split('\n') if line}):
        if path in gone or not (root / path).is_file():
            continue
        document = read(root, path)
        if document is None:
            # Passing over an unread file would let the check succeed without looking at it.
            if path not in unread:
                found[path] = [UNREADABLE + 'ため、削除・移動したファイルへの参照を確認できない']
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
    except (UnicodeDecodeError, OSError):
        return None


def collect(root, arguments):
    """Choose the files to inspect, the changed files, the removed paths, and the base used."""
    chosen, removed = changed(root)
    base = arguments.base or notes.default_base(root)
    if base is None and not (arguments.paths or arguments.all):
        # Without a base the commits on this branch would go unseen behind a clean tree.
        raise LookupError(None)
    if base:
        # An unresolvable ref, or one without a common ancestor, would otherwise look
        # like an empty difference.
        if not notes.git_output(root, 'rev-parse', '--verify', '--quiet', f'{base}^{{commit}}') \
                or not notes.git_output(root, 'merge-base', base, 'HEAD'):
            raise LookupError(base)
        # Unquoted paths keep non-ASCII names readable, like the status listing.
        diff = notes.git_output(root, '-c', 'core.quotePath=false', 'diff', '--name-status',
                                f'{base}...HEAD', required=True)
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
        return targets, sorted(set(targets) & set(changes)), [], base
    if arguments.all:
        return notes.knowledge_paths(root), changes, removed, base
    return changes, changes, removed, base


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
                              '--untracked-files=all', strip=False, required=True)
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


def report(root, base, targets, removed, knowledge, hits, findings):
    print(f'# ノート検査: {notes.repository_name(root)}（ブランチ {notes.branch_name(root)}）')
    print()
    if base:
        print(f'- 変更は `{base}` との共通祖先からの差分と、未コミットの変更から集めた')
    else:
        print('- 差分の基準がないため、変更は未コミットのものだけを集めた')
    print(f'- 対象ファイル {len(targets)}件、検査したナレッジ文書 {len(knowledge)}件')
    if removed:
        print(f'- 削除・移動したファイル {len(removed)}件。作業コピー内の .md ファイルから参照が残っていないか確認した')
    print()

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
