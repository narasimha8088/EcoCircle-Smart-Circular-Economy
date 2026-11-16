"""
Phase 1 + Phase 2 + Phase 3 Pipeline Orchestrator
====================================================
Phase 1 — Image analysis (runs concurrently on uploaded product images):
  Image bytes
    ├─► [M1] CLIP Category Classifier  ──► product category
    ├─► [M2] YOLOv8 Damage Detector    ──► damage severity + bbox
    ├─► [M3] EasyOCR Text Extractor    ──► brand + model number
    └─► [M4] Material Classifier       ──► material + CO2 factor

Phase 2 — Scoring & Estimation (runs on structured data from Phase 1):
  Structured inputs
    ├─► [M5] Carbon Footprint Estimator  ──► kg CO₂e saved (LCA table + GBR)
    ├─► [M6] Resale Valuation Model      ──► estimated resale price in INR
    └─► [M7] Eco-Score Trend Predictor  ──► 30-day eco-score forecast

Phase 3 — Matching & Recommendation (runs on donation flow):
  Item description + NGO list
    └─► [M8] Sentence-BERT NGO Matcher  ──► top-k NGO matches by semantic similarity

All models within each phase run in parallel using ThreadPoolExecutor.
Phase 1+2 reports are merged and injected into the Gemini context prompt.
Phase 3 report is injected into the Gemini context for donation-specific flows.

Graceful degradation:
  • Every model has an is_available() guard and a fallback return value.
  • The pipeline never crashes — missing dependencies yield empty sub-dicts.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

logger = logging.getLogger(__name__)


def run_phase1_pipeline(image_bytes: bytes, anonymize_faces: bool = True) -> dict:
    """
    Run all Phase 1 models on a single image concurrently.
    Includes automated privacy-preserving face blurring (DPDP Act 2023 compliant).

    Args:
        image_bytes: Raw bytes of the product image (JPEG/PNG/WebP).
        anonymize_faces: If True, detects and blurs any human faces before processing.

    Returns:
        PhaseOneReport dict — see schema below.
    """
    start = time.perf_counter()
    report: dict = {
        "clip_category":  None,
        "yolo_damage":    None,
        "ocr_text":       None,
        "material":       None,
        "privacy":        None,
        "pipeline_ms":    0,
        "models_available": {},
    }

    # ── Privacy Preserving Face Blurring (DPDP Act 2023) ────────
    if anonymize_faces:
        try:
            from ml.face_blurrer import is_available as blur_ok, anonymize_image
            if blur_ok():
                image_bytes, priv_meta = anonymize_image(image_bytes)
                report["privacy"] = priv_meta
        except Exception as e:
            logger.warning("[Phase1] Privacy blurring check skipped: %s", e)

    # ── Availability check ────────────────────────────────────────
    from ml.clip_classifier    import is_available as clip_ok, classify_category
    from ml.yolo_damage_detector import is_available as yolo_ok, detect_damage
    from ml.ocr_reader         import is_available as ocr_ok, extract_text
    from ml.material_classifier import is_available as mat_ok, classify_material

    availability = {
        "clip":     clip_ok(),
        "yolo":     yolo_ok(),
        "ocr":      ocr_ok(),
        "material": mat_ok(),
    }
    report["models_available"] = availability

    tasks = {}
    if availability["clip"]:
        tasks["clip_category"] = (classify_category, image_bytes)
    if availability["yolo"]:
        tasks["yolo_damage"]   = (detect_damage, image_bytes)
    if availability["ocr"]:
        tasks["ocr_text"]      = (extract_text, image_bytes)
    if availability["material"]:
        tasks["material"]      = (classify_material, image_bytes)

    # ── Run available models in parallel ─────────────────────────
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="phase1") as executor:
        futures = {
            executor.submit(fn, arg): key
            for key, (fn, arg) in tasks.items()
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                report[key] = future.result(timeout=60)
            except Exception as e:
                logger.error("[Phase1] %s failed: %s", key, e)
                report[key] = {"error": str(e)}

    report["pipeline_ms"] = round((time.perf_counter() - start) * 1000, 1)
    logger.info(
        "[Phase1] Pipeline complete in %.0f ms. Models: %s",
        report["pipeline_ms"],
        ", ".join(k for k, v in availability.items() if v),
    )
    return report


def build_gemini_context(phase1_report: dict) -> str:
    """
    Convert Phase 1 report into a structured text block to prepend
    to the Gemini vision prompt.

    This gives Gemini concrete facts to reason from, reducing hallucination
    and improving specificity of recommendations.
    """
    lines = ["## Pre-Analysis (Phase 1 ML Pipeline Results)"]
    lines.append("The following structured data was extracted before your vision analysis:\n")

    # ── CLIP Category ────────────────────────────────────────────
    clip = phase1_report.get("clip_category")
    if clip and not clip.get("error"):
        conf = clip.get("confidence", 0)
        cat  = clip.get("category", "unknown")
        lines.append(
            f"**Category Detection (CLIP):** {cat.title()} "
            f"(confidence: {conf:.0%})"
        )
        top_k = clip.get("top_k", [])
        if len(top_k) > 1:
            others = ", ".join(
                f"{t['label']} ({t['score']:.0%})"
                for t in top_k[1:]
            )
            lines.append(f"  → Other possibilities: {others}")

    # ── YOLOv8 Damage ────────────────────────────────────────────
    yolo = phase1_report.get("yolo_damage")
    if yolo and not yolo.get("error"):
        detected = yolo.get("detected_object", "unknown")
        conf     = yolo.get("detection_confidence", 0)
        summary  = yolo.get("damage_summary", "")
        dmg      = yolo.get("damage", {})
        severity = dmg.get("severity", "unknown")
        lines.append(
            f"**Object Detection (YOLOv8):** Detected '{detected}' "
            f"(confidence: {conf:.0%})"
        )
        lines.append(f"**Damage Assessment:** {severity.upper()} — {summary}")

    # ── EasyOCR Text ─────────────────────────────────────────────
    ocr = phase1_report.get("ocr_text")
    if ocr and not ocr.get("error"):
        brand  = ocr.get("brand")
        model  = ocr.get("model_number")
        texts  = ocr.get("all_text", [])
        if brand:
            lines.append(f"**Brand (OCR):** {brand}")
        if model:
            lines.append(f"**Model Number (OCR):** {model}")
        if texts and not brand and not model:
            preview = ", ".join(f'"{t}"' for t in texts[:5])
            lines.append(f"**OCR Text Found:** {preview}")

    # ── Material ─────────────────────────────────────────────────
    mat = phase1_report.get("material")
    if mat and not mat.get("error"):
        material      = mat.get("material", "unknown")
        conf          = mat.get("confidence", 0)
        co2_factor    = mat.get("co2_factor_kg", 0)
        recyclability = mat.get("recyclability", 0)
        eco_note      = mat.get("eco_note", "")
        lines.append(
            f"**Material Composition (CLIP zero-shot):** {material.title()} "
            f"(confidence: {conf:.0%}, CO₂ factor: {co2_factor} kg/kg, "
            f"recyclability: {recyclability}/100)"
        )
        if eco_note:
            lines.append(f"  → {eco_note}")

    # ── Footer ────────────────────────────────────────────────────
    ms = phase1_report.get("pipeline_ms", 0)
    active = [k for k, v in phase1_report.get("models_available", {}).items() if v]
    lines.append(
        f"\n*Pipeline ran {len(active)} model(s) ({', '.join(active)}) in {ms:.0f} ms.*"
    )
    lines.append(
        "Use the above structured data to ground your analysis. "
        "If the image confirms or contradicts these facts, note it explicitly.\n"
    )
    return "\n".join(lines)


def get_phase1_summary(phase1_report: dict) -> dict:
    """
    Extract key structured facts from the Phase 1 report for API response.
    Returns a clean, minimal dict to attach to the final JSON response.
    """
    summary = {}

    clip = phase1_report.get("clip_category")
    if clip and not clip.get("error"):
        summary["detected_category"]   = clip.get("category")
        summary["category_confidence"] = clip.get("confidence")

    yolo = phase1_report.get("yolo_damage")
    if yolo and not yolo.get("error"):
        summary["detected_object"]      = yolo.get("detected_object")
        summary["damage_severity"]      = yolo.get("damage", {}).get("severity")
        summary["damage_summary"]       = yolo.get("damage_summary")

    ocr = phase1_report.get("ocr_text")
    if ocr and not ocr.get("error"):
        summary["brand"]       = ocr.get("brand")
        summary["model_number"] = ocr.get("model_number")
        summary["ocr_texts"]   = ocr.get("all_text", [])[:8]

    mat = phase1_report.get("material")
    if mat and not mat.get("error"):
        summary["material"]          = mat.get("material")
        summary["material_confidence"] = mat.get("confidence")
        summary["co2_factor_kg"]     = mat.get("co2_factor_kg")
        summary["recyclability"]     = mat.get("recyclability")
        summary["material_eco_note"] = mat.get("eco_note")

    priv = phase1_report.get("privacy")
    if priv:
        summary["privacy_protection"] = {
            "faces_redacted": priv.get("faces_detected", 0),
            "privacy_preserved": priv.get("privacy_preserved", False),
            "compliance": priv.get("compliance", "DPDP Act 2023"),
        }

    summary["pipeline_ms"]       = phase1_report.get("pipeline_ms")
    summary["models_active"]     = [
        k for k, v in phase1_report.get("models_available", {}).items() if v
    ]

    return summary


# ════════════════════════════════════════════════════════════════════════════
#  Phase 2 Pipeline
# ════════════════════════════════════════════════════════════════════════════

def run_phase2_pipeline(
    category:       str,
    material:       str       = "other",
    weight_kg:      float     = 1.0,
    action:         str       = "recycle",
    purchase_price: float     = 0.0,
    age_years:      float     = 0.0,
    condition:      str       = "good",
    brand:          str       = "",
    user_history:   list      = None,
) -> dict:
    """
    Run all Phase 2 scoring models concurrently.

    Args:
        category:       Product category (from Phase 1 CLIP or user input)
        material:       Primary material (from Phase 1 or user input)
        weight_kg:      Product weight
        action:         Intended circular-economy action
        purchase_price: Original purchase price (INR)
        age_years:      Age in years
        condition:      Product condition string
        brand:          Brand name string
        user_history:   List of past user action dicts (for eco-trend)

    Returns:
        PhaseTwoReport dict.
    """
    from ml.carbon_estimator import predict as carbon_predict
    from ml.resale_model     import predict as resale_predict
    from ml.eco_trend_model  import predict_trend

    if user_history is None:
        user_history = []

    start = time.perf_counter()

    report: dict = {
        "carbon":     None,
        "resale":     None,
        "eco_trend":  None,
        "pipeline_ms": 0,
    }

    def _run_carbon():
        return carbon_predict(category, material, weight_kg, action)

    def _run_resale():
        if purchase_price <= 0:
            return None
        return resale_predict(purchase_price, age_years, condition, category, brand)

    def _run_eco_trend():
        return predict_trend(user_history)

    tasks = {
        "carbon":    _run_carbon,
        "resale":    _run_resale,
        "eco_trend": _run_eco_trend,
    }

    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="phase2") as executor:
        futures = {executor.submit(fn): key for key, fn in tasks.items()}
        for future in as_completed(futures):
            key = futures[future]
            try:
                report[key] = future.result(timeout=30)
            except Exception as e:
                logger.error("[Phase2] %s failed: %s", key, e)
                report[key] = {"error": str(e)}

    report["pipeline_ms"] = round((time.perf_counter() - start) * 1000, 1)
    logger.info("[Phase2] Pipeline complete in %.0f ms.", report["pipeline_ms"])
    return report


def build_phase2_gemini_context(phase2_report: dict) -> str:
    """
    Convert Phase 2 report into a structured text block to prepend
    to the Gemini vision prompt alongside Phase 1 context.
    """
    lines = ["## Phase 2 Scoring & Estimation Results\n"]

    # ── Carbon (M5) ────────────────────────────────────────────────────────────
    carbon = phase2_report.get("carbon")
    if carbon and not carbon.get("error"):
        lines.append(
            f"**Carbon Footprint (M5 — LCA Estimator):** "
            f"{carbon.get('carbon_total_kg', 0):.2f} kg CO₂e lifecycle | "
            f"Saves {carbon.get('carbon_saved_kg', 0):.2f} kg CO₂e by "
            f"{carbon.get('action', 'recycling')} "
            f"(≈ {carbon.get('trees_equivalent', 0)} trees / "
            f"{carbon.get('car_km_equivalent', 0)} km avoided). "
            f"[Confidence: {carbon.get('confidence', 'lca_table')}]"
        )

    # ── Resale (M6) ────────────────────────────────────────────────────────────
    resale = phase2_report.get("resale")
    if resale and not resale.get("error") and resale:
        lo, hi = resale.get("price_range", [0, 0])
        lines.append(
            f"**Resale Valuation (M6 — XGBoost):** "
            f"₹{resale.get('estimated_price', 0):,.0f} "
            f"(range ₹{lo:,.0f} – ₹{hi:,.0f}). "
            f"Depreciation: {resale.get('depreciation_pct', 0)}%. "
            f"[Confidence: {resale.get('confidence', 'formula')}]"
        )

    # ── Eco Trend (M7) ─────────────────────────────────────────────────────────
    trend = phase2_report.get("eco_trend")
    if trend and not trend.get("error"):
        lines.append(
            f"**Eco-Score Trend (M7):** Current score {trend.get('current_score', 0)} pts → "
            f"Predicted {trend.get('predicted_30d', 0)} pts in 30 days "
            f"({trend.get('trend', 'stable').upper()}, +{trend.get('change_pct', 0)}%). "
            f"Top driver: {trend.get('top_driver', 'activity')}."
        )

    ms = phase2_report.get("pipeline_ms", 0)
    lines.append(f"\n*Phase 2 ran in {ms:.0f} ms.*")
    lines.append(
        "Use these numeric estimates to validate your qualitative analysis. "
        "Reference the resale price and carbon savings in your response.\n"
    )
    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════════════
#  Phase 3 Pipeline — M8 Sentence-BERT NGO Matching
# ════════════════════════════════════════════════════════════════════════════

def run_phase3_pipeline(
    item_description: str,
    ngo_list: list,
    top_k: int = 5,
) -> dict:
    """
    Run Phase 3 (M8) to semantically match a donated item to NGOs.

    Args:
        item_description: Free-text item description from the user.
        ngo_list:         Full list of NGO dicts.
        top_k:            Number of top NGO matches to return.

    Returns:
        PhaseThreeReport dict with top_matches, method, pipeline_ms.
    """
    from ml.ngo_matcher import match_ngos, is_available as m8_ok

    start = time.perf_counter()
    report: dict = {
        "top_matches":    [],
        "match_method":   "unavailable",
        "query":          item_description,
        "pipeline_ms":    0,
        "m8_available":   m8_ok(),
    }

    try:
        matches = match_ngos(item_description, ngo_list, top_k=top_k)
        report["top_matches"]  = matches
        report["match_method"] = matches[0]["match_method"] if matches else "none"
    except Exception as e:
        logger.error("[Phase3] M8 match_ngos failed: %s", e)
        report["error"] = str(e)

    report["pipeline_ms"] = round((time.perf_counter() - start) * 1000, 1)
    logger.info(
        "[Phase3] Pipeline complete in %.0f ms. Method: %s, Matches: %d",
        report["pipeline_ms"],
        report["match_method"],
        len(report["top_matches"]),
    )
    return report


def build_phase3_gemini_context(phase3_report: dict) -> str:
    """
    Convert Phase 3 report into a structured text block to inject
    into Gemini's donation-flow prompt.
    """
    lines = ["## Phase 3 — NGO Semantic Matching Results (M8)\n"]
    matches = phase3_report.get("top_matches", [])
    method  = phase3_report.get("match_method", "unknown")
    query   = phase3_report.get("query", "")

    lines.append(f"**Item Query:** \"{query}\"")
    lines.append(f"**Match Method:** {method} ({'Sentence-BERT' if method == 'semantic' else 'keyword fallback'})\n")

    if matches:
        lines.append("**Top Matched NGOs:**")
        for i, ngo in enumerate(matches[:3], 1):
            sim    = ngo.get("similarity_score", 0)
            score  = ngo.get("combined_score", 0)
            urgency = ngo.get("urgency", 0)
            needs  = ", ".join(ngo.get("needs", [])[:3])
            lines.append(
                f"  {i}. {ngo.get('name')} — Similarity: {sim:.0%}, "
                f"Urgency: {urgency}%, Needs: {needs}"
            )
    else:
        lines.append("No strong NGO matches found.")

    ms = phase3_report.get("pipeline_ms", 0)
    lines.append(f"\n*Phase 3 ran in {ms:.0f} ms.*")
    lines.append(
        "Use these NGO matches to guide your donation recommendation. "
        "Prioritise NGOs with high urgency and high semantic similarity.\n"
    )
    return "\n".join(lines)

