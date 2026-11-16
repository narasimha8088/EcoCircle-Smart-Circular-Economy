"""
Phase 1 Model 4: Material / Fabric Classifier
==============================================
Detects the primary material composition of a product from its image.

Strategy — CLIP zero-shot with material prompts:
  • No training data needed
  • Works across diverse product types
  • Can be swapped for a fine-tuned ResNet18/EfficientNet in Phase 2
    once a labeled material dataset is assembled

Material taxonomy (aligned with EcoCircle carbon impact model):
  ┌─────────────────┬──────────────────────────────────────────┐
  │ Material        │ CO2e (kg per kg of material, production)  │
  ├─────────────────┼──────────────────────────────────────────┤
  │ cotton          │ 5.9                                       │
  │ polyester       │ 9.5                                       │
  │ nylon           │ 7.3                                       │
  │ wool            │ 36.0                                      │
  │ leather         │ 17.0                                      │
  │ denim           │ 6.8                                       │
  │ plastic         │ 6.0                                       │
  │ glass           │ 0.85                                      │
  │ aluminium       │ 11.5                                      │
  │ steel           │ 2.8                                       │
  │ wood            │ 0.5                                       │
  │ rubber          │ 3.2                                       │
  │ ceramic         │ 1.2                                       │
  │ cardboard       │ 1.1                                       │
  │ silicon         │ 45.0  (semiconductor-grade)               │
  │ mixed/composite │ 8.0   (default average)                   │
  └─────────────────┴──────────────────────────────────────────┘

CO2 factors are used downstream by the carbon impact estimator.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Lazy globals (reuse CLIP if already loaded) ──────────────────
_model     = None
_processor = None
_device    = None

# ── Material prompts (CLIP text embeddings) ───────────────────────
MATERIAL_PROMPTS: dict[str, str] = {
    "cotton":          "a product made of cotton fabric or cotton cloth",
    "polyester":       "a product made of polyester synthetic fabric",
    "nylon":           "a product made of nylon or nylon fabric",
    "wool":            "a product made of wool or woolen fabric",
    "leather":         "a product made of leather or faux leather",
    "denim":           "a product made of denim or jeans material",
    "plastic":         "a product made of plastic or hard polymer",
    "glass":           "a product made of glass",
    "aluminium":       "a product made of aluminium or aluminum metal",
    "steel":           "a product made of steel or stainless steel",
    "wood":            "a product made of wood or timber",
    "rubber":          "a product made of rubber or silicone rubber",
    "ceramic":         "a product made of ceramic or porcelain",
    "cardboard":       "a product made of cardboard or paper",
    "silicon":         "a product containing silicon chips or circuit boards",
    "mixed/composite": "a product made of multiple materials combined together",
}

MATERIAL_LABELS = list(MATERIAL_PROMPTS.keys())
MATERIAL_TEXT   = list(MATERIAL_PROMPTS.values())

# ── CO2 emission factors per kg of material (production) ─────────
MATERIAL_CO2_FACTORS: dict[str, float] = {
    "cotton":          5.9,
    "polyester":       9.5,
    "nylon":           7.3,
    "wool":            36.0,
    "leather":         17.0,
    "denim":           6.8,
    "plastic":         6.0,
    "glass":           0.85,
    "aluminium":       11.5,
    "steel":           2.8,
    "wood":            0.5,
    "rubber":          3.2,
    "ceramic":         1.2,
    "cardboard":       1.1,
    "silicon":         45.0,
    "mixed/composite": 8.0,
}

# ── Recyclability scores (0-100) ──────────────────────────────────
MATERIAL_RECYCLABILITY: dict[str, int] = {
    "cotton":          75,
    "polyester":       40,
    "nylon":           35,
    "wool":            80,
    "leather":         20,
    "denim":           70,
    "plastic":         55,
    "glass":           95,
    "aluminium":       90,
    "steel":           88,
    "wood":            70,
    "rubber":          45,
    "ceramic":         30,
    "cardboard":       85,
    "silicon":         60,
    "mixed/composite": 30,
}


def _load_model():
    """Lazy-load CLIP for material classification (shares cache with clip_classifier)."""
    global _model, _processor, _device

    if _model is not None:
        return

    # Try to reuse already-loaded CLIP model from clip_classifier
    try:
        from ml.clip_classifier import _model as clip_model, _processor as clip_proc, _device as clip_dev
        if clip_model is not None:
            _model     = clip_model
            _processor = clip_proc
            _device    = clip_dev
            logger.info("[MaterialClassifier] Reusing already-loaded CLIP model.")
            return
    except ImportError:
        pass

    # Load fresh
    try:
        import torch
        from transformers import CLIPModel, CLIPProcessor

        _device    = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("[MaterialClassifier] Loading CLIP model on %s …", _device)
        _processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
        _model     = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(_device)
        _model.eval()
        logger.info("[MaterialClassifier] CLIP model loaded.")
    except ImportError as e:
        raise RuntimeError(
            f"Material classifier requires 'transformers' and 'torch'. "
            f"Run: pip install transformers torch\nError: {e}"
        )


def classify_material(image_bytes: bytes, top_k: int = 3) -> dict:
    """
    Identify the primary material composition of a product from its image.

    Returns:
        {
          "material":         "plastic",
          "confidence":       0.72,
          "co2_factor_kg":    6.0,      # kg CO2 per kg of this material
          "recyclability":    55,        # 0-100 score
          "top_k": [
            {"material": "plastic",   "score": 0.72, "co2_factor": 6.0, "recyclability": 55},
            {"material": "aluminium", "score": 0.18, "co2_factor": 11.5, "recyclability": 90},
            {"material": "glass",     "score": 0.05, "co2_factor": 0.85, "recyclability": 95},
          ],
          "eco_note": "Plastic has a recyclability score of 55/100. ..."
        }
    """
    import io
    from PIL import Image

    try:
        _load_model()
        import torch
    except Exception as e:
        logger.error("[MaterialClassifier] Model initialization failed: %s", e)
        return {"material": "mixed/composite", "confidence": 0.0, "error": f"Material classifier unavailable: {e}"}

    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as e:
        return {"material": "mixed/composite", "confidence": 0.0, "error": f"Could not decode image: {e}"}

    try:
        with torch.no_grad():
            inputs = _processor(
                text=MATERIAL_TEXT,
                images=image,
                return_tensors="pt",
                padding=True,
            )
            inputs  = {k: v.to(_device) for k, v in inputs.items()}
            outputs = _model(**inputs)
            probs   = outputs.logits_per_image.softmax(dim=-1)[0]

        scores = [(MATERIAL_LABELS[i], float(probs[i])) for i in range(len(MATERIAL_LABELS))]
        scores.sort(key=lambda x: x[1], reverse=True)

        top_label, top_score = scores[0]
        co2_factor    = MATERIAL_CO2_FACTORS.get(top_label, 8.0)
        recyclability = MATERIAL_RECYCLABILITY.get(top_label, 30)

        # Build eco note
        if recyclability >= 80:
            eco_note = f"{top_label.title()} is highly recyclable ({recyclability}/100). Ensure it reaches the right recycling facility."
        elif recyclability >= 50:
            eco_note = f"{top_label.title()} has moderate recyclability ({recyclability}/100). Check local facilities for this material."
        else:
            eco_note = f"{top_label.title()} is difficult to recycle ({recyclability}/100). Consider repair or donate options first."

        top_k_result = []
        for lbl, sc in scores[:top_k]:
            top_k_result.append({
                "material":     lbl,
                "score":        round(sc, 4),
                "co2_factor":   MATERIAL_CO2_FACTORS.get(lbl, 8.0),
                "recyclability": MATERIAL_RECYCLABILITY.get(lbl, 30),
            })

        return {
            "material":      top_label,
            "confidence":    round(top_score, 4),
            "co2_factor_kg": co2_factor,
            "recyclability": recyclability,
            "top_k":         top_k_result,
            "eco_note":      eco_note,
        }
    except Exception as e:
        logger.error("[MaterialClassifier] Inference error: %s", e)
        return {"material": "mixed/composite", "confidence": 0.0, "error": f"Inference failed: {e}"}


def estimate_carbon_impact(material: str, weight_kg: float, action: str) -> dict:
    """
    Estimate CO2 impact based on material type, weight, and chosen action.

    Actions and their CO2 multipliers (fraction of production emissions saved):
      keep_using: 0.85 saved  | repair: 0.70 | resell: 0.75
      recycle: 0.55           | donate: 0.80  | discard: 0.0

    Returns detailed carbon breakdown.
    """
    co2_factor = MATERIAL_CO2_FACTORS.get(material.lower(), 8.0)
    production_co2 = weight_kg * co2_factor

    action_multipliers = {
        "keep using": 0.85, "keep_using": 0.85,
        "repair":     0.70,
        "resell":     0.75,
        "recycle":    0.55,
        "donate":     0.80,
        "discard":    0.00,
    }
    multiplier = action_multipliers.get(action.lower(), 0.5)
    co2_saved  = production_co2 * multiplier

    trees_equiv  = round(co2_saved / 21.0, 2)
    km_car_equiv = round(co2_saved / 0.21, 1)

    return {
        "material":         material,
        "weight_kg":        weight_kg,
        "action":           action,
        "production_co2":   round(production_co2, 2),
        "co2_saved_kg":     round(co2_saved, 2),
        "trees_equivalent": trees_equiv,
        "km_car_equivalent": km_car_equiv,
        "message": (
            f"By choosing to {action} this {weight_kg}kg {material} item, "
            f"you save approximately {co2_saved:.1f} kg of CO₂ — "
            f"equivalent to planting {trees_equiv} trees or not driving {km_car_equiv} km."
        ),
    }


def is_available() -> bool:
    """Return True if CLIP dependencies are installed."""
    try:
        import transformers  # noqa: F401
        import torch         # noqa: F401
        return True
    except (ImportError, ModuleNotFoundError):
        return False

