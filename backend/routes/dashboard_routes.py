from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models.user_model import User
from models.product_model import Product
from models.listing_model import Listing
from models.eco_model import EcoAction
from extensions import db
from datetime import datetime, timezone
import time

dashboard_bp = Blueprint("dashboard", __name__)

# ── Simple in-memory TTL cache for /stats ──────────────────────
# Avoids re-running the ML carbon estimator on every page load.
_stats_cache = {}          # uid → (timestamp, result)
_STATS_TTL   = 60          # seconds before cache expires


@dashboard_bp.route("/stats", methods=["GET"])
@jwt_required()
def stats():
    uid = int(get_jwt_identity())

    # ── Return cached result if fresh ─────────────────────────
    cached = _stats_cache.get(uid)
    if cached and (time.time() - cached[0]) < _STATS_TTL:
        return jsonify(cached[1])

    user     = User.query.get_or_404(uid)
    products = Product.query.filter_by(owner_id=uid).all()
    listings = Listing.query.filter_by(seller_id=uid).all()

    sold_count    = sum(1 for l in listings if l.status == "sold")

    # Donations count — from EcoAction log first, then fallback
    try:
        donated_count = EcoAction.query.filter_by(
            user_id=uid, action_type="donated"
        ).count()
    except Exception:
        donated_count = sum(1 for p in products if (p.lifecycle_stage or "").lower() == "donated")

    # ── Carbon saved via Phase 2 M5 (per product) ─────────────────────────────
    carbon_saved = 0.0
    try:
        from ml.carbon_estimator import predict as carbon_predict
        for p in products:
            stage = (p.lifecycle_stage or "in use").lower()
            action = "recycle" if stage == "recycled" else "reuse"
            res = carbon_predict(
                category  = (p.category or "other").lower(),
                material  = (p.material  or "other").lower(),
                weight_kg = p.weight_kg  or 1.0,
                action    = action,
            )
            carbon_saved += res.get("carbon_saved_kg", 0)
    except Exception:
        # Fallback: rough formula
        carbon_saved = sum(p.weight_kg * 30 for p in products if p.weight_kg)

    # ── Eco score from DB (real persisted value) ───────────────────────────────
    eco_score = user.eco_score or 0

    # ── Login streak (real consecutive-day value) ──────────────────────────────
    streak = user.login_streak or 0

    # ── Lifecycle breakdown ───────────────────────────────────────────────────
    lifecycle = {}
    for p in products:
        stage = p.lifecycle_stage or "In Use"
        lifecycle[stage] = lifecycle.get(stage, 0) + 1

    # ── Phase 2 M7 eco-trend ──────────────────────────────────────────────────
    # Build history from EcoAction log (real data)
    user_history = []
    try:
        actions = EcoAction.query.filter_by(user_id=uid).order_by(EcoAction.created_at).all()
        for a in actions:
            user_history.append({
                "action":    a.action_type,
                "category":  a.category or "other",
                "timestamp": a.created_at.strftime("%Y-%m-%d"),
            })
    except Exception:
        pass

    eco_trend_data = None
    try:
        from ml.eco_trend_model import predict_trend
        eco_trend_data = predict_trend(user_history)
    except Exception:
        pass

    resp_data = {
        "user":             user.to_dict(),
        "total_products":   len(products),
        "items_sold":       sold_count,
        "items_donated":    donated_count,
        "carbon_saved_kg":  round(carbon_saved, 1),
        "lifecycle_stages": lifecycle,
        "eco_score":        eco_score,
        "streak":           streak,
        "badge_label":      user.badge()["label"],
        "badge_level":      user.badge()["level"],
        "eco_trend":        eco_trend_data,
    }
    _stats_cache[uid] = (time.time(), resp_data)
    return jsonify(resp_data)


@dashboard_bp.route("/eco-trend", methods=["GET"])
@jwt_required()
def eco_trend():
    """Returns 30-day eco-score forecast using real EcoAction history."""
    uid = int(get_jwt_identity())

    user_history = []
    try:
        actions = EcoAction.query.filter_by(user_id=uid).order_by(EcoAction.created_at).all()
        for a in actions:
            user_history.append({
                "action":    a.action_type,
                "category":  a.category or "other",
                "timestamp": a.created_at.strftime("%Y-%m-%d"),
            })
    except Exception:
        pass

    try:
        from ml.eco_trend_model import predict_trend
        result = predict_trend(user_history, forecast_days=30)
        return jsonify({"status": "success", **result})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e), "eco_trend": None}), 500


@dashboard_bp.route("/leaderboard", methods=["GET"])
def leaderboard():
    """Top 10 users by eco_score for platform leaderboard. Public endpoint."""
    top_users = User.query.order_by(User.eco_score.desc()).limit(10).all()
    board = []
    for rank, u in enumerate(top_users, start=1):
        board.append({
            "rank":        rank,
            "name":        u.name,
            "user_number": u.user_number,
            "eco_score":   u.eco_score or 0,
            "badge_label": u.badge()["label"],
            "badge_level": u.badge()["level"],
            "location":    u.location or "",
        })
    return jsonify({"leaderboard": board, "total": len(board)})


@dashboard_bp.route("/activity", methods=["GET"])
@jwt_required()
def activity_feed():
    """Recent eco actions for the profile activity feed."""
    uid = int(get_jwt_identity())
    try:
        actions = EcoAction.query.filter_by(user_id=uid)\
            .order_by(EcoAction.created_at.desc()).limit(20).all()
        return jsonify({
            "actions": [a.to_dict() for a in actions],
            "total":   len(actions),
        })
    except Exception as e:
        return jsonify({"actions": [], "error": str(e)}), 500
