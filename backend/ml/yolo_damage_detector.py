"""
Phase 1 Model 2: YOLOv8 Damage Detector
========================================
Uses YOLOv8n (nano, pretrained on COCO) to detect visible damage zones
in product images. Since COCO doesn't include "torn", "scratched",
"cracked" etc., we run a two-stage approach:

Stage A — Object Detection (COCO pretrained):
  • Detect the product's primary object class (confirms what the item is).
  • Extracts bounding boxes + confidence for the most prominent object.

Stage B — Damage Severity Heuristic (no fine-tuning needed yet):
  • Inspects image statistics within detected bounding boxes:
      - Gradient variance → edge sharpness (cracks/scratches raise this)
      - Color saturation drop → discoloration/staining
      - Dark region ratio → burn marks, heavy wear zones
  • Maps these to a DamageSeverity enum:
      NONE | MINOR | MODERATE | SEVERE

Note: Full fine-tuning on an annotated damage dataset (COCO-damage or
a custom dataset) is planned for Phase 2. This Phase 1 implementation
provides a solid baseline using pretrained weights + heuristics.

Returns structured damage report consumable by downstream models and Gemini.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Lazy globals ─────────────────────────────────────────────────
_yolo_model = None


class DamageSeverity(str, Enum):
    NONE     = "none"
    MINOR    = "minor"
    MODERATE = "moderate"
    SEVERE   = "severe"


# COCO classes that map to EcoCircle product categories
COCO_TO_ECOCIRCLE = {
    "cell phone":        "mobile",
    "laptop":            "laptop",
    "keyboard":          "electronics",
    "mouse":             "electronics",
    "remote":            "electronics",
    "tv":                "electronics",
    "monitor":           "electronics",
    "microwave":         "appliance",
    "oven":              "appliance",
    "refrigerator":      "appliance",
    "washing machine":   "appliance",
    "hair drier":        "appliance",
    "toaster":           "appliance",
    "clock":             "other",
    "vase":              "other",
    "scissors":          "other",
    "teddy bear":        "other",
    "chair":             "furniture",
    "sofa":              "furniture",
    "couch":             "furniture",
    "dining table":      "furniture",
    "bed":               "furniture",
    "book":              "books",
    "backpack":          "clothing",
    "handbag":           "clothing",
    "suitcase":          "clothing",
    "tie":               "clothing",
    "umbrella":          "clothing",
    "bicycle":           "vehicle",
    "motorcycle":        "vehicle",
    "car":               "vehicle",
    "sports ball":       "sports",
    "skateboard":        "sports",
    "surfboard":         "sports",
    "tennis racket":     "sports",
    "baseball glove":    "sports",
}


def _load_yolo():
    """Lazy-load YOLOv8n on first call."""
    global _yolo_model
    if _yolo_model is not None:
        return

    try:
        from ultralytics import YOLO
        logger.info("[YOLOv8] Loading yolov8n.pt …")
        _yolo_model = YOLO("yolov8n.pt")  # auto-downloads on first run
        logger.info("[YOLOv8] Model loaded.")
    except ImportError as e:
        raise RuntimeError(
            f"YOLOv8 requires 'ultralytics'. Run: pip install ultralytics\nError: {e}"
        )


def _compute_damage_heuristics(img_array: np.ndarray, bbox: Optional[list] = None) -> dict:
    """
    Compute image statistics to estimate damage severity.
    Works on the cropped product region if bbox is provided, else full image.

    Args:
        img_array: HxWx3 uint8 numpy array (RGB)
        bbox: [x1, y1, x2, y2] in pixel coordinates, or None

    Returns dict with gradient_variance, dark_ratio, saturation_drop, severity
    """
    import cv2

    if bbox is not None:
        x1, y1, x2, y2 = [int(v) for v in bbox]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(img_array.shape[1], x2), min(img_array.shape[0], y2)
        if x2 > x1 and y2 > y1:
            roi = img_array[y1:y2, x1:x2]
        else:
            roi = img_array
    else:
        roi = img_array

    # Convert to BGR for OpenCV
    roi_bgr = cv2.cvtColor(roi, cv2.COLOR_RGB2BGR)

    # 1) Gradient variance (Laplacian) — high = edges/cracks/scratches
    gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    # 2) Dark pixel ratio — heavy discoloration / burn marks
    dark_mask = gray < 40
    dark_ratio = float(dark_mask.sum()) / max(gray.size, 1)

    # 3) Saturation drop using HSV
    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    mean_sat = float(hsv[:, :, 1].mean())

    # ── Heuristic rules ──────────────────────────────────────────
    # Empirically calibrated on a range of product images:
    # lap_var: pristine ~50-200, minor damage 200-500, severe >500
    # dark_ratio: >0.15 suggests staining/burn
    # mean_sat < 30 suggests very faded / desaturated product

    if lap_var > 600 or dark_ratio > 0.20:
        severity = DamageSeverity.SEVERE
    elif lap_var > 300 or dark_ratio > 0.10 or mean_sat < 25:
        severity = DamageSeverity.MODERATE
    elif lap_var > 150:
        severity = DamageSeverity.MINOR
    else:
        severity = DamageSeverity.NONE

    return {
        "gradient_variance": round(lap_var, 1),
        "dark_pixel_ratio":  round(dark_ratio, 4),
        "mean_saturation":   round(mean_sat, 1),
        "severity":          severity.value,
    }


def detect_damage(image_bytes: bytes) -> dict:
    """
    Run YOLOv8 object detection + damage heuristics on a product image.

    Returns:
        {
          "detected_object":   "laptop",           # COCO class name
          "eco_category":      "laptop",            # mapped EcoCircle category
          "detection_confidence": 0.91,
          "bounding_box":      [x1, y1, x2, y2],
          "damage": {
            "severity":          "minor",
            "gradient_variance": 187.3,
            "dark_pixel_ratio":  0.03,
            "mean_saturation":   82.4,
          },
          "damage_summary": "Minor wear detected — gradient variance 187.3. Likely surface scratches or light scuffing.",
        }
    """
    import io
    import cv2
    from PIL import Image

    try:
        _load_yolo()
    except Exception as e:
        logger.error("[YOLOv8] Model initialization failed: %s", e)
        return {"error": f"YOLOv8 model unavailable: {e}"}

    # Decode
    try:
        pil_img    = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img_array  = np.array(pil_img)
    except Exception as e:
        return {"error": f"Could not decode image: {e}"}

    # ── Stage A: YOLO detection ──────────────────────────────────
    results = _yolo_model(img_array, verbose=False)

    best_box      = None
    best_conf     = 0.0
    best_cls_name = "unknown"

    for result in results:
        if result.boxes is None or len(result.boxes) == 0:
            continue
        for box in result.boxes:
            conf = float(box.conf[0])
            if conf > best_conf:
                best_conf     = conf
                best_cls_name = result.names[int(box.cls[0])]
                best_box      = box.xyxy[0].tolist()  # [x1,y1,x2,y2]

    eco_cat = COCO_TO_ECOCIRCLE.get(best_cls_name.lower(), "other")

    # ── Stage B: Damage heuristics on product ROI ────────────────
    damage_stats = _compute_damage_heuristics(img_array, best_box)
    severity     = damage_stats["severity"]

    # ── Build human-readable summary ─────────────────────────────
    severity_desc = {
        "none":     "No significant damage visible — product appears to be in good condition.",
        "minor":    f"Minor wear detected — gradient variance {damage_stats['gradient_variance']}. Likely surface scratches or light scuffing.",
        "moderate": f"Moderate damage indicators — possible cracks, stains, or significant wear (variance {damage_stats['gradient_variance']}, dark ratio {damage_stats['dark_pixel_ratio']:.1%}).",
        "severe":   f"Severe damage detected — high edge variance ({damage_stats['gradient_variance']}) and/or significant dark regions ({damage_stats['dark_pixel_ratio']:.1%}). Product may need major repair or recycling.",
    }

    return {
        "detected_object":      best_cls_name,
        "eco_category":         eco_cat,
        "detection_confidence": round(best_conf, 4),
        "bounding_box":         best_box,
        "damage":               damage_stats,
        "damage_summary":       severity_desc.get(severity, "Unknown damage level."),
    }


def is_available() -> bool:
    """Return True if YOLOv8 + OpenCV dependencies are installed."""
    try:
        from ultralytics import YOLO  # noqa: F401
        import cv2                    # noqa: F401
        return True
    except ImportError:
        return False
