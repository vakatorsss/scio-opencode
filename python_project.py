"""Run project Python with project imports enabled, including in the embedded runtime."""
import os
from pathlib import Path
import runpy
import sys


def main():
    mode, *args = sys.argv[1:]
    sys.path.insert(0, os.getcwd())
    if mode == 'script':
        sys.argv = args
        sys.path.insert(0, str(Path(args[0]).resolve().parent))
        runpy.run_path(args[0], run_name='__main__')
    elif mode == 'snippet':
        sys.argv = ['-c']
        exec(compile(args[0], '<string>', 'exec'), {'__name__': '__main__'})
    elif mode == 'module':
        sys.argv = args
        runpy.run_module(args[0], run_name='__main__', alter_sys=True)
    else:
        raise ValueError('Unsupported Python execution mode')


if __name__ == '__main__': main()
