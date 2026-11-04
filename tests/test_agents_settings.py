import io
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import scio_console as scio
import settings
from session_console import Console
from workspace_tools import WorkspaceTools
from scio_native import NativeClient
from configure_native_opencode import generate


class AgentSettingsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = patch.object(scio, 'DATA_DIR', self.root / 'data')
        self.data.start()
        args = SimpleNamespace(workspace=str(self.root), model='anthropic-strong',
            allow_write=False, allow_exec=False, allow_network=False, max_steps=5,
            cloudflared=None, public_url=None, discovery_port=0)
        self.console = Console(args)

    def tearDown(self):
        self.console.close()
        self.data.stop()
        self.temp.cleanup()

    def catalog(self, row):
        tools = WorkspaceTools(row['project'])
        self.console.add_agent_tools(row, tools)
        # Delegate permission is independent of child filesystem approvals.
        tools.approve = lambda n, a, e: e in ('read', 'delegate')
        return tools

    def test_nested_agents_return_real_results_without_changing_selection(self):
        c = self.console
        parent = c.new('parent')
        initial = c.active
        def connect(row, refresh=False):
            tools = self.catalog(row)
            def run(chat, prompt, executor, **kw):
                if row.get('depth', 0) < 2:
                    result = executor('agent_spawn', {'prompt':'task', 'title':'child'})
                    status = executor('agent_wait', {'agent_id':result['agent_id'], 'timeout_seconds':3})
                    self.assertEqual(status['status'], 'done')
                    return {'text': 'child said: ' + status['result']}
                return {'text':'GRANDCHILD_RESULT'}
            return SimpleNamespace(run=run), tools
        with patch.object(c, 'connect', side_effect=connect):
            c.start(parent, 'delegate')
            c.jobs[parent['key']].join(5)
        self.assertEqual(parent['status'], 'done', parent.get('error'))
        self.assertIn('GRANDCHILD_RESULT', parent['result'])
        self.assertEqual(len(c.rows), 3)
        self.assertEqual(c.active, initial)
        self.assertEqual(c.rows[-1]['depth'], 2)
        unrelated = c.new('unrelated')
        with self.assertRaisesRegex(ValueError, 'descendant'):
            self.catalog(unrelated).call('agent_status', {'agent_id':c.rows[1]['key']})

    def test_agent_limits_do_not_create_orphan_rows(self):
        c = self.console
        row = c.new()
        tools = self.catalog(row)
        c.settings['max_depth'] = 0
        with self.assertRaisesRegex(ValueError, 'depth'):
            tools.call('agent_spawn', {'prompt':'task'})
        c.settings['max_depth'] = 3
        c.settings['max_children'] = 0
        with self.assertRaisesRegex(ValueError, 'budget'):
            tools.call('agent_spawn', {'prompt':'task'})
        c.settings['max_children'] = 32
        c.settings['max_agents'] = 1
        c.jobs['occupied'] = SimpleNamespace(is_alive=lambda:True)
        try:
            with self.assertRaisesRegex(ValueError, 'slot'):
                tools.call('agent_spawn', {'prompt':'task'})
        finally: c.jobs.clear()
        self.assertEqual(len(c.rows), 1)

    def test_repeated_spawn_with_new_call_id_reuses_worker(self):
        c = self.console
        row = c.new()
        tools = self.catalog(row)
        with patch.object(c, 'start') as start:
            one = tools.call('agent_spawn', {'prompt':'read a.txt', 'title':'reader'})
            two = tools.call('agent_spawn', {'prompt':'read a.txt', 'title':'reader'})
            self.assertEqual(one['agent_id'], two['agent_id'])
            self.assertTrue(two['already_spawned'])
            start.assert_called_once()
            self.assertEqual(len(c.rows), 2)

    def test_missing_thinking_confirmation_is_reported_honestly(self):
        client = NativeClient.__new__(NativeClient)
        client.thinking = 'high'
        client.send_once = MagicMock(return_value={'text':'ok', 'calls':[], 'thinking_confirmed':False})
        with self.assertWarnsRegex(RuntimeWarning, 'did not confirm'):
            result = client.send('chat', 'task')
        self.assertFalse(result['thinking_confirmed'])

    def test_auto_allow_resolves_pending_and_persists(self):
        c = self.console
        result = []
        job = threading.Thread(target=lambda:result.append(c.approvals.ask('child','write',{},'write')))
        job.start()
        deadline = time.monotonic()+3
        while not c.approvals.pending and time.monotonic()<deadline: time.sleep(.01)
        c.setting_set('auto_allow','on')
        job.join(3)
        self.assertEqual(result, [True])
        self.assertTrue(c.approvals.ask('other','shell',{},'execute'))
        self.assertTrue(settings.load()['auto_allow'])
        c.setting_set('auto_allow','off')
        self.assertFalse(c.approvals.auto)

    def test_child_permissions_and_thinking_inherit(self):
        c = self.console
        c.setting_set('thinking','low')
        parent = c.new()
        child = c.new('child',parent=parent)
        with patch('session_console.NativeRuntime'), patch('session_console.NativeClient') as client, patch.object(scio,'get_token',return_value='token'):
            client.return_value.new_chat.return_value='chat'
            _, tools = c.connect(child)
            self.assertEqual(client.call_args.kwargs['options']['thinking'], 'low')
            c.setting_set('auto_allow','on')
            tools.call('write_file',{'path':'child.txt','content':'allowed'})
            self.assertEqual((self.root/'child.txt').read_text(),'allowed')
            with self.assertRaises(ValueError):tools.call('write_file',{'path':'../escape','content':'no'})
        c.clients.clear()
        c.runtimes.clear()

    def test_unsupported_settings_rejected(self):
        for name, value in [('temperature','0.5'),('thinking','ultra'),('max_agents','0'),('max_depth','999')]:
            with self.assertRaises(ValueError):self.console.setting_set(name,value)

    def test_compatibility_config_enables_nested_workers(self):
        import scio_provider
        with patch.object(scio_provider,'KEY_FILE',self.root/'key'), patch.object(scio_provider,'local_key',return_value='key'):
            options={**settings.DEFAULTS,'auto_allow':True,'max_depth':4}
            config=json.loads(generate(self.root,options=options).read_text())
            self.assertEqual(config['default_agent'],'SCIO CODE')
            self.assertEqual(config['subagent_depth'],4)
            self.assertEqual(config['permission'],'allow')
            self.assertEqual(config['agent']['scio-worker']['permission']['task'],'allow')

    def test_server_thinking_tool_is_not_executed_as_local_tool(self):
        client = NativeClient.__new__(NativeClient)
        client.state={'calls':{}}
        client.state_file=None
        client.thinking='high'
        client.token='test'
        client.wire_names={}
        client.tools={}
        events=[{'type':'tool-input-available','toolCallId':'setting','toolName':'set_thinking_level','input':{'level':'high'}},
                {'type':'tool-output-available','toolCallId':'setting','output':'set high'}, {'type':'finish'}]
        response=MagicMock()
        response.__enter__.return_value=response
        response.headers={'Content-Type':'text/event-stream'}
        with patch('scio_native.urlopen',return_value=response), patch.object(scio,'events',return_value=map(json.dumps,events)):
            self.assertEqual(client.stream({'sessionId':'test'})['calls'],[])
        with patch('scio_native.urlopen',return_value=response), patch.object(scio,'events',return_value=map(json.dumps,[events[0],events[-1]])):
            with self.assertRaisesRegex(RuntimeError,'confirm'):client.stream({'sessionId':'test'})

    def test_continuation_carries_actual_receipts_only_for_its_session(self):
        client = NativeClient.__new__(NativeClient)
        own = {'id':'one','name':'agent_wait','arguments':{},'session_id':'a',
               'status':'submitted','output':{'status':'done','result':'ACTUAL_RECEIPT'}}
        other = {**own,'id':'two','session_id':'b','output':'OTHER_SESSION'}
        client.state = {'calls':{'one':own,'two':other}}
        client.save = MagicMock()
        client.send = MagicMock(return_value={'text':'done','calls':[]})
        client.continue_after_results('a')
        text = client.send.call_args.args[1]
        self.assertIn('ACTUAL_RECEIPT', text)
        self.assertNotIn('OTHER_SESSION', text)
        self.assertTrue(own['context_delivered'])
        self.assertNotIn('context_delivered', other)


if __name__ == '__main__':unittest.main()
