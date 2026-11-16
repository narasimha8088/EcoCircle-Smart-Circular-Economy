// ============================================================
// CONFIG.JS    App configuration
// ============================================================
// Map: Using Leaflet.js + OpenStreetMap tiles (no API key needed!)
// The frontend map is completely free and open-source.
// Backend geocoding uses LocationIQ  set LOCATIONIQ_API_KEY in backend/.env

// Works out where the backend API lives.
//  1. If this page is served by the Flask backend itself (the normal case: the terminal link),
//     use the SAME origin, whatever port the server runs on (5000, 5001, 8000 ...).
//  2. If the page is opened some other way (file://, VS Code Live Server, another static server),
//     fall back to the backend on localhost:5000.
function resolveApiBase() {
  const loc = window.location;
  const fallback = `http://${loc.hostname && loc.protocol !== "file:" ? loc.hostname : "localhost"}:5000/api`;
  if (loc.protocol === "file:") return "http://localhost:5000/api";
  const sameOrigin = loc.origin + "/api";
  try {
    const key = "sce_api_base:" + loc.origin;
    const cached = sessionStorage.getItem(key);
    if (cached) return cached;
    // Tiny synchronous probe so every later script sees the right value immediately.
    const xhr = new XMLHttpRequest();
    xhr.open("GET", sameOrigin + "/health", false);
    xhr.send();
    if (xhr.status === 200 && /"status"\s*:\s*"ok"/.test(xhr.responseText)) {
      sessionStorage.setItem(key, sameOrigin);
      return sameOrigin;
    }
  } catch (_) { /* not served by the backend */ }
  return (loc.hostname === "localhost" || loc.hostname === "127.0.0.1") ? fallback : sameOrigin;
}

const CONFIG = {
  API_BASE: resolveApiBase(),
};

// Do not edit below this line
window.CONFIG = CONFIG;

// Unified global location manager — tied to the current login session.
// Location is cleared on logout and re-requested on every new login session.
window.GlobalLocation = (function() {
  // Derive a session key from the stored auth token so each login gets fresh location
  function _sessionKey() {
    const token = localStorage.getItem('sce_token');
    return token ? 'glb_loc_' + token.slice(-16) : null;
  }

  // Load previously stored location ONLY for the current login session
  function _load() {
    const key = _sessionKey();
    if (!key) return { lat: null, lng: null };
    try {
      const raw = sessionStorage.getItem(key);
      if (raw) { const d = JSON.parse(raw); return { lat: d.lat, lng: d.lng }; }
    } catch(_) {}
    return { lat: null, lng: null };
  }

  const stored = _load();

  return {
    lat: stored.lat,
    lng: stored.lng,

    // forceRefresh=true  always calls geolocation API (browser may silently return without popup if already granted)
    // forceRefresh=false  uses in-session cached value if available
    get: function(forceRefresh) {
      return new Promise((resolve, reject) => {
        if (!forceRefresh && this.lat && this.lng) {
          return resolve({ lat: parseFloat(this.lat), lng: parseFloat(this.lng) });
        }
        if (!navigator.geolocation) {
          return reject(new Error('Geolocation is not supported by your browser.'));
        }
        navigator.geolocation.getCurrentPosition(
          pos => {
            this.lat = pos.coords.latitude;
            this.lng = pos.coords.longitude;
            // Cache against the current login session token
            const key = _sessionKey();
            if (key) sessionStorage.setItem(key, JSON.stringify({ lat: this.lat, lng: this.lng }));
            resolve({ lat: this.lat, lng: this.lng });
          },
          err => {
            let msg = 'Could not get your location.';
            if (err.code === 1) msg = 'Location access denied. Please allow location in your browser settings and try again.';
            else if (err.code === 2) msg = 'Location unavailable. Check your device GPS/network and try again.';
            else if (err.code === 3) msg = 'Location request timed out. Please try again.';
            reject(new Error(msg));
          },
          { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
        );
      });
    },

    // Clears all location data (called on logout)
    clear: function() {
      this.lat = null;
      this.lng = null;
      // Clear all session location keys
      Object.keys(sessionStorage).forEach(k => {
        if (k.startsWith('glb_loc_') || k === 'glb_lat' || k === 'glb_lng') {
          sessionStorage.removeItem(k);
        }
      });
    }
  };
})();

// ============================================================
// XSS GUARD  -  escapeHtml(str)
// Use this whenever inserting user-provided text into innerHTML.
// ============================================================
window.escapeHtml = function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g,  '&amp;')
    .replace(/</g,  '&lt;')
    .replace(/>/g,  '&gt;')
    .replace(/"/g,  '&quot;')
    .replace(/'/g,  '&#39;');
};