#!/usr/bin/env python3
"""null web launcher. Static Clyde by default; dynamic Luraph is owner opt-in.

python3 web_server.py --host 0.0.0.0 --port 8080
Never expose dynamic Luau execution to the public internet. Emulation is not
an OS sandbox. See WEB.md for private deployment / GitHub Codespaces.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import hmac
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import tempfile
import time
from urllib.parse import urlsplit, parse_qs

import cli

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / 'web'
MAX_INPUT = 8 * 1024 * 1024
MAX_BODY = (MAX_INPUT * 4 // 3) + 65536
JOB_TTL = 24 * 3600
SESSION_TTL = 7 * 24 * 3600
TERMINAL = {'ready', 'partial', 'unverified', 'failed', 'cancelled', 'interrupted'}


class WorkerKeyError(PermissionError):
    """Only the owner key is missing/invalid; never weaken job authorization."""


def detection(data):
    text = data[:20000].decode('utf-8', errors='replace')
    luraph = cli.BANNER.search(text[:4096])
    if luraph:
        version = luraph.group(1)
        engine = next((e for e in ('14.7', '14.8', '14.9', '15') if version == e or version.startswith(e + '.')), None)
        return {'engine': 'luraph', 'version': version, 'backend': engine,
                'warning': '15.1+ compatibility is experimental; full recovery is not verified.' if version.startswith('15.') and not version.startswith('15.0') else None}
    if re.search(r'clydeprotection|Clyde Protection|ClydeProtection', text, re.I):
        version = re.search(r'(?:Protection|Clyde)[^\r\n]{0,30}?\bV\s*(\d+)', text, re.I)
        return {'engine': 'clyde', 'version': version.group(1) if version else 'auto', 'backend': 'clyde', 'warning': None}
    return {'engine': None, 'version': None, 'backend': None, 'warning': 'No reliable signature. Select the engine/version manually.'}


def clean_environment():
    env = {k: os.environ[k] for k in ('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'LANG') if k in os.environ}
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
    return env


def kill_process(process):
    if process is None:
        return
    try:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=10)
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass


class Job:
    def __init__(self, owner, folder, name, data, settings):
        self.id = folder.name
        self.owner = owner
        self.folder = folder
        self.name = name
        self.data = data
        self.settings = settings
        self.created = time.time()
        self.finished = None
        self.state = 'queued'
        self.stage = 0
        self.logs = []
        self.log_bytes = 0
        self.cancelled = threading.Event()
        self.process = None
        self.lock = threading.RLock()
        self.result = None
        self.report = {}
        self.detected = detection(data)
        self.filename = re.sub(r'[^A-Za-z0-9_.-]', '_', Path(name.replace('\\', '/')).name)[:100] or 'script.lua'

    def log(self, text):
        with self.lock:
            text = str(text)[:3000]
            # Bounded log history, including very chatty or hostile input.
            cost = len(text.encode('utf-8')) + 1
            if len(self.logs) < 4000 and self.log_bytes + cost <= 256000:
                self.logs.append(text)
                self.log_bytes += cost

    def snapshot(self, after=0):
        with self.lock:
            return {'id': self.id, 'name': self.filename, 'state': self.state, 'stage': self.stage,
                    'logs': self.logs[after:after + 200], 'cursor': min(len(self.logs), after + 200),
                    'detection': self.detected, 'report': self.report, 'created': self.created, 'finished': self.finished, 'settings': self.settings,
                    'download': f'/api/jobs/{self.id}/download' if self.result else None}


class Manager:
    def __init__(self, data_dir, allow_dynamic=False, access_key='', timeout=180):
        if allow_dynamic and len(access_key) < 24:
            raise ValueError('Dynamic Luraph needs NULL_WEB_ACCESS_KEY (at least 24 characters). Use a private sandbox, never a public worker.')
        self.folder = Path(data_dir).resolve()
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.allow_dynamic = allow_dynamic
        self.access_key = access_key
        self.timeout = timeout
        self.jobs = {}
        self.lock = threading.RLock()
        self.pending = queue.Queue(maxsize=4)
        self.stopping = threading.Event()
        self.session_secret = self.load_session_secret()
        self.restore_jobs()
        self.worker = threading.Thread(target=self.work, daemon=True)
        self.worker.start()

    def load_session_secret(self):
        path = self.folder / '.session-secret'
        if path.is_file() and not path.is_symlink() and path.stat().st_size == 32:
            value = path.read_bytes()
            if len(value) == 32:
                return value
        value = secrets.token_bytes(32)
        with tempfile.NamedTemporaryFile(dir=self.folder, delete=False) as file:
            file.write(value)
            temporary = file.name
        os.replace(temporary, path)
        return value

    def persist(self, job):
        if not job.folder.is_dir():
            return
        with job.lock:
            record = dict(job.snapshot(), owner=job.owner, logs=list(job.logs), result=job.result.name if job.result else None)
            record.pop('download', None)
            record.pop('cursor', None)
            encoded = json.dumps(record, ensure_ascii=False).encode('utf-8')
            if len(encoded) > 2 * 1024 * 1024:
                job.log('[warning] Result metadata exceeds the saved-history limit; download before restarting the worker.')
                return
            with tempfile.NamedTemporaryFile(dir=job.folder, delete=False) as file:
                file.write(encoded)
                temporary = file.name
            os.replace(temporary, job.folder / 'job.json')

    def restore_jobs(self):
        for folder in self.folder.iterdir():
            if not folder.is_dir() or not re.fullmatch(r'[0-9a-f]{32}', folder.name):
                continue
            try:
                if folder.is_symlink():
                    continue
                path = folder / 'job.json'
                if path.is_symlink() or path.stat().st_size > 2 * 1024 * 1024:
                    raise ValueError('Invalid journal')
                record = json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(record, dict) or not isinstance(record.get('report'), dict) or not isinstance(record.get('settings'), dict) or not isinstance(record.get('logs'), list):
                    raise ValueError('Invalid journal shape')
                if not re.fullmatch(r'[0-9a-f]{48}\.[0-9a-f]{64}', record['owner']):
                    raise ValueError('Invalid owner')
                if time.time() - (record.get('finished') or record['created']) > JOB_TTL or len(self.jobs) >= 20:
                    raise ValueError('Expired history')
                job = Job(record['owner'], folder, record['name'], b'', record['settings'])
                job.created, job.finished = record['created'], record.get('finished')
                job.detected = record.get('detection', {})
                job.state, job.stage = record['state'], int(record['stage'])
                for line in record.get('logs', [])[:4000]:
                    job.log(line)
                job.report = record.get('report', {})
                result = record.get('result')
                if result in ('result.lua', 'result.json') and (folder / result).is_file() and not (folder / result).is_symlink():
                    target = folder / result
                    if target.stat().st_size <= 16 * 1024 * 1024 and hashlib.sha256(target.read_bytes()).hexdigest() == job.report.get('output_sha256'):
                        job.result = target
                if job.state not in TERMINAL:
                    job.state, job.result, job.finished = 'interrupted', None, time.time()
                    job.log('[interrupted] Worker restarted before this job finished. Upload again; code is never automatically rerun.')
                elif result and not job.result:
                    job.state = 'failed'
                    job.log('[error] Saved result missing or changed; download unavailable.')
                self.jobs[job.id] = job
                self.persist(job)
            except (OSError, ValueError, KeyError, TypeError):
                shutil.rmtree(folder, ignore_errors=True)

    def history(self, owner):
        self.cleanup()
        with self.lock:
            jobs = [job for job in self.jobs.values() if hmac.compare_digest(job.owner, owner)]
        records = []
        for job in sorted(jobs, key=lambda item: item.created, reverse=True):
            item = job.snapshot()
            records.append({key: item[key] for key in ('id', 'name', 'state', 'stage', 'created', 'finished', 'settings', 'download')})
        return records

    def cleanup(self):
        with self.lock:
            expired = [j for j in self.jobs.values() if j.state in TERMINAL and time.time() - (j.finished or j.created) > JOB_TTL]
            for job in expired:
                self.jobs.pop(job.id, None)
                shutil.rmtree(job.folder, ignore_errors=True)

    def require_owner_key(self, key):
        if not hmac.compare_digest(key.encode('utf-8'), self.access_key.encode('utf-8')):
            raise WorkerKeyError('Missing or incorrect owner key. Open Worker settings, paste the current key from your Codespace terminal, and check it before starting. A restarted worker may have a new key.')

    def submit(self, owner, name, data, settings, key=''):
        if not data or len(data) > MAX_INPUT:
            raise ValueError('Choose a non-empty Lua/text file no larger than 8 MiB.')
        if settings.get('engine', 'auto') not in ('auto', 'clyde', 'luraph'):
            raise ValueError('Unknown engine.')
        if settings.get('version', 'auto') not in ('auto', '14.7', '14.8', '14.9', '15', '15.0', '15.1'):
            raise ValueError('Unknown Luraph version.')
        if settings.get('mode', 'deobfuscate') not in ('deobfuscate', 'trace', 'inspect'):
            raise ValueError('Unknown mode.')
        detected = detection(data)
        engine = settings.get('engine', 'auto')
        engine = detected['engine'] if engine == 'auto' else engine
        if engine is None:
            raise ValueError('No supported signature found. Choose Clyde or Luraph explicitly.')
        if engine == 'luraph' and settings.get('mode') != 'inspect':
            if not self.allow_dynamic:
                raise PermissionError('Dynamic Luraph is disabled on this safe-mode server. Static VM inspection is available; see WEB.md for a private, owner-authenticated worker.')
            self.require_owner_key(key)
        self.cleanup()
        with self.lock:
            if len(self.jobs) >= 20 or self.pending.full():
                raise ValueError('Worker queue is full. Try again after a job finishes or expires.')
            folder = self.folder / secrets.token_hex(16)
            folder.mkdir(mode=0o700)
            job = Job(owner, folder, name, data, dict(settings, engine=engine))
            self.jobs[job.id] = job
            try:
                self.persist(job)
            except OSError:
                self.jobs.pop(job.id, None)
                shutil.rmtree(folder, ignore_errors=True)
                raise
            self.pending.put_nowait(job)
        return job

    def find(self, job_id, owner):
        self.cleanup()
        with self.lock:
            job = self.jobs.get(job_id)
            return job if job and hmac.compare_digest(job.owner, owner) else None

    def run_command(self, job, command):
        if job.cancelled.is_set():
            raise InterruptedError('Cancelled before engine start.')
        env = clean_environment()
        env['HOME'] = str(job.folder)
        kwargs = {'start_new_session': True} if os.name != 'nt' else {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs)
        with job.lock:
            job.process = process
        deadline = time.monotonic() + self.timeout
        finished = threading.Event()
        def watch():
            while not finished.is_set():
                if job.cancelled.wait(0.15) or time.monotonic() >= deadline:
                    kill_process(process)
                    return
        monitor = threading.Thread(target=watch, daemon=True)
        monitor.start()
        try:
            # Read bounded chunks, not unbounded lines from untrusted engine output.
            while True:
                line = process.stdout.readline(4096)
                if not line:
                    break
                job.log(line.decode('utf-8', errors='replace').rstrip())
            code = process.wait()
        finally:
            finished.set()
            kill_process(process)
            process.stdout.close()
            monitor.join(timeout=1)
            with job.lock:
                job.process = None
        if job.cancelled.is_set():
            raise InterruptedError('Cancelled by you.')
        if time.monotonic() >= deadline:
            raise TimeoutError('Engine time limit reached; no result published.')
        if code:
            raise RuntimeError(f'Engine exited with code {code}. See the log above.')

    def execute(self, job):
        with job.lock:
            if job.cancelled.is_set():
                job.state = 'cancelled'
                return
            job.state = 'running'
            job.stage = 1
        self.persist(job)
        source = job.folder / 'input.lua'
        source.write_bytes(job.data)
        job.data = b''
        output = job.folder / 'result.lua'
        meta = job.folder / 'engine.json'
        engine = job.settings['engine']
        job.log(f'[receive] {job.filename} received. Original file is never modified.')
        job.log(f'[detect] {engine} / version {job.detected.get("version") or "manual"}')
        if job.detected.get('warning'):
            job.log('[warning] ' + job.detected['warning'])
        mode = job.settings.get('mode', 'deobfuscate')
        with job.lock:
            job.stage = 2
        if engine == 'clyde':
            node = shutil.which('node')
            if not node:
                raise RuntimeError('Node.js 16+ is required for Clyde. See WEB.md.')
            if mode != 'deobfuscate':
                raise ValueError('Clyde supports static deobfuscation; select Deobfuscate mode.')
            command = [node, '--max-old-space-size=256', str(ROOT / 'clyde_cli.js'), str(source), '-o', str(output), '--report', str(meta)]
        elif mode == 'inspect':
            if not cli.find_ast():
                raise RuntimeError('AST tool missing. Run python start.py --setup.')
            output = job.folder / 'result.json'
            command = [sys.executable, '-B', str(cli.ENGINE_ROOT / 'obfuscators/luraph_v15/inspect15_1.py'), str(source), '-o', str(output)]
        else:
            version = job.settings.get('version', 'auto')
            backend = job.detected.get('backend') if version == 'auto' else ('15' if version.startswith('15.') else version)
            if not backend:
                raise ValueError('Select a supported Luraph version; auto detection was inconclusive.')
            if not cli.find_runtime() or not cli.find_ast():
                raise RuntimeError('Luau tools missing. Run python start.py --setup.')
            command = [sys.executable, '-B', str(ROOT / 'cli.py'), str(source), '-o', str(output), '--engine', backend,
                       '--job-timeout', str(max(1, self.timeout - 5)), '--no-color']
            if mode == 'trace':
                command.append('--trace-only')
            job.log('[warning] This engine executes input in emulation, NOT an OS sandbox. Recovery may be partial.')
        self.run_command(job, command)
        if engine == 'clyde' and meta.exists():
            from clyde_refine import refine_if_known
            if refine_if_known(source, output, meta, cli.find_ast()):
                job.log('[refine] null sample-scoped pass: recovered the reviewed RoMidi loader, not its external MIDI payload.')
        if not output.is_file() or not output.stat().st_size:
            raise RuntimeError('Engine returned no non-empty result.')
        if output.stat().st_size > 16 * 1024 * 1024:
            raise RuntimeError('Output exceeds the 16 MiB download limit.')
        with job.lock:
            job.stage = 3
        job.log('[validate] Checking output without executing the recovered file.')
        report = json.loads(meta.read_text()) if meta.exists() else {}
        state = 'unverified'
        if output.suffix == '.json':
            json.loads(output.read_text())
            report.update(status='static_analysis_only', syntax_valid=None)
            state = 'partial'
        elif cli.find_ast():
            executable = cli.validate_result(output)
            report.update(syntax_valid=True, has_executable_statements=executable)
            if engine == 'clyde':
                state = 'partial' if report.get('status') == 'partial' or not executable else 'ready'
            else:
                # Syntax and process exit status alone cannot certify a lifted VM.
                state = 'partial'
                report['status'] = 'recovered_with_unverified_completeness'
        else:
            job.log('[warning] AST tool unavailable. Syntax has NOT been validated.')
            state = 'partial' if report.get('status') == 'partial' else 'unverified'
        job.log('[notice] Saved does not mean complete, safe, or behaviorally equivalent. Recovered output was not executed.')
        report.update(owner='null', engine=engine, mode=mode,
                      input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), input_bytes=source.stat().st_size,
                      source_executed=(engine == 'luraph' and mode != 'inspect'),
                      behavioral_equivalence_verified=False, recovered_output_executed=False,
                      output_bytes=output.stat().st_size,
                      output_sha256=hashlib.sha256(output.read_bytes()).hexdigest())
        with job.lock:
            if job.cancelled.is_set():
                raise InterruptedError('Cancelled before publication.')
            job.result = output
            job.report = report
            job.stage = 4
            job.state = state
        job.log('[saved] ' + ('Partial recovery / analysis' if state == 'partial' else 'Recovery saved; review limitations'))

    def work(self):
        while not self.stopping.is_set():
            try:
                job = self.pending.get(timeout=.3)
            except queue.Empty:
                self.cleanup()
                continue
            try:
                self.execute(job)
            except InterruptedError as exc:
                with job.lock:
                    job.state = 'interrupted' if self.stopping.is_set() else 'cancelled'
                job.log(('[' + job.state + '] ') + str(exc))
            except Exception as exc:
                with job.lock:
                    job.state = 'interrupted' if self.stopping.is_set() else 'failed'
                    job.result = None
                job.log(('[interrupted] ' if self.stopping.is_set() else '[error] ') + str(exc))
            finally:
                job.data = b''
                job.finished = time.time()
                try:
                    self.persist(job)
                except OSError:
                    job.log('[warning] Could not save restart history; download before stopping this worker.')
                self.pending.task_done()

    def close(self):
        self.stopping.set()
        with self.lock:
            for job in self.jobs.values():
                job.cancelled.set()
                kill_process(job.process)
        self.worker.join(timeout=5)
        with self.lock:
            for job in self.jobs.values():
                with job.lock:
                    if job.state not in TERMINAL:
                        job.state, job.result = 'interrupted', None
                        job.log('[interrupted] Worker stopped. Upload again to restart; no automatic execution.')
                    job.finished = job.finished or time.time()
                self.persist(job)


class Handler(BaseHTTPRequestHandler):
    server_version = 'null'
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass  # Do not persist upload names, access keys or result URLs in access logs.

    @property
    def manager(self):
        return self.server.manager

    def send(self, status, data, content_type='application/json; charset=utf-8', extra=None):
        body = json.dumps(data).encode() if isinstance(data, (dict, list)) else data
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def session(self):
        jar = cookies.SimpleCookie()
        try:
            jar.load(self.headers.get('Cookie', ''))
            sid = jar.get('null_session')
            sid = sid.value if sid else ''
        except cookies.CookieError:
            sid = ''
        # Stateless, server-authenticated cookie: a caller cannot forge another owner's session.
        pieces = sid.split('.')
        if len(pieces) == 2 and re.fullmatch('[0-9a-f]{48}', pieces[0]) and re.fullmatch('[0-9a-f]{64}', pieces[1]):
            expected = hmac.new(self.server.secret, pieces[0].encode(), hashlib.sha256).hexdigest()
            if hmac.compare_digest(pieces[1], expected):
                return sid
        return None

    def csrf(self, sid):
        return hmac.new(self.server.secret, ('csrf:' + sid).encode(), hashlib.sha256).hexdigest()

    def do_GET(self):
        try:
            self.get()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.close_connection = True

    def get(self):
        url = urlsplit(self.path)
        if url.path in ('/', '/index.html', '/app.js', '/runtime-link.js', '/workspace-store.js', '/style.css'):
            name = {'/': 'index.html', '/index.html': 'index.html', '/app.js': 'app.js', '/runtime-link.js': 'runtime-link.js', '/workspace-store.js': 'workspace-store.js', '/style.css': 'style.css'}[url.path]
            mime = {'html': 'text/html; charset=utf-8', 'js': 'text/javascript; charset=utf-8', 'css': 'text/css; charset=utf-8'}[name.split('.')[-1]]
            return self.send(200, (STATIC / name).read_bytes(), mime)
        if url.path == '/api/session':
            sid = self.session()
            if not sid:
                nonce = secrets.token_hex(24)
                sid = nonce + '.' + hmac.new(self.server.secret, nonce.encode(), hashlib.sha256).hexdigest()
            host = self.headers.get('Host', '').split(':')[0].lower()
            https = self.headers.get('X-Forwarded-Proto', '').split(',')[0].strip() == 'https' or host.endswith(('.e2b.app', '.app.github.dev'))
            # HTTPS previews may be embedded cross-site. CHIPS keeps their cookie
            # partitioned by top-level site; signed ownership + CSRF still gate writes.
            policy = '; Secure; SameSite=None; Partitioned' if https else '; SameSite=Strict'
            return self.send(200, {'csrf': self.csrf(sid), 'max_bytes': MAX_INPUT,
                                  'dynamic_enabled': self.manager.allow_dynamic,
                                  'node_available': bool(shutil.which('node')), 'ast_available': bool(cli.find_ast()),
                                  'runtime_available': bool(cli.find_runtime()),
                                  'owner_key_command': f'cat output/private-worker-{self.server.server_port}.key'}, extra={
                                      'Set-Cookie': 'null_session=' + sid + '; HttpOnly; Path=/; Max-Age=' + str(SESSION_TTL) + policy})
        if url.path == '/api/jobs':
            sid = self.session()
            if not sid:
                return self.send(403, {'error': 'Reload to establish your session.'})
            return self.send(200, {'jobs': self.manager.history(sid), 'retention_seconds': JOB_TTL})
        match = re.fullmatch(r'/api/jobs/([0-9a-f]{32})(/download|/preview|/report)?', url.path)
        sid = self.session()
        job = self.manager.find(match[1], sid) if match and sid else None
        if not job:
            return self.send(404, {'error': 'Not found or this session does not own the job.'})
        action = match[2]
        if not action:
            try:
                after = max(0, int(parse_qs(url.query).get('after', ['0'])[0]))
            except ValueError:
                return self.send(400, {'error': 'Invalid log cursor.'})
            return self.send(200, job.snapshot(after))
        with job.lock:
            if not job.result or job.state not in TERMINAL:
                return self.send(409, {'error': 'No downloadable result yet.'})
            if action == '/report':
                return self.send(200, job.report)
            if action == '/preview':
                with job.result.open('rb') as inp:
                    content = inp.read(200000)
                return self.send(200, {'text': content.decode('utf-8', errors='replace'),
                                       'truncated': job.result.stat().st_size > len(content)})
            suffix = '.vm-map.json' if job.result.suffix == '.json' else ('.partial.lua' if job.state == 'partial' else '.recovered.lua')
            if job.report.get('external_payload_included') is False:
                suffix = '.loader.lua'
            filename = Path(job.filename).stem[:80] + suffix
            return self.send(200, job.result.read_bytes(), 'application/octet-stream',
                             {'Content-Disposition': 'attachment; filename="' + filename + '"'})

    def do_POST(self):
        try:
            self.post()
        except (ValueError, json.JSONDecodeError, UnicodeError) as exc:
            self.send(400, {'error': str(exc)})
        except WorkerKeyError as exc:
            self.send(403, {'error': str(exc), 'code': 'worker_key_required'})
        except PermissionError as exc:
            self.send(403, {'error': str(exc)})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.send(500, {'error': 'Server error; no result published.'})

    def post(self):
        origin = self.headers.get('Origin')
        if origin and urlsplit(origin).netloc != self.headers.get('Host'):
            self.close_connection = True
            return self.send(403, {'error': 'Cross-origin writes are disabled. Use the same-origin launcher.'})
        sid = self.session()
        if not sid or not hmac.compare_digest(self.headers.get('X-CSRF-Token', '').encode('utf-8'), self.csrf(sid).encode('ascii')):
            self.close_connection = True
            return self.send(403, {'error': 'Reload the page to establish a session.'})
        if self.headers.get('Transfer-Encoding'):
            self.close_connection = True
            return self.send(400, {'error': 'Chunked uploads are not accepted.'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            length = -1
        if not 0 < length <= MAX_BODY:
            self.close_connection = True
            return self.send(413, {'error': 'Upload request exceeds the size limit.'})
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            self.close_connection = True
            return self.send(415, {'error': 'Use JSON uploads.'})
        self.connection.settimeout(30)
        body = self.rfile.read(length)
        if len(body) != length:
            raise ValueError('Incomplete request body.')
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError('Expected a JSON object.')
        if self.path in ('/api/detect', '/api/jobs') and not isinstance(payload.get('data'), str):
            raise ValueError('File data must be a base64 string.')
        if self.path == '/api/jobs/clear-history':
            with self.manager.lock:
                for job in list(self.manager.jobs.values()):
                    if hmac.compare_digest(job.owner, sid) and job.state in TERMINAL:
                        self.manager.jobs.pop(job.id, None)
                        shutil.rmtree(job.folder, ignore_errors=True)
            return self.send(200, {'ok': True})
        if self.path == '/api/worker/check-key':
            if not self.manager.allow_dynamic:
                raise PermissionError('Dynamic Luraph is disabled on this worker.')
            self.manager.require_owner_key(self.headers.get('X-Worker-Key', ''))
            return self.send(200, {'valid': True})
        if self.path == '/api/detect':
            data = base64.b64decode(payload.get('data', ''), validate=True)
            if len(data) > MAX_INPUT:
                raise ValueError('Input exceeds 8 MiB.')
            return self.send(200, detection(data))
        if self.path == '/api/jobs':
            data = base64.b64decode(payload.get('data', ''), validate=True)
            settings = payload.get('settings', {})
            if not isinstance(settings, dict) or not isinstance(payload.get('filename', ''), str):
                raise ValueError('Invalid settings or filename.')
            job = self.manager.submit(sid, payload.get('filename', 'script.lua'), data, settings,
                                      self.headers.get('X-Worker-Key', ''))
            return self.send(202, job.snapshot())
        match = re.fullmatch(r'/api/jobs/([0-9a-f]{32})/cancel', self.path)
        job = self.manager.find(match[1], sid) if match else None
        if not job:
            return self.send(404, {'error': 'Job not found.'})
        with job.lock:
            if job.state not in TERMINAL:
                job.cancelled.set()
                if job.state == 'queued':
                    job.state = 'cancelled'
                kill_process(job.process)
        return self.send(200, job.snapshot())


class Server(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, manager):
        self.manager = manager
        self.secret = manager.session_secret if manager else secrets.token_bytes(32)
        super().__init__(address, Handler)


def load_private_key(path):
    """Reuse only a bounded, locally generated URL-safe key, never a symlink."""
    path = Path(path)
    try:
        if path.is_symlink():
            return None
        with path.open('r', encoding='ascii') as file:
            raw = file.read(257)
        if len(raw) > 256:
            return None
        key = raw.strip()
        if 24 <= len(key) <= 256 and re.fullmatch(r'[A-Za-z0-9_-]+', key):
            return key
    except (OSError, UnicodeError):
        pass
    return None


def save_private_key(path, key):
    """Owner-readable key, atomically replaced; never print it in server logs."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, prefix='.null-key-', delete=False) as file:
            temporary = Path(file.name)
            file.write(key + '\n')
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=int(os.environ.get('PORT', '8080')))
    parser.add_argument('--allow-dynamic', action='store_true', help='private owner-only Luraph execution; needs NULL_WEB_ACCESS_KEY')
    parser.add_argument('--private-worker', action='store_true', help='explicitly enable owner-key Luraph and generate a local key if no environment key is provided; use a disposable PRIVATE host')
    parser.add_argument('--timeout', type=int, default=180)
    parser.add_argument('--data-dir', type=Path, default=None)
    args = parser.parse_args()
    if not 10 <= args.timeout <= 1800:
        parser.error('--timeout must be 10–1800 seconds')
    dynamic = args.allow_dynamic or args.private_worker
    key = os.environ.get('NULL_WEB_ACCESS_KEY', '')
    generated = args.private_worker and not key
    if generated:
        key = secrets.token_urlsafe(36)
    if dynamic and len(key) < 24:
        parser.error('Dynamic Luraph needs NULL_WEB_ACCESS_KEY (at least 24 characters), or use --private-worker to generate one locally.')
    # Bind before cleaning any job directory. A duplicate launch must not delete
    # uploads/results belonging to the worker already using this port.
    try:
        server = Server((args.host, args.port), None)
    except OSError as exc:
        parser.error(f'Cannot listen on port {args.port}: {exc}. Use a free private port or stop the existing worker.')
    manager = None
    try:
        folder = f'private-web-jobs-{server.server_port}' if args.private_worker else ('web-jobs' if server.server_port == 8080 else f'web-jobs-{server.server_port}')
        data_dir = args.data_dir or ROOT / 'output' / folder
        if generated:
            key_path = ROOT / 'output' / f'private-worker-{server.server_port}.key'
            key = load_private_key(key_path) or key
        manager = Manager(data_dir, dynamic, key, args.timeout)
        server.manager = manager
        server.secret = manager.session_secret
        if generated:
            key_path = ROOT / 'output' / f'private-worker-{server.server_port}.key'
            save_private_key(key_path, key)
            print(f'Owner key file (retained across restarts, never logged): {key_path}', flush=True)
            print('Read that file locally and paste the key in Worker settings in the PRIVATE runner tab. Never paste it into Pages or make this port public.', flush=True)
    except BaseException:
        if manager:
            manager.close()
        server.server_close()
        raise
    print(f'null web • listening on {args.host}:{server.server_port}', flush=True)
    print('Clyde: static • Luraph execution: ' + ('OWNER-KEY ONLY — emulation is NOT an OS sandbox' if dynamic else 'disabled (safe mode); static VM inspection available'), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        manager.close()


if __name__ == '__main__':
    main()
