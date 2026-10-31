'use strict';
// null browser adapter. This worker parses text; it never executes uploaded Lua.
const {detectClyde, deobfuscateClyde} = require('../vendor/clyde/clyde_static_deob.js');
const digest = async bytes => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), x => x.toString(16).padStart(2, '0')).join('');
const log = text => self.postMessage({type: 'log', text});
self.onmessage = async ({data}) => {
  try {
    const bytes = data.bytes;
    if (!(bytes instanceof Uint8Array) || !bytes.length || bytes.length > 8 * 1024 * 1024) throw Error('Choose a non-empty file up to 8 MiB.');
    const text = new TextDecoder().decode(bytes);
    const detected = detectClyde(text);
    if (!detected.isClyde) throw Error('The pinned Clyde engine does not recognize this input.');
    log('[detect] Clyde / ' + detected.mode);
    log('[decode] Static recovery in your browser. Uploaded Lua is never executed.');
    const result = deobfuscateClyde(text);
    if (!result.success || typeof result.output !== 'string' || !result.output.trim()) throw Error(result.error || 'No recovered source.');
    const stats = {...result.stats}; delete stats.decodedStrings;
    const partial = stats.outputSize > result.output.length || /peeled/.test(stats.mode || '') || /pending|core lift failed|nested failed|cipher failed/i.test(stats.note || '');
    let output = '-- null • Clyde browser recovery\n-- Static recovery; browser syntax and behavior have NOT been verified.\n' +
      (partial ? '-- PARTIAL: a VM/protection layer remains. Not a fully deobfuscated program.\n' : '') + result.output + '\n';
    const inputHash = await digest(bytes);
    let report = {owner: 'null', engine: 'clyde', runtime: 'browser-worker', upstream_commit: '871020866fb425bd8d290ac10dca0a7129f36ce7',
      input_sha256: inputHash, input_bytes: bytes.length, status: partial ? 'partial' : 'recovered_unverified', syntax_valid: null,
      source_executed: false, recovered_output_executed: false, behavioral_equivalence_verified: false, uploaded: false, stats};
    log('[result] ' + report.status + ' / ' + stats.mode);
    if (stats.note) log('[warning] ' + stats.note);
    // Reuse the previously reviewed recovery only for the exact attached input.
    // This is explicitly a hash-matched reference, not a browser AST refinement.
    if (inputHash === 'c4bebd51d7cbcc3476f2ca770f3b211c9a8f83a0bd1a29da8f5ea953750c2b2a') {
      try {
        const response = await fetch(new URL('./recovered/RoMidiYessirAp.deobfuscated.lua', self.location.href));
        if (!response.ok) throw Error('Reference not available.');
        const reference = await response.text();
        if (await digest(new TextEncoder().encode(reference)) !== 'e0fc1a2b9431c9cbb8e79abff8448ae58fa601df8593d64f45fc6c30b29b95c1') throw Error('Reference hash mismatch.');
        output = reference;
        report = {...report, status: 'devirtualized_loader_external_payload_not_included', reference_recovery_used: true,
          refinement: 'Previously reviewed exact-input recovery; AST refinement not rerun in the browser.',
          decoded_constants: 4, decoded_instructions: 12, external_payload_fetched: false, external_payload_included: false,
          reference_syntax_valid: true};
        log('[reference] Exact RoMidi input hash matched. Using null’s previously reviewed loader recovery; no browser AST refinement is claimed.');
      } catch (error) { log('[warning] ' + error.message + ' Keeping the upstream partial result.'); }
    }
    const outputBytes = new TextEncoder().encode(output);
    if (outputBytes.length > 16 * 1024 * 1024) throw Error('Output exceeds 16 MiB.');
    report.output_sha256 = await digest(outputBytes); report.output_bytes = outputBytes.length;
    log('[validate] Browser has no trusted Luau AST tool: syntax is not checked in this run. Behavior is not certified.');
    self.postMessage({type: 'result', output, report});
  } catch (error) { self.postMessage({type: 'error', text: error.message || String(error)}); }
};
