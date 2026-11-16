"""
Phase 1 Model 3: EasyOCR Brand/Model Reader
============================================
Uses EasyOCR to extract text from product images — capturing brand names,
model numbers, serial numbers, and specification labels that appear on:
  • Product labels / stickers
  • Screen text
  • Packaging (if visible)
  • Engraved text on device bodies

The extracted text is:
  1. Filtered to likely brand/model patterns (regex + confidence threshold)
  2. Normalized and deduplicated
  3. Matched against a known brand registry for product category hints

This structured output is passed as context to Gemini so it can make
more accurate recommendations without having to guess the brand from
a blurry label.

Lazy-loads EasyOCR reader on first call.
Supports: en (English) + optionally additional language codes.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ── Lazy globals ─────────────────────────────────────────────────
_reader = None

# ── Known brand → EcoCircle category mapping ─────────────────────
BRAND_CATEGORY_MAP = {
    # Mobile
    "apple": "mobile", "samsung": "mobile", "xiaomi": "mobile",
    "redmi": "mobile", "realme": "mobile", "oneplus": "mobile",
    "oppo": "mobile", "vivo": "mobile", "motorola": "mobile",
    "nokia": "mobile", "iqoo": "mobile", "poco": "mobile",
    "google": "mobile", "nothing": "mobile",
    # Laptop
    "dell": "laptop", "hp": "laptop", "lenovo": "laptop",
    "asus": "laptop", "acer": "laptop", "msi": "laptop",
    "lg": "laptop", "microsoft": "laptop", "razer": "laptop",
    # Electronics / gadgets
    "sony": "electronics", "bose": "electronics", "jbl": "electronics",
    "logitech": "electronics", "boat": "electronics", "skullcandy": "electronics",
    "anker": "electronics", "belkin": "electronics",
    # Appliances
    "whirlpool": "appliance", "lg": "appliance", "samsung": "appliance",
    "bosch": "appliance", "siemens": "appliance", "philips": "appliance",
    "havells": "appliance", "bajaj": "appliance", "prestige": "appliance",
    "crompton": "appliance", "voltas": "appliance", "godrej": "appliance",
    # Furniture
    "ikea": "furniture", "hometown": "furniture", "nilkamal": "furniture",
    # Sports / Fitness
    "nike": "sports", "adidas": "sports", "puma": "sports",
    "reebok": "sports", "yonex": "sports", "cosco": "sports",
    # Books / Office
    "penguin": "books", "oxford": "books",
}

# ── Regex patterns for brand/model extraction ─────────────────────
MODEL_NUMBER_PATTERN = re.compile(
    r'\b([A-Z]{1,5}[-\s]?\d{2,6}[A-Z0-9]{0,4})\b',  # e.g. SM-G975F, M2003J15SC
    re.IGNORECASE
)
BRAND_PATTERN = re.compile(
    r'\b(' + '|'.join(re.escape(b) for b in BRAND_CATEGORY_MAP.keys()) + r')\b',
    re.IGNORECASE
)

# Minimum confidence for OCR text to be included
MIN_CONFIDENCE = 0.40


def _load_reader():
    """Lazy-load EasyOCR reader on first call."""
    global _reader
    if _reader is not None:
        return

    try:
        import easyocr
        logger.info("[EasyOCR] Initializing reader (en) …")
        # gpu=False ensures CPU compatibility; set gpu=True if CUDA is available
        _reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        logger.info("[EasyOCR] Reader ready.")
    except ImportError as e:
        raise RuntimeError(
            f"EasyOCR requires 'easyocr'. Run: pip install easyocr\nError: {e}"
        )


def extract_text(image_bytes: bytes) -> dict:
    """
    Extract brand, model number, and all readable text from product image.

    Returns:
        {
          "brand":          "Samsung",
          "model_number":   "SM-G975F",
          "category_hint":  "mobile",      # derived from brand
          "all_text":       ["SAMSUNG", "SM-G975F", "IMEI", "Made in Vietnam"],
          "raw_detections": [
            {"text": "SAMSUNG", "confidence": 0.99, "bbox": [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]},
            ...
          ]
        }
    """
    import io
    import numpy as np
    from PIL import Image

    try:
        _load_reader()
    except Exception as e:
        logger.error("[EasyOCR] Reader initialization failed: %s", e)
        return {"error": f"EasyOCR unavailable: {e}"}

    # Decode image
    try:
        pil_img   = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img_array = np.array(pil_img)
    except Exception as e:
        return {"error": f"Could not decode image: {e}"}

    # Run OCR
    try:
        detections = _reader.readtext(img_array, detail=1, paragraph=False)
    except Exception as e:
        logger.warning("[EasyOCR] OCR failed: %s", e)
        return {"error": str(e)}

    # Filter by confidence threshold
    raw_detections = []
    all_texts      = []

    for (bbox, text, conf) in detections:
        if conf >= MIN_CONFIDENCE and text.strip():
            clean = text.strip()
            raw_detections.append({
                "text":       clean,
                "confidence": round(conf, 4),
                "bbox":       [[int(p[0]), int(p[1])] for p in bbox],
            })
            all_texts.append(clean)

    # ── Extract brand ──────────────────────────────────────────
    combined_text = " ".join(all_texts)
    brand         = None
    category_hint = None

    brand_match = BRAND_PATTERN.search(combined_text)
    if brand_match:
        brand         = brand_match.group(0).title()
        category_hint = BRAND_CATEGORY_MAP.get(brand.lower(), None)

    # ── Extract model number ───────────────────────────────────
    model_number = None
    model_match  = MODEL_NUMBER_PATTERN.search(combined_text)
    if model_match:
        model_number = model_match.group(0).upper().strip()

    # ── Fallback: pick highest-confidence large text as brand ──
    if not brand and raw_detections:
        # Sort by confidence * text_length heuristic
        sorted_dets = sorted(
            raw_detections,
            key=lambda d: d["confidence"] * len(d["text"]),
            reverse=True,
        )
        brand = sorted_dets[0]["text"].title() if sorted_dets else None

    return {
        "brand":          brand,
        "model_number":   model_number,
        "category_hint":  category_hint,
        "all_text":       all_texts,
        "raw_detections": raw_detections,
    }


def is_available() -> bool:
    """Return True if EasyOCR is installed."""
    try:
        import easyocr  # noqa: F401
        return True
    except ImportError:
        return False
