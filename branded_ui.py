"""Download the project's checksum-verified SCIO CODE Windows terminal build."""
import hashlib
import io
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen
import zipfile

import scio_console as scio

RELEASE = 'scio-code-v0.3.1'
VERSION = '1.19.3-scio.2'
ASSET = 'scio-code-windows-x64.zip'


def binary(explicit=None):
    if explicit: return str(Path(explicit).resolve(strict=True))
    if scio.DIST_DIR:
        path = scio.DIST_DIR / 'bin' / 'scio-code' / 'scio-code.exe'
        info = json.loads(path.with_name('build-info.json').read_text())
        if info.get('version') != VERSION or hashlib.sha256(path.read_bytes()).hexdigest() != info.get('sha256'):
            raise RuntimeError('Bundled UI verification failed; extract a fresh SCIO CODE distribution.')
        return str(path.resolve(strict=True))
    if os.name != 'nt': raise RuntimeError('The branded build currently targets Windows x64; supply --opencode PATH for another compatible v1 binary.')
    import platform
    if platform.machine().lower() not in ('amd64','x86_64'): raise RuntimeError('The bundled SCIO CODE UI requires Windows x64')
    directory = scio.DATA_DIR / 'bin' / 'scio-code'
    path = directory / 'scio-code.exe'
    check = directory / 'scio-code.sha256'
    try:
        cached = json.loads((directory/'build-info.json').read_text())
    except (OSError, ValueError):
        cached = {}
    if cached.get('version') == VERSION and path.exists() and check.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == check.read_text().strip():
        return str(path)
    req = Request(f'https://api.github.com/repos/vakatorsss/scio-opencode/releases/tags/{RELEASE}', headers={'User-Agent':'SCIO-CODE'})
    with urlopen(req, timeout=30) as response: release = json.load(response)
    asset = next(a for a in release['assets'] if a['name'] == ASSET)
    with urlopen(asset['browser_download_url'], timeout=120) as response: data = response.read(250_000_001)
    if len(data) > 250_000_000 or asset.get('digest') != 'sha256:' + hashlib.sha256(data).hexdigest():
        raise RuntimeError('SCIO CODE download checksum mismatch or missing GitHub digest')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        executable = archive.read('scio-code.exe')
        info = json.loads(archive.read('build-info.json'))
        license_text = archive.read('OPENCODE-LICENSE.txt')
    digest = hashlib.sha256(executable).hexdigest()
    if info.get('sha256') != digest: raise RuntimeError('SCIO CODE executable checksum mismatch')
    if info.get('version') != VERSION: raise RuntimeError('SCIO CODE executable version mismatch')
    directory.mkdir(parents=True, exist_ok=True)
    path.write_bytes(executable)
    (directory/'OPENCODE-LICENSE.txt').write_bytes(license_text)
    (directory/'build-info.json').write_text(json.dumps(info,indent=2))
    check.write_text(digest)
    return str(path)
