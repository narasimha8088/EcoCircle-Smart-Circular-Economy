import json
import os
import uuid
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from models.product_model import Product, ProductEvent, log_product_event
from models.user_model import User
from models.eco_model import award_eco_points, ECO_POINTS
from extensions import db
from datetime import datetime, timedelta

product_bp = Blueprint("products", __name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads", "products")
ALLOWED_EXTS  = {"jpg", "jpeg", "png", "webp", "gif"}

def _save_image(file) -> str | None:
    """Save an uploaded image file and return its relative URL path, or None on failure."""
    if not file or not file.filename:
        return None
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTS:
        return None
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    fname = f"{uuid.uuid4().hex}.{ext}"
    file.save(os.path.join(UPLOAD_FOLDER, fname))
    return f"/uploads/products/{fname}"

# Stages a user (or the platform) can move an item through. These are the same
# names the dashboard already counts, so tracking shows up there automatically.
VALID_STAGES = ["In Use", "Repaired", "Listed", "Donated", "Recycled", "Sold"]
_STAGE_LOOKUP = {s.lower(): s for s in VALID_STAGES}

_CATEGORY_KEYWORDS = [
    (("phone", "mobile", "smartphone", "iphone", "android"), "Mobile"),
    (("laptop", "notebook", "macbook", "chromebook"), "Laptop"),
    (("fridge", "refrigerator", "washing", "microwave", "oven", "mixer", "blender", "appliance",
      "fan", "cooler", "heater", "iron", "kettle", "vacuum"), "Appliance"),
    (("chair", "table", "sofa", "desk", "bed", "shelf", "cabinet", "wardrobe", "furniture"), "Furniture"),
    (("cloth", "shirt", "jacket", "jeans", "dress", "saree", "shoe", "footwear", "apparel",
      "textile", "sweater", "hoodie", "bag"), "Clothing"),
    (("book", "novel", "textbook", "magazine", "notebook", "stationery"), "Books"),
    (("toy", "game", "puzzle", "doll", "lego"), "Toys"),
    (("tablet", "tv", "television", "monitor", "keyboard", "mouse", "charger", "cable",
      "headphone", "earphone", "speaker", "camera", "electronic", "gadget", "watch", "console"), "Electronics"),
]


def normalize_category(raw: str) -> str:
    text = (raw or "").strip().lower()
    if not text:
        return "Other"
    for keywords, label in _CATEGORY_KEYWORDS:
        if any(k in text for k in keywords):
            return label
    return text.title()[:100]


def _num(value, default=0.0):
    try:
        f = float(value)
        return f if f == f else default      # NaN guard
    except (TypeError, ValueError):
        return default


def create_or_update_from_analysis(user, result: dict, description: str = "", analysis_ref: str = "",
                                   existing_product_id=None):
    """
    Turn an AI Analyzer result into a tracked item in "My Items".

    - Idempotent: the same analysis_ref never creates two items (page reloads,
      retries and tab switches are safe).
    - Caller is responsible for db.session.commit().
    Returns (product, created: bool, points: int)
    """
    result = result or {}
    used = ((result.get("input_received") or {}).get("used_by_models")) or {}
    phase2 = result.get("phase2") or {}
    carbon = (phase2.get("carbon") or {}) if isinstance(phase2, dict) else {}
    resale = (phase2.get("resale") or {}) if isinstance(phase2, dict) else {}

    name = (result.get("product_name") or "").strip() or "Scanned item"
    cond_raw = str(used.get("condition") or "").strip().lower()
    condition = {"new": "New", "good": "Good", "fair": "Fair", "poor": "Poor"}.get(cond_raw)
    if not condition:
        txt = str(result.get("condition_assessment") or "").lower()
        condition = next((c.title() for c in ("new", "good", "fair", "poor") if c in txt), "Good")

    age = _num(used.get("age_years"), 0.0)
    purchase_date = (datetime.utcnow() - timedelta(days=int(age * 365))).date() if age > 0 else None
    category = normalize_category(used.get("category") or result.get("category") or name)
    material = (str(result.get("material") or used.get("material") or "").strip().lower() or None)
    if material and len(material) > 100:
        material = material[:100]

    co2 = carbon.get("carbon_saved_kg") if isinstance(carbon, dict) else None
    price_est = resale.get("estimated_price") if isinstance(resale, dict) else None
    recommendation = str(result.get("recommendation") or "").strip() or None
    score = int(_num(result.get("sustainability_score"), 0))
    notes = (description or "").strip() or str(result.get("reason") or "")[:300]

    product = None
    attach_only = False
    if existing_product_id not in (None, ""):
        # The user analyzed an item that is already in My Items: attach the AI result to it
        try:
            product = Product.query.filter_by(id=int(existing_product_id), owner_id=user.id).first()
            attach_only = product is not None
        except (TypeError, ValueError):
            product = None
    if product is None and analysis_ref:
        product = Product.query.filter_by(owner_id=user.id, analysis_ref=analysis_ref).first()
    created = product is None

    if created:
        product = Product(
            name=name[:200], category=category, brand=str(used.get("brand") or "")[:100],
            description=notes, purchase_date=purchase_date, condition=condition,
            lifecycle_stage="In Use", purchase_price=_num(used.get("purchase_price")),
            weight_kg=_num(used.get("weight_kg")), owner_id=user.id, material=material,
            co2_saved_kg=_num(co2, None) if co2 is not None else None,
            resale_estimate=_num(price_est, None) if price_est is not None else None,
        )
        product.source = "ai_scan"
        product.analysis_ref = (analysis_ref or None)
        db.session.add(product)
        db.session.flush()          # need product.id for the timeline event
    elif attach_only:
        # keep what the user entered; only fill in what is missing
        if product.co2_saved_kg is None and co2 is not None:
            product.co2_saved_kg = _num(co2, None)
        if product.resale_estimate is None and price_est is not None:
            product.resale_estimate = _num(price_est, None)
        if not product.material and material:
            product.material = material
    else:
        product.name = name[:200]
        product.category = category
        product.condition = condition
        if co2 is not None:
            product.co2_saved_kg = _num(co2, None)
        if price_est is not None:
            product.resale_estimate = _num(price_est, None)

    product.ai_recommendation = recommendation
    product.ai_score = score
    try:
        product.ai_analysis = json.dumps(result, default=str)[:900000]
    except Exception:
        product.ai_analysis = None
    product.updated_at = datetime.utcnow()

    pts = 0
    if created:
        log_product_event(product, "Added", "Added automatically from your AI analysis")
        log_product_event(product, "AI analyzed",
                          f"Recommended: {recommendation or 'n/a'} · Score {score}/100")
        pts = award_eco_points(user, "added_item", category=category,
                               description=f"AI-scanned '{product.name}' added to My Items")
    else:
        log_product_event(product, "AI re-analyzed",
                          f"Recommended: {recommendation or 'n/a'} · Score {score}/100")
    return product, created, pts


def set_stage(product, stage: str, note: str = "") -> bool:
    """Move an item to a new lifecycle stage and record it. Caller commits."""
    stage = _STAGE_LOOKUP.get((stage or "").strip().lower())
    if not stage or (product.lifecycle_stage or "") == stage:
        return False
    product.lifecycle_stage = stage
    product.updated_at = datetime.utcnow()
    log_product_event(product, stage, note)
    return True


def _with_events(product, limit=8):
    d = product.to_dict()
    evs = (ProductEvent.query.filter_by(product_id=product.id)
           .order_by(ProductEvent.created_at.desc(), ProductEvent.id.desc()).limit(limit).all())
    d["events"] = [e.to_dict() for e in evs]
    return d


@product_bp.route("/", methods=["GET"])
@jwt_required()
def get_products():
    uid = int(get_jwt_identity())
    products = Product.query.filter_by(owner_id=uid).order_by(Product.created_at.desc(), Product.id.desc()).all()
    return jsonify([_with_events(p) for p in products])


@product_bp.route("/", methods=["POST"])
@jwt_required()
def add_product():
    uid = int(get_jwt_identity())
    user = User.query.get_or_404(uid)

    # Accept both multipart/form-data (with image) and application/json
    if request.content_type and "multipart" in request.content_type:
        data = request.form
        image_url = _save_image(request.files.get("image"))
    else:
        data = request.get_json() or {}
        image_url = None

    purchase_date = None
    if data.get("purchase_date"):
        try:
            purchase_date = datetime.strptime(data["purchase_date"], "%Y-%m-%d").date()
        except ValueError:
            pass

    p = Product(
        name=data.get("name", ""),
        category=data.get("category", ""),
        brand=data.get("brand", ""),
        description=data.get("description", ""),
        purchase_date=purchase_date,
        condition=data.get("condition", "Good"),
        lifecycle_stage=_STAGE_LOOKUP.get(str(data.get("lifecycle_stage", "In Use")).lower(), "In Use"),
        purchase_price=_num(data.get("purchase_price")),
        weight_kg=_num(data.get("weight_kg")),
        material=data.get("material") or None,
        owner_id=uid,
        image=image_url,
    )
    p.source = "manual"
    db.session.add(p)
    db.session.flush()
    log_product_event(p, "Added", "Added manually")
    pts = award_eco_points(user, "added_item", category=p.category,
                           description=f"Added '{p.name}' to inventory")
    db.session.commit()
    return jsonify({
        "message": "Product added",
        "product": _with_events(p),
        "eco_points": pts,
        "eco_score": user.eco_score,
    }), 201


@product_bp.route("/from-analysis", methods=["POST"])
@jwt_required()
def add_from_analysis():
    """Save (or refresh) the item behind an AI analysis. Safe to call more than once."""
    uid = int(get_jwt_identity())
    user = User.query.get_or_404(uid)
    data = request.get_json() or {}
    analysis = data.get("analysis")
    if not isinstance(analysis, dict):
        return jsonify({"error": "analysis object is required."}), 400
    product, created, pts = create_or_update_from_analysis(
        user, analysis, data.get("description", ""), str(data.get("analysis_ref") or "")[:64])
    db.session.commit()
    return jsonify({"product": _with_events(product), "created": created,
                    "eco_points": pts, "eco_score": user.eco_score}), 201 if created else 200


@product_bp.route("/by-analysis/<ref>", methods=["GET"])
@jwt_required()
def by_analysis(ref):
    """Lets the AI Engine page recover a finished analysis after the user left the page mid-request."""
    uid = int(get_jwt_identity())
    p = Product.query.filter_by(owner_id=uid, analysis_ref=ref[:64]).first()
    if not p:
        return jsonify({"found": False}), 404
    try:
        analysis = json.loads(p.ai_analysis) if p.ai_analysis else None
    except ValueError:
        analysis = None
    return jsonify({"found": True, "product": _with_events(p), "analysis": analysis})


@product_bp.route("/<int:pid>", methods=["PUT"])
@jwt_required()
def update_product(pid):
    uid = int(get_jwt_identity())
    user = User.query.get_or_404(uid)
    p = Product.query.filter_by(id=pid, owner_id=uid).first_or_404()
    data = request.get_json() or {}

    old_stage = (p.lifecycle_stage or "").lower()
    for field in ("name", "category", "brand", "description", "condition", "weight_kg"):
        if field in data:
            setattr(p, field, data[field])
    if "lifecycle_stage" in data:
        set_stage(p, data["lifecycle_stage"], data.get("note") or "Updated by you")

    # Award eco points for meaningful lifecycle transitions
    new_stage = (p.lifecycle_stage or "").lower()
    pts = 0
    stage_action_map = {
        "repaired": ("repaired", f"Repaired '{p.name}'"),
        "recycled": ("recycled", f"Recycled '{p.name}'"),
        "donated":  ("donated",  f"Donated '{p.name}'"),
        "sold":     ("sold",     f"Sold '{p.name}'"),
    }
    if new_stage != old_stage and new_stage in stage_action_map:
        action, desc = stage_action_map[new_stage]
        pts = award_eco_points(user, action, category=p.category, description=desc)

    p.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "Updated", "product": _with_events(p), "eco_points": pts})


@product_bp.route("/<int:pid>/events", methods=["GET"])
@jwt_required()
def product_events(pid):
    uid = int(get_jwt_identity())
    Product.query.filter_by(id=pid, owner_id=uid).first_or_404()
    evs = (ProductEvent.query.filter_by(product_id=pid)
           .order_by(ProductEvent.created_at.desc(), ProductEvent.id.desc()).all())
    return jsonify({"events": [e.to_dict() for e in evs]})


@product_bp.route("/<int:pid>", methods=["DELETE"])
@jwt_required()
def delete_product(pid):
    uid = int(get_jwt_identity())
    p = Product.query.filter_by(id=pid, owner_id=uid).first_or_404()
    ProductEvent.query.filter_by(product_id=pid).delete()
    try:
        from models.donation_model import DonationRecord
        DonationRecord.query.filter_by(product_id=pid).update({"product_id": None})
    except Exception:
        pass
    try:
        from models.listing_model import Listing
        Listing.query.filter_by(product_id=pid).delete()
    except Exception:
        pass
    db.session.delete(p)
    db.session.commit()
    return jsonify({"message": "Deleted"})
