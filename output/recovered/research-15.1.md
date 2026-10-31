# Luraph 15.1 follow-up: actual tests, not a support claim

Date: 2026-10-31. Maintainer: **null**.

## Answer

The supplied `steal.lua.txt` is **still not fully devirtualized**. The original engine failed to capture its VM prototypes. A newer public candidate got further, but both tested configurations produced incomplete/broken reconstruction. The existing `steal.partial-decoded.lua` remains the useful, syntax-checked **partial** decoded chunk; it has not been replaced with a falsely labeled successful decode.

A v15.1 header is evidence of the producer version, not proof that any tool recognizing the header supports that file's layout. The CLI now calls v15.1 matching **experimental v15 compatibility** and prints a warning rather than implying verified full support.

## Public references inspected

1. [ludicious-claw/Deobfuscator-Luraph-V15-1](https://github.com/ludicious-claw/Deobfuscator-Luraph-V15-1), examined at commit [`d78c335d96cce5ae3551c88e4a9857a40ab2c62b`](https://github.com/ludicious-claw/Deobfuscator-Luraph-V15-1/tree/d78c335d96cce5ae3551c88e4a9857a40ab2c62b). MIT-licensed source; advertises v15/v15.1. It includes boolean-local dispatcher recognition, additional closure-maker/currying handling, and a stack-ceiling compatibility runtime patch. These source differences were inspected rather than assuming the README promise was sufficient.
2. [mehCake/luraph-deobfuscator-py](https://github.com/mehCake/luraph-deobfuscator-py): its inspected root contained README/license material, not a runnable public decoder implementation.
3. [mehCake/Luraph-V15.1-V15-Deobfuscator](https://github.com/mehCake/Luraph-V15.1-V15-Deobfuscator): inspected as a support/sample reference, not adopted as an available source engine.
4. [Public v15.1 deobfuscator issue](https://github.com/4fundsagent-source/luau.site/issues/20): describes a v15.1 tool offering. This is a claim/reference, not independent validation of the uploaded sample.

Archive-only downloads and unknown bundled executables were not used. No payment, Discord login, API secret, or external code-download endpoint was supplied to a third party.

## Confirmed layout difference

Static comparison on the same decoded 948,746-byte chunk found:

| Mapper | Dispatchers recognized | Closure makers recognized |
| --- | ---: | ---: |
| Current v15 mapper | 8 | 0 |
| Candidate mapper | 9 | 2 |

This supports a real model/instrumentation mismatch in the existing engine. It does **not** show that the version number is the only issue, nor that the candidate correctly reconstructs all control flow.

**Later correction:** the candidate's ninth detected loop was inspected directly and is an ordinary application merge loop, not an additional VM dispatcher. Our new native discovery stage maps the eight real loops to two curried factories; see [`native-15.1.md`](native-15.1.md). The earlier recognition count remains a historical raw measurement, not evidence of a ninth VM.

## Retry A: candidate source + existing source-built runtime

- The candidate was kept in an ignored research directory; none of its downloaded native binaries was executed.
- Its binary paths were replaced with our locally built Luau 0.739 runtime and AST tool.
- It captured enough VM data to attempt lifting **36 functions**.
- Final lift reported **11 unlifted blocks** and zero additional constant requests.
- The retained debug reconstruction contained **150 calls of `nil`**. Although that debug file parsed, it was not a correct executable recovery.
- The candidate itself rejected that reconstruction and selected its behavior trace instead. Its final trace contained source-position artifacts and did not pass our Lua syntax check.

**Verdict: failed full recovery.** A zero process exit status / JSON `success: true` was not accepted as proof of correct source.

## Retry B: candidate source + its runtime compatibility patch

- Built a separate runtime from the pinned upstream Luau source using the candidate's source patches. The main project's runtime was not overwritten.
- The candidate again reached **36 functions**.
- Its final lift reported **12 unlifted blocks**, with **55 calls of `nil`** in the emitted file.
- Naming/local-function passes reported parse errors. Independent syntax validation also failed.

**Verdict: failed full recovery.** The experimental runtime/source was not installed into the everyday deobfuscator, and the broken output was not published as `steal.deobfuscated.lua`.

## Focused follow-up: closure bindings and cross-instruction state

A fresh source build of Luau 0.739 was used after the local analysis cache was rebuilt. Candidate native binaries were again replaced with trusted local builds before execution. The exact candidate base commit remains unchanged. This was a diagnostic investigation, not evidence of new upstream support.

1. **Fresh live capture:** 36 functions, 11 unlifted blocks, zero final constant requests. The selected reconstruction passed syntax validation, but independent AST inspection found **44 actual calls to `nil`, 13 emitted `devirt:` error sites, and six runtime-function stubs** that raise `Luraph runtime function, not devirtualized`. This is concrete evidence that a parsing file and JSON `success: true` can still be unusable.
2. **Closure-binding probe:** an offline capture walk observed 34 closure render calls without missing register-name bindings. This does not rule out wrong captured values or unobserved closures. The offline walk also had **290 pending constant requests**, so its function/error counts cannot be equated with those of the live, request-enabled lift.
3. **Numeric-state experiment:** a research-only change preserved numeric/boolean prologue locals that handlers both read before writing and write across instructions, excluding known fixed/special/register-file/stack-pointer locals. This tested a possible gap in the candidate's cross-instruction state model. With a bounded 20,000-state walk, the live run still reported **36 functions and 11 unlifted blocks**. Its syntax-valid reconstruction contained **123 AST-confirmed `nil` calls**, 13 emitted error sites, and six runtime-function stubs. The candidate rejected that reconstruction in favor of a trace, which failed independent syntax validation. The change was **not installed in the main engine**.

Remaining emitted failures include symbolic stores into instruction/prototype arrays, corrupt/encrypted register indexes, and a comparison of a missing value against `70`. Removing those checks, replacing `nil` with guessed functions, or deleting error statements would not establish correct recovery.

Counts differ between fresh captures; the earlier 150/55 counts and the latest 44/123 counts describe their respective actual runs, not a controlled proof of improvement or regression. Neither latest run satisfies full recovery.

The credential-free [`steal.blockers.json`](steal.blockers.json) records hashes, parser results, exact error-marker messages, and AST call-site locations. Experimental Lua and raw captures remain excluded from Git. Both published Lua artifacts were independently syntax-checked again and their hashes are unchanged.

**Outcome: full recovery still not achieved.** The existing `steal.partial-decoded.lua` was preserved rather than replaced by a broken reconstruction.

## What about StealB?

`StealB.deobfuscated.lua` still passes syntax validation. Its original successful run reported **1,138 functions, zero unlifted blocks, zero unstructured jumps**, and zero remaining constant requests. A follow-up literal scan found:

- zero `devirt:` / unexplored-successor diagnostic markers;
- zero `(nil)(` calls;
- zero `LPH_` or `__PROTOS` markers;
- two `loadstring(` calls, which are not by themselves evidence of remaining VM protection (the recovered program uses external library loading).

That is strong evidence of substantial VM reconstruction, **not a certificate that every original behavior/string/library has been recovered**. The runtime stopped at `Chilli Library bootstrap is invalid.` External libraries were not downloaded to make the program run, original local names are not recoverable, and one webhook credential is intentionally redacted. Behavioral equivalence has not been proved.

## Reproducibility and safety

Verbose logs, downloaded candidate source, prototype dumps, decoded constants, and experimental binaries remain ignored locally. They are not automatically downloaded by setup, nor used by `start.py`.

The useful published outputs and hashes remain listed in `analysis.json`. Their syntax was checked without executing the final recovered artifacts. The tracing harness uses emulation, not an OS security boundary; use a disposable isolated environment for untrusted scripts.

Further work requires correct modeling of this sample's additional closure/dispatcher/register behavior and regression fixtures—not simply changing a version string or weakening output validation.
