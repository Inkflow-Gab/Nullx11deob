"""Native, non-executing discovery stage for curried Luraph 15.1 VMs.

This is a front-end for a future semantic lifter, NOT a full 15.1 decoder.
It uses this repository's AST/dispatcher implementation, not a downloaded
engine. A layout match never authorizes guessing register values or skipping
an unsupported instruction. JSON contains locations/names, not source bodies
or decoded string constants.

python inspect15_1.py decoded.lua --output decoded.vm-map.json
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from obfuscators.luraph_v15 import vmmap


def nodes(root):
    pending = [root]
    while pending:
        node = pending.pop()
        if isinstance(node, dict):
            yield node
            pending.extend(node.values())
        elif isinstance(node, list):
            pending.extend(node)


def returned_function(fn):
    """Resolve only a literal or uniquely bound local tail-returned function."""
    body = fn.get('body', {}).get('body', [])
    if not body or body[-1].get('type') != 'AstStatReturn':
        return None
    values = body[-1].get('list', [])
    if len(values) != 1:
        return None
    value = vmmap.unwrap(values[0])
    if value.get('type') == 'AstExprFunction':
        return value
    if value.get('type') != 'AstExprLocal':
        return None
    decl = value['local']['location']
    candidates = []
    # Stop at direct statements: a branch/loop assignment is not a proven
    # binding and a same-spelling local in another scope is not this local.
    for stat in body[:-1]:
        if stat.get('type') == 'AstStatLocalFunction' and stat['name']['location'] == decl:
            candidates.append(stat['func'])
        elif stat.get('type') == 'AstStatLocal':
            for i, var in enumerate(stat['vars']):
                if var['location'] == decl:
                    candidates.append(stat['values'][i] if i < len(stat['values']) else {})
        # Any later write to the binding invalidates a simple declaration.
        for sub in nodes(stat):
            if sub.get('type') in ('AstStatAssign', 'AstStatCompoundAssign'):
                targets = sub.get('vars', [sub.get('var', {})])
                if any(vmmap.unwrap(v).get('type') == 'AstExprLocal' and
                       vmmap.unwrap(v)['local']['location'] == decl for v in targets):
                    return None
    if len(candidates) == 1 and vmmap.unwrap(candidates[0]).get('type') == 'AstExprFunction':
        return vmmap.unwrap(candidates[0])
    return None


def free_bindings(vm, factory, binder):
    """Report exact declaration identities; never merge locals by spelling."""
    own = set()
    for node in nodes(vm):
        if node.get('type') == 'AstExprFunction':
            own.update(vmmap._decls_in(node))
    available = {}
    for scope, fn in [('factory', factory), ('binder', binder)]:
        for decl, name in vmmap._decls_in(fn).items():
            available[decl] = (scope, name)
    used = {}
    for node in nodes(vm):
        if node.get('type') != 'AstExprLocal':
            continue
        local = node['local']
        decl = local['location']
        if decl in own:
            continue
        scope, name = available.get(decl, ('enclosing', local['name']))
        used[decl] = {'name': name, 'declaration': decl, 'scope': scope}
    return sorted(used.values(), key=lambda item: vmmap.loc({'location': item['declaration']}))


def discover(root):
    dispatchers = vmmap.find_dispatchers(root)
    by_loop = {id(d['node']): i for i, d in enumerate(dispatchers)}
    groups = {}
    pending = [(root, ())]
    while pending:
        node, stack = pending.pop()
        if isinstance(node, dict):
            if node.get('type') == 'AstExprFunction':
                stack += (node,)
            if id(node) in by_loop:
                for i in range(len(stack) - 3, -1, -1):
                    factory, binder, vm = stack[i:i + 3]
                    if returned_function(factory) is not binder or returned_function(binder) is not vm:
                        continue
                    key = (factory['location'], binder['location'], vm['location'])
                    if key not in groups:
                        groups[key] = {'factory': factory, 'binder': binder, 'vm': vm, 'dispatchers': []}
                    groups[key]['dispatchers'].append(by_loop[id(node)])
                    # Nearest proven triple, not arbitrary deeper callbacks.
                    break
            pending.extend((value, stack) for value in node.values() if isinstance(value, (dict, list)))
        elif isinstance(node, list):
            pending.extend((value, stack) for value in node)
    return dispatchers, sorted(groups.values(), key=lambda g: vmmap.loc(g['factory']))


def build_report(source, root, *, max_opcode=255):
    if not 0 <= max_opcode <= 65535:
        raise ValueError('max opcode must be between 0 and 65535')
    dispatchers, groups = discover(root)
    loops = []
    for i, disp in enumerate(dispatchers):
        handlers = vmmap.handler_map(disp, [], max_opcode + 1)
        mapped = {op for item in handlers.values() for op in item['ops']}
        loops.append({
            'id': i, 'location': disp['node']['location'], 'opcode_local': disp['op'],
            'opcode_declaration': disp['op_decl'], 'instruction_array': disp['arr'],
            'program_counter': disp['pc'],
            'no_handler_opcodes': sorted(set(range(max_opcode + 1)) - mapped),
            'handler_regions': [{'opcodes': item['ops'], 'location': item['node']['location']}
                                for item in handlers.values()],
        })
    factories = []
    for group in groups:
        factory, binder, vm = (group[k] for k in ('factory', 'binder', 'vm'))
        factories.append({
            'factory_location': factory['location'], 'binder_location': binder['location'],
            'vm_location': vm['location'], 'dispatchers': sorted(set(group['dispatchers'])),
            'factory_parameters': [{'name': a['name'], 'declaration': a['location']} for a in factory['args']],
            'binder_parameters': [{'name': a['name'], 'declaration': a['location']} for a in binder['args']],
            'free_bindings': free_bindings(vm, factory, binder),
        })
    covered = {i for group in factories for i in group['dispatchers']}
    return {
        'schema_version': 1, 'owner': 'null', 'stage': 'static_vm_discovery',
        'source_sha256': hashlib.sha256(source).hexdigest(), 'source_bytes': len(source),
        'source_executed': False, 'full_devirtualization': False,
        'opcode_range': [0, max_opcode], 'location_convention': 'zero-based line,byte-column; end exclusive',
        'dispatcher_count': len(loops), 'curried_factory_count': len(factories),
        'unattributed_dispatchers': [i for i in range(len(loops)) if i not in covered],
        'dispatchers': loops, 'curried_factories': factories,
        'limitations': [
            'Region maps are static opcode-to-source routing, not decoded bytecode or recovered control flow.',
            'Unattributed loops may be another VM layout or ordinary application code.',
            'Only the requested opcode range is enumerated; no fixed opcode meanings are assumed.',
            'Runtime capture, prototype/closure identity, lazy constants, register semantics and semantic validation remain required.',
        ],
    }


def inspect_path(path, *, max_opcode=255):
    path = Path(path)
    before = path.read_bytes()
    root = vmmap.load_ast(str(path))
    if path.read_bytes() != before:
        raise ValueError('input changed during AST analysis')
    return build_report(before, root, max_opcode=max_opcode)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('-o', '--output', type=Path, help='new JSON file; existing files are never overwritten')
    parser.add_argument('--max-opcode', type=int, default=255)
    args = parser.parse_args(argv)
    try:
        report = inspect_path(args.source, max_opcode=args.max_opcode)
        text = json.dumps(report, indent=2) + '\n'
        if args.output:
            if args.output.resolve() == args.source.resolve():
                raise ValueError('output must not replace the input')
            if args.output.suffix.lower() != '.json':
                raise ValueError('static analysis output must use .json, not .lua')
            args.output.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive creation is deliberately no-clobber, even on shared
            # storage. Remove only our own partial file if the write fails.
            fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            identity = os.fstat(fd)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as out:
                    out.write(text)
            except BaseException:
                try:
                    current = args.output.stat()
                    if (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino):
                        args.output.unlink()
                except FileNotFoundError:
                    pass
                raise
            print('Saved static VM map: %s (%d dispatchers, %d curried factories; NOT full devirtualization)' %
                  (args.output, report['dispatcher_count'], report['curried_factory_count']))
        else:
            print(text, end='')
        return 0
    except (OSError, ValueError, SyntaxError) as exc:
        print('VM inspection failed: %s' % exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    import backend
    sys.exit(backend.run_big_stack(main))
