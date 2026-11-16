//  api.js    thin wrapper around fetch 
const API = {
  base: () => (window.CONFIG?.API_BASE || "http://localhost:5000/api"),

  headers() {
    const h = { "Content-Type": "application/json" };
    const token = localStorage.getItem("sce_token");
    if (token) h["Authorization"] = `Bearer ${token}`;
    return h;
  },

  async get(path) {
    const r = await fetch(this.base() + path, { headers: this.headers() });
    return this._handle(r);
  },

  async post(path, body) {
    const r = await fetch(this.base() + path, {
      method: "POST", headers: this.headers(), body: JSON.stringify(body),
    });
    return this._handle(r);
  },

  async put(path, body) {
    const r = await fetch(this.base() + path, {
      method: "PUT", headers: this.headers(), body: JSON.stringify(body),
    });
    return this._handle(r);
  },

  async delete(path) {
    const r = await fetch(this.base() + path, { method: "DELETE", headers: this.headers() });
    return this._handle(r);
  },

  async _handle(r) {
    const data = await r.json().catch(() => ({}));
    if (r.status === 401) {
      // JWT expired or invalid — clear token and send to login
      localStorage.removeItem("sce_token");
      localStorage.removeItem("sce_user");
      window.location.href = "login.html";
      throw new Error("Session expired. Please log in again.");
    }
    if (!r.ok) throw new Error(data.error || data.message || `Request failed (${r.status})`);
    return data;
  },
};

//  Auth helpers 
const Auth = {
  save(token, user) {
    localStorage.setItem("sce_token", token);
    localStorage.setItem("sce_user", JSON.stringify(user));
  },
  clear() {
    localStorage.removeItem("sce_token");
    localStorage.removeItem("sce_user");
    // Clear cached location so map asks for location again after next login
    if (window.GlobalLocation && typeof window.GlobalLocation.clear === 'function') {
      window.GlobalLocation.clear();
    } else {
      // Fallback: clear old-style keys
      sessionStorage.removeItem('glb_lat');
      sessionStorage.removeItem('glb_lng');
      Object.keys(sessionStorage).forEach(k => {
        if (k.startsWith('glb_loc_')) sessionStorage.removeItem(k);
      });
    }
  },
  token()   { return localStorage.getItem("sce_token"); },
  user()    { try { return JSON.parse(localStorage.getItem("sce_user")); } catch { return null; } },
  isLoggedIn() { return !!this.token(); },
  requireLogin() {
    if (!this.isLoggedIn()) {
      window.location.href = "login.html";
      return false;
    }
    return true;
  },
};

//  Toast notifications 
function showToast(msg, type = "success") {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.className = "toast-container";
    document.body.appendChild(container);
  }
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span>${type === "success" ? "" : ""}</span> ${msg}`;
  container.appendChild(toast);
  setTimeout(() => { toast.style.opacity = "0"; toast.style.transform = "translateY(10px)"; toast.style.transition = "0.3s"; setTimeout(() => toast.remove(), 300); }, 3500);
}

//  Navbar user state 
function initNavbar() {
  const user     = Auth.user();
  const scoreEl  = document.getElementById("nav-eco-score");
  const loginBtn = document.getElementById("nav-login-btn");
  const userMenu = document.getElementById("nav-user-menu");
  const userName = document.getElementById("nav-user-name");
  const logoutBtn= document.getElementById("nav-logout");

  if (scoreEl && user) {
    scoreEl.textContent = ` ${user.eco_score || 0} pts`;
    scoreEl.style.display = "flex";
  }
  if (loginBtn && userMenu) {
    if (user) {
      loginBtn.style.display = "none";
      userMenu.style.display = "flex";
      if (userName) userName.textContent = user.name?.split(" ")[0];
    } else {
      loginBtn.style.display = "flex";
      userMenu.style.display = "none";
    }
  }
  // Wire logout for both top navbar and sidebar-brand
  document.querySelectorAll('#nav-logout').forEach(btn => {
    btn.addEventListener('click', () => {
      Auth.clear();
      window.location.href = 'login.html';
    });
  })

  // Active link highlight
  const links = document.querySelectorAll(".nav-links a, .sidebar-link");
  const current = window.location.pathname.split("/").pop();
  links.forEach(l => {
    if (l.getAttribute("href") === current || l.getAttribute("href")?.endsWith(current)) {
      l.classList.add("active");
    }
  });
}

//  Tab system 
function initTabs(containerSelector) {
  const container = document.querySelector(containerSelector || ".tabs-container");
  if (!container) return;
  const btns   = container.querySelectorAll(".tab-btn");
  const panels = container.querySelectorAll(".tab-panel");
  btns.forEach((btn, i) => {
    btn.addEventListener("click", () => {
      btns.forEach(b => b.classList.remove("active"));
      panels.forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      panels[i]?.classList.add("active");
    });
  });
  btns[0]?.click();
}

//  Utility 
function formatDate(d) { return new Date(d).toLocaleDateString("en-IN", { day:"numeric", month:"short", year:"numeric" }); }
function formatPrice(n){ return "" + Number(n).toLocaleString("en-IN"); }
function conditionBadge(c) {
  const map = { New:"green", Good:"green", Fair:"amber", Poor:"red" };
  return `<span class="badge badge-${map[c]||'gray'}">${c}</span>`;
}
function categoryEmoji(cat) {
  const map = { Mobile:"", Laptop:"", Appliance:"", Furniture:"", Clothing:"", Electronics:"", Vehicle:"", Books:"", Sports:"" };
  return map[cat] || "";
}

window.API    = API;
window.Auth   = Auth;
window.showToast = showToast;
window.initNavbar = initNavbar;
window.initTabs = initTabs;
window.formatDate = formatDate;
window.formatPrice = formatPrice;
window.conditionBadge = conditionBadge;
window.categoryEmoji = categoryEmoji;

//  WebSocket Initialization 
window.addEventListener('DOMContentLoaded', () => {
    // Inject the socket.io and custom socket.js scripts dynamically
    if (!window.io) {
        const socketScript = document.createElement('script');
        socketScript.src = "https://cdn.socket.io/4.7.2/socket.io.min.js";
        document.head.appendChild(socketScript);

        socketScript.onload = () => {
            const ecoSocketScript = document.createElement('script');
            // Assuming api.js is loaded with a relative path like ../js/api.js
            let srcPath = document.querySelector('script[src$="api.js"]')?.getAttribute('src');
            let basePath = srcPath ? srcPath.replace('api.js', '') : '../js/';
            ecoSocketScript.src = basePath + "socket.js";
            document.head.appendChild(ecoSocketScript);

            ecoSocketScript.onload = () => {
                if (window.EcoSocket) {
                    window.EcoSocket.connect();
                    console.log("[App] WebSocket global connection initiated.");
                    
                    // Specific room subscription for donation events
                    if (window.location.pathname.includes('donate.html')) {
                        window.EcoSocket.joinDonateRoom();
                    }
                }
            };
        };
    }
});
