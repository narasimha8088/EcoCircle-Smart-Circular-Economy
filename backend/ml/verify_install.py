"""
Phase 1 Installation Verification Script
=========================================
Run from the backend/ directory:
    python ml/verify_install.py

Checks that all Phase 1 ML dependencies are installed and functional.
"""
import sys
import importlib

CHECKS = [
    ("torch",          "PyTorch"),
    ("transformers",   "HuggingFace Transformers"),
    ("PIL",            "Pillow"),
    ("ultralytics",    "Ultralytics YOLOv8"),
    ("cv2",            "OpenCV"),
    ("easyocr",        "EasyOCR"),
    ("numpy",          "NumPy"),
]

print("\n=== Phase 1 Dependency Check ===\n")
all_ok = True

for module, label in CHECKS:
    try:
        mod = importlib.import_module(module)
        version = getattr(mod, "__version__", "unknown")
        print(f"  [OK] {label:<30} {version}")
    except ImportError as e:
        print(f"  [MISSING] {label:<30} {e}")
        all_ok = False

print()

if all_ok:
    print("[OK] All Phase 1 dependencies installed.\n")
    print("Next: Start the Flask server and hit GET /api/ai/models/health")
else:
    print("[ERROR] Some dependencies are missing.")
    print("   Run: pip install -r requirements.txt")
    sys.exit(1)
