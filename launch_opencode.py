"""Launch SCIO CODE, based on the public MIT-licensed OpenCode terminal client."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import threading
import uuid

import scio_console as scio
import settings
from configure_native_opencode import generate
from native_provider import NativeProvider,serve
from native_transport import NativeRuntime

# Keep the old function name as a compatibility import for existing callers.
from branded_ui import binary as opencode_binary


def main():
    if hasattr(sys.stdout, "reconfigure"):sys.stdout.reconfigure(encoding="utf-8",errors="replace")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',default=None)
    parser.add_argument('--model',choices=list(scio.MODELS),default='anthropic-strong')
    parser.add_argument('--cloudflared')
    parser.add_argument('--opencode')
    parser.add_argument('--port',type=int,default=0)
    parser.add_argument('--prompt',help='Run one task instead of opening the interactive TUI')
    parser.add_argument('--auto-allow',action=argparse.BooleanOptionalAction,default=None)
    parser.add_argument('--thinking',choices=['default','low','high'],default=None)
    parser.add_argument('--max-depth',type=int,default=None)
    parser.add_argument('--max-steps',type=int,default=None)
    args=parser.parse_args()
    options=settings.load()
    for name in settings.DEFAULTS:
        value=getattr(args,name,None)
        if value is not None:options[name]=settings.validate(name,value)
    saved=scio.read_json(scio.DATA_DIR/'console-sessions.json',{})
    root=Path(args.workspace or saved.get('project','.')).resolve(strict=True)
    if not root.is_dir():parser.error('Workspace must be a directory')
    token=scio.get_token(interactive=sys.stdin.isatty())
    print('SCIO CODE - preparing the terminal interface...',flush=True)
    executable=opencode_binary(args.opencode)
    version=subprocess.run([executable,'--version'],capture_output=True,text=True,timeout=30)
    if version.returncode or not version.stdout.strip().startswith('1.'):
        raise RuntimeError('This launcher targets OpenCode 1.x. Supply --opencode with a v1 binary; v2 configuration is different.')
    runtime=None;provider=None;server=None;thread=None
    try:
        runtime=NativeRuntime(args.cloudflared)
        instance=uuid.uuid4().hex
        provider=NativeProvider(token,runtime,state_dir=scio.DATA_DIR/'native-provider-runs'/instance,thinking=options['thinking'])
        server=serve(provider,args.port)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        config=generate(root,server.server_port,instance=instance,options=options)
        env={k:v for k,v in os.environ.items() if k!='SCIO_TOKEN'}
        env['OPENCODE_CONFIG']=str(config.resolve())
        env['OPENCODE_DISABLE_AUTOUPDATE']='true'
        env['OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS']='true'
        command=[executable]
        if args.prompt:command+=['run','--model','scio-native/'+args.model,args.prompt]
        else:command+=[str(root),'--model','scio-native/'+args.model]
        print('Starting SCIO CODE. Credentials stay in the local adapter.',flush=True)
        return subprocess.call(command,cwd=root,env=env)
    finally:
        if server:server.shutdown();server.server_close()
        if thread:thread.join(timeout=3)
        if provider and provider.close():print('Some remote MCP configurations could not be cleared; local endpoints are stopping.',file=sys.stderr)
        if runtime:runtime.close()


if __name__=='__main__':
    try:raise SystemExit(main())
    except KeyboardInterrupt:print('\nStopped.')
    except Exception as exc:print(f'Launch failed: {type(exc).__name__}: {exc}',file=sys.stderr);raise SystemExit(1)
