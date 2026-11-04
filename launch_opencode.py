"""Launch official OpenCode 1.x with the native Scio provider and workspace tools."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from urllib.request import Request,urlopen
import zipfile

import scio_console as scio
from configure_native_opencode import generate
from native_provider import NativeProvider,serve
from native_transport import NativeRuntime

VERSION='1.19.3'


def opencode_binary(explicit=None):
    if explicit:return str(Path(explicit).resolve(strict=True))
    installed=shutil.which('opencode')
    if installed:return installed
    if os.name!='nt':raise RuntimeError('Install OpenCode 1.x first or pass --opencode PATH. Automatic download currently supports Windows x64.')
    import platform
    if platform.machine().lower() not in ('amd64','x86_64'):raise RuntimeError('Pass an OpenCode executable for this CPU architecture.')
    directory=scio.DATA_DIR/'bin'/('opencode-'+VERSION)
    path=directory/'opencode.exe'
    check=directory/'opencode.sha256'
    if path.exists() and check.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==check.read_text().strip():return str(path)
    request=Request('https://api.github.com/repos/anomalyco/opencode/releases/tags/v'+VERSION,headers={'User-Agent':'scio-opencode-native'})
    with urlopen(request,timeout=30) as response:release=json.load(response)
    asset=next(a for a in release['assets'] if a['name']=='opencode-windows-x64-baseline.zip')
    if not (asset.get('digest') or '').startswith('sha256:'):raise RuntimeError('Official release has no checksum; install OpenCode manually.')
    with urlopen(asset['browser_download_url'],timeout=120) as response:data=response.read(200_000_001)
    if len(data)>200_000_000 or hashlib.sha256(data).hexdigest()!=asset['digest'].split(':',1)[1]:raise RuntimeError('OpenCode download checksum mismatch')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names=[n for n in archive.namelist() if Path(n).name=='opencode.exe']
        if len(names)!=1:raise RuntimeError('Unexpected OpenCode release archive')
        executable=archive.read(names[0])
    directory.mkdir(parents=True,exist_ok=True)
    path.write_bytes(executable)
    check.write_text(hashlib.sha256(executable).hexdigest())
    return str(path)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',default='.')
    parser.add_argument('--model',choices=list(scio.MODELS),default='anthropic-strong')
    parser.add_argument('--cloudflared')
    parser.add_argument('--opencode')
    parser.add_argument('--port',type=int,default=8767)
    parser.add_argument('--prompt',help='Run one task instead of opening the interactive TUI')
    args=parser.parse_args()
    root=Path(args.workspace).resolve(strict=True)
    if not root.is_dir():parser.error('Workspace must be a directory')
    token=scio.get_token(interactive=sys.stdin.isatty())
    print('Preparing OpenCode and native Scio tools...',flush=True)
    executable=opencode_binary(args.opencode)
    version=subprocess.run([executable,'--version'],capture_output=True,text=True,timeout=30)
    if version.returncode or not version.stdout.strip().startswith('1.'):
        raise RuntimeError('This launcher targets OpenCode 1.x. Supply --opencode with a v1 binary; v2 configuration is different.')
    runtime=None;provider=None;server=None;thread=None
    try:
        runtime=NativeRuntime(args.cloudflared)
        provider=NativeProvider(token,runtime)
        server=serve(provider,args.port)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        config=generate(root,args.port)
        env={k:v for k,v in os.environ.items() if k!='SCIO_TOKEN'}
        env['OPENCODE_CONFIG']=str(config.resolve())
        env['OPENCODE_DISABLE_AUTOUPDATE']='true'
        command=[executable]
        if args.prompt:command+=['run','--model','scio-native/'+args.model,args.prompt]
        else:command+=[str(root),'--model','scio-native/'+args.model]
        print('Starting OpenCode with Scio native tools. Credentials stay in the local adapter.',flush=True)
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
