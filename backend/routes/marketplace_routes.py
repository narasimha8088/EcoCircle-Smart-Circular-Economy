from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models.listing_model import Listing
from models.product_model import Product
from models.user_model import User
from models.eco_model import award_eco_points
from extensions import db
from routes.product_routes import _save_image

market_bp = Blueprint("marketplace", __name__)

@market_bp.route("/", methods=["GET"])
def get_listings():
    q        = request.args.get("q","").lower()
    category = request.args.get("category","")
    ltype    = request.args.get("type","")
    query    = Listing.query.filter_by(status="active")
    if q:        query = query.filter(Listing.title.ilike(f"%{q}%"))
    if category: query = query.filter_by(category=category)
    if ltype:    query = query.filter_by(listing_type=ltype)
    listings = query.order_by(Listing.created_at.desc()).all()
    return jsonify([l.to_dict() for l in listings])

@market_bp.route("/", methods=["POST"])
@jwt_required()
def create_listing():
    uid  = int(get_jwt_identity())
    user = User.query.get_or_404(uid)

    # Support both JSON and multipart/form-data
    if request.content_type and "multipart" in request.content_type:
        data = request.form
    else:
        data = request.get_json() or {}

    # ── Validate product_id ──────────────────────────────────────
    product_id = data.get("product_id")
    if product_id:
        try:
            product_id = int(product_id)
        except (ValueError, TypeError):
            product_id = None

    product_image = None
    if product_id:
        _p = Product.query.filter_by(id=product_id, owner_id=uid).first()
        if not _p:
            return jsonify({"error": "Product not found or does not belong to you."}), 404
        product_image = _p.image  # inherit product's photo

    # ── Handle uploaded image (overrides product image) ──────────
    listing_image = product_image
    img_file = request.files.get("image")
    if img_file and img_file.filename:
        saved = _save_image(img_file)
        if saved:
            listing_image = saved

    listing = Listing(
        product_id   = product_id or 0,
        seller_id    = uid,
        title        = data.get("title",""),
        description  = data.get("description",""),
        price        = float(data.get("price", 0) or 0),
        condition    = data.get("condition","Good"),
        category     = data.get("category",""),
        listing_type = data.get("listing_type","sell"),
        location     = data.get("location",""),
        image        = listing_image,
    )
    db.session.add(listing)
    # Track the item: it is now Listed for sale (shows in My Items + dashboard lifecycle)
    try:
        from routes.product_routes import set_stage
        _p = Product.query.filter_by(id=product_id, owner_id=uid).first()
        if _p:
            set_stage(_p, "Listed", f"Listed on marketplace as '{listing.title}'")
    except Exception as _e:
        print(f"[Track] could not update item stage: {_e}")
    pts = award_eco_points(user, "listed", category=listing.category,
                           description=f"Listed '{listing.title}' on marketplace")
    db.session.commit()
    return jsonify({
        "message":    "Listing created",
        "listing":    listing.to_dict(),
        "eco_points": pts,
        "eco_score":  user.eco_score,
    }), 201

@market_bp.route("/<int:lid>/buy", methods=["POST"])
@jwt_required()
def buy_listing(lid):
    uid     = int(get_jwt_identity())
    buyer   = User.query.get_or_404(uid)
    listing = Listing.query.filter_by(id=lid, status="active").first_or_404()
    if listing.seller_id == uid:
        return jsonify({"error": "Cannot buy your own listing"}), 400
    listing.status = "sold"
    pts = award_eco_points(buyer, "bought", category=listing.category,
                           description=f"Bought '{listing.title}' on marketplace")
    db.session.commit()
    return jsonify({
        "message":    "Purchase successful!",
        "eco_points": pts,
        "eco_score":  buyer.eco_score,
    })

@market_bp.route("/my", methods=["GET"])
@jwt_required()
def my_listings():
    uid = int(get_jwt_identity())
    listings = Listing.query.filter_by(seller_id=uid).order_by(Listing.created_at.desc()).all()
    return jsonify([l.to_dict() for l in listings])
