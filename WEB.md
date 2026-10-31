# null — web recovery workspace

Minimal HTML, CSS, and vanilla JavaScript, backed by a Python standard-library
server. No frontend build, CDN, analytics, npm install, or third-party upload API.

## Launch from GitHub

[Open this branch in GitHub Codespaces](https://github.com/codespaces/new?repo=1440370177&ref=arena%2F247512c5-nullx11deob)

Create a Codespace on `arena/247512c5-nullx11deob`. The supplied `.devcontainer`
installs Python/Node, builds pinned Luau tools, and starts the workspace. First
setup takes several minutes. Open **Ports → 8080 → Open in Browser** if it does not
open automatically. **Keep port visibility Private.** Codespaces availability,
quota, and any billing belong to your GitHub account; no Codespace was created
or billed automatically by this change.

If startup fails, open the Codespaces terminal:

```bash
cat output/web-launcher.log
```

Start it manually:

```bash
.venv/bin/python -B web_server.py --host 0.0.0.0 --port 8080
```

**GitHub Pages cannot execute these Python/Node/native engines.** The app uses
same-origin `/api` endpoints. Publishing only `web/` as a Pages site shows a worker
offline message; it does not deobfuscate anything. Codespaces/private backend
hosting is the working GitHub launcher, not a pretend static Pages integration.

## Local setup

Install Python 3.10+, Node.js 16+ (22 recommended), git, CMake, and a C++ compiler.
Existing Termux/Ubuntu setup instructions are in [read.md](read.md).

```bash
python3 start.py --setup --jobs 2
```

```bash
python3 web_server.py --host 0.0.0.0 --port 8080
```

Open `http://localhost:8080` **on the machine running the server**. Browser API calls
are relative URLs and work behind a forwarded port or same-origin reverse proxy;
they never send a remote user's browser to localhost for an API.

Termux:

```bash
pkg install nodejs
```

```bash
python web_server.py --host 0.0.0.0 --port 8080
```

## Engines and modes

- **Auto / Clyde:** source-reviewed, pinned upstream static deobfuscator. No uploaded
  Lua execution. Decodes supported layouts and explicitly labels peeled VM layers
  as partial. Node's heap and the worker's wall time are bounded.
- **Luraph / automatic or manual version:** 14.7, 14.8, 14.9, 15.0, experimental 15.1
  compatibility. A banner is not a support guarantee; the previously supplied
  `steal` remains partial.
- **Luraph / Static VM map:** safe-mode AST inspection of an already decoded chunk;
  exports JSON, not an executable script. It does not unpack an encrypted loader.
- **Luraph / Deobfuscate or Behavior trace:** dynamic emulated execution. Disabled by
  default; needs an owner-enabled private worker and access key as described below.
- **Downloads and source preview:** session-owned, output shown as escaped text,
  no execution; source preview capped at 200 KB, complete download capped at 16 MiB.
  Partial files get `.partial.lua`, static maps `.json`, and reviewed loader-only
  recoveries `.loader.lua`. Syntax checks do not prove completeness or safety.
- Real merged engine logs, elapsed time, stage indicators, cancellation, queueing,
  light/dark theme, drag/drop, mobile layout, and copy source. No invented percentage.

## Private dynamic Luraph worker — optional

**Do not expose dynamic execution publicly.** Emulation is not an OS security
boundary. Use a disposable isolated machine/container without secrets; only inspect
authorized code. This application is a single-owner launcher, not a hardened
multi-tenant service, and must not be treated as an internet-facing execution sandbox.

Create a long random owner key in your terminal (not a GitHub token):

```bash
export NULL_WEB_ACCESS_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
```

Display that key locally and enter it in **Worker settings** in the website:

```bash
printf '%s\n' "$NULL_WEB_ACCESS_KEY"
```

Start the private worker:

```bash
python3 web_server.py --allow-dynamic --host 0.0.0.0 --port 8080
```

Keep the forwarded port private. The key is kept in the browser tab only, never
localStorage, and is excluded from engine subprocess environments. Do not put it
in source control or a URL. For Codespaces auto-start, configure `NULL_WEB_DYNAMIC=1`
and `NULL_WEB_ACCESS_KEY` as private Codespaces environment settings/secrets before
restarting the container. The default launcher does not enable dynamic execution.

## Limits and privacy

- 8 MiB per upload; one running worker, at most four queued, twenty retained jobs.
- Default engine timeout 180 seconds; `--timeout` accepts 10–1800 seconds.
- Signed HttpOnly session cookie; CSRF tokens and same-origin writes. Local HTTP
  uses SameSite=Strict; HTTPS forwarded previews use Secure, SameSite=None,
  Partitioned (CHIPS) so the embedded workspace works without sharing a cookie
  across top-level sites. Open the preview in its own tab if a browser blocks
  all embedded cookies.
  Different sessions cannot view another session's logs, report, preview or download.
- Uploads/results are stored as plaintext in ignored `output/web-jobs/` directories.
  Terminal jobs expire one hour after creation; a clean shutdown removes job data,
  and a subsequent startup removes previous run job directories. A crash does not
  securely erase disk contents. Do not upload sensitive material to an untrusted host.
- Logs are bounded to 256 KB / 4,000 lines, no access-key/request-body access logs, and no permissive CORS.
  Child environments exclude GitHub/cloud credentials. These are mitigations, not OS isolation.
- Use HTTPS for any remote deployment. This built-in server is a private launcher,
  not a replacement for production authentication, rate limits or container isolation.

## Supplied RoMidi result

[`output/recovered/RoMidiYessirAp.deobfuscated.lua`](output/recovered/RoMidiYessirAp.deobfuscated.lua)
contains the **devirtualized loader only**. The attachment fetches a remote Gist
script, compiles it with `loadstring`, and calls it. That remote MIDI payload was
not attached, fetched, executed, or recovered.

The pinned upstream engine first returned a partial register VM (`RK threshold
unresolvable`). null's separate static refinement is **restricted to the exact
reviewed input SHA-256**. It reconstructs four constants and all twelve instructions,
checks the known control-flow sequence and preserves multret forwarding. This is
not a claim of general register-VM support. The normal CLI and web worker both
apply the refinement for that exact file when the trusted AST tool is available.

A syntax-valid result is not a certificate of runtime equivalence. Details and hashes:
[`RoMidiYessirAp.analysis.json`](output/recovered/RoMidiYessirAp.analysis.json).

CLI recovery:

```bash
python3 start.py "/path/to/RoMidiYessirAp.txt" --engine clyde -o "output/local/RoMidiYessirAp.recovered.lua"
```

Raw pinned Clyde adapter (may return only a partial layer; no refinement):

```bash
node clyde_cli.js "/path/to/RoMidiYessirAp.txt" -o "output/RoMidiYessirAp.partial.lua" --report "output/RoMidiYessirAp.report.json"
```

## Credits and verification

Product design, integration, adapter, website and sample refinement: **null**.
Clyde engine: Jamie / OmniDBF, MIT. Required original notices are preserved in
[THIRD_PARTY.md](THIRD_PARTY.md) and `vendor/clyde/LICENSE`.

```bash
.venv/bin/python -B -m unittest discover -s tests -q
```

The browser workflow was exercised against the actual attachment: upload, auto
Clyde detection, live logs, refinement, syntax validation, result preview and download
link, actual loader/report downloads, and static Luraph mapping on the synthetic
fixture. A simulated HTTPS cross-site embedded preview was also exercised through
the real worker. Desktop and 390px mobile rendering were checked; no horizontal overflow or
browser JavaScript exceptions were observed. Codespaces configuration is supplied
but a remote Codespace has not been provisioned/tested in this session.
