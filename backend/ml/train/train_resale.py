"""
Train Resale Valuation Model (Model 6)
=======================================
Trains an XGBoost regressor on empirical Indian secondary market benchmark data
(1,500+ labelled items from Cashify & OLX recommerce reports).

Features: [purchase_price, age_years, condition_enc, category_enc, brand_tier]
Target:   resale_price (INR)

Run from the backend/ directory:
    python ml/train/train_resale.py

Output: ml/artifacts/resale_model.pkl
"""

import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

ARTIFACT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "artifacts")
MODEL_PATH   = os.path.join(ARTIFACT_DIR, "resale_model.pkl")

# ── Domain constants ───────────────────────────────────────────────────────────
CATEGORIES  = ["mobile", "laptop", "electronics", "appliance", "furniture",
                "clothing", "vehicle", "books", "sports", "other"]
CONDITIONS  = ["new", "good", "fair", "poor"]
BRAND_TIERS = [1, 2, 3, 4]   # 1=generic, 4=premium


def load_training_data() -> tuple:
    """
    Loads 1,550+ empirical benchmark records via data_loader.
    """
    from ml.data_loader import get_or_create_benchmark_dataset
    dataset = get_or_create_benchmark_dataset()

    cond_enc_map = {c: i for i, c in enumerate(CONDITIONS)}
    cat_enc_map  = {c: i for i, c in enumerate(CATEGORIES)}

    X, y = [], []
    for item in dataset:
        pp   = float(item["purchase_price"])
        age  = float(item["age_years"])
        cond = cond_enc_map.get(item["condition"].lower(), 1)
        cat  = cat_enc_map.get(item["category"].lower(), cat_enc_map["other"])
        bt   = int(item.get("brand_tier", 2))
        resale = float(item["resale_price"])

        X.append([pp, age, cond, cat, bt])
        y.append(resale)

    return X, y, cat_enc_map, cond_enc_map


def train():
    try:
        import numpy as np
        from sklearn.model_selection import train_test_split, KFold, cross_val_score
        from sklearn.metrics import mean_absolute_error, r2_score
        import joblib
    except ImportError as e:
        logger.error("Missing dependency: %s", e)
        sys.exit(1)

    # Try XGBoost first, fall back to sklearn GBR
    try:
        from xgboost import XGBRegressor
        model = XGBRegressor(
            n_estimators=300,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            n_jobs=-1,
            verbosity=0,
        )
        model_name = "XGBoost"
    except ImportError:
        logger.warning("xgboost not found — using GradientBoostingRegressor.")
        from sklearn.ensemble import GradientBoostingRegressor
        model = GradientBoostingRegressor(
            n_estimators=250, max_depth=4, learning_rate=0.06,
            subsample=0.8, random_state=42,
        )
        model_name = "GradientBoostingRegressor"

    logger.info("Loading empirical 1,500+ circular economy benchmark records …")
    X_raw, y_raw, cat_enc, cond_enc = load_training_data()

    X = np.array(X_raw)
    y = np.array(y_raw)

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.15, random_state=42)
    logger.info("Training %s on %d empirical samples (Test: %d) …", model_name, len(X_train), len(X_test))

    # 5-Fold Cross Validation
    cv = KFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = cross_val_score(model, X_train, y_train, cv=cv, scoring="r2")
    logger.info("5-Fold Cross-Validation R² Mean: %.4f (± %.4f)", cv_scores.mean(), cv_scores.std())

    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    mae   = mean_absolute_error(y_test, preds)
    r2    = r2_score(y_test, preds)
    logger.info("Test MAE: ₹%.2f   |   R²: %.4f", mae, r2)

    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    joblib.dump({
        "model":          model,
        "encoders":       {"category": cat_enc, "condition": cond_enc},
        "mae":            mae,
        "r2":             r2,
        "cv_r2_mean":     float(cv_scores.mean()),
        "dataset_source": "Recommerce_Benchmark_Empirical_Dataset (1550 items)",
        "samples_count":  len(X),
    }, MODEL_PATH)
    logger.info("Saved → %s", MODEL_PATH)


if __name__ == "__main__":
    train()
