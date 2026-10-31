# null — web recovery workspace

Minimal HTML, CSS, and vanilla JavaScript in two editions: browser-only GitHub
Pages for static Clyde, and a Python server for private Luraph/Clyde work.
No CDN, analytics, npm runtime dependency, or third-party upload API.

## GitHub Pages — github.io

Expected site URL after enabling hosting:
**https://inkflow-gab.github.io/Nullx11deob/**

The ready-to-publish site is committed under `docs/`. It runs the pinned Clyde
engine in a dedicated browser Web Worker, without Node, Python, backend requests,
or uploading your input. It provides automatic signature detection, actual worker
logs, a 180-second timeout, cancellation, source preview, local file/report downloads,
and the same responsive light/dark interface.

### One-time activation

The current GitHub connection returned **403 Resource not accessible by integration**
when asked to enable Pages. Hosting could not be activated automatically. Either
reconnect GitHub in Arena with Pages administration permission, or use the repository
settings directly (no token/password is needed in chat):

1. Open [Settings → Pages](https://github.com/Inkflow-Gab/Nullx11deob/settings/pages).
2. Set **Source → Deploy from a branch**.
3. Choose branch **`arena/247512c5-nullx11deob`**, folder **`/docs`**.
4. Click **Save**, then wait for GitHub's Pages deployment to finish. GitHub will
   show the live URL. Until enabled and deployed, that URL can return 404.

Use this branch, not `main`: these changes are still in the open pull request.
The `.nojekyll` file makes this a plain static deployment. No Codespace needs to
be started for Clyde. Later pushes to this branch's `docs/` redeploy automatically.

### Browser edition limitations

- **Luraph cannot run on Pages.** Detection/version display is available, but its
  recovery button is disabled. Use **Launch** for the private Codespaces worker.
- No browser Luau AST tool is bundled: syntax and behavior are **not checked** in
  the browser. Unsupported/peeled VM layers are labeled partial.
- For the exact RoMidi input hash, the worker can return the previously reviewed,
  hash-verified loader already published in this repository. The log and report
  explicitly mark it as a reference recovery, not a new browser AST refinement.
  The remote MIDI payload is still not fetched or included.
- Input and current results stay in the tab. Closing/reloading discards them;
  downloaded files remain wherever your browser saves them. The worker never
  executes uploaded Lua. GitHub still receives ordinary requests for public
  site assets and may retain standard hosting access logs.
- File limit 8 MiB, output limit 16 MiB; only the current result is retained.
  A large input can exceed browser memory despite these bounds. Cancellation
  terminates the worker. Logs have the same 256 KB / 4,000-line cap.

### Rebuild after editing source

The generated worker is a closed CommonJS module graph compiled as ordinary
functions: no `eval`, no dynamic uploaded JavaScript/Lua execution, no npm build
download. Clyde copyright/license comments are retained, with the full MIT notice
in `docs/Clyde-LICENSE.txt`. Only the public reviewed loader/report are copied as
reference assets; raw uploads and private job directories are not published.

```bash
python3 tools/build_pages.py
```

```bash
python3 tools/build_pages.py --check
```

Commit the generated `docs/` changes along with the source changes. CI checks
that the committed static build is current. Preview locally without any backend:

```bash
python3 -m http.server 8090 --bind 0.0.0.0 --directory docs
```

Open `http://localhost:8090`. The Pages edition uses relative asset URLs, including
inside a project subpath such as `/Nullx11deob/`; it never calls `/api` on github.io.

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

The server edition in `web/` uses same-origin `/api` endpoints. Do not publish
`web/` directly as a Pages site: use the built `docs/` edition instead. Pages runs
Clyde in a browser worker; Python/native Luraph still requires this private server.

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
