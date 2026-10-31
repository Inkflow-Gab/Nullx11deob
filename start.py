#!/usr/bin/env python3
"""One entry point: prepare dependencies on first use, then open null's CLI.

    python start.py              guided first setup, then the menu
    python start.py --setup      explicit setup/repair only
    python start.py --yes        permit first setup without prompting

All other arguments are forwarded to cli.py. No shell command construction.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

import cli

ROOT = Path(__file__).resolve().parent


def environment_python():
    return ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def setup_command(arguments):
    command = [sys.executable, "-B", str(ROOT / "cli.py"), "--setup"]
    for i, argument in enumerate(arguments):
        if argument == "--jobs" and i + 1 < len(arguments):
            command.extend(["--jobs", arguments[i + 1]])
        elif argument.startswith("--jobs="):
            command.append(argument)
        elif argument == "--no-color":
            command.append(argument)
    return command


def main(argv=None):
    cli.configure_output_streams()
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--yes", action="store_true")
    starter, arguments = parser.parse_known_args(sys.argv[1:] if argv is None else argv)
    ui = cli.UI("--no-color" in arguments)
    if "--help" in arguments or "-h" in arguments:
        ui.say("Starter: --yes permits first-time setup without prompting; all CLI options below are supported.\n")
    python = environment_python()
    # Help/check/setup must never trigger an implicit download.
    explicit_action = any(flag in arguments for flag in ("--setup", "--doctor", "--help", "-h"))
    try:
        if not explicit_action:
            ready = python.is_file() and cli.find_runtime() and cli.find_ast()
            if ready:
                ready = not cli.validate_native_tools()
            if not ready:
                ui.say("First setup / repair is needed. This creates .venv, installs Rich, and prepares Luau.", "cyan")
                ui.say("Internet is required. Native builds need your OS compiler/CMake packages; see read.md.")
                if not starter.yes:
                    if not sys.stdin.isatty():
                        ui.say("Run python start.py --setup first, or pass --yes to permit setup explicitly.", "yellow")
                        return 2
                    if not ui.confirm("Prepare the local environment now?", default=True):
                        return 0
                result = cli.stream_process(setup_command(arguments), ui, cwd=ROOT, timeout=2200)
                if result:
                    ui.say("Setup did not complete. Fix the reported issue, then rerun python start.py.", "red")
                    return result
                if not python.is_file() or not cli.find_runtime() or not cli.find_ast():
                    ui.say("Setup returned without the required local environment/tools. Run --doctor.", "red")
                    return 1
        executable = str(python) if python.is_file() else sys.executable
        sys.stdout.flush()
        sys.stderr.flush()
        # Replacing the starter avoids a second waiting launcher and makes
        # cancellation/exit codes belong to the actual CLI process.
        os.execv(executable, [executable, "-B", str(ROOT / "cli.py"), *arguments])
        return 0  # only reached by mocks in unit tests
    except (KeyboardInterrupt, EOFError, cli.Cancelled):
        ui.say("\nCancelled.", "yellow")
        return 130
    except (OSError, ValueError, RuntimeError) as exc:
        ui.say(f"Cannot start: {exc}", "red")
        return 1


if __name__ == "__main__":
    if sys.version_info < (3, 10):
        sys.exit("Python 3.10 or newer is required.")
    sys.exit(main())
