// ============================================================
// session_store.js - keeps in-progress work alive across page changes
// ------------------------------------------------------------
// The app is a set of separate pages, so anything typed or uploaded is normally
// lost when you click another sidebar item. This stores drafts (text, photos,
// videos, AI results) in IndexedDB - which, unlike localStorage, can hold files.
// Data is kept until the page calls EcoStore.del(key) (the "New" button).
// Falls back to localStorage (text only) if IndexedDB is unavailable.
// ============================================================
(function () {
  const DB_NAME = 'ecocircle_sessions';
  const STORE   = 'sessions';
  let _dbPromise = null;

  function openDb() {
    if (_dbPromise) return _dbPromise;
    _dbPromise = new Promise((resolve, reject) => {
      if (!window.indexedDB) { reject(new Error('IndexedDB not supported')); return; }
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => { req.result.createObjectStore(STORE); };
      req.onsuccess = () => resolve(req.result);
      req.onerror   = () => reject(req.error);
      req.onblocked = () => reject(new Error('IndexedDB blocked'));
    });
    return _dbPromise;
  }

  function tx(mode, fn) {
    return openDb().then(db => new Promise((resolve, reject) => {
      const t = db.transaction(STORE, mode);
      const store = t.objectStore(STORE);
      const req = fn(store);
      t.oncomplete = () => resolve(req && 'result' in req ? req.result : undefined);
      t.onerror = t.onabort = () => reject(t.error);
    }));
  }

  // localStorage fallback: JSON only, files are dropped (but names are kept so the UI can warn)
  function lsKey(k) { return 'ecostore:' + k; }
  function lsPut(key, value) {
    try {
      const v = Object.assign({}, value);
      if (Array.isArray(v.files)) v.files = [];
      localStorage.setItem(lsKey(key), JSON.stringify(v));
    } catch (_) { /* quota - ignore */ }
  }
  function lsGet(key) {
    try { return JSON.parse(localStorage.getItem(lsKey(key)) || 'null'); } catch (_) { return null; }
  }

  window.EcoStore = {
    // Files are stored as plain {name,type,blob} records (works the same in every browser)
    packFiles(files) {
      return (files || []).map(f => ({ name: f.name || 'file', type: f.type || '', blob: f }));
    },
    unpackFiles(rows) {
      return (rows || []).filter(r => r && r.blob).map(r => {
        try { return new File([r.blob], r.name || 'file', { type: r.type || r.blob.type || '' }); }
        catch (e) { return r.blob; }
      });
    },
    async put(key, value) {
      try { await tx('readwrite', s => s.put(value, key)); }
      catch (e) { console.warn('[EcoStore] IndexedDB put failed, using localStorage:', e); lsPut(key, value); }
    },
    async get(key) {
      try { const v = await tx('readonly', s => s.get(key)); if (v !== undefined) return v; }
      catch (e) { console.warn('[EcoStore] IndexedDB get failed, using localStorage:', e); }
      return lsGet(key);
    },
    async del(key) {
      try { await tx('readwrite', s => s.delete(key)); } catch (e) { /* ignore */ }
      try { localStorage.removeItem(lsKey(key)); } catch (_) {}
    },
  };
})();
