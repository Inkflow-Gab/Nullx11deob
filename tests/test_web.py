"""HTTP, isolation, static-engine and sample-scope regressions. No user Lua is executed."""
import base64
import contextlib
import io
import http.cookiejar
import json
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPCookieProcessor
from unittest.mock import patch

import cli
import clyde_refine
import web_server as web

FIXTURE = b'-- Clyde clydeprotection\nprint("null static fixture")\n'


class WebUnitTests(unittest.TestCase):
    def test_luraph_minor_detection_and_warning(self):
        detected = web.detection(b'-- This file was protected using Luraph Obfuscator v15.1\nreturn 1')
        self.assertEqual(detected['backend'], '15')
        self.assertEqual(detected['version'], '15.1')
        self.assertIn('experimental', detected['warning'])

    def test_clyde_and_unknown_detection(self):
        self.assertEqual(web.detection(FIXTURE)['engine'], 'clyde')
        self.assertIsNone(web.detection(b'print("unrecognized")')['engine'])

    def test_child_environment_does_not_inherit_credentials(self):
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'test-only', 'NULL_WEB_ACCESS_KEY': 'test-only', 'AWS_SECRET_ACCESS_KEY': 'test-only'}):
            env = web.clean_environment()
            for key in ('GITHUB_TOKEN', 'NULL_WEB_ACCESS_KEY', 'AWS_SECRET_ACCESS_KEY'):
                self.assertNotIn(key, env)

    def test_dynamic_mode_requires_owner_key(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                web.Manager(folder, allow_dynamic=True, access_key='short')

    def test_refinement_refuses_other_inputs_without_parsing(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'unknown.lua'
            source.write_bytes(FIXTURE)
            with patch('clyde_refine.subprocess.run') as run:
                self.assertFalse(clyde_refine.refine_if_known(source, 'missing', 'missing', 'ast'))
                run.assert_not_called()

    def test_reviewed_decoder_rejects_unknown_instruction(self):
        with self.assertRaises(ValueError):
            clyde_refine.decode_code([999, 0, 0, 0])

    def test_text_attachment_recognition_does_not_scan_unrelated_text(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'RoMidi.txt'
            source.write_bytes(FIXTURE)
            self.assertTrue(cli.is_lua_path(source))
            source.write_text('ordinary notes')
            self.assertFalse(cli.is_lua_path(source))

    def test_private_dynamic_key_is_required_and_not_kept_in_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = web.Manager(folder, allow_dynamic=True, access_key='owner-key-for-unit-test-only-24')
            self.addCleanup(manager.close)
            fixture = b'-- Luraph Obfuscator v15.1\nreturn 1'
            with self.assertRaises(PermissionError):
                manager.submit('owner', 'in.lua', fixture, {'engine': 'luraph'}, key='wrong')
            with patch.object(manager, 'execute'):
                job = manager.submit('owner', 'in.lua', fixture, {'engine': 'luraph'}, key=manager.access_key)
                manager.pending.join()
                self.assertNotIn('key', job.settings)

    def test_logs_are_bounded(self):
        job = web.Job('owner', Path('a' * 32), 'in.lua', b'', {})
        for _ in range(400):
            job.log('x' * 10000)
        self.assertLessEqual(job.log_bytes, 256000)
        self.assertLessEqual(len(job.snapshot()['logs']), 200)
        blank = web.Job('owner', Path('b' * 32), 'in.lua', b'', {})
        for _ in range(5000):
            blank.log('')
        self.assertLessEqual(len(blank.logs), 4000)
        self.assertGreater(blank.log_bytes, 0)

    def test_duplicate_start_cannot_clean_running_workers_job_directory(self):
        with patch('sys.argv', ['web_server.py', '--private-worker', '--port', '8081']), \
             patch.object(web, 'Server', side_effect=OSError('address in use')), \
             patch.object(web, 'Manager') as manager, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                web.main()
        manager.assert_not_called()

    def test_generated_owner_key_is_private_and_atomic(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'worker.key'
            web.save_private_key(path, 'test-key-not-a-real-credential')
            self.assertEqual(path.read_text().strip(), 'test-key-not-a-real-credential')
            if web.os.name != 'nt':
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            web.save_private_key(path, 'replacement-test-key')
            self.assertEqual(path.read_text().strip(), 'replacement-test-key')
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()), ['worker.key'])

    def test_clyde_command_routes_to_static_adapter(self):
        with patch('cli.shutil.which', return_value='node'):
            command = cli.engine_command(Path('input.lua'), Path('out.lua'), 'clyde')
            self.assertIn(str(cli.ROOT / 'clyde_cli.js'), command)
            self.assertIn('--report', command)
            with self.assertRaises(ValueError):
                cli.engine_command(Path('input.lua'), Path('out.lua'), 'clyde', trace_only=True)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.manager = web.Manager(self.temp.name, timeout=10)
        self.server = web.Server(('127.0.0.1', 0), self.manager)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)
        self.client = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.session = self.request('/api/session')[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.manager.close()
        self.thread.join(timeout=3)
        self.temp.cleanup()

    def request(self, path, payload=None, headers=None, client=None):
        data = json.dumps(payload).encode() if payload is not None else None
        hdr = {'Content-Type': 'application/json', 'X-CSRF-Token': self.session['csrf'] if hasattr(self, 'session') else ''}
        hdr.update(headers or {})
        req = Request(self.base + path, data=data, headers=hdr)
        try:
            with (client or self.client).open(req, timeout=20) as response:
                body = response.read()
                return response.status, json.loads(body) if 'application/json' in response.headers.get('Content-Type', '') else body
        except HTTPError as error:
            return error.code, json.loads(error.read())

    def payload(self, data=FIXTURE, **settings):
        return {'filename': '../../input.txt', 'data': base64.b64encode(data).decode(), 'settings': settings}

    def test_html_static_assets_and_no_path_traversal(self):
        code, html = self.request('/')
        self.assertEqual(code, 200)
        self.assertIn(b'A clearer view', html)
        self.assertEqual(self.request('/web_server.py')[0], 404)
        self.assertEqual(self.request('/../.git/config')[0], 404)
        self.assertEqual(self.request('/app.js')[0], 200)

    def test_https_preview_uses_secure_partitioned_cookie(self):
        with self.client.open(Request(self.base + '/api/session', headers={'X-Forwarded-Proto': 'https'})) as response:
            policy = response.headers['Set-Cookie']
            self.assertIn('Secure', policy)
            self.assertIn('HttpOnly', policy)
            self.assertIn('SameSite=None', policy)
            self.assertIn('Partitioned', policy)

    def test_cross_origin_writes_rejected(self):
        status, _ = self.request('/api/jobs', self.payload(engine='clyde'), {'Origin': 'https://attacker.invalid'})
        self.assertEqual(status, 403)

    def test_csrf_and_foreign_session_rejected(self):
        self.assertEqual(self.request('/api/jobs', self.payload(), {'X-CSRF-Token': ''})[0], 403)
        stranger = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.assertEqual(self.request('/api/jobs', self.payload(), client=stranger)[0], 403)

    def test_invalid_base64_and_empty_upload(self):
        self.assertEqual(self.request('/api/jobs', {'data': '!!!!', 'settings': {}})[0], 400)
        self.assertEqual(self.request('/api/jobs', self.payload(b''))[0], 400)

    def test_json_type_validation(self):
        for data in (None, [], 123, {}):
            self.assertEqual(self.request('/api/detect', {'data': data})[0], 400)
        for settings in (None, [], 123, 'shell'):
            payload = self.payload()
            payload['settings'] = settings
            self.assertEqual(self.request('/api/jobs', payload)[0], 400)
        self.assertEqual(self.request('/api/jobs', [1, 2])[0], 400)

    def test_expired_results_are_not_served(self):
        job = web.Job(self.request_session_id(), Path(self.temp.name) / ('b' * 32), 'in.lua', b'', {})
        job.folder.mkdir()
        job.result = job.folder / 'result.lua'
        job.result.write_text('print("expired")')
        job.state = 'ready'
        job.created = time.time() - 3601
        self.manager.jobs[job.id] = job
        self.assertEqual(self.request('/api/jobs/' + job.id + '/download')[0], 404)
        self.assertFalse(job.folder.exists())

    def request_session_id(self):
        # Session is a signed cookie, not the CSRF token returned to JavaScript.
        for handler in self.client.handlers:
            if isinstance(handler, HTTPCookieProcessor):
                return next(cookie.value for cookie in handler.cookiejar if cookie.name == 'null_session')
        self.fail('No session cookie')

    def test_cancel_running_and_queued_jobs_without_publication(self):
        entered, release = threading.Event(), threading.Event()
        def hold(job):
            if job.cancelled.is_set():
                raise InterruptedError('Cancelled queued job')
            with job.lock:
                job.state = 'running'
            entered.set()
            release.wait(5)
            raise InterruptedError('Cancelled running job')
        with patch.object(self.manager, 'execute', side_effect=hold):
            try:
                first = self.request('/api/jobs', self.payload(engine='clyde'))[1]
                self.assertTrue(entered.wait(3))
                second = self.request('/api/jobs', self.payload(engine='clyde'))[1]
                self.assertEqual(self.request('/api/jobs/' + second['id'] + '/cancel', {})[1]['state'], 'cancelled')
                self.assertEqual(self.request('/api/jobs/' + first['id'] + '/cancel', {})[0], 200)
            finally:
                release.set()
                self.manager.pending.join()
        for ident in (first['id'], second['id']):
            done = self.request('/api/jobs/' + ident)[1]
            self.assertEqual(done['state'], 'cancelled')
            self.assertIsNone(done['download'])

    def test_unknown_engine_and_version(self):
        self.assertEqual(self.request('/api/jobs', self.payload(engine='remote-shell'))[0], 400)
        self.assertEqual(self.request('/api/jobs', self.payload(engine='clyde', version='99'))[0], 400)

    def test_luraph_execution_disabled_but_detection_available(self):
        source = b'-- Luraph Obfuscator v15.1\nreturn 1'
        self.assertEqual(self.request('/api/detect', self.payload(source))[1]['engine'], 'luraph')
        self.assertEqual(self.request('/api/jobs', self.payload(source, engine='luraph'))[0], 403)

    def test_non_owned_job_is_not_disclosed(self):
        job = web.Job('another-owner', Path(self.temp.name) / ('a' * 32), 'private.lua', FIXTURE, {})
        self.manager.jobs[job.id] = job
        self.assertEqual(self.request('/api/jobs/' + job.id)[0], 404)
        self.assertEqual(self.request('/api/jobs/' + job.id + '/cancel', {})[0], 404)

    def test_queue_limit_is_bounded(self):
        # Fill retained records without dispatching work; the request must fail closed.
        for i in range(20):
            ident = f'{i:032x}'
            self.manager.jobs[ident] = web.Job('owner', Path(self.temp.name) / ident, 'sample.lua', b'', {})
        self.assertEqual(self.request('/api/jobs', self.payload(engine='clyde'))[0], 400)

    @unittest.skipUnless(shutil.which('node'), 'Node required for actual static engine')
    def test_clyde_job_logs_download_and_session_ownership(self):
        status, job = self.request('/api/jobs', self.payload(engine='auto'))
        self.assertEqual(status, 202)
        self.manager.pending.join()
        status, done = self.request('/api/jobs/' + job['id'])
        self.assertEqual(status, 200)
        self.assertIn(done['state'], ('ready', 'unverified'))
        self.assertEqual(done['name'], 'input.txt')
        self.assertTrue(done['download'])
        self.assertTrue(any('Static' in line for line in done['logs']))
        status, result = self.request(done['download'])
        self.assertEqual(status, 200)
        self.assertIn(b'null static fixture', result)
        stranger = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.assertEqual(self.request(done['download'], client=stranger)[0], 404)
        self.assertFalse(done['report']['behavioral_equivalence_verified'])
        self.assertEqual(self.request('/api/jobs/' + job['id'] + '?after=999999')[1]['logs'], [])

    @unittest.skipUnless(cli.find_ast(), 'Luau AST tool required')
    def test_luraph_static_analysis_never_needs_dynamic_opt_in(self):
        fixture = (Path(__file__).parent / 'fixtures/luraph15_1_synthetic.lua').read_bytes()
        status, job = self.request('/api/jobs', self.payload(fixture, engine='luraph', mode='inspect'))
        self.assertEqual(status, 202)
        self.manager.pending.join()
        done = self.request('/api/jobs/' + job['id'])[1]
        self.assertEqual(done['state'], 'partial')
        self.assertEqual(done['report']['status'], 'static_analysis_only')
        report = json.loads(self.request(done['download'])[1])
        self.assertEqual(report['curried_factory_count'], 2)
        self.assertFalse(report['source_executed'])


if __name__ == '__main__':
    unittest.main()
