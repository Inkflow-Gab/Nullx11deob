"""Failure, concurrency, process cleanup, and native-tool validation regressions."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import cli
from test_cli import FakeUI


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "source.lua"
        self.source.write_text("return 42")
        self.dest = self.root / "result.lua"
        self.ui = FakeUI()

    def run_fake_job(self, action, *, overwrite=False):
        def fake_process(command, ui, **kwargs):
            Path(command[0]).write_text("return 42")
            action()
            return 0
        with patch.object(cli, "find_runtime", return_value="runtime"), \
             patch.object(cli, "find_ast", return_value="ast"), \
             patch.object(cli, "validate_native_tools", return_value=[]), \
             patch.object(cli, "validate_result", return_value=True), \
             patch.object(cli, "engine_command", side_effect=lambda source, dest, *args: [str(dest)]), \
             patch.object(cli, "stream_process", side_effect=fake_process):
            return cli.run_job(self.ui, self.source, self.dest, "15", overwrite=overwrite)

    def test_result_appears_during_job_is_not_overwritten(self):
        with self.assertRaisesRegex(RuntimeError, "appeared"):
            self.run_fake_job(lambda: self.dest.write_text("other user's result"))
        self.assertEqual(self.dest.read_text(), "other user's result")
        self.assertEqual(list(self.root.glob(".null-deob-*")), [])

    def test_existing_result_changed_during_job_is_not_overwritten(self):
        self.dest.write_text("old")
        with self.assertRaisesRegex(RuntimeError, "changed"):
            self.run_fake_job(lambda: self.dest.write_text("new external result"), overwrite=True)
        self.assertEqual(self.dest.read_text(), "new external result")

    def test_existing_result_removed_during_job_is_not_recreated(self):
        self.dest.write_text("old")
        with self.assertRaisesRegex(RuntimeError, "changed"):
            self.run_fake_job(self.dest.unlink, overwrite=True)
        self.assertFalse(self.dest.exists())

    def test_output_alias_to_input_created_during_job_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "original"):
            self.run_fake_job(lambda: os.link(self.source, self.dest))
        self.assertEqual(self.source.read_text(), "return 42")

    def test_unchanged_existing_output_can_be_replaced_with_consent(self):
        self.dest.write_text("old")
        self.run_fake_job(lambda: None, overwrite=True)
        self.assertEqual(self.dest.read_text(), "return 42")

    def test_run_job_itself_requires_overwrite_consent(self):
        self.dest.write_text("old")
        with self.assertRaisesRegex(ValueError, "confirmation"):
            cli.run_job(self.ui, self.source, self.dest, "15")
        self.assertEqual(self.dest.read_text(), "old")

    def test_invalid_yes_no_is_reprompted(self):
        with patch("builtins.input", side_effect=["maybe", "YES"]), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(cli.UI().confirm("Continue?"))

    def test_powershell_drag_and_drop_path(self):
        self.assertEqual(cli.clean_path(f"& '{self.source}'"), self.source)

    def test_nul_in_path_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "NUL"):
            cli.clean_path("invalid\x00.lua")

    def test_manual_engine_selection_survives_detector_timeout(self):
        ui = FakeUI(["14.8"])
        with patch.object(cli, "detect_engine", side_effect=subprocess.TimeoutExpired("detector", 30)):
            self.assertEqual(cli.choose_engine(ui, self.source), "14.8")
        self.assertTrue(any("manual version" in message for message in ui.messages))

    def test_invalid_detector_output_never_selects_engine(self):
        for confidence in ("nonsense", "nan", "inf", "2"):
            result = subprocess.CompletedProcess([], 0, f"luraph_v15\t{confidence}\tLuraph v15", "")
            with patch.object(cli.subprocess, "run", return_value=result):
                self.assertIsNone(cli.detect_engine(self.source)[0])

    def test_failed_detector_is_reported(self):
        result = subprocess.CompletedProcess([], 1, "", "missing engine")
        with patch.object(cli.subprocess, "run", return_value=result):
            version, detail = cli.detect_engine(self.source)
        self.assertIsNone(version)
        self.assertIn("detector failed", detail)

    def test_ascii_redirected_menu_works_with_and_without_site_packages(self):
        for flags in ([], ["-S"]):
            env = dict(os.environ, PYTHONIOENCODING="ascii")
            result = subprocess.run([sys.executable, *flags, "-B", str(cli.ROOT / "cli.py"), "--no-color"],
                                    input="0\n", capture_output=True, text=True, encoding="ascii", env=env, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_stream_drains_final_logs(self):
        code = "import sys; [print(i) for i in range(200)]; sys.stdout.write('last without newline')"
        self.assertEqual(cli.stream_process([sys.executable, "-c", code], self.ui, timeout=5), 0)
        self.assertEqual(len(self.ui.messages), 201)
        self.assertEqual(self.ui.messages[-1], "last without newline")

    def test_log_output_does_not_emit_terminal_control_characters(self):
        code = "print('before\\x1b[31mafter\\x07')"
        cli.stream_process([sys.executable, "-c", code], self.ui, timeout=5)
        self.assertNotIn("\x1b", self.ui.messages[0])
        self.assertNotIn("\x07", self.ui.messages[0])

    @unittest.skipIf(os.name == "nt", "POSIX process-group assertion")
    def test_timeout_kills_child_that_ignores_sigterm(self):
        pidfile = self.root / "pid"
        child = ("import os,signal,time; from pathlib import Path; "
                 "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                 f"Path({str(pidfile)!r}).write_text(str(os.getpid())); time.sleep(60)")
        parent = f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',{child!r}]); time.sleep(60)"
        with self.assertRaises(TimeoutError):
            cli.stream_process([sys.executable, "-c", parent], self.ui, timeout=0.8)
        self.assertTrue(pidfile.is_file(), "child must start before cancellation is tested")
        pid = int(pidfile.read_text())
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                stat = Path(f"/proc/{pid}/stat")
                if sys.platform.startswith("linux") and stat.exists() and stat.read_text().split()[2] == "Z":
                    return  # Dead, awaiting init's reaper, not running.
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.02)
        self.fail("cancelled process left a running child behind")

    def test_keyboard_interrupt_cleans_up_real_subprocess(self):
        process = None
        real_popen = subprocess.Popen

        def capture(*args, **kwargs):
            nonlocal process
            process = real_popen(*args, **kwargs)
            return process

        def interrupt(text, style=None):
            if text == "ready":
                raise KeyboardInterrupt

        self.ui.say = interrupt
        with patch.object(cli.subprocess, "Popen", side_effect=capture):
            with self.assertRaises(KeyboardInterrupt):
                cli.stream_process([sys.executable, "-u", "-c", "import time; print('ready'); time.sleep(60)"],
                                   self.ui, timeout=5)
        self.assertIsNotNone(process.poll())
        self.assertTrue(process.stdout.closed)


class NativeProbeTests(unittest.TestCase):
    def validate(self, runtime_result, ast_result):
        with patch.object(cli, "find_runtime", return_value="runtime"), \
             patch.object(cli, "find_ast", return_value="ast"), \
             patch.object(cli.subprocess, "run", side_effect=[runtime_result, ast_result]):
            return cli.validate_native_tools()

    @staticmethod
    def result(stdout, code=0):
        return subprocess.CompletedProcess([], code, stdout, b"test stderr")

    def test_native_probe_accepts_compatible_tools(self):
        self.assertEqual(self.validate(self.result(b"null-native-tool-check\n"),
                                       self.result(b'{"root":{"type":"AstStatBlock"}}')), [])

    def test_native_probe_rejects_wrong_runtime_output(self):
        errors = self.validate(self.result(b"not the runtime"), self.result(b'{"root":{"type":"AstStatBlock"}}'))
        self.assertIn("runtime did not execute", errors[0])

    def test_native_probe_rejects_bad_ast_formats(self):
        for payload in (b"not json", b"[]", b'{"root":null}', b'{"root":{"type":"wrong"}}'):
            with self.subTest(payload=payload):
                errors = self.validate(self.result(b"null-native-tool-check"), self.result(payload))
                self.assertEqual(len(errors), 1)
                self.assertIn("AST unusable", errors[0])

    def test_native_probe_catches_bad_architecture_and_timeouts(self):
        errors = self.validate(OSError("Exec format error"), subprocess.TimeoutExpired("ast", 10))
        self.assertEqual(len(errors), 2)
        self.assertIn("Exec format error", errors[0])
        self.assertIn("timed out", errors[1])

    def test_native_probe_rejects_nonzero_exit(self):
        errors = self.validate(self.result(b"", 1), self.result(b"", 2))
        self.assertEqual(len(errors), 2)


class ResultValidationTests(unittest.TestCase):
    def test_valid_ast_with_statements(self):
        result = subprocess.CompletedProcess([], 0, b'{"root":{"type":"AstStatBlock","body":[{"type":"AstStatReturn"}]}}', b"")
        with patch.object(cli, "find_ast", return_value="ast"), patch.object(cli.subprocess, "run", return_value=result):
            self.assertTrue(cli.validate_result(Path("result.lua")))

    def test_comments_only_result_is_detected(self):
        result = subprocess.CompletedProcess([], 0, b'{"root":{"type":"AstStatBlock","body":[]}}', b"")
        with patch.object(cli, "find_ast", return_value="ast"), patch.object(cli.subprocess, "run", return_value=result):
            self.assertFalse(cli.validate_result(Path("result.lua")))

    def test_parse_errors_rejected_even_with_zero_exit_code(self):
        result = subprocess.CompletedProcess([], 0, b'{"root":{"type":"AstStatBlock","body":[]}}', b"Parse errors were encountered")
        with patch.object(cli, "find_ast", return_value="ast"), patch.object(cli.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(RuntimeError, "syntax validation"):
                cli.validate_result(Path("result.lua"))

    def test_error_nodes_and_bad_formats_rejected(self):
        payloads = [b"not JSON", b"[]", b'{"root":{"type":"AstStatBlock"}}',
                    b'{"root":{"type":"AstStatBlock","body":[{"type":"AstStatError"}]}}']
        for payload in payloads:
            result = subprocess.CompletedProcess([], 0, payload, b"")
            with patch.object(cli, "find_ast", return_value="ast"), patch.object(cli.subprocess, "run", return_value=result):
                with self.assertRaisesRegex(RuntimeError, "syntax validation"):
                    cli.validate_result(Path("result.lua"))

    def test_parser_timeout_does_not_escape_as_traceback(self):
        with patch.object(cli, "find_ast", return_value="ast"), \
             patch.object(cli.subprocess, "run", side_effect=subprocess.TimeoutExpired("ast", 30)):
            with self.assertRaisesRegex(RuntimeError, "syntax validation"):
                cli.validate_result(Path("result.lua"))


class NativeBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("native_builder", cli.ENGINE_ROOT / "build_luau.py")
        cls.builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.builder)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        path = self.root / "VM" / "src" / "lveclib.cpp"
        path.parent.mkdir(parents=True)
        path.write_text(self.builder.FREEZE)
        self.args = type("Args", (), {"portable": True, "jobs": 1})()
        for name in ("luau", "luau-ast"):
            exe = name + (".exe" if os.name == "nt" else "")
            product = self.root / "build-deobf" / exe
            product.parent.mkdir(exist_ok=True)
            product.write_bytes(b"fake binary")

    def test_build_targets_both_tools_and_honors_job_limit(self):
        with patch.object(self.builder, "run") as run, \
             patch.object(self.builder, "BIN", str(self.root / "bin")):
            self.builder.build_tools(str(self.root), self.args)
        command = run.call_args.args[0]
        self.assertIn("Luau.Repl.CLI", command)
        self.assertIn("Luau.Ast.CLI", command)
        self.assertEqual(command[-2:], ["--parallel", "1"])
        self.assertEqual(len(list((self.root / "bin").iterdir())), 2)

    def test_macos_does_not_force_linux_static_gcc_flags(self):
        with patch.object(self.builder.sys, "platform", "darwin"), \
             patch.object(self.builder.shutil, "which", return_value="available"), \
             patch.object(self.builder, "run") as run, \
             patch.object(self.builder, "BIN", str(self.root / "bin")):
            self.builder.build_tools(str(self.root), self.args)
        configure = run.call_args_list[0].args[0]
        self.assertFalse(any("-static " in x or "COMPILER=gcc" in x for x in configure))

    def test_missing_ast_does_not_replace_existing_runtime(self):
        exe = "luau-ast.exe" if os.name == "nt" else "luau-ast"
        (self.root / "build-deobf" / exe).unlink()
        target = self.root / "bin"
        target.mkdir()
        runtime = target / ("luau.exe" if os.name == "nt" else "luau")
        runtime.write_text("old working runtime")
        with patch.object(self.builder, "run"), patch.object(self.builder, "BIN", str(target)):
            with self.assertRaises(SystemExit):
                self.builder.build_tools(str(self.root), self.args)
        self.assertEqual(runtime.read_text(), "old working runtime")

    def test_failed_clone_removes_temporary_checkout(self):
        paths = []

        def fail(command):
            paths.append(Path(command[-1]).parent)
            raise subprocess.CalledProcessError(1, command)

        with patch.object(sys, "argv", ["build_luau.py"]), patch.object(self.builder, "run", side_effect=fail):
            with self.assertRaises(subprocess.CalledProcessError):
                self.builder.main()
        self.assertFalse(paths[0].exists())

    def test_patch_is_idempotent(self):
        self.builder.patch(str(self.root))
        self.builder.patch(str(self.root))
        text = (self.root / "VM" / "src" / "lveclib.cpp").read_text()
        self.assertEqual(text.count(self.builder.PATCHED), 1)


if __name__ == "__main__":
    unittest.main()
