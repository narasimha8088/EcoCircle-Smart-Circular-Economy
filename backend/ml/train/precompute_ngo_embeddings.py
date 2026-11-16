"""
Pre-compute NGO Embeddings
===========================
Encodes all NGO need profiles using Sentence-BERT and saves the
embeddings to ml/artifacts/ngo_embeddings.pkl.

Run once from the backend/ directory:
    python ml/train/precompute_ngo_embeddings.py

Idempotent — safe to re-run to refresh embeddings after adding new NGOs.
"""

import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

# Ensure backend/ is on sys.path regardless of CWD
_this_dir    = os.path.dirname(os.path.abspath(__file__))          # backend/ml/train/
_ml_dir      = os.path.dirname(_this_dir)                           # backend/ml/
_backend_dir = os.path.dirname(_ml_dir)                             # backend/
for _p in [_backend_dir, _ml_dir]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── Full NGO list (mirrors donate_routes.py) ──────────────────────────────────
NGO_LIST = [
    {"id": 1,  "name": "Clothes for All",      "category": "Clothes",     "location": "Koramangala, Bengaluru",    "urgency": 92, "needs": ["Clothes", "Blankets", "Shoes"],             "open": True},
    {"id": 2,  "name": "HelpHands Foundation", "category": "Clothes",     "location": "Indiranagar, Bengaluru",    "urgency": 78, "needs": ["Clothes", "Food", "Toys"],                  "open": True},
    {"id": 3,  "name": "Goonj Donation Hub",   "category": "Clothes",     "location": "HSR Layout, Bengaluru",     "urgency": 85, "needs": ["Clothes", "Utensils", "Books"],              "open": True},
    {"id": 4,  "name": "Book Bridge NGO",       "category": "Books",       "location": "Whitefield, Bengaluru",     "urgency": 96, "needs": ["Books", "Stationery", "Uniforms"],           "open": True},
    {"id": 5,  "name": "EduReach India",        "category": "Books",       "location": "Marathahalli, Bengaluru",   "urgency": 71, "needs": ["Books", "Tablets", "Bags"],                  "open": True},
    {"id": 6,  "name": "Read & Rise",           "category": "Books",       "location": "Yelahanka, Bengaluru",      "urgency": 60, "needs": ["Books", "Pencils", "Notebooks"],             "open": False},
    {"id": 7,  "name": "TechForAll India",      "category": "Electronics", "location": "Electronic City, Bengaluru","urgency": 88, "needs": ["Laptops", "Phones", "Chargers"],            "open": True},
    {"id": 8,  "name": "Digital Inclusion",     "category": "Electronics", "location": "Jayanagar, Bengaluru",      "urgency": 75, "needs": ["Tablets", "Keyboards", "Cables"],           "open": True},
    {"id": 9,  "name": "ConnectKids NGO",       "category": "Electronics", "location": "JP Nagar, Bengaluru",       "urgency": 65, "needs": ["Computers", "Headphones", "Mice"],          "open": True},
    {"id": 10, "name": "Shelter India",         "category": "Furniture",   "location": "Malleshwaram, Bengaluru",   "urgency": 82, "needs": ["Furniture", "Mats", "Curtains"],             "open": True},
    {"id": 11, "name": "Smiles Foundation",     "category": "Toys",        "location": "Basavanagudi, Bengaluru",   "urgency": 89, "needs": ["Toys", "Games", "Clothes"],                  "open": True},
    {"id": 12, "name": "ChildJoy NGO",          "category": "Toys",        "location": "Vijayanagar, Bengaluru",    "urgency": 76, "needs": ["Toys", "Books", "Crayons"],                  "open": True},
]


def main():
    from ml.ngo_matcher import precompute_and_save, _has_sentence_transformers

    if not _has_sentence_transformers():
        logger.warning(
            "sentence-transformers not installed. "
            "Install with: pip install sentence-transformers\n"
            "Falling back to TF-IDF keyword encoding (less accurate)."
        )

    logger.info("Pre-computing embeddings for %d NGOs …", len(NGO_LIST))
    path = precompute_and_save(NGO_LIST)
    logger.info("Done! Saved → %s", path)
    logger.info("NGO embeddings will be loaded automatically on server start.")


if __name__ == "__main__":
    main()
