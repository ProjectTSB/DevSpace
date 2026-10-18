"""Checks how the source generator chooses inputs and reuses output, without network or Java."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/minecraft/source.py'

# The generator reads these to find DevSpace and Java; the tests pass both explicitly.
for variable in ('DEVSPACE_ROOT', 'DEVSPACE_CONFIG', 'JAVA_BIN'):
    os.environ.pop(variable, None)

spec = importlib.util.spec_from_file_location('minecraft_source', SCRIPT)
source = importlib.util.module_from_spec(spec)
sys.modules['minecraft_source'] = source
spec.loader.exec_module(source)


def sha(data, algorithm='sha1'):
    return hashlib.new(algorithm, data).hexdigest()


def jar(*names):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name in names:
            archive.writestr(name, b'')
    return buffer.getvalue()


SERVER = jar('META-INF/versions.list', 'net/minecraft/bundler/Main.class')


class Mojang:
    """Serves a manifest, version definitions and their files from memory."""

    def __init__(self, mappings=True, java=17, client=None):
        self.files = {}
        self.requests = []
        self.downloads = {'client': self.add('client.jar', client or jar('net/minecraft/A.class')),
                          'server': self.add('server.jar', SERVER)}
        if mappings:
            self.downloads['client_mappings'] = self.add('client.txt', b'mappings')
        self.library = {'name': 'com.mojang:brigadier:1.2.9', 'downloads': {'artifact': {
            **self.add('brigadier.jar', b'library'), 'path': 'com/mojang/brigadier/1.2.9/brigadier.jar'}}}
        self.java = java
        self.versions = []
        self.publish('1.20.4')
        for name in ('renamer', 'decompiler'):
            self.files[f'https://example.invalid/{name}.jar'] = f'{name} tool'.encode()

    def add(self, name, data):
        self.files[f'https://example.invalid/{name}'] = data
        return {'url': f'https://example.invalid/{name}', 'sha1': sha(data), 'size': len(data)}

    def publish(self, version):
        definition = json.dumps({'id': version, 'downloads': self.downloads,
                                 'libraries': [self.library],
                                 'javaVersion': {'majorVersion': self.java}}).encode()
        url = f'https://example.invalid/{version}.json'
        self.files[url] = definition
        self.versions.append({'id': version, 'url': url, 'sha1': sha(definition)})
        self.files[source.MANIFEST] = json.dumps({'versions': self.versions}).encode()

    def fetch(self, url):
        self.requests.append(url)
        if url not in self.files:
            raise source.Failure(f'unexpected request {url}')
        return self.files[url]


class Runner:
    """Records commands and writes what each tool would leave behind."""

    def __init__(self, java_version='openjdk version "17.0.20.1" 2026-08-18', fail=None,
                 silent=None):
        self.commands = []
        self.java_version = java_version
        self.fail = fail
        self.silent = silent

    def __call__(self, command, cwd=None, capture=False):
        self.commands.append(command)
        if command[1] == '-version':
            return self.java_version
        name = Path(command[2]).name if command[1] == '-jar' else 'server'
        if name.startswith(self.fail or '\0'):
            raise source.Failure(f'{name} failed')
        if name.startswith(self.silent or '\0'):
            return ''
        if name.startswith('renamer'):
            Path(command[command.index('--output') + 1]).write_bytes(b'named')
        elif name.startswith('decompiler'):
            output = Path(command[-1]) / 'net/minecraft'
            output.mkdir(parents=True)
            (output / 'Example.java').write_text('class Example {}\n')
        else:
            reports = Path(command[command.index('--output') + 1]) / 'reports'
            reports.mkdir(parents=True)
            (reports / 'commands.json').write_text('{}\n')
        return ''

    def tool(self, name):
        return [command for command in self.commands
                if command[1] == '-jar' and Path(command[2]).name.startswith(name)]


class SourceTest(unittest.TestCase):
    def setUp(self):
        tools = source.TOOLS
        self.addCleanup(setattr, source, 'TOOLS', tools)
        source.TOOLS = {name: {'url': f'https://example.invalid/{name}.jar',
                               'sha256': sha(f'{name} tool'.encode(), 'sha256')}
                        for name in ('renamer', 'decompiler')}
        self.cache = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.cache, ignore_errors=True)

    def prepare(self, mojang, runner, version='1.20.4', eula=True):
        return source.prepare(version, self.cache, mojang.fetch, runner,
                              lambda: {'java': 'java', 'eula': eula})

    def rebuild_with_other_options(self):
        options = source.DECOMPILE_OPTIONS
        self.addCleanup(setattr, source, 'DECOMPILE_OPTIONS', options)
        source.DECOMPILE_OPTIONS = [*options, '--extra']
        return options

    def leftovers(self):
        return [path.name for path in (self.cache / 'minecraft').iterdir()
                if '.work-' in path.name or '.old-' in path.name]

    def test_a_version_is_generated_once_and_then_reused_without_the_network(self):
        mojang, runner = Mojang(), Runner()
        target = self.prepare(mojang, runner)
        self.assertEqual(target, self.cache / 'minecraft/1.20.4')
        self.assertTrue((target / 'src/net/minecraft/Example.java').is_file())
        self.assertTrue((target / 'reports/commands.json').is_file())
        recorded = json.loads((target / 'source.json').read_text())
        self.assertEqual(recorded['downloads']['client'], mojang.downloads['client']['sha1'])
        self.assertEqual(sorted(path.name for path in (self.cache / 'minecraft').iterdir()
                                if path.name.startswith('1.20.4')), ['1.20.4'])
        # The decompiler reads the renamed jar and the libraries for type information.
        decompile = runner.tool('decompiler')[0]
        self.assertTrue(decompile[-2].endswith('client-named.jar'))
        self.assertTrue(any(part.endswith('brigadier.jar') for part in decompile))

        offline = Runner()
        self.assertEqual(source.prepare('1.20.4', self.cache, self.no_network, offline,
                                        self.no_settings), target)
        self.assertEqual(offline.commands, [])

    def test_versions_are_kept_side_by_side(self):
        mojang = Mojang()
        mojang.publish('1.21')
        for version in ('1.20.4', '1.21'):
            self.prepare(mojang, Runner(), version)
        for version in ('1.20.4', '1.21'):
            recorded = json.loads((self.cache / 'minecraft' / version / 'source.json').read_text())
            self.assertEqual(recorded['version'], version)

    def test_the_runtime_server_jar_is_reused_when_it_is_the_same_file(self):
        mojang = Mojang()
        (self.cache / 'server-1.20.4.jar').write_bytes(SERVER)
        runner = Runner()
        self.prepare(mojang, runner)
        self.assertNotIn('https://example.invalid/server.jar', mojang.requests)
        server = [command for command in runner.commands if 'server-1.20.4.jar' in ' '.join(command)]
        self.assertEqual(len(server), 1)

    def test_a_version_without_mappings_is_decompiled_as_shipped(self):
        runner = Runner()
        self.prepare(Mojang(mappings=False), runner)
        self.assertEqual(runner.tool('renamer'), [])
        self.assertTrue(runner.tool('decompiler')[0][-2].endswith('-client'))

    def test_an_obfuscated_jar_without_mappings_is_refused(self):
        mojang = Mojang(mappings=False, client=jar('a.class', 'net/minecraft/client/main/Main.class'))
        with self.assertRaisesRegex(source.Failure, '難読化'):
            self.prepare(mojang, Runner())
        self.assertFalse((self.cache / 'minecraft/1.20.4').exists())

    def test_a_server_jar_older_than_the_bundler_stops_before_decompiling(self):
        mojang = Mojang()
        old = jar('net/minecraft/server/Main.class')
        mojang.downloads['server'] = mojang.add('server.jar', old)
        mojang.versions.clear()
        mojang.publish('1.17.1')
        runner = Runner()
        with self.assertRaisesRegex(source.Failure, 'bundler 形式ではない'):
            self.prepare(mojang, runner, '1.17.1')
        self.assertEqual(runner.tool('decompiler'), [])

    def test_changed_options_rebuild_the_version(self):
        self.prepare(Mojang(), Runner())
        self.rebuild_with_other_options()
        runner = Runner()
        self.prepare(Mojang(), runner)
        self.assertEqual(len(runner.tool('decompiler')), 1)

    def test_a_missing_output_directory_is_rebuilt(self):
        target = self.prepare(Mojang(), Runner())
        shutil.rmtree(target / 'src')
        runner = Runner()
        self.prepare(Mojang(), runner)
        self.assertEqual(len(runner.tool('decompiler')), 1)
        self.assertTrue((target / 'src').is_dir())

    def test_a_failed_rebuild_keeps_the_previous_output(self):
        target = self.prepare(Mojang(), Runner())
        options = self.rebuild_with_other_options()
        for runner, message in ((Runner(fail='decompiler'), 'decompiler'),
                                (Runner(silent='decompiler'), 'net/minecraft がない'),
                                (Runner(silent='server'), 'reports/commands.json を書かなかった')):
            with self.assertRaisesRegex(source.Failure, message):
                self.prepare(Mojang(), runner)
            self.assertTrue((target / 'src/net/minecraft/Example.java').is_file())
            recorded = json.loads((target / 'source.json').read_text())
            self.assertEqual(recorded['decompile_options'], options)
            self.assertEqual(self.leftovers(), [])

    def test_work_directories_left_by_an_interrupted_run_are_removed(self):
        (self.cache / 'minecraft/1.20.4.work-1/out').mkdir(parents=True)
        (self.cache / 'minecraft/1.20.4.old-1').mkdir()
        self.prepare(Mojang(), Runner())
        self.assertEqual(self.leftovers(), [])

    def test_generating_needs_the_eula_but_reading_does_not(self):
        mojang = Mojang()
        with self.assertRaisesRegex(source.Failure, 'EULA'):
            self.prepare(mojang, Runner(), eula=False)
        self.assertEqual(mojang.requests, [])
        target = self.prepare(Mojang(), Runner())
        self.assertEqual(self.prepare(Mojang(), Runner(), eula=False), target)

    def test_settings_follow_the_runtime_config(self):
        root = self.cache / 'devspace'
        shutil.copytree(SCRIPT.parents[1] / 'lib', root / 'scripts/lib')
        (root / 'devspace.local.conf').write_text('JAVA_BIN=/opt/jdk/bin/java\nACCEPT_EULA=false\n')
        self.assertEqual(source.settings(root), {'java': '/opt/jdk/bin/java', 'eula': False})
        (root / '.runtime').mkdir()
        (root / '.runtime/eula.txt').write_text('eula=true\n')
        self.assertTrue(source.settings(root)['eula'])
        # A relative --java is fixed now, before the server runs in its own work directory.
        self.assertEqual(source.settings(root, 'jdk/bin/java')['java'],
                         os.path.abspath('jdk/bin/java'))
        self.assertEqual(source.settings(root, 'java21')['java'], 'java21')

    def test_a_digest_mismatch_stops_without_leaving_the_file(self):
        mojang = Mojang()
        mojang.files['https://example.invalid/client.jar'] = b'tampered'
        with self.assertRaisesRegex(source.Failure, 'sha1 が一致しない'):
            self.prepare(mojang, Runner())
        self.assertFalse(any((self.cache / 'minecraft/downloads').glob('*-client*')))
        self.assertFalse((self.cache / 'minecraft/1.20.4').exists())

    def test_a_java_older_than_the_version_needs_stops_before_downloading(self):
        mojang = Mojang(java=21)
        with self.assertRaisesRegex(source.Failure, 'Java 21 以上が必要.*--java'):
            self.prepare(mojang, Runner())
        self.assertNotIn('https://example.invalid/client.jar', mojang.requests)

    def test_unknown_versions_and_definitions_without_a_server_are_refused(self):
        with self.assertRaisesRegex(source.Failure, '版一覧にない'):
            self.prepare(Mojang(), Runner(), '0.0')
        with self.assertRaisesRegex(source.Failure, 'server の配布がない'):
            source.build_plan({'id': 'x', 'downloads': {'client': {}}})

    def test_libraries_follow_the_linux_rules_and_skip_natives(self):
        def library(name, rules=None):
            entry = {'name': name, 'downloads': {'artifact': {'path': name, 'url': name, 'sha1': ''}}}
            return {**entry, 'rules': rules} if rules else entry
        plan = source.build_plan({'downloads': {'client': {}, 'server': {}}, 'libraries': [
            library('a:common:1'),
            library('a:mac-only:1', [{'action': 'allow', 'os': {'name': 'osx'}}]),
            library('a:not-on-mac:1', [{'action': 'allow'},
                                       {'action': 'disallow', 'os': {'name': 'osx'}}]),
            library('a:binaries:1:natives-linux'),
        ]})
        self.assertEqual([entry['path'] for entry in plan['libraries']],
                         ['a:common:1', 'a:not-on-mac:1'])

    def test_java_versions_are_read_from_both_numbering_styles(self):
        self.assertEqual(source.java_major('openjdk version "17.0.20.1" 2026-08-18'), 17)
        self.assertEqual(source.java_major('java version "1.8.0_372"'), 8)
        self.assertEqual(source.java_major('openjdk version "21" 2023-09-19'), 21)
        self.assertIsNone(source.java_major('no version here'))

    @staticmethod
    def no_network(url):
        raise AssertionError(f'network used for {url}')

    @staticmethod
    def no_settings():
        raise AssertionError('settings read for a generated version')


if __name__ == '__main__':
    unittest.main()
