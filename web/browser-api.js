'use strict';
// GitHub Pages adapter: no /api requests, no remote execution service, no uploads.
(() => {
  let current = null;
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
    logs: job.logs.slice(after, after + 200), cursor: Math.min(job.logs.length, after + 200), report: job.report, download: job.download});
  const append = (job, text) => {
    text = String(text).slice(0, 3000); const cost = new TextEncoder().encode(text).length + 1;
    if (job.logs.length < 4000 && job.logBytes + cost <= 256000) { job.logs.push(text); job.logBytes += cost; }
  };
  const stop = (job, state, text) => { job.worker?.terminate(); job.worker = null; clearTimeout(job.timer); job.state = state; append(job, text); };
  window.nullBrowser = {
    reportURL: id => current?.id === id ? current.reportURL : '',
    async api(path, payload) {
      if (path === '/api/session') return {browser_only: true, dynamic_enabled: false, node_available: false, ast_available: false, runtime_available: false};
      if (path === '/api/detect') return detect(payload.data);
      if (path === '/api/jobs') {
        const detection = detect(payload.data);
        const engine = payload.settings.engine === 'auto' ? detection.engine : payload.settings.engine;
        if (engine !== 'clyde') throw Error('GitHub Pages runs static Clyde only. Use Launch for a private Luraph worker.');
        if (payload.settings.mode !== 'deobfuscate') throw Error('Browser mode supports static Clyde recovery only.');
        const input = bytes(payload.data); clear();
        const job = current = {id: crypto.randomUUID().replaceAll('-', ''), name: payload.filename, state: 'running', stage: 2,
          logs: [], logBytes: 0, report: {}, download: null, output: '', filename: ''};
        append(job, '[receive] File stays in this browser tab. Nothing is uploaded.');
        const worker = job.worker = new Worker(new URL('./clyde-worker.js', document.baseURI));
        worker.onerror = () => stop(job, 'failed', '[error] Browser worker failed or ran out of memory. Try a smaller file.');
        worker.onmessage = ({data}) => {
          if (job !== current || job.state !== 'running') return;
          if (data.type === 'log') append(job, data.text);
          else if (data.type === 'error') stop(job, 'failed', '[error] ' + data.text);
          else if (data.type === 'result') {
            job.output = data.output; job.report = data.report; job.stage = 4;
            job.filename = payload.filename.replace(/[^A-Za-z0-9_.-]/g, '_').slice(0, 80).replace(/\.[^.]+$/, '') +
              (data.report.external_payload_included === false ? '.loader.lua' : data.report.status === 'partial' ? '.partial.lua' : '.recovered.lua');
            job.download = fileURL(data.output, 'text/plain;charset=utf-8');
            job.reportURL = fileURL(JSON.stringify(data.report, null, 2) + '\n', 'application/json');
            stop(job, data.report.status === 'partial' ? 'partial' : 'unverified', '[saved] Local download ready. Syntax and behavior are not certified.');
          }
        };
        job.timer = setTimeout(() => stop(job, 'failed', '[error] 180-second time limit reached.'), 180000);
        worker.postMessage({bytes: input}, [input.buffer]);
        return snapshot(job);
      }
      const match = /^\/api\/jobs\/([0-9a-f]{32})(\/(?:preview|cancel))?(?:\?after=(\d+))?$/.exec(path);
      if (!match || !current || current.id !== match[1]) { const error = Error('Local result expired. Upload again.'); error.status = 404; throw error; }
      if (match[2] === '/cancel' && current.state === 'running') stop(current, 'cancelled', '[cancelled] Browser worker terminated; no download published.');
      if (match[2] === '/preview') return {text: current.output.slice(0, 200000), truncated: current.output.length > 200000};
      return snapshot(current, Number(match[3] || 0));
    }
  };
  window.addEventListener('pagehide', clear);
})();
