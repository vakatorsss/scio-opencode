"""Workspace tools shared by the terminal client and OpenCode's local MCP server.

Path checks are containment checks, not an OS sandbox. Command/code execution is
separately permissioned because an approved process has the user's OS privileges.
"""
import ast
import base64
import csv
import difflib
import fnmatch
import gzip
import hashlib
import html
import inspect
import io
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import textwrap
import time
import urllib.parse
import urllib.request
import uuid
import zipfile

import jsonschema

MAX_FILE = 2_000_000
MAX_OUTPUT = 30_000
BLOCKED = {'.git', 'scio_data', '.ssh', '.aws', '.azure', '.gnupg'}


class WorkspaceTools:
    def __init__(self, root, approve=None):
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError('Workspace must be a directory')
        self.approve = approve or (lambda name, args, effect: effect == 'read')
        self.tools = {}
        self._register()

    def add(self, name, description, fn, effect='read'):
        properties, required = {}, []
        for key, parameter in inspect.signature(fn).parameters.items():
            annotation = parameter.annotation
            kind = {int: 'integer', float: 'number', bool: 'boolean', list: 'array', dict: 'object'}.get(annotation, 'string')
            schema = {'type': kind}
            if kind == 'array': schema['items'] = {}
            if parameter.default is inspect.Parameter.empty: required.append(key)
            else: schema['default'] = parameter.default
            properties[key] = schema
        self.tools[name] = {'name': name, 'description': description, 'inputSchema': {'type': 'object', 'properties': properties, 'required': required, 'additionalProperties': False}, '_fn': fn, '_effect': effect}

    def definitions(self):
        return [{k: v for k, v in tool.items() if not k.startswith('_')} for tool in self.tools.values()]

    def call(self, name, arguments):
        if name not in self.tools: raise ValueError('Unknown tool: ' + name)
        tool = self.tools[name]
        jsonschema.validate(arguments, tool['inputSchema'])
        if not self.approve(name, arguments, tool['_effect']):
            return {'ok': False, 'error': 'User denied permission; do not retry without new authorization.'}
        value = tool['_fn'](**arguments)
        encoded = json.dumps(value, ensure_ascii=False, default=str)
        if len(encoded) > MAX_OUTPUT:
            return {'truncated': True, 'preview': encoded[:MAX_OUTPUT], 'total_characters': len(encoded)}
        return value

    def path(self, name='.'):
        candidate = (self.root / name).resolve()
        try: relative = candidate.relative_to(self.root)
        except ValueError: raise ValueError('Path escapes selected workspace')
        if any(p.lower() in BLOCKED or p.lower().startswith('.env') for p in relative.parts):
            raise ValueError('Credential/internal path is excluded from file tools')
        return candidate

    def read(self, path):
        p = self.path(path)
        if p.stat().st_size > MAX_FILE: raise ValueError('File exceeds 2 MB limit')
        return p.read_text(encoding='utf-8')

    def write(self, path, text):
        if len(text.encode()) > MAX_FILE: raise ValueError('Write exceeds 2 MB limit')
        p = self.path(path)
        if p == self.root: raise ValueError('Cannot replace workspace root')
        p.parent.mkdir(parents=True, exist_ok=True)
        # Atomic replacement; callers should inspect diffs before accepting edits.
        temp = p.with_name(p.name + '.scio-' + uuid.uuid4().hex + '.tmp')
        try:
            temp.write_text(text, encoding='utf-8')
            temp.replace(p)
        finally: temp.unlink(missing_ok=True)
        return {'path': str(p.relative_to(self.root)), 'bytes': len(text.encode())}

    def walk(self, pattern='*', limit=1000):
        result = []
        for directory, dirs, files in os.walk(self.root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d.lower() not in BLOCKED | {'node_modules', '.venv', '__pycache__'} and not (Path(directory) / d).is_symlink())
            for name in sorted(files):
                p = Path(directory) / name
                try: self.path(str(p))
                except ValueError: continue
                relative = p.relative_to(self.root).as_posix()
                if fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(name, pattern): result.append(relative)
                if len(result) >= min(max(limit, 1), 5000): return result
        return result

    def run(self, argv, cwd='.', timeout=60):
        if not argv or not all(isinstance(x, str) for x in argv): raise ValueError('argv must contain strings')
        env = {k: v for k, v in os.environ.items() if not any(x in k.upper() for x in ('TOKEN', 'SECRET', 'PASSWORD', 'API_KEY'))}
        with __import__('tempfile').TemporaryFile() as output:
            proc = subprocess.Popen(argv, cwd=self.path(cwd), env=env, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            timed_out = False
            try: proc.wait(timeout=min(max(timeout, 1), 120))
            except subprocess.TimeoutExpired:
                timed_out = True
                if os.name == 'nt': subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True)
                else: proc.kill()
                proc.wait()
            output.seek(0)
            text = output.read(MAX_OUTPUT + 1).decode('utf-8', errors='replace')
        return {'exit_code': proc.returncode, 'timeout': timed_out, 'output': text[:MAX_OUTPUT], 'truncated': len(text) > MAX_OUTPUT}

    def _register(self):
        a = self.add
        def workspace_info(): return {'root': str(self.root), 'tool_count': len(self.tools), 'excluded': sorted(BLOCKED), 'file_limit_bytes': MAX_FILE}
        def list_directory(path: str = '.'):
            out = []
            for p in sorted(self.path(path).iterdir()):
                try: self.path(str(p))
                except ValueError: continue
                out.append({'name': p.name, 'directory': p.is_dir(), 'symlink': p.is_symlink()})
                if len(out) >= 1000: break
            return out
        def file_tree(limit: int = 500): return self.walk('*', limit)
        def glob_files(pattern: str, limit: int = 500): return self.walk(pattern, limit)
        def read_file(path: str): return self.read(path)
        def read_lines(path: str, start: int = 1, count: int = 100):
            if start < 1 or count < 1: raise ValueError('Use positive line numbers/count')
            return [{'line': i + start, 'text': line} for i, line in enumerate(self.read(path).splitlines()[start-1:start-1+min(count,1000)])]
        def file_stat(path: str):
            p=self.path(path); s=p.stat(); return {'bytes': s.st_size, 'modified': s.st_mtime, 'directory': p.is_dir()}
        def path_exists(path: str): return self.path(path).exists()
        def file_hash(path: str):
            p=self.path(path)
            if p.stat().st_size > MAX_FILE: raise ValueError('File too large')
            return hashlib.sha256(p.read_bytes()).hexdigest()
        def search_files(pattern: str): return self.walk(pattern)
        def find_text(text: str, pattern: str = '*', limit: int = 100):
            result=[]
            for path in self.walk(pattern):
                try: lines=self.read(path).splitlines()
                except (UnicodeError, ValueError, OSError): continue
                for i,line in enumerate(lines,1):
                    if text in line: result.append({'path':path,'line':i,'text':line[:500]})
                    if len(result)>=min(max(limit,1),1000): return result
            return result
        def write_file(path: str, content: str): return self.write(path,content)
        def append_file(path: str, content: str): return self.write(path,(self.read(path) if self.path(path).exists() else '')+content)
        def replace_text(path: str, old: str, new: str, expected_count: int = 1):
            if not old: raise ValueError('old must not be empty')
            value=self.read(path)
            if value.count(old)!=expected_count: raise ValueError('Match count differs; read the current file first')
            return self.write(path,value.replace(old,new))
        def insert_lines(path: str, line: int, content: str):
            lines=self.read(path).splitlines(keepends=True)
            if not 1<=line<=len(lines)+1: raise ValueError('Invalid insertion line')
            lines[line-1:line-1]=[content if content.endswith('\n') else content+'\n'];return self.write(path,''.join(lines))
        def delete_lines(path: str, start: int, count: int):
            lines=self.read(path).splitlines(keepends=True)
            if start<1 or count<1 or start-1+count>len(lines): raise ValueError('Invalid line range')
            del lines[start-1:start-1+count];return self.write(path,''.join(lines))
        def make_directory(path: str): self.path(path).mkdir(parents=True,exist_ok=True);return {'created':path}
        def copy_file(source: str, destination: str):
            src,dst=self.path(source),self.path(destination)
            if dst.exists(): raise ValueError('Destination already exists')
            if src.stat().st_size>MAX_FILE: raise ValueError('File too large')
            dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst);return {'copied':destination}
        def move_file(source: str, destination: str):
            src,dst=self.path(source),self.path(destination)
            if not src.is_file() or dst.exists(): raise ValueError('Source must be a file; destination must not exist')
            dst.parent.mkdir(parents=True,exist_ok=True);src.rename(dst);return {'moved':destination}
        def delete_file(path: str):
            p=self.path(path)
            if not p.is_file(): raise ValueError('Only individual files can be deleted')
            p.unlink();return {'deleted':path}
        def remove_empty_directory(path: str):
            p=self.path(path)
            if p==self.root: raise ValueError('Cannot remove workspace root')
            p.rmdir();return {'removed':path}
        def compare_files(left: str, right: str): return ''.join(difflib.unified_diff(self.read(left).splitlines(True),self.read(right).splitlines(True),fromfile=left,tofile=right))
        for fn in [workspace_info,list_directory,file_tree,glob_files,read_file,read_lines,file_stat,path_exists,file_hash,search_files,find_text,compare_files]:a(fn.__name__,fn.__name__.replace('_',' ')+' within the selected workspace.',fn)
        for fn in [write_file,append_file,replace_text,insert_lines,delete_lines,make_directory,copy_file,move_file,delete_file,remove_empty_directory]:a(fn.__name__,fn.__name__.replace('_',' ')+' within the selected workspace.',fn,'write')

        def regex_search(text: str, pattern: str): return [m.group(0) for m in re.finditer(pattern,text[:MAX_OUTPUT])][:1000]
        def regex_replace(text: str, pattern: str, replacement: str): return re.sub(pattern,replacement,text[:MAX_OUTPUT])
        def split_lines(text: str): return text.splitlines()
        def join_lines(lines: list): return '\n'.join(str(x) for x in lines)
        def sort_lines(text: str): return '\n'.join(sorted(text.splitlines()))
        def unique_lines(text: str): return '\n'.join(dict.fromkeys(text.splitlines()))
        def count_text(text: str): return {'characters':len(text),'words':len(text.split()),'lines':len(text.splitlines()),'utf8_bytes':len(text.encode())}
        def trim_text(text: str): return text.strip()
        def normalize_newlines(text: str): return text.replace('\r\n','\n').replace('\r','\n')
        def indent_text(text: str, prefix: str = '    '): return textwrap.indent(text,prefix)
        def dedent_text(text: str): return textwrap.dedent(text)
        def base64_encode(text: str): return base64.b64encode(text.encode()).decode()
        def base64_decode(text: str): return base64.b64decode(text,validate=True).decode()
        def url_encode(text: str): return urllib.parse.quote(text,safe='')
        def url_decode(text: str): return urllib.parse.unquote(text)
        def html_escape(text: str): return html.escape(text)
        def html_unescape(text: str): return html.unescape(text)
        def text_diff(before: str, after: str): return ''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='before',tofile='after'))
        for fn in [regex_search,regex_replace,split_lines,join_lines,sort_lines,unique_lines,count_text,trim_text,normalize_newlines,indent_text,dedent_text,base64_encode,base64_decode,url_encode,url_decode,html_escape,html_unescape,text_diff]:a(fn.__name__,fn.__name__.replace('_',' ')+'; transforms supplied text without changing files.',fn)

        def json_parse(text: str): return json.loads(text)
        def json_format(text: str): return json.dumps(json.loads(text),ensure_ascii=False,indent=2)
        def json_minify(text: str): return json.dumps(json.loads(text),ensure_ascii=False,separators=(',',':'))
        def json_validate(text: str, schema: dict): jsonschema.validate(json.loads(text),schema);return {'valid':True}
        def json_get(text: str, keys: list):
            value=json.loads(text)
            for key in keys:value=value[int(key)] if isinstance(value,list) else value[str(key)]
            return value
        def json_set(text: str, keys: list, value: str):
            obj=json.loads(text);target=obj
            if not keys:return json.loads(value)
            for key in keys[:-1]:target=target[int(key)] if isinstance(target,list) else target[str(key)]
            target[int(keys[-1]) if isinstance(target,list) else str(keys[-1])]=json.loads(value);return obj
        def json_merge(left: str, right: str):
            one,two=json.loads(left),json.loads(right)
            if not isinstance(one,dict) or not isinstance(two,dict):raise ValueError('Both values must be objects')
            return {**one,**two}
        def json_keys(text: str): return list(json.loads(text).keys())
        def json_flatten(text: str):
            output={}
            def walk(value,path):
                if isinstance(value,dict):
                    for k,v in value.items():walk(v,path+'/'+str(k).replace('~','~0').replace('/','~1'))
                elif isinstance(value,list):
                    for k,v in enumerate(value):walk(v,path+'/'+str(k))
                else:output[path]=value
            walk(json.loads(text),'');return output
        for fn in [json_parse,json_format,json_minify,json_validate,json_get,json_set,json_merge,json_keys,json_flatten]:a(fn.__name__,fn.__name__.replace('_',' ')+' on supplied JSON text. keys are a path array; json_set value is JSON text.',fn)

        def csv_read(path: str): return list(csv.DictReader(io.StringIO(self.read(path))))
        def csv_write(path: str, rows: list):
            if not rows:return self.write(path,'')
            out=io.StringIO(newline='');w=csv.DictWriter(out,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows);return self.write(path,out.getvalue())
        def csv_filter(path: str, column: str, equals: str): return [r for r in csv_read(path) if r.get(column)==equals]
        def csv_select(path: str, columns: list): return [{c:r.get(c) for c in columns} for r in csv_read(path)]
        def csv_sort(path: str, column: str): return sorted(csv_read(path),key=lambda r:r[column])
        def csv_statistics(path: str, column: str):
            values=[float(r[column]) for r in csv_read(path)];return {'count':len(values),'sum':sum(values),'mean':sum(values)/len(values) if values else None,'min':min(values) if values else None,'max':max(values) if values else None}
        def csv_headers(path: str): return next(csv.reader(io.StringIO(self.read(path))),[])
        for fn in [csv_read,csv_filter,csv_select,csv_sort,csv_statistics,csv_headers]:a(fn.__name__,fn.__name__.replace('_',' ')+' on a workspace CSV file.',fn)
        a('csv_write','Write rows as a CSV file.',csv_write,'write')

        def zip_create(destination: str, paths: list):
            dst=self.path(destination)
            if dst.exists():raise ValueError('Destination already exists')
            files=[self.path(p) for p in paths]
            if sum(p.stat().st_size for p in files)>MAX_FILE:raise ValueError('Archive exceeds limit')
            with zipfile.ZipFile(dst,'x',zipfile.ZIP_DEFLATED) as z:
                for p in files:
                    if not p.is_file():raise ValueError('Only files can be archived')
                    z.write(p,p.relative_to(self.root).as_posix())
            return {'archive':destination}
        def zip_list(path: str):
            with zipfile.ZipFile(self.path(path)) as z:return [{'name':i.filename,'bytes':i.file_size} for i in z.infolist()][:1000]
        def zip_extract(path: str, destination: str):
            base=self.path(destination)
            with zipfile.ZipFile(self.path(path)) as z:
                infos=z.infolist()
                if len(infos)>1000 or sum(i.file_size for i in infos)>MAX_FILE:raise ValueError('Archive exceeds extraction limits')
                pairs=[]
                for info in infos:
                    p=self.path(str(base/info.filename))
                    if not p.is_relative_to(base) or (info.external_attr>>16)&0o170000==0o120000:raise ValueError('Unsafe archive member')
                    if p.exists():raise ValueError('Extraction would overwrite existing paths')
                    pairs.append((info,p))
                for info,p in pairs:
                    if info.is_dir():p.mkdir(parents=True,exist_ok=True)
                    else:p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(info))
            return {'extracted':len(pairs)}
        def gzip_compress(source: str, destination: str):
            data=self.read(source).encode();p=self.path(destination)
            if p.exists():raise ValueError('Destination exists')
            p.write_bytes(gzip.compress(data));return {'compressed':destination}
        def gzip_decompress(source: str, destination: str):
            with gzip.open(self.path(source),'rb') as f:data=f.read(MAX_FILE+1)
            if len(data)>MAX_FILE:raise ValueError('Decompressed data exceeds limit')
            if self.path(destination).exists():raise ValueError('Destination exists')
            return self.write(destination,data.decode())
        for fn in [zip_create,zip_extract,gzip_compress,gzip_decompress]:a(fn.__name__,fn.__name__.replace('_',' ')+' within workspace; refuses overwrites.',fn,'write')
        a('zip_list','List archive members without extracting.',zip_list)

        def git(args):return self.run(['git','--no-pager','-c','core.hooksPath='+os.devnull,'-c','core.fsmonitor=false',*args])
        def revision(value):
            if value.startswith('-') or not re.fullmatch(r'[\w./~^@{}:+-]+',value):raise ValueError('Invalid git revision')
            return value
        def git_status():return git(['status','--short'])
        def git_diff():return git(['diff','--no-ext-diff','--no-textconv'])
        def git_staged_diff():return git(['diff','--cached','--no-ext-diff','--no-textconv'])
        def git_log(count: int = 20):return git(['log','--oneline','-n',str(min(max(count,1),100))])
        def git_show(rev: str = 'HEAD'):return git(['show','--no-ext-diff','--no-textconv',revision(rev),'--'])
        def git_branches():return git(['branch','--list'])
        def git_current_branch():return git(['branch','--show-current'])
        def git_tracked_files():return git(['ls-files'])
        def git_untracked_files():return git(['ls-files','--others','--exclude-standard'])
        def git_blame(path: str):return git(['blame','--',str(self.path(path).relative_to(self.root))])
        def git_root():return git(['rev-parse','--show-toplevel'])
        def git_stashes():return git(['stash','list'])
        def git_check_ignore(path: str):return git(['check-ignore','--',str(self.path(path).relative_to(self.root))])
        def git_add(paths: list):return git(['add','--',*[str(self.path(p).relative_to(self.root)) for p in paths]])
        def git_commit(message: str):return git(['-c','commit.gpgsign=false','commit','-m',message])
        def git_create_branch(name: str):return git(['branch',revision(name)])
        def git_switch_branch(name: str):return git(['switch',revision(name)])
        for fn in [git_status,git_diff,git_staged_diff,git_log,git_show,git_branches,git_current_branch,git_tracked_files,git_untracked_files,git_blame,git_root,git_stashes,git_check_ignore]:a(fn.__name__,fn.__name__.replace('_',' ')+' in the selected repository.',fn)
        for fn in [git_add,git_commit,git_create_branch,git_switch_branch]:a(fn.__name__,fn.__name__.replace('_',' ')+' in the selected repository.',fn,'write')

        def system_info():return {'os':platform.system(),'release':platform.release(),'architecture':platform.machine(),'python':platform.python_version()}
        def cpu_count():return os.cpu_count()
        def disk_usage():return dict(zip(['total','used','free'],shutil.disk_usage(self.root)))
        def find_executable(name: str):return shutil.which(name)
        def current_time():return {'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'unix':time.time()}
        def generate_uuid():return str(uuid.uuid4())
        def python_syntax_check(path: str):ast.parse(self.read(path),filename=path);return {'valid':True}
        def python_symbols(path: str):return [{'name':n.name,'line':n.lineno,'kind':type(n).__name__} for n in ast.walk(ast.parse(self.read(path))) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))]
        def python_format_ast(code: str):return ast.unparse(ast.parse(code))
        python_runner = [sys.executable, str(Path(__file__).with_name('python_project.py'))]
        def python_run_script(path: str, arguments: list = []):return self.run([*python_runner,'script',str(self.path(path)),*arguments])
        def python_run_snippet(code: str):return self.run([*python_runner,'snippet',code])
        def python_unittest(directory: str = '.'):return self.run([*python_runner,'module','unittest','discover','-s',str(self.path(directory))])
        def python_packages():return self.run([*python_runner,'module','pip','list','--format=json'])
        def run_command(argv: list, cwd: str = '.', timeout: int = 60):return self.run(argv,cwd,timeout)
        def run_shell(command: str, cwd: str = '.', timeout: int = 60):return self.run(['powershell','-NoProfile','-NonInteractive','-Command',command] if os.name=='nt' else ['/bin/sh','-c',command],cwd,timeout)
        def run_tests(argv: list, cwd: str = '.'):return self.run(argv,cwd,120)
        def http_get(url: str):
            if urllib.parse.urlparse(url).scheme not in ('https','http'):raise ValueError('HTTP(S) URL required')
            with urllib.request.urlopen(url,timeout=20) as r:return {'status':r.status,'text':r.read(MAX_OUTPUT).decode('utf-8',errors='replace')}
        def http_head(url: str):
            if urllib.parse.urlparse(url).scheme not in ('https','http'):raise ValueError('HTTP(S) URL required')
            with urllib.request.urlopen(urllib.request.Request(url,method='HEAD'),timeout=20) as r:return {'status':r.status,'headers':dict(r.headers)}
        def project_manifests():return [p for p in self.walk() if Path(p).name in {'package.json','pyproject.toml','requirements.txt','Cargo.toml','go.mod','pom.xml','Makefile'}]
        def find_todos():return find_text('TODO')
        def file_extensions():
            counts={}
            for p in self.walk():ext=Path(p).suffix;counts[ext]=counts.get(ext,0)+1
            return counts
        for fn in [system_info,cpu_count,disk_usage,find_executable,current_time,generate_uuid,python_syntax_check,python_symbols,python_format_ast,project_manifests,find_todos,file_extensions]:a(fn.__name__,fn.__name__.replace('_',' ')+'.',fn)
        for fn in [python_run_script,python_run_snippet,python_unittest,python_packages,run_command,run_shell,run_tests]:a(fn.__name__,fn.__name__.replace('_',' ')+'. Requires execution permission; runs with OS user privileges, not sandboxed.',fn,'execute')
        for fn in [http_get,http_head]:a(fn.__name__,fn.__name__.replace('_',' ')+'. Requires network permission.',fn,'network')
