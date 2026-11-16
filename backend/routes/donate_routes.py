from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models.user_model import User
from models.eco_model import award_eco_points
from extensions import db
from datetime import datetime
from urllib.parse import quote

donate_bp = Blueprint("donate", __name__)


def _clean_phone(raw) -> str:
    return "".join(ch for ch in str(raw or "") if ch.isdigit() or ch == "+")


def build_contact(name, phone="", email="", address="", lat=None, lng=None, open_now=None) -> dict:
    """Everything a donor needs to actually reach the NGO (call / WhatsApp / directions)."""
    digits = _clean_phone(phone)
    wa_num = digits.lstrip("+")
    if wa_num and len(wa_num) == 10:
        wa_num = "91" + wa_num                       # Indian mobile numbers
    if lat is not None and lng is not None:
        maps = f"https://www.google.com/maps/dir/?api=1&destination={lat},{lng}"
    elif address:
        maps = f"https://www.google.com/maps/search/?api=1&query={quote(str(name) + ' ' + str(address))}"
    else:
        maps = ""
    return {
        "name": name, "phone": phone or "", "email": email or "", "address": address or "",
        "lat": lat, "lng": lng, "open": open_now,
        "call_url":     f"tel:{digits}" if digits else "",
        "whatsapp_url": f"https://wa.me/{wa_num}" if wa_num else "",
        "email_url":    f"mailto:{email}" if email else "",
        "maps_url":     maps,
    }


def contact_from_static(ngo: dict) -> dict:
    return build_contact(ngo["name"], ngo.get("contact", ""), "", ngo.get("location", ""),
                         ngo.get("lat"), ngo.get("lng"), ngo.get("open"))


def contact_from_profile(ngo) -> dict:
    return build_contact(ngo.name, ngo.contact_phone or "", ngo.contact_email or "", ngo.address or "",
                         ngo.latitude, ngo.longitude, True)

# ── Static NGO data (replace with DB later) ───────────────────────────────────
NGO_LIST = [
    {"id": 1,  "name": "Clothes for All",      "category": "Clothes",     "location": "Koramangala, Bengaluru",     "lat": 12.9352, "lng": 77.6245, "urgency": 92, "needs": ["Clothes", "Blankets", "Shoes"],             "contact": "9876501234", "open": True},
    {"id": 2,  "name": "HelpHands Foundation", "category": "Clothes",     "location": "Indiranagar, Bengaluru",     "lat": 12.9784, "lng": 77.6408, "urgency": 78, "needs": ["Clothes", "Food", "Toys"],                  "contact": "9845098765", "open": True},
    {"id": 3,  "name": "Goonj Donation Hub",   "category": "Clothes",     "location": "HSR Layout, Bengaluru",      "lat": 12.9116, "lng": 77.6474, "urgency": 85, "needs": ["Clothes", "Utensils", "Books"],              "contact": "9900001111", "open": True},
    {"id": 4,  "name": "Book Bridge NGO",       "category": "Books",       "location": "Whitefield, Bengaluru",      "lat": 12.9698, "lng": 77.7499, "urgency": 96, "needs": ["Books", "Stationery", "Uniforms"],           "contact": "9741234567", "open": True},
    {"id": 5,  "name": "EduReach India",        "category": "Books",       "location": "Marathahalli, Bengaluru",    "lat": 12.9591, "lng": 77.6972, "urgency": 71, "needs": ["Books", "Tablets", "Bags"],                  "contact": "9632587410", "open": True},
    {"id": 6,  "name": "Read & Rise",           "category": "Books",       "location": "Yelahanka, Bengaluru",       "lat": 13.1007, "lng": 77.5963, "urgency": 60, "needs": ["Books", "Pencils", "Notebooks"],             "contact": "8012345678", "open": False},
    {"id": 7,  "name": "TechForAll India",      "category": "Electronics", "location": "Electronic City, Bengaluru", "lat": 12.8399, "lng": 77.6770, "urgency": 88, "needs": ["Laptops", "Phones", "Chargers"],            "contact": "9856321470", "open": True},
    {"id": 8,  "name": "Digital Inclusion",     "category": "Electronics", "location": "Jayanagar, Bengaluru",       "lat": 12.9250, "lng": 77.5938, "urgency": 75, "needs": ["Tablets", "Keyboards", "Cables"],           "contact": "9741852963", "open": True},
    {"id": 9,  "name": "ConnectKids NGO",       "category": "Electronics", "location": "JP Nagar, Bengaluru",        "lat": 12.9111, "lng": 77.5850, "urgency": 65, "needs": ["Computers", "Headphones", "Mice"],          "contact": "8765432109", "open": True},
    {"id": 10, "name": "Shelter India",         "category": "Furniture",   "location": "Malleshwaram, Bengaluru",    "lat": 13.0027, "lng": 77.5714, "urgency": 82, "needs": ["Furniture", "Mats", "Curtains"],             "contact": "9988776655", "open": True},
    {"id": 11, "name": "Smiles Foundation",     "category": "Toys",        "location": "Basavanagudi, Bengaluru",    "lat": 12.9416, "lng": 77.5729, "urgency": 89, "needs": ["Toys", "Games", "Clothes"],                  "contact": "9845671230", "open": True},
    {"id": 12, "name": "ChildJoy NGO",          "category": "Toys",        "location": "Vijayanagar, Bengaluru",     "lat": 12.9719, "lng": 77.5354, "urgency": 76, "needs": ["Toys", "Books", "Crayons"],                  "contact": "8012309876", "open": True},
]


# ── GET /api/donate/ngos ──────────────────────────────────────────────────────
def _haversine_km(lat1, lng1, lat2, lng2) -> float:
    """Straight-line distance in km between two lat/lng points."""
    import math
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@donate_bp.route("/ngos", methods=["GET"])
def get_ngos():
    """Return all NGOs, optionally filtered by category and sorted by proximity."""
    category = request.args.get("category", "").strip()
    try:
        user_lat = float(request.args.get("lat", ""))
        user_lng = float(request.args.get("lng", ""))
        has_location = True
    except (ValueError, TypeError):
        has_location = False

    if category:
        result = [dict(n) for n in NGO_LIST if n["category"].lower() == category.lower()]
    else:
        result = [dict(n) for n in NGO_LIST]

    if has_location:
        for n in result:
            if n.get("lat") and n.get("lng"):
                n["distance_km"] = round(_haversine_km(user_lat, user_lng, n["lat"], n["lng"]), 1)
            else:
                n["distance_km"] = None
        # Sort: open NGOs first, then by combined score (urgency + proximity)
        def sort_key(n):
            dist = n.get("distance_km") or 999
            # Proximity score: 100 at 0km, 0 at 50km+
            prox = max(0, 100 - dist * 2)
            # Combined: 60% urgency + 40% proximity
            return -(n["urgency"] * 0.6 + prox * 0.4)
        result.sort(key=sort_key)
    else:
        result.sort(key=lambda n: -n["urgency"])

    return jsonify({"ngos": result, "total": len(result)})


# ── GET /api/donate/ngos/<id> ─────────────────────────────────────────────────
@donate_bp.route("/ngos/<int:ngo_id>", methods=["GET"])
def get_ngo(ngo_id):
    ngo = next((n for n in NGO_LIST if n["id"] == ngo_id), None)
    if not ngo:
        return jsonify({"error": "NGO not found"}), 404
    return jsonify(ngo)


# ── GET /api/donate/ngos/match — Phase 3 M8 live semantic search ──────────────
@donate_bp.route("/ngos/match", methods=["GET"])
def semantic_ngo_match():
    """
    Live semantic NGO search endpoint for Phase 3.
    Query param: ?q=<item description text>
    Returns top-k NGOs ranked by Sentence-BERT cosine similarity + urgency.
    """
    query  = request.args.get("q", "").strip()
    top_k  = int(request.args.get("top_k", 5))

    if not query:
        return jsonify({"ngos": NGO_LIST[:top_k], "match_method": "none", "query": ""}), 200

    try:
        from ml.ngo_matcher import match_ngos
        matches = match_ngos(query, NGO_LIST, top_k=top_k)
        return jsonify({
            "ngos":         matches,
            "total":        len(matches),
            "match_method": matches[0]["match_method"] if matches else "none",
            "query":        query,
        })
    except Exception as e:
        return jsonify({"error": str(e), "ngos": NGO_LIST[:top_k]}), 500


# ── POST /api/donate/classify — item category + NGO matching ──────────────────
_CLASSIFY_RULES = [
    (("shirt", "tshirt", "t-shirt", "jacket", "trouser", "pant", "dress", "cloth", "wear", "fabric",
      "sweater", "hoodie", "jeans", "saree", "kurta", "shoe", "sandal", "blanket", "coat", "scarf",
      "uniform", "sock", "bag", "backpack", "apparel", "garment", "winter"), "Clothes"),
    (("book", "novel", "textbook", "magazine", "notebook", "comic", "manual", "guide", "dictionary",
      "encyclopedia", "stationery", "pencil", "pen ", "crayon"), "Books"),
    (("laptop", "phone", "smartphone", "tablet", "computer", "monitor", "keyboard", "mouse", "charger",
      "cable", "gadget", "electronic", "mobile", "tv", "television", "headphone", "earphone", "speaker",
      "camera", "printer", "router", "pc ", "desktop", "ipad", "iphone", "android", "powerbank"), "Electronics"),
    (("chair", "table", "desk", "sofa", "couch", "bed", "mattress", "shelf", "cabinet", "wardrobe",
      "furniture", "stool", "bench", "curtain", "mat ", "carpet", "almirah"), "Furniture"),
    (("toy", "doll", "puzzle", "game", "lego", "teddy", "bicycle", "tricycle", "blocks", "cycle",
      "board game", "stuffed"), "Toys"),
]


@donate_bp.route("/classify", methods=["POST"])
def classify_item():
    """
    Classify a donated item into an NGO category and rank matching NGOs.

    Keyword rules decide the category first (fast and predictable). If no keyword
    is found, Sentence-BERT semantic matching (Phase 3 M8) is used when installed.
    The NGO list is ranked semantically when possible, otherwise by urgency.
    """
    data        = request.get_json() or {}
    description = (data.get("description") or "").strip()
    item_name   = (data.get("name") or "").strip()
    given_cat   = (data.get("category") or "").strip()
    query_text  = f"{item_name} {description}".strip()

    if not query_text and not given_cat:
        return jsonify({"error": "Describe the item (or pick a category) so the AI can match NGOs."}), 400

    text = f" {query_text.lower()} "
    category, confidence, method = None, 0, "keyword_rules"
    for keywords, cat in _CLASSIFY_RULES:
        hits = sum(1 for k in keywords if k in text)
        if hits:
            category   = cat
            confidence = min(96, 78 + 6 * hits)
            break

    matched_ngos = []
    try:
        from ml.ngo_matcher import match_ngos
        matched_ngos = match_ngos(query_text or given_cat, NGO_LIST, top_k=5)
        if matched_ngos:
            m = matched_ngos[0].get("match_method", "semantic")
            if category is None:
                top = matched_ngos[0]
                if top.get("similarity_score", 0) > 0.12:
                    category, confidence, method = top["category"], min(90, int(top["similarity_score"] * 100) + 40), m
            elif m == "semantic":
                method = "keyword_rules+semantic"
    except Exception as e:
        print(f"[classify] semantic matcher unavailable: {e}")

    if category is None:
        category   = given_cat if given_cat in ("Clothes", "Books", "Electronics", "Furniture", "Toys") else "General"
        confidence = 60 if category == "General" else 70
        method     = "default"

    in_cat = [dict(n) for n in NGO_LIST if n["category"] == category and n.get("open", True)]
    if category == "General" or not in_cat:
        in_cat = [dict(n) for n in NGO_LIST if n.get("open", True)]
    in_cat.sort(key=lambda n: n["urgency"], reverse=True)
    for n in in_cat:
        n.setdefault("match_method", method)
        n.setdefault("similarity_score", 0.5)
        n["contact_info"] = contact_from_static(n)
    matched_for_cat = in_cat[:3]

    action_map = {
        "Clothes":     {"action": "DONATE", "reason": "Clothing is in high demand at NGOs. Donating extends its life and helps those in need.", "score": 94},
        "Books":       {"action": "DONATE", "reason": "Educational materials are urgently needed for underprivileged students.", "score": 96},
        "Electronics": {"action": "DONATE", "reason": "Functional electronics enable digital inclusion for underserved communities.", "score": 88},
        "Furniture":   {"action": "DONATE", "reason": "Furniture provides comfort to families without basic amenities.", "score": 82},
        "Toys":        {"action": "DONATE", "reason": "Toys bring joy to children in NGO care homes and shelters.", "score": 89},
        "General":     {"action": "DONATE", "reason": "This item can still be useful. Donating is the sustainable choice.", "score": 72},
    }
    info = action_map.get(category, action_map["General"])

    return jsonify({
        "category":     category,
        "confidence":   confidence,
        "action":       info["action"],
        "reason":       info["reason"],
        "match_score":  info["score"],
        "matched_ngos": matched_for_cat,
        "match_method": method,
        "name":         item_name or description[:40],
        "phase3":       True,
    })


# ── POST /api/donate/request ──────────────────────────────────────────────────
@donate_bp.route("/request", methods=["POST"])
@jwt_required()
def submit_donation():
    """
    Confirm a donation to an NGO.

    - awards eco points
    - saves a DonationRecord (so it shows in My Donations)
    - marks the linked item in My Items as Donated (tracked in its timeline)
    - returns the NGO's contact details so the donor knows who to reach
    """
    from models.donation_model import DonationRecord
    from models.product_model import Product

    uid  = int(get_jwt_identity())
    user = User.query.get(uid)
    data = request.get_json() or {}

    ngo_id    = data.get("ngo_id")
    category  = data.get("category", "General")
    item_desc = data.get("description", "")
    item_name = (data.get("item_name") or "").strip()

    try:
        ngo_id_int = int(ngo_id)
    except (TypeError, ValueError):
        ngo_id_int = None
    ngo = next((n for n in NGO_LIST if n["id"] == ngo_id_int), None)
    if not ngo:
        return jsonify({"error": "Please choose an NGO to donate to."}), 400
    ngo_name = ngo["name"]
    contact  = contact_from_static(ngo)

    # Link to a tracked item (My Items) if one was given and belongs to this user
    product = None
    pid = data.get("product_id")
    if pid not in (None, ""):
        try:
            product = Product.query.filter_by(id=int(pid), owner_id=uid).first()
        except (TypeError, ValueError):
            product = None
    if product and not item_name:
        item_name = product.name

    pts = 0
    conf_id = f"DON-{uid}-{ngo_id_int}-{int(datetime.utcnow().timestamp())}"
    record = DonationRecord(
        donor_id=uid, product_id=product.id if product else None,
        ngo_ref=str(ngo_id_int), ngo_name=ngo_name, ngo_phone=contact["phone"],
        ngo_email=contact["email"], ngo_address=contact["address"],
        ngo_lat=contact["lat"], ngo_lng=contact["lng"],
        item_name=item_name or category, category=category,
        description=item_desc, status="pledged", confirmation_id=conf_id,
    )
    db.session.add(record)

    if user:
        pts = award_eco_points(user, "donated", category=category,
                               description=f"Donated {item_name or category} to {ngo_name}")

    if product:
        try:
            from routes.product_routes import set_stage
            set_stage(product, "Donated", f"Donation sent to {ngo_name} · contact {contact['phone'] or 'n/a'}")
        except Exception as e:
            print(f"[Track] could not mark item as donated: {e}")

    db.session.commit()

    # ── Broadcast real-time WebSocket event ─────────────────────────────────────
    try:
        from socket_events import broadcast_new_donation, broadcast_urgency_update
        user_name = user.name if user else f"User #{uid}"
        broadcast_new_donation(user_name=user_name, ngo_name=ngo_name, category=category)
        new_urgency = max(0, ngo["urgency"] - 5)
        broadcast_urgency_update(ngo_id=ngo["id"], ngo_name=ngo_name, new_urgency=new_urgency)
    except Exception as ws_err:
        print(f"[WS] Could not broadcast donation event: {ws_err}")

    return jsonify({
        "message":         f"Donation request sent to {ngo_name}!",
        "confirmation_id": conf_id,
        "donation_id":     record.id,
        "ngo":             ngo_name,
        "contact":         contact,
        "category":        category,
        "eco_points":      pts,
        "eco_score":       user.eco_score if user else 0,
        "product_id":      product.id if product else None,
        "next_steps":      f"Please contact {ngo_name} on {contact['phone'] or 'their listed number'} to arrange "
                           "pickup or drop-off. They may also reach out to you within 24 hours.",
    })


# ── GET /api/donate/my-donations ──────────────────────────────────────────────
@donate_bp.route("/my-donations", methods=["GET"])
@jwt_required()
def my_donations():
    """
    Everything the user has donated or pledged, newest first, each with the NGO's
    contact details (phone / WhatsApp / directions) so they can follow up.
    """
    from models.donation_model import DonationRecord
    from models.ngo_model import PledgeRecord, NGOProfile, NeedsBoardEntry

    uid = int(get_jwt_identity())
    rows = []

    for d in DonationRecord.query.filter_by(donor_id=uid).all():
        item = d.to_dict()
        item["contact"] = build_contact(d.ngo_name, d.ngo_phone, d.ngo_email, d.ngo_address,
                                        d.ngo_lat, d.ngo_lng)
        rows.append(item)

    for p in PledgeRecord.query.filter_by(donor_id=uid).all():
        pd   = p.to_dict()
        ngo  = NGOProfile.query.get(p.ngo_id)
        need = NeedsBoardEntry.query.get(p.need_id) if p.need_id else None
        pd["record_type"]   = "pledge"
        pd["ngo_name"]      = ngo.name if ngo else "Unknown NGO"
        pd["ngo_address"]   = ngo.address if ngo else ""
        pd["item_category"] = need.item_category if need else ""
        pd["contact"]       = contact_from_profile(ngo) if ngo else None
        rows.append(pd)

    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return jsonify({"donations": rows[:100], "total": len(rows)})


# ── POST /api/donate/donations/<id>/cancel ────────────────────────────────────
@donate_bp.route("/donations/<int:donation_id>/cancel", methods=["POST"])
@jwt_required()
def cancel_donation(donation_id: int):
    """Donor cancels a donation that has not been delivered yet; the item goes back to 'In Use'."""
    from models.donation_model import DonationRecord
    from models.product_model import Product
    uid = int(get_jwt_identity())
    rec = DonationRecord.query.filter_by(id=donation_id, donor_id=uid).first()
    if not rec:
        return jsonify({"error": "Donation not found."}), 404
    if rec.status != "pledged":
        return jsonify({"error": f"Cannot cancel a donation in '{rec.status}' state. Please contact the NGO directly."}), 400
    rec.status = "cancelled"
    if rec.product_id:
        p = Product.query.filter_by(id=rec.product_id, owner_id=uid).first()
        if p:
            from routes.product_routes import set_stage
            set_stage(p, "In Use", f"Donation to {rec.ngo_name} was cancelled")
    db.session.commit()
    return jsonify({"message": "Donation cancelled.", "donation": rec.to_dict()})


# ── GET /api/donate/needed-items ──────────────────────────────────────────────
@donate_bp.route("/needed-items", methods=["GET"])
def get_needed_items():
    """Return a live list of items urgently needed across all NGOs."""
    items = []
    for ngo in NGO_LIST:
        for need in ngo["needs"]:
            items.append({"item": need, "ngo": ngo["name"], "urgency": ngo["urgency"]})
    items.sort(key=lambda x: x["urgency"], reverse=True)
    return jsonify({"items": items[:20]})


# ── GET /api/donate/stats ─────────────────────────────────────────────────────
@donate_bp.route("/stats", methods=["GET"])
def get_stats():
    """Return platform-wide donation stats."""
    from models.ngo_model import PledgeRecord
    total_delivered = PledgeRecord.query.filter_by(status="delivered").count()
    return jsonify({
        "total_donations":     max(2847, total_delivered),
        "ngo_partners":        len(NGO_LIST),
        "items_needed":        1240,
        "pickup_slots":        12,
        "donations_this_week": 384,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 3 — Live DB-Backed Needs-Matching Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

# ── GET /api/donate/ngos/matched-needs ───────────────────────────────────────
@donate_bp.route("/ngos/matched-needs", methods=["GET"])
def matched_needs():
    """
    Return ranked, staleness-aware, location-filtered NGO needs for a given
    item category.

    Query params:
        category  str    Required. Classified item category (e.g. 'Clothes').
        lat       float  Optional. Donor latitude for proximity scoring.
        lng       float  Optional. Donor longitude for proximity scoring.
        top_k     int    Optional. Max results (default 10).
    """
    from models.ngo_model import NeedsBoardEntry, NGOProfile
    from ml.ngo_matcher import score_needs_for_donor

    category = request.args.get("category", "").strip()
    top_k    = int(request.args.get("top_k", 10))
    try:
        donor_lat = float(request.args.get("lat"))  if request.args.get("lat") else None
        donor_lng = float(request.args.get("lng"))  if request.args.get("lng") else None
    except (ValueError, TypeError):
        donor_lat = donor_lng = None

    # Fetch open/partial needs matching the category from DB
    query = NeedsBoardEntry.query.filter(
        NeedsBoardEntry.status.in_(["open", "partially_fulfilled"]),
    )
    if category:
        query = query.filter_by(item_category=category)

    needs = query.all()

    # Build combined dicts for the scoring engine
    needs_with_ngos = []
    for n in needs:
        ngo = NGOProfile.query.get(n.ngo_id)
        if not ngo:
            continue
        nd = n.to_dict()
        nd["ngo_name"]    = ngo.name
        nd["ngo_address"] = ngo.address
        nd["latitude"]    = ngo.latitude
        nd["longitude"]   = ngo.longitude
        nd["verified"]    = ngo.verified
        nd["contact_phone"] = ngo.contact_phone
        nd["contact_email"] = ngo.contact_email
        needs_with_ngos.append(nd)

    ranked = score_needs_for_donor(
        item_category   = category,
        donor_lat       = donor_lat,
        donor_lng       = donor_lng,
        needs_with_ngos = needs_with_ngos,
        top_k           = top_k,
    )

    return jsonify({
        "matched_needs": ranked,
        "total":         len(ranked),
        "category":      category,
        "scored_by":     "staleness_aware_db",
    })


# ── POST /api/donate/pledge ───────────────────────────────────────────────────
@donate_bp.route("/pledge", methods=["POST"])
@jwt_required()
def create_pledge():
    """
    Donor pledges a classified item to a specific NGO need.
    Soft-holds the requested quantity on the NeedsBoardEntry.

    Body (JSON):
        ngo_id              str   required
        need_id             str   required
        item_name           str   optional
        item_classification dict  optional  AI metadata
        quantity            int   optional  default 1
        donor_note          str   optional
    """
    from models.ngo_model import NGOProfile, NeedsBoardEntry, PledgeRecord
    uid  = int(get_jwt_identity())
    user = User.query.get_or_404(uid)
    data = request.get_json() or {}

    ngo_id  = data.get("ngo_id", "").strip()
    need_id = data.get("need_id", "").strip()

    if not ngo_id or not need_id:
        return jsonify({"error": "ngo_id and need_id are required."}), 400

    ngo  = NGOProfile.query.get(ngo_id)
    need = NeedsBoardEntry.query.filter_by(need_id=need_id, ngo_id=ngo_id).first()

    if not ngo:
        return jsonify({"error": "NGO not found."}), 404
    if not need:
        return jsonify({"error": "Need not found or does not belong to this NGO."}), 404
    if need.status == "closed":
        return jsonify({"error": "This need is already fully fulfilled."}), 409

    quantity = int(data.get("quantity", 1))
    if quantity < 1:
        quantity = 1

    # Soft-hold
    need.quantity_pledged = (need.quantity_pledged or 0) + quantity
    need.sync_status()

    pledge = PledgeRecord(
        donor_id           = uid,
        ngo_id             = ngo_id,
        need_id            = need_id,
        item_name          = data.get("item_name", "").strip() or None,
        item_classification = data.get("item_classification"),
        quantity           = quantity,
        status             = "pledged",
        donor_note         = data.get("donor_note", "").strip() or None,
    )
    db.session.add(pledge)

    # Track the linked item (My Items) as Donated
    tracked_pid = None
    try:
        from models.product_model import Product
        from routes.product_routes import set_stage
        if data.get("product_id") not in (None, ""):
            _p = Product.query.filter_by(id=int(data["product_id"]), owner_id=uid).first()
            if _p:
                set_stage(_p, "Donated", f"Pledged to {ngo.name} · contact {ngo.contact_phone or 'n/a'}")
                tracked_pid = _p.id
    except Exception as _e:
        print(f"[Track] pledge item tracking skipped: {_e}")

    # ── Award Eco Points ─────────────────────────────────────────────────────
    pts = award_eco_points(user, "donated", category=need.item_category,
                           description=f"Pledged {quantity}x {need.item_category} to {ngo.name}")

    db.session.commit()

    # ── Broadcast WebSocket event ────────────────────────────────────────────────────
    try:
        from socket_events import broadcast_new_donation
        broadcast_new_donation(
            user_name=user.name,
            ngo_name=ngo.name,
            category=need.item_category,
        )
    except Exception as ws_err:
        print(f"[WS] Pledge broadcast error: {ws_err}")

    contact = contact_from_profile(ngo)
    return jsonify({
        "message":     f"Pledge submitted to {ngo.name}!",
        "pledge_id":   pledge.pledge_id,
        "pledge":      pledge.to_dict(),
        "need_status": need.status,
        "eco_points":  pts,
        "eco_score":   user.eco_score,
        "contact":     contact,
        "product_id":  tracked_pid,
        "next_steps":  f"Please contact {ngo.name} on {contact['phone'] or 'their listed number'} "
                       "to arrange pickup or drop-off.",
    }), 201


# ── GET /api/donate/pledges/my-pledges ───────────────────────────────────────
@donate_bp.route("/pledges/my-pledges", methods=["GET"])
@jwt_required()
def my_pledges():
    """Return all pledges made by the authenticated donor."""
    from models.ngo_model import PledgeRecord, NGOProfile, NeedsBoardEntry
    uid    = int(get_jwt_identity())
    status = request.args.get("status", "").strip()
    query  = PledgeRecord.query.filter_by(donor_id=uid).order_by(
        PledgeRecord.created_at.desc()
    )
    if status:
        query = query.filter(PledgeRecord.status == status)

    pledges = []
    for p in query.limit(50).all():
        pd = p.to_dict()
        ngo  = NGOProfile.query.get(p.ngo_id)
        need = NeedsBoardEntry.query.get(p.need_id) if p.need_id else None
        pd["ngo_name"]     = ngo.name    if ngo  else "Unknown NGO"
        pd["ngo_address"]  = ngo.address if ngo  else ""
        pd["item_category"] = need.item_category if need else ""
        pledges.append(pd)

    return jsonify({"pledges": pledges, "total": len(pledges)})


# ── POST /api/donate/pledges/<pledge_id>/cancel ──────────────────────────────
@donate_bp.route("/pledges/<pledge_id>/cancel", methods=["POST"])
@jwt_required()
def cancel_pledge(pledge_id: str):
    """Donor cancels their own pledge (only allowed while status is 'pledged')."""
    from models.ngo_model import PledgeRecord, NeedsBoardEntry
    uid    = int(get_jwt_identity())
    pledge = PledgeRecord.query.filter_by(pledge_id=pledge_id, donor_id=uid).first()

    if not pledge:
        return jsonify({"error": "Pledge not found."}), 404
    if pledge.status != "pledged":
        return jsonify({
            "error": f"Cannot cancel a pledge in '{pledge.status}' state. "
                     "Contact the NGO directly."
        }), 400

    # Release soft-hold
    need = NeedsBoardEntry.query.get(pledge.need_id) if pledge.need_id else None
    if need:
        need.quantity_pledged = max(0, need.quantity_pledged - pledge.quantity)
        need.sync_status()

    pledge.status     = "cancelled"
    pledge.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"message": "Pledge cancelled.", "pledge": pledge.to_dict()})

