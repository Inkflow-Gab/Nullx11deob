"""Termux/mobile configuration and shared-storage behavior (host-simulated)."""
import argparse
import errno
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import cli
from test_cli import FakeUI


class MobileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "result.lua"
        self.source.write_text("return 42\n")
        self.dest = self.root / "published.lua"

    def test_android_and_termux_detection(self):
        with patch.dict(os.environ, {"TERMUX_VERSION": "0.118.3"}):
            self.assertTrue(cli.is_mobile_environment())
        with patch.dict(os.environ, {"TERMUX_VERSION": "", "PREFIX": "/data/data/com.termux/files/usr"}):
            self.assertTrue(cli.is_mobile_environment())
        with patch.object(sys, "getandroidapilevel", return_value=35, create=True):
            self.assertTrue(cli.is_mobile_environment())

    def test_termux_venv_uses_distribution_pip_without_bootstrapping_system_pip(self):
        with patch.object(cli, "ROOT", self.root), patch.object(cli, "is_mobile_environment", return_value=True), \
             patch.object(cli.venv, "EnvBuilder") as builder, \
             patch.object(cli, "stream_process", return_value=0):
            cli.setup(FakeUI(), skip_runtime=True)
        builder.assert_called_once_with(with_pip=False, system_site_packages=True)

    def test_setup_forwards_low_memory_job_limit(self):
        with patch.object(cli, "ROOT", self.root), patch.object(cli.venv, "EnvBuilder"), \
             patch.object(cli, "find_runtime", side_effect=[None, "luau"]), \
             patch.object(cli, "find_ast", return_value="ast"), \
             patch.object(cli, "validate_native_tools", return_value=[]), \
             patch.object(cli.shutil, "which", return_value="tool"), \
             patch.object(cli, "stream_process", return_value=0) as stream:
            cli.setup(FakeUI(), jobs=1)
        self.assertEqual(stream.call_args.args[0][-2:], ["--jobs", "1"])

    def test_txt_lua_attachments_are_selected_and_named_correctly(self):
        path = self.root / "StealB.LUA.TXT"
        path.write_text("return 1")
        self.assertEqual(cli.validate_input(path), path)
        self.assertEqual(cli.script_stem(path), "StealB")
        self.assertIn(path, cli.scan_lua(self.root))
        self.assertEqual(cli.output_path(self.root, path).name, "StealB.deobfuscated.lua")

    def test_shared_storage_copy_fallback(self):
        with patch.object(cli.os, "link", side_effect=OSError(errno.EPERM, "Operation not permitted")):
            self.assertFalse(cli.publish_new_result(self.source, self.dest))
        self.assertEqual(self.dest.read_text(), "return 42\n")

    def test_shared_storage_fallback_never_replaces_existing_file(self):
        self.dest.write_text("existing")
        with patch.object(cli.os, "link", side_effect=OSError(errno.EOPNOTSUPP, "unsupported")):
            with self.assertRaisesRegex(RuntimeError, "appeared"):
                cli.publish_new_result(self.source, self.dest)
        self.assertEqual(self.dest.read_text(), "existing")

    def test_shared_storage_copy_error_removes_partial_file(self):
        with patch.object(cli.os, "link", side_effect=OSError(errno.EXDEV, "different filesystems")), \
             patch.object(cli.shutil, "copyfileobj", side_effect=OSError("out of storage")):
            with self.assertRaisesRegex(OSError, "out of storage"):
                cli.publish_new_result(self.source, self.dest)
        self.assertFalse(self.dest.exists())

    def test_shared_storage_cancellation_removes_partial_file(self):
        with patch.object(cli.os, "link", side_effect=OSError(errno.EPERM, "not supported")), \
             patch.object(cli.shutil, "copyfileobj", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                cli.publish_new_result(self.source, self.dest)
        self.assertFalse(self.dest.exists())

    def test_unexpected_filesystem_errors_are_not_hidden(self):
        with patch.object(cli.os, "link", side_effect=OSError(errno.ENOSPC, "out of space")):
            with self.assertRaises(OSError):
                cli.publish_new_result(self.source, self.dest)
        self.assertFalse(self.dest.exists())

    def test_invalid_setup_job_limit_is_rejected(self):
        with patch.object(sys, "stderr"), self.assertRaises(SystemExit) as error:
            cli.main(["--setup", "--jobs", "0"])
        self.assertEqual(error.exception.code, 2)

    def test_mobile_builder_uses_clang_defaults_without_static_gcc_flags(self):
        spec = importlib.util.spec_from_file_location("mobile_builder", cli.ENGINE_ROOT / "build_luau.py")
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        with patch.object(builder, "is_mobile_environment", return_value=True), \
             patch.object(builder, "patch"), patch.object(builder, "run") as run, \
             patch.object(builder.shutil, "which", return_value="present"):
            # No fake build products: stop after inspecting generated commands.
            with self.assertRaises(SystemExit):
                builder.build_tools(str(self.root), argparse.Namespace(portable=True, jobs=1))
        configure = run.call_args_list[0].args[0]
        self.assertFalse(any("-static" in item or "COMPILER=gcc" in item for item in configure))
        self.assertEqual(run.call_args.args[0][-2:], ["--parallel", "1"])

    def test_mobile_default_is_one_compiler_job(self):
        spec = importlib.util.spec_from_file_location("mobile_builder", cli.ENGINE_ROOT / "build_luau.py")
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        with patch.object(builder, "is_mobile_environment", return_value=True), \
             patch.object(builder, "build_tools") as build, \
             patch.object(sys, "argv", ["build_luau.py", "--src", str(self.root)]):
            builder.main()
        self.assertEqual(build.call_args.args[1].jobs, 1)


if __name__ == "__main__":
    unittest.main()
