# null • Clyde + Luraph

Owner / maintainer: **null**.

The project now has a guided root-level CLI for the existing Luraph **14.7, 14.8, 14.9, and 15** engines: one-time setup, colors, file/folder selection, auto/manual version selection, safe output handling, and live engine logs with elapsed time.

**[Open read.md for the complete setup guide, menu walkthrough, individually copyable Python commands, troubleshooting, and limitations.](read.md)**

## Web workspace

**[Launch / setup guide → WEB.md](WEB.md)** ·
**[Open in GitHub Codespaces](https://github.com/codespaces/new?repo=1440370177&ref=arena%2F247512c5-nullx11deob)**

Minimal vanilla HTML/CSS/JS frontend with a real Python backend: choose Clyde or
Luraph, automatic/manual version, live logs, cancellation, static VM mapping,
source preview/copy, and session-owned downloads. Default safe mode runs static
Clyde and AST inspection; dynamic Luraph needs a private owner-enabled worker.
Codespaces forwards private port 8080. The new **[GitHub Pages browser edition](WEB.md#github-pages--githubio)**
runs static Clyde without a backend or uploads; Luraph still needs a private worker.

Pages address after one-time activation: **https://inkflow-gab.github.io/Nullx11deob/**.
The current GitHub connection could not enable Pages (403). In **Settings → Pages**,
select **Deploy from a branch → `arena/247512c5-nullx11deob` → `/docs` → Save**.
Hosting is not confirmed live until that deployment succeeds.

After normal setup and installing Node.js 16+:

```bash
python3 web_server.py --host 0.0.0.0 --port 8080
```

**RoMidiYessirAp:** [recovered loader](output/recovered/RoMidiYessirAp.deobfuscated.lua)
· [analysis / hashes](output/recovered/RoMidiYessirAp.analysis.json). The attachment
is a remote loader, not the MIDI implementation. Its external payload was not
fetched or executed. Exact-sample static refinement is not general Clyde register-VM
support. Prior StealB/steal results are preserved unchanged.

Branding/integration: **null**. Clyde upstream Jamie / OmniDBF (MIT), pinned and
vendored with unchanged source and required credits; see [THIRD_PARTY.md](THIRD_PARTY.md).

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

## Native 15.1 development

An original static VM-discovery front-end is now available. It detects curried factories, declaration-accurate free bindings, and opcode regions without executing the inspected Lua:

```bash
python3 start.py output/recovered/steal.partial-decoded.lua --inspect-vm -o output/local/steal.vm-map.json
```

This is the first native front-end stage, **not a full 15.1 devirtualizer**. See [implemented behavior, actual sample results, tests, and remaining work](output/recovered/native-15.1.md).

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
