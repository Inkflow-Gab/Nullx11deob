# Native 15.1 development — discovery stage

Maintainer: **null**. Date: **2026-10-31**.

## What is implemented

This repository now has its **own static 15.1 front-end**, `Deobfuscator/deobf/obfuscators/luraph_v15/inspect15_1.py`, accessible through `start.py --inspect-vm`. It uses the local source-built Luau parser and the project's dispatcher mapper. It does not download or execute another deobfuscator.

Implemented and tested:

- Detect anonymous `factory -> binder -> VM closure` returns.
- Detect locally named returned functions and protected-call callbacks nested inside the VM closure.
- Enumerate exact free-variable **declaration identities**, preserving duplicate/shadowed parameter distinctions rather than merging names.
- Route opcode values through direct comparisons, parenthesized comparisons, and pure boolean-local dispatch conditions.
- Stop routing when an unknown condition, side-effect prefix, or trailing statement would otherwise lose semantics.
- Exclude the application's multi-value merge loop that the public candidate counted as an extra dispatcher.
- Export a source-hashed JSON map without executing the inspected Lua, including source locations, opcode regions, factory parameters, and required capture bindings. Existing outputs are never overwritten. Opcode values with no matching source branch are recorded explicitly in `no_handler_opcodes`, not silently invented.
- Avoid legacy mapper crashes on dispatcher functions without the expected vararg/enclosing-maker shape.

**This is stage one, not a working full 15.1 devirtualizer.** No arbitrary opcode meanings, missing values, or closure bindings are guessed. Static routing does not decode runtime-encrypted instruction operands or reconstruct executable control flow.

## Actual result on steal

Input attachment: `steal.lua.txt`, SHA-256 `67eeb8e868287746c10c2391a44785905e23e9a2843d7697a628a4ad060993b8`.

The published [`steal.vm-map.json`](steal.vm-map.json) was built from the preserved decoded chunk [`steal.partial-decoded.lua`](steal.partial-decoded.lua), SHA-256 `c198d8df2672e4f000c748818d6f624daadb593bf6ee3583841ab9d0d08ccdba`:

| Native discovery result | Count |
| --- | ---: |
| Opcode-dispatch loops | 8 |
| Curried VM factories | 2 |
| Dispatch modes/loops per factory | 4 and 4 |
| Exact free bindings per VM closure | 34 and 34 |
| Dispatchers unassigned to those factories | 0 |

The previously reported public-candidate **ninth** dispatcher is not another VM: in the formatted chunk at zero-based line 20,858 it is an application merge loop with two RHS expressions. This corrects the interpretation of the earlier 9-versus-8 comparison; merely finding more loops did not demonstrate better VM recognition.

The updated compatibility engine was also actually rerun on the original attachment, using a clean child-process environment and locally source-built Luau 0.739. It decoded the same 948,746-byte nested chunk, but still hit its endless-loop watchdog and captured **zero VM prototypes**. It explicitly returned a partial trace, not a devirtualized program. That trace did not replace the better published partial chunk. Raw captures/logs remain ignored.

**Full recovery is still not achieved.** The existing `steal.partial-decoded.lua` and `StealB.deobfuscated.lua` are unchanged. Neither the opcode map nor the passing test suite certifies that `steal` works.

## Use the native front-end

Run setup first if the AST tool is missing. For a fresh, non-existing report path:

```bash
python3 start.py output/recovered/steal.partial-decoded.lua --inspect-vm -o output/local/steal.vm-map.json
```

On Termux:

```bash
python start.py output/recovered/steal.partial-decoded.lua --inspect-vm -o output/local/steal.vm-map.json
```

To inspect your own decoded chunk:

```bash
python3 start.py "/path/to/decoded.lua" --inspect-vm -o "output/local/my-sample.vm-map.json"
```

To print a bounded opcode map directly without writing a file:

```bash
.venv/bin/python -B Deobfuscator/deobf/obfuscators/luraph_v15/inspect15_1.py output/recovered/steal.partial-decoded.lua --max-opcode 255
```

The inspected source is **not executed**. It must already contain the decoded VM source; this command does not unpack an encrypted outer loader. Report locations refer to the exact file hash recorded in the report, use zero-based line/byte-column coordinates, and have exclusive end positions.

## Remaining implementation, in dependency order

1. **Capture contract:** use the two proven factory/binder layouts to give each prototype and resulting closure a stable identity and capture the 34 exact bindings. The old `(VM object, prototype, upvalues)` maker assumption does not fit these factories. Instrumentation must be validated for collisions, reentrancy, and stack-layout effects before accepting captures.
2. **Closure construction:** reconstruct both lexical scopes and preserve by-reference upvalues, including children created only on unobserved paths. Do not substitute `nil` for an unresolved capture.
3. **Instruction decoding:** resolve lazy constants and in-place instruction mutations against path-sensitive state; propagate registers, varargs, mode switches, and exceptional returns.
4. **Semantic lifting and validation:** prove convergence of the reachable instruction graph, reject unresolved edges/stubs, structure real control flow, validate syntax, and compare behavior on original synthetic fixtures. Only then attempt to replace the sample's published partial result.

## Regression tests

**116 tests passed**, including 22 new front-end regressions. The original synthetic fixture covers anonymous/named currying, duplicate parameter names, a protected-call callback, opcode regions, and an ordinary application loop that must be excluded. Its known behavior was checked in Luau. Other tests ensure inspection does not execute a top-level `error`, does not clobber files, does not label JSON as recovered Lua, and recognizes the real published chunk's eight loops/two factories.

```bash
.venv/bin/python -B -m unittest discover -s tests -q
```
