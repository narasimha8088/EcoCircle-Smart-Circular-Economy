from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models.repair_model import RepairCenter
from models.user_model import User
from models.eco_model import award_eco_points
from extensions import db

repair_bp = Blueprint("repair", __name__)

@repair_bp.route("/centers", methods=["GET"])
def get_centers():
    centers = RepairCenter.query.order_by(RepairCenter.rating.desc()).all()
    return jsonify([c.to_dict() for c in centers])

@repair_bp.route("/centers", methods=["POST"])
@jwt_required()
def add_center():
    uid  = int(get_jwt_identity())
    user = User.query.get_or_404(uid)
    if not user.is_admin:
        return jsonify({"error": "Admin access required to add repair centers."}), 403
    data = request.get_json()
    c = RepairCenter(
        name=data.get("name"), location=data.get("location"),
        service_type=data.get("service_type"), rating=data.get("rating", 0),
        lat=data.get("lat", 0), lng=data.get("lng", 0), contact=data.get("contact", "")
    )
    db.session.add(c)
    db.session.commit()
    return jsonify(c.to_dict()), 201

@repair_bp.route("/log", methods=["POST"])
@jwt_required()
def log_repair():
    """User logs a completed repair and earns eco points."""
    uid  = int(get_jwt_identity())
    user = User.query.get_or_404(uid)
    data = request.get_json() or {}
    category = data.get("category", "other")
    item_name = data.get("item_name", "item")

    pts = award_eco_points(user, "repaired", category=category,
                           description=f"Repaired {item_name}")
    db.session.commit()
    return jsonify({
        "message":    f"Repair logged! You earned +{pts} eco points 🌱",
        "eco_points": pts,
        "eco_score":  user.eco_score,
    })

@repair_bp.route("/book", methods=["POST"])
@jwt_required()
def book_repair():
    """Book a repair appointment at a repair center."""
    uid  = int(get_jwt_identity())
    user = User.query.get_or_404(uid)
    data = request.get_json() or {}

    center_id     = data.get("center_id")
    item_name     = data.get("item_name", "item")
    category      = data.get("category", "other")
    preferred_date = data.get("preferred_date", "Within 3 working days")

    center = RepairCenter.query.get(center_id) if center_id else None
    center_name = center.name if center else "Selected Repair Center"

    pts = award_eco_points(user, "repair_booked", category=category,
                           description=f"Booked repair for {item_name} at {center_name}")
    db.session.commit()

    return jsonify({
        "message":        f"Repair appointment booked at {center_name}!",
        "confirmation":   f"REP-{uid}-{center_id or 0}",
        "scheduled_date": preferred_date,
        "center_name":    center_name,
        "eco_points":     pts,
        "eco_score":      user.eco_score,
        "next_steps":     f"The center will confirm your appointment. Contact: {center.contact if center else 'N/A'}",
    })

@repair_bp.route("/cost-estimate", methods=["POST"])
def cost_estimate():
    """Simple heuristic repair cost estimate."""
    data     = request.get_json()
    category = data.get("category", "").lower()
    ESTIMATES = {
        "mobile":      {"min": 500,  "max": 3000},
        "laptop":      {"min": 1000, "max": 8000},
        "appliance":   {"min": 500,  "max": 5000},
        "electronics": {"min": 300,  "max": 4000},
        "furniture":   {"min": 200,  "max": 3000},
    }
    est = ESTIMATES.get(category, {"min": 300, "max": 2000})
    return jsonify({"category": category, "estimated_min": est["min"],
                    "estimated_max": est["max"],
                    "note": "Actual cost depends on damage extent."})
