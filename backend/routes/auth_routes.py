from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from models.user_model import User
from extensions import db
from datetime import datetime
import json, math, random, string
from sqlalchemy import or_

auth_bp = Blueprint("auth", __name__)

# ─────────────────────────────────────────────────────────────
# Standard Auth Routes
# ─────────────────────────────────────────────────────────────

@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    if not data or not all(k in data for k in ("name","email","password")):
        return jsonify({"error": "name, email and password are required"}), 400

    if User.query.filter_by(email=data["email"]).first():
        return jsonify({"error": "Email already registered"}), 409

    # Generate unique user_number
    while True:
        rand_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        user_num = f"ECO-{rand_str}"
        if not User.query.filter_by(user_number=user_num).first():
            break

    user = User(name=data["name"], email=data["email"],
                user_number=user_num, location=data.get("location",""))
    user.set_password(data["password"])
    user.last_login = datetime.utcnow()
    db.session.add(user)
    db.session.commit()

    token = create_access_token(identity=str(user.id))
    return jsonify({"message": "Registered successfully", "token": token,
                    "user": user.to_dict()}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    identifier = data.get("email", "").strip()
    
    user = User.query.filter(
        or_(User.email == identifier, User.user_number == identifier)
    ).first()
    
    if not user or not user.check_password(data.get("password","")):
        return jsonify({"error": "Invalid email/ID or password"}), 401

    user.last_login = datetime.utcnow()
    user.update_streak()
    db.session.commit()
    token = create_access_token(identity=str(user.id))
    return jsonify({"token": token, "user": user.to_dict()})


@auth_bp.route("/profile", methods=["GET"])
@jwt_required()
def profile():
    uid  = int(get_jwt_identity())
    user = User.query.get_or_404(uid)
    return jsonify(user.to_dict())


@auth_bp.route("/profile", methods=["PUT"])
@jwt_required()
def update_profile():
    uid  = int(get_jwt_identity())
    user = User.query.get_or_404(uid)
    data = request.get_json()
    if "name"     in data: user.name     = data["name"]
    if "location" in data: user.location = data["location"]
    db.session.commit()
    return jsonify({"message": "Profile updated", "user": user.to_dict()})


# ─────────────────────────────────────────────────────────────
# Camera Face Authentication Routes
# Face detection & descriptor generation happens fully in the
# browser (face-api.js / WebGL). The server only stores and
# compares the 128-float descriptor vector.
# ─────────────────────────────────────────────────────────────

FACE_MATCH_THRESHOLD  = 0.45   # Euclidean distance; must be BELOW this to accept
FACE_MARGIN_MIN       = 0.08   # Best match must beat second-best by this margin (prevents ambiguous matches between similar users)


def _euclidean_distance(a: list, b: list) -> float:
    """Euclidean distance between two 128-float face descriptors."""
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


# ── 1. Save Face Descriptor (Registration) ───────────────────
@auth_bp.route("/face/save-descriptor", methods=["POST"])
@jwt_required()
def face_save_descriptor():
    """
    Accepts a 128-float face descriptor captured by the browser
    (face-api.js) and persists it against the authenticated user.

    Body: { "descriptor": [f1, f2, ..., f128] }
    """
    uid  = int(get_jwt_identity())
    user = User.query.get_or_404(uid)
    data = request.get_json()

    descriptor = data.get("descriptor")
    if not descriptor or not isinstance(descriptor, list) or len(descriptor) != 128:
        return jsonify({"error": "A valid 128-element face descriptor array is required."}), 400

    user.face_descriptor = json.dumps(descriptor)
    db.session.commit()

    return jsonify({
        "message": "Face enrolled successfully! You can now use Face Login.",
        "user": user.to_dict()
    }), 200


# ── 2. Face Login  ────────────────────────────────────────────
@auth_bp.route("/face/login", methods=["POST"])
def face_login():
    """
    Matches the submitted face descriptor against all enrolled users.
    Returns a JWT on success.

    Body: { "descriptor": [f1, ..., f128] }
    (Optionally) Body: { "email": "...", "descriptor": [...] }
      — providing email restricts the search to one user for speed.
    """
    data = request.get_json()
    descriptor = data.get("descriptor")
    if not descriptor or not isinstance(descriptor, list) or len(descriptor) != 128:
        return jsonify({"error": "A valid 128-element face descriptor array is required."}), 400

    email_hint = data.get("email", "").strip()

    # Build candidate set
    if email_hint:
        candidates = User.query.filter(
            or_(User.email == email_hint, User.user_number == email_hint),
            User.face_descriptor.isnot(None)
        ).all()
    else:
        candidates = User.query.filter(User.face_descriptor.isnot(None)).all()

    if not candidates:
        return jsonify({"error": "No enrolled face found. Please enroll first from your Profile page."}), 404

    best_user     = None
    best_distance = float("inf")
    second_best   = float("inf")

    for candidate in candidates:
        try:
            stored = json.loads(candidate.face_descriptor)
        except (json.JSONDecodeError, TypeError):
            continue
        if len(stored) != 128:
            continue
        dist = _euclidean_distance(descriptor, stored)
        if dist < best_distance:
            second_best   = best_distance
            best_distance = dist
            best_user     = candidate
        elif dist < second_best:
            second_best = dist

    # Reject if no match found or distance above threshold
    if best_user is None or best_distance > FACE_MATCH_THRESHOLD:
        return jsonify({
            "error": "Face not recognised. Please try again or use your password.",
        }), 401

    # Reject if two users are ambiguously similar (margin too small)
    if second_best < float("inf") and (second_best - best_distance) < FACE_MARGIN_MIN:
        return jsonify({
            "error": "Face match is ambiguous. Please enter your email first to assist recognition.",
        }), 401

    best_user.last_login = datetime.utcnow()
    best_user.update_streak()
    db.session.commit()
    token = create_access_token(identity=str(best_user.id))
    return jsonify({
        "message": f"Welcome back, {best_user.name}!",
        "token":   token,
        "user":    best_user.to_dict()
    }), 200


# ── 3. Disable Face Login  ────────────────────────────────────
@auth_bp.route("/face/disable", methods=["DELETE"])
@jwt_required()
def face_disable():
    """Remove the stored face descriptor for the authenticated user."""
    uid  = int(get_jwt_identity())
    user = User.query.get_or_404(uid)
    user.face_descriptor = None
    db.session.commit()
    return jsonify({"message": "Face Login disabled.", "user": user.to_dict()}), 200

