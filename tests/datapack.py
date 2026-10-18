"""Checks that the datapack check reports convention breaks in changed lines and runs the repository's own check."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/datapack/check.py'

# The throwaway repositories must not resolve to a working copy named by the caller's
# environment, such as a worktree opened through GIT_DIR from another mount path.
for variable in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR'):
    os.environ.pop(variable, None)

spec = importlib.util.spec_from_file_location('datapack_check', SCRIPT)
check = importlib.util.module_from_spec(spec)
sys.modules['datapack_check'] = check
spec.loader.exec_module(check)

FUNCTIONS = 'Asset/data/asset/functions'


def git(root, *arguments):
    environment = dict(os.environ, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.com',
                       GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@example.com')
    return subprocess.run(('git', '-C', str(root)) + arguments, check=True,
                          capture_output=True, text=True, env=environment).stdout


class Workcopy:
    """A throwaway working copy laid out like Asset, with one artifact."""

    def __init__(self, stack):
        self.root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        git(self.root, 'init', '--quiet', '--initial-branch=master')
        git(self.root, 'remote', 'add', 'origin', 'https://example.invalid/ProjectTSB/Asset.git')
        self.write(f'{FUNCTIONS}/artifact/0001.first/trigger/1.trigger.mcfunction', 'say trigger\n')
        self.commit('初期')

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def commit(self, subject):
        git(self.root, 'add', '--all')
        git(self.root, 'commit', '--quiet', '--message', subject)
        # A commit on master stands for one already pushed, so it becomes the default base.
        if git(self.root, 'branch', '--show-current').strip() == 'master':
            git(self.root, 'update-ref', 'refs/remotes/origin/master', 'HEAD')
            git(self.root, 'symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/master')


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

    def test_a_clean_working_copy_has_no_findings(self):
        code, output = self.run_check()
        self.assertEqual(code, 0)
        self.assertIn('## 指摘なし', output)

    def test_declare_must_sit_one_level_below_its_imp_doc(self):
        self.copy.write(f'{FUNCTIONS}/artifact/0001.first/trigger/_index.d.mcfunction', '\n'.join([
            '#> asset:artifact/0001.first/trigger/_index.d',
            '# @private',
            '',
            '#> tag',
            '# @within function asset:artifact/0001.first/trigger/**',
            '    #declare tag 0001.Good',
            '#declare tag 0001.Flat',
            '        #declare tag 0001.Deep',
            '',
        ]))
        code, output = self.run_check()
        self.assertEqual(code, 1)
        self.assertNotIn('6行', output)
        self.assertIn('7行: `#declare` は4行の `#>` より4スペース深くする（今は0、期待は4）', output)
        self.assertIn('8行: `#declare` は4行の `#>` より4スペース深くする（今は8、期待は4）', output)

    def test_only_changed_lines_are_checked(self):
        path = f'{FUNCTIONS}/artifact/0001.first/trigger/2.main.mcfunction'
        self.copy.write(path, 'execute as @a[tag=Old,sort=nearest,limit=1] run say old\n')
        self.copy.commit('既存の書き方')
        self.copy.write(path, 'execute as @a[tag=Old,sort=nearest,limit=1] run say old\n'
                              'execute as @a[limit=1, tag=New, sort=nearest] run say new\n')
        code, output = self.run_check()
        self.assertEqual(code, 1)
        self.assertNotIn('1行', output)
        self.assertIn('2行: `@a[limit=1, tag=New, sort=nearest]` は `@p[tag=New]` と同じ選択になる', output)

    def test_base_includes_committed_changes_since_the_merge_base(self):
        git(self.copy.root, 'branch', 'origin-base')
        self.copy.write(f'{FUNCTIONS}/artifact/0001.first/trigger/2.main.mcfunction',
                        'tag @a[sort=nearest,limit=1] add X\n')
        self.copy.commit('コミット済みの変更')
        code, _ = self.run_check()
        self.assertEqual(code, 0)
        code, output = self.run_check('--base', 'origin-base')
        self.assertEqual(code, 1)
        self.assertIn('`@p` で書く', output)
        code, output = self.run_check('--base', 'missing-ref')
        self.assertEqual(code, 2)
        self.assertIn('差分の基準 missing-ref を使えない', output)

    def test_selectors_keep_nested_values_and_other_kinds_alone(self):
        self.copy.write(f'{FUNCTIONS}/artifact/0001.first/trigger/2.main.mcfunction', '\n'.join([
            'tag @a[scores={X=1..},nbt={Inventory:[{id:"a,b]"}]},sort=nearest,limit=1] add Y',
            'tag @a[sort=nearest,limit=2] add Y',
            'tag @a[sort=furthest,limit=1] add Y',
            '$tag @a[tag=$(Tag),sort=nearest,limit=1] add Y',
            '# tag @a[sort=nearest,limit=1] add Y',
            'tellraw @a {"text":"mail@example.com"}',
            '',
        ]))
        code, output = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('1行: `@a[scores={X=1..},nbt={Inventory:[{id:"a,b]"}]},sort=nearest,limit=1]` は '
                      '`@p[scores={X=1..},nbt={Inventory:[{id:"a,b]"}]}]` と同じ選択になる', output)
        self.assertIn('4行: `@a[tag=$(Tag),sort=nearest,limit=1]` は `@p[tag=$(Tag)]`', output)
        for line in ('2行', '3行', '5行', '6行'):
            self.assertNotIn(line, output)

    def test_unbounded_entity_searches_are_review_notes(self):
        self.copy.write(f'{FUNCTIONS}/artifact/0001.first/trigger/2.main.mcfunction', '\n'.join([
            'kill @e[type=marker,tag=X]',
            'kill @e[type=marker,tag=X,distance=..5]',
            'kill @e[type=marker,tag=X,dx=0]',
            'kill @e[tag=X] @e[tag=X]',
            'kill @e[tag=X,distance=5..]',
            'kill @e[tag=X,distance=3]',
            'kill @e[tag=X,x=0,y=0,z=0]',
            'kill @e[type=player,tag=X]',
            'kill @e[type=!player,tag=X]',
            'kill @e[tag=X,limit=1]',
            'kill @e[tag=X,sort=nearest,limit=1]',
            '',
        ]))
        code, output = self.run_check()
        self.assertEqual(code, 0)
        self.assertIn('## 確認', output)
        self.assertIn('1行: `@e[type=marker,tag=X]` は dx/dy/dz も distance の上限もなく', output)
        self.assertEqual(output.count('4行'), 1)
        # A lower bound or a position alone keeps the search to one dimension without a box.
        self.assertIn('5行: `@e[tag=X,distance=5..]` は dx/dy/dz も distance の上限もなく、'
                      '実行中のディメンションのentityをすべて調べる', output)
        self.assertIn('7行: `@e[tag=X,x=0,y=0,z=0]` は dx/dy/dz も distance の上限もなく、'
                      '実行中のディメンション', output)
        self.assertIn('1行: `@e[type=marker,tag=X]` は dx/dy/dz も distance の上限もなく、'
                      '全ディメンション', output)
        # `type=player` searches players, not entities; a negated type does not.
        self.assertIn('9行: `@e[type=!player,tag=X]`', output)
        # Without a sort, a limit stops the search early.
        self.assertIn('10行: `@e[tag=X,limit=1]` は dx/dy/dz も distance の上限もなく、'
                      '全ディメンションのentityを見つかるまで調べる', output)
        self.assertIn('11行: `@e[tag=X,sort=nearest,limit=1]` は dx/dy/dz も distance の上限もなく、'
                      '全ディメンションのentityをすべて調べる', output)
        for line in ('2行', '3行', '6行', '8行'):
            self.assertNotIn(line, output)
        self.copy.write(f'{FUNCTIONS}/artifact/0001.first/trigger/3.main.mcfunction',
                        'kill @e[gamemode=survival]\nkill @e[level=1..]\nkill @e[advancements={a=true}]\n'
                        'kill @e[tag=X,sort=arbitrary,limit=1]\n')
        output = self.run_check()[1]
        self.assertNotIn('3.main.mcfunction`\n  - 1行', output)
        self.assertIn('4行: `@e[tag=X,sort=arbitrary,limit=1]` は dx/dy/dz も distance の上限もなく、'
                      '全ディメンションのentityを見つかるまで調べる', output)
        self.assertNotIn('3.main.mcfunction`\n  - 2行', output)

    def test_diff_prefix_settings_do_not_hide_changed_lines(self):
        self.copy.write(f'{FUNCTIONS}/artifact/0001.first/trigger/2.main.mcfunction',
                        'tag @a[sort=nearest,limit=1] add X\n')
        for key in ('diff.mnemonicPrefix', 'diff.noprefix'):
            settings = {'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': key, 'GIT_CONFIG_VALUE_0': 'true'}
            os.environ.update(settings)
            try:
                code, output = self.run_check()
            finally:
                for variable in settings:
                    os.environ.pop(variable)
            self.assertEqual(code, 1, key)
            self.assertIn('`@p` で書く', output)

    def test_a_renamed_function_is_checked_only_where_it_changed(self):
        old = f'{FUNCTIONS}/artifact/0001.first/trigger/2.main.mcfunction'
        self.copy.write(old, 'tag @a[sort=nearest,limit=1] add X\nsay a\nsay b\nsay c\n')
        self.copy.commit('既存の書き方')
        git(self.copy.root, 'mv', old, old.replace('2.main', '2.main.m'))
        code, output = self.run_check()
        self.assertEqual(code, 0, output)

    def test_paths_with_spaces_are_read_and_the_index_is_left_alone(self):
        self.copy.write(f'{FUNCTIONS}/artifact/0001.first/trigger/a b.mcfunction', 'say x\n')
        self.copy.commit('空白のあるパス')
        self.copy.write(f'{FUNCTIONS}/artifact/0001.first/trigger/a b.mcfunction',
                        'say x\ntag @a[sort=nearest,limit=1] add X\n')
        index = self.copy.root / '.git/index'
        before = index.stat().st_mtime_ns
        code, output = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('a b.mcfunction', output)
        self.assertEqual(index.stat().st_mtime_ns, before)

    def test_binary_files_and_a_non_utf8_console_do_not_break_the_check(self):
        structure = self.copy.root / 'Asset/data/asset/structures/arena.nbt'
        structure.parent.mkdir(parents=True)
        structure.write_bytes(bytes(range(256)))
        self.copy.commit('構造物')
        # A tracked binary that changes reaches the diff unless the check narrows it.
        structure.write_bytes(bytes(reversed(range(256))))
        self.copy.write(f'{FUNCTIONS}/artifact/0001.first/trigger/1.trigger.mcfunction',
                        'say trigger\n# 日本語のコメント\ntag @a[sort=nearest,limit=1] add X\n')
        # The C locale without UTF-8 fallbacks reads and writes ASCII, as cp932 cannot hold UTF-8.
        environment = dict(os.environ, LC_ALL='C', PYTHONUTF8='0', PYTHONCOERCECLOCALE='0',
                           PYTHONIOENCODING='')
        result = subprocess.run([sys.executable, str(SCRIPT), str(self.copy.root)],
                                capture_output=True, env=environment)
        output = result.stdout.decode('utf-8')
        self.assertEqual(result.returncode, 1, result.stderr.decode('utf-8', 'replace'))
        self.assertIn('3行: `@a[sort=nearest,limit=1]`', output)

    def test_pathspec_modes_from_the_environment_do_not_hide_functions(self):
        self.copy.write(f'{FUNCTIONS}/artifact/0001.first/trigger/1.trigger.mcfunction',
                        'say trigger\ntag @a[sort=nearest,limit=1] add X\n')
        for variable in ('GIT_LITERAL_PATHSPECS', 'GIT_GLOB_PATHSPECS'):
            os.environ[variable] = '1'
            try:
                code, output = self.run_check()
            finally:
                os.environ.pop(variable)
            self.assertEqual(code, 1, variable)
            self.assertIn('`@p` で書く', output)

    def test_context_options_from_the_environment_do_not_widen_the_changed_lines(self):
        path = f'{FUNCTIONS}/artifact/0001.first/trigger/2.main.mcfunction'
        self.copy.write(path, 'tag @a[sort=nearest,limit=1] add X\nsay a\nsay b\n')
        self.copy.commit('既存の書き方')
        self.copy.write(path, 'tag @a[sort=nearest,limit=1] add X\nsay a\nsay c\n')
        os.environ['GIT_DIFF_OPTS'] = '--unified=3'
        try:
            code, output = self.run_check()
        finally:
            os.environ.pop('GIT_DIFF_OPTS')
        self.assertEqual(code, 0, output)

    def test_a_git_failure_while_reading_the_repository_check_stops(self):
        def failing(root, *arguments, **options):
            if arguments[:1] == ('ls-tree',):
                raise check.GitFailure('fatal: bad object')
            return original(root, *arguments, **options)
        original = check.git_output
        check.git_output = failing
        self.addCleanup(setattr, check, 'git_output', original)
        code, output = self.run_check()
        self.assertEqual(code, 2)
        self.assertIn('gitでrepo固有の検査を取り出せない', output)

    def test_generated_declarations_are_skipped(self):
        self.copy.write('Asset/data/minecraft/functions/declares.d.mcfunction',
                        '#> declare\n# @within **\n#declare objective X\n')
        code, _ = self.run_check()
        self.assertEqual(code, 0)

    def repository_check(self, body):
        self.copy.write('scripts/datapack/repository.py', 'import json, sys\n' + body)

    def publish_default_branch(self):
        """Point origin/HEAD at the current commit, as a clone of the remote would."""
        git(self.copy.root, 'update-ref', 'refs/remotes/origin/master', 'HEAD')
        git(self.copy.root, 'symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/master')

    def test_the_working_copy_version_runs_only_when_asked(self):
        code, output = self.run_check('--run-working-copy')
        self.assertEqual(code, 0)
        self.assertIn('repo固有の検査（`scripts/datapack/repository.py`）: この作業コピーにない', output)
        self.repository_check('print(json.dumps({"findings": {}}))\n')
        code, output = self.run_check()
        self.assertEqual(code, 0)
        self.assertRegex(output, r': 共通祖先 `[0-9a-f]{9}` にないため実行していない')
        code, output = self.run_check('--run-working-copy')
        self.assertEqual(code, 0)
        self.assertIn(': 作業コピーの版を実行した', output)
        self.assertIn('## 指摘なし', output)
        self.repository_check('assert sys.argv[2] == "--json"\n'
                              'print(json.dumps({"findings": {"give.json": ["`x` がない"]}}))\n'
                              'sys.exit(1)\n')
        code, output = self.run_check('--run-working-copy')
        self.assertEqual(code, 1)
        self.assertIn('## repo固有の検査の指摘\n\n- `give.json`\n  - `x` がない', output)
        self.assertNotIn('## 指摘\n', output)

    def test_a_review_runs_the_merge_base_version_outside_the_working_copy(self):
        self.repository_check('print(json.dumps({"findings": {"base": ["共通祖先の版"]}})); sys.exit(1)\n')
        self.copy.commit('repo固有の検査')
        self.publish_default_branch()
        git(self.copy.root, 'checkout', '--quiet', '-b', 'pull-request')
        marker = self.copy.root / 'ran-from-the-change'
        # The change under review rewrites the check and adds a module that would shadow `json`.
        self.repository_check(f'open({str(marker)!r}, "w").close()\nprint("{{}}")\n')
        self.copy.write('scripts/datapack/json.py', f'open({str(marker)!r}, "w").close()\n')
        self.copy.commit('検査を書き換える')
        code, output = self.run_check()
        self.assertEqual(code, 1, output)
        self.assertIn('共通祖先の版', output)
        self.assertRegex(output, r': 共通祖先 `[0-9a-f]{9}` の版を実行した')
        self.assertFalse(marker.exists())

    def test_a_check_missing_from_the_merge_base_is_not_run(self):
        self.publish_default_branch()
        git(self.copy.root, 'checkout', '--quiet', '-b', 'pull-request')
        self.repository_check('print(json.dumps({"findings": {}}))\n')
        self.copy.commit('検査を足す')
        code, output = self.run_check()
        self.assertEqual(code, 0)
        self.assertRegex(output, r': 共通祖先 `[0-9a-f]{9}` にないため実行していない')

    def test_a_failing_repository_check_stops_instead_of_passing(self):
        for body in ('sys.exit(2)\n', 'print("not json")\n',
                     'print(json.dumps({"findings": {"a": ["b"]}}))\n',
                     'print(json.dumps({"findings": {"a": "abc"}})); sys.exit(1)\n',
                     'print(json.dumps({"findings": {"a": []}})); sys.exit(1)\n'):
            self.repository_check(body)
            code, output = self.run_check('--run-working-copy')
            self.assertEqual(code, 2, body)
            self.assertRegex(output, 'repository.py (が終了コード 2 で失敗した|の出力が取り決めの形と違う)')
            self.assertNotIn('## 指摘なし', output)

    def test_without_a_default_branch_the_check_stops_instead_of_passing(self):
        git(self.copy.root, 'update-ref', '-d', 'refs/remotes/origin/HEAD')
        git(self.copy.root, 'update-ref', '-d', 'refs/remotes/origin/master')
        code, output = self.run_check()
        self.assertEqual(code, 2)
        self.assertIn('--base <ref> を渡す', output)

    def test_a_declare_without_an_imp_doc_is_a_finding(self):
        self.copy.write('data/core/functions/tick.mcfunction', 'say tick\n#declare tag Flat\n')
        code, output = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('2行: `#declare` の上に対応するIMP Doc（`#>`）がない', output)

    def test_a_diff_attribute_does_not_hide_changed_lines(self):
        self.copy.write('.gitattributes', '*.mcfunction -diff\n')
        self.copy.commit('属性')
        self.copy.write(f'{FUNCTIONS}/artifact/0001.first/trigger/1.trigger.mcfunction',
                        'say trigger\ntag @a[sort=nearest,limit=1] add X\n')
        code, output = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('2行: `@a[sort=nearest,limit=1]`', output)

    def test_an_unreadable_git_stops_instead_of_finding_nothing(self):
        (self.copy.root / '.git/index').write_bytes(b'DIRC')
        code, output = self.run_check()
        self.assertEqual(code, 2)
        self.assertNotIn('## 指摘なし', output)


if __name__ == '__main__':
    unittest.main()
