'use strict';
// GitHub Pages adapter: no /api requests, no remote execution service, no uploads.
(() => {
  let current = null;
  const cached = new Map();
  const urls = new Set();
  const fileURL = (text, type) => { const url = URL.createObjectURL(new Blob([text], {type})); urls.add(url); return url; };
  const clear = () => { if (current?.worker) current.worker.terminate(); clearTimeout(current?.timer); for (const url of urls) URL.revokeObjectURL(url); urls.clear(); };
  const bytes = data => {
    if (typeof data !== 'string' || data.length > 11200000) throw Error('File exceeds the upload-size limit.');
    const binary = atob(data); if (!binary.length || binary.length > 8 * 1024 * 1024) throw Error('Choose a non-empty file up to 8 MiB.');
    return Uint8Array.from(binary, char => char.charCodeAt(0));
  };
  const detect = data => {
    const text = new TextDecoder().decode(bytes(data).subarray(0, 20000));
    const luraph = /Luraph Obfuscator v(\d+(?:\.\d+)*)/i.exec(text.slice(0, 4096));
    if (luraph) return {engine: 'luraph', version: luraph[1], warning: 'Luraph detected. Use the full-runner panel to open your private Python/Luau worker. 15.1 remains experimental.'};
    if (/clydeprotection|Clyde Protection/i.test(text)) return {engine: 'clyde', version: 'auto', warning: null};
    return {engine: null, version: null, warning: 'No reliable signature. Select Clyde manually, or use a private worker for Luraph.'};
  };
  const snapshot = (job, after = 0) => ({id: job.id, name: job.name, filename: job.filename, state: job.state, stage: job.stage,
    logs: job.logs.slice(after, after + 200), cursor: Math.min(job.logs.length, after + 200), report: job.report, download: job.download, created: job.created, finished: job.finished, settings: job.settings});
  const append = (job, text) => {
    text = String(text).slice(0, 3000); const cost = new TextEncoder().encode(text).length + 1;
    if (job.logs.length < 4000 && job.logBytes + cost <= 256000) { job.logs.push(text); job.logBytes += cost; }
  };
  const record = job => ({id: job.id, name: job.name, filename: job.filename, state: job.state, stage: job.stage, logs: job.logs, logBytes: job.logBytes,
    report: job.report, output: job.output, created: job.created, finished: job.finished, settings: job.settings});
  const stop = (job, state, text) => { job.worker?.terminate(); job.worker = null; clearTimeout(job.timer); job.state = state; job.finished = Date.now() / 1000; job.output = ''; job.report = {}; job.download = null; job.reportURL = null; append(job, text); void window.nullStore.save(record(job)); };
  const hydrate = item => {
    if (['running', 'queued'].includes(item.state)) return {...item, state: 'detached', download: null,
      logs: [...item.logs, '[notice] This browser worker is not attached to this tab. Check the original tab if open; a closed tab cannot keep browser-only Clyde running. Upload again if it was closed.']};
    return {...item, download: item.output ? fileURL(item.output, 'text/plain;charset=utf-8') : null,
      reportURL: item.output ? fileURL(JSON.stringify(item.report, null, 2), 'application/json') : null};
  };
  window.nullBrowser = {
    reportURL: id => current?.id === id ? current.reportURL : cached.get(id)?.reportURL || '',
    async api(path, payload) {
      if (path === '/api/session') return {browser_only: true, dynamic_enabled: false, node_available: false, ast_available: false, runtime_available: false};
      if (path === '/api/jobs' && !payload) {
        let records = []; try { records = await window.nullStore.all(); } catch { window.dispatchEvent(new CustomEvent('null-storage-error', {detail: 'Saved browser results could not be read. Storage may be blocked or cleared; download important files yourself.'})); }
        const jobs = records.map(item => current?.id === item.id ? snapshot(current) : {...item, state: ['running', 'queued'].includes(item.state) ? 'detached' : item.state, logs: undefined, output: undefined});
        if (current && !jobs.some(item => item.id === current.id)) jobs.unshift(snapshot(current));
        return {jobs, browser_only: true};
      }
      if (path === '/api/jobs/clear-history') { await window.nullStore.clearFinished(current?.state === 'running' ? current.id : null); if (current && current.state !== 'running') { current = null; clear(); } for (const item of cached.values()) for (const url of [item.download, item.reportURL]) if (url) { URL.revokeObjectURL(url); urls.delete(url); } cached.clear(); return {ok: true}; }
      if (path === '/api/detect') return detect(payload.data);
      if (path === '/api/jobs') {
        const detection = detect(payload.data);
        const engine = payload.settings.engine === 'auto' ? detection.engine : payload.settings.engine;
        if (engine !== 'clyde') throw Error('GitHub Pages runs static Clyde only. Use Launch for a private Luraph worker.');
        if (payload.settings.mode !== 'deobfuscate') throw Error('Browser mode supports static Clyde recovery only.');
        const input = bytes(payload.data); clear();
        const job = current = {id: crypto.randomUUID().replaceAll('-', ''), name: payload.filename, state: 'running', stage: 2,
          logs: [], logBytes: 0, report: {}, download: null, output: '', filename: '', created: Date.now() / 1000, finished: null, settings: {...payload.settings, engine}};
        cached.clear();
        await window.nullStore.save(record(job));
        append(job, '[receive] File stays in this browser tab. Nothing is uploaded.');
        const worker = job.worker = new Worker(new URL('./clyde-worker.js', document.baseURI));
        worker.onerror = () => stop(job, 'failed', '[error] Browser worker failed or ran out of memory. Try a smaller file.');
        worker.onmessage = async ({data}) => {
          if (job !== current || job.state !== 'running') return;
          if (data.type === 'log') append(job, data.text);
          else if (data.type === 'error') stop(job, 'failed', '[error] ' + data.text);
          else if (data.type === 'result') {
            job.output = data.output; job.report = data.report; job.stage = 4;
            job.filename = payload.filename.replace(/[^A-Za-z0-9_.-]/g, '_').slice(0, 80).replace(/\.[^.]+$/, '') +
              (data.report.external_payload_included === false ? '.loader.lua' : data.report.status === 'partial' ? '.partial.lua' : '.recovered.lua');
            const state = data.report.status === 'partial' ? 'partial' : 'unverified';
            job.worker?.terminate(); job.worker = null; clearTimeout(job.timer);
            const finished = Date.now() / 1000;
            append(job, '[saved] Local download ready. Syntax and behavior are not certified.');
            await window.nullStore.save({...record(job), state, finished});
            if (job.state !== 'running') return;
            job.download = fileURL(data.output, 'text/plain;charset=utf-8');
            job.reportURL = fileURL(JSON.stringify(data.report, null, 2) + '\n', 'application/json');
            job.state = state; job.finished = finished;
          }
        };
        job.timer = setTimeout(() => stop(job, 'failed', '[error] 180-second time limit reached.'), 180000);
        worker.postMessage({bytes: input}, [input.buffer]);
        return snapshot(job);
      }
      const match = /^\/api\/jobs\/([0-9a-f]{32})(\/(?:preview|cancel))?(?:\?after=(\d+))?$/.exec(path);
      if (!match) { const error = Error('Local result expired. Upload again.'); error.status = 404; throw error; }
      let job = current?.id === match[1] ? current : null;
      if (!job) {
        const saved = await window.nullStore.get(match[1]);
        if (!saved) { const error = Error('Local result expired. Upload again.'); error.status = 404; throw error; }
        const previous = cached.get(saved.id);
        job = previous && previous.report.output_sha256 === saved.report.output_sha256 && previous.finished === saved.finished && !['running', 'queued'].includes(saved.state) ? previous : hydrate(saved);
        cached.set(job.id, job);
      }
      if (match[2] === '/cancel' && job === current && job.state === 'running') stop(job, 'cancelled', '[cancelled] Browser worker terminated; no download published.');
      if (match[2] === '/preview') return {text: job.output.slice(0, 200000), truncated: job.output.length > 200000};
      return snapshot(job, Number(match[3] || 0));
    }
  };
  window.addEventListener('pagehide', clear);
  // pagehide stops the worker/revokes URLs; rehydrate instead of restoring stale links from bfcache.
  window.addEventListener('pageshow', event => { if (event.persisted) location.reload(); });
})();
