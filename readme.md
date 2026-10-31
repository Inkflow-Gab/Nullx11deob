# null • Luraph Deobfuscator

Owner / maintainer: **null**.

The project now has a guided root-level CLI for the existing Luraph **14.7, 14.8, 14.9, and 15** engines: one-time setup, colors, file/folder selection, auto/manual version selection, safe output handling, and live engine logs with elapsed time.

**[Open read.md for the complete setup guide, menu walkthrough, individually copyable Python commands, troubleshooting, and limitations.](read.md)**

## Simplest start — Linux / macOS / Ubuntu

After installing the OS prerequisites in [read.md](read.md), run one command:

```bash
python3 start.py
```

On first use it asks before installing dependencies/building Luau, then opens the menu. On later runs it selects `.venv` automatically—no activation command is needed. If a compiler/CMake package is missing, setup prints a platform-specific package-install hint.

## Simplest start — Windows

```powershell
py -3 start.py
```

## Explicit setup / repair

```bash
python3 start.py --setup --jobs 1
```

Then use `python3 start.py` again. All existing CLI file/output/version options can also be passed to `start.py`.

## Version limits

Luraph **15.1 is recognized but experimental** with the current v15 compatibility backend; recognizing a banner is not full support. The supplied v15.1 file did not fully decode even with the independently tested public candidate. See the [15.1 research report](output/recovered/research-15.1.md).

## Mobile / Android

In Termux, use `python start.py` after installing the required packages. Termux and Ubuntu-on-phone instructions, storage permissions, one-job native builds, and verification limitations are documented in the [mobile setup section](read.md#android--mobile-termux-and-ubuntu). Keep the checkout in private home storage, not `/sdcard`.

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
