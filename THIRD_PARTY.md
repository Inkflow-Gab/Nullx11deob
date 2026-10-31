# Third-party notices

Project design, integration, launcher, web worker, native discovery work, and
sample-scoped Clyde refinement: **null**. This does not reassign upstream authorship.

## Clyde static engine

- Repository: https://github.com/JamiesNolandGiggleShi1er/ClydeDeobfuscator
- Pinned commit: `871020866fb425bd8d290ac10dca0a7129f36ce7`
- Author attribution: Jamie / @_jmi. / OmniDBF; copyright 2026 JamiesNolandGiggleShi1er.
- License: MIT; full original notice retained in [`vendor/clyde/LICENSE`](vendor/clyde/LICENSE).
- `vendor/clyde/clyde_static_deob.js` and `vendor/clyde/clyde/*.js` are unchanged copies
  of the reviewed source at that commit. There are no npm runtime dependencies.
- The original README and engine output credit are retained. `clyde_cli.js` is null's
  adapter, not a claim that null authored the upstream engine.
- `docs/clyde-worker.js` is a generated browser bundle of that same source, with
  a local empty `process.env` shim and null's separate worker adapter. Source and
  license comments are retained; `docs/Clyde-LICENSE.txt` carries the full license.
- `clyde_refine.py` is null's separate, exact-input-hash-gated static refinement for
  `RoMidiYessirAp.txt`. It is not general Clyde register-VM support.

The existing Luraph framework retains its upstream technical documentation and
credits under `Deobfuscator/`. Product branding is null; existing licenses and
copyright notices must not be removed from redistributed source.
