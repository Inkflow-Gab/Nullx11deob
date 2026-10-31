'use strict';
// Per-origin + per-workspace storage. No raw uploads; keys only after opt-in.
(() => {
  const scope = new URL('.', location.href).pathname;
  const prefix = 'null.workspace.v3:' + scope;
  let database;
  const local = {
    get(name) { try { return JSON.parse(localStorage.getItem(prefix + name)); } catch { return null; } },
    set(name, value) { try { localStorage.setItem(prefix + name, JSON.stringify(value)); return true; } catch { return false; } },
    remove(name) { try { localStorage.removeItem(prefix + name); } catch {} }
  };
  const open = () => database || (database = new Promise((resolve, reject) => {
    if (!window.indexedDB) { reject(Error('Browser storage unavailable')); return; }
    const request = indexedDB.open('null.results.v3:' + scope, 2);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains('runs')) db.createObjectStore('runs', {keyPath: 'id'});
      if (!db.objectStoreNames.contains('summaries')) {
        const summaries = db.createObjectStore('summaries', {keyPath: 'id'});
        const cursor = request.transaction.objectStore('runs').openCursor();
        cursor.onsuccess = () => { const item = cursor.result; if (item) { summaries.put(summary(item.value)); item.continue(); } };
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(Error('Saved results are locked by another tab.'));
  }));
  const summary = item => ({id: item.id, name: item.name, state: item.state, stage: item.stage, created: item.created, finished: item.finished, settings: item.settings, storage_bytes: new TextEncoder().encode(item.output || '').length + new TextEncoder().encode(JSON.stringify(item.logs || [])).length + new TextEncoder().encode(JSON.stringify(item.report || {})).length});
  const transaction = async (mode, action, name = 'runs') => {
    const db = await open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(mode === 'readwrite' ? ['runs', 'summaries'] : [name], mode); const request = action(tx.objectStore(name), tx);
      tx.oncomplete = () => resolve(request.result);
      tx.onerror = tx.onabort = () => reject(tx.error || Error('Unable to save browser results.'));
    });
  };
  const all = async () => (await transaction('readonly', store => store.getAll(), 'summaries')).sort((a, b) => b.created - a.created);
  window.nullStore = {
    available: true,
    latest() { const id = local.get('latest'); return typeof id === 'string' && /^[0-9a-f]{32}$/.test(id) ? id : null; },
    setLatest(id) { return local.set('latest', id); },
    clearLatest() { local.remove('latest'); },
    savedKey() {
      const item = local.get('owner-key');
      if (!item || typeof item.key !== 'string' || !Number.isFinite(item.expires) || item.expires <= Date.now()) { local.remove('owner-key'); return ''; }
      return item.key;
    },
    saveKey(key) { return local.set('owner-key', {key, expires: Date.now() + 7 * 86400000}); },
    forgetKey() { local.remove('owner-key'); },
    all,
    get(id) { return transaction('readonly', store => store.get(id)); },
    async save(record) {
      try {
        await transaction('readwrite', (store, tx) => { tx.objectStore('summaries').put(summary(record)); return store.put(record); });
        const records = await all(); let used = 0;
        for (let index = 0; index < records.length; index++) {
          const item = records[index];
          used += item.storage_bytes || 0;
          if (index >= 5 || used > 32 * 1024 * 1024) await transaction('readwrite', (store, tx) => { tx.objectStore('summaries').delete(item.id); return store.delete(item.id); });
        }
      } catch (error) {
        this.available = false;
        window.dispatchEvent(new CustomEvent('null-storage-error', {detail: 'Browser storage is unavailable/full. This run can still be downloaded now, but may not be saved for your return.'}));
      }
    },
    async clearFinished(activeID) {
      for (const item of await all()) if (item.id !== activeID) await transaction('readwrite', (store, tx) => { tx.objectStore('summaries').delete(item.id); return store.delete(item.id); });
    }
  };
})();
