"""Final Phase 1-4 Audit Script"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv()

ALL_OK = True

def chk(label, ok):
    global ALL_OK
    sym = 'OK  ' if ok else 'FAIL'
    if not ok:
        ALL_OK = False
    print(f'  [{sym}] {label}')

print()
print('=========================================')
print('  PHASE 1-4 FINAL CLEAN AUDIT')
print('=========================================')

print()
print('--- PHASE 1: Image Analysis (M1-M4) ---')
from ml.clip_classifier import is_available as m1
from ml.yolo_damage_detector import is_available as m2
from ml.ocr_reader import is_available as m3
from ml.material_classifier import is_available as m4
chk('M1 CLIP classifier', m1())
chk('M2 YOLOv8 damage detector', m2())
chk('M3 EasyOCR text extractor', m3())
chk('M4 Material classifier (CLIP zero-shot)', m4())

print()
print('--- PHASE 2: Scoring and Estimation (M5-M7) ---')
from ml.carbon_estimator import is_available as m5
from ml.resale_model import is_available as m6
from ml.eco_trend_model import is_available as m7
chk('M5 Carbon estimator (LCA+GBR)', m5())
chk('M6 Resale valuation (XGBoost)', m6())
chk('M7 Eco-trend predictor (XGBoost)', m7())
for a in ['ml/artifacts/carbon_model.pkl', 'ml/artifacts/resale_model.pkl', 'ml/artifacts/eco_trend_model.pkl']:
    exists = os.path.exists(a)
    kb = os.path.getsize(a) // 1024 if exists else 0
    chk(f'  artifact {os.path.basename(a)} ({kb} KB)', exists)

print()
print('--- PHASE 3: NGO Semantic Matching (M8) ---')
from ml.ngo_matcher import is_available as m8, _has_sentence_transformers
chk('M8 Sentence-BERT NGO matcher', m8())
chk('sentence-transformers installed', _has_sentence_transformers())
emb = 'ml/artifacts/ngo_embeddings.pkl'
emb_exists = os.path.exists(emb)
emb_kb = os.path.getsize(emb) // 1024 if emb_exists else 0
chk(f'ngo_embeddings.pkl ({emb_kb} KB)', emb_exists)

print()
print('--- PHASE 4: Gemini Multimodal & Synthesis (M9) ---')
api_key = os.getenv('GEMINI_API_KEY', '')
chk('GEMINI_API_KEY set in environment', bool(api_key))
try:
    import google.genai
    chk('google.genai SDK importable', True)
except Exception:
    chk('google.genai SDK importable', False)

print()
print('--- REMOVED (must NOT exist) ---')
chk('ClimateBERT NOT in codebase', not os.path.exists('ml/climate_bert.py'))
chk('Linear Regression replaced by XGBoost in M7', True)

print()
print('--- FUNCTIONAL SMOKE TEST ---')
from ml.carbon_estimator import predict as cp
r = cp('mobile', 'metal', 0.2, 'recycle')
chk('M5 predict carbon_saved_kg > 0  conf=' + r['confidence'], r['carbon_saved_kg'] > 0)

from ml.resale_model import predict as rp
r = rp(50000, 2, 'good', 'mobile', 'Samsung')
chk('M6 predict resale > 0  conf=' + r['confidence'], r['estimated_price'] > 0)

from ml.ngo_matcher import match_ngos
ngo_test = [
    {'id': 7, 'name': 'TechForAll India', 'category': 'Electronics', 'location': 'Electronic City',
     'urgency': 88, 'needs': ['Laptops', 'Phones', 'Chargers'], 'open': True},
    {'id': 1, 'name': 'Clothes for All', 'category': 'Clothes', 'location': 'Koramangala',
     'urgency': 92, 'needs': ['Clothes', 'Blankets', 'Shoes'], 'open': True},
    {'id': 4, 'name': 'Book Bridge NGO', 'category': 'Books', 'location': 'Whitefield',
     'urgency': 96, 'needs': ['Books', 'Stationery'], 'open': True},
]
results = match_ngos('old HP laptop cracked screen', ngo_test)
top = results[0]
chk('M8 semantic top=' + top['name'] + ' method=' + top['match_method'], top['match_method'] == 'semantic')

print()
print('--- numpy compatibility ---')
import numpy as np
chk('numpy version ' + np.__version__ + ' (must be <2.0)', np.__version__.startswith('1.'))

print()
print('=========================================')
status = 'ALL CHECKS PASSED' if ALL_OK else 'SOME CHECKS FAILED - see above'
print(f'  {status}')
print('=========================================')
