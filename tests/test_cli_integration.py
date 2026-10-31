"""Optional real-runtime smoke tests; run after --setup.

These exercise each frontend and the runtime/AST tools on a tiny synthetic
trace fixture, not full devirtualization of a protected VM.
"""
from pathlib import Path
import subprocess
import os
import sys
import tempfile
import unittest

import cli


@unittest.skipUnless(cli.find_runtime() and cli.find_ast(), "run cli.py --setup for native smoke tests")
class NativeSmokeTests(unittest.TestCase):
    def test_frontends_trace_and_save_with_real_luau(self):
        with tempfile.TemporaryDirectory(prefix="null-native-smoke-") as folder:
            root = Path(folder).resolve()
            for version in ("14.7", "14.8", "14.9", "15.0"):
                with self.subTest(version=version):
                    source = root / ("sample " + version + ".lua")
                    dest = root / ("result " + version + ".lua")
                    text = (f"-- This file was protected using Luraph Obfuscator v{version}\n"
                            'print("null CLI native smoke")\n')
                    source.write_text(text)
                    result = subprocess.run([sys.executable, str(cli.ROOT / "cli.py"), str(source),
                                             "--trace-only", "-o", str(dest), "--job-timeout", "30"],
                                            capture_output=True, text=True, timeout=45)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertTrue(dest.is_file())
                    self.assertIn("null CLI native smoke", dest.read_text())
                    self.assertEqual(source.read_text(), text)

    def test_menu_from_unrelated_directory_with_unicode_paths(self):
        with tempfile.TemporaryDirectory(prefix="null-menu-") as folder:
            root = Path(folder).resolve()
            source = root / "input path é.lua"
            source.write_text('-- This file was protected using Luraph Obfuscator v15.0\nprint("menu smoke")\n')
            destination = root / "output path é.lua"
            answers = f'1\n"{source}"\nauto\n"{destination}"\ny\ny\n0\n'
            result = subprocess.run([sys.executable, "-B", str(cli.ROOT / "cli.py"), "--no-color"],
                                    input=answers, capture_output=True, text=True, encoding="utf-8",
                                    cwd=root, timeout=45, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(destination.exists(), result.stdout)
            self.assertIn("menu smoke", destination.read_text())
            self.assertNotIn("\x1b", result.stdout)

    def test_pretty_printer_preserves_parenthesized_statement_boundaries(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            source = root / "before.lua"
            # A grouped assignment is first in one function; an IIFE follows
            # a call in another block. Neither may acquire ambiguous syntax.
            source.write_text('local unused = function(...) (...)[...] = nil end\n'
                              'print("before"); (function() print("after") end)()\n')
            destination = root / "after.lua"
            formatted = subprocess.run([sys.executable, "-B", str(cli.ENGINE_ROOT / "luauast.py"), str(source)],
                                       capture_output=True, timeout=15)
            self.assertEqual(formatted.returncode, 0, formatted.stderr)
            destination.write_bytes(formatted.stdout)
            self.assertTrue(cli.validate_result(destination))
            original = subprocess.run([cli.find_runtime(), str(source)], capture_output=True, timeout=10)
            recovered = subprocess.run([cli.find_runtime(), str(destination)], capture_output=True, timeout=10)
            self.assertEqual(recovered.returncode, 0, recovered.stderr)
            self.assertEqual(original.stdout, recovered.stdout)
            self.assertEqual(recovered.stdout.strip(), b"before\nafter")

    def test_empty_proto_capture_falls_back_to_useful_trace(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            source = root / "plain.lua"
            source.write_text('-- This file was protected using Luraph Obfuscator v15.0\nprint("fallback trace")\n')
            destination = root / "result.lua"
            result = subprocess.run([sys.executable, "-B", str(cli.ROOT / "cli.py"), str(source),
                                     "-o", str(destination), "--job-timeout", "30"],
                                    capture_output=True, text=True, timeout=45)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("fallback trace", destination.read_text())
            self.assertTrue(cli.validate_result(destination))

    def test_invalid_recovered_syntax_is_rejected_by_real_ast(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "bad.lua"
            source.write_text("local = ???")
            with self.assertRaisesRegex(RuntimeError, "syntax validation"):
                cli.validate_result(source)
            source.write_text("-- no recovered statements\n")
            self.assertFalse(cli.validate_result(source))

    @unittest.skipUnless((cli.ROOT / "SON.LUA").is_file(), "bundled protected fixture missing")
    def test_bundled_v15_sample_full_recovery_and_syntax(self):
        with tempfile.TemporaryDirectory(prefix="null-protected-") as folder:
            root = Path(folder).resolve()
            source = root / "protected.lua"
            original = (cli.ROOT / "SON.LUA").read_bytes()
            source.write_bytes(original)
            destination = root / "recovered.lua"
            result = subprocess.run([sys.executable, "-B", str(cli.ROOT / "cli.py"), str(source),
                                     "-o", str(destination), "--job-timeout", "60"],
                                    capture_output=True, text=True, cwd=root, timeout=75)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(cli.validate_result(destination))
            self.assertIn('print("hello")', destination.read_text())
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(list(root.glob(".null-deob-*")), [])


if __name__ == "__main__":
    unittest.main()
