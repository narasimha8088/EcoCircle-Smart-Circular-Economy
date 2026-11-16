# 🌱 Smart Circular Economy Platform (EcoCircle)

Full-stack, AI-driven circular economy platform to buy, sell, repair, reuse, donate & recycle products with multi-phase sustainability intelligence.

## ⚡ Tech Stack
- **Frontend**: HTML5, Vanilla JavaScript (SPA Fetch Router), Tailwind CSS
- **Maps**: Leaflet.js + OpenStreetMap (100% Free, no frontend API key needed!)
- **Backend**: Python 3.11+, Flask (RESTful API), Flask-SocketIO (WebSockets with `eventlet`)
- **Database**: SQLite with SQLAlchemy ORM (`backend/instance/circular_economy.db`)
- **AI & ML Engine (4-Phase Architecture)**:
  - **Phase 1 (Vision Detection)**: CLIP (Category & Material Classifier), YOLOv8 (Damage Detector), EasyOCR (Brand/Model Reader)
  - **Phase 2 (Scoring & Valuation)**: LCA Carbon Estimator + GBR (M5), XGBoost Resale Pricing (M6), XGBoost Eco-Trend Predictor (M7)
  - **Phase 3 (Semantic Matching)**: Sentence-BERT (M8 semantic NGO donation matcher)
  - **Phase 4 (Synthesis)**: Google Gemini 3.8 Flash Multimodal API

---

## 📁 Project Structure
```
smart-circular-economy/
├── frontend/
│   ├── pages/          → All HTML pages (dashboard, ai-engine, map, donate, marketplace, repair, recycling, profile, admin)
│   ├── css/            → Design system & stylesheets
│   ├── js/             → Modular JS (api.js, config.js, nav.js)
│   └── assets/         → Landing page React build & assets
├── backend/
│   ├── app.py          → Flask entry point & WebSocket engine
│   ├── routes/         → RESTful API routes (ai, auth, donate, ngo, marketplace, repair, recycling, etc.)
│   ├── models/         → SQLAlchemy database models (user, product, listing, ngo, repair, recycling, eco)
│   ├── ml/             → 4-Phase ML pipeline, models & trained artifacts
│   ├── instance/       → circular_economy.db (active SQLite DB)
│   ├── audit_all_phases.py → Phase 1-4 audit & health check script
│   └── .env.example    → Environment variable template
├── start.bat           → Quick start for Windows
├── start.sh            → Quick start for Linux / macOS
└── README.md
```

---

## 🔑 Environment Configuration (`backend/.env`)

Copy `backend/.env.example` to `backend/.env` and configure:

```ini
# Required: Flask session & JWT secret
SECRET_KEY=any_random_secret_string_here

# Google Gemini API Key (for Phase 4 AI Vision Analysis & Synthesis)
# Free at: https://aistudio.google.com/app/apikey
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.8-flash

# Optional: LocationIQ API Key (for backend geocoding / nearby facility lookup)
# Free at: https://locationiq.com/register
LOCATIONIQ_API_KEY=your_locationiq_api_key_here

# Optional: Carbon Interface API Key (for real-time emissions data)
# Free at: https://www.carboninterface.com/users/sign_up
CARBON_API_KEY=your_carbon_api_key_here
```

> **Note on Maps:** The frontend interactive map uses Leaflet.js and OpenStreetMap tiles. **No Google Maps API key is required!**

---

## 🚀 How to Run

### Quick Start (Windows)
Double-click `start.bat` (or run `./start.bat` from terminal).

### Quick Start (Linux / macOS)
```bash
chmod +x start.sh
./start.sh
```

### Manual Run
```bash
cd backend
python -m venv venv

# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
python app.py
```

Open your browser at: **http://localhost:5000/**

---

## 🧪 Testing the ML Pipeline
To verify all 4 phases of the AI/ML pipeline:
```bash
cd backend
python audit_all_phases.py
```
This tests CLIP, YOLOv8, EasyOCR, Material Classifier, Carbon LCA model, XGBoost resale valuation, Sentence-BERT NGO matcher, and Gemini 3.8 Flash synthesis.
