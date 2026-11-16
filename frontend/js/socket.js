/**
 * socket.js    Frontend WebSocket client wrapper
 *
 * Uses the Socket.IO client library (loaded from CDN in each page that needs it).
 * Connects to the Flask-SocketIO backend at localhost:5000.
 *
 * Usage in any HTML page:
 *   1. Include Socket.IO CDN script BEFORE this file
 *   2. Include this file:   <script src="../js/socket.js"></script>
 *   3. Call EcoSocket.connect() after the DOM is ready
 */

const EcoSocket = (() => {
  const BACKEND_URL = window.CONFIG?.API_BASE?.replace("/api", "") || "http://localhost:5000";
  let _socket = null;
  let _listeners = {}; // external handlers registered via EcoSocket.on()

  //  Connect 
  function connect() {
    if (_socket && _socket.connected) return; // already connected

    _socket = io(BACKEND_URL, {
      transports: ["websocket", "polling"], // prefer native WebSocket
      reconnection: true,
      reconnectionAttempts: 10,
      reconnectionDelay: 2000,
    });

    //  Core lifecycle events 
    _socket.on("connect", () => {
      console.log("[EcoSocket]  Connected  | sid:", _socket.id);
      _trigger("connect", { sid: _socket.id });
    });

    _socket.on("disconnect", (reason) => {
      console.log("[EcoSocket]   Disconnected |", reason);
      _trigger("disconnect", { reason });
    });

    _socket.on("connect_error", (err) => {
      console.warn("[EcoSocket] Connection error:", err.message);
      _trigger("error", { message: err.message });
    });

    //  Application events 

    /** How many users are currently on the platform */
    _socket.on("user_count", (data) => {
      console.log("[EcoSocket]  Online users:", data.count);
      _trigger("user_count", data);
    });

    /**
     * Fired when ANY user on the platform successfully submits a donation.
     * data: { user, ngo, category, eco_points, message }
     */
    _socket.on("donation_confirmed", (data) => {
      console.log("[EcoSocket]  New donation:", data);
      _trigger("donation_confirmed", data);
      // Show a global toast notification for every visitor on the donate page
      if (typeof showToast === "function") {
        showToast(data.message, "success");
      }
    });

    /**
     * Fired when an NGO's urgency level changes.
     * data: { ngo_id, ngo_name, urgency, message }
     */
    _socket.on("urgency_update", (data) => {
      console.log("[EcoSocket]  Urgency update:", data);
      _trigger("urgency_update", data);
    });

    /** Confirmation that we joined the donate room */
    _socket.on("room_joined", (data) => {
      console.log("[EcoSocket]  Joined room:", data.room);
      _trigger("room_joined", data);
    });
  }

  //  Join the donate room (subscribe to donation events) 
  function joinDonateRoom() {
    if (_socket) _socket.emit("join_donate_room", {});
  }

  function leaveDonateRoom() {
    if (_socket) _socket.emit("leave_donate_room", {});
  }

  //  Emit a custom event to the server 
  function emit(event, data) {
    if (_socket) _socket.emit(event, data || {});
  }

  //  Register an external handler 
  function on(event, callback) {
    if (!_listeners[event]) _listeners[event] = [];
    _listeners[event].push(callback);
  }

  function off(event, callback) {
    if (!_listeners[event]) return;
    _listeners[event] = _listeners[event].filter(cb => cb !== callback);
  }

  //  Internal dispatcher 
  function _trigger(event, data) {
    (_listeners[event] || []).forEach(cb => { try { cb(data); } catch (e) { console.error(e); } });
  }

  //  Disconnect cleanly 
  function disconnect() {
    if (_socket) { _socket.disconnect(); _socket = null; }
  }

  // Public API
  return { connect, disconnect, joinDonateRoom, leaveDonateRoom, emit, on, off };
})();

// Expose globally
window.EcoSocket = EcoSocket;
