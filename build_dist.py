"""Build one self-contained Windows x64 SCIO CODE ZIP from an explicit allowlist."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.request import urlopen
import uuid
import zipfile

from scio_app import VERSION
from branded_ui import binary

ROOT = Path(__file__).resolve().parent
PYTHON = {'version': '3.14.10', 'url': 'https://www.python.org/ftp/python/3.14.10/python-3.14.10-embed-amd64.zip',
          'sha256': '90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159'}
CLOUDFLARED = {'version': '2026.10.7', 'url': 'https://github.com/cloudflare/cloudflared/releases/download/2026.10.7/cloudflared-windows-amd64.exe',
              'sha256': '2493dbc168923bb3e59e5e7716f71deced92992eea9acd6e9d74f84ac7751343'}
APP_FILES = ['scio_app.py', 'scio_code.py', 'scio_console.py', 'scio_native.py', 'settings.py',
             'session_console.py', 'launch_opencode.py', 'branded_ui.py', 'native_provider.py',
             'native_transport.py', 'scio_provider.py', 'configure_native_opencode.py',
             'workspace_tools.py', 'workspace_mcp.py', 'python_project.py']


def download(component, name):
    cache = ROOT / 'work' / 'dist-downloads' / name
    cache.parent.mkdir(parents=True, exist_ok=True)
    if not cache.exists() or hashlib.sha256(cache.read_bytes()).hexdigest() != component['sha256']:
        with urlopen(component['url'], timeout=120) as response: data = response.read(150_000_001)
        if hashlib.sha256(data).hexdigest() != component['sha256']:
            raise RuntimeError('Download checksum failed: ' + name)
        cache.write_bytes(data)
    return cache


def main():
    # A unique staging folder avoids deleting an existing build or user data.
    stage = ROOT / 'work' / ('dist-stage-' + uuid.uuid4().hex) / 'SCIO CODE'
    runtime, app = stage / 'runtime', stage / 'app'
    runtime.mkdir(parents=True); app.mkdir()
    with zipfile.ZipFile(download(PYTHON, 'python-3.14.10.zip')) as archive:
        for name in archive.namelist():
            target = (runtime / name).resolve()
            if not target.is_relative_to(runtime.resolve()): raise RuntimeError('Invalid runtime archive path')
        archive.extractall(runtime)
    (runtime / 'python314._pth').write_text('python314.zip\n.\nLib/site-packages\n../app\nimport site\n')
    requirements = ROOT / 'requirements-dist.lock'
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--only-binary=:all:', '--platform', 'win_amd64',
                    '--python-version', '3.14', '--implementation', 'cp', '--abi', 'cp314', '--no-compile',
                    '--target', str(runtime / 'Lib' / 'site-packages'), '-r', str(requirements)], check=True)
    for name in APP_FILES: shutil.copy2(ROOT / name, app / name)
    ui = stage / 'bin' / 'scio-code'
    ui.mkdir(parents=True)
    executable = Path(binary())
    for name in ('scio-code.exe', 'build-info.json', 'OPENCODE-LICENSE.txt'):
        shutil.copy2(executable.with_name(name), ui / name)
    shutil.copy2(download(CLOUDFLARED, 'cloudflared-2026.10.7.exe'), stage / 'bin' / 'cloudflared.exe')
    licenses = stage / 'licenses'; licenses.mkdir()
    shutil.copy2(ROOT / 'branding' / 'OPENCODE-LICENSE.txt', licenses)
    shutil.copy2(ROOT / 'branding' / 'CLOUDFLARED-LICENSE.txt', licenses)
    for name in ('README.md', 'TUTORIAL.md', 'MODEL-SETTINGS.md', 'THIRD-PARTY-NOTICES.md', 'requirements-dist.lock'):
        shutil.copy2(ROOT / name, stage / name)
    for name, mode in [('SCIO CODE.cmd', ''), ('SCIO CODE UI.cmd', 'ui'), ('SCIO CODE Console.cmd', 'console')]:
        (stage / name).write_text('@echo off\nsetlocal\ntitle SCIO CODE\nset "PYTHONUTF8=1"\n'
            + '"%~dp0runtime\\python.exe" "%~dp0app\\scio_app.py" ' + mode + ' %*\n'
            + 'set "SCIO_EXIT=%ERRORLEVEL%"\nif not "%SCIO_EXIT%"=="0" pause\nexit /b %SCIO_EXIT%\n')
    manifest = {'version': VERSION, 'python': PYTHON, 'cloudflared': CLOUDFLARED,
                'ui': json.loads((ui / 'build-info.json').read_text()),
                'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()}
    (stage / 'distribution.json').write_text(json.dumps(manifest, indent=2))
    subprocess.run([str(runtime / 'python.exe'), str(app / 'scio_app.py'), 'doctor'], check=True)
    files = {p.relative_to(stage).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in stage.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    (stage / 'checksums.json').write_text(json.dumps(files, indent=2))
    destination = ROOT / 'dist'; destination.mkdir(exist_ok=True)
    archive_path = destination / 'SCIO-CODE-windows-x64.zip'
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for p in stage.rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts:
                archive.write(p, p.relative_to(stage.parent))
    checksum = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    archive_path.with_suffix('.zip.sha256').write_text(checksum + '  ' + archive_path.name + '\n')
    print('DIST:', archive_path, '\nSHA256:', checksum, '\nSTAGING:', stage)


if __name__ == '__main__': main()
