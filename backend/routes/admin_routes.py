from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from models.user_model import User
from models.product_model import Product
from models.listing_model import Listing
from models.ngo_model import NGOProfile, NeedsBoardEntry, PledgeRecord
from models.eco_model import EcoAction
from extensions import db

admin_bp = Blueprint("admin", __name__)


def _require_admin():
    uid  = int(get_jwt_identity())
    user = User.query.get(uid)
    return user if (user and user.is_admin) else None


# ── Platform Stats ──────────────────────────────────────────────────────────

@admin_bp.route("/stats", methods=["GET"])
@jwt_required()
def admin_stats():
    if not _require_admin():
        return jsonify({"error": "Admin only"}), 403

    total_eco_pts = db.session.query(db.func.sum(User.eco_score)).scalar() or 0
    total_actions = EcoAction.query.count()

    return jsonify({
        "total_users":       User.query.count(),
        "total_products":    Product.query.count(),
        "active_listings":   Listing.query.filter_by(status="active").count(),
        "sold_listings":     Listing.query.filter_by(status="sold").count(),
        "total_ngos":        NGOProfile.query.count(),
        "verified_ngos":     NGOProfile.query.filter_by(verified=True).count(),
        "pending_ngos":      NGOProfile.query.filter_by(verified=False).count(),
        "total_pledges":     PledgeRecord.query.count(),
        "delivered_pledges": PledgeRecord.query.filter_by(status="delivered").count(),
        "total_eco_points":  int(total_eco_pts),
        "total_eco_actions": total_actions,
    })


# ── User Management ─────────────────────────────────────────────────────────

@admin_bp.route("/users", methods=["GET"])
@jwt_required()
def list_users():
    if not _require_admin():
        return jsonify({"error": "Admin only"}), 403
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify([u.to_dict() for u in users])


@admin_bp.route("/users/<int:uid>/toggle-admin", methods=["POST"])
@jwt_required()
def toggle_admin(uid):
    if not _require_admin():
        return jsonify({"error": "Admin only"}), 403
    target = User.query.get_or_404(uid)
    target.is_admin = not target.is_admin
    db.session.commit()
    return jsonify({"message": f"Admin status updated", "is_admin": target.is_admin, "user": target.to_dict()})


# ── Listings Management ─────────────────────────────────────────────────────

@admin_bp.route("/listings", methods=["GET"])
@jwt_required()
def list_all_listings():
    if not _require_admin():
        return jsonify({"error": "Admin only"}), 403
    listings = Listing.query.order_by(Listing.created_at.desc()).all()
    return jsonify([l.to_dict() for l in listings])


@admin_bp.route("/listing/<int:lid>", methods=["DELETE"])
@jwt_required()
def remove_listing(lid):
    if not _require_admin():
        return jsonify({"error": "Admin only"}), 403
    listing = Listing.query.get_or_404(lid)
    db.session.delete(listing)
    db.session.commit()
    return jsonify({"message": "Listing removed"})


# ── NGO Management ──────────────────────────────────────────────────────────

@admin_bp.route("/ngos", methods=["GET"])
@jwt_required()
def list_ngos():
    """List all NGOs (verified and pending)."""
    if not _require_admin():
        return jsonify({"error": "Admin only"}), 403
    ngos = NGOProfile.query.order_by(NGOProfile.created_at.desc()).all()
    return jsonify([n.to_dict() for n in ngos])


@admin_bp.route("/ngos/<ngo_id>/verify", methods=["POST"])
@jwt_required()
def verify_ngo(ngo_id):
    """Approve or revoke NGO verification."""
    if not _require_admin():
        return jsonify({"error": "Admin only"}), 403
    ngo = NGOProfile.query.get_or_404(ngo_id)
    data = request.get_json() or {}
    ngo.verified = data.get("verified", True)
    db.session.commit()
    status = "verified" if ngo.verified else "unverified"
    return jsonify({
        "message": f"NGO '{ngo.name}' has been {status}.",
        "ngo_id":  ngo.ngo_id,
        "verified": ngo.verified,
    })


@admin_bp.route("/ngos/<ngo_id>", methods=["DELETE"])
@jwt_required()
def delete_ngo(ngo_id):
    """Remove an NGO from the platform."""
    if not _require_admin():
        return jsonify({"error": "Admin only"}), 403
    ngo = NGOProfile.query.get_or_404(ngo_id)
    db.session.delete(ngo)
    db.session.commit()
    return jsonify({"message": f"NGO '{ngo.name}' removed."})


# ── Activity Log ────────────────────────────────────────────────────────────

@admin_bp.route("/eco-actions", methods=["GET"])
@jwt_required()
def eco_actions():
    """Recent platform-wide eco actions."""
    if not _require_admin():
        return jsonify({"error": "Admin only"}), 403
    actions = EcoAction.query.order_by(EcoAction.created_at.desc()).limit(50).all()
    result = []
    for a in actions:
        d = a.to_dict()
        user = User.query.get(a.user_id)
        d["user_name"]   = user.name if user else "?"
        d["user_number"] = user.user_number if user else "?"
        result.append(d)
    return jsonify({"actions": result})


# ── Pilot Evaluation & Field Telemetry ──────────────────────────────────────

@admin_bp.route("/pilot-report", methods=["GET"])
def get_pilot_report():
    """
    Returns aggregate performance analytics from the 4-week field pilot study
    conducted across 5 Bangalore partner NGOs for KSCST grant evaluation.
    Publicly accessible or admin-auditable for evaluator review.
    """
    try:
        from scripts.generate_pilot_report import analyze_pilot_performance
        report = analyze_pilot_performance()
        return jsonify(report), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
