"""
NGO Portal API Routes
=====================
All routes under /api/ngo — used by the NGO Dashboard frontend.

Auth:  NGO-specific JWT (ngo_id claim).  An NGO logs in via
       POST /api/ngo/login and receives a token with sub=<ngo_id>.
       This keeps NGO auth completely separate from donor (user) auth
       while re-using the same JWT extension.

Endpoints
---------
POST /api/ngo/register          Register a new NGO profile.
POST /api/ngo/login             NGO portal login → JWT.
GET  /api/ngo/dashboard         Full NGO dashboard data (needs + pledges).
GET  /api/ngo/needs             List this NGO's needs board entries.
POST /api/ngo/needs             Add a new needs board entry.
PUT  /api/ngo/needs/<need_id>   Edit an existing need.
DELETE /api/ngo/needs/<need_id> Remove a need (only if no active pledges).
GET  /api/ngo/pledges           List incoming pledges for this NGO.
POST /api/ngo/pledges/<pledge_id>/status   Advance pledge state.
GET  /api/ngo/list              Public list of all verified NGOs (no auth).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any, List

from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token,
    jwt_required,
    get_jwt_identity,
    get_jwt,
)
from extensions import db
from models.ngo_model import (
    NGOProfile,
    NeedsBoardEntry,
    PledgeRecord,
    VALID_CATEGORIES,
    VALID_URGENCIES,
    VALID_CONDITIONS,
)

logger = logging.getLogger(__name__)
ngo_bp = Blueprint("ngo", __name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _current_ngo() -> Optional[NGOProfile]:
    """Return the NGOProfile for the token's ngo_id claim, or None."""
    claims = get_jwt()
    ngo_id = claims.get("ngo_id") or get_jwt_identity()
    return NGOProfile.query.get(ngo_id)


def _ngo_token(ngo: NGOProfile) -> str:
    """Create an access token encoding the ngo_id as both subject and claim."""
    return create_access_token(
        identity=ngo.ngo_id,
        additional_claims={"ngo_id": ngo.ngo_id, "role": "ngo"},
        expires_delta=timedelta(hours=12),
    )


# ── Public endpoints ───────────────────────────────────────────────────────────

@ngo_bp.route("/list", methods=["GET"])
def list_ngos():
    """Return all verified NGO profiles (public — no auth required)."""
    category = request.args.get("category", "").strip()
    ngos     = NGOProfile.query.filter_by(verified=True).all()
    if category:
        ngos = [n for n in ngos if category in (n.category_tags or [])]
    return jsonify({"ngos": [n.to_dict() for n in ngos], "total": len(ngos)})


@ngo_bp.route("/register", methods=["POST"])
def register_ngo():
    """
    Register a new NGO.

    Body (JSON):
        name            str   required
        registration_no str   required
        address         str   required
        password        str   required
        contact_phone   str   optional
        contact_email   str   optional
        category_tags   list  optional  e.g. ["Clothes","Books"]
    """
    data = request.get_json() or {}

    required = ["name", "registration_no", "address", "password"]
    missing  = [f for f in required if not data.get(f, "").strip()]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    # Duplicate check
    if NGOProfile.query.filter_by(registration_no=data["registration_no"]).first():
        return jsonify({"error": "An NGO with this registration number already exists."}), 409

    # ── Geocoding: try LocationIQ / Nominatim, fallback to None ──────────────
    lat, lng = _geocode_address(data["address"])

    ngo = NGOProfile(
        name            = data["name"].strip(),
        registration_no = data["registration_no"].strip(),
        address         = data["address"].strip(),
        latitude        = lat,
        longitude       = lng,
        category_tags   = [c for c in data.get("category_tags", []) if c in VALID_CATEGORIES],
        contact_phone   = data.get("contact_phone", "").strip() or None,
        contact_email   = data.get("contact_email", "").strip() or None,
        verified        = False,
    )
    ngo.set_password(data["password"])
    db.session.add(ngo)
    db.session.commit()

    return jsonify({
        "message": "NGO registered successfully. Awaiting admin verification.",
        "ngo_id":  ngo.ngo_id,
        "token":   _ngo_token(ngo),
        "ngo":     ngo.to_dict(),
    }), 201


@ngo_bp.route("/login", methods=["POST"])
def login_ngo():
    """Authenticate NGO and return JWT."""
    data     = request.get_json() or {}
    reg_no   = data.get("registration_no", "").strip()
    password = data.get("password", "")

    if not reg_no or not password:
        return jsonify({"error": "registration_no and password are required."}), 400

    ngo = NGOProfile.query.filter_by(registration_no=reg_no).first()
    if not ngo or not ngo.check_password(password):
        return jsonify({"error": "Invalid credentials."}), 401

    return jsonify({
        "token":   _ngo_token(ngo),
        "ngo_id":  ngo.ngo_id,
        "name":    ngo.name,
        "verified": ngo.verified,
    })


# ── Authenticated NGO endpoints ────────────────────────────────────────────────

@ngo_bp.route("/dashboard", methods=["GET"])
@jwt_required()
def ngo_dashboard():
    """
    Full dashboard snapshot for the logged-in NGO:
      - Profile details
      - All needs entries
      - Incoming pledges (with donor name)
      - Summary stats
    """
    ngo = _current_ngo()
    if not ngo:
        return jsonify({"error": "NGO not found."}), 404

    needs   = [n.to_dict() for n in ngo.needs]
    pledges = []
    for p in PledgeRecord.query.filter_by(ngo_id=ngo.ngo_id).order_by(
        PledgeRecord.created_at.desc()
    ).limit(50).all():
        pd = p.to_dict()
        # Annotate with donor name
        from models.user_model import User
        donor    = User.query.get(p.donor_id)
        pd["donor_name"]  = donor.name  if donor else f"Donor #{p.donor_id}"
        pd["donor_email"] = donor.email if donor else ""
        pledges.append(pd)

    open_needs   = [n for n in ngo.needs if n.status != "closed"]
    pending_pledges = PledgeRecord.query.filter_by(ngo_id=ngo.ngo_id, status="pledged").count()
    delivered    = PledgeRecord.query.filter_by(ngo_id=ngo.ngo_id, status="delivered").count()

    return jsonify({
        "ngo":      ngo.to_dict(),
        "needs":    needs,
        "pledges":  pledges,
        "stats": {
            "open_needs":       len(open_needs),
            "pending_pledges":  pending_pledges,
            "total_delivered":  delivered,
        },
    })


# ── Needs Board CRUD ──────────────────────────────────────────────────────────

@ngo_bp.route("/needs", methods=["GET"])
@jwt_required()
def get_needs():
    """List this NGO's needs board entries, optionally filtered by status."""
    ngo = _current_ngo()
    if not ngo:
        return jsonify({"error": "NGO not found."}), 404

    status_filter = request.args.get("status", "").strip()
    needs = ngo.needs
    if status_filter:
        needs = [n for n in needs if n.status == status_filter]
    return jsonify({"needs": [n.to_dict() for n in needs], "total": len(needs)})


@ngo_bp.route("/needs", methods=["POST"])
@jwt_required()
def add_need():
    """
    Add a new needs board entry.

    Body (JSON):
        item_category      str  required  (one of VALID_CATEGORIES)
        quantity_needed    int  required  > 0
        urgency            str  optional  low|medium|high  (default medium)
        condition_accepted str  optional  new|used-good|any (default any)
        notes              str  optional
    """
    ngo = _current_ngo()
    if not ngo:
        return jsonify({"error": "NGO not found."}), 404

    data     = request.get_json() or {}
    category = data.get("item_category", "").strip()
    qty      = data.get("quantity_needed", 0)

    if category not in VALID_CATEGORIES:
        return jsonify({"error": f"item_category must be one of: {VALID_CATEGORIES}"}), 400
    if not isinstance(qty, int) or qty < 1:
        return jsonify({"error": "quantity_needed must be a positive integer."}), 400

    urgency   = data.get("urgency", "medium")
    condition = data.get("condition_accepted", "any")
    if urgency not in VALID_URGENCIES:
        urgency = "medium"
    if condition not in VALID_CONDITIONS:
        condition = "any"

    need = NeedsBoardEntry(
        ngo_id             = ngo.ngo_id,
        item_category      = category,
        quantity_needed    = qty,
        urgency            = urgency,
        condition_accepted = condition,
        notes              = data.get("notes", "").strip() or None,
        status             = "open",
        last_updated       = datetime.utcnow(),
    )
    db.session.add(need)
    db.session.commit()
    return jsonify({"message": "Need added.", "need": need.to_dict()}), 201


@ngo_bp.route("/needs/<need_id>", methods=["PUT"])
@jwt_required()
def update_need(need_id: str):
    """Update an existing need. Touching any field refreshes last_updated."""
    ngo = _current_ngo()
    if not ngo:
        return jsonify({"error": "NGO not found."}), 404

    need = NeedsBoardEntry.query.filter_by(need_id=need_id, ngo_id=ngo.ngo_id).first()
    if not need:
        return jsonify({"error": "Need not found."}), 404

    data = request.get_json() or {}
    if "quantity_needed" in data:
        qty = data["quantity_needed"]
        if isinstance(qty, int) and qty >= 1:
            need.quantity_needed = qty
    if "urgency" in data and data["urgency"] in VALID_URGENCIES:
        need.urgency = data["urgency"]
    if "condition_accepted" in data and data["condition_accepted"] in VALID_CONDITIONS:
        need.condition_accepted = data["condition_accepted"]
    if "notes" in data:
        need.notes = data["notes"].strip() or None

    need.last_updated = datetime.utcnow()  # explicit refresh
    need.sync_status()
    db.session.commit()
    return jsonify({"message": "Need updated.", "need": need.to_dict()})


@ngo_bp.route("/needs/<need_id>", methods=["DELETE"])
@jwt_required()
def delete_need(need_id: str):
    """Remove a need only if it has no active (non-cancelled) pledges."""
    ngo = _current_ngo()
    if not ngo:
        return jsonify({"error": "NGO not found."}), 404

    need = NeedsBoardEntry.query.filter_by(need_id=need_id, ngo_id=ngo.ngo_id).first()
    if not need:
        return jsonify({"error": "Need not found."}), 404

    active_pledges = PledgeRecord.query.filter(
        PledgeRecord.need_id == need_id,
        PledgeRecord.status.in_(["pledged", "in_transit"]),
    ).count()
    if active_pledges:
        return jsonify({
            "error": f"Cannot delete need with {active_pledges} active pledge(s). Cancel them first."
        }), 409

    db.session.delete(need)
    db.session.commit()
    return jsonify({"message": "Need deleted."})


# ── Pledge management (NGO side) ──────────────────────────────────────────────

@ngo_bp.route("/pledges", methods=["GET"])
@jwt_required()
def get_pledges():
    """List all incoming pledges for this NGO."""
    ngo = _current_ngo()
    if not ngo:
        return jsonify({"error": "NGO not found."}), 404

    status_filter = request.args.get("status", "").strip()
    query = PledgeRecord.query.filter_by(ngo_id=ngo.ngo_id).order_by(
        PledgeRecord.created_at.desc()
    )
    if status_filter:
        query = query.filter(PledgeRecord.status == status_filter)

    from models.user_model import User
    pledges = []
    for p in query.limit(100).all():
        pd = p.to_dict()
        donor = User.query.get(p.donor_id)
        pd["donor_name"]  = donor.name  if donor else f"Donor #{p.donor_id}"
        pd["donor_email"] = donor.email if donor else ""
        pledges.append(pd)

    return jsonify({"pledges": pledges, "total": len(pledges)})


@ngo_bp.route("/pledges/<pledge_id>/status", methods=["POST"])
@jwt_required()
def update_pledge_status(pledge_id: str):
    """
    Advance a pledge through its state machine.

    Body (JSON):
        status   str  required  One of: in_transit | delivered | cancelled

    State transitions allowed by NGO:
        pledged    → in_transit | cancelled
        in_transit → delivered  | cancelled

    Side effects:
        delivered  → NeedsBoardEntry.quantity_fulfilled += pledge.quantity
                     NeedsBoardEntry.quantity_pledged   -= pledge.quantity
                     NeedsBoardEntry.sync_status()
        cancelled  → NeedsBoardEntry.quantity_pledged   -= pledge.quantity
    """
    ngo = _current_ngo()
    if not ngo:
        return jsonify({"error": "NGO not found."}), 404

    pledge = PledgeRecord.query.filter_by(pledge_id=pledge_id, ngo_id=ngo.ngo_id).first()
    if not pledge:
        return jsonify({"error": "Pledge not found."}), 404

    data       = request.get_json() or {}
    new_status = data.get("status", "").strip()

    # Validate transition
    TRANSITIONS = {
        "pledged":    ["in_transit", "cancelled"],
        "in_transit": ["delivered",  "cancelled"],
    }
    allowed = TRANSITIONS.get(pledge.status, [])
    if new_status not in allowed:
        return jsonify({
            "error": f"Cannot transition from '{pledge.status}' to '{new_status}'. "
                     f"Allowed: {allowed}"
        }), 400

    # ── Apply side-effects on the linked NeedsBoardEntry ─────────────────────
    need = NeedsBoardEntry.query.get(pledge.need_id) if pledge.need_id else None

    if new_status == "delivered" and need:
        need.quantity_fulfilled = max(0, need.quantity_fulfilled + pledge.quantity)
        need.quantity_pledged   = max(0, need.quantity_pledged   - pledge.quantity)
        need.sync_status()

    elif new_status == "cancelled" and need:
        need.quantity_pledged = max(0, need.quantity_pledged - pledge.quantity)
        need.sync_status()

    pledge.status     = new_status
    pledge.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        "message":    f"Pledge status updated to '{new_status}'.",
        "pledge":     pledge.to_dict(),
        "need_status": need.status if need else None,
    })


# ── Geocoding helper ──────────────────────────────────────────────────────────

def _geocode_address(address: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Try to geocode an address string via Nominatim (OpenStreetMap).
    Returns (lat, lng) or (None, None) on failure.
    """
    try:
        import requests
        url    = "https://nominatim.openstreetmap.org/search"
        params = {"q": address, "format": "json", "limit": 1}
        resp   = requests.get(url, params=params, timeout=5,
                               headers={"User-Agent": "EcoCircle-NGO-Matcher/1.0"})
        results = resp.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception as e:
        logger.warning("[Geocode] Failed: %s", e)
    return None, None


# ── Tunable Matching Weights & AHP Preference Endpoints ──────────────────────

@ngo_bp.route("/matching-weights", methods=["GET"])
def get_matching_weights():
    """Returns available AHP presets and theoretical weight distribution."""
    from ml.ngo_matcher import AHP_PRESETS
    return jsonify({
        "status": "success",
        "description": "Multi-Criteria Decision Making (MCDM) / AHP Matching Weights",
        "presets": AHP_PRESETS,
        "default_weights": {"proximity": 0.40, "urgency": 0.30, "unmet": 0.30},
    }), 200


@ngo_bp.route("/matching-weights/ahp-calculate", methods=["POST"])
def calculate_ahp():
    """
    Computes normalized criteria weights from a 3x3 pairwise comparison matrix
    using Saaty's Analytic Hierarchy Process (AHP).
    Expected JSON: {"matrix": [[1, 3, 2], [0.333, 1, 0.5], [0.5, 2, 1]]}
    """
    data = request.get_json() or {}
    matrix = data.get("matrix")
    if not matrix or len(matrix) != 3 or any(len(row) != 3 for row in matrix):
        return jsonify({"error": "A 3x3 pairwise matrix is required for [proximity, urgency, unmet]."}), 400

    try:
        from ml.ngo_matcher import calculate_ahp_weights
        result = calculate_ahp_weights(matrix)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@ngo_bp.route("/matching-weights/calibrate", methods=["POST"])
def calibrate_weights():
    """
    Dynamic reinforcement tuning: Adjusts weights using NGO acceptance/rejection metrics.
    Expected JSON: {"base_weights": {...}, "accepted": 12, "rejected_distance": 3, "rejected_delay": 1}
    """
    data = request.get_json() or {}
    base = data.get("base_weights", {"proximity": 0.4, "urgency": 0.3, "unmet": 0.3})
    accepted = int(data.get("accepted", 0))
    rej_dist = int(data.get("rejected_distance", 0))
    rej_delay = int(data.get("rejected_delay", 0))

    from ml.ngo_matcher import calibrate_weights_from_feedback
    calibrated = calibrate_weights_from_feedback(base, accepted, rej_dist, rej_delay)
    return jsonify({
        "status": "success",
        "calibrated_weights": calibrated,
    }), 200
