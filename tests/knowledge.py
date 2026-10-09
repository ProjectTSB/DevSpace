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


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


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

    def note(self, relative, title='判定の見出し', description='どの作業で読むか', area='motion'):
        return self.write(relative, NOTE.format(title=title, description=description, area=area))

    def commit(self, subject):
        git(self.root, 'add', '--all')
        git(self.root, 'commit', '--quiet', '--message', subject)

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

    def test_filters_narrow_the_result_to_one_area(self):
        self.copy.note('docs/knowledge/notes/motion/stop.md')
        self.copy.note('docs/knowledge/notes/geometry/ray.md', area='geometry')
        self.copy.write('docs/knowledge/mob.md',
                        NOTE.format(title='Mob', description='Mobを変更するときに読む', area=''))
        _, output = self.generate('--area', 'motion')
        self.assertIn('ノート: motion', output)
        self.assertNotIn('geometry', output)
        self.assertNotIn('## 領域文書', output)
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
        self.assertFalse(list(self.copy.root.glob('**/INDEX*')))

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
        with contextlib.redirect_stdout(output):
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
        self.copy.note('docs/knowledge/notes/motion/stop.md')
        self.copy.commit('ノートを追加')
        git(self.copy.root, 'branch', 'origin-base', 'HEAD~1')
        code, output = self.run_check('--base', 'origin-base')
        self.assertEqual(code, 0)
        self.copy.note('docs/knowledge/notes/motion/stop.md', description='')
        self.copy.commit('ノートを壊す')
        code, output = self.run_check('--base', 'origin-base')
        self.assertEqual(code, 1)
        self.assertIn('description が空である', output)

    def test_protected_changes_are_listed_without_becoming_findings(self):
        self.copy.write('docs/knowledge/README.md', '# 入口\n\n変更した。\n')
        code, output = self.run_check()
        self.assertEqual(code, 0)
        self.assertIn('## 保護対象の変更', output)
        self.assertIn('`docs/knowledge/README.md`', output)
        self.assertIn('人のマージを待つ', output)

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
