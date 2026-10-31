#!/usr/bin/env python3
"""Build the committed /docs Pages site without npm, eval, or external downloads.

The reviewed CommonJS engine only has literal relative require() calls. Bundle
that closed module graph as ordinary functions; never evaluate uploaded source.
"""
import argparse
from pathlib import Path
import re
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REQUIRE = re.compile(r"\brequire\(['\"]([^'\"]+)['\"]\)")


def bundle():
    modules = {}
    def visit(path):
        path = path.resolve()
        name = path.relative_to(ROOT).as_posix()
        if name in modules:
            return name
        source = path.read_text(encoding='utf-8')
        modules[name] = (source, {})
        for request in REQUIRE.findall(source):
            if not request.startswith('.'):
                raise ValueError('Browser bundle refuses external imports: ' + request)
            modules[name][1][request] = visit(path.parent / request)
        return name
    entry = visit(ROOT / 'web/clyde-worker.js')
    import json
    result = ['// null browser build. Clyde upstream MIT notice: ./Clyde-LICENSE.txt\n',
              "'use strict';\n(() => {\nconst process = {env: Object.freeze({})};\nconst modules = {\n"]
    for name, (source, dependencies) in sorted(modules.items()):
        result.append(json.dumps(name) + ': [function(require, module, exports) {\n' + source + '\n}, ' + json.dumps(dependencies, sort_keys=True) + '],\n')
    result.append('};\nconst cache = Object.create(null);\nfunction load(id) {\nif (cache[id]) return cache[id].exports;\nconst [fn, deps] = modules[id]; const module = cache[id] = {exports: {}};\nfn(name => {if (!Object.prototype.hasOwnProperty.call(deps, name)) throw Error("Unknown module"); return load(deps[name]);}, module, module.exports);\nreturn module.exports;\n}\nload(' + json.dumps(entry) + ');\n})();\n')
    return ''.join(result)


def build(destination):
    destination.mkdir(parents=True, exist_ok=True)
    for name in ('style.css', 'app.js', 'browser-api.js', 'runtime-link.js'):
        shutil.copyfile(ROOT / 'web' / name, destination / name)
    html = (ROOT / 'web/index.html').read_text(encoding='utf-8')
    html = html.replace('<script src="./app.js" defer>', '<script src="./browser-api.js" defer></script><script src="./app.js" defer>')
    csp = "default-src 'self'; script-src 'self'; worker-src 'self'; connect-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'; form-action 'none'"
    html = html.replace('<meta name="description"', f'<meta http-equiv="Content-Security-Policy" content="{csp}"><meta name="description"')
    html = html.replace('Jamie / OmniDBF · MIT', 'Jamie / OmniDBF · <a href="./Clyde-LICENSE.txt">MIT</a>')
    html = html.replace('Session-scoped results', 'Files stay in your browser').replace('No sign-up', 'No uploads')
    html = html.replace('Clyde static recovery + Luraph compatibility and VM analysis.', 'Browser Clyde recovery. Private worker required for Luraph.')
    html = html.replace('Session-owned downloads. Files expire after one hour.', 'Clyde stays local. Luraph transfers only with consent.')
    (destination / 'index.html').write_text(html, encoding='utf-8')
    (destination / 'clyde-worker.js').write_text(bundle(), encoding='utf-8')
    shutil.copyfile(ROOT / 'vendor/clyde/LICENSE', destination / 'Clyde-LICENSE.txt')
    (destination / '.nojekyll').write_text('')
    (destination / 'recovered').mkdir(exist_ok=True)
    for name in ('RoMidiYessirAp.deobfuscated.lua', 'RoMidiYessirAp.analysis.json'):
        shutil.copyfile(ROOT / 'output/recovered' / name, destination / 'recovered' / name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='fail if committed Pages assets are stale')
    args = parser.parse_args()
    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            build(Path(tmp))
            for file in Path(tmp).rglob('*'):
                if file.is_file():
                    target = ROOT / 'docs' / file.relative_to(tmp)
                    if not target.is_file() or target.read_text(encoding='utf-8') != file.read_text(encoding='utf-8'):
                        raise SystemExit('Pages assets stale. Run python3 tools/build_pages.py: ' + str(target))
    else:
        build(ROOT / 'docs')
        print('Built docs/: publish this branch, /docs in Settings → Pages.')


if __name__ == '__main__':
    main()
