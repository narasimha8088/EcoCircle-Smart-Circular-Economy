"""
Train Eco-Score Trend Predictor (Model 7)
==========================================
Generates synthetic user action histories and trains an XGBoost regressor
to predict 30-day eco-score delta.

Features: rolling action counts, current score, streak, diversity
Target:   eco_score_delta over 30 days

Run from the backend/ directory:
    python ml/train/train_eco_trend.py

Output: ml/artifacts/eco_trend_model.pkl
"""

import os
import sys
import random
import logging
import datetime

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

ARTIFACT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "artifacts")
MODEL_PATH   = os.path.join(ARTIFACT_DIR, "eco_trend_model.pkl")

ACTION_POINTS = {
    "donated": 20, "sold": 15, "repaired": 12,
    "recycled": 18, "added": 10,
}
ACTIONS     = list(ACTION_POINTS.keys())
CATEGORIES  = ["electronics", "clothing", "furniture", "mobile", "laptop",
               "appliance", "vehicle", "books", "sports", "other"]


def simulate_user(seed: int, history_days: int = 90) -> tuple[dict, float]:
    """
    Simulate one user's 90-day action history.
    Returns (feature_dict, eco_score_delta_30d).
    """
    rng = random.Random(seed)
    base_date = datetime.date(2025, 1, 1)

    # Random user activity profile
    activity_level = rng.uniform(0.1, 1.0)   # actions per day rate
    action_probs   = {a: rng.random() for a in ACTIONS}
    total = sum(action_probs.values())
    action_probs   = {a: v / total for a, v in action_probs.items()}

    # Generate 90 days of past actions
    history = []
    for day_offset in range(-history_days, 0):
        if rng.random() < activity_level * 0.6:
            n_actions = rng.randint(1, 3)
            for _ in range(n_actions):
                action = rng.choices(ACTIONS, weights=list(action_probs.values()))[0]
                cat    = rng.choice(CATEGORIES)
                history.append({
                    "action":    action,
                    "category":  cat,
                    "timestamp": str(base_date + datetime.timedelta(days=day_offset + history_days)),
                })

    # Generate next 30 days (for target)
    future_actions = []
    for day_offset in range(0, 30):
        if rng.random() < activity_level * 0.6:
            n_actions = rng.randint(1, 3)
            for _ in range(n_actions):
                action = rng.choices(ACTIONS, weights=list(action_probs.values()))[0]
                future_actions.append(action)

    # Current score from history
    from collections import Counter
    counts = Counter(h["action"] for h in history)
    current_score = sum(ACTION_POINTS.get(a, 5) * c for a, c in counts.items())

    # Future delta
    delta = sum(ACTION_POINTS.get(a, 5) for a in future_actions)

    # Extract features
    week_cutoff = base_date + datetime.timedelta(days=history_days - 7)
    recent = [h for h in history
              if datetime.date.fromisoformat(h["timestamp"]) >= week_cutoff]
    recent_counts = Counter(r["action"] for r in recent)
    cat_counts    = Counter(h["category"] for h in history)

    # Streak
    streak = 0
    day = base_date + datetime.timedelta(days=history_days - 1)
    action_dates = {datetime.date.fromisoformat(h["timestamp"]) for h in history}
    while day in action_dates:
        streak += 1
        day -= datetime.timedelta(days=1)

    features = {
        "total_actions":     len(history),
        "current_score":     current_score,
        "donated_total":     counts.get("donated", 0),
        "sold_total":        counts.get("sold", 0),
        "repaired_total":    counts.get("repaired", 0),
        "recycled_total":    counts.get("recycled", 0),
        "donated_7d":        recent_counts.get("donated", 0),
        "sold_7d":           recent_counts.get("sold", 0),
        "repaired_7d":       recent_counts.get("repaired", 0),
        "recycled_7d":       recent_counts.get("recycled", 0),
        "category_diversity":len(cat_counts),
        "streak":            streak,
        "actions_7d":        len(recent),
    }
    return features, float(delta)


def train():
    try:
        import numpy as np
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import mean_absolute_error, r2_score
        import joblib
    except ImportError as e:
        logger.error("Missing dependency: %s", e)
        sys.exit(1)

    try:
        from xgboost import XGBRegressor
        model = XGBRegressor(
            n_estimators=300,
            max_depth=5,
            learning_rate=0.06,
            subsample=0.8,
            colsample_bytree=0.9,
            random_state=42,
            n_jobs=-1,
            verbosity=0,
        )
        model_name = "XGBoost"
    except ImportError:
        logger.warning("xgboost not found — using GradientBoostingRegressor.")
        from sklearn.ensemble import GradientBoostingRegressor
        model = GradientBoostingRegressor(
            n_estimators=250, max_depth=4, learning_rate=0.07,
            subsample=0.8, random_state=42,
        )
        model_name = "GradientBoostingRegressor"

    n_users = 5000
    logger.info("Simulating %d users × 90-day histories …", n_users)

    feature_order = [
        "total_actions", "current_score",
        "donated_total", "sold_total", "repaired_total", "recycled_total",
        "donated_7d",    "sold_7d",    "repaired_7d",    "recycled_7d",
        "category_diversity", "streak", "actions_7d",
    ]

    rows, targets = [], []
    for seed in range(n_users):
        feats, delta = simulate_user(seed)
        rows.append([feats[f] for f in feature_order])
        targets.append(delta)

    X = np.array(rows)
    y = np.array(targets)

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.1, random_state=42)
    logger.info("Training %s on %d users …", model_name, len(X_train))
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    mae   = mean_absolute_error(y_test, preds)
    r2    = r2_score(y_test, preds)
    logger.info("Test MAE: %.1f pts   |   R²: %.4f", mae, r2)

    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    logger.info("Saved → %s", MODEL_PATH)


if __name__ == "__main__":
    train()
