from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models.recycling_model import RecyclingCenter
from models.user_model import User
from models.eco_model import award_eco_points
from extensions import db

recycle_bp = Blueprint("recycling", __name__)

@recycle_bp.route("/centers", methods=["GET"])
def get_centers():
    centers = RecyclingCenter.query.all()
    return jsonify([c.to_dict() for c in centers])

@recycle_bp.route("/classify", methods=["POST"])
def classify_waste():
    data     = request.get_json()
    material = data.get("material", "").lower()
    CLASSES  = {
        "plastic":     {"type": "Recyclable",     "bin": "Blue",         "tip": "Clean before recycling"},
        "glass":       {"type": "Recyclable",     "bin": "Green",        "tip": "Remove lids"},
        "paper":       {"type": "Recyclable",     "bin": "Blue",         "tip": "Keep dry"},
        "metal":       {"type": "Recyclable",     "bin": "Yellow",       "tip": "Rinse cans"},
        "electronics": {"type": "E-Waste",        "bin": "Special E-Waste", "tip": "Take to e-waste centre"},
        "battery":     {"type": "Hazardous",      "bin": "Red",          "tip": "Never throw in general bin"},
        "food":        {"type": "Organic",        "bin": "Brown",        "tip": "Good for composting"},
        "cloth":       {"type": "Donate/Recycle", "bin": "Textile",      "tip": "Donate if still wearable"},
    }
    result = CLASSES.get(material, {"type": "General Waste", "bin": "Black", "tip": "Check local guidelines"})
    return jsonify({"material": material, **result})

@recycle_bp.route("/schedule-pickup", methods=["POST"])
@jwt_required()
def schedule_pickup():
    """Schedule a recycling pickup and award eco points."""
    uid  = int(get_jwt_identity())
    user = User.query.get_or_404(uid)
    data = request.get_json() or {}

    center_id      = data.get("center_id")
    category       = data.get("category", "other")
    item_name      = data.get("item_name", "item")
    preferred_date = data.get("preferred_date", "Within 3 working days")

    center = RecyclingCenter.query.get(center_id) if center_id else None
    center_name = center.name if center else "Selected Recycling Center"

    pts = award_eco_points(user, "recycle_booked", category=category,
                           description=f"Scheduled recycling pickup for {item_name} at {center_name}")
    db.session.commit()

    return jsonify({
        "message":        f"Recycling pickup scheduled at {center_name}!",
        "confirmation":   f"PICKUP-{uid}-{center_id or data.get('product_id', 0)}",
        "scheduled_date": preferred_date,
        "center_name":    center_name,
        "eco_points":     pts,
        "eco_score":      user.eco_score,
        "next_steps":     f"You'll receive a confirmation call. Contact: {center.contact if center else 'N/A'}",
    })
