// ============================================================
// NAV.JS  SPA Fetch Router (instant page switching)
// ============================================================
// How it works:
//   1. On load: fade in the page, set active sidebar link,
//      and begin prefetching other pages in the background.
//   2. On sidebar click: fetch() the target HTML, parse it,
//      extract <main> + body-level scripts, swap content,
//      re-run page scripts  no full browser reload.
//   3. On popstate (browser back/forward): same swap logic.
//
// Resources that load ONCE (never re-downloaded):
//   Tailwind CDN, Google Fonts, Material Icons, api.js,
//   config.js, nav.js, style.css, socket.io
// ============================================================

(function () {
  'use strict';

  //  Pages handled by SPA router 
  const SPA_PAGES = new Set([
    'dashboard.html', 'products.html', 'ai-engine.html',
    'donate.html', 'marketplace.html', 'repair.html',
    'recycling.html', 'map.html', 'profile.html',
    'ngo_dashboard.html', 'admin.html',
  ]);


  const LEAFLET_PAGES = new Set(['map.html', 'donate.html', 'lush_map_view.html']);
  const LEAFLET_CSS = 'https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.min.css';
  const LEAFLET_JS  = 'https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.min.js';

  // In-memory HTML string cache (raw text, to avoid repeat fetches)
  const pageCache = new Map();
  // In-memory parsed DOM cache (avoids re-running DOMParser on every visit)
  const parsedCache = new Map();
  // Tracks in-flight script loads to avoid duplicate <script> injections
  const _scriptLoading = new Map();

  //  Progress bar styles 
  function ensureStyles() {
    if (document.getElementById('__nav_styles__')) return;
    const s = document.createElement('style');
    s.id = '__nav_styles__';
    s.textContent = `
      #__nav_overlay__ {
        position:fixed; inset:0; z-index:9999;
        pointer-events:none; background:#f2f9ea;
        opacity:0; transition:opacity 0.18s ease;
      }
      #__nav_overlay__.nav-out { opacity:1; pointer-events:all; }
      #__nav_progress__ {
        position:fixed; top:0; left:0; height:3px; width:0%;
        background:linear-gradient(90deg,#176a21,#5db65a);
        border-radius:0 2px 2px 0; z-index:10000;
        opacity:0; transition:width 0.25s cubic-bezier(0.4,0,0.2,1), opacity 0.15s ease;
      }
      #__nav_progress__.active { opacity:1; }
      main { transition: opacity 0.1s ease; }
      main.__fading__ { opacity:0.4; pointer-events:none; }
    `;
    document.head.appendChild(s);
  }

  function getOrCreate(id, tag) {
    let el = document.getElementById(id);
    if (!el) { el = document.createElement(tag); el.id = id; document.body.appendChild(el); }
    return el;
  }

  //  Progress bar 
  function progressStart() {
    const bar = getOrCreate('__nav_progress__', 'div');
    bar.style.transition = 'none'; bar.style.width = '0%';
    bar.classList.add('active');
    requestAnimationFrame(() => {
      bar.style.transition = 'width 0.3s cubic-bezier(0.4,0,0.2,1)';
      bar.style.width = '70%';
    });
  }
  function progressDone() {
    const bar = document.getElementById('__nav_progress__');
    if (!bar) return;
    bar.style.width = '100%';
    setTimeout(() => {
      bar.style.opacity = '0';
      setTimeout(() => { bar.style.width = '0%'; bar.classList.remove('active'); bar.style.opacity = ''; }, 150);
    }, 100);
  }

  //  Page fade-in on first load 
  function fadePageIn() {
    const overlay = getOrCreate('__nav_overlay__', 'div');
    overlay.style.transition = 'none'; overlay.style.opacity = '1'; overlay.style.pointerEvents = 'none';
    requestAnimationFrame(() => requestAnimationFrame(() => {
      overlay.style.transition = 'opacity 0.15s ease'; overlay.style.opacity = '0';
    }));
  }

  //  Update sidebar active link 
  function updateActiveLink(page) {
    document.querySelectorAll('aside nav a, aside a[href]').forEach(a => {
      const href = (a.getAttribute('href') || '').split('/').pop();
      const isActive = href === page || href === page.split('/').pop();
      a.classList.remove('text-emerald-900','font-bold','border-l-4','border-emerald-600','bg-emerald-100/60');
      a.classList.add('text-emerald-700/70');
      if (isActive) {
        a.classList.remove('text-emerald-700/70');
        a.classList.add('text-emerald-900','font-bold','border-l-4','border-emerald-600','bg-emerald-100/60');
      }
    });
  }

  //  Inject Leaflet CSS on demand 
  function ensureLeafletCSS() {
    if (!document.querySelector(`link[href="${LEAFLET_CSS}"]`)) {
      const css = document.createElement('link');
      css.rel = 'stylesheet'; css.href = LEAFLET_CSS;
      document.head.appendChild(css);
    }
  }

  //  Load an external script, deduplicating in-flight loads 
  function loadScript(src) {
    if (document.querySelector(`script[src="${src}"]`)) return Promise.resolve();
    if (_scriptLoading.has(src)) return _scriptLoading.get(src);
    const p = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = src; s.crossOrigin = '';
      s.onload  = () => { _scriptLoading.delete(src); resolve(); };
      s.onerror = () => { _scriptLoading.delete(src); reject(new Error('Script failed: ' + src)); };
      document.head.appendChild(s);
    });
    _scriptLoading.set(src, p);
    return p;
  }

  //  Inject page-specific inline styles 
  function injectPageStyles(fetchedDoc) {
    const old = document.getElementById('__page_style__');
    if (old) old.remove();
    const styles = Array.from(fetchedDoc.head.querySelectorAll('style'))
      .filter(s => s.id !== 'tailwind-config' && !s.id.includes('nav_styles'));
    if (!styles.length) return;
    const combined = document.createElement('style');
    combined.id = '__page_style__';
    styles.forEach(s => { combined.textContent += s.textContent + '\n'; });
    document.head.appendChild(combined);
  }

  //  Page-specific elements that live OUTSIDE <main> (modals, floating buttons, overlays) 
  // The shared shell (aside + header) stays; everything else a page adds directly under <body>
  // must be swapped together with <main>, otherwise buttons like "Add item" have no modal to open.
  const SHELL_TAGS = new Set(['ASIDE', 'HEADER', 'MAIN', 'SCRIPT', 'STYLE', 'LINK', 'META', 'NOSCRIPT', 'TEMPLATE']);
  function isPageExtra(el) {
    if (!el || el.nodeType !== 1 || SHELL_TAGS.has(el.tagName)) return false;
    const id = el.id || '';
    if (id.startsWith('__nav_') || id === 'toast-container') return false;
    return true;
  }
  function tagCurrentExtras() {
    Array.from(document.body.children).forEach(el => { if (isPageExtra(el)) el.setAttribute('data-page-extra', '1'); });
  }
  function swapPageExtras(fetchedDoc) {
    document.querySelectorAll('[data-page-extra]').forEach(el => el.remove());
    Array.from(fetchedDoc.body.children).forEach(el => {
      if (!isPageExtra(el)) return;
      const clone = document.importNode(el, true);   // clone: the parsed-page cache must stay pristine
      clone.setAttribute('data-page-extra', '1');
      document.body.appendChild(clone);
    });
  }

  //  Execute a page's inline script in its OWN function scope
  // Why: every page declares top-level `const`/`let` (e.g. `sidebarUser`). Running them as plain
  // global scripts a second time throws "Identifier 'x' has already been declared" and the whole
  // page script silently never runs (typing, uploads, buttons all dead). A function scope makes
  // every visit independent. Page functions and any variables used by inline HTML handlers
  // (onclick="...") are re-exported to `window` so those handlers keep working.
  function handlerIdentifiers(markup) {
    const ids = new Set();
    const attrRe = /\son[a-z]+\s*=\s*(?:"([^"]*)"|'([^']*)')/gi;
    let m;
    while ((m = attrRe.exec(markup))) {
      const body = m[1] || m[2] || '';
      (body.match(/[A-Za-z_$][\w$]*/g) || []).forEach(id => ids.add(id));
    }
    return ids;
  }

  function execInlineScript(code, pageName, usedByHandlers) {
    const fnNames = new Set();
    const varNames = new Set();
    let m;
    const fnRe  = /^(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*\(/gm;
    const varRe = /^(?:const|let|var)\s+([A-Za-z_$][\w$]*)/gm;
    while ((m = fnRe.exec(code)))  fnNames.add(m[1]);
    while ((m = varRe.exec(code))) varNames.add(m[1]);

    let prelude = '';
    // Function declarations are hoisted, so these assignments are valid before the page code runs.
    fnNames.forEach(n => { prelude += `try{window.${n}=${n};}catch(_){}\n`; });
    // Live bindings for variables that inline HTML handlers refer to (e.g. onclick="map.setView(..)")
    varNames.forEach(n => {
      if (usedByHandlers && usedByHandlers.has(n) && !fnNames.has(n)) {
        prelude += `try{Object.defineProperty(window,${JSON.stringify(n)},{configurable:true,get:function(){return ${n};},set:function(v){${n}=v;}});}catch(_){}\n`;
      }
    });

    const wrapped = '(function(){\n' + prelude + code + '\n})();\n//# sourceURL=spa-page-' + pageName + '.js';
    const ns = document.createElement('script');
    ns.textContent = wrapped;
    document.body.appendChild(ns);
    Promise.resolve().then(() => { if (ns.parentNode) ns.remove(); });
  }

  //  Core navigation 
  async function navigateTo(href, pushState = true) {
    const page = href.split('/').pop().split('?')[0] || href;
    const current = window.location.pathname.split('/').pop();
    if (page === current && pushState) return;

    progressStart();

    try {
      // 1. Fetch HTML (use string cache if already loaded)
      if (!pageCache.get(page) && _warming.has(page)) await _warming.get(page);
      let html = pageCache.get(page);
      if (!html) {
        const res = await fetch(href, { credentials: 'same-origin' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        html = await res.text();
        pageCache.set(page, html);
      }

      // 2. Parse DOM (use parsed cache to skip DOMParser on repeat visits)
      // NOTE: Leaflet pages have mutable overlay state (map-overlay, loc-denied-panel),
      // so we always re-parse from raw HTML to ensure overlays appear fresh on every visit.
      let fetched;
      if (!LEAFLET_PAGES.has(page)) {
        fetched = parsedCache.get(page);
      }
      if (!fetched) {
        fetched = new DOMParser().parseFromString(html, 'text/html');
        if (!LEAFLET_PAGES.has(page)) {
          parsedCache.set(page, fetched);
        }
      }

      const newMain = fetched.querySelector('main');
      const curMain = document.querySelector('main');

      if (!newMain || !curMain) {
        window.location.href = href; return;
      }

      // 3. Destroy existing Leaflet map (prevents re-init error)
      if (window._ecoLeafletMap) {
        try { window._ecoLeafletMap.remove(); } catch (_) {}
        window._ecoLeafletMap = null;
      }

      if (LEAFLET_PAGES.has(page)) ensureLeafletCSS();

      // 4. Collect all body scripts from fetched doc
      const allBodyScripts = Array.from(fetched.body.querySelectorAll('script'));
      const externalScripts = allBodyScripts.filter(s => s.src);
      const inlineScripts   = allBodyScripts.filter(s => !s.src && s.textContent.trim());

      // 5. Kick off loading NEW external scripts in parallel with the fade animation
      const newExternals = externalScripts.filter(s => !document.querySelector(`script[src="${s.src}"]`));
      const scriptPreload = newExternals.length
        ? Promise.all(newExternals.map(s => loadScript(s.src).catch(e => console.warn('[nav] Script load failed:', s.src))))
        : Promise.resolve();

      // 6. Apply page styles + update metadata
      injectPageStyles(fetched);
      document.title = fetched.title || document.title;
      if (pushState) history.pushState({ page }, document.title, href);

      // 7. Fade out current content (40ms  perceptibly smooth, not sluggish)
      curMain.classList.add('__fading__');

      // 8. Swap content using the cached innerHTML
      curMain.className = newMain.className;
      curMain.innerHTML = newMain.innerHTML;
      swapPageExtras(fetched);

      // 9. Update sidebar + navbar
      updateActiveLink(page);
      if (typeof initNavbar === 'function') {
        try { initNavbar(); } catch (_) {}
      }

      // 10. Fade back in immediately
      curMain.classList.remove('__fading__');
      curMain.style.opacity = '0';
      requestAnimationFrame(() => {
        curMain.style.transition = 'opacity 0.12s ease';
        curMain.style.opacity = '';
        setTimeout(() => { curMain.style.transition = ''; }, 150);
      });

      progressDone();

      // 11. Wait for externals, then fire all inline scripts (no artificial delays between them)
      await scriptPreload;
      const handlerIds = handlerIdentifiers(curMain.innerHTML + Array.from(document.querySelectorAll('[data-page-extra]')).map(e => e.outerHTML).join(''));
      for (const s of inlineScripts) {
        try { execInlineScript(s.textContent, page.replace(/[^\w.-]/g, '_'), handlerIds); }
        catch (e) { console.error('[nav.js] Page script failed for ' + page + ':', e); }
      }

    } catch (err) {
      console.warn('[nav.js] SPA fetch failed, falling back to hard nav:', err);
      progressDone();
      window.location.href = href;
    }
  }

  //  Global click interception 
  function interceptLinks() {
    document.addEventListener('click', e => {
      const a = e.target.closest('a[href]');
      if (!a) return;
      const href = a.getAttribute('href') || '';
      if (!href || href.startsWith('#') || href.startsWith('http') ||
          href.startsWith('//') || href.startsWith('mailto:') ||
          href.startsWith('tel:') || a.target === '_blank') return;
      const page = href.split('/').pop().split('?')[0];
      if (!SPA_PAGES.has(page)) return;
      e.preventDefault();
      navigateTo(href);
    });
  }

  //  Back / Forward button 
  window.addEventListener('popstate', () => {
    navigateTo(window.location.href, false);
  });

  //  Prefetch SPA pages (gently) 
  // Fetching all pages at once right after start-up competes with the first page's own API calls on
  // the single-threaded dev server. Fetch them two at a time, after the page has finished loading,
  // and fetch a page immediately when the pointer/finger heads for its sidebar link.
  function warmPage(page) {
    if (pageCache.has(page) || _warming.has(page)) return Promise.resolve();
    const p = fetch(page, { credentials: 'same-origin' })
      .then(r => (r.ok ? r.text() : Promise.reject(new Error('HTTP ' + r.status))))
      .then(html => { pageCache.set(page, html); })
      .catch(() => {})
      .finally(() => { _warming.delete(page); });
    _warming.set(page, p);
    return p;
  }
  const _warming = new Map();

  function prefetchAll() {
    const current = window.location.pathname.split('/').pop();
    // Most-used tabs first
    const order = ['products.html', 'ai-engine.html', 'dashboard.html', 'marketplace.html', 'donate.html',
                   'repair.html', 'recycling.html', 'map.html', 'profile.html'];
    const queue = order.filter(pg => SPA_PAGES.has(pg) && pg !== current && !pageCache.has(pg));
    let running = 0;
    (function pump() {
      while (running < 2 && queue.length) {
        running++;
        warmPage(queue.shift()).finally(() => { running--; pump(); });
      }
    })();
  }

  function interceptHover() {
    const intent = e => {
      const a = e.target.closest && e.target.closest('aside a[href]');
      if (!a) return;
      const page = (a.getAttribute('href') || '').split('/').pop().split('?')[0];
      if (SPA_PAGES.has(page)) warmPage(page);
    };
    document.addEventListener('mouseover', intent, { passive: true });
    document.addEventListener('touchstart', intent, { passive: true });
    document.addEventListener('focusin', intent);
  }

  //  Init 
  ensureStyles();

  document.addEventListener('DOMContentLoaded', () => {
    tagCurrentExtras();
    fadePageIn();
    interceptLinks();
    interceptHover();
    const cur = window.location.pathname.split('/').pop() || 'dashboard.html';
    updateActiveLink(cur);
    // Start warming other tabs only once this page has fully loaded and the browser is idle
    const startWarm = () => {
      if ('requestIdleCallback' in window) requestIdleCallback(prefetchAll, { timeout: 3000 });
      else setTimeout(prefetchAll, 1500);
    };
    if (document.readyState === 'complete') setTimeout(startWarm, 800);
    else window.addEventListener('load', () => setTimeout(startWarm, 800), { once: true });
  });

  // bfcache support
  window.addEventListener('pageshow', e => { if (e.persisted) fadePageIn(); });


})();

