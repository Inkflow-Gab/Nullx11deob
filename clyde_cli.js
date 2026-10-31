#!/usr/bin/env node
'use strict';
// null integration. The vendored engine and its MIT attribution are unchanged.
const fs = require('fs');
const crypto = require('crypto');
const {detectClyde, deobfuscateClyde} = require('./vendor/clyde/clyde_static_deob.js');
const args = process.argv.slice(2);
const source = args.shift();
function option(name) { const i = args.indexOf(name); return i < 0 ? null : args[i + 1]; }
try {
  if (!source) throw Error('Usage: node clyde_cli.js INPUT [-o OUTPUT] [--report JSON] [--detect]');
  const limit = 8 * 1024 * 1024;
  const fd = fs.openSync(source, 'r');
  let bytes;
  try {
    const stat = fs.fstatSync(fd);
    if (!stat.isFile()) throw Error('Input must be a regular file.');
    if (stat.size > limit) throw Error('Input exceeds the 8 MiB limit.');
    // Bounded even if a local writer grows the file between stat and read.
    const buffer = Buffer.alloc(Math.min(stat.size + 1, limit + 1));
    let count = 0, read;
    while (count < buffer.length && (read = fs.readSync(fd, buffer, count, buffer.length - count, null))) count += read;
    if (count > limit || count > stat.size) throw Error('Input exceeds the limit or changed while being read.');
    bytes = buffer.subarray(0, count);
  } finally { fs.closeSync(fd); }
  const text = bytes.toString('utf8');
  const detection = detectClyde(text);
  if (args.includes('--detect')) { console.log(JSON.stringify(detection)); process.exit(0); }
  if (!detection.isClyde) throw Error('The supplied file is not recognized as Clyde.');
  const output = option('-o');
  if (!output) throw Error('Supply -o OUTPUT. Existing output is never overwritten.');
  console.log('[detect] Clyde / ' + detection.mode);
  console.log('[decode] Static constant, instruction and control-flow recovery; input is not executed.');
  const result = deobfuscateClyde(text);
  if (!result.success || typeof result.output !== 'string' || !result.output.trim()) {
    throw Error(result.error || 'Engine returned no recovered source.');
  }
  const stats = {...result.stats};
  delete stats.decodedStrings; // Never put recovered secrets in job metadata.
  const partial = stats.outputSize > result.output.length || /peeled/.test(stats.mode || '') || /pending|core lift failed|nested failed|cipher failed/i.test(stats.note || '');
  const banner = '-- null • Clyde recovery\n-- Static recovery; syntax and behavior require independent validation.\n' +
    (partial ? '-- PARTIAL: a VM/protection layer remains. Not a fully deobfuscated program.\n' : '');
  const recovered = banner + result.output + '\n';
  const metadata = {
    owner: 'null', engine: 'clyde', upstream: 'JamiesNolandGiggleShi1er/ClydeDeobfuscator',
    upstream_commit: '871020866fb425bd8d290ac10dca0a7129f36ce7',
    input_sha256: crypto.createHash('sha256').update(bytes).digest('hex'),
    output_sha256: crypto.createHash('sha256').update(recovered).digest('hex'),
    input_bytes: bytes.length, output_bytes: Buffer.byteLength(recovered),
    status: partial ? 'partial' : 'recovered_unverified', syntax_valid: null,
    source_executed: false, recovered_output_executed: false, behavioral_equivalence_verified: false, stats
  };
  fs.writeFileSync(output, recovered, {flag: 'wx'});
  if (option('--report')) fs.writeFileSync(option('--report'), JSON.stringify(metadata, null, 2) + '\n', {flag: 'wx'});
  console.log('[result] ' + metadata.status + ' / ' + metadata.output_bytes + ' bytes / mode ' + stats.mode);
  if (stats.note) console.log('[warning] ' + stats.note);
} catch (error) {
  console.error('[error] ' + error.message);
  process.exitCode = 1;
}
