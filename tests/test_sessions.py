from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scio_console as scio
from session_console import Console, Approvals
from native_provider import NativeProvider


def args(root):
    return SimpleNamespace(workspace=str(root), model='anthropic-strong',
        allow_write=False, allow_exec=False, allow_network=False, max_steps=4,
        cloudflared=None, public_url=None, discovery_port=0)


class SessionsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = patch.object(scio, 'DATA_DIR', self.root / 'data')
        self.data.start()

    def tearDown(self):
        self.data.stop()
        self.temp.cleanup()

    def test_startup_is_offline_and_project_changes_do_not_move_sessions(self):
        with patch('session_console.NativeRuntime') as runtime:
            console = Console(args(self.root))
            first = console.new('one')
            other = self.root / 'other'
            other.mkdir()
            console.project_set(str(other))
            second = console.new('two')
            self.assertEqual(first['project'], str(self.root))
            self.assertEqual(second['project'], str(other))
            runtime.assert_not_called()
            restored = Console(args(self.root))
            self.assertEqual(len(restored.rows), 2)

    def test_parallel_tasks_and_busy_guard(self):
        console = Console(args(self.root))
        barrier = threading.Barrier(3)
        release = threading.Event()
        client = MagicMock()
        def run(*a, **kw):
            barrier.wait(timeout=4)
            release.wait(4)
            return {'text': 'done'}
        client.run.side_effect = run
        first, second = console.new('one'), console.new('two')
        with patch.object(console, 'connect', return_value=(client, MagicMock())):
            console.start(first, 'hello')
            console.start(second, 'world')
            try:
                barrier.wait(timeout=4)
                with self.assertRaisesRegex(ValueError, 'busy'):
                    console.start(first, 'duplicate')
            finally:
                release.set()
                console.close()
        self.assertEqual(client.run.call_count, 2)

    def test_refresh_preserves_chat_and_ledger_and_never_runs_task(self):
        console = Console(args(self.root))
        row = console.new('saved')
        row['chat'] = 'existing-chat'
        ledger = scio.DATA_DIR / 'console-ledgers' / (row['key'] + '.json')
        saved = {'calls': {'write-1': {'status': 'executed', 'output': 'ok'}}}
        scio.save_json(ledger, saved)
        old, runtime = MagicMock(), MagicMock()
        console.clients[row['key']] = (old, MagicMock())
        console.runtimes[row['key']] = runtime
        with patch('session_console.NativeRuntime') as new_runtime, \
             patch('session_console.NativeClient') as factory, \
             patch.object(scio, 'get_token', return_value='renewed-token'):
            console.start(row, refresh=True)
            console.jobs[row['key']].join(5)
            self.assertFalse(console.jobs[row['key']].is_alive())
            old.close.assert_called_once()
            runtime.close.assert_called_once()
            self.assertEqual(factory.call_args.args[0], 'renewed-token')
            self.assertEqual(factory.call_args.kwargs['state_file'], ledger)
            self.assertEqual(row['chat'], 'existing-chat')
            factory.return_value.new_chat.assert_not_called()
            factory.return_value.run.assert_not_called()
            self.assertEqual(scio.read_json(ledger, {}), saved)
            console.close()

    def test_permission_isolation_and_shutdown_denial(self):
        approvals = Approvals()
        with ThreadPoolExecutor(2) as pool:
            one = pool.submit(approvals.ask, 'one', 'write', {'path':'a'}, 'write')
            two = pool.submit(approvals.ask, 'two', 'write', {'path':'b'}, 'write')
            import time
            deadline = time.monotonic()+3
            while time.monotonic()<deadline:
                with approvals.lock:
                    rows = dict(approvals.pending)
                if len(rows)==2: break
                time.sleep(.01)
            self.assertEqual(len(rows), 2)
            key = next(k for k,r in rows.items() if r['session']=='one')
            approvals.resolve(key, True)
            self.assertTrue(one.result(timeout=2))
            approvals.close()
            self.assertFalse(two.result(timeout=2))
            self.assertFalse(approvals.ask('three','write',{},'write'))

    def test_provider_independent_chats_are_concurrent(self):
        provider = NativeProvider('token', None)
        barrier = threading.Barrier(2)
        def complete(body, key):
            barrier.wait(timeout=3)
            return key
        with patch.object(provider, '_complete', side_effect=complete), ThreadPoolExecutor(2) as pool:
            jobs = [pool.submit(provider.complete, {'messages':[{'role':'user','content':x}]})
                    for x in ['one', 'two']]
            self.assertNotEqual(jobs[0].result(4), jobs[1].result(4))

    def test_provider_continuation_keeps_conversation_lock(self):
        body = {'messages':[{'role':'system','content':'rules'}, {'role':'user','content':'one'}]}
        key = NativeProvider.conversation_key(body)
        body['messages'] += [{'role':'assistant','content':'ok'}, {'role':'user','content':'next'}]
        self.assertEqual(key, NativeProvider.conversation_key(body))

    def test_launcher_has_no_project_prompt(self):
        for name in ['start_scio_code.cmd','start_scio_opencode.cmd']:
            content = (Path(__file__).resolve().parents[1] / name).read_text()
            self.assertNotIn('set /p', content.lower())
            self.assertIn('%*', content)


if __name__ == '__main__':
    unittest.main()
