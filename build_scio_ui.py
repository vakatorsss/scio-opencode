"""Build the SCIO CODE terminal UI from pinned, MIT-licensed OpenCode source."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).resolve().parent
REVISION = 'e3c4eb242585dcd77be1a867391b7c25fd47ce52'
BUN_VERSION = '1.3.14'
VERSION = '1.19.3-scio.2'


def bun_binary():
    path = ROOT / 'work' / 'bun.exe'
    checksum = path.with_suffix('.sha256')
    if path.exists() and checksum.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == checksum.read_text().strip():
        return path
    request = Request(f'https://api.github.com/repos/oven-sh/bun/releases/tags/bun-v{BUN_VERSION}', headers={'User-Agent':'SCIO-CODE-builder'})
    with urlopen(request, timeout=30) as response: release = json.load(response)
    asset = next(a for a in release['assets'] if a['name'] == 'bun-windows-x64.zip')
    with urlopen(asset['browser_download_url'], timeout=120) as response: data = response.read(100_000_001)
    if len(data) > 100_000_000 or asset.get('digest') != 'sha256:' + hashlib.sha256(data).hexdigest():
        raise RuntimeError('Bun release checksum verification failed')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        name = next(n for n in archive.namelist() if n.endswith('/bun.exe'))
        executable = archive.read(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(executable)
    checksum.write_text(hashlib.sha256(executable).hexdigest())
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bun', help='Use an installed Bun 1.3.14+ executable')
    parser.add_argument('--skip-install', action='store_true', help='Dependencies are already installed')
    args = parser.parse_args()
    if os.name != 'nt': parser.error('This packaged build targets Windows x64')
    source = ROOT / 'work' / 'opencode-upstream'
    if not source.exists():
        subprocess.run(['git','clone','--depth','1','--branch','v1.19.3',
                        'https://github.com/anomalyco/opencode.git', str(source)], check=True)
    head = subprocess.check_output(['git','rev-parse','HEAD'], cwd=source, text=True).strip()
    if head != REVISION: raise RuntimeError('Unexpected upstream source revision')
    patch = ROOT / 'branding' / 'scio-code.patch'
    applied = subprocess.run(['git','apply','--reverse','--check',str(patch)],cwd=source,capture_output=True).returncode == 0
    if not applied:
        subprocess.run(['git','apply','--check',str(patch)],cwd=source,check=True)
        subprocess.run(['git','apply',str(patch)],cwd=source,check=True)
    bun = Path(args.bun).resolve(strict=True) if args.bun else bun_binary()
    env = dict(os.environ)
    env['PATH'] = str(bun.parent) + os.pathsep + env.get('PATH','')
    env.pop('OPENCODE_RELEASE', None)
    env['OPENCODE_VERSION'] = VERSION
    env['OPENCODE_CHANNEL'] = 'scio-code'
    if not args.skip_install:
        subprocess.run([str(bun),'install','--frozen-lockfile'],cwd=source,env=env,check=True)
    package = source / 'packages' / 'opencode'
    # The upstream build cleans dist. Verify it cannot resolve outside this package.
    dist = package / 'dist'
    if dist.is_symlink() or dist.resolve() != package.resolve() / 'dist':
        raise RuntimeError('Unsafe upstream dist path')
    subprocess.run([str(bun),'run','script/build.ts','--single','--skip-install','--skip-embed-web-ui'],cwd=package,env=env,check=True)
    candidates = list(dist.glob('opencode-windows-x64/bin/opencode*'))
    candidates = [p for p in candidates if p.is_file() and p.suffix in ('','.exe')]
    if len(candidates) != 1: raise RuntimeError('Expected one Windows x64 binary')
    destination = ROOT / 'scio_data' / 'bin' / 'scio-code'
    destination.mkdir(parents=True, exist_ok=True)
    executable = destination / 'scio-code.exe'
    shutil.copy2(candidates[0], executable)
    shutil.copy2(ROOT/'branding'/'OPENCODE-LICENSE.txt', destination/'OPENCODE-LICENSE.txt')
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    (destination/'scio-code.sha256').write_text(digest)
    (destination/'build-info.json').write_text(json.dumps({'version':VERSION,'upstream_commit':REVISION,'sha256':digest},indent=2))
    subprocess.run([str(executable),'--version'], check=True)
    print('SCIO CODE UI built:', executable)


if __name__ == '__main__': main()
