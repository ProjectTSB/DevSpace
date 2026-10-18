"""Checks that the INDEX reflects only the branch's headers and that findings are real."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts/knowledge'

# The throwaway repositories must not resolve to a working copy named by the caller's
# environment, such as a worktree opened through GIT_DIR from another mount path.
for variable in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR'):
    os.environ.pop(variable, None)


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Windows has no geteuid, and chmod cannot make a file unreadable there.
POSIX_PERMISSIONS = hasattr(os, 'geteuid') and os.geteuid() != 0

notes = load('notes')
index = load('index')
check = load('check')

NOTE = """---
title: {title}
description: {description}
area: {area}
---

# {title}

根拠と適用条件を書く。
"""


def write_link(path, text):
    """Write a `.git` link file; Git for Windows may leave an existing one read-only."""
    if path.exists():
        path.chmod(0o644)
    path.write_text(text, encoding='utf-8')


def git(root, *arguments):
    environment = dict(os.environ, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.com',
                       GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@example.com')
    return subprocess.run(('git', '-C', str(root)) + arguments, check=True,
                          capture_output=True, text=True, env=environment).stdout


class Workcopy:
    """A throwaway working copy with a knowledge directory and an origin remote name."""

    def __init__(self, stack, name='Asset'):
        self.root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        (self.root / 'docs/knowledge/notes').mkdir(parents=True)
        self.write('docs/knowledge/README.md', '# 入口\n')
        git(self.root, 'init', '--quiet', '--initial-branch=master')
        git(self.root, 'remote', 'add', 'origin', f'https://example.invalid/ProjectTSB/{name}.git')
        self.commit('初期ナレッジ')

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def note(self, relative, title='判定の見出し', description='どの作業で読むか', area='motion',
             related=None):
        text = NOTE.format(title=title, description=description, area=area)
        if related:
            text = text.replace('\n---\n', f'\nrelated:\n  - {related}\n---\n', 1)
        return self.write(relative, text)

    def area(self, name='mob.md'):
        """Add an area document that the entry's guide table routes to."""
        self.write(f'docs/knowledge/{name}',
                   NOTE.format(title=name, description='この領域を変更するときに読む', area=''))
        self.write('docs/knowledge/README.md', f'# 入口\n\n|目的|文書|\n|---|---|\n|領域|[{name}]({name})|\n')
        return f'docs/knowledge/{name}'

    def commit(self, subject, pushed=True):
        git(self.root, 'add', '--all')
        git(self.root, 'commit', '--quiet', '--message', subject)
        # A commit on master stands for one already pushed, so it becomes the default base.
        if pushed and git(self.root, 'branch', '--show-current').strip() == 'master':
            git(self.root, 'update-ref', 'refs/remotes/origin/master', 'HEAD')
            git(self.root, 'symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/master')

    def status(self):
        return git(self.root, 'status', '--porcelain=v1', '--untracked-files=all')


class IndexTest(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.copy = Workcopy(self.stack)

    def generate(self, *arguments):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = index.main([str(self.copy.root), *arguments])
        return code, output.getvalue()

    def test_notes_are_grouped_by_area_with_their_paths(self):
        self.copy.write('docs/knowledge/notes/motion/stop.md', """---
title: 慣性だけを消す
description: 移動停止を実装するときに読む
area: motion
paths:
  - docs/knowledge/README.md
related:
  - TheSkyBlessing:docs/knowledge/api-and-storage.md#libとapi
---

# 慣性だけを消す

同じ条件で二行を続ける。
""")
        self.copy.note('docs/knowledge/notes/geometry/ray.md',
                       title='標的を実行者にする', area='geometry')
        code, output = self.generate()
        self.assertEqual(code, 0)
        self.assertIn('# ナレッジINDEX: Asset', output)
        self.assertIn('ブランチ master', output)
        self.assertIn('ノート: motion（1件）', output)
        self.assertIn('ノート: geometry（1件）', output)
        self.assertIn('- path: `docs/knowledge/notes/motion/stop.md`', output)
        self.assertIn('移動停止を実装するときに読む', output)
        self.assertIn('TheSkyBlessing:docs/knowledge/api-and-storage.md#libとapi', output)

    def test_area_documents_are_listed_before_notes(self):
        self.copy.write('docs/knowledge/mob.md',
                        NOTE.format(title='Mob', description='Mobを変更するときに読む', area=''))
        self.copy.note('docs/knowledge/notes/motion/stop.md')
        code, output = self.generate()
        self.assertEqual(code, 0)
        self.assertLess(output.index('## 領域文書'), output.index('## ノート: motion'))

    def test_area_filter_narrows_notes_and_keeps_area_documents(self):
        self.copy.note('docs/knowledge/notes/motion/stop.md')
        self.copy.note('docs/knowledge/notes/geometry/ray.md', area='geometry')
        self.copy.write('docs/knowledge/mob.md',
                        NOTE.format(title='Mob', description='Mobを変更するときに読む', area=''))
        _, output = self.generate('--area', 'motion')
        self.assertIn('ノート: motion', output)
        self.assertNotIn('geometry', output)
        self.assertIn('## 領域文書（1件）', output)
        self.assertIn('docs/knowledge/mob.md', output)
        _, notes_only = self.generate('--notes-only')
        self.assertNotIn('## 領域文書', notes_only)

    def test_documents_without_a_header_keep_their_heading(self):
        self.copy.write('docs/knowledge/legacy.md', '# 旧い領域文書\n\n本文。\n')
        _, output = self.generate()
        self.assertIn('## ヘッダー未整備', output)
        self.assertIn('`docs/knowledge/legacy.md` — 旧い領域文書', output)

    def test_generation_leaves_the_working_copy_and_index_unchanged(self):
        self.copy.note('docs/knowledge/notes/motion/stop.md')
        self.copy.commit('ノートを追加')
        before = self.copy.status()
        self.generate()
        with contextlib.redirect_stdout(io.StringIO()):
            check.main([str(self.copy.root), '--all'])
        self.assertEqual(self.copy.status(), before)
        # Git's own `.git/index` matches `INDEX*` where names ignore case, as on Windows.
        self.assertFalse([path for path in self.copy.root.glob('**/INDEX*') if '.git' not in path.parts])

    def test_an_unknown_area_lists_the_existing_ones(self):
        self.copy.note('docs/knowledge/notes/motion/stop.md')
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            code = index.main([str(self.copy.root), '--area', 'motionn'])
        self.assertEqual(code, 2)
        self.assertIn('ある領域: motion', error.getvalue())

    def test_unreadable_documents_are_named_on_stderr(self):
        self.copy.note('docs/knowledge/notes/motion/stop.md')
        (self.copy.root / 'docs/knowledge/notes/motion/old.md').write_bytes('# 旧\n'.encode('shift_jis'))
        error = io.StringIO()
        with contextlib.redirect_stderr(error), contextlib.redirect_stdout(io.StringIO()):
            code = index.main([str(self.copy.root)])
        self.assertEqual(code, 0)
        self.assertIn('INDEXから除いた: docs/knowledge/notes/motion/old.md', error.getvalue())

    def test_an_unreadable_git_is_warned_without_stopping_the_index(self):
        self.copy.note('docs/knowledge/notes/motion/stop.md')
        (self.copy.root / '.git').rename(self.copy.root / 'git-moved')
        write_link(self.copy.root / '.git', 'gitdir: /nonexistent/worktrees/x\n')
        error, output = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(error), contextlib.redirect_stdout(output):
            code = index.main([str(self.copy.root)])
        self.assertEqual(code, 0)
        self.assertIn('Gitの作業コピーとして読めない', error.getvalue())
        self.assertIn('docs/knowledge/notes/motion/stop.md', output.getvalue())

    def test_missing_knowledge_directory_is_reported(self):
        empty = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            code = index.main([str(empty)])
        self.assertEqual(code, 2)
        self.assertIn('docs/knowledge/ がない', error.getvalue())


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.copy = Workcopy(self.stack)

    def run_check(self, *arguments):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = check.main([str(self.copy.root), *arguments])
        return code, output.getvalue()

    def findings(self, text):
        path = self.copy.write('docs/knowledge/notes/motion/case.md', text)
        document = notes.Document(self.copy.root, 'docs/knowledge/notes/motion/case.md')
        path.unlink()
        return notes.validate(document)

    def test_header_shape_problems_are_named_once(self):
        self.assertEqual(self.findings('# 見出しだけ\n\n本文。\n')[:1],
                         ['ヘッダーがない: 先頭行から `---` で囲んだ title・description を置く'])
        self.assertIn('ヘッダーの終端 `---` がない', self.findings('---\ntitle: a\n'))
        unknown = self.findings('---\ntitle: a\ndescription: b\nconfidence: high\n---\n\n# a\n\n本文。\n')
        self.assertTrue(any('使えないキー: confidence' in message for message in unknown))
        duplicate = self.findings('---\ntitle: a\ntitle: b\ndescription: c\n---\n\n# a\n\n本文。\n')
        self.assertTrue(any('キーが重複している: title' in message for message in duplicate))
        orphan = self.findings('---\ntitle: a\ndescription: b\n  - x\n---\n\n# a\n\n本文。\n')
        self.assertTrue(any('対応するリストのキーがない' in message for message in orphan))

    def test_required_fields_and_their_limits(self):
        self.assertIn('description が空である',
                      self.findings('---\ntitle: a\ndescription:\n---\n\n# a\n\n本文。\n'))
        long = 'あ' * (notes.DESCRIPTION_LIMIT + 1)
        self.assertTrue(any('description が長い' in message for message in
                            self.findings(f'---\ntitle: a\ndescription: {long}\n---\n\n# a\n\n本文。\n')))

    def test_body_must_correspond_to_the_header(self):
        mismatch = self.findings('---\ntitle: 正しい題\ndescription: b\n---\n\n# 別の題\n\n本文。\n')
        self.assertTrue(any('本文の見出しがヘッダーと違う' in message for message in mismatch))
        self.assertIn('本文が見出しだけである: 根拠と適用条件を残す',
                      self.findings('---\ntitle: a\ndescription: b\n---\n\n# a\n'))

    def test_references_must_resolve_in_the_same_working_copy(self):
        missing = self.findings("""---
title: a
description: b
paths:
  - Asset/data/missing.mcfunction
related:
  - docs/knowledge/absent.md#節
---

# a

[切れたリンク](../../absent.md) と [URL](https://example.invalid/page)。
""")
        self.assertTrue(any('paths の対象が作業コピーにない' in message for message in missing))
        self.assertTrue(any('related の参照先が作業コピーにない' in message for message in missing))
        self.assertTrue(any('本文のリンク先が作業コピーにない' in message for message in missing))
        self.assertFalse(any('example.invalid' in message for message in missing))

    def test_accepted_reference_forms(self):
        self.copy.write('docs/knowledge/mob.md', '# Mob\n')
        accepted = self.findings("""---
title: a
description: b
paths:
  - docs/knowledge/mob.md
related:
  - docs/knowledge/mob.md#装備の変更と見た目を分ける
  - TheSkyBlessing:docs/knowledge/api-and-storage.md
  - https://example.invalid/page
---

# a

[同じrepoの領域文書](../../mob.md) を読む。
""")
        self.assertEqual(accepted, [])
        absolute = self.findings('---\ntitle: a\ndescription: b\n---\n\n# a\n\n[絶対](/etc/hosts)\n')
        self.assertTrue(any('絶対パスを使っている' in message for message in absolute))

    def test_placement_and_naming_of_notes(self):
        self.copy.note('docs/knowledge/notes/motion/Stop_Note.md')
        code, output = self.run_check('--all')
        self.assertEqual(code, 1)
        self.assertIn('ノートのファイル名は英小文字・数字・ハイフンにする', output)
        self.copy.note('docs/knowledge/sub/deep.md', area='')
        _, output = self.run_check('--all')
        self.assertIn('docs/knowledge/ 直下か docs/knowledge/notes/ 配下に置く', output)

    def test_only_changed_documents_are_checked_by_default(self):
        self.copy.note('docs/knowledge/notes/motion/stop.md')
        self.copy.write('docs/knowledge/legacy.md', '# ヘッダーのない既存文書\n\n本文。\n')
        self.copy.commit('既存ナレッジ')
        code, output = self.run_check()
        self.assertEqual(code, 0)
        self.assertIn('## 指摘なし', output)
        self.copy.note('docs/knowledge/notes/motion/stop.md', title='題', description='')
        code, output = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('docs/knowledge/notes/motion/stop.md', output)
        self.assertNotIn('legacy.md', output)

    def test_base_adds_the_committed_difference(self):
        area = self.copy.area()
        self.copy.commit('領域文書')
        git(self.copy.root, 'checkout', '--quiet', '-b', 'work')
        self.copy.note('docs/knowledge/notes/motion/stop.md', related=area)
        self.copy.commit('ノートを追加')
        git(self.copy.root, 'branch', 'origin-base', 'HEAD~1')
        code, output = self.run_check('--base', 'origin-base')
        self.assertEqual(code, 0, output)
        self.copy.note('docs/knowledge/notes/motion/stop.md', description='', related=area)
        self.copy.commit('ノートを壊す')
        code, output = self.run_check('--base', 'origin-base')
        self.assertEqual(code, 1)
        self.assertIn('description が空である', output)

    def test_paths_outside_the_working_copy_are_refused(self):
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            code = check.main([str(self.copy.root), '../elsewhere.md'])
        self.assertEqual(code, 2)
        self.assertIn('作業コピーの外のパスは検査できない', error.getvalue())

    def test_an_unresolvable_base_is_refused_instead_of_looking_empty(self):
        self.copy.note('docs/knowledge/notes/motion/stop.md', description='')
        self.copy.commit('説明のないノート')
        code, output = self.run_check('--base', 'origin/absent')
        self.assertEqual(code, 2)
        self.assertIn('差分の基準 origin/absent を使えない', output)

    def test_duplicate_titles_in_one_working_copy_are_reported(self):
        self.copy.note('docs/knowledge/notes/motion/stop.md', title='同じ題')
        self.copy.note('docs/knowledge/notes/motion/copy.md', title='同じ題')
        code, output = self.run_check('--all')
        self.assertEqual(code, 1)
        self.assertIn('title が他の文書と重複している', output)
        self.assertIn('docs/knowledge/notes/motion/copy.md', output)

    def test_area_must_match_where_the_note_is_stored(self):
        self.copy.note('docs/knowledge/notes/motion/stop.md', area='geometry')
        code, output = self.run_check('--all')
        self.assertEqual(code, 1)
        self.assertIn('area が置き場所と違う', output)

    def test_changes_with_non_ascii_names_are_not_skipped(self):
        self.copy.note('docs/knowledge/notes/motion/ノート.md')
        code, output = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('ノート.md', output)
        self.assertIn('ノートのファイル名は英小文字・数字・ハイフンにする', output)

    def test_protected_changes_are_listed_without_becoming_findings(self):
        self.copy.write('docs/knowledge/README.md', '# 入口\n\n変更した。\n')
        code, output = self.run_check()
        self.assertEqual(code, 0)
        self.assertIn('## 保護対象の変更', output)
        self.assertIn('`docs/knowledge/README.md`', output)
        self.assertIn('人のマージを待つ', output)

    def publish_default_branch(self):
        """Point origin/HEAD at the current commit, as a clone of the remote would."""
        git(self.copy.root, 'update-ref', 'refs/remotes/origin/master', 'HEAD')
        git(self.copy.root, 'symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/master')

    def test_committed_changes_are_checked_without_naming_a_base(self):
        self.publish_default_branch()
        git(self.copy.root, 'checkout', '--quiet', '-b', 'work')
        self.copy.write('docs/knowledge/notes/motion/stop.md',
                        NOTE.format(title='停止', description='', area='motion'))
        self.copy.commit('ノート')
        code, output = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('`origin/HEAD` との共通祖先からの差分', output)
        self.assertIn('description が空である', output)

    def test_without_a_default_branch_the_check_stops_instead_of_passing(self):
        git(self.copy.root, 'update-ref', '-d', 'refs/remotes/origin/HEAD')
        git(self.copy.root, 'update-ref', '-d', 'refs/remotes/origin/master')
        code, output = self.run_check()
        self.assertEqual(code, 2)
        self.assertIn('既定ブランチ（origin/HEAD・origin/main・origin/master）がない。--base <ref> を渡す', output)
        # Checking every document does not depend on a base and still runs.
        code, output = self.run_check('--all')
        self.assertEqual(code, 0, output)
        self.assertIn('差分の基準がないため、変更は未コミットのものだけを集めた', output)
        git(self.copy.root, 'update-ref', 'refs/remotes/origin/main', 'HEAD')
        code, output = self.run_check()
        self.assertEqual(code, 0, output)
        self.assertIn('`origin/main` との共通祖先からの差分', output)

    def test_staged_changes_on_the_default_branch_are_findings(self):
        self.copy.write('docs/knowledge/README.md', '# 入口\n\n変更した。\n')
        self.copy.write('CLAUDE.local.md', '# 個人の設定\n')
        # Unstaged and untracked files may belong to someone else in the same copy.
        code, output = self.run_check()
        self.assertEqual(code, 0, output)
        self.assertIn('## 保護対象の変更', output)
        git(self.copy.root, 'add', 'docs/knowledge/README.md')
        code, output = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('- `docs/knowledge/README.md`\n  - 既定ブランチ master の上で変更をstage・commitしている', output)
        self.assertNotIn('CLAUDE.local.md`\n  - 既定ブランチ', output)
        git(self.copy.root, 'checkout', '--quiet', '-b', 'work')
        self.assertEqual(self.run_check()[0], 0)

    def test_devspace_main_takes_only_shared_knowledge_documents(self):
        self.copy.write('docs/knowledge-maintenance.md', '# 配置\n')
        self.copy.commit('DevSpace')
        for path in ('docs/terminology.md', 'scripts/server.sh', 'AGENTS.md'):
            self.copy.write(path, '変更した\n')
        git(self.copy.root, 'add', '--all')
        code, output = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('- `scripts/server.sh`\n  - 既定ブランチ master の上で共通知識の文書以外を変更している', output)
        self.assertIn('- `AGENTS.md`\n  - 既定ブランチ master の上で保護対象を変更している', output)
        self.assertNotIn('- `docs/terminology.md`\n  - 既定ブランチ', output)

    def test_unpushed_commits_on_devspace_main_are_findings(self):
        self.copy.write('docs/knowledge-maintenance.md', '# 配置\n')
        self.copy.commit('DevSpace')
        self.copy.write('docs/tool.sh', '#!/bin/sh\n')
        self.copy.write('docs/terminology.md', '# 用語\n')
        self.copy.commit('push前', pushed=False)
        code, output = self.run_check()
        self.assertEqual(code, 1, output)
        self.assertIn('- `docs/tool.sh`\n  - 既定ブランチ master の上で共通知識の文書以外を変更している', output)
        self.assertNotIn('- `docs/terminology.md`\n  - 既定ブランチ', output)

    def test_the_devspace_table_is_compared_with_the_branch_own_lists(self):
        self.copy.write('docs/knowledge-maintenance.md', '# 配置\n')
        added = ('scripts/new.sh',)
        devspace, child = notes.DEVSPACE_PROTECTED + added, notes.CHILD_PROTECTED
        def row(name, paths):
            return f'| {name} | ' + '、'.join(f'`{path}`' for path in paths) + ' |'
        self.copy.write('docs/knowledge-notes.md', '\n'.join(
            ['| repo | 保護対象 |', '| --- | --- |', row('DevSpace', devspace),
             row('Asset・TheSkyBlessing', child)]) + '\n')
        self.copy.write('scripts/knowledge/notes.py', f'DEVSPACE_PROTECTED = {devspace!r}\nCHILD_PROTECTED = {child!r}\n')
        git(self.copy.root, 'checkout', '--quiet', '-b', 'work')
        # The script running here does not list scripts/new.sh; the branch under check does.
        self.assertNotIn('の一覧と違う', self.run_check()[1])

    def test_a_move_on_devspace_main_counts_its_source(self):
        self.copy.write('docs/knowledge-maintenance.md', '# 配置\n')
        self.copy.write('scripts/server.sh', '#!/bin/sh\n')
        self.copy.commit('DevSpace')
        git(self.copy.root, 'mv', 'scripts/server.sh', 'docs/server.sh')
        code, output = self.run_check()
        self.assertEqual(code, 1, output)
        self.assertIn('- `scripts/server.sh`\n  - 既定ブランチ master の上で共通知識の文書以外を変更している', output)

    def test_an_untouched_workflow_is_not_asked_to_follow_the_lists(self):
        self.copy.write('.github/workflows/auto-merge-docs-tests.yml', "const protectedPaths = ['AGENTS.md'];\n")
        self.copy.commit('古いworkflow')
        git(self.copy.root, 'checkout', '--quiet', '-b', 'work')
        self.copy.note('docs/knowledge/notes/motion/stop.md', related=self.copy.area())
        code, output = self.run_check()
        self.assertNotIn('の一覧と違う', output)
        self.assertIn('の一覧と違う', self.run_check('--all')[1])

    def test_nested_instruction_files_are_protected_in_any_case(self):
        for path in ('docs/knowledge/notes/CLAUDE.md', 'docs/.claude/rules/reading.md',
                     'tests/AGENTS.md', 'docs/knowledge/readme.md', 'docs/CLAUDE.local.md'):
            self.assertEqual(notes.protected_hits(self.copy.root, [path]), [path], path)
        self.assertEqual(notes.protected_hits(self.copy.root, ['docs/claude-notes.md']), [])

    def test_a_workflow_protecting_other_paths_is_a_finding(self):
        def workflow(paths, names):
            listed = ', '.join(f"'{value}'" for value in paths)
            named = ', '.join(f"'{value}'" for value in names)
            self.copy.write('.github/workflows/auto-merge-docs-tests.yml',
                            f'const protectedPaths = [{listed}];\n'
                            f'return [{named}].includes(parts.at(-1));\n')
        git(self.copy.root, 'checkout', '--quiet', '-b', 'work')
        workflow(notes.CHILD_PROTECTED[:-1], notes.INSTRUCTION_NAMES[:-1])
        code, output = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('`protectedPaths` が DevSpace の scripts/knowledge/notes.py の一覧と違う', output)
        self.assertIn('指示ファイルの名前の一覧 が DevSpace の scripts/knowledge/notes.py の一覧と違う', output)
        workflow(notes.CHILD_PROTECTED, notes.INSTRUCTION_NAMES)
        self.assertNotIn('の一覧と違う', self.run_check()[1])

    def test_the_devspace_table_must_list_the_same_protected_paths(self):
        self.copy.write('docs/knowledge-maintenance.md', '# 配置\n')
        rows = {'DevSpace': notes.DEVSPACE_PROTECTED, 'Asset・TheSkyBlessing': notes.CHILD_PROTECTED}
        def table(missing=None):
            lines = ['| repo | 保護対象 |', '| --- | --- |']
            for name, paths in rows.items():
                kept = [path for path in paths if path != missing]
                lines.append(f'| {name} | ' + '、'.join(f'`{path}`' for path in kept) + ' |')
            return '\n'.join(lines) + '\n'
        self.copy.write('docs/knowledge-notes.md', table())
        self.assertNotIn('の一覧と違う', self.run_check()[1])
        self.copy.write('docs/knowledge-notes.md', table(missing='scripts/lib/workcopy.py'))
        code, output = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('人がマージする範囲の表の DevSpace の行が scripts/knowledge/notes.py の一覧と違う', output)

    def test_deleting_a_note_reports_documents_still_linking_to_it(self):
        self.copy.note('docs/knowledge/notes/motion/stop.md')
        self.copy.write('docs/knowledge/mob.md', NOTE.format(
            title='Mob', description='Mobを変更するときに読む', area='')
            + '\n[停止](notes/motion/stop.md#節) を参照する。\n')
        self.copy.write('docs/knowledge/README.md', '# 入口\n\n[Mob](mob.md)\n')
        self.copy.commit('ノートと参照元')
        (self.copy.root / 'docs/knowledge/notes/motion/stop.md').unlink()
        code, output = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('削除・移動したファイル 1件', output)
        self.assertIn('`docs/knowledge/mob.md`', output)
        self.assertIn('削除・移動したファイルを参照している: notes/motion/stop.md#節', output)

    def test_renames_and_committed_deletions_are_traced_from_the_base(self):
        self.copy.note('docs/knowledge/notes/motion/stop.md')
        self.copy.note('docs/knowledge/notes/geometry/ray.md', title='レイ', area='geometry')
        self.copy.write('docs/knowledge/notes/geometry/link.md', NOTE.format(
            title='参照元', description='どの作業で読むか', area='geometry')
            + '\n[停止](../motion/stop.md)、[レイ](ray.md)\n')
        self.copy.commit('ノートと参照元')
        git(self.copy.root, 'branch', 'origin-base')
        git(self.copy.root, 'mv', 'docs/knowledge/notes/geometry/ray.md',
            'docs/knowledge/notes/geometry/ray-target.md')
        git(self.copy.root, 'rm', '--quiet', 'docs/knowledge/notes/motion/stop.md')
        self.copy.commit('移動と削除')
        code, output = self.run_check('--base', 'origin-base')
        self.assertEqual(code, 1)
        self.assertIn('削除・移動したファイルを参照している: ../motion/stop.md', output)
        self.assertIn('削除・移動したファイルを参照している: ray.md', output)

    def test_entry_links_and_its_guide_to_area_documents_are_checked(self):
        self.copy.write('docs/knowledge/mob.md',
                        NOTE.format(title='Mob', description='Mobを変更するときに読む', area=''))
        code, output = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('領域文書が入口の案内表にない: `docs/knowledge/mob.md`', output)
        # A link outside the table does not route the reader to the area document.
        self.copy.write('docs/knowledge/README.md', '# 入口\n\n先に [Mob](mob.md) を読む。\n')
        _, output = self.run_check()
        self.assertIn('領域文書が入口の案内表にない: `docs/knowledge/mob.md`', output)
        self.copy.write('docs/knowledge/README.md',
                        '# 入口\n\n|目的|文書|\n|---|---|\n|Mob|[Mob](./mob.md)|\n\n[切れた](absent.md)\n')
        code, output = self.run_check()
        self.assertEqual(code, 1)
        self.assertNotIn('案内表にない', output)
        self.assertIn('本文のリンク先が作業コピーにない: absent.md', output)
        # The guide is checked from file names, so an area document that is not UTF-8
        # still has to be routed.
        (self.copy.root / 'docs/knowledge/item.md').write_bytes('# 道具\n'.encode('shift_jis'))
        _, output = self.run_check('docs/knowledge/README.md')
        self.assertIn('領域文書が入口の案内表にない: `docs/knowledge/item.md`', output)

    def test_changing_an_area_document_also_checks_the_entry_links(self):
        self.copy.write('docs/knowledge/mob.md',
                        NOTE.format(title='Mob', description='Mobを変更するときに読む', area=''))
        self.copy.write('docs/knowledge/README.md',
                        '# 入口\n\n|目的|文書|\n|---|---|\n|Mob|[Mob](mob.md)|\n\n[切れた](absent.md)\n')
        self.copy.commit('入口と領域文書')
        self.copy.write('docs/knowledge/mob.md',
                        NOTE.format(title='Mob', description='Mobを扱うときに読む', area=''))
        code, output = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('本文のリンク先が作業コピーにない: absent.md', output)

    def test_a_removed_directory_breaks_paths_that_name_it(self):
        self.copy.write('data/weather/is_sunny.json', '{}')
        self.copy.write('data/weather/is_raining.json', '{}')
        self.copy.write('docs/knowledge/notes/predicate/weather.md', """---
title: 天候
description: 天候で発動する機能を実装するときに読む
area: predicate
paths:
  - data/weather
---

# 天候

根拠と適用条件を書く。
""")
        self.copy.commit('天候のノート')
        (self.copy.root / 'data/weather/is_raining.json').unlink()
        code, output = self.run_check()
        self.assertEqual(code, 0)
        (self.copy.root / 'data/weather/is_sunny.json').unlink()
        code, output = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('削除・移動したファイルを参照している: data/weather', output)

    def test_all_and_named_paths_keep_their_own_scope(self):
        self.copy.note('docs/knowledge/notes/motion/stop.md', related=self.copy.area())
        self.copy.note('docs/knowledge/notes/motion/gone.md', title='消す')
        self.copy.write('docs/knowledge/notes/motion/link.md', NOTE.format(
            title='参照元', description='どの作業で読むか', area='motion') + '\n[消す](gone.md)\n')
        self.copy.commit('ノート')
        (self.copy.root / 'docs/knowledge/notes/motion/gone.md').unlink()
        self.copy.write('docs/knowledge/README.md', '# 入口\n\n変更した。\n')
        code, output = self.run_check('--all')
        self.assertEqual(code, 1)
        self.assertIn('## 保護対象の変更', output)
        # The validated note reports its broken link once, not again from the removal scan.
        self.assertIn('本文のリンク先が作業コピーにない: gone.md', output)
        self.assertNotIn('削除・移動したファイルを参照している: gone.md', output)
        code, output = self.run_check('docs/knowledge/notes/motion/stop.md')
        self.assertEqual(code, 0)
        self.assertNotIn('削除・移動', output)
        self.assertNotIn('## 保護対象の変更', output)

    def test_unreadable_documents_fail_the_removal_scan(self):
        self.copy.note('docs/knowledge/notes/motion/gone.md')
        self.copy.commit('ノート')
        (self.copy.root / 'legacy.md').write_bytes('# 旧文書\n'.encode('shift_jis'))
        # Without a removal the file outside the knowledge is not read at all.
        code, _ = self.run_check()
        self.assertEqual(code, 0)
        (self.copy.root / 'docs/knowledge/notes/motion/gone.md').unlink()
        code, output = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('- `legacy.md`', output)
        self.assertIn('削除・移動したファイルへの参照を確認できない', output)
        self.assertNotIn('## 指摘なし', output)

    def test_an_unreadable_knowledge_document_is_reported_once_with_a_removal(self):
        self.copy.note('docs/knowledge/notes/motion/gone.md')
        self.copy.commit('ノート')
        (self.copy.root / 'docs/knowledge/notes/motion/gone.md').unlink()
        (self.copy.root / 'docs/knowledge/notes/motion/old.md').write_bytes(
            '---\ntitle: 旧\n---\n'.encode('shift_jis'))
        code, output = self.run_check()
        self.assertEqual(code, 1)
        self.assertEqual(output.count('UTF-8 として読めない'), 1)
        self.assertIn('合計 1件', output)

    def test_an_unreadable_entry_is_reported_once_with_a_removal(self):
        self.copy.write('docs/knowledge/mob.md',
                        NOTE.format(title='Mob', description='Mobを変更するときに読む', area=''))
        self.copy.commit('領域文書')
        (self.copy.root / 'docs/knowledge/README.md').write_bytes('# 入口\n'.encode('shift_jis'))
        (self.copy.root / 'docs/knowledge/mob.md').unlink()
        code, output = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('合計 1件', output)

    def test_a_missing_entry_is_a_finding_while_area_documents_remain(self):
        self.copy.write('docs/knowledge/mob.md',
                        NOTE.format(title='Mob', description='Mobを変更するときに読む', area=''))
        self.copy.write('docs/knowledge/README.md', '# 入口\n\n|目的|文書|\n|---|---|\n|Mob|[Mob](mob.md)|\n')
        self.copy.commit('入口と領域文書')
        (self.copy.root / 'docs/knowledge/README.md').unlink()
        code, output = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('入口がなく、領域文書を案内表から辿れない', output)
        self.copy.commit('入口を削除')
        code, output = self.run_check('--all')
        self.assertEqual(code, 1)
        self.assertIn('入口がなく、領域文書を案内表から辿れない', output)

    @unittest.skipIf(not POSIX_PERMISSIONS, 'needs POSIX permissions that bind a non-root user')
    def test_an_unreadable_directory_stops_the_check(self):
        self.copy.note('docs/knowledge/notes/motion/gone.md')
        self.copy.write('guides/ref.md', '# 参照\n\n[旧](../docs/knowledge/notes/motion/gone.md)\n')
        self.copy.commit('ノートと参照元')
        (self.copy.root / 'docs/knowledge/notes/motion/gone.md').unlink()
        guides = self.copy.root / 'guides'
        guides.chmod(0)
        try:
            code, output = self.run_check()
        finally:
            guides.chmod(0o755)
        self.assertEqual(code, 2)
        self.assertIn('検査を続けられない', output)

    def test_a_failing_git_query_stops_instead_of_finding_nothing(self):
        self.copy.note('docs/knowledge/notes/motion/stop.md')
        # A truncated index still resolves the work tree but fails the status query.
        (self.copy.root / '.git/index').write_bytes(b'DIRC')
        code, output = self.run_check()
        self.assertEqual(code, 2)
        self.assertIn('gitで変更やファイルの一覧を読めない', output)
        self.assertNotIn('## 指摘なし', output)

    @unittest.skipIf(not POSIX_PERMISSIONS, 'needs POSIX permissions that bind a non-root user')
    def test_a_file_that_cannot_be_opened_is_a_finding(self):
        self.copy.note('docs/knowledge/notes/motion/gone.md')
        self.copy.commit('ノート')
        (self.copy.root / 'docs/knowledge/notes/motion/gone.md').unlink()
        locked = self.copy.root / 'locked.md'
        locked.write_text('# 開けない\n', encoding='utf-8')
        locked.chmod(0)
        try:
            code, output = self.run_check()
        finally:
            locked.chmod(0o644)
        self.assertEqual(code, 1)
        self.assertIn('- `locked.md`', output)
        self.assertIn('開けないか、UTF-8 として読めない', output)

    def test_unreadable_knowledge_documents_are_findings_in_every_mode(self):
        self.copy.note('docs/knowledge/notes/motion/stop.md')
        self.copy.commit('ノート')
        (self.copy.root / 'docs/knowledge/notes/motion/old.md').write_bytes(
            '---\ntitle: 旧\n---\n'.encode('shift_jis'))
        for arguments in ((), ('--all',), ('docs/knowledge/notes/motion/old.md',)):
            code, output = self.run_check(*arguments)
            self.assertEqual(code, 1, arguments)
            self.assertIn('UTF-8 として読めない', output)
            self.assertNotIn('作業コピーの外', output)

    def test_named_paths_may_follow_options_and_list_only_changed_protected_files(self):
        self.copy.note('docs/knowledge/notes/motion/stop.md')
        self.copy.commit('ノート')
        git(self.copy.root, 'branch', 'origin-base')
        code, output = self.run_check('--base', 'origin-base', 'docs/knowledge/README.md')
        self.assertEqual(code, 0)
        self.assertNotIn('## 保護対象の変更', output)
        self.copy.write('docs/knowledge/README.md', '# 入口\n\n変更した。\n')
        code, output = self.run_check('docs/knowledge/README.md', '--base', 'origin-base')
        self.assertEqual(code, 0)
        self.assertIn('## 保護対象の変更', output)

    def test_a_deleted_area_document_is_reported_once_on_the_entry(self):
        self.copy.write('docs/knowledge/mob.md',
                        NOTE.format(title='Mob', description='Mobを変更するときに読む', area=''))
        self.copy.write('docs/knowledge/README.md',
                        '# 入口\n\n|目的|文書|\n|---|---|\n|Mob|[Mob](mob.md)|\n')
        self.copy.commit('入口と領域文書')
        (self.copy.root / 'docs/knowledge/mob.md').unlink()
        code, output = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('本文のリンク先が作業コピーにない: mob.md', output)
        self.assertNotIn('削除・移動したファイルを参照している: mob.md', output)

    def test_ids_name_their_category_and_exist_in_the_asset_datapack(self):
        self.copy.write('Asset/data/asset/functions/object/1068.icicle/hit.mcfunction', '')
        self.copy.area()
        typed = self.findings('---\ntitle: a\ndescription: b\nids:\n  - object:1068\n'
                              'related:\n  - docs/knowledge/mob.md\n---\n\n# a\n\n本文。\n')
        self.assertEqual(typed, [])
        bare = self.findings('---\ntitle: a\ndescription: b\nids:\n  - 1068\n---\n\n# a\n\n本文。\n')
        self.assertTrue(any('ids は `<種別>:<ID>` で書く' in message for message in bare))
        absent = self.findings('---\ntitle: a\ndescription: b\nids:\n  - object:1069\n  - artefact:1068\n---\n\n# a\n\n本文。\n')
        self.assertTrue(any('ids の対象が作業コピーにない: object:1069' in message for message in absent))
        self.assertTrue(any('ids の種別が' in message for message in absent))

    def test_an_emptied_directory_linked_from_the_entry_is_reported(self):
        self.copy.write('docs/knowledge/mob.md',
                        NOTE.format(title='Mob', description='Mobを変更するときに読む', area=''))
        self.copy.note('docs/knowledge/notes/motion/stop.md')
        self.copy.write('docs/knowledge/README.md',
                        '# 入口\n\n|目的|文書|\n|---|---|\n|Mob|[Mob](mob.md)|\n\n[移動](notes/motion/)\n')
        self.copy.commit('入口とノート')
        (self.copy.root / 'docs/knowledge/notes/motion/stop.md').unlink()
        self.copy.write('docs/knowledge/README.md',
                        '# 入口\n\n|目的|文書|\n|---|---|\n|Mob|[Mob](mob.md)|\n\n[移動](notes/motion/)。\n')
        code, output = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('削除・移動したファイルを参照している: notes/motion/', output)

    def test_only_markdown_under_the_knowledge_directory_is_a_document(self):
        self.copy.write('docs/knowledge/notes/motion/figure.png', '\x89PNG')
        code, output = self.run_check()
        self.assertEqual(code, 0)
        self.assertIn('検査したナレッジ文書 0件', output)

    def test_a_named_path_that_does_not_exist_is_refused(self):
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            code = check.main([str(self.copy.root), 'docs/knowledge/notes/motion/typo.md'])
        self.assertEqual(code, 2)
        self.assertIn('指定したファイルがない', error.getvalue())

    def test_git_that_points_elsewhere_or_fails_stops_the_check(self):
        other = Workcopy(self.stack, name='TheSkyBlessing')
        self.copy.note('docs/knowledge/notes/motion/stop.md', description='')
        saved = {key: os.environ.get(key) for key in ('GIT_DIR', 'GIT_WORK_TREE')}
        os.environ['GIT_DIR'] = str(other.root / '.git')
        os.environ['GIT_WORK_TREE'] = str(other.root)
        try:
            code, output = self.run_check()
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        self.assertEqual(code, 2)
        self.assertIn('git が別の作業ツリー', output)
        broken = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        write_link(broken / '.git', 'gitdir: /nonexistent/worktrees/x\n')
        (broken / 'docs/knowledge').mkdir(parents=True)
        error = io.StringIO()
        with contextlib.redirect_stderr(error), contextlib.redirect_stdout(io.StringIO()):
            code = check.main([str(broken)])
        self.assertEqual(code, 2)
        self.assertIn('Gitの作業コピーとして読めない', error.getvalue())

    def test_git_dir_alone_naming_another_repository_stops_the_check(self):
        other = Workcopy(self.stack, name='TheSkyBlessing')
        saved = os.environ.get('GIT_DIR')
        os.environ['GIT_DIR'] = str(other.root / '.git')
        try:
            output = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                code = check.main([str(self.copy.root)])
        finally:
            if saved is None:
                os.environ.pop('GIT_DIR', None)
            else:
                os.environ['GIT_DIR'] = saved
        self.assertEqual(code, 2)
        self.assertIn('git が別のリポジトリ', output.getvalue())

    def test_a_base_without_common_history_is_refused(self):
        git(self.copy.root, 'checkout', '--quiet', '--orphan', 'unrelated')
        self.copy.commit('無関係な履歴')
        git(self.copy.root, 'checkout', '--quiet', 'master')
        code, output = self.run_check('--base', 'unrelated')
        self.assertEqual(code, 2)
        self.assertIn('HEADと共通の祖先', output)

    def test_ids_are_checked_for_shape_outside_asset(self):
        self.copy.area()
        self.assertEqual(self.findings(
            '---\ntitle: a\ndescription: b\nids:\n  - mob:0392\nrelated:\n  - docs/knowledge/mob.md\n'
            '---\n\n# a\n\n本文。\n'), [])
        self.assertTrue(any('ids は `<種別>:<ID>` で書く' in message for message in self.findings(
            '---\ntitle: a\ndescription: b\nids:\n  - 0392\n---\n\n# a\n\n本文。\n')))

    def test_a_worktree_from_another_environment_is_read_through_both_variables(self):
        git(self.copy.root, 'worktree', 'add', '--quiet', '-b', 'side', str(self.copy.root) + '-side')
        side = Path(str(self.copy.root) + '-side')
        self.stack.callback(lambda: subprocess.run(('rm', '-rf', str(side))))
        admin = self.copy.root / '.git/worktrees' / side.name
        # The other environment keeps the same worktree name under its own repository path.
        write_link(side / '.git', f'gitdir: /home/elsewhere/.git/worktrees/{side.name}\n')
        (side / 'docs/knowledge/notes/motion').mkdir(parents=True, exist_ok=True)
        note_path = side / 'docs/knowledge/notes/motion/stop.md'
        note_path.write_text(NOTE.format(title='停止', description='', area='motion'), encoding='utf-8')

        def run_through(git_dir):
            saved = {key: os.environ.get(key) for key in ('GIT_DIR', 'GIT_WORK_TREE')}
            os.environ['GIT_DIR'], os.environ['GIT_WORK_TREE'] = str(git_dir), str(side)
            try:
                output = io.StringIO()
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                    code = check.main([str(side)])
            finally:
                for key, value in saved.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
            return code, output.getvalue()

        code, output = run_through(admin)
        self.assertEqual(code, 1, output)
        self.assertIn('ブランチ side', output)
        self.assertIn('description が空である', output)
        # Naming the main repository instead of the worktree would compare another branch.
        code, output = run_through(self.copy.root / '.git')
        self.assertEqual(code, 2, output)
        self.assertIn('git が別のリポジトリ', output)

    def test_a_non_utf8_console_still_reads_and_writes_japanese(self):
        self.copy.note('docs/knowledge/notes/motion/stop.md')
        # A Japanese branch name passes through git's output and the console. The C locale
        # without UTF-8 fallbacks reads and writes ASCII, as cp932 cannot hold UTF-8; unlike
        # Windows it also cannot open Japanese file names, so the names here stay ASCII.
        git(self.copy.root, 'checkout', '--quiet', '-b', '作業')
        environment = dict(os.environ, LC_ALL='C', PYTHONUTF8='0', PYTHONCOERCECLOCALE='0',
                           PYTHONIOENCODING='')
        for script, expected in (('check.py', 'ブランチ 作業'), ('index.py', '判定の見出し')):
            result = subprocess.run([sys.executable, str(SCRIPTS / script), str(self.copy.root)],
                                    capture_output=True, env=environment)
            self.assertIn(result.returncode, (0, 1), result.stderr.decode('utf-8', 'replace'))
            self.assertIn(expected, result.stdout.decode('utf-8'), script)

    def test_notes_name_an_area_document_and_can_be_listed_from_it(self):
        area = self.copy.area()
        self.copy.note('docs/knowledge/notes/motion/stop.md', related=area)
        self.copy.note('docs/knowledge/notes/motion/lost.md', title='迷子')
        code, output = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('- `docs/knowledge/notes/motion/lost.md`\n  - related に関係する領域文書', output)
        self.assertNotIn('stop.md`\n  - related', output)
        listed = io.StringIO()
        with contextlib.redirect_stdout(listed):
            self.assertEqual(index.main([str(self.copy.root), '--for', 'mob.md']), 0)
        self.assertIn('notes/motion/stop.md', listed.getvalue())
        self.assertNotIn('notes/motion/lost.md', listed.getvalue())
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(index.main([str(self.copy.root), '--for', 'absent.md']), 2)

    def test_ids_must_match_the_directory_digits(self):
        self.copy.write('Asset/data/asset/functions/mob/0392.ecual_first/tick.mcfunction', '')
        short = self.findings('---\ntitle: a\ndescription: b\nids:\n  - mob:392\n---\n\n# a\n\n本文。\n')
        self.assertTrue(any('ids の対象が作業コピーにない: mob:392' in message for message in short))

    def test_byte_order_marks_and_markdown_named_directories_are_tolerated(self):
        (self.copy.root / 'docs/knowledge/notes/motion').mkdir(parents=True)
        area = self.copy.area()
        (self.copy.root / 'docs/knowledge/notes/motion/bom.md').write_bytes(
            NOTE.format(title='BOM', description='どの作業で読むか', area='motion')
            .replace('\n---\n', f'\nrelated:\n  - {area}\n---\n', 1).encode('utf-8-sig'))
        (self.copy.root / 'docs/knowledge/notes/motion/folder.md').mkdir()
        code, output = self.run_check('--all')
        self.assertEqual(code, 0, output)
        self.assertIn('## 指摘なし', output)

    def test_area_documents_do_not_declare_an_area(self):
        self.copy.write('docs/knowledge/mob.md',
                        NOTE.format(title='Mob', description='Mobを変更するときに読む', area='motion'))
        self.copy.write('docs/knowledge/README.md',
                        '# 入口\n\n|目的|文書|\n|---|---|\n|Mob|[Mob](mob.md)|\n')
        code, output = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('area はノートにだけ書く', output)

    def test_base_difference_keeps_non_ascii_names(self):
        git(self.copy.root, 'branch', 'origin-base')
        self.copy.note('docs/knowledge/notes/motion/ノート.md')
        self.copy.commit('名前の誤ったノート')
        code, output = self.run_check('--base', 'origin-base')
        self.assertEqual(code, 1)
        self.assertIn('ノートのファイル名は英小文字・数字・ハイフンにする', output)

    def test_devspace_and_child_repositories_protect_different_paths(self):
        self.assertIn('docs/knowledge/README.md', notes.protected_paths(self.copy.root))
        devspace = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        (devspace / 'docs').mkdir()
        (devspace / 'docs/knowledge-maintenance.md').write_text('x', encoding='utf-8')
        self.assertIn('AGENTS.md', notes.protected_paths(devspace))
        self.assertEqual(notes.protected_hits(devspace, ['scripts/knowledge/index.py', 'README.md']),
                         ['scripts/knowledge/index.py'])
        self.assertEqual(notes.protected_hits(self.copy.root, ['docs/knowledge/notes/a/b.md']), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
