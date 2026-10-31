"""Independent synthetic recipes; no original attachment or recovered Lua execution."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import cli
import clyde_refine as refine
import web_server as web


def encode_constants(strings):
    """Inverse the reviewed recipe using an artificial identity substitution."""
    pool = []
    for index, text in enumerate(strings):
        salt = index & 255
        data = [ord(x) ^ ((salt + j) & 255) for j, x in enumerate(text)]
        data = [(x + ((91 + salt + j * 235) & 255)) & 255 for j, x in enumerate(data)]
        before = data[:]
        for j in range(1, len(data)):
            data[j] ^= (before[j-1] * 123 + 124 + salt) & 255
        data = [x ^ ((30 + salt + (j // 2) * 142) & 255) if j % 2 == 0 else
                x ^ ((58 + salt + (j // 2) * 22) & 255) for j, x in enumerate(data)]
        data = [x ^ ((((j * 127 + 101) % 251) + salt) % 251) for j, x in enumerate(data)]
        pool.append(data)
    return pool


def encode_code():
    # Hand-written inverse operand packing for the synthetic twelve-op loader.
    permutation = {21: (1, (1, 2, 0)), 27: (53, (2, 1, 0)), 29: (7, (2, 1, 0)),
                   5: (33, (0, 1, 2)), 36: (25, (0, 2, 1)), 1: (47, (2, 1, 0))}
    words = []
    for pos in range(0, len(refine.EXPECTED_CODE), 4):
        mapped, *args = refine.EXPECTED_CODE[pos:pos + 4]
        opcode, indices = permutation[mapped]
        pc = pos + 1
        words.extend([opcode ^ ((115 + pc * 29 + pc * pc * 112) & 255), *(args[i] for i in indices)])
    return words


def lua_table(data):
    if isinstance(data, list):
        return '{' + ','.join(lua_table(x) for x in data) + '}'
    return str(data)


class ClydeRefinementTests(unittest.TestCase):
    def test_constant_recipe_roundtrip(self):
        constants = ['loadstring', 'game', 'HttpGet', 'https://gist.githubusercontent.com/example/synthetic/raw/main']
        self.assertEqual(refine.decode_constants(encode_constants(constants), list(range(256))), constants)

    def test_instruction_recipe_and_complete_sequence_guard(self):
        words = encode_code()
        self.assertEqual(refine.decode_code(words), refine.EXPECTED_CODE)
        words[-1] += 1
        with self.assertRaises(ValueError):
            refine.decode_code(words)

    @unittest.skipUnless(cli.find_ast(), 'Native AST tool needed for synthetic refinement')
    def test_synthetic_ast_refinement_and_hash_evidence(self):
        constants = ['loadstring', 'game', 'HttpGet', 'https://gist.githubusercontent.com/example/synthetic/raw/main']
        peeled = ('local W, X\nW=' + lua_table(encode_constants(constants)) + '\nX=' + lua_table(encode_code()) +
                  '\nlocal function inverter() local _0inv=' + lua_table(list(range(256))) + ' end\n')
        with tempfile.TemporaryDirectory() as folder:
            source, output, report = (Path(folder) / name for name in ('input.lua', 'output.lua', 'report.json'))
            source.write_text('-- synthetic test input, not a protected attachment')
            output.write_text(peeled)
            report.write_text(json.dumps({'output_sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'stats': {'mode': 'reg-vm-peeled'}}))
            with patch.object(refine, 'SAMPLE_SHA256', hashlib.sha256(source.read_bytes()).hexdigest()):
                self.assertTrue(refine.refine_if_known(source, output, report, cli.find_ast()))
            result = output.read_text()
            self.assertIn('compile(httpGet(service, "' + constants[-1] + '"))', result)
            self.assertTrue(cli.validate_result(output))
            evidence = json.loads(report.read_text())
            self.assertEqual(evidence['decoded_instructions'], 12)
            self.assertEqual(evidence['output_sha256'], hashlib.sha256(output.read_bytes()).hexdigest())
            self.assertFalse(evidence['external_payload_fetched'])

    @unittest.skipIf(sys.platform == 'win32', 'POSIX process-group regression')
    def test_timeout_kills_descendant_holding_stdout_after_parent_exit(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = web.Manager(folder, timeout=.2)
            self.addCleanup(manager.close)
            job = web.Job('owner', Path(folder), 'synthetic.lua', b'', {})
            code = ('import subprocess,sys; subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"]); '
                    'print("synthetic parent exiting", flush=True)')
            with self.assertRaises(TimeoutError):
                manager.run_command(job, [sys.executable, '-c', code])
            self.assertIsNone(job.process)

    @unittest.skipUnless(shutil.which('node'), 'Node required for static adapter')
    def test_adapter_detects_and_refuses_output_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / 'source.lua', Path(folder) / 'out.lua'
            source.write_text('-- Clyde clydeprotection\nprint("synthetic")')
            command = [shutil.which('node'), str(cli.ROOT / 'clyde_cli.js'), str(source)]
            detect = subprocess.run(command + ['--detect'], capture_output=True, text=True, timeout=10)
            self.assertEqual(detect.returncode, 0, detect.stderr)
            self.assertTrue(json.loads(detect.stdout)['isClyde'])
            output.write_text('keep this existing output')
            result = subprocess.run(command + ['-o', str(output)], capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output.read_text(), 'keep this existing output')


if __name__ == '__main__':
    unittest.main()
