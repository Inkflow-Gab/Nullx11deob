# null • Luraph Deobfuscator

Owner / maintainer: **null**.

The project now has a guided root-level CLI for the existing Luraph **14.7, 14.8, 14.9, and 15** engines: one-time setup, colors, file/folder selection, auto/manual version selection, safe output handling, and live engine logs with elapsed time.

**[Open read.md for the complete setup guide, menu walkthrough, individually copyable Python commands, troubleshooting, and limitations.](read.md)**

## Quick start — Linux / macOS

Python 3.10+ is required. Native Luau builds require Git, CMake, and a C++ compiler; see [read.md](read.md) for OS prerequisites.

```bash
python3 cli.py --setup
```

```bash
.venv/bin/python cli.py
```

## Quick start — Windows

```powershell
py -3 cli.py --setup
```

```powershell
.venv\Scripts\python.exe cli.py
```

## Mobile / Android

Termux and Ubuntu-on-phone instructions, storage permissions, one-job native builds, and verification limitations are documented in the [mobile setup section](read.md#android--mobile-termux-and-ubuntu). Keep the checkout in private home storage, not `/sdcard`.

## Requested recovery artifacts

See [`output/recovered/README.md`](output/recovered/README.md) for the recovered `StealB` output, the **partial** decoded `steal` chunk, and their limitations. Embedded webhook credentials are redacted from the repository-facing result.

## Existing engines and technical documentation

- `Deobfuscator/deobf/cli.py`: Luraph v14.7 / v14.8 / v14.9 frontend.
- `Deobfuscator/deobf/deob.py`: plugin frontend including Luraph v15.
- `deobfuscate.py`: separate LuaObfuscator.com/Ferib engine, not Luraph.
- [Luraph technical notes](Deobfuscator/LURAPH.md).
- [Framework notes](Deobfuscator/CLAUDE.md).
- [IronBrew technical notes](Deobfuscator/IRONBREW1.md).

Current project branding is null. Upstream engine authorship and technical credits are not reassigned; earlier documentation credited KryptIT / larpcorrupt for the framework.

Use only on code you own or are authorized to inspect. Recovery can be partial; a behavior trace is not full devirtualization. An emulated runtime is not an OS security boundary: use an isolated environment for untrusted scripts.
