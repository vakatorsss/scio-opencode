"""Check the release ZIP and exercise its bundled runtime/MCP without Scio credentials."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def verify(archive_path):
    with tempfile.TemporaryDirectory(prefix='scio-dist-check-') as temp:
        root = Path(temp)
        with zipfile.ZipFile(archive_path) as archive:
            for name in archive.namelist():
                if not (root / name).resolve().is_relative_to(root.resolve()):
                    raise ValueError('Archive path escapes extraction directory')
                if any(part in ('scio_data', '.venv', '.git', 'work') for part in Path(name).parts):
                    raise ValueError('Private/build directory in distribution')
                if Path(name).name in ('token.dpapi', 'provider-key.txt', '.env'):
                    raise ValueError('Private file in distribution')
            archive.extractall(root)
        stage = root / 'SCIO CODE'
        checksums = json.loads((stage / 'checksums.json').read_text())
        for name, digest in checksums.items():
            path = (stage / name).resolve()
            assert path.is_relative_to(stage.resolve())
            assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, name
        python, app = str(stage / 'runtime/python.exe'), str(stage / 'app/scio_app.py')
        project = root / 'test project'; project.mkdir()
        env = {k: v for k, v in os.environ.items() if k not in ('SCIO_TOKEN', 'PYTHONPATH', 'PYTHONHOME')}
        env['SCIO_DATA_DIR'] = str(root / 'test data')
        env['PATH'] = os.path.join(os.environ['SystemRoot'], 'System32')
        for args in [['doctor'], ['settings', 'set', 'locale', 'cs'], ['project', str(project)],
                     ['settings', 'show'], ['console', '--list-tools']]:
            result = subprocess.run([python, app, *args], cwd=project, env=env,
                                    capture_output=True, text=True, encoding='utf-8', timeout=60, check=True)
            if args == ['settings', 'show']: assert '"locale": "cs"' in result.stdout
            if args == ['console', '--list-tools']: assert len(json.loads(result.stdout)) >= 104
        (project / 'helper.py').write_text('VALUE = 323\n')
        (project / 'main.py').write_text('from helper import VALUE\nprint(VALUE)\n')
        params = StdioServerParameters(command=python, args=[str(stage / 'app/workspace_mcp.py'), '--workspace', str(project)], env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                assert len((await session.list_tools()).tools) >= 99
                for name, args, expected in [
                    ('write_file', {'path': 'receipt.txt', 'content': 'PACKAGED_MCP_OK'}, ''),
                    ('read_file', {'path': 'receipt.txt'}, 'PACKAGED_MCP_OK'),
                    ('python_run_snippet', {'code': 'from helper import VALUE; print(VALUE)'}, '323'),
                    ('python_run_script', {'path': 'main.py'}, '323')]:
                    result = await session.call_tool(name, args)
                    assert not result.isError, result
                    assert expected in ''.join(c.text for c in result.content), result
        assert (project / 'receipt.txt').read_text() == 'PACKAGED_MCP_OK'
        print('PASS: archive hashes, isolated bundled runtime, settings/project, tool catalog, MCP, file I/O and project Python imports.')


if __name__ == '__main__':
    asyncio.run(verify(Path(sys.argv[1] if len(sys.argv) > 1 else 'dist/SCIO-CODE-windows-x64.zip')))
