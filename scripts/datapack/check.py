"""Check a working copy's mcfunction against conventions the CI linter does not see.

    python3 scripts/datapack/check.py <作業コピー> [--base <ref>]

This header is the one list of the rules and of how to change them; AGENTS.md and the
README only say when to run the check and how to treat its results.

Rules on changed lines, that is lines added or changed since HEAD, or with --base since the
merge base with that ref. Existing code predates some of them, so unchanged lines are left
alone, and generated functions (GENERATED) are skipped:
  - `#declare` sits 4 spaces deeper than the `#>` IMP Doc block above it (finding)
  - `@a[...,sort=nearest,limit=1]` is the same selector as `@p[...]` and is written so
    (finding)
  - `@e` without dx/dy/dz or an upper distance is not bounded to a box (review note, since
    some searches need to be unbounded); `type=player` is left out, as it searches players
A file renamed without `git mv` is untracked and checked in full, so rename with `git mv`.
Paths with characters a function ID cannot have, such as spaces or quotes, are not read.
Rules of the target repository itself: a repository keeps the rules about its own
contracts, which usually span the whole working copy, in `scripts/datapack/repository.py`
(Asset, for example, keeps its ID and registration rules there). When the working copy has that
file, it is run as `python3 <file> <作業コピー> --json` and has to print
`{"findings": {"<path>": ["<message>", ...]}}`, listing only paths with at least one
message, and exit with 1 exactly when there are findings, 0 without, or 2 when it cannot
check. Its findings are listed under their own heading, since they may come from code the
current change did not touch. Running it executes code of the working copy, including
modules next to it, so a review reads any change under `scripts/datapack/` first.

The check itself only reads: it changes neither the working tree nor the Git index. Exit
status is 0 without findings (review notes may remain), 1 with findings, and 2 when the
working copy, the base or the repository's own check cannot be read.

Changing the rules:
  - Add a rule for a convention in AGENTS.md or docs/mcfunction-idioms.md that review or
    an AI missed and that the text alone decides. A contract of one repository goes to
    that repository's repository.py instead, and a convention that needs judgment stays
    in the documents.
  - Count the existing violations in Asset and TheSkyBlessing first, for example by running
    the rule with `--base $(git rev-list --max-parents=0 HEAD)`, which counts every line.
    A rule with none may look at the whole working copy; otherwise it looks at changed lines
    only.
  - Make it a finding when it has no legitimate exception, else a review note.
  - Base a rule on vanilla behaviour only after reading the target version's source
    (docs/minecraft-source.md), and cite the version, class and method next to it.
  - Add a test to tests/datapack.py that fails without the rule, then run the check over a
    recent range of real commits (for example `--base HEAD~30` on Asset) to see the noise.
  - On a version migration, check the rules that rest on vanilla behaviour against the new
    version's source. Drop a rule once the CI linter covers it, and add a file to
    GENERATED once its generator is known.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from workcopy import GitFailure, branch_name, git_output, git_problem, repository_name  # noqa: E402

# Written by TheSkyBlessing's datapack-linter workflow; fixed in its generator, not here.
GENERATED = {'Asset/data/minecraft/functions/declares.d.mcfunction'}
REPOSITORY_CHECK = 'scripts/datapack/repository.py'
HUNK = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@')
# Only dx/dy/dz or a distance with an upper bound give the search a box (1.20.4
# `EntitySelectorParser#getSelector`). Any of these, x/y/z and a distance with only a lower
# bound keep it to the running dimension (`EntitySelectorOptions#bootStrap`); with none of
# them `EntitySelector#findEntitiesRaw` visits every dimension. `type=player` searches
# players instead of entities (`bootStrap` clears includesEntities), so it is not noted.
DELTAS = {'dx', 'dy', 'dz'}
LOCATING = DELTAS | {'distance', 'x', 'y', 'z'}


def main(argv=None):
    parser = argparse.ArgumentParser(description='mcfunctionの規約を変更した行で検査し、repo固有の検査も実行する')
    parser.add_argument('workcopy', help='対象repoの作業コピー（repo直下）')
    parser.add_argument('--base', help='このrefとの共通祖先からの変更を対象にする（例: origin/master）')
    arguments = parser.parse_args(argv)

    root = Path(arguments.workcopy).resolve()
    problem = git_problem(root)
    if problem:
        print(problem, file=sys.stderr)
        return 2
    try:
        start = starting_point(root, arguments.base)
        lines = changed_lines(root, start)
    except LookupError as base:
        print(f'--base を差分の基準にできない: {base}。fetch済みで、HEADと共通の祖先を持つrefを渡す',
              file=sys.stderr)
        return 2
    except GitFailure as failure:
        print(f'gitで変更を読めない: {failure}', file=sys.stderr)
        return 2
    try:
        return inspect(root, arguments.base, lines)
    except RepositoryCheckFailure as failure:
        print(failure, file=sys.stderr)
        return 2
    except OSError as error:
        # A traceback would exit with 1, the status that means findings.
        print(f'ファイルを読めず、検査を続けられない: {error}', file=sys.stderr)
        return 2


def inspect(root, base, lines):
    findings, notes = {}, {}
    scripts = sorted(path for path in lines if path.endswith('.mcfunction')
                     and path not in GENERATED and (root / path).is_file())
    for path in scripts:
        found, noted = line_findings((root / path).read_text(encoding='utf-8', errors='replace'),
                                     lines[path])
        if found:
            findings[path] = found
        if noted:
            notes[path] = noted
    own = repository_findings(root)
    report(root, base, scripts, findings, own, notes)
    return 1 if findings or own else 0


class RepositoryCheckFailure(Exception):
    """The target repository's own check could not run or answered in another shape."""


def repository_findings(root):
    """Run the repository's own check if it has one; None when it does not."""
    script = root / REPOSITORY_CHECK
    if not script.is_file():
        return None
    result = subprocess.run([sys.executable, str(script), str(root), '--json'],
                            capture_output=True, text=True, check=False,
                            env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
    try:
        found = json.loads(result.stdout)['findings'] if result.returncode in (0, 1) else None
    except (ValueError, KeyError, TypeError):
        found = None
    well_formed = isinstance(found, dict) and all(
        isinstance(messages, list) and messages and all(isinstance(m, str) and m for m in messages)
        for messages in found.values())
    if result.returncode not in (0, 1):
        detail = (result.stderr or result.stdout).strip().split('\n')[-1]
        raise RepositoryCheckFailure(f'{REPOSITORY_CHECK} が終了コード {result.returncode} で失敗した: {detail}')
    if not well_formed or bool(found) != (result.returncode == 1):
        raise RepositoryCheckFailure(f'{REPOSITORY_CHECK} の出力が取り決めの形と違う'
                                     f'（終了コード {result.returncode}、出力 {result.stdout.strip()[:120]}）')
    return found


def starting_point(root, base):
    """Name the commit that changes are counted from."""
    if not base:
        return 'HEAD'
    if not git_output(root, 'rev-parse', '--verify', '--quiet', f'{base}^{{commit}}'):
        raise LookupError(base)
    merge_base = git_output(root, 'merge-base', base, 'HEAD')
    if not merge_base:
        raise LookupError(base)
    return merge_base


def changed_lines(root, start):
    """Map each changed path to its added line numbers; an untracked file counts in full."""
    # diff-index leaves the index untouched, unlike diff. Fixed prefixes, text mode, rename
    # detection and no textconv keep the `+++ b/<path>` lines and hunks this parser reads,
    # whatever diff.noprefix, diff.mnemonicPrefix, diff.renames, a `-diff` attribute or a
    # textconv driver say.
    diff = git_output(root, '-c', 'core.quotePath=false', 'diff-index', '-p', '-U0', '--text',
                      '--find-renames', '--no-ext-diff', '--no-textconv', '--src-prefix=a/',
                      '--dst-prefix=b/', start, '--', strip=False, required=True)
    lines, path = {}, None
    for line in diff.split('\n'):
        if line.startswith('+++ '):
            # Git ends a path holding spaces with a tab here.
            path = line[6:].rstrip('\t') if line.startswith('+++ b/') else None
        elif path and (match := HUNK.match(line)):
            first, count = int(match.group(1)), int(match.group(2) or 1)
            lines.setdefault(path, set()).update(range(first, first + count))
    untracked = git_output(root, '-c', 'core.quotePath=false', 'ls-files', '--others',
                           '--exclude-standard', required=True)
    for path in filter(None, untracked.split('\n')):
        lines[path] = None
    return lines


def line_findings(text, changed):
    """Check the changed lines of one function; `changed` is None for a new file."""
    found, noted = [], []
    doc = None
    for number, line in enumerate(text.split('\n'), 1):
        stripped = line.lstrip(' ')
        indent = len(line) - len(stripped)
        if stripped.startswith('#>'):
            doc = (number, indent)
        target = changed is None or number in changed
        if not target:
            continue
        if stripped.startswith('#declare'):
            if doc is None:
                found.append(f'{number}行: `#declare` の上に対応するIMP Doc（`#>`）がない')
            elif indent != doc[1] + 4:
                found.append(f'{number}行: `#declare` は{doc[0]}行の `#>` より4スペース深くする'
                             f'（今は{indent}、期待は{doc[1] + 4}）')
            continue
        if stripped.startswith('#'):
            continue
        for kind, options, written in selectors(stripped.removeprefix('$')):
            keys = {key for key, _ in options}
            if kind == 'a' and ('sort', 'nearest') in options and ('limit', '1') in options:
                rest = [f'{key}={value}' for key, value in options if key not in ('sort', 'limit')]
                replacement = '@p' + (f'[{",".join(rest)}]' if rest else '')
                found.append(f'{number}行: `{written}` は `{replacement}` と同じ選択になる。`@p` で書く')
            elif kind == 'e' and not bounded(options) and not players_only(options):
                scope = ('実行中のディメンションのentityを' if keys & LOCATING
                         else '全ディメンションのentityを')
                # Without a sort, `limit=N` stops the search at N matches
                # (1.20.4 `EntitySelector#addEntities`).
                scope += ('見つかるまで調べる' if 'limit' in keys and dict(options).get('sort', 'arbitrary') == 'arbitrary'
                          else 'すべて調べる')
                noted.append(f'{number}行: `{written}` は dx/dy/dz も distance の上限もなく、'
                             f'{scope}。範囲を限定できないか確かめる')
    # Two equal selectors on one line give one message.
    return list(dict.fromkeys(found)), list(dict.fromkeys(noted))


def players_only(options):
    return any(key == 'type' and value in ('player', 'minecraft:player') for key, value in options)


def bounded(options):
    for key, value in options:
        if key in DELTAS:
            return True
        # `distance=5` and `distance=..5` have an upper bound; `distance=5..` does not.
        if key == 'distance' and value.partition('..')[2 if '..' in value else 0]:
            return True
    return False


def selectors(command):
    """Yield (kind, [(key, value)], written text) for each target selector in a command."""
    index = 0
    while (index := command.find('@', index)) != -1:
        kind = command[index + 1:index + 2]
        if kind not in ('a', 'e', 'p', 'r', 's') or command[index + 2:index + 3].isalnum():
            index += 1
            continue
        end = index + 2
        options = []
        if command[end:end + 1] == '[':
            close = closing_bracket(command, end)
            if close is None:
                return
            options = parse_options(command[end + 1:close])
            end = close + 1
        yield kind, options, command[index:end]
        index = end


def closing_bracket(text, opening):
    """Find the `]` that closes the bracket at `opening`, skipping nested values and quotes."""
    depth = 0
    for position, character, quoted in characters(text, opening):
        if quoted:
            continue
        if character in '[{':
            depth += 1
        elif character in ']}':
            depth -= 1
            if depth == 0:
                return position
    return None


def parse_options(body):
    """Split selector options at the top level into (key, value) pairs without spaces."""
    options, depth, start = [], 0, 0
    for position, character, quoted in characters(body + ',', 0):
        if quoted:
            continue
        if character in '[{':
            depth += 1
        elif character in ']}':
            depth -= 1
        elif character == ',' and depth == 0:
            key, _, value = body[start:position].partition('=')
            if key.strip():
                options.append((key.strip(), value.strip()))
            start = position + 1
    return options


def characters(text, start):
    """Yield each character with whether it lies inside a quoted string, quotes included."""
    quote, escaped = None, False
    for position in range(start, len(text)):
        character = text[position]
        if quote:
            if escaped:
                escaped = False
            elif character == '\\':
                escaped = True
            elif character == quote:
                quote = None
            yield position, character, True
        elif character in '"\'':
            quote = character
            yield position, character, True
        else:
            yield position, character, False


def report(root, base, scripts, findings, own, notes):
    print(f'# データパック検査: {repository_name(root)}（ブランチ {branch_name(root)}）')
    print()
    origin = f'`{base}` との共通祖先' if base else 'HEAD'
    print(f'- {origin}から変更した行を調べたmcfunction {len(scripts)}件')
    if own is None:
        print(f'- repo固有の検査（`{REPOSITORY_CHECK}`）はこの作業コピーにない')
    else:
        print(f'- repo固有の検査（`{REPOSITORY_CHECK}`）を実行した')
    print()
    for title, items in (('指摘', findings), ('repo固有の検査の指摘', own or {}), ('確認', notes)):
        if not items:
            continue
        print(f'## {title}')
        print()
        for path, messages in sorted(items.items()):
            print(f'- `{path}`')
            for message in messages:
                print(f'  - {message}')
        print()
    if not findings and not own:
        print('## 指摘なし')
        return
    total = sum(len(messages) for items in (findings, own or {}) for messages in items.values())
    print(f'合計 {total}件の指摘がある。')


if __name__ == '__main__':
    raise SystemExit(main())
