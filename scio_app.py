"""SCIO CODE unified launcher, settings and portable-distribution diagnostics."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import scio_console as scio
import settings

VERSION = '0.4.0'


def configure(words):
    if not words or words == ['show']:
        print(json.dumps(settings.describe(settings.load()), indent=2, ensure_ascii=False))
        print('Saved in:', scio.DATA_DIR)
        return
    values = settings.load()
    if words[0] == 'instructions-file' and len(words) == 2:
        values['instructions'] = settings.validate('instructions', Path(words[1]).read_text(encoding='utf-8-sig'))
    elif words[0] == 'clear-instructions' and len(words) == 1:
        values['instructions'] = ''
    elif words[0] == 'set' and len(words) >= 3:
        name = words[1].replace('-', '_')
        values[name] = settings.validate(name, ' '.join(words[2:]))
    else:
        raise ValueError('Use settings show | set NAME VALUE | instructions-file PATH | clear-instructions')
    settings.save(values)
    print('Saved. Used by the next UI launch and new console sessions.')


def project(value):
    root = Path(value.strip().strip('"')).expanduser().resolve(strict=True)
    if not root.is_dir(): raise ValueError('Project must be a directory')
    path = scio.DATA_DIR / 'console-sessions.json'
    saved = scio.read_json(path, {})
    saved['project'] = str(root)
    scio.save_json(path, saved)
    print('Project:', root)


def doctor():
    from branded_ui import binary
    from native_transport import cloudflared_binary
    from workspace_tools import WorkspaceTools
    import mcp.server.stdio
    import jsonschema
    print('SCIO CODE', VERSION, '| Python', sys.version.split()[0])
    print('Data directory:', scio.DATA_DIR)
    print('Token saved:', (scio.DATA_DIR / 'token.dpapi').exists())
    print('Workspace tools:', len(WorkspaceTools(Path.cwd()).definitions()))
    for name, executable in [('Terminal UI', binary()), ('Tunnel', cloudflared_binary())]:
        result = subprocess.run([executable, '--version'], capture_output=True, text=True, timeout=30, check=True)
        print(name + ':', result.stdout.strip())
    print('Local checks passed. No account request or tunnel was started.')


def run_mode(mode, args):
    sys.argv = [sys.argv[0], *args]
    if mode == 'ui':
        import launch_opencode
        return launch_opencode.main()
    import scio_code
    return scio_code.main()


def menu():
    while True:
        saved = scio.read_json(scio.DATA_DIR / 'console-sessions.json', {})
        print('\nSCIO CODE ' + VERSION)
        print('Project:', saved.get('project', str(Path.cwd())))
        print('[Enter] Terminal UI   [c] Console   [s] Settings   [p] Project')
        print('[t] Save/replace token   [d] Diagnostics   [q] Quit')
        choice = input('> ').strip().lower()
        try:
            if choice in ('q', 'quit'): return 0
            if choice in ('', 'ui'): return run_mode('ui', [])
            if choice == 'c': return run_mode('console', [])
            if choice == 'p': project(input('Project directory: '))
            elif choice == 't': scio.get_token(replace=True)
            elif choice == 'd': doctor()
            elif choice == 's':
                configure([])
                print('Enter NAME VALUE (e.g. locale cs, web_search on, conciseness short).')
                print('For multiline instructions: instructions-file PATH. Empty line returns.')
                while True:
                    text = input('settings> ').strip()
                    if not text: break
                    try:
                        name, _, value = text.partition(' ')
                        if name == 'instructions-file': configure([name, value.strip('"')])
                        elif name == 'clear-instructions': configure([name])
                        else: configure(['set', name, value])
                    except (OSError, ValueError) as exc: print(exc)
        except (OSError, ValueError, RuntimeError) as exc: print(exc)


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ('ui', 'console'): return run_mode(args[0], args[1:])
    if args and args[0] == 'settings': configure(args[1:]); return 0
    if args and args[0] == 'project' and len(args) == 2: project(args[1]); return 0
    parser = argparse.ArgumentParser(description=__doc__, epilog='Commands: ui [options], console [options], settings [show|set NAME VALUE|instructions-file PATH|clear-instructions], project PATH, login, doctor')
    parser.add_argument('command', nargs='?', choices=['login', 'doctor'])
    parser.add_argument('--version', action='version', version='SCIO CODE ' + VERSION)
    parsed = parser.parse_args(args)
    if parsed.command == 'login': scio.get_token(replace=True); return 0
    if parsed.command == 'doctor': doctor(); return 0
    if not sys.stdin.isatty(): parser.print_help(); return 0
    return menu()


if __name__ == '__main__':
    try: raise SystemExit(main())
    except (KeyboardInterrupt, EOFError): print('\nStopped.')
    except Exception as exc:
        print(f'SCIO CODE: {type(exc).__name__}: {exc}', file=sys.stderr)
        raise SystemExit(1)
