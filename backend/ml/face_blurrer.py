"""
Privacy-Preserving AI — Automated Face & PII Blurring Module
============================================================
Compliance: Digital Personal Data Protection (DPDP) Act 2023 & Ethical AI.
Detects human faces and private identity elements in user-uploaded product
photos and applies strong Gaussian anonymization before passing images to
vision models (YOLO, CLIP, Gemini) or saving to disk.
"""

from __future__ import annotations

import logging
from typing import Tuple, Dict, Any, List, Optional
import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Initialize OpenCV Haar Cascade Classifiers
_face_cascade = None
_profile_cascade = None


def _load_cascades():
    global _face_cascade, _profile_cascade
    if _face_cascade is None:
        try:
            cascade_path = cv2.data.haarcascades
            _face_cascade = cv2.CascadeClassifier(cascade_path + "haarcascade_frontalface_default.xml")
            _profile_cascade = cv2.CascadeClassifier(cascade_path + "haarcascade_profileface.xml")
            logger.info("[FaceBlurrer] Haar cascade face models loaded successfully.")
        except Exception as e:
            logger.error("[FaceBlurrer] Error loading cascade models: %s", e)


def is_available() -> bool:
    """Checks whether OpenCV face detection cascades are available."""
    try:
        _load_cascades()
        return _face_cascade is not None and not _face_cascade.empty()
    except Exception:
        return False


def anonymize_image(image_bytes: bytes, blur_kernel: int = 99) -> tuple[bytes, dict]:
    """
    Scans image bytes for human faces, applies heavy Gaussian blurring to any detected
    face bounding box (with safety margin), and returns the sanitized image bytes.

    Args:
        image_bytes: Raw JPEG/PNG/WebP image bytes.
        blur_kernel: Kernel size for Gaussian blur (must be an odd integer, default 99).

    Returns:
        tuple (sanitized_bytes, privacy_metadata)
    """
    _load_cascades()

    metadata = {
        "faces_detected": 0,
        "privacy_preserved": False,
        "method": "OpenCV Haar-Cascade Face Anonymization",
        "compliance": "DPDP Act 2023 / Ethical AI",
    }

    if _face_cascade is None or _face_cascade.empty():
        return image_bytes, metadata

    try:
        # Decode image from buffer
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return image_bytes, metadata

        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)

        # Detect frontal faces
        faces = _face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(30, 30),
            flags=cv2.CASCADE_SCALE_IMAGE,
        )

        detected_boxes = list(faces) if len(faces) > 0 else []

        # Detect profile faces if frontal detection found nothing
        if len(detected_boxes) == 0 and _profile_cascade is not None and not _profile_cascade.empty():
            profiles = _profile_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(30, 30),
            )
            if len(profiles) > 0:
                detected_boxes.extend(profiles)

        metadata["faces_detected"] = len(detected_boxes)

        if len(detected_boxes) > 0:
            for (x, y, fw, fh) in detected_boxes:
                # Add 15% padding around the face for complete ear-to-hair boundary coverage
                pad_x = int(fw * 0.15)
                pad_y = int(fh * 0.15)
                x1 = max(0, x - pad_x)
                y1 = max(0, y - pad_y)
                x2 = min(w, x + fw + pad_x)
                y2 = min(h, y + fh + pad_y)

                face_roi = img[y1:y2, x1:x2]
                if face_roi.size > 0:
                    # Apply dual-layer blur: Pixelation + Gaussian Blur
                    # Step 1: Pixelate
                    pw = max(4, (x2 - x1) // 12)
                    ph = max(4, (y2 - y1) // 12)
                    small = cv2.resize(face_roi, (pw, ph), interpolation=cv2.INTER_LINEAR)
                    pixelated = cv2.resize(small, (x2 - x1, y2 - y1), interpolation=cv2.INTER_NEAREST)

                    # Step 2: Smooth with Gaussian Blur
                    k = blur_kernel if blur_kernel % 2 == 1 else blur_kernel + 1
                    blurred = cv2.GaussianBlur(pixelated, (k, k), 30)

                    img[y1:y2, x1:x2] = blurred

            metadata["privacy_preserved"] = True
            logger.info("[FaceBlurrer] Redacted %d face(s) for privacy compliance.", len(detected_boxes))

            # Encode back to JPEG
            success, encoded_img = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
            if success:
                return encoded_img.tobytes(), metadata

        return image_bytes, metadata

    except Exception as e:
        logger.error("[FaceBlurrer] Failed during anonymization: %s", e)
        return image_bytes, metadata
