"""
Train Carbon Footprint Estimator (Model 5)
==========================================
Generates synthetic LCA-grounded training data and trains a
GradientBoostingRegressor to interpolate between known LCA table values.

Run from the backend/ directory:
    python ml/train/train_carbon.py

Output: ml/artifacts/carbon_model.pkl
"""

import os
import sys
import random
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

# ── Ensure backend is on path ─────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from ml.carbon_estimator import LCA_TABLE

ARTIFACT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "artifacts")
MODEL_PATH   = os.path.join(ARTIFACT_DIR, "carbon_model.pkl")


def generate_data(n_samples: int = 8000, seed: int = 42) -> tuple:
    """
    Generate synthetic training data from the LCA table with ±20% noise.
    Features: [cat_enc, mat_enc, weight_kg]
    Target:   base CO₂ factor (kg CO₂e / kg product)
    """
    rng = random.Random(seed)

    categories = list({cat for cat, _ in LCA_TABLE})
    materials  = list({mat for _, mat in LCA_TABLE})

    cat_enc_map = {c: i for i, c in enumerate(sorted(categories))}
    mat_enc_map = {m: i for i, m in enumerate(sorted(materials))}

    X, y = [], []
    for _ in range(n_samples):
        cat = rng.choice(categories)
        mat = rng.choice(materials)
        wt  = round(rng.uniform(0.05, 50.0), 3)

        # Base factor from LCA table (with category-material fallback)
        base = LCA_TABLE.get((cat, mat)) or LCA_TABLE.get((cat, "other")) or 10.0
        # ±20% realistic noise
        noisy = base * rng.uniform(0.80, 1.20)

        X.append([cat_enc_map[cat], mat_enc_map[mat], wt])
        y.append(noisy)

    return X, y, cat_enc_map, mat_enc_map


def train():
    try:
        from sklearn.ensemble import GradientBoostingRegressor
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import mean_absolute_error, r2_score
        import joblib
        import numpy as np
    except ImportError as e:
        logger.error("Missing dependency: %s\nRun: pip install scikit-learn joblib numpy", e)
        sys.exit(1)

    logger.info("Generating synthetic LCA training data …")
    X_raw, y_raw, cat_map, mat_map = generate_data(n_samples=8000)

    X = np.array(X_raw)
    y = np.array(y_raw)

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.15, random_state=42)

    logger.info("Training GradientBoostingRegressor on %d samples …", len(X_train))
    model = GradientBoostingRegressor(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.08,
        subsample=0.8,
        min_samples_leaf=5,
        random_state=42,
    )
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    mae   = mean_absolute_error(y_test, preds)
    r2    = r2_score(y_test, preds)
    logger.info("Test MAE: %.3f kg CO₂e/kg   |   R²: %.4f", mae, r2)

    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    joblib.dump({
        "model":      model,
        "label_maps": {"category": cat_map, "material": mat_map},
        "mae":        mae,
        "r2":         r2,
    }, MODEL_PATH)
    logger.info("Saved → %s", MODEL_PATH)


if __name__ == "__main__":
    train()
