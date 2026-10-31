"""PostMessage boundary tests without a browser package or network access."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('node'), 'Node needed for the browser connector tests')
class RuntimeLinkTests(unittest.TestCase):
    def run_node(self, code):
        result = subprocess.run([shutil.which('node'), '-e', code, str(ROOT / 'web/runtime-link.js')], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_worker_url_rejects_credentials_non_https_and_editor_links(self):
        self.run_node(r'''
const assert = require('assert');
global.window = {}; global.location = {origin: 'https://inkflow-gab.github.io'};
require(process.argv[1]); const validate = window.nullRuntimeLink.validateURL;
for (const value of ['javascript:alert(1)', 'http://worker.test/', 'https://user:secret@worker.test/', 'https://worker.test/?key=secret', 'https://worker.test/#key', 'https://worker.test/api/jobs', 'https://inkflow-gab.github.io/', 'https://editor.github.dev/']) assert.throws(() => validate(value));
assert.equal(validate('https://workspace-8081.app.github.dev/').origin, 'https://workspace-8081.app.github.dev');
''')

    def test_receiver_requires_exact_origin_window_nonce_and_never_runs_job(self):
        self.run_node(r'''
const assert = require('assert');
(async () => {
const token = 'a'.repeat(64), posted = []; let listener, imports = 0;
const opener = {postMessage: (data, origin) => posted.push({data, origin})};
global.window = {opener, addEventListener: (name, cb) => listener = cb, removeEventListener: () => {}};
global.location = {hash: '#nullSource=https%3A%2F%2Finkflow-gab.github.io&nullToken='+token, pathname: '/', search: ''};
global.history = {replaceState: () => {}}; global.setTimeout = () => 1; global.clearTimeout = () => {};
require(process.argv[1]);
window.nullRuntimeLink.receive(async payload => { imports++; assert.equal(payload.filename, 'test.lua'); }, () => {});
assert.equal(posted[0].data.type, 'null-runner-ready');
const payload = {filename:'test.lua',data:Buffer.from('print("test fixture")').toString('base64'),settings:{engine:'luraph',version:'15.0',mode:'deobfuscate'}};
const message = {source:opener,origin:'https://inkflow-gab.github.io',data:{type:'null-runner-import',token,payload}};
await listener({...message, origin:'https://evil.invalid'});
await listener({...message, source:{}});
await listener({...message, data:{...message.data,token:'wrong'}});
assert.equal(imports, 0);
await listener(message); await listener(message);
assert.equal(imports, 1); assert.equal(window.opener, null);
assert.equal(posted[1].data.type, 'null-runner-imported');
for (const event of posted) { assert.deepEqual(Object.keys(event.data).sort(), ['token','type']); assert.equal(event.origin,'https://inkflow-gab.github.io'); }
})().catch(error => {console.error(error);process.exitCode=1;});
''')

    def test_untrusted_source_cannot_trigger_readiness(self):
        self.run_node(r'''
const assert = require('assert'); let posted = 0;
global.window = {opener: {postMessage: () => posted++}};
global.location = {hash:'#nullSource=https%3A%2F%2Fevil.invalid&nullToken='+'a'.repeat(64)};
require(process.argv[1]);
window.nullRuntimeLink.receive(() => {throw Error('unexpected import')}, () => {});
assert.equal(posted, 0);
''')


if __name__ == '__main__':
    unittest.main()
