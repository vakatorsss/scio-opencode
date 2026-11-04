"""Write an isolated OpenCode v1 configuration; never overwrite user settings."""
import json
from pathlib import Path
import sys
import scio_provider as provider
import settings
from workspace_tools import WorkspaceTools


def generate(workspace,port=8767,instance=None,options=None):
    options=options or settings.load()
    provider.local_key()
    key_path=provider.KEY_FILE.resolve().as_posix()
    config={'$schema':'https://opencode.ai/config.json','provider':{'scio-native':{'npm':'@ai-sdk/openai-compatible','name':'Scio native tools','options':{'baseURL':f'http://127.0.0.1:{port}/v1','apiKey':'{file:'+key_path+'}'},'models':{key:{'name':'SCIO CODE / '+name,'tool_call':True,'limit':{'context':64000,'output':8192}} for key,name in provider.scio.MODELS.items()}}},'model':'scio-native/anthropic-strong','mcp':{'scio_workspace':{'type':'local','command':[sys.executable,str(Path(__file__).with_name('workspace_mcp.py').resolve()),'--workspace',str(Path(workspace).resolve())],'enabled':True}},'permission':{'scio_workspace_*':'ask','bash':'ask','edit':'ask','external_directory':'ask'}}
    for name,tool in WorkspaceTools(workspace).tools.items():
        if tool['_effect']=='read':config['permission']['scio_workspace_'+name]='allow'
    # The legacy Scio-as-a-tool server is unnecessary when Scio is the model.
    config['mcp']['scio']={'enabled':False}
    config['provider']['scio-native']['name']='SCIO CODE'
    config['default_agent']='SCIO CODE'
    config['subagent_depth']=options['max_depth']
    # Specific rule follows wildcard: the worker is allowed to delegate recursively.
    permissions={'task':{'*':'ask','scio-worker':'allow'}}
    config['agent']={
        'SCIO CODE':{'description':'SCIO CODE coding agent with parallel delegation', 'mode':'primary',
            'prompt':'You are SCIO CODE. Use task with scio-worker for independent work; background=true permits parallel tasks. Give each worker a self-contained task and non-overlapping files. Collect actual results before claiming completion.',
            'permission':permissions,'steps':options['max_steps']},
        'scio-worker':{'description':'SCIO CODE worker that may delegate independent subtasks', 'mode':'subagent',
            'prompt':'You are a SCIO CODE subagent. Complete the assigned task and return concrete results. You may delegate independent subtasks to scio-worker with background=true. Avoid overlapping file edits.',
            'permission':permissions,'steps':options['max_steps']}}
    if options['auto_allow']:
        config['permission']='allow'
        for agent in config['agent'].values():agent['permission']={'*':'allow','task':'allow'}
    destination=provider.scio.DATA_DIR/(('opencode.native.'+instance+'.json') if instance else 'opencode.native.json')
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(config,indent=2)+'\n',encoding='utf-8')
    return destination


if __name__=='__main__':print(generate(sys.argv[1] if len(sys.argv)>1 else '.'))
