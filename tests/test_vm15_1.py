"""Original 15.1 front-end fixtures: no customer Lua is executed."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import cli

ENGINE = cli.ENGINE_ROOT
spec = importlib.util.spec_from_file_location('null_vmmap_tests', ENGINE / 'obfuscators/luraph_v15/vmmap.py')
vmmap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vmmap)


def local(name, decl='0,0 - 0,1'):
    return {'type': 'AstExprLocal', 'local': {'name': name, 'location': decl}}


def compare(opcode=None):
    return {'type': 'AstExprBinary', 'op': 'CompareLt', 'left': opcode or local('op'),
            'right': {'type': 'AstExprConstantNumber', 'value': 2}}


def boolean_tree(condition=None):
    yes = {'type': 'AstStatBlock', 'location': '3,0 - 3,1', 'body': []}
    no = {'type': 'AstStatBlock', 'location': '4,0 - 4,1', 'body': []}
    branch = {'type': 'AstStatIf', 'condition': condition or local('flag', '1,0 - 1,4'),
              'thenbody': yes, 'elsebody': no}
    block = {'type': 'AstStatBlock', 'body': [
        {'type': 'AstStatLocal', 'vars': [{'name': 'flag', 'location': '1,0 - 1,4'}], 'values': [compare()]},
        branch]}
    return block, yes, no


class DispatcherUnitTests(unittest.TestCase):
    def test_boolean_alias_true_and_false(self):
        tree, yes, no = boolean_tree()
        self.assertIs(vmmap.resolve(tree, 'op', 1), yes)
        self.assertIs(vmmap.resolve(tree, 'op', 2), no)

    def test_parenthesized_comparison(self):
        condition = {'type': 'AstExprGroup', 'expr': compare()}
        self.assertTrue(vmmap.eval_cond(condition, 'op', 1))

    def test_negated_boolean_alias(self):
        tree, yes, no = boolean_tree({'type': 'AstExprUnary', 'op': 'Not', 'expr': local('flag', '1,0 - 1,4')})
        self.assertIs(vmmap.resolve(tree, 'op', 1), no)

    def test_shadowed_boolean_does_not_match_by_name(self):
        tree, _, _ = boolean_tree(local('flag', '9,0 - 9,4'))
        self.assertIs(vmmap.resolve(tree, 'op', 1), tree)

    def test_shadowed_opcode_does_not_match_by_name(self):
        self.assertIsNone(vmmap.eval_cond(compare(local('op', '9,0 - 9,2')), 'op', 1, '0,0 - 0,1'))

    def test_side_effect_prefix_is_not_dropped(self):
        tree, _, _ = boolean_tree()
        tree['body'].insert(0, {'type': 'AstStatExpr', 'expr': {}})
        self.assertIs(vmmap.resolve(tree, 'op', 1), tree)

    def test_trailing_statement_is_not_dropped(self):
        tree, _, _ = boolean_tree()
        tree['body'].append({'type': 'AstStatExpr', 'expr': {}})
        self.assertIs(vmmap.resolve(tree, 'op', 1), tree)

    def test_empty_block_stays_empty(self):
        block = {'type': 'AstStatBlock', 'body': []}
        self.assertIs(vmmap.resolve(block, 'op', 0), block)

    def test_inspection_mode_rejects_trace_or_no_input(self):
        for args in (['--inspect-vm'], ['x.lua', '--inspect-vm', '--trace-only'],
                     ['x.lua', '--inspect-vm', '--force']):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                cli.main(args)


@unittest.skipUnless(cli.find_ast(), 'run --setup for native AST regression tests')
class NativeLayoutTests(unittest.TestCase):
    script = ENGINE / 'obfuscators/luraph_v15/inspect15_1.py'
    fixture = Path(__file__).parent / 'fixtures/luraph15_1_synthetic.lua'

    def inspect(self, source=None, *extra):
        result = subprocess.run([sys.executable, '-B', str(self.script), str(source or self.fixture), *extra],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_anonymous_named_and_protected_callback_layouts(self):
        report = self.inspect()
        self.assertEqual(report['dispatcher_count'], 2)
        self.assertEqual(report['curried_factory_count'], 2)
        self.assertEqual(report['unattributed_dispatchers'], [])
        self.assertFalse(report['source_executed'])
        self.assertFalse(report['full_devirtualization'])
        for factory in report['curried_factories']:
            self.assertEqual({(b['name'], b['scope']) for b in factory['free_bindings']},
                             {('code', 'factory'), ('constants', 'factory'), ('upvalues', 'binder')})

    def test_duplicate_parameter_resolves_to_last_declaration(self):
        factory = self.inspect()['curried_factories'][0]
        constants = [p for p in factory['factory_parameters'] if p['name'] == 'constants']
        capture = next(p for p in factory['free_bindings'] if p['name'] == 'constants')
        self.assertEqual(len(constants), 2)
        self.assertEqual(capture['declaration'], constants[-1]['declaration'])

    def test_longer_return_chain_chooses_nearest_factory(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'chain.lua'
            source.write_text('return function(code) return function(B) return function(C) '
                              'return function(...) local pc=1; while true do local op=code[pc]; '
                              'if op<1 then return B else return C end end end end end end')
            factory = self.inspect(source)['curried_factories'][0]
            self.assertEqual(factory['factory_parameters'][0]['name'], 'B')
            self.assertEqual(factory['binder_parameters'][0]['name'], 'C')
            self.assertIn(('code', 'enclosing'), {(b['name'], b['scope']) for b in factory['free_bindings']})

    def test_opcode_ranges_and_regions(self):
        report = self.inspect(None, '--max-opcode', '2')
        regions = report['dispatchers'][0]['handler_regions']
        self.assertEqual(sorted(op for r in regions for op in r['opcodes']), [0, 1, 2])
        self.assertEqual(len(regions), 3)

    def test_application_merge_loop_is_excluded(self):
        report = self.inspect()
        # Fixture has three while loops, only two of which dispatch opcodes.
        self.assertEqual(report['dispatcher_count'], 2)

    def test_no_clobber_even_for_json(self):
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder) / 'existing.json'
            dest.write_text('keep me')
            result = subprocess.run([sys.executable, '-B', str(self.script), str(self.fixture), '-o', str(dest)],
                                    capture_output=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(dest.read_text(), 'keep me')

    def test_json_report_cannot_be_written_as_lua(self):
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder) / 'wrong.lua'
            result = subprocess.run([sys.executable, '-B', str(self.script), str(self.fixture), '-o', str(dest)],
                                    capture_output=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(dest.exists())

    def test_mutable_named_function_is_not_assumed_to_be_a_factory(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'mutated.lua'
            text = self.fixture.read_text().replace('        return bind\n', '        bind = state.replacement\n        return bind\n')
            source.write_text(text)
            report = self.inspect(source)
            self.assertEqual(report['dispatcher_count'], 2)
            self.assertEqual(report['curried_factory_count'], 1)
            self.assertEqual(len(report['unattributed_dispatchers']), 1)

    def test_legacy_hooks_do_not_crash_on_non_vararg_dispatcher(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'plain.lua'
            source.write_text('return function(code, pc) while true do local op=code[pc]; if op<1 then return 1 else return 2 end end end')
            root = vmmap.load_ast(str(source))
            self.assertEqual(vmmap.closure_entries(root), [])
            self.assertEqual(vmmap.maker_info(root), [])

    def test_real_published_chunk_shape(self):
        source = cli.ROOT / 'output/recovered/steal.partial-decoded.lua'
        if not source.is_file():
            self.skipTest('published research artifact not installed')
        report = self.inspect(source)
        self.assertEqual(report['dispatcher_count'], 8)
        self.assertEqual(report['curried_factory_count'], 2)
        self.assertEqual([len(f['dispatchers']) for f in report['curried_factories']], [4, 4])
        self.assertEqual([len(f['free_bindings']) for f in report['curried_factories']], [34, 34])
        self.assertEqual([d['no_handler_opcodes'] for d in report['dispatchers']], [[], [82], [83], [], [], [13], [5], []])
        for d in report['dispatchers']:
            routed = [op for h in d['handler_regions'] for op in h['opcodes']]
            self.assertEqual(sorted(routed + d['no_handler_opcodes']), list(range(256)))

    def test_inspection_does_not_execute_top_level_error(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'not-executed.lua'
            source.write_text('error("inspection must never execute this")\n' + self.fixture.read_text())
            self.assertEqual(self.inspect(source)['curried_factory_count'], 2)

    def test_original_synthetic_fixture_has_known_behavior(self):
        runtime = cli.find_runtime()
        if not runtime:
            self.skipTest('native runtime not installed')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'fixture.luau').write_text(self.fixture.read_text())
            runner = root / 'verify.luau'
            runner.write_text('local f=require("./fixture")\n'
                              'assert(f.anonymous({}, {0,1}, {99}, {42})({})()==42)\n'
                              'assert(f.named({}, {0,1}, {42})({})()==true)\n'
                              'print("original fixture semantics verified")\n')
            result = subprocess.run([runtime, str(runner)], capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('original fixture semantics verified', result.stdout)

    def test_cli_static_mode_works_without_runtime_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder) / 'report.json'
            result = subprocess.run([sys.executable, '-B', str(cli.ROOT / 'start.py'), str(self.fixture),
                                     '--inspect-vm', '-o', str(dest), '--no-color'],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(json.loads(dest.read_text())['curried_factory_count'], 2)
            self.assertIn('not full', result.stdout.lower())


if __name__ == '__main__':
    unittest.main()
