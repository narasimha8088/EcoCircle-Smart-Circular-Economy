# 🚀 How to Run — EcoCircle

## ✅ Quick Start (Windows)
Double-click `start.bat` (or run `.\start.bat` from terminal)

## ✅ Quick Start (Mac / Linux)
```bash
chmod +x start.sh
./start.sh
```

---

## 🔧 Manual Setup

### Running the Platform
Since the Flask backend serves the frontend statically and handles WebSocket connections, you only need to run **one** server!

```bash
cd backend
python -m venv venv

# Mac/Linux:
source venv/bin/activate

# Windows:
venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env        # ← EDIT THIS FILE with your API keys
python app.py
```
App runs at: **http://localhost:5000/**
Test API Health: http://localhost:5000/api/health

---

## 🌍 What happens when you start it

1. Run `python app.py` (inside `backend`). The terminal prints a clickable link, e.g. `http://localhost:5000/`.
2. **Ctrl+Click** the link (your browser also opens automatically). The **3D globe landing page** appears first.
3. Click **Get Started** → the login screen → then the dashboard.

## 🤖 Making the AI Analyzer work (3 checks)

1. Put your Gemini key in **`backend/.env`** (not `.env.example`): `GEMINI_API_KEY=...` and `GEMINI_MODEL=gemini-3.8-flash`. **Save the file (Ctrl+S)**, then restart the server — the key is read only at start-up.
2. `pip install google-genai` (already in `requirements.txt`).
3. Run `python check_gemini.py` in `backend`. It tests your network, key, model and an image request, and says exactly what is wrong.

At start-up the terminal also prints `[OK] Gemini key loaded…` and `[OK] Gemini self-check passed…` (or a `[WARN]` with the reason).

You can analyze with a **description only, photos/videos only, or both**. The page shows exactly what it received.

---

## 🔑 API Keys & Configuration

### Open `backend/.env` and configure:

| Key | Where to Get | Required? | Purpose |
|-----|-------------|-----------|---------|
| `SECRET_KEY` | Any random string | ✅ Yes | Flask session & JWT token encryption |
| `GEMINI_API_KEY` | https://aistudio.google.com/app/apikey | Recommended | Phase 4 Multimodal Vision & Synthesis |
| `GEMINI_MODEL` | Default: `gemini-2.5-flash` | Optional | Specifies Gemini model version |
| `LOCATIONIQ_API_KEY` | https://locationiq.com/register | Optional | Geocoding & nearby facility search |
| `CARBON_API_KEY` | https://www.carboninterface.com/users/sign_up | Optional | External carbon data |

> 🗺️ **Maps Note:** The frontend map uses **Leaflet.js + OpenStreetMap** tiles. No Google Maps API key or setup is required!

---

## 📁 Complete Project Structure
```
smart-circular-economy/
│
├── 📄 README.md
├── 📄 HOW-TO-RUN.md         ← You are here
├── 🖥️  start.sh              ← Mac/Linux quick start
├── 🖥️  start.bat             ← Windows quick start
│
├── 🐍 backend/
│   ├── app.py               ← Flask entry point & WebSocket engine
│   ├── requirements.txt     ← pip install -r requirements.txt
│   ├── .env.example         ← Copy to .env and add API keys
│   ├── audit_all_phases.py  ← Phase 1-4 audit script
│   ├── instance/
│   │   └── circular_economy.db ← SQLite database
│   ├── ml/                  ← 4-Phase Machine Learning Pipeline
│   │   ├── clip_classifier.py     ← M1 CLIP category classifier
│   │   ├── yolo_damage_detector.py← M2 YOLOv8 damage detector
│   │   ├── ocr_reader.py          ← M3 EasyOCR text extractor
│   │   ├── material_classifier.py ← M4 CLIP material classifier
│   │   ├── carbon_estimator.py    ← M5 Carbon footprint model
│   │   ├── resale_model.py        ← M6 Resale price model (XGBoost)
│   │   ├── eco_trend_model.py     ← M7 Eco-score predictor (XGBoost)
│   │   ├── ngo_matcher.py         ← M8 Sentence-BERT semantic matcher
│   │   ├── pipeline.py            ← Concurrency & orchestration
│   │   └── artifacts/             ← Trained model weights (.pkl)
│   ├── models/
│   │   ├── user_model.py    ← User, streaks, face descriptor & auth
│   │   ├── product_model.py ← Product lifecycle tracking
│   │   ├── listing_model.py ← Marketplace listings
│   │   ├── repair_model.py  ← Repair centres
│   │   ├── recycling_model.py ← Recycling centres
│   │   ├── ngo_model.py     ← NGO profiles & needs boards
│   │   └── eco_model.py     ← Eco-points & audit actions
│   └── routes/
│       ├── auth_routes.py   ← /api/auth (login, register, face auth)
│       ├── product_routes.py← /api/products (CRUD)
│       ├── marketplace_routes.py ← /api/marketplace
│       ├── repair_routes.py ← /api/repair
│       ├── recycling_routes.py   ← /api/recycling
│       ├── ai_routes.py     ← /api/ai (vision-analyze, recommend, synthesize)
│       ├── donate_routes.py ← /api/donate (donations & matching)
│       ├── ngo_routes.py    ← /api/ngo (NGO dashboard portal)
│       ├── dashboard_routes.py   ← /api/dashboard
│       └── admin_routes.py  ← /api/admin
│
└── 🌐 frontend/
    ├── css/
    │   └── style.css        ← Design system & animations
    ├── js/
    │   ├── config.js        ← Global location & API URL config
    │   ├── api.js           ← API client, auth & toast utilities
    │   └── nav.js           ← Instant SPA fetch router
    └── pages/
        ├── index.html       ← Interactive 3D landing page
        ├── login.html       ← Login & Registration (with face unlock)
        ├── dashboard.html   ← User dashboard & metrics
        ├── products.html    ← Digital product inventory
        ├── marketplace.html ← Secondhand circular marketplace
        ├── donate.html      ← Smart donation & NGO matching
        ├── map.html         ← Interactive Leaflet eco-map
        ├── repair.html      ← Repair shops & cost estimator
        ├── recycling.html   ← Recycling centers & classification
        ├── ai-engine.html   ← AI vision analysis & intelligence
        ├── profile.html     ← Profile & face authentication setup
        ├── ngo_dashboard.html ← NGO administration portal
        └── admin.html       ← Platform admin panel
```

---

## 🌐 Key API Endpoints

### Auth
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/register` | Register new user |
| POST | `/api/auth/login` | Login with email or user ID |
| POST | `/api/auth/face/match` | 128-float face descriptor biometric login |
| GET  | `/api/auth/profile` | Get current user profile |

### AI Engine (4-Phase ML)
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/ai/vision-analyze` | Multimodal product photo/video analysis |
| POST | `/api/ai/synthesize` | Text-only Gemini 3.8 Flash eco synthesis |
| POST | `/api/ai/recommend` | Sustainability recommendation |
| POST | `/api/ai/carbon` | Carbon footprint calculation (M5) |
| POST | `/api/ai/price-predict` | Resale valuation calculation (M6) |
| GET  | `/api/ai/models/health` | Phase 1 model status (CLIP, YOLO, OCR) |
| GET  | `/api/ai/phase2/health` | Phase 2 model & artifact status |
| GET  | `/api/ai/phase3/health` | Phase 3 Sentence-BERT NGO matcher status |

### Donations & NGOs
| Method | Endpoint | Description |
|---|---|---|
| GET  | `/api/donate/ngos` | List verified NGOs |
| GET  | `/api/donate/ngos/match` | Semantic search NGOs by item description |
| POST | `/api/donate/classify` | Semantic item donation classifier |
| POST | `/api/donate/request` | Submit donation with real-time WebSocket broadcast |
| GET  | `/api/ngo/dashboard` | NGO portal dashboard |
