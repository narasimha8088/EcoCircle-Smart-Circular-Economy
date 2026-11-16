"""
warmup.py — keep the slow ML imports/model loads OFF the request path.

Why this exists
---------------
The app runs on a single eventlet thread. Importing torch / transformers / ultralytics / easyocr,
or loading CLIP / YOLO / OCR weights, takes seconds to minutes and is CPU-bound. If that happens
inside a request, the WHOLE server freezes: page fetches, tab switches and API calls all queue
behind it. That is what made switching tabs slow right after `python app.py`.

So:
  * Availability checks use importlib.util.find_spec() (instant, imports nothing).
  * Heavy loading happens in a REAL OS thread (not an eventlet green thread), started in the
    background — at most once — and requests simply don't wait for it.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import time

logger = logging.getLogger(__name__)


def _orig_threading():
    """The real `threading` module, even when eventlet has monkey-patched it."""
    try:
        from eventlet import patcher
        return patcher.original("threading")
    except Exception:
        import threading
        return threading


_th = _orig_threading()

# Held while heavy models are loading, so Phase-1 inference never loads the same model twice.
heavy_lock = _th.Lock()
_state_lock = _th.Lock()
_state = {"light": "idle", "heavy": "idle"}      # idle | running | done | failed | unavailable


def installed(top_level_module: str) -> bool:
    """True if a package is installed. Does NOT import it (find_spec on a top-level name is cheap)."""
    try:
        return importlib.util.find_spec(top_level_module) is not None
    except (ImportError, ValueError, AttributeError):
        return False


def status() -> dict:
    with _state_lock:
        return dict(_state)


def _set(kind: str, value: str) -> None:
    with _state_lock:
        _state[kind] = value


def _claim(kind: str) -> bool:
    """Atomically move idle/failed -> running. Returns False if already running or done."""
    with _state_lock:
        if _state[kind] in ("running", "done"):
            return False
        _state[kind] = "running"
        return True


def _spawn(target) -> None:
    t = _th.Thread(target=target, daemon=True)
    t.start()


# ── Light warm-up: the scikit-learn / xgboost scoring models (Phase 2) ────────────────────────
def start_light(delay: float = 2.0) -> None:
    """Pre-import the Phase-2 scoring pipeline shortly after start-up (about a second of work)."""
    if not _claim("light"):
        return

    def work():
        try:
            time.sleep(delay)        # let the first page load finish first
            from ml.pipeline import run_phase2_pipeline
            run_phase2_pipeline(category="mobile", material="plastic", weight_kg=0.2, action="recycle",
                                purchase_price=1000, age_years=1, condition="good", brand="", user_history=[])
            _set("light", "done")
            logger.info("[Warmup] Phase 2 scoring models ready.")
        except BaseException as e:   # never crash the thread
            _set("light", "failed")
            logger.info("[Warmup] Phase 2 warm-up skipped: %s", e)

    _spawn(work)


# ── Heavy warm-up: CLIP / material CLIP / YOLO / OCR (Phase 1 image models) ───────────────────
_HEAVY_STEPS = (
    ("torch",        "ml.clip_classifier",      "_load_model"),
    ("torch",        "ml.material_classifier",  "_load_model"),
    ("ultralytics",  "ml.yolo_damage_detector", "_load_yolo"),
    ("easyocr",      "ml.ocr_reader",           "_load_reader"),
)


def heavy_dependencies_present() -> bool:
    return any(installed(dep) for dep, _, _ in _HEAVY_STEPS)


def start_heavy() -> None:
    """Load the Phase-1 image models in the background. Safe to call on every request: runs once."""
    if not heavy_dependencies_present():
        _set("heavy", "unavailable")
        return
    if not _claim("heavy"):
        return

    def work():
        ok = False
        try:
            with heavy_lock:
                for dep, module_name, loader in _HEAVY_STEPS:
                    if not installed(dep):
                        continue
                    try:
                        module = importlib.import_module(module_name)
                        getattr(module, loader)()
                        ok = True
                    except BaseException as e:
                        logger.info("[Warmup] %s not loaded: %s", module_name, e)
            _set("heavy", "done" if ok else "failed")
            logger.info("[Warmup] Phase 1 image models %s.", "ready" if ok else "unavailable")
        except BaseException as e:
            _set("heavy", "failed")
            logger.info("[Warmup] Phase 1 warm-up failed: %s", e)

    _spawn(work)
