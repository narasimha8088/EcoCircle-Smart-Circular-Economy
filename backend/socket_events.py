# socket_events.py  ─  All Flask-SocketIO event handlers
# Handles real-time events for:
#   • User connect / disconnect  (live user counter)
#   • Donation confirmation      (push to all clients instantly)
#   • NGO urgency broadcast      (periodic urgency refresh)

from flask_socketio import emit, join_room, leave_room
from extensions import socketio

# ─── Track connected users in memory ────────────────────────────────────────
connected_users = set()


# ─── connect / disconnect ────────────────────────────────────────────────────
@socketio.on("connect")
def on_connect():
    """Fired when a browser client opens the WebSocket connection."""
    from flask import request as freq
    connected_users.add(freq.sid)
    count = len(connected_users)
    print(f"[WS] Client connected  | sid={freq.sid} | total={count}")

    # Tell the newly joined client how many people are online right now
    emit("user_count", {"count": count})

    # Also broadcast the updated count to everyone else
    socketio.emit("user_count", {"count": count})


@socketio.on("disconnect")
def on_disconnect(reason=None):
    """Fired when a client tab closes or navigates away."""
    from flask import request as freq
    connected_users.discard(freq.sid)
    count = len(connected_users)
    print(f"[WS] Client disconnected | sid={freq.sid} | reason={reason} | total={count}")
    socketio.emit("user_count", {"count": count})


# ─── Custom events ───────────────────────────────────────────────────────────
@socketio.on("join_donate_room")
def on_join_donate(data):
    """Client subscribes to the 'donate' room for targeted events."""
    join_room("donate")
    emit("room_joined", {"room": "donate", "msg": "You are now receiving live donation updates."})


@socketio.on("leave_donate_room")
def on_leave_donate(data):
    leave_room("donate")


# ─── Helper called from donate_routes after a successful donation ─────────────
def broadcast_new_donation(user_name: str, ngo_name: str, category: str):
    """
    Push a real-time notification to every browser tab
    currently watching the donate page.
    """
    socketio.emit(
        "donation_confirmed",
        {
            "user":       user_name,
            "ngo":        ngo_name,
            "category":   category,
            "message":    f"🎉 {user_name} just donated {category} items to {ngo_name}!",
        },
        room="donate",   # only clients who called join_donate_room
    )


def broadcast_urgency_update(ngo_id: int, ngo_name: str, new_urgency: int):
    """Push real-time urgency updates when an NGO's stock level changes."""
    socketio.emit(
        "urgency_update",
        {
            "ngo_id":   ngo_id,
            "ngo_name": ngo_name,
            "urgency":  new_urgency,
            "message":  f"⚡ {ngo_name} urgency updated to {new_urgency}%",
        },
    )
