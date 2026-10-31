"""null's SAMPLE-SCOPED static refinement of the attached RoMidi Clyde loader.

This is not general register-VM support. It only accepts the exact reviewed
input SHA-256, reconstructs literal constants/instructions through the local
AST tool, and checks the complete known instruction sequence. Unknown inputs
remain with the upstream engine's honest partial result. No Lua is executed
and the referenced external script is not fetched.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess

SAMPLE_SHA256 = 'c4bebd51d7cbcc3476f2ca770f3b211c9a8f83a0bd1a29da8f5ea953750c2b2a'
EXPECTED_CODE = [21,0,6,0,27,1,3,0,21,0,2,0,27,0,1,1,29,0,1,0,27,0,0,2,21,0,-4,0,5,0,0,0,5,5,1,0,36,1,5,258,1,3,3,0,21,0,-11,0]


def nodes(value):
    pending = [value]
    while pending:
        node = pending.pop()
        if isinstance(node, dict):
            yield node
            pending.extend(node.values())
        elif isinstance(node, list):
            pending.extend(node)


def literal(node):
    kind = node['type']
    if kind in ('AstExprConstantNumber', 'AstExprConstantString', 'AstExprConstantBool'):
        return node['value']
    if kind == 'AstExprUnary' and node['op'] == 'Minus':
        return -literal(node['expr'])
    if kind == 'AstExprTable' and all(item['kind'] == 'item' for item in node['items']):
        return [literal(item['value']) for item in node['items']]
    raise ValueError('Non-literal value in the reviewed constant/instruction table.')


def decode_constants(pool, inverse):
    if sorted(inverse) != list(range(256)):
        raise ValueError('Invalid inverse substitution table.')
    decoded = []
    for index, encoded in enumerate(pool):
        data = list(map(ord, encoded)) if isinstance(encoded, str) else list(encoded)
        if any(not isinstance(x, int) or not 0 <= x <= 255 for x in data):
            raise ValueError('Invalid encoded byte.')
        salt = index & 255
        data = [x ^ ((((j * 127 + 101) % 251) + salt) % 251) for j, x in enumerate(data)]
        data = [x ^ ((30 + salt + (j // 2) * 142) & 255) if j % 2 == 0 else
                x ^ ((58 + salt + (j // 2) * 22) & 255) for j, x in enumerate(data)]
        # Forward, in-place feedback: the previous byte has already decoded.
        for j in range(1, len(data)):
            data[j] ^= (data[j - 1] * 123 + 124 + salt) & 255
        data = [(x - ((91 + salt + j * 235) & 255) + 256) & 255 for j, x in enumerate(data)]
        data = [inverse[x] ^ ((salt + j) & 255) for j, x in enumerate(data)]
        decoded.append(''.join(map(chr, data)))
    return decoded


def decode_code(words):
    permutation = {0:(0,1,2), 1:(2,0,1), 7:(2,1,0), 25:(0,2,1), 33:(0,1,2), 41:(0,1,2), 47:(2,1,0), 53:(2,1,0)}
    opcode = {0:0, 1:21, 7:29, 25:36, 33:5, 41:0, 47:1, 53:27}
    if len(words) % 4:
        raise ValueError('Incomplete instruction.')
    code = []
    for pos in range(0, len(words), 4):
        pc = pos + 1
        # k[pc] ^= old_key ^ new_key on execution, so k[pc] ^ key is
        # invariant on revisits; the initial per-PC key is zero.
        op = words[pos] ^ ((115 + pc * 29 + pc * pc * 112) & 255)
        if op not in opcode:
            raise ValueError('Unknown reviewed opcode.')
        operands = words[pos + 1:pos + 4]
        code.extend([opcode[op], *(operands[i] for i in permutation[op])])
    if code != EXPECTED_CODE:
        raise ValueError('Decoded control flow differs from the reviewed loader.')
    return code


def refine_if_known(source, output, report_path, ast_tool):
    source, output, report_path = map(Path, (source, output, report_path))
    if hashlib.sha256(source.read_bytes()).hexdigest() != SAMPLE_SHA256 or not ast_tool:
        return False
    # Check that the peeled program came from the pinned upstream result.
    report = json.loads(report_path.read_text())
    current = output.read_bytes()
    if hashlib.sha256(current).hexdigest() != report.get('output_sha256') or report.get('stats', {}).get('mode') != 'reg-vm-peeled':
        raise ValueError('Refinement requires the unmodified pinned upstream partial result.')
    parsed = subprocess.run([str(ast_tool), str(output)], capture_output=True, timeout=30)
    if parsed.returncode or b'parse errors' in parsed.stderr.lower():
        raise ValueError('Cannot refine invalid peeled Lua.')
    root = json.loads(parsed.stdout.decode('latin-1'))['root']
    values = {}
    for node in nodes(root):
        if node.get('type') in ('AstExprError', 'AstStatError'):
            raise ValueError('Peeled source contains parse error nodes.')
        if node.get('type') == 'AstStatAssign':
            for index, target in enumerate(node['vars']):
                if target.get('type') == 'AstExprLocal' and target['local']['name'] in ('W', 'X'):
                    value = node['values'][index]
                    if value['type'] == 'AstExprTable':
                        name = target['local']['name']
                        if name in values:
                            raise ValueError('Ambiguous reviewed table binding.')
                        values[name] = literal(value)
        elif node.get('type') == 'AstStatLocal' and node['vars'][0]['name'] == '_0inv':
            values['inverse'] = literal(node['values'][0])
    constants = decode_constants(values['W'], values['inverse'])
    instructions = decode_code(values['X'])
    if len(constants) != 4 or constants[:3] != ['loadstring', 'game', 'HttpGet'] or not constants[3].startswith('https://gist.githubusercontent.com/'):
        raise ValueError('Decoded constants differ from the reviewed loader shape.')
    # The path through all 12 instructions is 0,7,8,9,10,11,1,2,5,6,3,4.
    # Preserve global capture order, SELF's explicit receiver, and multret
    # forwarding from HttpGet to loadstring. No external content is fetched.
    code = ('-- null • RoMidi Clyde loader recovery\n'
            '-- Derived statically from the attached file; the recovered code was NOT executed.\n'
            '-- This is the loader only. The external MIDI payload is NOT included or fetched.\n'
            '-- Clyde engine upstream: JamiesNolandGiggleShi1er/ClydeDeobfuscator (MIT).\n'
            '-- Sample-scoped register-VM refinement: null. Behavior equivalence is not certified.\n\n'
            'local compile = loadstring\n'
            'local service = game\n'
            'local httpGet = service["HttpGet"]\n'
            'local entrypoint = compile(httpGet(service, ' + json.dumps(constants[3]) + '))\n'
            'entrypoint()\n'
            'return\n')
    temporary = output.with_suffix('.refined.tmp')
    temporary.write_text(code, encoding='utf-8')
    os.replace(temporary, output)
    report.update(status='devirtualized_loader_external_payload_not_included',
                  refinement='null / exact reviewed sample SHA-256 only; not general Clyde register-VM support',
                  decoded_constants=len(constants), decoded_instructions=len(instructions) // 4,
                  control_flow_order=[0,7,8,9,10,11,1,2,5,6,3,4],
                  external_payload_fetched=False, external_payload_included=False,
                  output_bytes=output.stat().st_size, output_sha256=hashlib.sha256(output.read_bytes()).hexdigest())
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    return True
