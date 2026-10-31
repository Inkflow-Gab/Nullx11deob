#!/usr/bin/env python3
"""null's guided Clyde + Luraph launcher. Python 3.10+; Rich is optional until setup."""
from __future__ import annotations

import argparse
import errno
import importlib.util
import json
import math
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import venv

ROOT = Path(__file__).resolve().parent
ENGINE_ROOT = ROOT / "Deobfuscator" / "deobf"
ENGINES = ("auto", "14.7", "14.8", "14.9", "15", "clyde")
BANNER = re.compile(r"Luraph Obfuscator v(\d+(?:\.\d+)*)", re.I)


class UI:
    def __init__(self, no_color=False):
        self.console = None
        try:
            from rich.console import Console
            self.console = Console(no_color=no_color or "NO_COLOR" in os.environ,
                                   highlight=False, markup=False)
        except ImportError:
            pass

    def say(self, text, style=None):
        if self.console:
            self.console.print(str(text), style=style)
        else:
            print(text, flush=True)

    def ask(self, text, default=None):
        suffix = f" [{default}]" if default is not None else ""
        answer = input(f"{text}{suffix}: ").strip()
        if answer.lower() in ("q", "quit", "back"):
            raise Cancelled("Cancelled; no result saved.")
        return answer or (default if default is not None else "")

    def confirm(self, text, default=False):
        while True:
            answer = self.ask(text + " (y/n)", "y" if default else "n").lower()
            if answer in ("y", "yes", "n", "no"):
                return answer in ("y", "yes")
            self.say("Please answer y or n.", "yellow")


class Cancelled(Exception):
    pass


def clean_path(value):
    """Accept pasted/dragged paths enclosed in either kind of quote."""
    value = str(value).strip()
    # PowerShell's drag-and-drop format can prefix a quoted path with &.
    if value.startswith("& "):
        value = value[2:].lstrip()
    if "\x00" in value:
        raise ValueError("Paths cannot contain NUL bytes.")
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return Path(os.path.expandvars(value)).expanduser().resolve()


def is_mobile_environment():
    return (hasattr(sys, "getandroidapilevel") or sys.platform == "android"
            or bool(os.environ.get("TERMUX_VERSION"))
            or "com.termux" in os.environ.get("PREFIX", ""))


def is_lua_path(path):
    if path.name.lower().endswith((".lua", ".luau", ".lua.txt", ".luau.txt")):
        return True
    if path.suffix.lower() == ".txt" and path.is_file():
        with path.open("rb") as inp:
            head = inp.read(4096).decode("utf-8", errors="replace")
        return bool(BANNER.search(head) or re.search(r"Clyde Protection|ClydeProtection|clydeprotection", head, re.I))
    return False


def script_stem(path):
    return path.with_suffix("").stem if path.name.lower().endswith((".lua.txt", ".luau.txt")) else path.stem


def scan_lua(folder):
    # Deliberately only scan the selected folder, not unrelated directories.
    return sorted((p for p in folder.iterdir()
                   if p.is_file() and is_lua_path(p)),
                  key=lambda p: p.name.casefold())


def validate_input(path):
    if not path.is_file():
        raise ValueError(f"Input file not found: {path}")
    if not is_lua_path(path):
        raise ValueError("Select a .lua, .luau, .lua.txt or .luau.txt file.")
    if not path.stat().st_size:
        raise ValueError("The selected file is empty.")
    return path


def select_input(ui):
    while True:
        path = clean_path(ui.ask("Path to a Lua file or folder (q = back)"))
        try:
            if path.is_dir():
                files = scan_lua(path)
                if not files:
                    raise ValueError("No .lua/.luau files found in that folder (non-recursive scan).")
                for i, file in enumerate(files, 1):
                    ui.say(f"  {i}. {file.name} ({file.stat().st_size:,} bytes)", "cyan")
                choice = ui.ask("Pick file number")
                if not choice.isdigit() or not 1 <= int(choice) <= len(files):
                    raise ValueError("Pick a number from the file list.")
                path = files[int(choice) - 1]
            return validate_input(path)
        except (OSError, ValueError) as exc:
            ui.say(str(exc), "red")


def detect_engine(path):
    """Use explicit banners first, then the existing detectors in isolation.

    Subprocess isolation matters: root and engine folders both contain modules
    called ir, structure, etc. Never mix them in this launcher's sys.path.
    """
    with path.open("rb") as source:
        head = source.read(20000).decode("utf-8-sig", errors="replace")
    if re.search(r"Clyde Protection|ClydeProtection|clydeprotection", head, re.I):
        node = shutil.which("node")
        if node:
            detected = subprocess.run([node, str(ROOT / "clyde_cli.js"), str(path), "--detect"],
                                      capture_output=True, text=True, timeout=15)
            if detected.returncode == 0 and json.loads(detected.stdout).get("isClyde"):
                return "clyde", "Clyde signature verified by the pinned static detector"
        return None, "Clyde signature found; install Node.js 16+ or select Clyde manually"
    match = BANNER.search(head[:4096])
    if match:
        version = match.group(1)
        for engine in ENGINES[1:]:
            if version == engine or version.startswith(engine + "."):
                warning = ("; experimental v15 compatibility — full v15.1 recovery is not verified"
                           if version.startswith("15.") and not version.startswith("15.0") else "")
                return engine, f"header v{version}{warning}"
        return None, f"unsupported header v{version}; do not assume a compatible engine"
    if head.lstrip().startswith("local init = (function(...") and "return({" in head:
        return "14.8", "v14.8 layout heuristic (not a guarantee)"
    result = subprocess.run([sys.executable, "-B", str(ENGINE_ROOT / "deob.py"), str(path), "--detect"],
                            capture_output=True, text=True, errors="replace", timeout=30,
                            cwd=ENGINE_ROOT)
    if result.returncode == 0:
        fields = result.stdout.strip().split("\t")
        try:
            confidence = float(fields[1]) if len(fields) >= 2 else 0
        except ValueError:
            confidence = 0
        if fields[0] == "luraph_v15" and math.isfinite(confidence) and 0.5 <= confidence <= 1:
            return "15", f"existing v15 detector, confidence {fields[1]} (heuristic)"
    else:
        return None, "detector failed; check engine installation or select the known version manually"
    return None, "unknown/ambiguous; header-stripped v14 files need a manual choice"


def choose_engine(ui, path):
    try:
        detected, reason = detect_engine(path)
    except (OSError, subprocess.SubprocessError) as exc:
        detected, reason = None, f"detector unavailable ({exc}); manual version selection is still available"
    ui.say(f"Detection: {detected or 'unknown'} — {reason}", "cyan")
    while True:
        choice = ui.ask("Engine: auto / clyde / 14.7 / 14.8 / 14.9 / 15", "auto").lower().removeprefix("v")
        if choice not in ENGINES:
            ui.say("Choose a listed version.", "yellow")
        elif choice == "auto" and not detected:
            ui.say("Cannot safely auto-detect. Select the known version, or q to go back.", "yellow")
        else:
            if choice != "auto" and detected and choice != detected:
                if not ui.confirm(f"Detected {detected}; override with {choice}?"):
                    continue
            return detected if choice == "auto" else choice


def output_path(value, source):
    path = clean_path(value)
    if path.is_dir():
        path /= script_stem(source) + ".deobfuscated.lua"
    if path == source or (path.exists() and os.path.samefile(path, source)):
        raise ValueError("Output cannot replace the original input file.")
    if path.suffix.lower() not in (".lua", ".luau"):
        raise ValueError("Use an output filename ending in .lua/.luau, or an existing folder.")
    return path


def select_output(ui, source):
    default = source.with_name(script_stem(source) + ".deobfuscated.lua")
    while True:
        try:
            path = output_path(ui.ask("Output file or existing folder", str(default)), source)
            if path.exists() and not ui.confirm(f"Replace existing output {path}?"):
                continue
            return path
        except (OSError, ValueError) as exc:
            ui.say(str(exc), "red")


def find_runtime():
    name = "luau.exe" if os.name == "nt" else "luau"
    local = ENGINE_ROOT / "bin" / name
    if local.is_file() and os.access(local, os.X_OK):
        return str(local)
    return shutil.which(name)


def find_ast():
    # Engines address this exact local path, not PATH.
    path = ENGINE_ROOT / "bin" / ("luau-ast.exe" if os.name == "nt" else "luau-ast")
    return str(path) if path.is_file() and os.access(path, os.X_OK) else None


def validate_native_tools():
    """Execute a tiny trusted fixture; file permissions alone do not prove readiness."""
    runtime, ast = find_runtime(), find_ast()
    errors = []
    with tempfile.TemporaryDirectory(prefix="null-tools-") as work:
        source = Path(work) / "probe.lua"
        source.write_text('print("null-native-tool-check")\n', encoding="ascii")
        for label, exe in (("Luau", runtime), ("Luau AST", ast)):
            if not exe:
                errors.append(f"{label} missing")
                continue
            try:
                result = subprocess.run([exe, str(source)], capture_output=True, timeout=10)
                if result.returncode:
                    detail = result.stderr.decode("utf-8", errors="replace").strip()[:300]
                    raise ValueError(f"exit {result.returncode}: {detail}")
                if label == "Luau":
                    if result.stdout.strip() != b"null-native-tool-check":
                        raise ValueError("runtime did not execute the test print correctly")
                else:
                    data = json.loads(result.stdout.decode("latin-1"))
                    if not isinstance(data, dict) or not isinstance(data.get("root"), dict):
                        raise ValueError("AST output has no compatible root object")
                    if data["root"].get("type") != "AstStatBlock":
                        raise ValueError("AST root is not AstStatBlock")
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                errors.append(f"{label} unusable: {exc}")
    return errors


def doctor(ui):
    ui.say("null • environment check", "bold cyan")
    ui.say(f"Python: {sys.version.split()[0]} ({sys.executable})")
    rich = importlib.util.find_spec("rich") is not None
    ui.say(f"Color/live UI: {'ready' if rich else 'optional Rich missing — run --setup'}")
    runtime = find_runtime()
    ui.say(f"Luau: {runtime or 'missing — run --setup (or build_luau.py)'}")
    ast = find_ast()
    ui.say(f"Luau AST: {ast or 'missing — rerun --setup'}")
    checks = [ENGINE_ROOT / "cli.py", ENGINE_ROOT / "deob.py", ENGINE_ROOT / "envlog.luau"]
    for version in (item for item in ENGINES[1:] if item != "clyde"):
        checks.append(ENGINE_ROOT / "obfuscators" / ("luraph_v" + version.replace(".", "_")) / "__init__.py")
    checks.extend([ROOT / "clyde_cli.js", ROOT / "vendor/clyde/clyde_static_deob.js", ROOT / "vendor/clyde/LICENSE"])
    ui.say("Clyde / Node.js: " + (shutil.which("node") or "optional Node.js missing — install it for Clyde"))
    missing = [str(p) for p in checks if not p.is_file()]
    ui.say("Engine files: " + (", ".join(missing) if missing else "all present"))
    build_path = str(ROOT / ".venv" / ("Scripts" if os.name == "nt" else "bin")) + os.pathsep + os.environ.get("PATH", "")
    ui.say("Native build tools: " + ", ".join(f"{x}={'yes' if shutil.which(x, path=build_path) else 'no'}"
                                               for x in ("git", "cmake", "g++", "clang++", "cl")))
    ui.say("Bundled Windows runtime is stock; patched builds improve Vector3 compatibility.", "yellow")
    failures = validate_native_tools() if runtime and ast and not missing else []
    for error in failures:
        ui.say(error, "red")
    if runtime and ast and not missing and not failures:
        ui.say("Native execution and AST format checks: passed", "green")
    return 0 if runtime and ast and not missing and not failures else 1


def stop_child(process):
    if os.name == "nt":
        if process.poll() is None:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if process.poll() is None:
                process.kill()
        process.wait()
        return
    # Kill the whole isolated session, including orphaned harness/compiler
    # children even if their launcher has already exited.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        process.wait()
        return
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        pass
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def stream_process(command, ui, *, cwd=ROOT, timeout=600, extra_env=None):
    """Stream merged unbuffered logs and keep a heartbeat when engines are quiet."""
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    if extra_env:
        env.update(extra_env)
    process = subprocess.Popen([str(x) for x in command], cwd=cwd, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding="utf-8", errors="replace",
                               start_new_session=os.name != "nt")
    lines = queue.Queue()

    def reader():
        try:
            for line in process.stdout:
                # Prevent source-controlled terminal escapes from reaching the terminal.
                safe = "".join(c for c in line.rstrip() if c == "\t" or c.isprintable())
                lines.put(safe)
        finally:
            lines.put(None)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    started = last_heartbeat = time.monotonic()
    status = (ui.console.status("Running engine…", spinner="dots")
              if ui.console and ui.console.is_terminal else None)
    try:
        if status:
            status.start()
        done = False
        while not done or process.poll() is None:
            elapsed = time.monotonic() - started
            if timeout and elapsed > timeout:
                raise TimeoutError(f"Job exceeded {timeout:g}s; increase --job-timeout if needed.")
            if status:
                status.update(f"Working • {elapsed:.0f}s elapsed • Ctrl+C to cancel")
            elif time.monotonic() - last_heartbeat >= 10:
                ui.say(f"[working] {elapsed:.0f}s elapsed; waiting for engine activity…")
                last_heartbeat = time.monotonic()
            try:
                line = lines.get(timeout=0.15)
                if line is None:
                    done = True
                else:
                    ui.say(line)
            except queue.Empty:
                pass
        return process.wait()
    finally:
        stop_child(process)
        if status:
            status.stop()
        thread.join(timeout=2)
        process.stdout.close()


def setup_prerequisite_hint():
    if "com.termux" in sys.executable or hasattr(sys, "getandroidapilevel") or sys.platform == "android":
        return "Termux: pkg install python python-pip git clang cmake ninja make"
    if sys.platform == "darwin":
        return "macOS: xcode-select --install; then install Git and CMake (for example brew install git cmake)."
    if os.name == "nt":
        return "Windows: install Git, CMake and C++ Build Tools; run from a Developer PowerShell."
    return "Ubuntu/Debian: sudo apt-get install python3-venv python3-pip git cmake build-essential ninja-build (omit sudo in a root proot shell)."


def setup(ui, skip_runtime=False, build_runtime=False, jobs=None):
    """One command creates a local environment and prepares native prerequisites."""
    target = ROOT / ".venv"
    python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    ui.say("[1/3] Preparing isolated .venv (no global pip changes)…", "cyan")
    if not python.is_file():
        if is_mobile_environment():
            # Termux distributes pip separately; do not bootstrap/upgrade its
            # system pip with ensurepip. pip still installs into the venv.
            venv.EnvBuilder(with_pip=False, system_site_packages=True).create(target)
        else:
            venv.EnvBuilder(with_pip=True).create(target)
    ui.say("[2/3] Installing color/live dependency from requirements.txt…", "cyan")
    if stream_process([python, "-m", "pip", "install", "-r", ROOT / "requirements.txt"], ui, timeout=300):
        raise RuntimeError("Dependency installation failed. Check pip/network access and rerun --setup.")
    if skip_runtime:
        ui.say("[3/3] Native Luau setup skipped; deobfuscation still requires it.", "yellow")
    elif find_runtime() and find_ast() and not build_runtime and not validate_native_tools():
        ui.say(f"[3/3] Using Luau: {find_runtime()}", "green")
    else:
        # Also find tools installed into this venv without requiring shell
        # activation (for example `python -m pip install cmake`).
        tool_path = str(python.parent) + os.pathsep + os.environ.get("PATH", "")
        required = [tool for tool in ("git", "cmake") if not shutil.which(tool, path=tool_path)]
        if not any(shutil.which(tool, path=tool_path) for tool in ("g++", "clang++", "cl")):
            required.append("a C++ compiler (GCC, Clang or MSVC developer prompt)")
        if required:
            raise RuntimeError("Install native build prerequisites: " + ", ".join(required)
                               + ".\n" + setup_prerequisite_hint()
                               + "\nThen rerun python start.py. See read.md for OS instructions.")
        ui.say("[3/3] Building pinned, patched Luau; first setup can take several minutes…", "cyan")
        command = [python, ENGINE_ROOT / "build_luau.py", "--portable"]
        if jobs is not None:
            command.extend(["--jobs", str(jobs)])
        if stream_process(command, ui, timeout=1800, extra_env={"PATH": tool_path}):
            raise RuntimeError("Luau build failed; see the build log above and read.md.")
        if not find_runtime() or not find_ast():
            raise RuntimeError("Build finished but executable Luau / Luau AST tools are missing.")
    if not skip_runtime:
        failures = validate_native_tools()
        if failures:
            raise RuntimeError("Native tool validation failed: " + "; ".join(failures))
    easy_python = "py -3" if os.name == "nt" else ("python" if is_mobile_environment() else "python3")
    ui.say("Setup complete.", "bold green")
    ui.say(f"Easy start from the repository folder: {easy_python} start.py", "cyan")
    ui.say("Or use the environment directly:")
    command = f'"{python}" "{ROOT / "cli.py"}"'
    if os.name == "nt":
        ui.say("PowerShell:")
        ui.say("& " + command)
        ui.say("Command Prompt:")
    ui.say(command)


def engine_command(source, destination, engine, trace_only=False):
    if engine not in ENGINES[1:]:
        raise ValueError(f"Unsupported engine: {engine}")
    if engine == "clyde":
        if trace_only:
            raise ValueError("Clyde is static; behavior-trace mode is not supported.")
        node = shutil.which("node")
        if not node:
            raise RuntimeError("Clyde requires Node.js 16+.")
        return [node, "--max-old-space-size=256", str(ROOT / "clyde_cli.js"), str(source), "-o", str(destination),
                "--report", str(destination) + ".report.json"]
    if engine == "15":
        command = [sys.executable, "-B", "-u", str(ENGINE_ROOT / "deob.py"), str(source),
                   "-o", str(destination), "--obfuscator", "luraph_v15", "--no-pypy"]
    else:
        command = [sys.executable, "-B", "-u", str(ENGINE_ROOT / "cli.py"), str(source),
                   "-o", str(destination), "--engine", engine]
    if trace_only:
        command.append("--no-devirt")
    return command


def validate_result(path):
    """Reject syntactically broken output without executing recovered code.

    Return whether the parsed root contains executable statements. A
    comments-only trace may be legitimate but must be disclosed to the user.
    """
    try:
        result = subprocess.run([find_ast(), str(path)], capture_output=True, timeout=30)
        diagnostics = result.stderr.decode("utf-8", errors="replace").strip()
        if result.returncode or "parse errors" in diagnostics.lower():
            raise ValueError(diagnostics[:1000] or f"AST tool exit {result.returncode}")
        data = json.loads(result.stdout.decode("latin-1"))
        root = data.get("root") if isinstance(data, dict) else None
        if not isinstance(root, dict) or root.get("type") != "AstStatBlock" or not isinstance(root.get("body"), list):
            raise ValueError("AST tool returned an incompatible result")
        pending = [root]
        while pending:
            node = pending.pop()
            if isinstance(node, dict):
                if node.get("type") in ("AstExprError", "AstStatError", "AstTypeError"):
                    raise ValueError("recovered syntax contains parser error nodes")
                pending.extend(node.values())
            elif isinstance(node, list):
                pending.extend(node)
        return bool(root["body"])
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"Recovered Lua failed syntax validation; destination was not changed: {exc}") from exc


def publish_new_result(source, destination):
    """No-clobber publish, including Android shared storage without hardlinks.

    Hardlink publication is atomic. The fallback reserves a new filename
    exclusively and copies it, cleaning up an incomplete copy on errors.
    It never overwrites an existing destination, but readers can observe the
    copy in progress on shared/FAT storage.
    """
    try:
        os.link(source, destination)
        source.unlink()
        return True
    except FileExistsError as exc:
        raise RuntimeError("Output appeared during this job; refusing to replace it.") from exc
    except OSError as exc:
        if exc.errno not in (errno.EPERM, errno.EACCES, errno.EXDEV, errno.EOPNOTSUPP, errno.ENOSYS):
            raise
    try:
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise RuntimeError("Output appeared during this job; refusing to replace it.") from exc
    created = os.fstat(fd)
    try:
        with os.fdopen(fd, "wb") as out, source.open("rb") as inp:
            shutil.copyfileobj(inp, out)
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        # Only remove the file we created, not an externally replaced path.
        try:
            current = destination.stat()
            if (created.st_dev, created.st_ino) == (current.st_dev, current.st_ino):
                destination.unlink()
        except FileNotFoundError:
            pass
        raise
    return False


def run_job(ui, source, destination, engine, *, trace_only=False, timeout=600, overwrite=False):
    validate_input(source)
    destination = output_path(destination, source)
    previous = destination.stat() if destination.exists() else None
    if previous is not None and not overwrite:
        raise ValueError("Output already exists; replacement requires confirmation or --force.")
    if not find_runtime():
        raise RuntimeError("Luau runtime missing. Run python cli.py --setup first; see read.md.")
    if not find_ast():
        raise RuntimeError("Luau AST tool missing. Rerun python cli.py --setup; both native tools are required.")
    failures = validate_native_tools()
    if failures:
        raise RuntimeError("Native tool validation failed: " + "; ".join(failures) + ". Rerun --setup.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    ui.say(f"Input: {source}\nEngine: {engine}\nOutput: {destination}", "cyan")
    ui.say("Mode: " + ("BEHAVIOR TRACE ONLY — not full deobfuscation" if trace_only
                            else "devirtualization (partial recovery is possible)"), "yellow")
    ui.say("Stages: input scanned → engine/logs → syntax check → save. No invented percent/ETA.")
    started = time.monotonic()
    # Stage on the destination filesystem: failure/cancellation leaves existing output intact.
    with tempfile.TemporaryDirectory(prefix=".null-deob-", dir=destination.parent) as work:
        staged = Path(work) / "result.lua"
        code = stream_process(engine_command(source, staged, engine, trace_only), ui,
                              cwd=ENGINE_ROOT, timeout=timeout)
        if code:
            raise RuntimeError(f"Engine failed (exit {code}); destination was not changed.")
        if not staged.is_file() or not staged.stat().st_size:
            raise RuntimeError("Engine produced no non-empty result; destination was not changed.")
        if engine == "clyde":
            from clyde_refine import refine_if_known
            report_path = Path(str(staged) + ".report.json")
            if refine_if_known(source, staged, report_path, find_ast()):
                ui.say("Recovered the reviewed RoMidi loader with null's sample-scoped static pass; external payload not fetched.", "yellow")
            metadata = json.loads(report_path.read_text())
            if metadata.get("status") == "partial":
                ui.say("WARNING: Clyde recovered only a partial layer; a VM remains. This is not full deobfuscation.", "yellow")
        ui.say("Engine finished; checking recovered Lua syntax…", "cyan")
        if not validate_result(staged):
            ui.say("WARNING: no executable statements recovered; result contains only comments/whitespace.\n"
                   "Do not treat this as complete recovery.", "yellow")
        ui.say("Syntax check passed; saving recovered result…", "cyan")
        # Recheck aliases and changes made while the engine was running.
        output_path(destination, source)
        if previous is None:
            # Atomic no-clobber publish: never replace a file that appeared
            # after the user selected a previously unused destination.
            if not publish_new_result(staged, destination):
                ui.say("Saved using shared-storage copy fallback (filesystem does not support atomic hardlinks).", "yellow")
        else:
            current = destination.stat() if destination.exists() else None
            identity = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns) if st else None
            if identity(previous) != identity(current):
                raise RuntimeError("Output changed during this job; refusing to replace it.")
            os.replace(staged, destination)
    ui.say(f"Saved: {destination}\n{destination.stat().st_size:,} bytes • {time.monotonic() - started:.1f}s", "bold green")
    ui.say("Review engine warnings and the result: saved does not mean complete or equivalent recovery.", "yellow")
    return destination


def inspect_vm(ui, source, output=None, *, timeout=600):
    """Run the native static front-end in isolation; never execute the input."""
    validate_input(source)
    if not find_ast():
        raise RuntimeError("Luau AST tool missing. Run python start.py --setup first.")
    destination = clean_path(output) if output else source.with_name(script_stem(source) + ".vm-map.json")
    if destination.is_dir():
        destination = destination / (script_stem(source) + ".vm-map.json")
    if destination.resolve() == source.resolve():
        raise ValueError("VM map must not replace the input.")
    if destination.suffix.lower() != ".json":
        raise ValueError("Static VM inspection requires a .json output, not recovered Lua.")
    if destination.exists():
        raise ValueError("VM map already exists; choose a new output path.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    ui.say("Static 15.1 VM discovery: source will NOT be executed. This is not full devirtualization.", "yellow")
    with tempfile.TemporaryDirectory(prefix=".null-deob-", dir=destination.parent) as work:
        staged = Path(work) / "map.json"
        command = [sys.executable, "-B", str(ENGINE_ROOT / "obfuscators/luraph_v15/inspect15_1.py"),
                   str(source), "-o", str(staged)]
        code = stream_process(command, ui, cwd=ENGINE_ROOT, timeout=timeout)
        if code:
            raise RuntimeError(f"VM discovery failed (exit {code}); no output published.")
        report = json.loads(staged.read_text(encoding="utf-8"))
        if report.get("stage") != "static_vm_discovery" or report.get("full_devirtualization") is not False:
            raise RuntimeError("Invalid static VM report; no output published.")
        publish_new_result(staged, destination)
    ui.say(f"Saved VM map: {destination} — {report['dispatcher_count']} dispatchers, "
           f"{report['curried_factory_count']} curried factories. Semantic lifting is not complete.", "yellow")
    return destination


def interactive(ui, args):
    ui.say("null • Clyde + Luraph deobfuscator", "bold cyan")
    ui.say("Only analyze code you own or are authorized to inspect. q = back; Ctrl+C = cancel.")
    while True:
        ui.say("\n[1] Start deobfuscation\n[2] Setup / repair dependencies\n[3] Environment check\n[4] Help\n[0] Exit", "cyan")
        try:
            choice = ui.ask("Select", "1")
            if choice in ("0", "exit"):
                return 0
            if choice == "1":
                source = select_input(ui)
                ui.say(f"Scanned: {source.name} • {source.stat().st_size:,} bytes", "green")
                engine = choose_engine(ui, source)
                destination = select_output(ui, source)
                trace = False if engine == "clyde" else ui.confirm("Fast behavior trace only? (not full deobfuscation)")
                ui.say("Clyde uses static recovery; input is not executed." if engine == "clyde" else
                       "The engine executes the input in an emulated environment; this is not an OS security boundary.", "yellow")
                if ui.confirm("Start this job?", default=True):
                    run_job(ui, source, destination, engine, trace_only=trace, timeout=args.job_timeout,
                            overwrite=destination.exists())
            elif choice == "2":
                if ui.confirm("Create .venv, install Rich, and build Luau if missing? Requires internet"):
                    setup(ui, jobs=args.jobs)
                    ui.say("Restart with start.py to select .venv automatically and enable Rich.")
            elif choice == "3":
                doctor(ui)
            elif choice == "4":
                ui.say("Paste a file path, or a folder to list its Lua files. Choose auto or a known version,\n"
                       "then choose an output file/folder. Existing results require confirmation.\n"
                       "Quiet engines still show elapsed time. Ctrl+C stops the job. See read.md.\n"
                       "Use an isolated machine/container for untrusted scripts; traces miss unexecuted paths.")
            else:
                ui.say("Choose 0–4.", "yellow")
        except EOFError:
            ui.say("\nInput closed. Exiting.")
            return 0
        except (Cancelled, KeyboardInterrupt):
            ui.say("\nCancelled. Returned to menu.", "yellow")
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            ui.say(f"Error: {exc}", "red")


def parser():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", nargs="?", help="omit to open the guided menu")
    ap.add_argument("-o", "--output", help="output Lua file or existing folder")
    ap.add_argument("--engine", choices=ENGINES, default="auto")
    ap.add_argument("--trace-only", action="store_true", help="behavior trace only, not full devirtualization")
    ap.add_argument("--force", action="store_true", help="allow replacing output (never the input)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--setup", action="store_true", help="create .venv, install Rich, prepare Luau")
    mode.add_argument("--doctor", action="store_true", help="check dependencies and engine files")
    mode.add_argument("--inspect-vm", action="store_true", help="static 15.1 VM/closure discovery to JSON; never executes input")
    ap.add_argument("--skip-runtime", action="store_true", help="with --setup, install Python dependencies only")
    ap.add_argument("--build-runtime", action="store_true", help="with --setup, build patched Luau even if already present")
    ap.add_argument("--jobs", type=int, help="native compiler jobs for setup/menu setup (mobile default 1, otherwise 2)")
    ap.add_argument("--no-color", action="store_true", help="disable color (also honors NO_COLOR)")
    ap.add_argument("--job-timeout", type=float, default=600, help="whole job timeout in seconds (default 600)")
    return ap


def configure_output_streams():
    # Legacy Windows shells / redirected ASCII logs must not crash on UI
    # bullets, arrows, or Unicode filenames. Keep the user's encoding and
    # escape only characters that it cannot represent.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="backslashreplace")
            except (OSError, ValueError):
                pass


def main(argv=None):
    configure_output_streams()
    ap = parser()
    args = ap.parse_args(argv)
    if args.jobs is not None and args.jobs < 1:
        ap.error("--jobs must be at least 1")
    if not math.isfinite(args.job_timeout) or args.job_timeout <= 0:
        ap.error("--job-timeout must be positive")
    if (args.skip_runtime or args.build_runtime) and not args.setup:
        ap.error("--skip-runtime/--build-runtime require --setup")
    if args.skip_runtime and args.build_runtime:
        ap.error("choose either --skip-runtime or --build-runtime")
    if args.input and (args.setup or args.doctor):
        ap.error("do not combine an input file with --setup/--doctor")
    if args.inspect_vm and (not args.input or args.trace_only or args.force or args.engine != "auto"):
        ap.error("--inspect-vm needs an input and a new JSON output; do not combine it with --trace-only/--force/--engine")
    ui = UI(args.no_color)
    try:
        if args.setup:
            setup(ui, args.skip_runtime, args.build_runtime, args.jobs)
            return 0
        if args.doctor:
            return doctor(ui)
        if not args.input:
            if args.output or args.engine != "auto" or args.force or args.trace_only:
                ap.error("job options require an input; the menu asks for its own settings")
            return interactive(ui, args)
        source = validate_input(clean_path(args.input))
        if args.inspect_vm:
            inspect_vm(ui, source, args.output, timeout=args.job_timeout)
            return 0
        engine = args.engine
        if engine == "auto":
            engine, reason = detect_engine(source)
            ui.say(f"Detection: {engine or 'unknown'} — {reason}")
            if engine is None:
                raise ValueError("Cannot safely auto-detect; supply --engine 14.7/14.8/14.9/15.")
        destination = output_path(args.output or source.with_name(script_stem(source) + ".deobfuscated.lua"), source)
        if destination.exists() and not args.force:
            raise ValueError("Output already exists. Use a different path or --force.")
        run_job(ui, source, destination, engine, trace_only=args.trace_only, timeout=args.job_timeout, overwrite=args.force)
        return 0
    except (KeyboardInterrupt, Cancelled, EOFError):
        ui.say("\nCancelled; no result saved.", "yellow")
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        ui.say(f"Error: {exc}", "red")
        return 1


if __name__ == "__main__":
    if sys.version_info < (3, 10):
        sys.exit("Python 3.10 or newer is required.")
    sys.exit(main())
