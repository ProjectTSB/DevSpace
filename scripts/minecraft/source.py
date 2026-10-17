"""Generate readable Minecraft: Java Edition source and data reports for one version.

    python3 scripts/minecraft/source.py <版> [--java <path>]

The client jar is renamed with Mojang's official mappings and decompiled, together with
the jar's assets and data; a version published without obfuscation is decompiled as is.
The server's data generator then writes its reports, such as the command tree. Using the
game files is governed by the Minecraft EULA, so generating requires the same acceptance
as starting the server (ACCEPT_EULA=true, or eula=true in .runtime/eula.txt); reading an
already generated version does not. Versions from 1.18 on, whose server jar is a bundler,
are supported.

Everything is written under the `.cache/minecraft/` of the checkout that holds this script
(DEVSPACE_ROOT overrides it, as for the runtime scripts):
  <版>/        `src/`, `reports/` and `source.json`; one directory per version, so several
               versions can be read side by side
  downloads/   version files by sha1; the server jar is taken from `.cache/server-<版>.jar`
               instead when the runtime has already fetched the same file
  libraries/   the libraries the decompiler reads for type information
  tools/       the pinned renamer and decompiler
A version whose `source.json` matches the tools and options here is left as is without any
network access. Otherwise it is rebuilt in a work directory under a lock (fcntl, so Linux
and macOS) and replaces the previous output only after the expected source and reports
exist. `<版>.work-*` and `<版>.old-*` left by an interrupted run are removed when that
version is built next; a version already current keeps them until then, so they may be
deleted by hand.

Java runs with `--java`, else the JAVA_BIN the server uses (devspace.local.conf, then the
environment), else `java`. It must be 17 or the version's own requirement, if newer. The
generated code and the mappings may not be redistributed, so nothing here is committed.
"""
import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

MANIFEST = 'https://piston-meta.mojang.com/mc/game/version_manifest_v2.json'
# Raise when the steps or the output layout change, so generated versions are rebuilt.
FORMAT = 1
# Changing a tool or an option changes the output, so both are part of `source.json`.
TOOLS = {
    'renamer': {
        'url': 'https://maven.neoforged.net/releases/net/neoforged/AutoRenamingTool/2.0.18/'
               'AutoRenamingTool-2.0.18-all.jar',
        'sha256': '64ece9706e5b111cebcb662d4eab56ba6b9b9b3b4bee1766382352fe02a6a7f3',
    },
    'decompiler': {
        'url': 'https://repo1.maven.org/maven2/org/vineflower/vineflower/1.12.0/'
               'vineflower-1.12.0.jar',
        'sha256': '1dfcfe974395734fa467ce620661c7623d05ba83670de0529b1fbd63ff548b9d',
    },
}
# The official mappings name obfuscated -> readable in reverse, hence `--reverse`.
RENAME_OPTIONS = ['--reverse', '--ann-fix', '--ids-fix', '--src-fix', '--record-fix']
DECOMPILE_OPTIONS = ['--log-level=warn', '--variable-renaming=jad']
MINIMUM_JAVA = 17


class Failure(Exception):
    """A step that cannot continue; the message tells what to fix."""


def main(argv=None):
    parser = argparse.ArgumentParser(description='Minecraftのソースとreportsを版ごとに生成する')
    parser.add_argument('version', help='Minecraft の版（例: 1.20.4）')
    parser.add_argument('--java', help='使う java（既定はサーバーと同じ JAVA_BIN）')
    arguments = parser.parse_args(argv)
    root = devspace_root()
    try:
        print(prepare(arguments.version, root / '.cache', fetch, run,
                      lambda: settings(root, arguments.java)))
    except Failure as failure:
        print(f'minecraft source: {failure}', file=sys.stderr)
        return 1
    return 0


def devspace_root():
    return Path(os.environ.get('DEVSPACE_ROOT') or Path(__file__).resolve().parents[2])


def settings(root, java=None):
    """Read JAVA_BIN and the EULA acceptance through the runtime's own config parser."""
    script = ('. "$1/scripts/lib/runtime.sh"\nruntime_init || exit\n'
              'printf "%s\\n%s\\n" "${JAVA_BIN:-java}" "${ACCEPT_EULA:-false}"\n')
    try:
        result = subprocess.run(['sh', '-c', script, 'sh', str(root)], capture_output=True,
                                text=True, env=dict(os.environ, DEVSPACE_ROOT=str(root)))
    except OSError as error:
        raise Failure(f'devspace.local.conf を読めない: {error}') from error
    if result.returncode != 0:
        raise Failure(f'devspace.local.conf を読めない: {result.stderr.strip()}')
    configured, accepted = result.stdout.strip().split('\n')[-2:]
    eula = root / '.runtime' / 'eula.txt'
    accepted = accepted == 'true' or (eula.is_file() and 'eula=true' in
                                      eula.read_text(encoding='utf-8', errors='replace').split())
    java = java or configured
    # A relative path would resolve against the server's work directory later on.
    return {'java': os.path.abspath(java) if os.sep in java else java, 'eula': accepted}


def prepare(version, dot_cache, fetch, run, configure):
    """Return the version's directory, generating it unless it is already current.

    `configure` gives the Java to run and the EULA acceptance; it is read only when the
    version has to be generated.
    """
    cache = dot_cache / 'minecraft'
    target = cache / version
    if current(target, version):
        return target
    cache.mkdir(parents=True, exist_ok=True)
    with (cache / '.lock').open('a') as lock:
        # Another run may have finished the same version while this one waited.
        fcntl.flock(lock, fcntl.LOCK_EX)
        if current(target, version):
            return target
        # Holding the lock, no other build is running: anything left is from an interrupted run.
        for leftover in [*cache.glob(f'{version}.work-*'), *cache.glob(f'{version}.old-*')]:
            shutil.rmtree(leftover, ignore_errors=True)
        work = cache / f'{version}.work-{os.getpid()}'
        try:
            build(version, dot_cache, cache, target, work, fetch, run, configure())
        finally:
            shutil.rmtree(work, ignore_errors=True)
    return target


def build(version, dot_cache, cache, target, work, fetch, run, configured):
    if not configured['eula']:
        raise Failure('Minecraft EULA への同意が必要。利用者が同意したうえで ACCEPT_EULA=true を'
                      '設定するか、.runtime/eula.txt に eula=true を書く')
    java = configured['java']
    definition_url, definition_sha1 = locate(version, fetch)
    definition = json.loads(verified(fetch(definition_url), 'sha1', definition_sha1, definition_url))
    plan = build_plan(definition)
    wanted = stamp(version, definition_sha1, plan)

    check_java(java, max(MINIMUM_JAVA, plan['java']), run)
    tools = {name: download(cache / 'tools', tool['url'], 'sha256', tool['sha256'], fetch)
             for name, tool in TOOLS.items()}
    runtime_server = dot_cache / f'server-{version}.jar'
    files = {name: (runtime_server if name == 'server' and matches(runtime_server, 'sha1', item['sha1'])
                    else download(cache / 'downloads', item['url'], 'sha1', item['sha1'], fetch,
                                  name=f"{item['sha1']}-{name}"))
             for name, item in plan['downloads'].items()}
    if 'client_mappings' not in files and obfuscated(files['client']):
        raise Failure(f'{version} は公式マッピングがなく、client jar も難読化されている')
    # Checked before the decompiler spends minutes: older server jars run no data generator
    # this way.
    if not bundled(files['server']):
        raise Failure(f'{version} の server jar は bundler 形式ではない（1.18より前の版は扱えない）')
    libraries = [download(cache / 'libraries', item['url'], 'sha1', item['sha1'], fetch,
                          name=item['path'])
                 for item in plan['libraries']]

    (work / 'out').mkdir(parents=True)
    client = files['client']
    if 'client_mappings' in files:
        client = work / 'client-named.jar'
        run([java, '-jar', str(tools['renamer']), '--input', str(files['client']),
             '--output', str(client), '--names', str(files['client_mappings']),
             *RENAME_OPTIONS])
    run([java, '-jar', str(tools['decompiler']), *DECOMPILE_OPTIONS,
         *(f'-e={library}' for library in libraries), str(client), str(work / 'out' / 'src')])
    # The bundled server unpacks its libraries into the working directory before running.
    run([java, '-DbundlerMainClass=net.minecraft.data.Main', '-jar', str(files['server']),
         '--reports', '--output', str(work / 'generated')], cwd=work)
    # A tool can exit with 0 without writing anything, such as on an unsupported jar.
    if not (work / 'out' / 'src' / 'net' / 'minecraft').is_dir():
        raise Failure('デコンパイルの出力に net/minecraft がない')
    if not (work / 'generated' / 'reports' / 'commands.json').is_file():
        raise Failure('data generator が reports/commands.json を書かなかった')
    (work / 'generated' / 'reports').rename(work / 'out' / 'reports')
    (work / 'out' / 'source.json').write_text(json.dumps(wanted, indent=2) + '\n', encoding='utf-8')

    replace(work / 'out', target)


def locate(version, fetch):
    manifest = json.loads(fetch(MANIFEST))
    for entry in manifest['versions']:
        if entry['id'] == version:
            return entry['url'], entry['sha1']
    raise Failure(f'{version} は Mojang の版一覧にない')


def build_plan(definition):
    """Pick the files to download from a version definition."""
    downloads = definition.get('downloads', {})
    for required in ('client', 'server'):
        if required not in downloads:
            raise Failure(f'{definition.get("id")} の定義に {required} の配布がない')
    chosen = {name: downloads[name] for name in ('client', 'server', 'client_mappings')
              if name in downloads}
    libraries = []
    for library in definition.get('libraries', []):
        artifact = library.get('downloads', {}).get('artifact')
        # Native jars only carry platform binaries; the decompiler needs class files.
        if artifact and allowed(library.get('rules')) and ':natives-' not in library['name']:
            libraries.append(artifact)
    return {'downloads': chosen, 'libraries': libraries,
            'java': definition.get('javaVersion', {}).get('majorVersion', MINIMUM_JAVA)}


def allowed(rules):
    """Apply a library's rules for Linux, the platform the source is read on."""
    if not rules:
        return True
    verdict = False
    for rule in rules:
        if rule.get('os', {}).get('name', 'linux') == 'linux':
            verdict = rule['action'] == 'allow'
    return verdict


def generation(version):
    """The inputs chosen here; the files of a released version stay the same."""
    return {
        'format': FORMAT,
        'version': version,
        'tools': {name: tool['sha256'] for name, tool in sorted(TOOLS.items())},
        'rename_options': RENAME_OPTIONS,
        'decompile_options': DECOMPILE_OPTIONS,
    }


def stamp(version, definition_sha1, plan):
    return {**generation(version), 'definition_sha1': definition_sha1,
            'downloads': {name: item['sha1'] for name, item in sorted(plan['downloads'].items())}}


def current(target, version):
    """Tell whether a generated version needs no rebuild, without asking the network."""
    recorded = read_stamp(target)
    return (recorded is not None and (target / 'src').is_dir() and (target / 'reports').is_dir()
            and all(recorded.get(key) == value for key, value in generation(version).items()))


def bundled(jar):
    with zipfile.ZipFile(jar) as archive:
        return 'META-INF/versions.list' in archive.namelist()


def obfuscated(jar):
    """Obfuscated jars keep most classes at the root under short names such as `a.class`."""
    with zipfile.ZipFile(jar) as archive:
        return any('/' not in name and name.endswith('.class') for name in archive.namelist())


def read_stamp(target):
    try:
        return json.loads((target / 'source.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def replace(built, target):
    """Move the finished output into place, keeping the previous one until the move."""
    previous = target.with_name(f'{target.name}.old-{os.getpid()}')
    if target.exists():
        target.rename(previous)
    built.rename(target)
    shutil.rmtree(previous, ignore_errors=True)


def download(directory, url, algorithm, expected, fetch, name=None):
    """Return a cached file whose digest matches, downloading it first if needed."""
    path = directory / (name or url.rsplit('/', 1)[-1])
    if matches(path, algorithm, expected):
        return path
    data = verified(fetch(url), algorithm, expected, url)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f'{path.name}.part-{os.getpid()}')
    partial.write_bytes(data)
    partial.replace(path)
    return path


def matches(path, algorithm, expected):
    return path.is_file() and digest(path.read_bytes(), algorithm) == expected


def verified(data, algorithm, expected, url):
    actual = digest(data, algorithm)
    if actual != expected:
        raise Failure(f'{url} の {algorithm} が一致しない（期待 {expected}、実際 {actual}）')
    return data


def digest(data, algorithm):
    return hashlib.new(algorithm, data).hexdigest()


def check_java(java, required, run):
    try:
        output = run([java, '-version'], capture=True)
    except Failure:
        raise Failure(f'Java を実行できない: {java}。--java で Java {required} 以上を指定する')
    major = java_major(output)
    if major is None or major < required:
        raise Failure(f'Java {required} 以上が必要（{java} は {major or "不明"}）。'
                      '--java で指定する')


def java_major(version_output):
    """Read the major version from `java -version`, such as 17 from `"17.0.20.1"`."""
    for token in version_output.split('"')[1::2]:
        parts = token.split('.')
        number = parts[1] if parts[0] == '1' and len(parts) > 1 else parts[0]
        if number.isdigit():
            return int(number)
    return None


def fetch(url):
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            return response.read()
    except OSError as error:
        raise Failure(f'{url} を取得できない: {error}') from error


def run(command, cwd=None, capture=False):
    try:
        result = subprocess.run(command, cwd=cwd, capture_output=capture, text=True, check=False)
    except OSError as error:
        raise Failure(f'{command[0]} を実行できない: {error}') from error
    if result.returncode != 0:
        detail = (result.stderr or '').strip().split('\n')[-1] if capture else ''
        raise Failure(f'{" ".join(command[:3])} … が終了コード {result.returncode} で失敗した {detail}'.rstrip())
    return (result.stdout or '') + (result.stderr or '') if capture else ''


if __name__ == '__main__':
    raise SystemExit(main())
