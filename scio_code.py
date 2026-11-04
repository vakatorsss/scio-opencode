"""Scio-native coding client. Run with a workspace; first run asks for a token."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from urllib.error import HTTPError

import scio_console as scio
from native_transport import NativeRuntime
from scio_native import NativeClient
from workspace_tools import WorkspaceTools


def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',default='.',help='Directory the local file tools may access')
    parser.add_argument('--model',choices=list(scio.MODELS),default='anthropic-strong')
    parser.add_argument('--prompt',help='Run one task and exit; denied operations are not executed')
    parser.add_argument('--allow-write',action='store_true',help='Preapprove workspace writes for this process')
    parser.add_argument('--allow-exec',action='store_true',help='Preapprove OS command execution for this process (not sandboxed)')
    parser.add_argument('--allow-network',action='store_true',help='Preapprove HTTP tools for this process')
    parser.add_argument('--max-steps',type=int,default=20)
    parser.add_argument('--cloudflared',help='Use this installed cloudflared executable')
    parser.add_argument('--public-url',help='Existing HTTPS reverse proxy to the discovery server; advanced usage')
    parser.add_argument('--discovery-port',type=int,default=0,help='Fixed local port for --public-url; default chooses a free port')
    parser.add_argument('--serve-opencode',action='store_true',help='Run the native OpenCode model provider instead of terminal chat')
    parser.add_argument('--port',type=int,default=8767)
    parser.add_argument('--list-tools',action='store_true',help='Print the catalog without token/network access')
    parser.add_argument('--replace-token',action='store_true')
    args=parser.parse_args()
    root=Path(args.workspace).resolve(strict=True)
    def approve(name,arguments,effect):
        if effect=='read':return True
        if {'write':args.allow_write,'execute':args.allow_exec,'network':args.allow_network}.get(effect):return True
        print(f'\nPermission required: {effect} / {name}\n'+json.dumps(arguments,ensure_ascii=False,indent=2)[:6000],flush=True)
        if not sys.stdin.isatty():return False
        return input('Allow this operation? [y/N] ').strip().lower()=='y'
    tools=WorkspaceTools(root,approve)
    if args.list_tools:
        print(json.dumps(tools.definitions(),ensure_ascii=False,indent=2));return 0
    if not 1<=args.max_steps<=100:parser.error('--max-steps must be 1..100')
    token=scio.get_token(replace=args.replace_token,interactive=sys.stdin.isatty())
    print('Starting schema-only MCP discovery and temporary HTTPS tunnel...',flush=True)
    runtime=None;client=None;provider=None;server=None
    try:
        runtime=NativeRuntime(args.cloudflared,args.public_url,args.discovery_port)
        if args.serve_opencode:
            from native_provider import NativeProvider,serve
            from configure_native_opencode import generate
            provider=NativeProvider(token,runtime)
            server=serve(provider,args.port)
            config=generate(root,args.port)
            print(f'Native Scio provider: http://127.0.0.1:{args.port}/v1\nOpenCode configuration: {config}\nCtrl+C stops the provider and tunnel.',flush=True)
            server.serve_forever()
            return 0
        state_key=hashlib.sha256(str(root).encode()).hexdigest()[:20]
        client=NativeClient(token,runtime,tools.definitions(),args.model,instructions=f'Selected local workspace: {root}. Prefer native file tools for edits. Shell commands require separate permission.',state_file=scio.DATA_DIR/'native-cli'/f'{state_key}.json')
        print('Verifying native tool discovery from Scio...',flush=True)
        client.prepare()
        session=client.new_chat(args.prompt[:80] if args.prompt else 'Scio Code: '+root.name)
        print(f'Ready: {len(tools.tools)} tools | {args.model} | {root}\nChat: https://chat.scio.cz/chat/{session}',flush=True)
        def run(prompt):
            answer=client.run(session,prompt,tools.call,max_steps=args.max_steps,on_call=lambda call:print('Tool: '+call['name'],flush=True))
            print('\n'+answer['text'],flush=True)
        if args.prompt:run(args.prompt);return 0
        print('/new, /chats, /resume NUMBER, /model ID, /tools, /quit')
        while True:
            try:prompt=input('\nYou> ').strip()
            except EOFError:break
            if prompt in ('/quit','/exit'):break
            if not prompt:continue
            if prompt=='/new':session=client.new_chat('Scio Code: '+root.name);print('New chat:',session);continue
            if prompt=='/tools':print('\n'.join(tools.tools));continue
            if prompt=='/chats':
                for i,c in enumerate(client.state['chats'],1):print(i,c['title'],c['id'])
                continue
            if prompt.startswith('/resume '):
                try:
                    number=int(prompt.split()[1])
                    if number<1:raise ValueError('Invalid chat number')
                    session=client.state['chats'][number-1]['id'];print('Resumed:',session)
                except (ValueError,IndexError):print('Use /chats and select a valid number.')
                continue
            if prompt.startswith('/model '):
                try:client.model=scio.validate_model(prompt.split()[1]);print('Model:',client.model)
                except (ValueError,IndexError):print('Models:',', '.join(scio.MODELS))
                continue
            try:run(prompt)
            except Exception as exc:print(f'Task stopped: {type(exc).__name__}: {exc}. Chat and tool ledger remain saved.',file=sys.stderr)
    except KeyboardInterrupt:print('\nStopping.',flush=True)
    except HTTPError as exc:
        print(f'Scio HTTP {exc.code}; check token, account access or quota. No automatic retry.',file=sys.stderr);return 1
    except Exception as exc:
        print(f'Stopped: {type(exc).__name__}: {exc}',file=sys.stderr);return 1
    finally:
        if server:server.server_close()
        if provider:
            if provider.close():print('Some private agents could not be disconnected; the local endpoint is stopping.',file=sys.stderr)
        if client:
            try:client.close()
            except Exception:print('Could not clear remote MCP configuration; local endpoint is stopping.',file=sys.stderr)
        if runtime:runtime.close()
    return 0


if __name__=='__main__':raise SystemExit(main())
