import base64
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
import uuid

import scio_console as scio
import settings
from scio_app import configure
from scio_native import NativeClient
from session_console import Console


class EndpointControlsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = patch.object(scio, 'DATA_DIR', self.root)
        self.data.start()
        self.uid = str(uuid.uuid4())
        self.pid = str(uuid.uuid4())
        self.token = 'x.' + base64.urlsafe_b64encode(json.dumps({'sub': self.uid}).encode()).decode().rstrip('=') + '.x'

    def tearDown(self):
        self.data.stop()
        self.temp.cleanup()

    def client(self, **options):
        self.request = MagicMock(return_value=[{'id': self.pid}])
        with patch('scio_native.request_json', self.request):
            return NativeClient(self.token, SimpleNamespace(register=lambda _: 'https://example.invalid/mcp'), [], options=options)

    def test_private_persona_preserves_harness_and_maps_controls(self):
        client = self.client(locale='cs', instructions='Keep the summary under 40 words.',
                             web_search='off', tone='direct', conciseness='short', thinking='high')
        cfg = self.request.call_args.args[3]
        self.assertIn('Wait for real results', cfg['system_prompt'])
        self.assertIn('Keep the summary under 40 words.', cfg['system_prompt'])
        self.assertEqual(cfg['visibility'], 'private')
        self.assertEqual(cfg['creator_id'], self.uid)
        self.assertEqual(cfg['tone'], 'direct')
        self.assertEqual(cfg['conciseness'], 'short')
        self.assertIn('web-search', cfg['skill_config']['disabled'])
        self.assertIn('set-thinking-level', cfg['skill_config']['always_on'])
        self.assertEqual(client.locale, 'cs')

    def test_search_modes_are_mutually_exclusive_and_do_not_enable_workspace(self):
        for mode, field in [('off', 'disabled'), ('auto', 'available'), ('on', 'always_on')]:
            self.client(web_search=mode)
            skills = self.request.call_args.args[3]['skill_config']
            self.assertIn('code-workspace', skills['disabled'])
            self.assertEqual([name for name, values in skills.items() if 'web-search' in values], [field])

    def test_locale_and_selection_sent_on_open_send_and_tool_continuation(self):
        client = self.client(locale='cs')
        sid = str(uuid.uuid4())
        response = MagicMock()
        response.__enter__.return_value = io.BytesIO(json.dumps({'id': sid}).encode())
        with patch('scio_native.urlopen', return_value=response) as network:
            client.new_chat()
            command = json.loads(network.call_args.args[0].data)['command']
            self.assertEqual(command['locale'], 'cs')
        client.stream = MagicMock(return_value={'text': '', 'calls': []})
        client.send_once(sid, 'test')
        self.assertEqual(client.stream.call_args.args[0]['locale'], 'cs')
        client.state['calls']['one'] = {'session_id': sid, 'name': 'test', 'status': 'requested'}
        client.submit('one', {'ok': True})
        command = client.stream.call_args.args[0]
        self.assertEqual(command['locale'], 'cs')
        self.assertEqual(command['personaId'], self.pid)
        self.assertEqual(command['builtInAgentId'], 'custom')

    def test_server_search_is_observed_without_local_execution_or_result_submission(self):
        client = self.client(web_search='on')
        events = [{'type': 'tool-input-available', 'toolCallId': 'search', 'toolName': 'browserSearch', 'input': {'query': 'IANA'}},
                  {'type': 'tool-output-available', 'toolCallId': 'search', 'output': {'results': []}},
                  {'type': 'text-delta', 'delta': 'Done'}, {'type': 'finish'}]
        response = MagicMock(); response.__enter__.return_value = response
        response.headers = {'Content-Type': 'text/event-stream'}
        with patch('scio_native.urlopen', return_value=response), patch.object(scio, 'events', return_value=map(json.dumps, events)):
            result = client.stream({'sessionId': str(uuid.uuid4())})
        self.assertEqual(result['calls'], [])
        self.assertEqual(client.state['calls'], {})
        self.assertEqual(result['remote_tools'], [{'name': 'browserSearch', 'status': 'completed'}])

    def test_children_keep_parent_snapshot_when_defaults_change(self):
        args = SimpleNamespace(workspace=str(self.root), model='google-weak')
        console = Console(args)
        try:
            console.setting_set('locale', 'cs')
            console.setting_set('instructions', 'Use short summaries.')
            parent = console.new()
            console.setting_set('locale', 'en')
            child = console.new(parent=parent)
            other = console.new()
            self.assertEqual(child['options']['locale'], 'cs')
            self.assertEqual(child['options']['instructions'], 'Use short summaries.')
            self.assertEqual(other['options']['locale'], 'en')
            self.assertIsNot(child['options'], parent['options'])
        finally: console.close()

    def test_multiline_settings_roundtrip_and_invalid_value_does_not_overwrite(self):
        path = self.root / 'preferences.txt'
        path.write_text('Use Czech.\nKeep summaries short.', encoding='utf-8')
        configure(['instructions-file', str(path)])
        configure(['set', 'locale', 'cs'])
        before = settings.load()
        self.assertEqual(before['instructions'], path.read_text())
        with self.assertRaises(ValueError): configure(['set', 'conciseness', 'brief'])
        self.assertEqual(settings.load(), before)
        configure(['clear-instructions'])
        self.assertEqual(settings.load()['instructions'], '')

    def test_close_updates_only_owned_persona(self):
        client = self.client()
        with patch('scio_native.request_json') as request: client.close()
        self.assertIn('&creator_id=eq.' + self.uid, request.call_args.args[1])


if __name__ == '__main__': unittest.main()
