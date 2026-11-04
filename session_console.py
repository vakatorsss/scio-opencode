"""Concurrent terminal sessions, with all input owned by the main thread."""
import json
from pathlib import Path
import threading
import uuid
import sys

import scio_console as scio
from native_transport import NativeRuntime
from scio_native import NativeClient
from workspace_tools import WorkspaceTools


class Approvals:
    def __init__(self):
        self.lock = threading.Lock()
        self.pending = {}
        self.closed = False

    def ask(self, session, name, arguments, effect):
        event = threading.Event()
        with self.lock:
            if self.closed:
                return False
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
        self.path = scio.DATA_DIR / 'console-sessions.json'
        saved = scio.read_json(self.path, {})
        self.project = str(Path(args.workspace or saved.get('project', '.')).resolve())
        self.model = args.model
        self.rows = saved.get('sessions', [])
        self.active = self.rows[-1]['key'] if self.rows else None
        self.clients = {}
        self.runtimes = {}
        self.jobs = {}
        self.lock = threading.RLock()
        self.approvals = Approvals()
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
        print('Project for new sessions:', root)

    def new(self, title='Scio Code'):
        root = Path(self.project).resolve(strict=True)
        if not root.is_dir():
            raise ValueError('Use /project PATH to select a directory')
        row = {'key': uuid.uuid4().hex, 'title': title, 'project': str(root),
               'model': self.model, 'chat': None}
        with self.lock:
            self.rows.append(row)
            self.active = row['key']
            self.save()
        print(f'Session {len(self.rows)} selected: {title} | {root}')
        return row

    def selected(self):
        return next((r for r in self.rows if r['key'] == self.active), None) or self.new()

    def connect(self, row, refresh=False):
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
                if effect == 'read' or {'write': self.args.allow_write,
                        'execute': self.args.allow_exec, 'network': self.args.allow_network}.get(effect):
                    return True
                return self.approvals.ask(key[:8], name, arguments, effect)
            tools = WorkspaceTools(row['project'], approve)
            previous_runtime = self.runtimes.pop(key, None)
            if previous_runtime:
                previous_runtime.close()
            runtime = NativeRuntime(self.args.cloudflared, self.args.public_url, self.args.discovery_port)
            self.runtimes[key] = runtime
            client = NativeClient(token, runtime, tools.definitions(), row['model'],
                instructions=f"Selected local workspace: {row['project']}.",
                state_file=scio.DATA_DIR / 'console-ledgers' / (key + '.json'))
            self.clients[key] = (client, tools)
        client, tools = self.clients[key]
        client.prepare()
        if not row['chat']:
            row['chat'] = client.new_chat(row['title'])
            self.save()
        return client, tools

    def start(self, row, prompt=None, refresh=False):
        key = row['key']
        with self.lock:
            if key in self.jobs and self.jobs[key].is_alive():
                raise ValueError('This session is busy. Use /new to run another task.')
            def work():
                try:
                    client, tools = self.connect(row, refresh)
                    if self.stopping.is_set():
                        return
                    if prompt is not None:
                        answer = client.run(row['chat'], prompt, tools.call,
                            max_steps=self.args.max_steps,
                            on_call=lambda call: print(f"\n[{key[:8]}] Tool: {call['name']}", flush=True))
                        print(f"\n[{key[:8]}] {answer['text']}", flush=True)
                    else:
                        print(f"\n[{key[:8]}] Refreshed: {row['chat']}", flush=True)
                except Exception as exc:
                    print(f'\n[{key[:8]}] Stopped: {type(exc).__name__}: {exc}. '
                          'History and tool ledger are saved. /refresh reconnects; no task is replayed.', flush=True)
            job = threading.Thread(target=work, name='scio-' + key[:8])
            self.jobs[key] = job
            job.start()

    def close(self):
        self.stopping.set()
        self.approvals.close()
        for job in self.jobs.values():
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
        print('Scio Code console ready. Project: ' + self.project)
        print('/project PATH, /new [title], /sessions, /switch N, /refresh [all], '
              '/model ID, /token, /permissions, /approve ID, /deny ID, /quit')
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
                        self.new(value or 'Scio Code')
                    elif command in ('/sessions', '/chats'):
                        for number, row in enumerate(self.rows, 1):
                            busy = row['key'] in self.jobs and self.jobs[row['key']].is_alive()
                            print(number, '*' if row['key'] == self.active else ' ', row['key'][:8],
                                  'running' if busy else 'idle', row['title'], row['model'], row['project'])
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
                        print('\n'.join(WorkspaceTools(self.project).tools))
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
