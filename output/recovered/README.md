# Requested Lua recovery results

Owner / maintainer: **null**. Analysis date: **2026-10-31**.

These are analysis artifacts from the user-supplied attachments, not trusted scripts. Do not execute them on an account or machine with secrets. Lua syntax validation does not establish safety, completeness, or equivalence.

## Results

| Attachment | Detected banner | Saved artifact | Actual outcome |
| --- | --- | --- | --- |
| `StealB.lua.txt` | Luraph 15.0 | [`StealB.deobfuscated.lua`](StealB.deobfuscated.lua) | Substantial devirtualized source recovered; syntax passed. Engine reported 1,138 functions, zero unlifted blocks, zero unstructured jumps, and no remaining constant requests in its final round. Runtime tracing stopped at `Chilli Library bootstrap is invalid.` The external library was **not** fetched for analysis. Complete runtime behavior was not verified. |
| `steal.lua.txt` | Luraph 15.1 | [`steal.partial-decoded.lua`](steal.partial-decoded.lua) | **Partial static recovery only.** Runtime tracing aborted in an endless-loop/tamper condition and captured **zero** VM prototypes. A 948,746-byte runtime-loaded chunk was decoded by the harness; that chunk was extracted and formatted without executing the recovered file. It contains readable functions **and a remaining VM wrapper**. Syntax passed. This is not a fully devirtualized original program. |
| `RoMidiYessirAp.txt` | Clyde register VM | [`RoMidiYessirAp.deobfuscated.lua`](RoMidiYessirAp.deobfuscated.lua) | **Loader recovered, external payload not included.** Pinned upstream peeled a partial VM. null's exact-sample static refinement decoded four constants/all twelve instructions and reconstructed the main loader. Syntax passed; neither input nor recovered output was executed. The external Gist MIDI implementation was not supplied, fetched or recovered. Behavioral equivalence is not certified. |

The first v15.1 attempt produced only comments. That file is deliberately **not** presented here as `steal.deobfuscated.lua`; the useful extracted chunk is labeled `partial-decoded` instead. The v15 engine was also corrected to fall back to its partial behavior trace rather than claiming a zero-prototype lift is useful devirtualization.

## RoMidi / Clyde provenance

- Input: 34,313 bytes, SHA-256 `c4bebd51d7cbcc3476f2ca770f3b211c9a8f83a0bd1a29da8f5ea953750c2b2a`.
- Recovered loader: 605 bytes, SHA-256 `e0fc1a2b9431c9cbb8e79abff8448ae58fa601df8593d64f45fc6c30b29b95c1`.
- [Machine-readable report](RoMidiYessirAp.analysis.json) / [web and reproduction guide](../../WEB.md).
- Scope is the main loader, with VM/protection checks removed. The separate original
  `clyde_refine.py` pass is hash-gated to this reviewed attachment, not general register-VM support.
- Clyde upstream MIT attribution is retained in `vendor/clyde/LICENSE`; null owns
  the integration/design/refinement, not the upstream engine's authorship.
- Existing StealB and steal Lua artifacts are unchanged by this addition.

## Follow-up: public v15.1 tools and StealB completeness

See [`research-15.1.md`](research-15.1.md). A source-reviewed public v15.1 candidate was tested with two separately source-built runtimes. It got further than the current engine, but neither attempt produced correct full recovery. Broken output was deliberately not promoted to a successful decode.

The latest focused investigation is recorded in [`steal.blockers.json`](steal.blockers.json). A fresh live reconstruction still reported 11 unlifted blocks; independent AST inspection found 44 actual `nil` calls, 13 emitted devirtualization-error sites, and six unresolved runtime-function stubs. An experimental cross-instruction numeric-state repair did not resolve these failures. The published partial Lua file is unchanged; **no fully working `steal.deobfuscated.lua` has been recovered**.

`StealB` has clean reconstruction counters and no obvious unresolved-marker/`nil`-call artifacts in the follow-up scan. That still does **not** prove full behavioral equivalence or include its externally loaded libraries.

## Native 15.1 engine development

See [`native-15.1.md`](native-15.1.md) for the new native static front-end, tested against the sample. It correctly maps eight dispatch loops to two curried factories and resolves 34 exact free bindings per VM closure. The source-hashed [`steal.vm-map.json`](steal.vm-map.json) is **analysis data, not recovered executable Lua**. The original attachment was rerun with the updated mapper; prototype capture still failed, so no replacement full decode is claimed.

## Credential handling

One embedded Discord webhook URL/token in `StealB` was replaced with:

```text
https://discord.com/api/webhooks/REDACTED/REDACTED
```

The repository-facing source has a redaction notice. This intentional edit changes that endpoint's behavior; do not describe the published artifact as byte-for-byte equivalent to the original. The decoded v15.1 chunk had no literal webhook URL matching that pattern. A limited literal scan also found no GitHub token, AWS access-key ID, or private-key header in the published Lua files; this is not a comprehensive secret audit.

Raw uploads, unredacted working copies, trace/prototype dumps, AST JSON, and verbose logs are intentionally excluded from Git. No runtime execution of the final recovered artifacts was performed. Analysis used the existing emulated Luau harness with a reduced child-process environment; an emulated runtime is **not** an OS-level security boundary.

## Provenance

- `StealB.lua.txt`: 1,067,422 bytes; SHA-256 `76c791a91561b1cd8c8971bae786b393833315317b80bdb72443465dd12cb190`.
- `steal.lua.txt`: 636,457 bytes; SHA-256 `67eeb8e868287746c10c2391a44785905e23e9a2843d7697a628a4ad060993b8`.
- The v15.0 launcher run took approximately 217 seconds in this Linux environment.
- The v15.1 initial launcher run took approximately 21 seconds before reporting the endless-loop condition. A separate debug run exposed the decoded runtime chunk for static formatting.
- See [`analysis.json`](analysis.json) for artifact hashes, sizes, redaction counts, and status fields.

## Reproduce with your own copies

From the repository root after setup, replace each input path with the location of your attachment. These inputs are intentionally not included in Git.

```bash
.venv/bin/python cli.py "/path/to/StealB.lua.txt" -o "output/local/StealB.recovered.lua" --job-timeout 1800
```

For diagnostics on the v15.1 input (this **does not guarantee successful devirtualization**):

```bash
.venv/bin/python Deobfuscator/deobf/deob.py "/path/to/steal.lua.txt" --obfuscator luraph_v15 --debug --no-pypy -o "output/local/steal.trace.luau"
```

Debug mode can expose sensitive decoded constants. Review/redact before sharing any files. Never use recovered endpoints, bypass licensing/tamper checks, or enable unauthorized actions against a third-party service.
