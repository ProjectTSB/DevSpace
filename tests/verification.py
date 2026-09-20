"""Checks for false positives and lost evidence in the scenario interpreter."""
import importlib.util
import json
from pathlib import Path
import tempfile
import subprocess
import tarfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('verification', Path(__file__).resolve().parents[1] / 'scripts/verification/run.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class Replies:
    def __init__(self, *replies):
        self.replies = iter(replies)

    def command(self, text):
        reply = next(self.replies)
        if isinstance(reply, Exception):
            raise reply
        return reply


class Verification(unittest.TestCase):
    def test_long_tick_steps_allow_enough_wall_time(self):
        scenario = {'steps': [{'name': 'long timer', 'ticks': 72000}]}
        with tempfile.TemporaryDirectory() as tmp:
            def finish(test, timeout, description):
                self.assertGreater(timeout, 72000 / 20)
                self.assertTrue(test())
            with patch.object(runner, 'wait_for', side_effect=finish):
                runner.run_steps(Replies('The game is frozen', 'The time is 100',
                                        'Stepping 72000 tick(s)', 'The time is 72100'),
                                 scenario, {'steps': []}, Path(tmp) / 'result.json')

    def test_tick_overshoot_is_a_failure(self):
        scenario = {'steps': [{'name': 'one tick', 'ticks': 1}]}
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'result.json'
            with self.assertRaises(AssertionError):
                runner.run_steps(Replies('The game is frozen', 'The time is 100',
                                        'Stepping 1 tick(s)', 'The time is 102'),
                                 scenario, {'steps': []}, p)
            step = json.loads(p.read_text())['steps'][0]
            self.assertFalse(step['passed'])
            self.assertEqual(step['actualTicks'], 2)

    def test_archive_keeps_untracked_contents_without_changing_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / 'repo'; repo.mkdir()
            def git(*args):
                return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.DEVNULL)
            git('init')
            (repo / 'tracked').write_text('before')
            git('add', 'tracked')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                '-c', 'commit.gpgsign=false', 'commit', '-m', 'fixture')
            (repo / 'tracked').write_text('after')
            (repo / 'new').write_text('untracked content')
            before = runner.digest(repo / '.git/index')
            dest = Path(tmp) / 'changes.tar.gz'
            runner.archive_changes(repo, dest)
            with tarfile.open(dest) as archive:
                self.assertEqual(archive.extractfile('tracked').read(), b'after')
                self.assertEqual(archive.extractfile('new').read(), b'untracked content')
            self.assertEqual(before, runner.digest(repo / '.git/index'))

    def test_command_error_cannot_be_hidden_by_later_success(self):
        scenario = {'steps': [{'name': 'bad command', 'commands': ['invalid', 'query'], 'expect': ['OK']}]}
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'result.json'
            with self.assertRaises(AssertionError):
                runner.run_steps(Replies('Incorrect argument for command', 'OK'), scenario, {'steps': []}, p)
            self.assertFalse(json.loads(p.read_text())['steps'][0]['passed'])

    def test_previous_success_does_not_satisfy_later_step(self):
        scenario = {'steps': [
            {'name': 'first', 'commands': ['query'], 'expect': ['OK']},
            {'name': 'second', 'commands': ['query'], 'expect': ['OK']}]}
        result = {'steps': []}
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'result.json'
            with self.assertRaises(AssertionError):
                runner.run_steps(Replies('OK', 'wrong'), scenario, result, p)
            saved = json.loads(p.read_text())
            self.assertTrue(saved['steps'][0]['passed'])
            self.assertFalse(saved['steps'][1]['passed'])
            self.assertEqual(saved['steps'][1]['output'], ['wrong'])

    def test_disconnect_preserves_partial_observations(self):
        scenario = {'steps': [{'name': 'disconnected', 'commands': ['one', 'two'], 'expect': ['OK']}]}
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'result.json'
            with self.assertRaises(EOFError):
                runner.run_steps(Replies('first response', EOFError()), scenario, {'steps': []}, p)
            saved = json.loads(p.read_text())['steps'][0]
            self.assertFalse(saved['passed'])
            self.assertEqual(saved['output'], ['first response'])

    def test_multiline_commands_and_unchecked_steps_are_rejected(self):
        for step in ({'commands': ['say ok\nstop'], 'expect': ['ok']}, {'commands': ['say ok']}):
            with self.assertRaises(ValueError):
                runner.validate({'name': 'invalid', 'scope': 'test', 'steps': [{'name': 'test', **step}]})


if __name__ == '__main__':
    unittest.main()
