"""Launcher regressions; fake engines keep tests deterministic and offline."""
import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import cli


class FakeUI:
    console = None

    def __init__(self, answers=()):
        self.answers = iter(answers)
        self.messages = []

    def say(self, text, style=None):
        self.messages.append(str(text))

    def ask(self, text, default=None):
        answer = next(self.answers)
        if answer == "q":
            raise cli.Cancelled()
        return answer or default or ""

    def confirm(self, text, default=False):
        return self.ask(text, "y" if default else "n") == "y"


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.source = self.root / "protected sample.LUA"
        self.source.write_text("-- This file was protected using Luraph Obfuscator v15.0\nreturn 42")
        self.ui = FakeUI()
        ast = patch.object(cli, "find_ast", return_value="luau-ast")
        ast.start()
        self.addCleanup(ast.stop)
        probes = patch.object(cli, "validate_native_tools", return_value=[])
        probes.start()
        self.addCleanup(probes.stop)
        desktop = patch.object(cli, "is_mobile_environment", return_value=False)
        desktop.start()
        self.addCleanup(desktop.stop)
        syntax = patch.object(cli, "validate_result", return_value=True)
        syntax.start()
        self.addCleanup(syntax.stop)

    def test_quoted_paths_and_uppercase_extension(self):
        self.assertEqual(cli.clean_path(f'"{self.source}"'), self.source)
        self.assertEqual(cli.clean_path(f"'{self.source}'"), self.source)
        self.assertEqual(cli.validate_input(self.source), self.source)

    def test_scan_only_direct_lua_files_sorted(self):
        (self.root / "a.luau").write_text("return 1")
        (self.root / "ignore.txt").write_text("lua")
        nested = self.root / "nested"
        nested.mkdir()
        (nested / "hidden.lua").write_text("return 1")
        self.assertEqual([p.name for p in cli.scan_lua(self.root)],
                         ["a.luau", self.source.name])

    def test_folder_selection_retries_invalid_number(self):
        ui = FakeUI([str(self.root), "99", str(self.root), "1"])
        self.assertEqual(cli.select_input(ui), self.source)
        self.assertTrue(any("Pick a number" in m for m in ui.messages))

    def test_file_selection(self):
        self.assertEqual(cli.select_input(FakeUI([str(self.source)])), self.source)

    def test_empty_and_non_lua_input_rejected(self):
        self.source.write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "empty"):
            cli.validate_input(self.source)
        with self.assertRaisesRegex(ValueError, "not found"):
            cli.validate_input(self.root / "missing.lua")
        txt = self.root / "test.txt"
        txt.write_text("return 1")
        with self.assertRaisesRegex(ValueError, ".lua"):
            cli.validate_input(txt)

    def test_header_detection_all_versions_and_unsupported(self):
        for version, expected in [("14.7", "14.7"), ("14.8.1", "14.8"),
                                  ("14.9", "14.9"), ("15.0", "15"), ("16.0", None),
                                  ("14.70", None)]:
            self.source.write_text(f"-- This file was protected using Luraph Obfuscator v{version}")
            self.assertEqual(cli.detect_engine(self.source)[0], expected)

    def test_headerless_v14_layout(self):
        self.source.write_text("local init = (function(...) return({}) end)()")
        self.assertEqual(cli.detect_engine(self.source)[0], "14.8")

    def test_existing_v15_detector_on_headerless_source(self):
        self.source.write_text("return setmetatable({[75]=bit32.rrotate}, {})")
        self.assertEqual(cli.detect_engine(self.source)[0], "15")

    def test_ambiguous_input_does_not_fall_back(self):
        self.source.write_text("return({})")
        self.assertIsNone(cli.detect_engine(self.source)[0])
        ui = FakeUI(["auto", "14.9"])
        self.assertEqual(cli.choose_engine(ui, self.source), "14.9")
        self.assertTrue(any("Cannot safely" in m for m in ui.messages))

    def test_output_directory_and_new_parent(self):
        self.assertEqual(cli.output_path(self.root, self.source),
                         self.root / "protected sample.deobfuscated.lua")
        expected = self.root / "new" / "out.lua"
        self.assertEqual(cli.output_path(expected, self.source), expected)

    def test_output_input_and_hardlink_protection(self):
        with self.assertRaisesRegex(ValueError, "original"):
            cli.output_path(self.source, self.source)
        alias = self.root / "alias.lua"
        os.link(self.source, alias)
        with self.assertRaisesRegex(ValueError, "original"):
            cli.output_path(alias, self.source)

    def test_output_extension_validation(self):
        with self.assertRaisesRegex(ValueError, "filename"):
            cli.output_path(self.root / "out.txt", self.source)

    def test_existing_output_requires_confirmation(self):
        dest = self.root / "out.lua"
        dest.write_text("old")
        ui = FakeUI([str(dest), "n", str(self.root / "different.lua")])
        self.assertEqual(cli.select_output(ui, self.source), self.root / "different.lua")
        self.assertEqual(dest.read_text(), "old")

    def test_engine_command_routing_and_trace_flag(self):
        for version in (v for v in cli.ENGINES[1:] if v != "clyde"):
            cmd = cli.engine_command(self.source, self.root / "out.lua", version, True)
            self.assertIn("--no-devirt", cmd)
            self.assertIn(str(self.source), cmd)
            if version == "15":
                self.assertIn("luraph_v15", cmd)
                self.assertIn("--no-pypy", cmd)
                self.assertTrue(any(x.endswith("deob.py") for x in cmd))
            else:
                self.assertIn("--engine", cmd)
                self.assertIn(version, cmd)
        with self.assertRaises(ValueError):
            cli.engine_command(self.source, self.source, "16")

    def test_streams_logs_and_exit_code(self):
        result = cli.stream_process([sys.executable, "-u", "-c",
                                     "import sys; print('lifting'); print('warn', file=sys.stderr); sys.exit(7)"],
                                    self.ui, timeout=5)
        self.assertEqual(result, 7)
        self.assertEqual(self.ui.messages, ["lifting", "warn"])

    def test_stream_timeout_stops_child(self):
        with self.assertRaises(TimeoutError):
            cli.stream_process([sys.executable, "-c", "import time; time.sleep(60)"],
                               self.ui, timeout=0.1)

    def fake_engine(self, code):
        def command(source, dest, engine, trace):
            return [sys.executable, "-c", code, str(dest)]
        return command

    def test_successful_job_atomic_save_and_parent_creation(self):
        dest = self.root / "new" / "out.lua"
        fake = self.fake_engine("from pathlib import Path; import sys; Path(sys.argv[1]).write_text('return 42')")
        with patch.object(cli, "find_runtime", return_value="luau"), \
             patch.object(cli, "engine_command", side_effect=fake):
            result = cli.run_job(self.ui, self.source, dest, "15", overwrite=True)
        self.assertEqual(result, dest)
        self.assertEqual(dest.read_text(), "return 42")
        self.assertIn("Luraph", self.source.read_text())
        self.assertEqual(list(dest.parent.glob(".null-deob-*")), [])

    def test_failure_empty_and_timeout_preserve_existing_result(self):
        dest = self.root / "out.lua"
        scenarios = [
            ("import sys; sys.exit(1)", RuntimeError, 5),
            ("pass", RuntimeError, 5),
            ("from pathlib import Path; import sys; Path(sys.argv[1]).touch()", RuntimeError, 5),
            ("import time; time.sleep(60)", TimeoutError, 0.1),
        ]
        for code, error, timeout in scenarios:
            dest.write_text("existing result")
            with patch.object(cli, "find_runtime", return_value="luau"), \
                 patch.object(cli, "engine_command", side_effect=self.fake_engine(code)):
                with self.assertRaises(error):
                    cli.run_job(self.ui, self.source, dest, "15", timeout=timeout, overwrite=True)
            self.assertEqual(dest.read_text(), "existing result")
            self.assertEqual(list(self.root.glob(".null-deob-*")), [])

    def test_missing_runtime_is_actionable(self):
        with patch.object(cli, "find_runtime", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "--setup"):
                cli.run_job(self.ui, self.source, self.root / "out.lua", "15")

    def test_missing_ast_fails_before_running_engine(self):
        with patch.object(cli, "find_runtime", return_value="luau"), \
             patch.object(cli, "find_ast", return_value=None), \
             patch.object(cli, "stream_process") as stream:
            with self.assertRaisesRegex(RuntimeError, "AST tool missing"):
                cli.run_job(self.ui, self.source, self.root / "out.lua", "15")
            stream.assert_not_called()

    def test_doctor_requires_both_native_tools(self):
        with patch.object(cli, "find_runtime", return_value="luau"), \
             patch.object(cli, "find_ast", return_value=None):
            self.assertEqual(cli.doctor(self.ui), 1)
        with patch.object(cli, "find_runtime", return_value="luau"), \
             patch.object(cli, "find_ast", return_value="luau-ast"):
            self.assertEqual(cli.doctor(self.ui), 0)

    def test_setup_builds_when_ast_is_missing(self):
        python = self.root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        python.parent.mkdir(parents=True)
        python.touch()
        with patch.object(cli, "ROOT", self.root), \
             patch.object(cli, "find_runtime", return_value="luau"), \
             patch.object(cli, "find_ast", side_effect=[None, "luau-ast"]), \
             patch.object(cli.shutil, "which", return_value="tool"), \
             patch.object(cli, "stream_process", return_value=0) as stream:
            cli.setup(self.ui)
        self.assertEqual(stream.call_count, 2)
        self.assertIn(cli.ENGINE_ROOT / "build_luau.py", stream.call_args.args[0])

    def test_setup_reuses_existing_native_tools(self):
        with patch.object(cli, "ROOT", self.root), patch.object(cli.venv, "EnvBuilder"), \
             patch.object(cli, "find_runtime", return_value="luau"), \
             patch.object(cli, "stream_process", return_value=0) as stream:
            cli.setup(self.ui)
        self.assertEqual(stream.call_count, 1)

    def test_keyboard_interrupt_preserves_existing_result(self):
        dest = self.root / "out.lua"
        dest.write_text("old")
        with patch.object(cli, "find_runtime", return_value="luau"), \
             patch.object(cli, "stream_process", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                cli.run_job(self.ui, self.source, dest, "15", overwrite=True)
        self.assertEqual(dest.read_text(), "old")
        self.assertEqual(list(self.root.glob(".null-deob-*")), [])

    def test_direct_mode_refuses_overwrite(self):
        dest = self.root / "out.lua"
        dest.write_text("old")
        with patch.object(cli, "UI", return_value=self.ui), patch.object(cli, "run_job") as job:
            self.assertEqual(cli.main([str(self.source), "-o", str(dest)]), 1)
            job.assert_not_called()

    def test_direct_mode_force_routes_job(self):
        dest = self.root / "out.lua"
        dest.write_text("old")
        with patch.object(cli, "UI", return_value=self.ui), patch.object(cli, "run_job") as job:
            self.assertEqual(cli.main([str(self.source), "-o", str(dest), "--force"]), 0)
            self.assertEqual(job.call_args.args[3], "15")

    def test_setup_uses_isolated_environment_and_can_skip_runtime(self):
        with patch.object(cli, "ROOT", self.root), patch.object(cli.venv, "EnvBuilder") as builder, \
             patch.object(cli, "stream_process", return_value=0) as stream:
            cli.setup(self.ui, skip_runtime=True)
            builder.assert_called_once_with(with_pip=True)
            builder.return_value.create.assert_called_once_with(self.root / ".venv")
            self.assertIn("pip", stream.call_args.args[0])
            self.assertTrue(any("skipped" in m for m in self.ui.messages))

    def test_setup_failed_pip_does_not_report_success(self):
        with patch.object(cli, "ROOT", self.root), patch.object(cli.venv, "EnvBuilder"), \
             patch.object(cli, "stream_process", return_value=1):
            with self.assertRaisesRegex(RuntimeError, "Dependency installation failed"):
                cli.setup(self.ui)
        self.assertFalse(any("Setup complete" in m for m in self.ui.messages))

    def test_menu_eof_and_cancel(self):
        with patch.object(cli, "UI", return_value=FakeUI(["1", "q", "0"])):
            self.assertEqual(cli.main([]), 0)
        with patch.object(cli, "UI", return_value=self.ui), patch.object(self.ui, "ask", side_effect=EOFError):
            self.assertEqual(cli.main([]), 0)

    def test_plain_ui_print_and_cancel(self):
        with patch.dict(sys.modules, {"rich.console": None}):
            ui = cli.UI()
        self.assertIsNone(ui.console)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            ui.say("plain")
        self.assertIn("plain", out.getvalue())
        with patch("builtins.input", return_value="q"):
            with self.assertRaises(cli.Cancelled):
                ui.ask("test")

    def test_invalid_flags_fail_fast(self):
        for args in (["--job-timeout", "0"], ["--job-timeout", "nan"], ["--job-timeout", "inf"], ["--skip-runtime"],
                     ["--setup", "--skip-runtime", "--build-runtime"],
                     ["--engine", "15"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                cli.main(args)
            self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
