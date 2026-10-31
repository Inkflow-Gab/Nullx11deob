'use strict';
// Explicit, one-way import into an owner-controlled tab. No CORS proxy, backend
// cookies, worker keys, output or logs ever pass back to the Pages origin.
(() => {
  let pending = null;
  const SOURCE = 'https://inkflow-gab.github.io';
  const TOKEN = /^[0-9a-f]{64}$/;
  function validateURL(value) {
    let url; try { url = new URL(value); } catch { throw Error('Paste the full HTTPS forwarded worker URL first.'); }
    if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash || !['/', '/index.html'].includes(url.pathname)) {
      throw Error('Use the worker root HTTPS URL, without a password, key, query, or fragment.');
    }
    if (url.hostname.endsWith('.github.dev') && !url.hostname.endsWith('.app.github.dev')) throw Error('Use the Ports forwarded URL, not the Codespace editor URL.');
    if (url.origin === location.origin) throw Error('This is the Pages site, not a Python/Luau worker.');
    return url;
  }
  function validPayload(value) {
    return value && typeof value.filename === 'string' && value.filename.length <= 250 && /\.(lua|luau|txt)$/i.test(value.filename) &&
      typeof value.data === 'string' && value.data.length <= 11200000 && value.settings &&
      ['auto', 'luraph', 'clyde'].includes(value.settings.engine) &&
      ['auto', '14.7', '14.8', '14.9', '15', '15.0', '15.1'].includes(value.settings.version) &&
      ['deobfuscate', 'trace', 'inspect'].includes(value.settings.mode);
  }
  window.nullRuntimeLink = {
    validateURL,
    open(payload, value, notice) {
      const url = validateURL(value);
      if (!validPayload(payload)) throw Error('Choose a valid Lua/text file and recovery settings.');
      if (!confirm(`Send ${payload.filename} to your private worker at ${url.origin}? Only use a worker you own. It will import the file, but will NOT start execution automatically.`)) return;
      if (pending) { clearTimeout(pending.timer); window.removeEventListener('message', pending.listener); pending = null; }
      const token = Array.from(crypto.getRandomValues(new Uint8Array(32)), byte => byte.toString(16).padStart(2, '0')).join('');
      url.hash = new URLSearchParams({nullSource: location.origin, nullToken: token}).toString();
      const popup = window.open(url.href, '_blank');
      if (!popup) throw Error('The popup was blocked. Allow this popup or open your worker manually and upload the file there.');
      const entry = pending = {popup, sent: false};
      const clean = () => { clearTimeout(entry.timer); window.removeEventListener('message', entry.listener); if (pending === entry) pending = null; };
      entry.listener = event => {
        if (event.source !== popup || event.origin !== url.origin || event.data?.token !== token) return;
        if (event.data.type === 'null-runner-ready' && !entry.sent) {
          entry.sent = true;
          popup.postMessage({type: 'null-runner-import', token, payload}, url.origin);
        } else if (event.data.type === 'null-runner-imported' && entry.sent) {
          clean(); notice('File imported into your private runner tab. Review settings and enter its owner key there, then press Start. Pages never receives your worker key or results.');
        } else if (event.data.type === 'null-runner-rejected') {
          clean(); notice('Worker import was rejected. Upload the file manually in that tab.');
        }
      };
      window.addEventListener('message', entry.listener);
      entry.timer = setTimeout(() => { clean(); notice('Automatic import did not connect. Sign in/open the worker and upload the file manually, or retry from this tab after signing in. Authentication or browser isolation can block tab imports.'); }, 60000);
      notice('Opening your private worker. Sign in if needed. The script will only be imported; execution requires your confirmation in that tab.');
    },
    receive(importFile, notice) {
      const params = new URLSearchParams(location.hash.slice(1));
      const source = params.get('nullSource'), token = params.get('nullToken');
      if (!source && !token) return;
      if (source !== SOURCE || !TOKEN.test(token || '') || !window.opener) {
        notice('Automatic import unavailable. Upload your script directly in this worker tab.'); return;
      }
      const opener = window.opener;
      let consumed = false;
      const listener = async event => {
        if (consumed || event.source !== opener || event.origin !== source || event.data?.token !== token || event.data.type !== 'null-runner-import') return;
        consumed = true; window.removeEventListener('message', listener); clearTimeout(timer);
        try {
          const payload = event.data.payload;
          if (!validPayload(payload)) throw Error('Invalid import.');
          const binary = atob(payload.data);
          if (!binary.length || binary.length > 8 * 1024 * 1024) throw Error('File must be 1 byte to 8 MiB.');
          await importFile(payload);
          history.replaceState(null, '', location.pathname + location.search);
          opener.postMessage({type: 'null-runner-imported', token}, source);
          // Sever the link after import; nothing needs to flow back during recovery.
          window.opener = null;
        } catch {
          opener.postMessage({type: 'null-runner-rejected', token}, source);
          notice('Import failed. Upload the file manually. No job was started.');
        }
      };
      window.addEventListener('message', listener);
      const timer = setTimeout(() => { window.removeEventListener('message', listener); notice('Import timed out. Upload your script manually.'); }, 60000);
      opener.postMessage({type: 'null-runner-ready', token}, source);
    }
  };
})();
