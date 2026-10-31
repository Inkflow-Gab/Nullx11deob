'use strict';
const $ = id => document.getElementById(id);
const state = {session: null, file: null, data: null, engine: 'auto', job: null, cursor: 0, busy: false, source: '', detected: null, began: 0, load: 0};
let pollTimer, clockTimer;
const terminal = new Set(['ready', 'partial', 'unverified', 'failed', 'cancelled']);
const stages = ['Receiving file', 'Detecting protection', 'Recovery in progress', 'Validating result', 'Result saved'];
function notice(message) { $('notice').textContent = message || ''; $('notice').hidden = !message; }
function size(n) { return n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(2)} MiB`; }
async function api(path, body) {
  if (window.nullBrowser) return window.nullBrowser.api(path, body);
  const options = {credentials: 'same-origin', cache: 'no-store'};
  if (body !== undefined) {
    options.method = 'POST';
    options.headers = {'Content-Type': 'application/json', 'X-CSRF-Token': state.session?.csrf || ''};
    if ($('worker-key').value) options.headers['X-Worker-Key'] = $('worker-key').value;
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok) { const error = new Error(result.error || `Worker returned ${response.status}`); error.status = response.status; throw error; }
  return result;
}
function toBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
  return btoa(binary);
}
function options() {
  const clyde = state.engine === 'clyde' || (state.engine === 'auto' && state.detected?.engine === 'clyde');
  $('version').disabled = clyde || state.busy;
  $('mode').disabled = clyde || state.busy;
  if (clyde) $('mode').value = 'deobfuscate';
  const engine = state.engine === 'auto' ? state.detected?.engine : state.engine;
  const note = state.session?.browser_only ? (engine === 'luraph' ? 'Full Luraph recovery runs in your private Python/Luau worker. Enter its URL below to open the runner and optionally import this file.' : 'Clyde runs locally in a browser worker. No uploads. Syntax is not checked here; unsupported layers are labeled partial.') : engine === 'clyde' ? 'Clyde uses static recovery: your script is not executed. Unsupported layers are labeled partial, not silently marked complete.' :
    state.session?.dynamic_enabled ? 'Luraph runs only with the private worker key. Emulation is not an OS sandbox. 15.1 compatibility remains experimental.' :
    'Safe-mode worker: dynamic Luraph is disabled. Choose Static VM map for a decoded chunk, or use an owner-enabled private worker.';
  $('engine-note').querySelector('p').textContent = note;
  $('start').disabled = !state.session || !state.data || state.busy;
  const linked = !!state.session?.browser_only && engine === 'luraph';
  $('runner-panel').hidden = !linked;
  $('privacy-label').lastChild.textContent = linked ? ' Transfer only with consent' : state.session?.browser_only ? ' Files stay in your browser' : ' Session-scoped results';
  $('privacy-mode').textContent = linked ? 'No auto-run' : state.session?.browser_only ? 'No uploads' : 'No sign-up';
  if (!state.busy) $('start').querySelector('span').textContent = linked ? 'Open full deobfuscator ↗' : 'Start recovery';
  document.querySelectorAll('[data-engine]').forEach(button => button.disabled = state.busy);
  $('file').disabled = state.busy;
  $('remove-file').disabled = state.busy;
}
function chooseEngine(engine) {
  state.engine = engine;
  document.querySelectorAll('[data-engine]').forEach(button => {
    const active = button.dataset.engine === engine;
    button.classList.toggle('active', active); button.setAttribute('aria-pressed', String(active));
  });
  options();
}
async function loadFile(file) {
  if (state.busy) return;
  const load = ++state.load;
  notice('');
  if (!file || !/\.(lua|luau|txt)$/i.test(file.name)) { notice('Choose a .lua, .luau, or .txt script.'); return; }
  if (!file.size || file.size > 8 * 1024 * 1024) { notice('Choose a non-empty script no larger than 8 MiB.'); return; }
  state.data = null; state.detected = null; state.file = file; state.job = null; resetDownload(); options();
  $('filename').textContent = file.name; $('filesize').textContent = size(file.size) + ' · detecting protection…';
  $('file-info').hidden = false; $('file-title').textContent = 'Script added'; $('file-subtitle').textContent = 'Drop another file to replace it';
  try {
    if (!state.session) throw new Error('Worker is offline. Reload when the backend is running.');
    const data = toBase64(await file.arrayBuffer());
    const detected = await api('/api/detect', {data});
    if (load !== state.load) return;
    state.data = data; state.detected = detected;
    $('filesize').textContent = `${size(file.size)} · ${detected.engine ? detected.engine + ' ' + (detected.version || '') : 'signature unknown'}`;
    $('detected-label').textContent = detected.engine ? `${detected.engine.toUpperCase()} ${detected.version || ''} DETECTED` : 'SELECT ENGINE MANUALLY';
    if (detected.warning) notice(detected.warning);
    options();
  } catch (error) { if (load === state.load) notice(error.message); }
}
function resetDownload() {
  $('download').classList.add('disabled'); $('download').removeAttribute('href'); $('download').setAttribute('aria-disabled', 'true');
  $('report').hidden = true; $('report').removeAttribute('href');
  $('copy').disabled = true; state.source = ''; $('source').textContent = '-- Waiting for a recovered result.';
}
function view(which) {
  for (const name of ['log', 'source']) {
    const active = name === which;
    $(name + '-tab').classList.toggle('active', active); $(name + '-tab').setAttribute('aria-selected', String(active));
    $(name + '-panel').hidden = !active;
  }
}
function busy(value) {
  state.busy = value; $('start').querySelector('span').textContent = value ? 'Worker is running…' : 'Start recovery';
  $('cancel').hidden = !value || !state.job; $('live-dot').classList.toggle('busy', value); options();
}
function clock() {
  const seconds = Math.floor((Date.now() - state.began) / 1000);
  $('elapsed').textContent = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
}
async function start() {
  if (!state.data || state.busy) return;
  if (state.session?.browser_only && (state.engine === 'luraph' || (state.engine === 'auto' && state.detected?.engine === 'luraph'))) {
    try { window.nullRuntimeLink.open({filename: state.file.name, data: state.data, settings: {engine: 'luraph', version: $('version').value, mode: $('mode').value}}, $('runner-url').value, notice); }
    catch (error) { notice(error.message); }
    return;
  }
  notice(''); resetDownload(); view('log');
  $('empty').hidden = true; $('logs').hidden = false; $('logs').textContent = '[client] Connecting to the worker…\n';
  $('job-badge').textContent = 'Starting';
  document.querySelectorAll('#stages li').forEach(item => item.classList.remove('done', 'current'));
  state.cursor = 0; state.job = null; state.began = Date.now(); busy(true);
  clearInterval(clockTimer); clockTimer = setInterval(clock, 1000); clock();
  try {
    const job = await api('/api/jobs', {filename: state.file.name, data: state.data,
      settings: {engine: state.engine, version: $('version').value, mode: $('mode').value}});
    state.job = job.id; $('cancel').hidden = false;
    $('result-title').textContent = 'Your job is in the worker queue.';
    $('result-detail').textContent = 'Live engine messages, not an invented percentage.';
    await poll();
  } catch (error) {
    notice(error.message); $('logs').textContent += `[error] ${error.message}\n`;
    $('job-badge').textContent = 'Not started'; $('job-badge').className = 'job-badge failed';
    $('result-title').textContent = 'No result was published.'; $('result-detail').textContent = 'Review the message and try again.';
    busy(false); clearInterval(clockTimer);
  }
}
async function poll() {
  try {
    const job = await api(`/api/jobs/${state.job}?after=${state.cursor}`);
    if (job.logs.length) {
      $('logs').textContent += job.logs.join('\n') + '\n';
      const area = document.querySelector('.output-body'); area.scrollTop = area.scrollHeight;
    }
    state.cursor = job.cursor;
    $('job-badge').textContent = job.state === 'ready' ? 'Recovered · review result' : job.state.replace(/^./, c => c.toUpperCase());
    $('job-badge').className = 'job-badge ' + job.state;
    $('stage-label').textContent = job.state === 'queued' ? 'Queued · waiting for worker' : terminal.has(job.state) ?
      (job.state === 'failed' ? 'Stopped · see activity' : job.state === 'cancelled' ? 'Job cancelled' : 'Finished · review recovery status') : stages[job.stage];
    document.querySelectorAll('#stages li').forEach((item, index) => {
      item.classList.toggle('done', index < job.stage || !!job.download);
      item.classList.toggle('current', index === job.stage && !terminal.has(job.state));
    });
    if (terminal.has(job.state)) {
      // Drain bounded log batches before stopping the stream.
      if (job.logs.length === 200) { pollTimer = setTimeout(poll, 50); return; }
      clearInterval(clockTimer);
      if (job.download) {
        $('report').href = window.nullBrowser ? window.nullBrowser.reportURL(state.job) : `/api/jobs/${state.job}/report`; $('report').hidden = false;
        $('download').href = job.download; if (job.filename) $('download').download = job.filename; $('download').classList.remove('disabled'); $('download').setAttribute('aria-disabled', 'false');
        $('result-title').textContent = job.report.external_payload_included === false ? 'Loader recovered. External payload excluded.' : job.state === 'partial' ? 'Partial recovery. Clearly labeled.' : job.state === 'unverified' ? 'Recovered · syntax not checked.' : 'Source recovered. Inspect before use.';
        $('result-detail').textContent = `${size(job.report.output_bytes)} · ${job.report.syntax_valid ? 'syntax checked' : 'no Lua syntax certificate'} · behavior not verified`;
        const preview = await api(`/api/jobs/${state.job}/preview`);
        state.source = preview.text;
        $('source').textContent = preview.text + (preview.truncated ? '\n\n-- Preview truncated. Download the full file.' : '');
        $('source-name').textContent = job.report.status === 'static_analysis_only' ? 'analysis.vm-map.json' : job.report.external_payload_included === false ? 'recovery.loader.lua' : job.state === 'partial' ? 'recovery.partial.lua' : 'recovery.lua';
        $('source-size').textContent = preview.truncated ? 'Preview · first 200 KB' : size(job.report.output_bytes);
        $('copy').disabled = preview.truncated || !preview.text;
        if (job.report.external_payload_included === false) notice((job.report.reference_recovery_used ? 'Exact input hash matched the previously reviewed loader; browser AST refinement was not rerun. ' : '') + 'The attached file is a remote loader. Its loader logic was recovered; the external MIDI payload was not fetched or included.');
        else if (job.state === 'partial') notice('This is a partial recovery or static analysis, not a fully deobfuscated working script. Review the activity and output.');
      } else {
        $('result-title').textContent = job.state === 'cancelled' ? 'Job cancelled. No download published.' : 'Recovery stopped. Your input is unchanged.';
        $('result-detail').textContent = 'See the activity log for details.';
      }
      busy(false); return;
    }
    pollTimer = setTimeout(poll, 750);
  } catch (error) {
    if (error.status === 404 || error.status === 403) {
      busy(false); clearInterval(clockTimer);
      notice('This job or session expired, or the worker restarted. Reload the page and upload again.');
      $('result-title').textContent = 'Session unavailable. No new result published.'; return;
    }
    notice(`Connection interrupted: ${error.message}. Retrying this job…`);
    pollTimer = setTimeout(poll, 2500);
  }
}
$('file').addEventListener('change', event => loadFile(event.target.files[0]));
$('dropzone').addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); if (!state.busy) $('file').click(); } });
for (const event of ['dragenter', 'dragover']) $('dropzone').addEventListener(event, e => { e.preventDefault(); $('dropzone').classList.add('dragging'); });
for (const event of ['dragleave', 'drop']) $('dropzone').addEventListener(event, e => { e.preventDefault(); $('dropzone').classList.remove('dragging'); });
$('dropzone').addEventListener('drop', event => loadFile(event.dataTransfer.files[0]));
$('remove-file').addEventListener('click', () => {
  if (state.busy) return; ++state.load; state.file = null; state.data = null; state.detected = null; $('file').value = '';
  $('file-info').hidden = true; $('file-title').textContent = 'Drop your script here'; $('file-subtitle').textContent = 'or browse files to get started';
  $('detected-label').textContent = 'AUTO-DETECT AVAILABLE'; notice(''); options();
});
document.querySelectorAll('[data-engine]').forEach(button => button.addEventListener('click', () => chooseEngine(button.dataset.engine)));
$('mode').addEventListener('change', options); $('log-tab').addEventListener('click', () => view('log')); $('source-tab').addEventListener('click', () => view('source'));
$('start').addEventListener('click', start);
$('cancel').addEventListener('click', async () => { try { await api(`/api/jobs/${state.job}/cancel`, {}); } catch (error) { notice(error.message); } });
$('copy').addEventListener('click', async () => {
  try { await navigator.clipboard.writeText(state.source); $('copy').textContent = 'Copied ✓'; setTimeout(() => $('copy').textContent = 'Copy source ↥', 1600); }
  catch { notice('Clipboard unavailable. Use Download or select the text manually.'); }
});
try { document.body.classList.toggle('dark', localStorage.getItem('null-theme') === 'dark'); } catch {}
$('theme').addEventListener('click', () => { document.body.classList.toggle('dark'); try { localStorage.setItem('null-theme', document.body.classList.contains('dark') ? 'dark' : 'light'); } catch {} });
async function connect() {
  try {
    state.session = await api('/api/session');
    if (state.session.browser_only) {
      $('connection').lastChild.textContent = ' Browser worker ready';
      $('advanced').hidden = true; options();
      return;
    }
    $('connection').lastChild.textContent = state.session.dynamic_enabled ? ' Private worker online' : ' Static worker online';
    options();
    window.nullRuntimeLink?.receive(async payload => {
      if (state.busy) throw new Error('A job is running. Wait for it to finish, then import again.');
      const binary = atob(payload.data);
      const file = new File([Uint8Array.from(binary, char => char.charCodeAt(0))], payload.filename, {type: 'text/plain'});
      await loadFile(file);
      if (!state.data || state.file !== file) throw new Error('Import was replaced or detection failed. Upload it manually.');
      chooseEngine(payload.settings.engine); $('version').value = payload.settings.version; $('mode').value = payload.settings.mode; options();
      if (state.session.dynamic_enabled) $('advanced').open = true;
      notice('Imported from your Pages tab. Review engine/version/mode. For dynamic Luraph, enter your owner key in Worker settings, then press Start recovery. No code has run.');
    }, notice);
    if (!state.session.node_available) notice('Node.js is missing: Clyde recovery needs Node 16+ installed on the worker.');
  } catch {
    $('connection').textContent = '○ Worker offline';
    notice('The backend is not reachable. Start web_server.py/Codespaces, or open the published GitHub Pages edition for browser-only Clyde. See WEB.md.');
  }
}
connect();
