"""One-command starter behavior without downloading dependencies in tests."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import cli
import start
from test_cli import FakeUI


class StarterTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.python = self.root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        self.python.parent.mkdir(parents=True)
        self.python.touch()
        self.ui = FakeUI()
        for name, replacement in (("ROOT", self.root),):
            mock = patch.object(start, name, replacement)
            mock.start()
            self.addCleanup(mock.stop)
        ui = patch.object(cli, "UI", return_value=self.ui)
        ui.start()
        self.addCleanup(ui.stop)

    def test_ready_environment_replaces_starter_without_setup(self):
        with patch.object(cli, "find_runtime", return_value="luau"), \
             patch.object(cli, "find_ast", return_value="ast"), \
             patch.object(cli, "validate_native_tools", return_value=[]), \
             patch.object(cli, "stream_process") as setup, patch.object(os, "execv") as execute:
            self.assertEqual(start.main([]), 0)
        setup.assert_not_called()
        self.assertEqual(execute.call_args.args[0], str(self.python))
        self.assertEqual(execute.call_args.args[1][-1], str(self.root / "cli.py"))

    def test_noninteractive_missing_setup_has_actionable_error(self):
        self.python.unlink()
        with patch.object(sys.stdin, "isatty", return_value=False), patch.object(os, "execv") as execute:
            self.assertEqual(start.main([]), 2)
        execute.assert_not_called()
        self.assertTrue(any("--setup" in message for message in self.ui.messages))

    def test_yes_bootstraps_and_preserves_job_arguments(self):
        with patch.object(cli, "find_runtime", side_effect=[None, "luau"]), \
             patch.object(cli, "find_ast", return_value="ast"), \
             patch.object(cli, "stream_process", return_value=0) as setup, \
             patch.object(os, "execv") as execute:
            self.assertEqual(start.main(["--yes", "protected.lua", "-o", "clean.lua", "--jobs", "1"]), 0)
        self.assertIn("--setup", setup.call_args.args[0])
        self.assertEqual(setup.call_args.args[0][-2:], ["--jobs", "1"])
        arguments = execute.call_args.args[1]
        self.assertIn("protected.lua", arguments)
        self.assertNotIn("--yes", arguments)

    def test_setup_failure_is_not_hidden(self):
        with patch.object(cli, "find_runtime", return_value=None), \
             patch.object(cli, "stream_process", return_value=7), patch.object(os, "execv") as execute:
            self.assertEqual(start.main(["--yes"]), 7)
        execute.assert_not_called()

    def test_setup_returning_without_tools_is_rejected(self):
        with patch.object(cli, "find_runtime", return_value=None), \
             patch.object(cli, "stream_process", return_value=0), patch.object(os, "execv") as execute:
            self.assertEqual(start.main(["--yes"]), 1)
        execute.assert_not_called()

    def test_explicit_actions_never_download_implicitly(self):
        self.python.unlink()
        for argument in ("--doctor", "--help", "--setup"):
            with patch.object(cli, "stream_process") as setup, patch.object(os, "execv") as execute:
                self.assertEqual(start.main([argument]), 0)
                self.assertEqual(execute.call_args.args[0], sys.executable)
            setup.assert_not_called()

    def test_user_can_decline_initial_setup(self):
        self.ui.answers = iter(["n"])
        with patch.object(cli, "find_runtime", return_value=None), \
             patch.object(sys.stdin, "isatty", return_value=True), \
             patch.object(cli, "stream_process") as setup:
            self.assertEqual(start.main([]), 0)
        setup.assert_not_called()

    def test_keyboard_interrupt_cancels_bootstrap(self):
        with patch.object(cli, "find_runtime", return_value=None), \
             patch.object(cli, "stream_process", side_effect=KeyboardInterrupt):
            self.assertEqual(start.main(["--yes"]), 130)

    def test_exec_failure_is_reported_without_traceback(self):
        with patch.object(os, "execv", side_effect=OSError("interpreter broken")):
            self.assertEqual(start.main(["--doctor"]), 1)

    def test_setup_options_are_forwarded_without_shell_parsing(self):
        command = start.setup_command(["--jobs=1", "--no-color", "file; echo ignored.lua"])
        self.assertIn("--jobs=1", command)
        self.assertIn("--no-color", command)
        self.assertNotIn("file; echo ignored.lua", command)

    def test_15_1_banner_is_explicitly_experimental(self):
        source = self.root / "v151.lua"
        source.write_text("-- This file was protected using Luraph Obfuscator v15.1\nreturn 1")
        engine, reason = cli.detect_engine(source)
        self.assertEqual(engine, "15")
        self.assertIn("experimental", reason)
        self.assertIn("not verified", reason)

    def test_setup_discovers_venv_native_tools_without_activation(self):
        def available(tool, path=None):
            if tool == "cmake":
                return str(self.python.parent / "cmake") if str(self.python.parent) in (path or "") else None
            return "tool"

        with patch.object(cli, "ROOT", self.root), \
             patch.object(cli, "find_runtime", side_effect=[None, "luau"]), \
             patch.object(cli, "find_ast", return_value="ast"), \
             patch.object(cli, "validate_native_tools", return_value=[]), \
             patch.object(cli.shutil, "which", side_effect=available), \
             patch.object(cli, "stream_process", return_value=0) as build:
            cli.setup(self.ui, jobs=1)
        self.assertEqual(build.call_args.kwargs["extra_env"]["PATH"].split(os.pathsep)[0], str(self.python.parent))

    def test_real_starter_can_display_help_and_open_menu(self):
        cases = [(["--help"], None)]
        real_python = cli.ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if real_python.is_file() and cli.find_runtime() and cli.find_ast():
            cases.append((["--no-color"], "0\n"))
        for arguments, text in cases:
            result = subprocess.run([sys.executable, "-B", str(cli.ROOT / "start.py"), *arguments],
                                    input=text, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
