"""
Phase 2 Model 6: Resale Valuation Model
========================================
Replaces the naive linear _estimate_resale() function in ai_routes.py.

Approach:
  XGBoost / LightGBM gradient-boosted regressor trained on synthetic
  marketplace data covering:
    • 10 product categories
    • 4 condition tiers (New, Good, Fair, Poor)
    • 5 brand tiers (Premium, Standard, Budget, Generic, Unknown)
    • Age 0–20 years
    • Purchase price 500 – 200,000 INR

  Falls back to the original linear formula if the .pkl artifact is missing.

Output contract (superset of old /price-predict response):
    {
      "estimated_price":   8200.0,
      "price_range":       [6800.0, 9800.0],    # ±15% confidence interval
      "depreciation_pct":  38.5,
      "original_price":    13300.0,
      "confidence":        "model",             # "model" | "formula"
      "category":          "mobile",
      "condition":         "good",
      "brand_tier":        "standard",
      "age_years":         2.5,
    }
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ── Artifact path ──────────────────────────────────────────────────────────────
_ARTIFACT_DIR = os.path.join(os.path.dirname(__file__), "artifacts")
_MODEL_PATH   = os.path.join(_ARTIFACT_DIR, "resale_model.pkl")

# ── Lazy model cache ───────────────────────────────────────────────────────────
_model      = None
_encoders   = None

# ── Brand tier mapping (normalise user-supplied brand names) ───────────────────
BRAND_TIER_MAP: dict[str, int] = {
    # tier 4 = Premium
    "apple": 4, "samsung": 4, "sony": 4, "lg": 4, "dyson": 4,
    "bose": 4, "dell": 4, "hp": 4, "lenovo": 4, "asus": 4,
    "ikea": 3, "philips": 3, "bosch": 3, "whirlpool": 3,
    # tier 3 = Standard
    "mi": 3, "xiaomi": 3, "realme": 3, "oppo": 3, "vivo": 3,
    "oneplus": 3, "motorola": 3, "nokia": 3,
    # tier 2 = Budget
    "intex": 2, "micromax": 2, "lava": 2, "karbonn": 2,
    # tier 1 = Generic
}

CONDITION_SCORES: dict[str, float] = {
    "new":  0.92,
    "good": 0.65,
    "fair": 0.38,
    "poor": 0.12,
}

# Category depreciation speed (higher = depreciates faster per year)
CATEGORY_DEPRECIATION: dict[str, float] = {
    "mobile":      0.18,
    "laptop":      0.15,
    "electronics": 0.14,
    "appliance":   0.10,
    "furniture":   0.06,
    "clothing":    0.25,
    "vehicle":     0.12,
    "books":       0.08,
    "sports":      0.10,
    "other":       0.12,
}


def _brand_tier(brand: str) -> int:
    """Map a brand name to tier 1-4 (4 = premium)."""
    if not brand:
        return 1
    b = brand.lower().strip()
    return BRAND_TIER_MAP.get(b, 2)   # default 2 = budget


def _load_model() -> bool:
    """Attempt to load the trained XGBoost pipeline from disk."""
    global _model, _encoders
    if _model is not None:
        return True
    if not os.path.exists(_MODEL_PATH):
        return False
    try:
        import joblib
        bundle   = joblib.load(_MODEL_PATH)
        _model   = bundle["model"]
        _encoders = bundle["encoders"]
        logger.info("[ResaleM6] Loaded XGBoost model from %s", _MODEL_PATH)
        return True
    except Exception as e:
        logger.warning("[ResaleM6] Could not load model: %s — using formula.", e)
        return False


def _formula_predict(
    purchase_price: float,
    age_years:      float,
    condition:      str,
    category:       str,
    brand_tier:     int,
) -> float:
    """Linear fallback formula (improved over original — adds category + brand)."""
    cond_f   = CONDITION_SCORES.get(condition.lower(), 0.40)
    dep_rate = CATEGORY_DEPRECIATION.get(category.lower(), 0.12)
    dep      = max(0.0, 1.0 - (age_years * dep_rate))
    brand_f  = 0.85 + (brand_tier * 0.05)   # 0.90 – 1.05 multiplier
    return purchase_price * cond_f * dep * brand_f


def predict(
    purchase_price: float,
    age_years:      float,
    condition:      str,
    category:       str,
    brand:          str = "",
) -> dict:
    """
    Estimate resale price for a product.

    Args:
        purchase_price: Original purchase price in INR
        age_years:      Product age in years (float)
        condition:      "new" | "good" | "fair" | "poor"
        category:       EcoCircle category string
        brand:          Brand name string (optional)

    Returns:
        Rich dict with estimated_price, price_range, depreciation_pct, …
    """
    pp   = max(float(purchase_price), 1.0)
    age  = max(float(age_years), 0.0)
    cat  = category.lower().strip()  if category  else "other"
    cond = condition.lower().strip() if condition  else "good"
    bt   = _brand_tier(brand)

    confidence = "formula"
    est_price  = None

    # ── Try ML model ───────────────────────────────────────────────────────────
    if _load_model():
        try:
            import numpy as np
            cat_enc  = _encoders["category"].get(cat, _encoders["category"].get("other", 0))
            cond_enc = _encoders["condition"].get(cond, _encoders["condition"].get("good", 1))
            X        = np.array([[pp, age, cond_enc, cat_enc, bt]])
            est_price = float(_model.predict(X)[0])
            confidence = "model"
        except Exception as e:
            logger.warning("[ResaleM6] Model inference failed: %s — falling back.", e)
            est_price = None

    # ── Fallback formula ───────────────────────────────────────────────────────
    if est_price is None:
        est_price = _formula_predict(pp, age, cond, cat, bt)

    est_price = max(0.0, est_price)
    dep_pct   = round((1 - est_price / pp) * 100, 1) if pp > 0 else 0.0

    # ±15% confidence interval
    low  = round(est_price * 0.85, 2)
    high = round(est_price * 1.15, 2)

    return {
        "estimated_price":  round(est_price, 2),
        "price_range":      [low, high],
        "depreciation_pct": dep_pct,
        "original_price":   pp,
        "confidence":       confidence,
        "category":         cat,
        "condition":        cond,
        "brand_tier":       bt,
        "age_years":        age,
    }


def is_available() -> bool:
    """Always True — formula fallback is always available."""
    return True
