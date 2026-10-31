"""GitHub Pages is a self-contained static site, not an unauthenticated backend."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

from tools import build_pages

ROOT = Path(__file__).resolve().parents[1]


class PagesTests(unittest.TestCase):
    def test_committed_pages_assets_are_current(self):
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'tools/build_pages.py'), '--check'], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_pages_root_setting_has_a_launcher(self):
        source = (ROOT / 'index.html').read_text()
        self.assertIn('content="0;url=./docs/"', source)
        self.assertIn('href="./docs/"', source)
        self.assertTrue((ROOT / '.nojekyll').exists())

    def test_static_build_includes_private_runtime_connector(self):
        self.assertEqual((ROOT / 'docs/runtime-link.js').read_text(), (ROOT / 'web/runtime-link.js').read_text())
        self.assertIn('runtime-link.js', (ROOT / 'docs/index.html').read_text())

    def test_dedicated_worker_template_uses_explicit_private_startup(self):
        worker = json.loads((ROOT / '.devcontainer/worker/devcontainer.json').read_text())
        regular = json.loads((ROOT / '.devcontainer/devcontainer.json').read_text())
        self.assertEqual(worker['postCreateCommand'], regular['postCreateCommand'])
        self.assertEqual(worker['postStartCommand'], 'NULL_WEB_DYNAMIC=1 python3 .devcontainer/launch.py')
        self.assertNotIn('NULL_WEB_DYNAMIC=1', regular['postStartCommand'])
        self.assertEqual(worker['forwardPorts'], [8080])
        self.assertNotIn('repositories', worker.get('customizations', {}).get('codespaces', {}))
        self.assertIn('devcontainer_path=.devcontainer%2Fworker%2Fdevcontainer.json', (ROOT / 'docs/index.html').read_text())

    def test_browser_bundle_contains_closed_relative_module_graph(self):
        source = build_pages.bundle()
        self.assertIn('const process = {env: Object.freeze({})}', source)
        self.assertIn('web/clyde-worker.js', source)
        self.assertIn('vendor/clyde/clyde_static_deob.js', source)
        self.assertNotIn('eval(', source)
        self.assertNotIn('new Function(', source)

    def test_static_site_loads_browser_adapter_before_ui(self):
        html = (ROOT / 'docs/index.html').read_text(encoding='utf-8')
        self.assertLess(html.index('browser-api.js'), html.index('app.js'))
        self.assertIn('Files stay in your browser', html)
        self.assertIn('Content-Security-Policy', html)
        self.assertTrue((ROOT / 'docs/.nojekyll').exists())
        self.assertEqual((ROOT / 'docs/Clyde-LICENSE.txt').read_text(), (ROOT / 'vendor/clyde/LICENSE').read_text())

    def test_reference_is_same_reviewed_loader_not_remote_payload(self):
        self.assertEqual((ROOT / 'docs/recovered/RoMidiYessirAp.deobfuscated.lua').read_bytes(), (ROOT / 'output/recovered/RoMidiYessirAp.deobfuscated.lua').read_bytes())
        report = json.loads((ROOT / 'docs/recovered/RoMidiYessirAp.analysis.json').read_text())
        self.assertFalse(report['external_payload_fetched'])
        self.assertFalse(report['external_payload_included'])

    @unittest.skipUnless(shutil.which('node'), 'Node needed to test compiled browser worker')
    def test_real_browser_bundle_recovers_synthetic_input_without_execution(self):
        script = r'''
const {webcrypto} = require('crypto'); global.crypto = webcrypto;
global.self = {location: {href: 'https://example.invalid/Nullx11deob/clyde-worker.js'}, postMessage(message) {
  if (message.type === 'result' || message.type === 'error') console.log(JSON.stringify(message));
}};
require(process.argv[1]);
self.onmessage({data: {bytes: new TextEncoder().encode('-- Clyde clydeprotection\nprint("synthetic Pages fixture")')}});
'''
        result = subprocess.run([shutil.which('node'), '-e', script, str(ROOT / 'docs/clyde-worker.js')], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        response = json.loads(result.stdout)
        self.assertEqual(response['type'], 'result', response)
        self.assertIn('synthetic Pages fixture', response['output'])
        self.assertFalse(response['report']['uploaded'])
        self.assertFalse(response['report']['source_executed'])
        self.assertIsNone(response['report']['syntax_valid'])


if __name__ == '__main__':
    unittest.main()
