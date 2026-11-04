"""OpenAI-compatible facade over Scio's native MCP tool calls.

OpenCode remains responsible for executing tools and asking for permission.
"""
import hashlib
import json
import threading
import time
import uuid
from http.server import ThreadingHTTPServer

import scio_console as scio
import scio_provider as legacy
from scio_native import NativeClient


def normalize(messages):
    result=[]
    for m in messages:
        content=m.get('content')
        if isinstance(content,list):
            if any(p.get('type')!='text' for p in content):raise ValueError('Native provider currently supports text only')
            content='\n'.join(p.get('text','') for p in content)
        row={'role':m['role'],'content':content or ''}
        if m.get('tool_calls'):row['tool_calls']=m['tool_calls']
        if m.get('tool_call_id'):row['tool_call_id']=m['tool_call_id']
        result.append(row)
    return result


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


class NativeProvider:
    def __init__(self, token, runtime, state_dir=None):
        self.token,self.runtime=token,runtime
        self.state_dir=state_dir or scio.DATA_DIR/'native-provider'
        self.clients={}
        self.lock=threading.Lock()
        self.conversation_locks={}

    def complete(self,body):
        key=self.conversation_key(body)
        with self.lock:
            lock=self.conversation_locks.setdefault(key,threading.Lock())
        with lock:return self._complete(body,key)

    @staticmethod
    def conversation_key(body):
        # Stable through tool continuations; unrelated first user turns run independently.
        messages=normalize(body['messages'])
        first=next((m for m in messages if m['role']=='user'),None)
        instructions=[m for m in messages if m['role'] in ('system','developer')]
        return digest([body.get('model','anthropic-strong'),body.get('tools') or [],instructions,first])

    def _complete(self,body,key):
        model=scio.validate_model(body.get('model','anthropic-strong'))
        messages=normalize(body['messages'])
        tools=[]
        for tool in body.get('tools') or []:
            fn=tool['function'];tools.append({'name':fn['name'],'description':fn.get('description',''),'inputSchema':fn.get('parameters',{'type':'object','properties':{}})})
        instructions='\n\n'.join(m['content'] for m in messages if m['role'] in ('system','developer'))
        if key not in self.clients:
            self.clients[key]=NativeClient(self.token,self.runtime,tools,model,instructions,state_file=self.state_dir/f'{key}.json')
        client=self.clients[key]
        client.prepare()
        prefixes=client.state.setdefault('prefix_sessions',{})
        session=None;prefix_count=0
        for size in range(len(messages),0,-1):
            found=prefixes.get(digest(messages[:size]))
            if found:session=found;prefix_count=size;break
        trailing=[]
        for m in reversed(messages):
            if m['role']!='tool':break
            trailing.insert(0,m)
        if trailing:
            known=[client.state['calls'].get(m.get('tool_call_id')) for m in trailing]
            if all(known):
                sessions={c['session_id'] for c in known}
                if len(sessions)!=1:raise ValueError('Tool results span multiple Scio chats')
                session=sessions.pop()
                follow=[]
                for m in trailing:
                    response=client.submit(m['tool_call_id'],m['content'])
                    if response['calls'] or response['text']:follow.append(response)
                answer=follow[-1] if follow else client.continue_after_results(session)
            else:
                raise ValueError('Unknown native tool call ID. Restore the matching provider state or start a new OpenCode chat.')
        else:
            if not session:session=client.new_chat('OpenCode native tools')
            current=[m for m in messages[prefix_count:] if m['role'] not in ('system','developer')]
            if not current:raise ValueError('No new conversation message; refusing to duplicate a request')
            prompt=current[0]['content'] if len(current)==1 and current[0]['role']=='user' else 'Current client conversation messages:\n'+json.dumps(current,ensure_ascii=False)
            prompt = 'This is a live request from the local coding client. Use the registered local_ MCP tools; tool names in the user request may omit that prefix. These tools access the selected local project, not a Scio browser workspace.\n\n' + prompt
            choice=body.get('tool_choice','auto')
            if choice=='none':prompt+='\nAnswer without calling tools for this turn.'
            elif choice=='required':prompt+='\nUse an appropriate registered native tool for this turn.'
            elif isinstance(choice,dict):prompt+='\nUse the registered tool '+choice['function']['name']+' for this turn.'
            if not body.get('parallel_tool_calls',True):prompt+='\nCall at most one tool in this turn.'
            answer=client.send(session,prompt)
        calls=answer['calls']
        if any(c.get('unsupported') or c['name']=='scio_client_ready' for c in calls):raise ValueError('Scio returned a tool outside the caller catalog; no local execution occurred')
        choice=body.get('tool_choice','auto')
        if choice=='none' and calls:raise ValueError('Model violated tool_choice=none; no local tool was executed')
        if choice=='required' and not calls:raise ValueError('Model did not return a required tool call')
        if isinstance(choice,dict) and (not calls or any(c['name']!=choice['function']['name'] for c in calls)):raise ValueError('Model did not honor the requested tool')
        if not body.get('parallel_tool_calls',True) and len(calls)>1:raise ValueError('Model returned multiple calls with parallel calls disabled')
        message={'role':'assistant','content':None if calls else answer['text']}
        if calls:message['tool_calls']=[{'id':c['id'],'type':'function','function':{'name':c['name'],'arguments':json.dumps(c['arguments'],ensure_ascii=False)}} for c in calls]
        prefixes[digest(messages+normalize([message]))]=session
        client.save()
        return {'id':'chatcmpl-'+uuid.uuid4().hex,'object':'chat.completion','created':int(time.time()),'model':model,'choices':[{'index':0,'message':message,'finish_reason':'tool_calls' if calls else 'stop'}]}

    def close(self):
        errors=[]
        for client in self.clients.values():
            try:client.close()
            except Exception:errors.append(client.persona_id)
        return errors


class Handler(legacy.Handler):
    def do_GET(self):
        if self.path=='/health':return self.reply(200,{'status':'ok','tool_mode':'native-mcp','execution':'client-side'})
        super().do_GET()


def serve(provider,port=8767):
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.complete=provider.complete
    legacy.local_key()
    return server
