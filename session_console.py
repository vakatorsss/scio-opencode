"""Concurrent terminal sessions, with all input owned by the main thread."""
import json
from pathlib import Path
import threading
import uuid
import sys
import hashlib

import scio_console as scio
from native_transport import NativeRuntime
from scio_native import NativeClient
from workspace_tools import WorkspaceTools
import settings


class Approvals:
    def __init__(self):
        self.lock = threading.Lock()
        self.pending = {}
        self.closed = False
        self.auto = False

    def ask(self, session, name, arguments, effect):
        event = threading.Event()
        with self.lock:
            if self.closed:
                return False
            if self.auto: return True
            key = uuid.uuid4().hex[:8]
            row = {'event': event, 'allowed': False, 'session': session,
                   'tool': name, 'arguments': arguments, 'effect': effect}
            self.pending[key] = row
        print(f'\n[{session}] Permission {key}: {effect} / {name}\n'
              + json.dumps(arguments, ensure_ascii=False)[:6000]
              + f'\n/approve {key} or /deny {key}', flush=True)
        event.wait()
        return row['allowed']

    def resolve(self, key, allowed):
        with self.lock:
            row = self.pending.pop(key)
            row['allowed'] = allowed
            row['event'].set()

    def close(self):
        with self.lock:
            self.closed = True
            for row in self.pending.values():
                row['event'].set()
            self.pending.clear()


class Console:
    def __init__(self, args):
        self.args = args
        self.settings = settings.load()
        for name in settings.DEFAULTS:
            value = getattr(args, name, None)
            if value is not None: self.settings[name] = settings.validate(name, value)
        self.path = scio.DATA_DIR / 'console-sessions.json'
        saved = scio.read_json(self.path, {})
        self.project = str(Path(args.workspace or saved.get('project', '.')).resolve())
        self.model = args.model
        self.rows = saved.get('sessions', [])
        for row in self.rows:
            if row.get('status') == 'running': row['status'] = 'interrupted'
        self.active = self.rows[-1]['key'] if self.rows else None
        self.clients = {}
        self.runtimes = {}
        self.jobs = {}
        self.lock = threading.RLock()
        self.approvals = Approvals()
        self.approvals.auto = self.settings['auto_allow']
        self.stopping = threading.Event()

    def save(self):
        with self.lock:
            scio.save_json(self.path, {'project': self.project, 'sessions': self.rows})

    def project_set(self, value):
        root = Path(value.strip().strip('"')).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError('Project must be a directory')
        self.project = str(root)
        self.active = None
        self.save()

    def run_prompt(self, prompt):
        """One-shot mode uses the same agent tools; only this thread reads stdin."""
        scio.get_token(interactive=sys.stdin.isatty())
        row = self.new(prompt[:80])
        self.start(row, prompt)
        try:
            while True:
                with self.lock:
                    running = any(j.is_alive() for j in self.jobs.values())
                if not running: break
                with self.approvals.lock: pending = list(self.approvals.pending)
                for key in pending:
                    allow = False
                    if sys.stdin.isatty():
                        try: allow = input(f'Allow operation {key}? [y/N] ').strip().lower() == 'y'
                        except EOFError: pass
                    try: self.approvals.resolve(key, allow)
                    except KeyError: pass
                threading.Event().wait(.1)
            return 0 if row['status'] == 'done' else 1
        finally:
            self.close()
        print('Project for new sessions:', root)

    def new(self, title='SCIO CODE', parent=None, model=None):
        root = Path(parent['project'] if parent else self.project).resolve(strict=True)
        if not root.is_dir():
            raise ValueError('Use /project PATH to select a directory')
        row = {'key': uuid.uuid4().hex, 'title': title, 'project': str(root),
               'model': model or (parent['model'] if parent else self.model), 'chat': None,
               'parent': parent['key'] if parent else None,
               'depth': parent.get('depth', 0) + 1 if parent else 0,
               'thinking': parent.get('thinking', 'default') if parent else self.settings['thinking'],
               'status': 'idle'}
        with self.lock:
            self.rows.append(row)
            if not parent: self.active = row['key']
            self.save()
        print(f"{'Agent created' if parent else 'Session selected'} {len(self.rows)}: {title} | {root}", flush=True)
        return row

    def selected(self):
        return next((r for r in self.rows if r['key'] == self.active), None) or self.new()

    def connect(self, row, refresh=False, _retry=1):
        key = row['key']
        if refresh:
            old = self.clients.pop(key, None)
            try:
                if old:
                    old[0].close()
            except Exception:
                print('Old remote endpoint could not be cleared; reconnecting.', flush=True)
            runtime = self.runtimes.pop(key, None)
            if runtime:
                runtime.close()
        if key not in self.clients:
            token = scio.get_token(interactive=False)
            def approve(name, arguments, effect):
                if self.stopping.is_set():
                    return False
                if self.settings['auto_allow'] or effect in ('read', 'delegate') or {'write': self.args.allow_write,
                        'execute': self.args.allow_exec, 'network': self.args.allow_network}.get(effect):
                    return True
                return self.approvals.ask(key[:8], name, arguments, effect)
            tools = WorkspaceTools(row['project'], approve)
            self.add_agent_tools(row, tools)
            previous_runtime = self.runtimes.pop(key, None)
            if previous_runtime:
                previous_runtime.close()
            runtime = NativeRuntime(self.args.cloudflared, self.args.public_url, self.args.discovery_port)
            self.runtimes[key] = runtime
            client = NativeClient(token, runtime, tools.definitions(), row['model'],
                instructions=f"Selected local workspace: {row['project']}. You may delegate independent tasks with agent_spawn; subagents may delegate too. Use agent_wait to collect their actual results before claiming completion. Agents share files: assign distinct files to concurrent writers. Parent instructions are not automatically copied: include the full task and constraints in the child prompt.",
                state_file=scio.DATA_DIR / 'console-ledgers' / (key + '.json'),
                thinking=row.get('thinking', 'default'))
            self.clients[key] = (client, tools)
        client, tools = self.clients[key]
        try:
            client.prepare()
        except RuntimeError as exc:
            if _retry and 'could not discover' in str(exc):
                print(f'[{key[:8]}] Reconnecting tool discovery before starting the task...', flush=True)
                return self.connect(row, refresh=True, _retry=_retry-1)
            raise
        if not row['chat']:
            row['chat'] = client.new_chat(row['title'])
            self.save()
        return client, tools

    def start(self, row, prompt=None, refresh=False):
        key = row['key']
        with self.lock:
            if self.stopping.is_set(): raise ValueError('SCIO CODE is stopping')
            if key in self.jobs and self.jobs[key].is_alive():
                raise ValueError('This session is busy. Use /new to run another task.')
            if sum(job.is_alive() for job in self.jobs.values()) >= self.settings['max_agents']:
                raise ValueError('Concurrent agent limit reached; wait for a task or increase /set max_agents N')
            row['status'] = 'running'
            row.pop('result', None)
            row.pop('error', None)
            self.save()
            def work():
                try:
                    client, tools = self.connect(row, refresh)
                    if self.stopping.is_set():
                        return
                    if prompt is not None:
                        request = ('This is a live request from the SCIO CODE local coding client. '
                                   'The registered local_ MCP tools access the selected real local project. '
                                   'Tool names in this request may omit local_; use their registered native names. '
                                   'No Scio browser or classroom workspace is needed.\n\n' + prompt)
                        answer = client.run(row['chat'], request, tools.call,
                            max_steps=self.settings['max_steps'],
                            on_call=lambda call: print(f"\n[{key[:8]}] Tool: {call['name']}", flush=True))
                        print(f"\n[{key[:8]}] {answer['text']}", flush=True)
                        with self.lock: row['result'] = answer['text'][:30000]
                    else:
                        print(f"\n[{key[:8]}] Refreshed: {row['chat']}", flush=True)
                    with self.lock: row['status'] = 'done'
                except Exception as exc:
                    with self.lock:
                        row['status'] = 'failed'
                        row['error'] = f'{type(exc).__name__}: {exc}'
                    print(f'\n[{key[:8]}] Stopped: {type(exc).__name__}: {exc}. '
                          'History and tool ledger are saved. /refresh reconnects; no task is replayed.', flush=True)
                finally:
                    with self.lock:
                        if row['status'] == 'running': row['status'] = 'interrupted'
                        self.save()
            job = threading.Thread(target=work, name='scio-' + key[:8])
            self.jobs[key] = job
            job.start()

    def add_agent_tools(self, parent, tools):
        def visible(agent_id):
            with self.lock:
                rows = {r['key']: r for r in self.rows}
                row = rows.get(agent_id)
                cursor = row
                while cursor and cursor.get('parent') != parent['key']:
                    cursor = rows.get(cursor.get('parent'))
                if not row or not cursor: raise ValueError('Agent is not a descendant of this session')
                return row

        def agent_spawn(prompt: str, title: str = 'Subagent', model: str = ''):
            if not prompt.strip(): raise ValueError('A self-contained task is required')
            if len(prompt) > 100000: raise ValueError('Task exceeds 100000 characters')
            selected_model = scio.validate_model(model) if model else parent['model']
            signature = hashlib.sha256(json.dumps([prompt, title, selected_model]).encode()).hexdigest()
            with self.lock:
                # Scio can emit the same request under a new call ID after its
                # remote execution fails. Never launch a duplicate worker for it.
                existing = next((r for r in self.rows if r.get('parent') == parent['key'] and r.get('spawn_signature') == signature), None)
                if existing:
                    return {'agent_id': existing['key'], 'status': existing['status'], 'already_spawned': True}
                if parent.get('depth', 0) >= self.settings['max_depth']:
                    raise ValueError('Maximum subagent depth reached')
                rows = {r['key']: r for r in self.rows}
                def root(row):
                    while row.get('parent'): row = rows[row['parent']]
                    return row['key']
                count = sum(bool(r.get('parent')) and root(r) == root(parent) for r in self.rows)
                if count >= self.settings['max_children']: raise ValueError('Task tree agent budget reached')
                if self.stopping.is_set() or sum(j.is_alive() for j in self.jobs.values()) >= self.settings['max_agents']:
                    raise ValueError('No free agent slot; collect existing results first')
                row = self.new(title, parent=parent, model=selected_model)
                row['spawn_signature'] = signature
                self.start(row, prompt)
                return {'agent_id': row['key'], 'status': 'running', 'project': row['project']}

        def agent_status(agent_id: str):
            with self.lock:
                row = visible(agent_id)
                return {k: row.get(k) for k in ('key', 'title', 'parent', 'status', 'result', 'error')}

        def agent_wait(agent_id: str, timeout_seconds: int = 30):
            visible(agent_id)
            if not 0 <= timeout_seconds <= 30: raise ValueError('Wait must be 0..30 seconds')
            job = self.jobs.get(agent_id)
            if job: job.join(timeout_seconds)
            return agent_status(agent_id)

        def agent_list():
            result = []
            with self.lock:
                for row in self.rows:
                    try: result.append(agent_status(row['key']))
                    except ValueError: pass
            return result

        def agent_followup(agent_id: str, prompt: str):
            row = visible(agent_id)
            self.start(row, prompt)
            return {'agent_id': agent_id, 'status': 'running'}

        for name, fn, desc in [
            ('agent_spawn', agent_spawn, 'Start an independent subagent in this project. Returns immediately. Child inherits permission policy and thinking level and may spawn children within limits.'),
            ('agent_status', agent_status, 'Read a descendant agent status and actual result.'),
            ('agent_wait', agent_wait, 'Wait up to 30 seconds for a descendant; running is not completion.'),
            ('agent_list', agent_list, 'List descendants and their actual results.'),
            ('agent_followup', agent_followup, 'Give an idle descendant another task.')]:
            tools.add(name, desc, fn, effect='delegate')

    def setting_set(self, name, value):
        with self.lock:
            self.settings[name] = settings.validate(name, value)
            settings.save(self.settings)
            if name == 'thinking': self.active = None
        if name == 'auto_allow':
            with self.approvals.lock:
                self.approvals.auto = self.settings[name]
                keys = list(self.approvals.pending) if self.settings[name] else []
            for key in keys:
                try: self.approvals.resolve(key, True)
                except KeyError: pass
        print(f'{name}: {self.settings[name]}')

    def close(self):
        with self.lock: self.stopping.set()
        self.approvals.close()
        for job in list(self.jobs.values()):
            if job.is_alive():
                print('Waiting for an in-flight task to finish safely...', flush=True)
                while job.is_alive():
                    job.join(30)
        for client, _ in self.clients.values():
            try:
                client.close()
            except Exception:
                print('Remote disconnect failed; local endpoint is stopping.', flush=True)
        for runtime in self.runtimes.values():
            runtime.close()
        self.save()

    def loop(self):
        print('SCIO CODE console ready. Project: ' + self.project)
        print('Auto-allow: ' + ('ON' if self.settings['auto_allow'] else 'OFF'))
        print('/project PATH, /new [title], /sessions, /switch N, /refresh [all], '
              '/model ID, /thinking default|low|high, /auto on|off, /settings, /set NAME VALUE, '
              '/agents, /token, /permissions, /approve ID, /deny ID, /quit')
        try:
            while True:
                try:
                    text = input('\nYou> ').strip()
                except EOFError:
                    break
                if not text:
                    continue
                command, _, value = text.partition(' ')
                try:
                    if command in ('/quit', '/exit'):
                        break
                    elif command == '/project':
                        if value: self.project_set(value)
                        else: print(self.project)
                    elif command == '/new':
                        self.new(value or 'SCIO CODE')
                    elif command in ('/sessions', '/chats', '/agents'):
                        for number, row in enumerate(self.rows, 1):
                            busy = row['key'] in self.jobs and self.jobs[row['key']].is_alive()
                            print(number, '*' if row['key'] == self.active else ' ', row['key'][:8],
                                  'running' if busy else row.get('status', 'idle'), row['title'], row['model'], row['project'], 'depth', row.get('depth', 0))
                    elif command == '/auto':
                        self.setting_set('auto_allow', value)
                    elif command == '/thinking':
                        self.setting_set('thinking', value)
                    elif command == '/settings':
                        print(json.dumps(settings.describe(self.settings), indent=2, ensure_ascii=False))
                    elif command == '/set':
                        name, value = value.split(maxsplit=1)
                        self.setting_set(name, value)
                    elif command in ('/switch', '/resume'):
                        number = int(value)
                        if not 1 <= number <= len(self.rows): raise ValueError('Invalid session number')
                        self.active = self.rows[number-1]['key']
                    elif command == '/model':
                        self.model = scio.validate_model(value)
                        self.active = None
                        print('Model for new sessions:', self.model)
                    elif command == '/token':
                        scio.get_token(replace=True)
                        print('Token saved. Use /refresh to reload it for an idle session.')
                    elif command == '/permissions':
                        with self.approvals.lock:
                            for key, row in self.approvals.pending.items():
                                print(key, row['session'], row['tool'], row['arguments'])
                    elif command in ('/approve', '/deny'):
                        self.approvals.resolve(value, command == '/approve')
                    elif command == '/refresh':
                        scio.get_token(interactive=sys.stdin.isatty())
                        for row in list(self.rows) if value == 'all' else [self.selected()]:
                            try: self.start(row, refresh=True)
                            except ValueError as exc: print(row['key'][:8], exc)
                    elif command == '/tools':
                        tools = WorkspaceTools(self.project)
                        self.add_agent_tools({'key':'catalog', 'project':self.project, 'model':self.model}, tools)
                        print('\n'.join(tools.tools))
                    elif command.startswith('/'):
                        print('Unknown command.')
                    else:
                        scio.get_token(interactive=sys.stdin.isatty())
                        self.start(self.selected(), prompt=text)
                except Exception as exc:
                    print(f'{type(exc).__name__}: {exc}')
        except KeyboardInterrupt:
            print('\nStopping; pending permissions are denied.')
        finally:
            self.close()
        return 0
