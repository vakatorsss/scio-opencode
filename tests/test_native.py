import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.error import HTTPError
from urllib.request import Request,urlopen
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from native_transport import Discovery
from workspace_tools import WorkspaceTools
from scio_native import NativeClient
from native_provider import normalize


class ToolsTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.tools=WorkspaceTools(self.root,lambda *_:True)
    def tearDown(self):self.temp.cleanup()
    def test_catalog_is_executable_and_schemas_match(self):
        import jsonschema
        self.assertGreaterEqual(len(self.tools.tools),90)
        for tool in self.tools.definitions():
            jsonschema.Draft202012Validator.check_schema(tool['inputSchema'])
            self.assertTrue(callable(self.tools.tools[tool['name']]['_fn']))
    def test_permission_denial_has_no_side_effect(self):
        denied=WorkspaceTools(self.root)
        result=denied.call('write_file',{'path':'no.txt','content':'secret'})
        self.assertFalse(result['ok']);self.assertFalse((self.root/'no.txt').exists())
    def test_containment_and_sensitive_paths(self):
        for path in ['../outside','.env','.git/config','scio_data/token.dpapi']:
            with self.assertRaises(ValueError):self.tools.path(path)
    def test_symlink_escape(self):
        with tempfile.TemporaryDirectory() as outside:
            try:(self.root/'link').symlink_to(outside,target_is_directory=True)
            except OSError:self.skipTest('Symlink privileges unavailable')
            with self.assertRaises(ValueError):self.tools.write('link/escape.txt','no')
    def test_edits_and_conflict_detection(self):
        self.tools.call('write_file',{'path':'a.py','content':'x = 1\n'})
        self.tools.call('replace_text',{'path':'a.py','old':'x = 1','new':'x = 2'})
        with self.assertRaises(ValueError):self.tools.call('replace_text',{'path':'a.py','old':'x = 1','new':'oops'})
        self.assertEqual((self.root/'a.py').read_text(),'x = 2\n')
        self.assertTrue(self.tools.call('python_syntax_check',{'path':'a.py'})['valid'])
    def test_csv_and_json_roundtrip(self):
        self.tools.call('csv_write',{'path':'items.csv','rows':[{'name':'a','amount':3},{'name':'b','amount':7}]})
        self.assertEqual(self.tools.call('csv_statistics',{'path':'items.csv','column':'amount'})['sum'],10)
        self.assertEqual(self.tools.call('json_set',{'text':'{"a":[1,2]}','keys':['a',1],'value':'9'}),{'a':[1,9]})
    def test_zip_traversal_is_rejected_before_writes(self):
        with zipfile.ZipFile(self.root/'bad.zip','w') as archive:
            archive.writestr('okay.txt','ok');archive.writestr('../escape.txt','bad')
        with self.assertRaises(ValueError):self.tools.call('zip_extract',{'path':'bad.zip','destination':'unpacked'})
        self.assertFalse((self.root/'unpacked').exists())
    def test_shell_timeout_and_output_bound(self):
        result=self.tools.call('run_command',{'argv':[sys.executable,'-c','import time; time.sleep(5)'],'timeout':1})
        self.assertTrue(result['timeout'])
    def test_no_implicit_command_approval(self):
        denied=WorkspaceTools(self.root)
        self.assertFalse(denied.call('python_run_snippet',{'code':'raise Exception("must not run")'})['ok'])
    def test_python_project_imports_work_in_scripts_and_snippets(self):
        (self.root/'helper.py').write_text('VALUE = 323\n')
        (self.root/'main.py').write_text('from helper import VALUE\nprint(VALUE)\n')
        script=self.tools.call('python_run_script',{'path':'main.py'})
        snippet=self.tools.call('python_run_snippet',{'code':'from helper import VALUE; print(VALUE)'})
        self.assertIn('323',json.dumps(script))
        self.assertIn('323',json.dumps(snippet))


class DiscoveryTest(unittest.TestCase):
    def test_discovery_cannot_execute_tools(self):
        discovery=Discovery()
        try:
            path=discovery.register([{'name':'secret','description':'Test','inputSchema':{'type':'object'}}])
            def request(method):
                req=Request(f'http://127.0.0.1:{discovery.port}'+path,data=json.dumps({'jsonrpc':'2.0','id':1,'method':method}).encode(),headers={'Content-Type':'application/json'})
                with urlopen(req) as r:return json.load(r)['result']
            self.assertEqual(request('tools/list')['tools'][0]['name'],'secret')
            self.assertTrue(request('tools/call')['isError'])
            with self.assertRaises(HTTPError):urlopen(Request(f'http://127.0.0.1:{discovery.port}/wrong',data=b'{}'))
        finally:discovery.close()


class LedgerTest(unittest.TestCase):
    def client(self):
        client=NativeClient.__new__(NativeClient)
        client.state_file=None
        client.state={'calls':{'a':{'id':'a','name':'write_file','arguments':{},'status':'requested'}}}
        return client
    def test_completed_call_is_not_reexecuted(self):
        client=self.client();executions=[]
        def execute(*args):executions.append(args);return {'ok':True}
        call={'id':'a','name':'write_file','arguments':{}}
        client.execute(call,execute);client.execute(call,execute)
        self.assertEqual(len(executions),1)
    def test_interrupted_call_is_not_reexecuted(self):
        client=self.client();client.state['calls']['a']['status']='executing'
        with self.assertRaises(RuntimeError):client.execute({'id':'a'},lambda *_:self.fail('must not execute'))
    def test_provider_rejects_multimodal_input(self):
        with self.assertRaises(ValueError):normalize([{'role':'user','content':[{'type':'image_url','image_url':{}}]}])
    def test_final_allowed_step_can_complete(self):
        client=self.client()
        call={'id':'a','name':'write_file','arguments':{}}
        client.send=lambda *_:{'calls':[call],'text':''}
        client.submit=lambda *_:{'calls':[],'text':'finished'}
        result=client.run('session','task',lambda *_:{'ok':True},max_steps=1)
        self.assertEqual(result['text'],'finished')


if __name__=='__main__':unittest.main()
