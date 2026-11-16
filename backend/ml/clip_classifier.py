"""
Phase 1 Model 1: CLIP-based Category Classifier
================================================
Uses OpenAI CLIP (via HuggingFace transformers) to zero-shot classify
the product category from uploaded images.

This runs BEFORE the Gemini vision call so the category is known early
and can be passed as structured context to downstream models.

Supported categories (mapped to EcoCircle taxonomy):
  electronics, mobile, laptop, appliance, furniture,
  clothing, vehicle, books, sports, other

Lazy-loads the model on first call — no startup overhead.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Lazy globals ────────────────────────────────────────────────
_model = None
_processor = None
_device = None

# ── Category prompt templates for zero-shot classification ─────
CATEGORY_PROMPTS = {
    "mobile":      "a photo of a mobile phone or smartphone",
    "laptop":      "a photo of a laptop or notebook computer",
    "electronics": "a photo of electronic gadgets or devices",
    "appliance":   "a photo of a home appliance like a washing machine or refrigerator",
    "furniture":   "a photo of furniture like a chair, table, or shelf",
    "clothing":    "a photo of clothing, garments, shoes, or accessories",
    "vehicle":     "a photo of a vehicle, bicycle, or scooter",
    "books":       "a photo of books, notebooks, or printed materials",
    "sports":      "a photo of sports equipment or gym accessories",
    "other":       "a photo of a miscellaneous household item",
}

# CATEGORY_LABELS must keep the same order as CATEGORY_PROMPTS
CATEGORY_LABELS = list(CATEGORY_PROMPTS.keys())
CATEGORY_TEXT   = list(CATEGORY_PROMPTS.values())


def _load_model():
    """Lazy-load CLIP model and processor on first call."""
    global _model, _processor, _device
    if _model is not None:
        return

    try:
        import torch
        from transformers import CLIPModel, CLIPProcessor

        _device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("[CLIP] Loading openai/clip-vit-base-patch32 on %s …", _device)

        _processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
        _model     = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(_device)
        _model.eval()
        logger.info("[CLIP] Model loaded successfully.")

    except (ImportError, ModuleNotFoundError) as e:
        raise RuntimeError(
            f"CLIP requires 'transformers' and 'torch'. "
            f"Run: pip install transformers torch\nOriginal error: {e}"
        )


def classify_category(image_bytes: bytes, top_k: int = 3) -> dict:
    """
    Classify the product category from raw image bytes using CLIP.

    Returns:
        {
          "category":    "mobile",        # top-1 category (EcoCircle label)
          "confidence":  0.87,            # softmax probability of top-1
          "top_k": [
            {"label": "mobile",      "score": 0.87},
            {"label": "electronics", "score": 0.09},
            {"label": "other",       "score": 0.02},
          ]
        }
    """
    import io
    from PIL import Image

    try:
        _load_model()
        import torch
    except Exception as e:
        logger.error("[CLIP] Model initialization failed: %s", e)
        return {
            "category": "other",
            "confidence": 0.0,
            "error": f"CLIP classifier unavailable: {e}",
            "top_k": [],
        }

    # Decode bytes → PIL Image
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as e:
        return {"category": "other", "confidence": 0.0, "error": f"Could not decode image: {e}", "top_k": []}

    try:
        with torch.no_grad():
            inputs = _processor(
                text=CATEGORY_TEXT,
                images=image,
                return_tensors="pt",
                padding=True,
            )
            # Move to device
            inputs = {k: v.to(_device) for k, v in inputs.items()}

            outputs    = _model(**inputs)
            logits_per_image = outputs.logits_per_image  # shape: (1, num_classes)
            probs      = logits_per_image.softmax(dim=-1)[0]  # shape: (num_classes,)

        scores = [(CATEGORY_LABELS[i], float(probs[i])) for i in range(len(CATEGORY_LABELS))]
        scores.sort(key=lambda x: x[1], reverse=True)

        top_label, top_score = scores[0]

        return {
            "category":   top_label,
            "confidence": round(top_score, 4),
            "top_k":      [{"label": lbl, "score": round(sc, 4)} for lbl, sc in scores[:top_k]],
        }
    except Exception as e:
        logger.error("[CLIP] Inference error: %s", e)
        return {"category": "other", "confidence": 0.0, "error": f"Inference failed: {e}", "top_k": []}


def is_available() -> bool:
    """Return True if CLIP dependencies are installed."""
    try:
        import transformers  # noqa: F401
        import torch         # noqa: F401
        return True
    except (ImportError, ModuleNotFoundError):
        return False

