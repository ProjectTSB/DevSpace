"""Run trusted console scenarios in disposable Linux runtimes, preserving evidence."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
REPOS = ('TheSkyBlessing', 'Asset', 'Asset-AnimatedJava')


def save(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def snapshot(repo):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args])
    names = git('ls-files', '-z', '--cached', '--others', '--exclude-standard').split(b'\0')
    files = {}
    for name in sorted(set(n for n in names if n)):
        p = repo / os.fsdecode(name)
        files[os.fsdecode(name)] = ('link:' + os.readlink(p) if p.is_symlink()
                                   else digest(p) if p.is_file() else 'missing')
    return {'head': git('rev-parse', 'HEAD').decode().strip(),
            'branch': git('branch', '--show-current').decode().strip(),
            'status': git('status', '--porcelain').decode(), 'files': files}


def code_files(state):
    """Compare working contents; Git metadata and known prose are evidence only."""
    def documentation(name):
        return (name in ('README.md', 'AGENTS.md', 'CLAUDE.md')
                or (name.startswith('docs/') and name.endswith('.md')))
    return {name: value for name, value in state['files'].items()
            if value != 'missing' and not documentation(name)}


def check_repository_changes(repos, result):
    result['repositoriesAfterRun'] = {
        name: {'path': str(path), **snapshot(path)} for name, path in repos.items()}
    changes = {}
    for name in repos:
        before = code_files(result['repositories'][name])
        after = code_files(result['repositoriesAfterRun'][name])
        changes[name] = sorted(path for path in before.keys() | after.keys()
                               if before.get(path) != after.get(path))
    result['changedCodeFiles'] = changes
    result['codeUnchangedDuringRun'] = not any(changes.values())
    if not result['codeUnchangedDuringRun']:
        result['status'] = 'failed'


def archive_changes(repo, destination):
    """Preserve changed and untracked contents, without changing the Git index."""
    names = set()
    for args in (['diff', '--name-only', '-z', 'HEAD'], ['ls-files', '--others', '--exclude-standard', '-z']):
        names.update(subprocess.check_output(['git', '-C', str(repo), *args]).split(b'\0'))
    with tarfile.open(destination, 'w:gz') as archive:
        for raw in sorted(n for n in names if n):
            name = os.fsdecode(raw)
            path = repo / name
            if path.exists() or path.is_symlink():
                archive.add(path, arcname=name, recursive=False)


def settings():
    # Reuse the non-executable config parser and repository path resolution.
    script = '''. "$1/scripts/lib/runtime.sh"
runtime_init || exit
for repo_name in TheSkyBlessing Asset Asset-AnimatedJava; do ds_repo_path "$repo_name" || exit; done
printf '%s\\n' "${ACCEPT_EULA:-false}" "${JAVA_BIN:-java}"
'''
    env = dict(os.environ, DEVSPACE_ROOT=str(ROOT))
    lines = subprocess.check_output(['sh', '-c', script, 'sh', str(ROOT)], env=env).decode().splitlines()
    if len(lines) != 5:
        raise ValueError('unexpected runtime settings')
    return dict(zip(REPOS, map(Path, lines[:3]))), lines[3], lines[4]


class Rcon:
    def __init__(self, port, password):
        self.sock = socket.create_connection(('127.0.0.1', port), 5)
        self.sock.settimeout(15)
        try:
            self.send(1, 3, password)
            while True:
                ident, kind, _ = self.receive()
                if ident == -1:
                    raise RuntimeError('RCON authentication failed')
                if kind == 2:
                    break
        except BaseException:
            self.sock.close()
            raise
        self.seq = 1

    def read(self, count):
        result = b''
        while len(result) < count:
            data = self.sock.recv(count - len(result))
            if not data:
                raise EOFError('RCON closed')
            result += data
        return result

    def send(self, ident, kind, text):
        data = struct.pack('<ii', ident, kind) + text.encode() + b'\0\0'
        self.sock.sendall(struct.pack('<i', len(data)) + data)

    def receive(self):
        size, = struct.unpack('<i', self.read(4))
        if not 10 <= size <= 4 * 1024 * 1024:
            raise ValueError('invalid RCON packet size')
        data = self.read(size)
        ident, kind = struct.unpack('<ii', data[:8])
        return ident, kind, data[8:-2].decode(errors='replace')

    def command(self, text):
        self.seq += 2
        self.send(self.seq, 2, text)
        ident, _, first = self.receive()
        if ident != self.seq:
            raise RuntimeError('unexpected RCON response')
        # A second request marks the end of potentially fragmented output.
        self.send(self.seq + 1, 2, '')
        parts = [first]
        while True:
            ident, _, text = self.receive()
            if ident == self.seq + 1:
                return ''.join(parts)
            if ident != self.seq:
                raise RuntimeError('unexpected RCON response')
            parts.append(text)


def wait_for(test, timeout, description):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if test():
            return
        time.sleep(.1)
    raise TimeoutError(description)


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def validate(scenario):
    if not isinstance(scenario.get('name'), str) or not scenario.get('scope'):
        raise ValueError('scenario requires name and scope')
    names = scenario.get('players', [])
    if len(names) != len(set(names)) or any(not re.fullmatch(r'[A-Za-z0-9_]{1,16}', n) for n in names):
        raise ValueError('invalid or duplicate player names')
    if not scenario.get('steps'):
        raise ValueError('scenario requires steps')
    for step in scenario['steps']:
        if not step.get('name') or sum(k in step for k in ('commands', 'ticks')) != 1:
            raise ValueError('step requires name and commands or ticks')
        if 'ticks' in step:
            if type(step['ticks']) is not int or not 1 <= step['ticks'] <= 72000:
                raise ValueError('invalid tick count')
        else:
            if not isinstance(step['commands'], list) or not step['commands']:
                raise ValueError('commands must be a nonempty list')
            if any(not isinstance(c, str) or any(x in c for x in '\r\n\0') for c in step['commands']):
                raise ValueError('commands must be single lines')
            if not step.get('expect'):
                raise ValueError('command steps require expected output')
            for pattern in step['expect']:
                re.compile(pattern)


def run_steps(rcon, scenario, result, result_path):
    for step in scenario['steps']:
        record = {'name': step['name'], 'input': step, 'output': [], 'passed': False}
        result['steps'].append(record)
        save(result_path, result)
        print('verify: ' + step['name'], flush=True)
        try:
            if 'ticks' in step:
                record['output'].append(rcon.command('tick freeze'))
                before = rcon.command('time query gametime')
                record['output'].append(before)
                start = int(re.search(r'The time is (\d+)', before)[1])
                response = rcon.command(f"tick step {step['ticks']}")
                record['output'].append(response)
                if 'Stepping' not in response:
                    raise AssertionError('tick step did not start')
                # A frozen tick query alone cannot establish that step N has completed.
                def finished():
                    response = rcon.command('time query gametime')
                    current = int(re.search(r'The time is (\d+)', response)[1])
                    elapsed = (current - start) % 2147483647
                    if elapsed >= step['ticks']:
                        record['output'].append(response)
                        record['actualTicks'] = elapsed
                        if elapsed != step['ticks']:
                            raise AssertionError('advanced more ticks than requested')
                        return True
                    return False
                wait_for(finished, max(180, step['ticks'] / 20 + 60), 'tick step completion')
            else:
                for command in step['commands']:
                    response = rcon.command(command)
                    record['output'].append(response)
                    if re.search(r'Incorrect argument for command|Unknown or incomplete command|Unknown function|Expected integer', response):
                        raise AssertionError('console command failed: ' + command)
                observed = '\n'.join(record['output'])
                for pattern in step['expect']:
                    if re.search(pattern, observed) is None:
                        raise AssertionError('missing expected output: ' + pattern)
            record['passed'] = True
        finally:
            save(result_path, result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario', type=Path)
    parser.add_argument('--retry-of', type=Path, help='previous result.json (records recovery history)')
    args = parser.parse_args()
    scenario = json.loads(args.scenario.read_text())
    validate(scenario)
    if sys.platform != 'linux':
        raise RuntimeError('verification runner currently supports Linux / DevContainer')
    if args.retry_of and not args.retry_of.is_file():
        raise ValueError('--retry-of must identify an existing result.json')
    runs = ROOT / '.runtime/verification-runs'
    runs.mkdir(exist_ok=True, parents=True)
    # Serialize verification and dependency installation; the OS releases on exit.
    lock = (runs / 'runner.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError('another verification is running')
    def interrupted(signum, frame):
        raise KeyboardInterrupt('signal ' + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    work = Path(tempfile.mkdtemp(prefix='run-', dir=runs))
    result_path = work / 'result.json'
    result = {'status': 'running', 'scope': scenario['scope'], 'steps': [],
              'scenario': str(args.scenario.resolve()), 'scenarioSha256': digest(args.scenario),
              'retryOf': str(args.retry_of.resolve()) if args.retry_of else None,
              'startedAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    save(work / 'scenario.json', scenario)
    save(result_path, result)
    print('verify: evidence ' + str(work), flush=True)
    server = clients = rcon = None
    handles = []
    repos = {}
    try:
        repos, accepted, java = settings()
        eula = ROOT / '.runtime/eula.txt'
        if accepted != 'true' and (not eula.exists() or not re.search(r'^eula=true\s*$', eula.read_text(), re.M)):
            raise RuntimeError('Minecraft EULA acceptance is required in the normal environment')
        result['repositories'] = {name: {'path': str(path), **snapshot(path)} for name, path in repos.items()}
        result['runnerFiles'] = {str(p.relative_to(ROOT)): digest(p) for p in
                                 [ROOT / 'scripts/server.sh', ROOT / 'scripts/lib/runtime.sh',
                                  ROOT / 'scripts/lib/common.sh', *Path(__file__).parent.glob('*.py'),
                                  *Path(__file__).parent.glob('*.cjs'), *Path(__file__).parent.glob('*.json')]}
        for name, path in repos.items():
            patch = subprocess.check_output(['git', '-C', str(path), 'diff', '--binary', 'HEAD'])
            (work / (name + '.patch')).write_bytes(patch)
            archive_changes(path, work / (name + '.changes.tar.gz'))
        save(result_path, result)
        (work / 'scripts').symlink_to(ROOT / 'scripts', target_is_directory=True)
        (work / '.runtime').mkdir()
        (work / '.cache').mkdir()
        jar = ROOT / '.cache/server-1.20.4.jar'
        if jar.exists():
            (work / '.cache' / jar.name).symlink_to(jar)
        port, rport = free_port(), free_port()
        while rport == port:
            rport = free_port()
        password = secrets.token_hex(20)
        keys = ('THE_SKY_BLESSING_PATH', 'ASSET_PATH', 'ANIMATED_JAVA_PATH')
        conf = [f'{key}={repos[name]}' for key, name in zip(keys, REPOS)]
        conf += ['ACCEPT_EULA=true', 'JAVA_XMS=512M', 'JAVA_XMX=4G', f'JAVA_BIN={java}', f'SERVER_PORT={port}']
        pack = ROOT / '.cache/resources.zip'
        if pack.exists():
            conf += ['RESOURCEPACK_URI=' + pack.as_uri()]
        (work / 'devspace.local.conf').write_text('\n'.join(conf) + '\n')
        props = ['server-ip=127.0.0.1', 'online-mode=false', 'enable-rcon=true',
                 f'rcon.port={rport}', f'rcon.password={password}', 'view-distance=2',
                 'simulation-distance=2', 'level-type=minecraft:flat', 'generate-structures=false',
                 'spawn-protection=0', 'sync-chunk-writes=false',
                 'generator-settings={"layers":[{"block":"minecraft:bedrock","height":1},{"block":"minecraft:dirt","height":2},{"block":"minecraft:grass_block","height":1}],"biome":"minecraft:plains"}']
        (work / '.runtime/server.properties').write_text('\n'.join(props) + '\n')
        result['runtime'] = {'world': str(work / '.runtime/world'), 'port': port,
                             'javaXmx': '4G', 'java': java, 'protocolClients': scenario.get('players', [])}
        env = {k: v for k, v in os.environ.items() if not k.startswith(('DEVSPACE_', 'RESOURCEPACK_', 'JAVA_'))
               and k not in (*keys, 'WORLD_PATH', 'SERVER_PORT', 'ACCEPT_EULA')}
        env.update(DEVSPACE_ROOT=str(work), DEVSPACE_CONFIG=str(work / 'devspace.local.conf'))
        server_log = work / 'server.log'
        log = server_log.open('w'); handles.append(log)
        server = subprocess.Popen(['sh', str(ROOT / 'scripts/server.sh')], cwd=work, env=env,
                                  stdin=subprocess.PIPE, stdout=log, stderr=log, start_new_session=True)
        result['serverPid'] = server.pid
        save(result_path, result)
        def ready():
            if server.poll() is not None:
                raise RuntimeError('server exited during startup; see server.log')
            return 'Done (' in server_log.read_text(errors='replace')
        wait_for(ready, 180, 'server startup')
        rcon = Rcon(rport, password)
        rcon.command('tick freeze')
        rcon.sock.close()
        rcon = None
        if scenario.get('players'):
            deps = ROOT / '.cache/verification-client'
            deps.mkdir(exist_ok=True)
            for name in ('package.json', 'package-lock.json'):
                shutil.copyfile(ROOT / 'scripts/verification' / name, deps / name)
            dep_log = (work / 'dependencies.log').open('w'); handles.append(dep_log)
            subprocess.run(['npm', 'ci', '--ignore-scripts', '--no-audit', '--no-fund', '--prefix', str(deps)],
                           stdout=dep_log, stderr=dep_log, check=True, timeout=120)
            client_log = work / 'clients.log'
            clog = client_log.open('w'); handles.append(clog)
            clients = subprocess.Popen(['node', str(ROOT / 'scripts/verification/clients.cjs'),
                        str(deps / 'node_modules/minecraft-protocol'), str(port), *scenario['players']],
                        stdout=clog, stderr=clog, start_new_session=True)
            def joined():
                if clients.poll() is not None:
                    raise RuntimeError('clients exited; see clients.log')
                text = client_log.read_text()
                return all('READY ' + n in text for n in scenario['players'])
            wait_for(joined, 60, 'protocol clients login')
        if re.search(r'Failed to load function|Parsing error|Couldn.t load tag', server_log.read_text()):
            raise RuntimeError('datapack load error; see server.log')
        rcon = Rcon(rport, password)
        run_steps(rcon, scenario, result, result_path)
        result['status'] = 'passed'
    except (Exception, KeyboardInterrupt) as e:
        result['status'] = 'failed'
        result['error'] = f'{type(e).__name__}: {e}'
        print('verify: ' + result['error'], file=sys.stderr, flush=True)
    finally:
        # Only signal the process groups created by this runner. Never delete locks.
        if rcon:
            rcon.sock.close()
        if server:
            shutdown = []
            if server.poll() is None:
                try:
                    server.stdin.write(b'stop\n'); server.stdin.flush()
                    shutdown.append('stop')
                    server.wait(timeout=60)
                except (BrokenPipeError, subprocess.TimeoutExpired):
                    os.killpg(server.pid, signal.SIGTERM); shutdown.append('TERM')
                    try:
                        server.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        os.killpg(server.pid, signal.SIGKILL); shutdown.append('KILL')
                        server.wait(timeout=10)
            result['shutdown'] = shutdown
            result['serverExitCode'] = server.returncode
            result['allDimensionsSaved'] = 'All dimensions are saved' in (work / 'server.log').read_text(errors='replace')
            if server.returncode != 0 or not result['allDimensionsSaved'] or 'TERM' in shutdown:
                result['status'] = 'failed'
        if clients and clients.poll() is None:
            clients.terminate()
            try:
                clients.wait(timeout=5)
            except subprocess.TimeoutExpired:
                clients.kill(); clients.wait()
        if repos and 'repositories' in result:
            try:
                check_repository_changes(repos, result)
            except Exception as e:
                result['status'] = 'failed'; result['snapshotError'] = str(e)
        for handle in handles:
            handle.close()
        result['finishedAt'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        save(result_path, result)
        lock.close()
    print('verify: ' + result['status'] + ' — ' + str(result_path), flush=True)
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
