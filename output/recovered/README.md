# Requested Lua recovery results

Owner / maintainer: **null**. Analysis date: **2026-10-31**.

These are analysis artifacts from the two user-supplied attachments, not trusted scripts. Do not execute them on an account or machine with secrets. Lua syntax validation does not establish safety, completeness, or equivalence.

## Results

| Attachment | Detected banner | Saved artifact | Actual outcome |
| --- | --- | --- | --- |
| `StealB.lua.txt` | Luraph 15.0 | [`StealB.deobfuscated.lua`](StealB.deobfuscated.lua) | Substantial devirtualized source recovered; syntax passed. Engine reported 1,138 functions, zero unlifted blocks, zero unstructured jumps, and no remaining constant requests in its final round. Runtime tracing stopped at `Chilli Library bootstrap is invalid.` The external library was **not** fetched for analysis. Complete runtime behavior was not verified. |
| `steal.lua.txt` | Luraph 15.1 | [`steal.partial-decoded.lua`](steal.partial-decoded.lua) | **Partial static recovery only.** Runtime tracing aborted in an endless-loop/tamper condition and captured **zero** VM prototypes. A 948,746-byte runtime-loaded chunk was decoded by the harness; that chunk was extracted and formatted without executing the recovered file. It contains readable functions **and a remaining VM wrapper**. Syntax passed. This is not a fully devirtualized original program. |

The first v15.1 attempt produced only comments. That file is deliberately **not** presented here as `steal.deobfuscated.lua`; the useful extracted chunk is labeled `partial-decoded` instead. The v15 engine was also corrected to fall back to its partial behavior trace rather than claiming a zero-prototype lift is useful devirtualization.

## Follow-up: public v15.1 tools and StealB completeness

See [`research-15.1.md`](research-15.1.md). A source-reviewed public v15.1 candidate was tested with two separately source-built runtimes. It got further than the current engine, but neither attempt produced correct full recovery. Broken output was deliberately not promoted to a successful decode.

`StealB` has clean reconstruction counters and no obvious unresolved-marker/`nil`-call artifacts in the follow-up scan. That still does **not** prove full behavioral equivalence or include its externally loaded libraries.

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
