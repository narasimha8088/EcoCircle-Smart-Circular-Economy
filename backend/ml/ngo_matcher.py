"""
Model 8 — Sentence-BERT NGO Semantic Matcher
=============================================
Uses `sentence-transformers` (all-MiniLM-L6-v2) to encode item descriptions
and NGO need profiles into 384-dimensional embeddings, then ranks NGOs by
cosine similarity + urgency weighting.

Graceful degradation:
  • If sentence-transformers is not installed → TF-IDF keyword overlap fallback
  • NGO embeddings are cached in-process after first encode call
  • Singleton model instance to avoid repeated disk loads

Usage:
    from ml.ngo_matcher import match_ngos, is_available
    results = match_ngos("old HP laptop cracked screen", NGO_LIST, top_k=5)
    # [{"id":7, "name":"TechForAll India", "similarity_score": 0.82, ...}, ...]
"""

from __future__ import annotations

import logging
import os
import pickle
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Module-level singletons ───────────────────────────────────────────────────
_model: Optional[object] = None            # SentenceTransformer instance
_ngo_embedding_cache: dict[str, np.ndarray] = {}  # key → embedding
_ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "artifacts")
_NGO_EMBEDDINGS_PKL = os.path.join(_ARTIFACTS_DIR, "ngo_embeddings.pkl")
_MODEL_NAME = "all-MiniLM-L6-v2"


# ── Availability ─────────────────────────────────────────────────────────────

def is_available() -> bool:
    """Returns True whether using model or keyword fallback — always True."""
    return True


_st_available: Optional[bool] = None

def _has_sentence_transformers() -> bool:
    global _st_available
    if _st_available is not None:
        return _st_available
    try:
        import sentence_transformers  # noqa: F401
        _st_available = True
    except (ImportError, OSError, Exception):
        _st_available = False
    return _st_available


_model_load_attempted: bool = False

def _load_model():
    global _model, _model_load_attempted
    if _model_load_attempted:
        return _model
    _model_load_attempted = True
    try:
        from sentence_transformers import SentenceTransformer
        logger.info("[M8] Loading SentenceTransformer: %s …", _MODEL_NAME)
        _model = SentenceTransformer(_MODEL_NAME)
        logger.info("[M8] Model loaded.")
    except (ImportError, OSError, Exception) as e:
        logger.warning("[M8] Could not load SentenceTransformer: %s — using fallback.", e)
        _model = None
    return _model


# ── Encoding ─────────────────────────────────────────────────────────────────

def encode_text(text: str) -> np.ndarray:
    """
    Encode a text string to a 384-dimensional float32 embedding.
    Falls back to TF-IDF bag-of-words vector if model unavailable.
    """
    model = _load_model()
    if model is not None:
        try:
            embedding = model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
            return embedding.astype(np.float32)
        except Exception as e:
            logger.error("[M8] encode failed: %s", e)

    # ── TF-IDF keyword fallback ───────────────────────────────────────────────
    return _tfidf_encode(text)


def _tfidf_encode(text: str) -> np.ndarray:
    """
    Simple bag-of-words fallback encoding when sentence-transformers unavailable.
    Returns a 384-d zero-padded term-frequency vector.
    """
    VOCAB = [
        "clothes", "cloth", "shirt", "jacket", "dress", "wear", "fabric",
        "saree", "blanket", "shoe", "sweater", "jacket", "trouser",
        "book", "novel", "textbook", "notebook", "magazine", "stationery",
        "pencil", "uniform", "comic",
        "laptop", "phone", "tablet", "computer", "mobile", "charger", "cable",
        "keyboard", "mouse", "electronics", "gadget", "monitor", "headphone",
        "chair", "table", "desk", "sofa", "bed", "shelf", "cabinet", "furniture", "mattress",
        "toy", "doll", "puzzle", "game", "teddy", "bicycle", "lego", "blocks",
        "food", "rice", "wheat", "flour", "grain", "cereal", "ration", "grocery", "pulse", "lentil", "oil",
        "utensil", "bag", "mat", "curtain", "crayon", "smartphone",
    ]
    text_lower = text.lower()
    vec = np.zeros(len(VOCAB), dtype=np.float32)
    for i, word in enumerate(VOCAB):
        if word in text_lower:
            vec[i] = 1.0
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    # Pad to 384 dimensions
    padded = np.zeros(384, dtype=np.float32)
    padded[:len(VOCAB)] = vec
    return padded


# ── NGO Profile Encoding ──────────────────────────────────────────────────────

def _ngo_profile_text(ngo: dict) -> str:
    """Build a rich text profile for an NGO from its metadata."""
    name     = ngo.get("name", "")
    category = ngo.get("category", "")
    needs    = ", ".join(ngo.get("needs", []))
    location = ngo.get("location", "")
    return f"{name}. Category: {category}. Needs: {needs}. Location: {location}."


def _load_cached_ngo_embeddings() -> dict[str, np.ndarray]:
    """Load pre-computed NGO embeddings from pkl artifact if available."""
    global _ngo_embedding_cache
    if _ngo_embedding_cache:
        return _ngo_embedding_cache
    if os.path.exists(_NGO_EMBEDDINGS_PKL):
        try:
            with open(_NGO_EMBEDDINGS_PKL, "rb") as f:
                _ngo_embedding_cache = pickle.load(f)
            logger.info("[M8] Loaded %d cached NGO embeddings.", len(_ngo_embedding_cache))
        except Exception as e:
            logger.warning("[M8] Could not load cached embeddings: %s", e)
    return _ngo_embedding_cache


def _get_ngo_embedding(ngo: dict) -> np.ndarray:
    """Get embedding for an NGO, using cache if available."""
    cache = _load_cached_ngo_embeddings()
    key   = str(ngo.get("id", ngo.get("name", "")))
    if key in cache:
        return cache[key]
    # Encode on-the-fly and store in memory cache
    text  = _ngo_profile_text(ngo)
    emb   = encode_text(text)
    _ngo_embedding_cache[key] = emb
    return emb


# ── Core Matching Function ────────────────────────────────────────────────────

def match_ngos(
    item_description: str,
    ngo_list: list[dict],
    top_k: int = 5,
    urgency_weight: float = 0.35,
    open_only: bool = True,
) -> list[dict]:
    """
    Semantically match an item description to NGOs.

    Args:
        item_description: Free-text description of the donated item.
        ngo_list:         List of NGO dicts (must have 'needs', 'urgency', 'open' keys).
        top_k:            Number of top matches to return.
        urgency_weight:   Weight for urgency score vs semantic similarity (0–1).
        open_only:        If True, only include NGOs where open=True.

    Returns:
        Top-k NGO dicts enriched with:
          - similarity_score (0–1, cosine similarity)
          - combined_score   (0–1, weighted blend)
          - match_method     ("semantic" or "keyword_fallback")
          - match_reason     (human-readable explanation)
    """
    if not item_description.strip():
        return ngo_list[:top_k]

    method    = "semantic" if _has_sentence_transformers() else "keyword_fallback"
    item_emb  = encode_text(item_description)
    candidates = [n for n in ngo_list if (not open_only or n.get("open", True))]

    scored = []
    for ngo in candidates:
        ngo_emb    = _get_ngo_embedding(ngo)
        similarity = float(np.dot(item_emb, ngo_emb))  # already L2 normalised
        similarity = max(0.0, min(1.0, similarity))     # clamp to [0, 1]

        urgency_norm = ngo.get("urgency", 50) / 100.0
        combined     = (1 - urgency_weight) * similarity + urgency_weight * urgency_norm

        # Generate match reason
        top_needs = ngo.get("needs", [])[:3]
        if similarity > 0.6:
            reason = f"High semantic match — NGO needs: {', '.join(top_needs)}"
        elif similarity > 0.35:
            reason = f"Moderate match — item may fit NGO's needs: {', '.join(top_needs)}"
        else:
            reason = f"Low item match, but urgency is high ({ngo.get('urgency', 0)}%)"

        enriched = {
            **ngo,
            "similarity_score": round(similarity, 3),
            "combined_score":   round(combined, 3),
            "match_method":     method,
            "match_reason":     reason,
        }
        scored.append(enriched)

    scored.sort(key=lambda x: x["combined_score"], reverse=True)
    return scored[:top_k]


# ── Precompute utility (called by training script) ────────────────────────────

def precompute_and_save(ngo_list: list[dict]) -> str:
    """
    Encode all NGOs and save to artifacts/ngo_embeddings.pkl.
    Returns path to saved file.
    """
    os.makedirs(_ARTIFACTS_DIR, exist_ok=True)
    _load_model()  # ensure model is loaded

    embeddings: dict[str, np.ndarray] = {}
    for ngo in ngo_list:
        key  = str(ngo.get("id", ngo.get("name")))
        text = _ngo_profile_text(ngo)
        emb  = encode_text(text)
        embeddings[key] = emb
        logger.info("[M8] Encoded NGO %s: %s", key, ngo.get("name"))

    with open(_NGO_EMBEDDINGS_PKL, "wb") as f:
        pickle.dump(embeddings, f)

    logger.info("[M8] Saved %d NGO embeddings → %s", len(embeddings), _NGO_EMBEDDINGS_PKL)
    return _NGO_EMBEDDINGS_PKL


# ── Staleness-Aware DB Needs Scoring Engine ───────────────────────────────────

import math
from datetime import datetime


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance in kilometres between two points
    on Earth (specified in decimal degrees).
    """
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi   = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _proximity_score(distance_km: float) -> float:
    """1 / (1 + distance_km) — ranges from ~1.0 (same spot) to ~0 (far away)."""
    return 1.0 / (1.0 + distance_km)


def score_needs_for_donor(
    item_category: str,
    donor_lat: float | None,
    donor_lng: float | None,
    needs_with_ngos: list[dict],
    top_k: int = 10,
    w_proximity: float = 0.4,
    w_urgency: float = 0.3,
    w_unmet: float = 0.3,
) -> list[dict]:
    """
    Stale-aware, location-weighted needs ranking for the donor map.

    Parameters
    ----------
    item_category     : Classified item category (e.g. "Clothes").
    donor_lat/lng     : Donor GPS coordinates (may be None; proximity skipped).
    needs_with_ngos   : List of dicts combining NeedsBoardEntry + NGOProfile fields:
                        {
                          "need_id", "ngo_id", "ngo_name", "ngo_address",
                          "latitude", "longitude", "item_category",
                          "quantity_needed", "quantity_fulfilled", "quantity_pledged",
                          "urgency", "condition_accepted", "notes", "last_updated",
                          "staleness_factor", "status"
                        }
    top_k             : Maximum number of results.
    w_proximity/urgency/unmet : Score component weights (must sum to 1).

    Returns
    -------
    Top-k enriched dicts sorted by final_score (descending), each annotated with:
      proximity_score, urgency_score, unmet_need_score, staleness_factor,
      raw_score, final_score, distance_km.
    """
    results = []

    for need in needs_with_ngos:
        # Skip closed needs or zero-quantity needs
        if need.get("status") == "closed":
            continue
        if need.get("quantity_needed", 0) <= 0:
            continue

        # ── Proximity ────────────────────────────────────────────────────────
        ngo_lat = need.get("latitude")
        ngo_lng = need.get("longitude")
        if donor_lat is not None and donor_lng is not None and ngo_lat and ngo_lng:
            dist_km   = _haversine_km(donor_lat, donor_lng, ngo_lat, ngo_lng)
            prox      = _proximity_score(dist_km)
        else:
            dist_km = None
            prox    = 0.5  # neutral when location unknown

        # ── Urgency ──────────────────────────────────────────────────────────
        urgency_map = {"low": 0.33, "medium": 0.66, "high": 1.0}
        urgency_s   = urgency_map.get(need.get("urgency", "medium"), 0.66)

        # ── Unmet need ───────────────────────────────────────────────────────
        q_needed    = need.get("quantity_needed", 1)
        q_fulfilled = need.get("quantity_fulfilled", 0)
        unmet_s     = max(0.0, min(1.0, (q_needed - q_fulfilled) / max(1, q_needed)))

        # ── Weight Resolution (supports custom tuned weights per need/NGO) ──
        w_p = need.get("custom_w_proximity", w_proximity)
        w_u = need.get("custom_w_urgency", w_urgency)
        w_m = need.get("custom_w_unmet", w_unmet)
        total_w = max(0.001, w_p + w_u + w_m)
        w_p, w_u, w_m = w_p / total_w, w_u / total_w, w_m / total_w

        # ── Raw score ────────────────────────────────────────────────────────
        raw_score = w_p * prox + w_u * urgency_s + w_m * unmet_s

        # ── Staleness discount ────────────────────────────────────────────────
        staleness = need.get("staleness_factor", 1.0)
        if isinstance(need.get("last_updated"), str):
            try:
                last_dt   = datetime.fromisoformat(need["last_updated"])
                days      = (datetime.utcnow() - last_dt).days
                staleness = max(0.5, 1.0 - days / 60.0)
            except Exception:
                staleness = need.get("staleness_factor", 1.0)

        final_score = raw_score * staleness

        results.append({
            **need,
            "proximity_score":  round(prox, 3),
            "urgency_score":    round(urgency_s, 3),
            "unmet_need_score": round(unmet_s, 3),
            "staleness_factor": round(staleness, 3),
            "raw_score":        round(raw_score, 3),
            "final_score":      round(final_score, 3),
            "distance_km":      round(dist_km, 2) if dist_km is not None else None,
            "weights_applied":  {"proximity": round(w_p, 3), "urgency": round(w_u, 3), "unmet": round(w_m, 3)},
        })

    results.sort(key=lambda x: x["final_score"], reverse=True)
    return results[:top_k]


# ── Analytic Hierarchy Process (AHP) & Dynamic Preference Calibration ─────────

AHP_PRESETS = {
    "disaster_relief": {
        "name": "Disaster & Emergency Relief",
        "description": "Urgency prioritized (rapid fulfillment over proximity)",
        "weights": {"urgency": 0.55, "proximity": 0.30, "unmet": 0.15},
    },
    "community_poverty": {
        "name": "Community & Poverty Support",
        "description": "Balanced proximity and volume fulfillment",
        "weights": {"urgency": 0.35, "proximity": 0.35, "unmet": 0.30},
    },
    "education_books": {
        "name": "Educational & Skill Resources",
        "description": "Unmet volume prioritized for batch library/classroom outfitting",
        "weights": {"urgency": 0.20, "proximity": 0.30, "unmet": 0.50},
    },
    "perishables": {
        "name": "Hyper-Local Perishables / Essentials",
        "description": "Immediate proximity prioritized for rapid physical pickup",
        "weights": {"urgency": 0.35, "proximity": 0.55, "unmet": 0.10},
    },
}


def calculate_ahp_weights(pairwise_matrix: list[list[float]]) -> dict:
    """
    Computes rigorous Analytic Hierarchy Process (AHP) weights from a 3x3 pairwise
    comparison matrix for [proximity, urgency, unmet].
    Returns normalized eigenvector weights + Consistency Ratio (CR).
    """
    A = np.array(pairwise_matrix, dtype=float)
    n = A.shape[0]

    # Column normalization
    col_sum = A.sum(axis=0)
    norm_A  = A / col_sum

    # Principal eigenvector (weights)
    weights = norm_A.mean(axis=1)

    # Consistency Check
    lambda_max = float(np.dot(col_sum, weights))
    ci = (lambda_max - n) / (n - 1) if n > 1 else 0.0
    ri_table = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12}
    ri = ri_table.get(n, 0.58)
    cr = ci / ri if ri > 0 else 0.0

    return {
        "weights": {
            "proximity": round(float(weights[0]), 3),
            "urgency":   round(float(weights[1]), 3),
            "unmet":     round(float(weights[2]), 3),
        },
        "consistency_ratio": round(float(cr), 4),
        "is_consistent": bool(cr < 0.10),
    }


def calibrate_weights_from_feedback(
    base_weights: dict,
    accepted_count: int,
    rejected_distance_count: int,
    rejected_delay_count: int,
) -> dict:
    """
    Human-in-the-Loop reinforcement tuning. Adjusts NGO matching weights based
    on historical pledge outcomes.
    """
    w_p = base_weights.get("proximity", 0.4)
    w_u = base_weights.get("urgency", 0.3)
    w_m = base_weights.get("unmet", 0.3)

    # If NGO frequently rejects distant items -> increase proximity weight
    if rejected_distance_count > 0:
        shift = min(0.20, rejected_distance_count * 0.03)
        w_p += shift
        w_u -= shift / 2
        w_m -= shift / 2

    # If NGO frequently rejects delayed/expired needs -> increase urgency weight
    if rejected_delay_count > 0:
        shift = min(0.20, rejected_delay_count * 0.03)
        w_u += shift
        w_p -= shift / 2
        w_m -= shift / 2

    # Normalize to 1.0
    total = max(0.01, w_p + w_u + w_m)
    return {
        "proximity": round(max(0.05, w_p / total), 3),
        "urgency":   round(max(0.05, w_u / total), 3),
        "unmet":     round(max(0.05, w_m / total), 3),
        "feedback_samples_used": accepted_count + rejected_distance_count + rejected_delay_count,
    }

