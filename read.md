# null • Clyde + Luraph

Project owner / maintainer: **null**.

A guided, colored terminal menu for pinned static **Clyde** and the existing Luraph **14.7 / 14.8 / 14.9 / 15** engines. This launcher does not claim to be a new universal decryptor: recovery depends on the input, VM layout, runtime compatibility, and existing engines. Original variable names and every code path cannot always be recovered.

## Web workspace / launch from GitHub

**[Open the web launcher guide](WEB.md)** for the actual backend, private GitHub
Codespaces launcher, engine/mode selection, upload, live logs, cancellation,
source preview and downloads. A separate **[GitHub Pages browser edition](WEB.md#github-pages--githubio)**
runs Clyde locally without uploads; Luraph still requires the private backend.
For github.io hosting, select this branch and `/docs` in repository Settings → Pages.
The current connection was denied permission to enable Pages automatically (403).
Product and integration branding: **null**; upstream license notices remain intact.

After the existing one-command setup below, install Node.js 16+ for Clyde (22 recommended).
Termux:

```bash
pkg install nodejs
```

Ubuntu / Debian:

```bash
sudo apt install nodejs
```

Start the safe-mode website:

```bash
python3 web_server.py --host 0.0.0.0 --port 8080
```

On Termux:

```bash
python web_server.py --host 0.0.0.0 --port 8080
```

Clyde CLI (same auto/manual engine selector and output handling):

```bash
python3 start.py "your-script.txt" --engine clyde -o "output/local/recovered.lua"
```

Recognizable Clyde/Luraph `.txt` attachments are included in input scanning.
Clyde is static; Luraph execution is owner-opt-in in the website. See [WEB.md](WEB.md)
for private dynamic workers. Raw engine/required attribution: [THIRD_PARTY.md](THIRD_PARTY.md).

**RoMidi result:** [recovered loader](output/recovered/RoMidiYessirAp.deobfuscated.lua)
and [analysis evidence](output/recovered/RoMidiYessirAp.analysis.json). The attached
file only loads an external Gist. That MIDI payload was not attached, fetched,
executed or recovered. The loader was statically reconstructed and syntax-checked;
behavioral equivalence is not certified.

## Easiest daily command

After the OS prerequisites and clone steps below, use the same command for first setup and every later session:

```bash
python3 start.py
```

On **Termux**, use:

```bash
python start.py
```

On **Windows**, use:

```powershell
py -3 start.py
```

First use asks permission to create the local environment, install Rich, and prepare both native tools, then opens the menu. Later runs automatically select `.venv`; no activation is needed. Errors include platform-specific prerequisite instructions. The starter uses the existing native Luraph engine and the reviewed, vendored Clyde static engine; it does not download and run arbitrary candidate binaries.

For explicit setup/repair without opening the menu:

```bash
python3 start.py --setup --jobs 1
```

For unattended first setup followed by the menu, explicitly permit installation:

```bash
python3 start.py --yes --jobs 1
```

Without `--yes`, non-interactive input will not silently trigger a download. Existing `cli.py` commands remain supported; job options can also be forwarded through `start.py`:

```bash
python3 start.py "protected.lua" -o "results/clean.lua"
```

**Compatibility:** Luraph 15.1 banners are recognized, but the current v15 backend is an experimental compatibility route, not verified full 15.1 support. The uploaded `steal.lua.txt` remains partially recovered after two additional tests of a public 15.1 candidate. [Read the actual research and rejection results](output/recovered/research-15.1.md).

## What’s new

- **One setup command:** creates a local `.venv`, installs Rich for colors/live status, and builds the pinned, patched Luau runtime if no usable runtime exists. No global pip install.
- **Start menu:** paste a `.lua`/`.luau` path (also `.lua.txt`/`.luau.txt` attachments), or paste a folder and pick a numbered file. Scans the chosen folder only; uppercase extensions and quoted paths with spaces work.
- **Auto or manual version:** uses banners first, then existing layout/plugin heuristics. Ambiguous files require a manual choice instead of silently using the wrong engine. Unsupported banners are reported.
- **Output selection:** choose a filename or an existing folder. Missing output parent folders are created. Input files are never overwritten; existing results require confirmation (or `--force` in command mode).
- **Live activity:** actual engine logs, a spinner, elapsed time, and a heartbeat in plain mode. No fake percentage or estimated completion time. During quiet lifting phases the spinner indicates activity, not measurable progress.
- **Failure protection:** results are staged and syntax-checked with `luau-ast` before saving. Existing outputs require consent and are rechecked for changes during the job. New outputs are published without overwriting a file that appeared meanwhile. Android shared storage without hardlinks uses an exclusive-create copy fallback; readers may see the copy in progress, and interruption cleans up the partial copy.
- **Practical controls:** Ctrl+C cancels the running job and its process tree, `q` goes back at prompts, environment checks, color-off mode, configurable whole-job timeout, and optional trace-only mode.
- **No Rich required to start:** the menu works in plain text before setup. Restart with the printed `.venv` command after setup to enable Rich.

## Requirements

- **Python 3.10+**, with `venv` and `pip`.
- Internet during first setup (PyPI and GitHub); no network is needed by the launcher after dependencies/runtime are installed.
- Windows has bundled stock `luau.exe` tooling. Linux/macOS need a native Luau build. Setup builds it if missing.
- Native builds require **Git, CMake, and a C++ compiler** (GCC, Clang, or MSVC). Two compiler jobs are used by default on desktop; Termux/mobile defaults to one. `--setup --jobs 1` explicitly limits compiler memory use. Native setup can take several minutes.
- Stock Luau (including the bundled Windows runtime) lacks this project's writable Vector3 metatable patch. Use `--build-runtime` for improved Vector3 compatibility. Not every engine/tooling path is guaranteed on every OS; `luau-ast` is required for instrumentation/readability; setup builds both `luau` and `luau-ast`.

## Get the project

Each command is in its own copyable box. Run commands from the repository root unless indicated otherwise. If you already have this working checkout, skip cloning. Clone commands target the feature branch containing this CLI, which has not been merged into `main` here.

```bash
git clone --branch arena/247512c5-nullx11deob https://github.com/Inkflow-Gab/Nullx11deob.git
```

```bash
cd Nullx11deob
```

### Linux prerequisites (Debian / Ubuntu)

Install system prerequisites once; setup cannot install system packages or compilers for you.

```bash
sudo apt-get update
```

```bash
sudo apt-get install -y python3 python3-venv python3-pip git cmake build-essential
```

### macOS prerequisites

Install Python 3.10+ and Git/CMake (for example using Homebrew), and Apple's command-line compiler tools.

```bash
xcode-select --install
```

```bash
brew install python git cmake
```

### Windows prerequisites

Install Python 3.10+ with the Python launcher. The bundled Windows runtime means the usual setup does not need a compiler. For `--build-runtime`, install Git, CMake, and Visual Studio C++ Build Tools, then use a Developer PowerShell/Command Prompt.

## Android / mobile: Termux and Ubuntu

Mobile support is implemented through source builds for the phone's own architecture, not Windows or x86-only downloads. **The configuration and shared-storage behaviors have regression tests; an actual Android handset/ARM Ubuntu session has not been available here, so device-specific execution is not yet verified.** The full pipeline has been tested on Linux x86-64.

### Native Termux (recommended mobile route)

Use a maintained Termux build (for example from F-Droid or the official Termux GitHub releases). Work in Termux's private home directory, **not `/sdcard` or Downloads**: Android shared storage is commonly `noexec` and cannot host the runtime/venv correctly.

```bash
pkg update
```

```bash
pkg install python python-pip git clang cmake ninja make
```

```bash
cd "$HOME"
```

Skip cloning if this checkout already exists in your home directory:

```bash
git clone --branch arena/247512c5-nullx11deob https://github.com/Inkflow-Gab/Nullx11deob.git
```

```bash
cd "$HOME/Nullx11deob"
```

```bash
python cli.py --setup --jobs 1
```

```bash
.venv/bin/python cli.py --doctor
```

```bash
.venv/bin/python cli.py
```

Termux provides pip as a distribution package. Mobile setup creates a venv that can use that distribution pip (`system_site_packages=True`, no ensurepip bootstrap); dependency installation still targets the venv. Do not upgrade/reinstall Termux's global pip with pip. Android builds use the available Clang toolchain and do not force desktop GCC/static-link flags.

To access Downloads, grant the storage permission requested by this command:

```bash
termux-setup-storage
```

Example with an attachment from Downloads (replace the filename as appropriate):

```bash
.venv/bin/python cli.py "$HOME/storage/downloads/StealB.lua.txt" -o "$HOME/storage/downloads/StealB.recovered.lua" --job-timeout 1800
```

Paths with spaces must be quoted. Use the numeric menu followed by Enter on the mobile keyboard. If ANSI colors are troublesome, use `--no-color`.

### Ubuntu on a phone (including proot-distro)

From **Termux**, install and open Ubuntu if you do not already have it:

```bash
pkg install proot-distro
```

```bash
proot-distro install ubuntu
```

```bash
proot-distro login ubuntu
```

The next commands run **inside Ubuntu**, not in the Termux shell. A proot session usually logs in as root; native Ubuntu users should prepend `sudo` to the two apt commands if needed.

```bash
apt-get update
```

```bash
apt-get install -y python3 python3-venv python3-pip git cmake build-essential ninja-build
```

```bash
cd "$HOME"
```

```bash
git clone --branch arena/247512c5-nullx11deob https://github.com/Inkflow-Gab/Nullx11deob.git
```

```bash
cd Nullx11deob
```

```bash
python3 cli.py --setup --jobs 1
```

```bash
.venv/bin/python cli.py --doctor
```

```bash
.venv/bin/python cli.py
```

Build separate native tools inside each environment; do not copy Windows/x86 binaries into ARM Termux or reuse a Termux venv inside Ubuntu. Shared-storage paths depend on the proot bind mounts (`/sdcard/Download` is common); first check that the input path exists inside that Ubuntu session.

### Mobile limits

- Keep enough free RAM and disk for the Luau parser/compiler and large inputs. One job reduces build concurrency, not the size of a single compiler task. Android can still terminate a memory-hungry process.
- Leave the app in the foreground, disable aggressive battery restrictions for long jobs, and expect slower builds/lifting than a desktop.
- Setup's native-build limit is 30 minutes. If a slow phone exceeds it, build manually without that launcher deadline, then rerun setup:

```bash
.venv/bin/python Deobfuscator/deobf/build_luau.py --portable --jobs 1
```

- For a slow deobfuscation run, increase `--job-timeout`; engine-internal per-run budgets still apply. A timeout or incomplete trace is not a successful full recovery.
- New output on shared/FAT storage uses an exclusive copy when atomic hardlinks are unsupported. A partial copy may be visible while writing; detected errors/cancellation remove it. Existing files are never silently overwritten.

## One-time setup + menu

### Linux / macOS

Create the environment, install Python dependencies, and prepare Luau:

```bash
python3 cli.py --setup
```

Start the menu with that environment (no activation required):

```bash
.venv/bin/python cli.py
```

Check the installation:

```bash
.venv/bin/python cli.py --doctor
```

### Windows (PowerShell or Command Prompt)

```powershell
py -3 cli.py --setup
```

```powershell
.venv\Scripts\python.exe cli.py
```

```powershell
.venv\Scripts\python.exe cli.py --doctor
```

`--doctor` returns exit 1 if the runtime, AST tool, or required engine files are missing; missing Rich is optional and reported separately. On Windows setup normally reuses bundled Luau. On Linux/macOS it builds from the pinned Luau tag in `Deobfuscator/deobf/build_luau.py`.

### Optional setup modes

Python dependencies only (does **not** make deobfuscation ready if Luau is missing):

```bash
python3 cli.py --setup --skip-runtime
```

Force a patched runtime build even if a runtime already exists:

```bash
python3 cli.py --setup --build-runtime
```

On Windows replace `python3` in these optional commands with `py -3`.

## Menu walkthrough

```text
null • Luraph deobfuscator

[1] Start deobfuscation
[2] Setup / repair dependencies
[3] Environment check
[4] Help
[0] Exit
```

1. Type **1**, then Enter. This is a terminal menu, not a mouse/touch interface.
2. Paste a file path, such as `C:\Scripts\protected.lua` or `/home/me/scripts/protected.lua`.
3. Alternatively paste a folder; the CLI lists its `.lua`/`.luau` files with sizes. Enter a file number. This lists files, not the full potentially huge obfuscated source.
4. Review the scan/detection result. Enter `auto`, `14.7`, `14.8`, `14.9`, or `15`. Headerless v14 inputs can be ambiguous. Use the known version rather than guessing.
5. Enter a destination filename or existing folder. Press Enter for `<input stem>.deobfuscated.lua` beside the input. A directory that does not exist must be entered as a full filename, such as `new-folder/result.lua`.
6. Choose whether to use **behavior trace only** (default: no). Tracing is faster but is **not full deobfuscation** and only reflects executed paths.
7. Confirm the job. Watch real engine logs and elapsed time. A quiet phase is not necessarily a hang.
8. When successful, the CLI prints the saved file's absolute path, size, and elapsed time. Review engine warnings and the result before relying on it.

Type `q`, `quit`, or `back` at prompts to cancel/go back. Ctrl+C while running cancels the job and returns to the menu. Ctrl+C in command mode exits with status 130. Closing standard input exits the menu.

## Native 15.1 development: static VM discovery

The new native front-end finds curried VM factories, exact captured-variable declarations, and opcode-handler regions. It does **not** execute the inspected source. This is the first stage of native 15.1 support, **not full devirtualization**: prototype capture and semantic lifting remain unfinished.

Inspect the published decoded chunk and write a **new JSON report**:

```bash
python3 start.py output/recovered/steal.partial-decoded.lua --inspect-vm -o output/local/steal.vm-map.json
```

On Termux:

```bash
python start.py output/recovered/steal.partial-decoded.lua --inspect-vm -o output/local/steal.vm-map.json
```

Use an existing decoded VM source file, not an encrypted outer loader. Existing report files are not overwritten. See [native 15.1 progress and remaining stages](output/recovered/native-15.1.md) and the [sample VM map](output/recovered/steal.vm-map.json). The sample remains only partially decoded.

## Direct commands (without the menu)

The following examples use the Linux/macOS venv interpreter. On Windows replace `.venv/bin/python` with `.venv\Scripts\python.exe`. Replace example input/output paths with your own. Quote paths containing spaces.

Automatic detection:

```bash
.venv/bin/python cli.py "protected.lua" -o "results/clean.lua"
```

Force v14.7:

```bash
.venv/bin/python cli.py "protected.lua" --engine 14.7 -o "results/clean.lua"
```

Force v14.8:

```bash
.venv/bin/python cli.py "protected.lua" --engine 14.8 -o "results/clean.lua"
```

Force v14.9:

```bash
.venv/bin/python cli.py "protected.lua" --engine 14.9 -o "results/clean.lua"
```

Force v15:

```bash
.venv/bin/python cli.py "protected.lua" --engine 15 -o "results/clean.lua"
```

Explicitly replace a previous result (never the input):

```bash
.venv/bin/python cli.py "protected.lua" --engine 15 -o "results/clean.lua" --force
```

Behavior trace only — incomplete by design:

```bash
.venv/bin/python cli.py "protected.lua" --engine 15 --trace-only -o "results/trace.lua"
```

Increase the whole-job timeout (default 600 seconds; engine-internal runtime budgets still apply):

```bash
.venv/bin/python cli.py "protected.lua" --engine 15 --job-timeout 1800 -o "results/clean.lua"
```

Disable colors (also honors `NO_COLOR`):

```bash
.venv/bin/python cli.py --no-color
```

List all launcher options:

```bash
.venv/bin/python cli.py --help
```

## Advanced / existing launchers

Existing engine entry points remain available, including their advanced debug, strings, tracing, and lifting flags. They are not replaced by the menu. These commands work from the repository root:

```bash
.venv/bin/python Deobfuscator/deobf/cli.py --help
```

```bash
.venv/bin/python Deobfuscator/deobf/deob.py --help
```

Detect v15 using the existing plugin registry without executing the protected script:

```bash
.venv/bin/python Deobfuscator/deobf/deob.py "protected.lua" --detect
```

Manually build patched Luau with a smaller compiler job count if memory is limited:

```bash
.venv/bin/python Deobfuscator/deobf/build_luau.py --portable --jobs 1
```

The root `deobfuscate.py` is a **separate LuaObfuscator.com/Ferib engine**, not a Luraph engine. The new Luraph menu deliberately does not route unknown files to that unrelated backend.

## Troubleshooting

- **`venv` / `ensurepip` missing:** install your OS's Python venv/pip packages, then rerun setup. Do not use `sudo pip`.
- **Rich missing / no colors:** start with the `.venv` interpreter printed by setup. Plain mode still works. Colors are automatically suppressed for non-terminal output.
- **Luau missing / cannot execute:** Windows `.exe` files do not run natively on Linux/macOS. Install native build prerequisites and rerun `--setup`.
- **Build failed / offline setup:** setup streams compiler/pip logs and exits nonzero on failure. Fix the reported prerequisite/network issue and rerun. Setup does not silently declare a failed native build successful. On first build you need enough RAM/disk; `--jobs 1` reduces compiler concurrency.
- **Vector3 member errors:** build patched Luau with `--setup --build-runtime`.
- **Unknown version:** select the known supported version manually; unsupported versions are not magically compatible. Remove neither the input nor the banner to force a guess.
- **No result / timeout:** check the engine's logs, try the correct version, and increase `--job-timeout` for large files. A trace-only result is not a replacement for full devirtualization.
- **Partial output:** engine limitations still apply; successful saving validates non-empty output and Lua syntax, **not behavioral equivalence or completeness**. Comments-only output is explicitly warned about. Warnings may indicate unresolved states or incomplete code.
- **Auxiliary files:** the launcher stages the final result safely, but engines can still write their own runtime caches/diagnostics near inputs. Avoid read-only input directories and preserve your originals/backups.

## Tests

No third-party test runner is needed. Tests cover selection (including `.lua.txt` attachments), detection, engine routing, output races, shared-storage copy fallback, native-tool execution probes, syntax rejection, process-tree cancellation, mobile build configuration, setup behavior, and menu handling. Starter tests additionally check first-run permission, environment selection, argument forwarding and setup failure handling. Native integration tests additionally run all four frontends and the bundled v15 protected sample when native tools are installed; they do not claim complete recovery for every protected sample.

```bash
python3 -m unittest discover -s tests -v
```

## Verification scope and attached samples

- Full tests and protected-sample runs were executed on Linux x86-64 with Python 3.11.
- Android/Termux/Ubuntu-mobile configurations are tested with host-simulated environment/filesystem cases; a real handset is not certified.
- `.github/workflows/cli-tests.yml` adds Windows/macOS/Linux launcher checks and a complete Linux native-build job. Merely adding this workflow does not mean its remote jobs have run or passed.
- User-requested analysis artifacts are in [`output/recovered/`](output/recovered/README.md). Each result is labeled by actual recovery quality; the v15.1 input did **not** fully devirtualize. An embedded webhook credential was redacted from the GitHub-facing v15.0 result.
- Unredacted working copies, debug dumps, raw inputs, runtime binaries, and venv files remain ignored. Only explicitly selected analysis artifacts are publishable under `output/recovered/`.

## Future ideas (not implemented)

- Batch queue with per-file outcomes and explicit version overrides.
- Optional saved run reports (engine, duration, warnings) with privacy controls.
- Retry presets for known unresolved-state failures, without hiding partial results.

## Ownership, attribution, and safe use

This project's current owner/maintainer branding is **null**. The bundled engine documentation and upstream implementation credits are retained where applicable; changing project branding does not change authorship of existing work. Earlier project documentation credited KryptIT / larpcorrupt for the engine framework.

Only analyze code you own or are authorized to inspect. The engines execute protected code in an emulated environment, which is **not an OS-level security boundary**. Use a disposable, isolated machine/container without secrets for untrusted inputs. The project is not affiliated with Luraph and does not guarantee complete decryption, correctness, or safe execution of arbitrary scripts.
