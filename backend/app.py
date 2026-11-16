import os as _os

# Real OS threads by default. eventlet's monkey-patching of Python's SSL layer caused
# "RecursionError: maximum recursion depth exceeded" inside the Gemini (google-genai) HTTPS calls.
# To go back to eventlet:  set SOCKETIO_ASYNC_MODE=eventlet in the OS environment (not .env).
ASYNC_MODE = _os.environ.get("SOCKETIO_ASYNC_MODE", "threading").strip().lower()
if ASYNC_MODE == "eventlet":
    import eventlet
    eventlet.monkey_patch()  # must run before anything else is imported

import os
import sys

# Ensure backend root is always on the path so `ml.*` imports work
_backend_dir = os.path.dirname(os.path.abspath(__file__))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from extensions import db, jwt, socketio

# Fix Unicode output on Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Always read backend/.env (next to this file), whatever folder the server was started from.
# override=True so a stale/empty GEMINI_API_KEY left in the Windows environment can't hide the file's value.
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(ENV_PATH, override=True)


def _check_ssl_patching():
    """Gemini's HTTPS calls die with 'RecursionError: maximum recursion depth exceeded' when eventlet/gevent
    has monkey-patched ssl. Say so at start-up instead of failing later inside an analysis."""
    import ssl as _ssl
    mod = (getattr(_ssl.SSLContext, "__module__", "") or "")
    if "eventlet" in mod or "gevent" in mod or ASYNC_MODE == "eventlet":
        print("[WARN] eventlet/gevent has patched Python's SSL layer. Gemini calls will fail with "
              "'RecursionError'. Unset SOCKETIO_ASYNC_MODE (Windows: `set SOCKETIO_ASYNC_MODE=` ) and restart "
              "so the server runs in the default threading mode.")
    else:
        print("[OK] Server running in threading mode (SSL not patched).")


def _report_env_status():
    """Print, at start-up, exactly what the app found — so a missing key is obvious in the terminal."""
    key = (os.getenv("GEMINI_API_KEY") or "").strip().strip("\"'")
    if not os.path.exists(ENV_PATH):
        print(f"[WARN] {ENV_PATH} not found. Copy .env.example to .env and add your keys.")
    elif not key or key == "your_gemini_api_key_here":
        print(f"[WARN] GEMINI_API_KEY is empty in {ENV_PATH}. Add it, SAVE the file (Ctrl+S), and restart.")
    else:
        print(f"[OK] Gemini key loaded from .env ({len(key)} chars, ends ...{key[-4:]}) | model: {os.getenv('GEMINI_MODEL') or 'gemini-3.8-flash'}")


def create_app():
    # Resolve the frontend directory (one level up from backend/)
    FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

    app = Flask(__name__, static_folder=None)

    # ── Config ────────────────────────────────────────────
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-me")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///circular_economy.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["JWT_SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-me")

    # ── Extensions ─────────────────────────────────────────
    CORS(app, origins=["*"])
    db.init_app(app)
    jwt.init_app(app)

    # Initialize SocketIO (threading mode by default) with CORS open for localhost
    socketio.init_app(
        app,
        cors_allowed_origins="*",
        async_mode=ASYNC_MODE,
        logger=False,
        engineio_logger=False,
    )

    # ── Register HTTP Blueprints ───────────────────────────
    from routes.auth_routes import auth_bp
    from routes.product_routes import product_bp
    from routes.marketplace_routes import market_bp
    from routes.repair_routes import repair_bp
    from routes.recycling_routes import recycle_bp
    from routes.ai_routes import ai_bp
    from routes.dashboard_routes import dashboard_bp
    from routes.admin_routes import admin_bp
    from routes.donate_routes import donate_bp
    from routes.ngo_routes import ngo_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(product_bp, url_prefix="/api/products")
    app.register_blueprint(market_bp, url_prefix="/api/marketplace")
    app.register_blueprint(repair_bp, url_prefix="/api/repair")
    app.register_blueprint(recycle_bp, url_prefix="/api/recycling")
    app.register_blueprint(ai_bp, url_prefix="/api/ai")
    app.register_blueprint(dashboard_bp, url_prefix="/api/dashboard")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(donate_bp, url_prefix="/api/donate")
    app.register_blueprint(ngo_bp,    url_prefix="/api/ngo")

    # ── Register WebSocket Event Handlers ─────────────────
    import socket_events  # noqa: F401 - side-effect import registers @socketio.on handlers

    # ── Create Tables + Seed — all inside app context ──────
    with app.app_context():
        from models.user_model import User  # noqa: F401
        from models.product_model import Product, ProductEvent  # noqa: F401
        from models.donation_model import DonationRecord  # noqa: F401
        from models.listing_model import Listing  # noqa: F401
        from models.repair_model import RepairCenter  # noqa: F401
        from models.recycling_model import RecyclingCenter  # noqa: F401
        from models.ngo_model import NGOProfile, NeedsBoardEntry, PledgeRecord  # noqa: F401
        from models.eco_model import EcoAction  # noqa: F401
        from models.pilot_model import PilotTelemetry, seed_pilot_data_if_empty  # noqa: F401

        db.create_all()

        from sqlalchemy import text
        import random
        import string
        
        # ── Auto-migrate: add new columns if they don't exist ──
        with db.engine.connect() as _conn:
            for _col, _type in [
                ("face_descriptor",  "TEXT"),    # Camera face recognition
                ("user_number",      "TEXT"),    # ECO-XXXX identifier
                ("eco_score",        "INTEGER DEFAULT 0"),  # Gamification score
                ("login_streak",     "INTEGER DEFAULT 0"),  # Consecutive login days
                ("last_streak_date", "DATE"),    # Date of last streak update
            ]:
                try:
                    _conn.execute(text(f"ALTER TABLE users ADD COLUMN {_col} {_type}"))
                    print(f"[Migration] Added column: {_col}")
                except Exception:
                    pass  # Column already exists — that's fine
            _conn.commit()

        # ── Auto-migrate: AI-scan tracking columns on products (v3) ──
        with db.engine.connect() as _conn:
            for _col, _type in [
                ("source",            "VARCHAR(30) DEFAULT 'manual'"),
                ("ai_recommendation", "VARCHAR(30)"),
                ("ai_score",          "INTEGER"),
                ("ai_analysis",       "TEXT"),
                ("analysis_ref",      "VARCHAR(64)"),
                ("updated_at",        "DATETIME"),
                ("image",             "VARCHAR(255)"),
            ]:
                try:
                    _conn.execute(text(f"ALTER TABLE products ADD COLUMN {_col} {_type}"))
                    print(f"[Migration] Added products.{_col}")
                except Exception:
                    pass  # Column already exists — that's fine
            _conn.commit()

        # ── Auto-migrate: image column on listings ────────────────
        with db.engine.connect() as _conn:
            try:
                _conn.execute(text("ALTER TABLE listings ADD COLUMN image VARCHAR(255)"))
                print("[Migration] Added listings.image")
            except Exception:
                pass  # Already exists
            _conn.commit()

        # Backfill user_number for existing users
        users = User.query.filter_by(user_number=None).all()
        for u in users:
            while True:
                rand_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                new_num = f"ECO-{rand_str}"
                # Ensure uniqueness
                if not User.query.filter_by(user_number=new_num).first():
                    u.user_number = new_num
                    break
        if users:
            db.session.commit()
            print(f"[Migration] Backfilled user_number for {len(users)} users.")


        # Seed repair centres
        if RepairCenter.query.count() == 0:
            db.session.add_all([
                RepairCenter(name="QuickFix Electronics", location="Bengaluru, KA",
                             service_type="Electronics", rating=4.5,
                             lat=12.9716, lng=77.5946, contact="9876543210"),
                RepairCenter(name="MobileCare Hub", location="Mysuru, KA",
                             service_type="Mobile & Laptop", rating=4.2,
                             lat=12.2958, lng=76.6394, contact="9845012345"),
                RepairCenter(name="HomeAppliance Fix", location="Mysuru, KA",
                             service_type="Appliances", rating=4.0,
                             lat=12.3052, lng=76.6553, contact="9900112233"),
            ])

        # Seed recycling centres
        if RecyclingCenter.query.count() == 0:
            db.session.add_all([
                RecyclingCenter(name="EcoRecycle Mysuru", location="Mysuru, KA",
                                accepted_materials="Electronics, Plastic, Metal",
                                lat=12.2958, lng=76.6394, contact="080-12345678"),
                RecyclingCenter(name="GreenWaste Hub", location="Bengaluru, KA",
                                accepted_materials="Paper, Glass, Plastic",
                                lat=12.9716, lng=77.5946, contact="080-87654321"),
            ])

        # Seed NGO profiles
        if NGOProfile.query.count() == 0:
            from werkzeug.security import generate_password_hash
            seed_ngos = [
                NGOProfile(
                    name="Clothes for All Foundation",
                    registration_no="NGO-KA-2019-001",
                    address="Koramangala, Bengaluru, Karnataka",
                    latitude=12.9352, longitude=77.6245,
                    category_tags=["Clothes", "Toys", "General"],
                    contact_phone="9876501234",
                    contact_email="clothesforall@eco.in",
                    verified=True,
                    password_hash=generate_password_hash("ngo123"),
                ),
                NGOProfile(
                    name="TechForAll India",
                    registration_no="NGO-KA-2020-007",
                    address="Electronic City, Bengaluru, Karnataka",
                    latitude=12.8399, longitude=77.6770,
                    category_tags=["Electronics", "Books"],
                    contact_phone="9856321470",
                    contact_email="techforall@eco.in",
                    verified=True,
                    password_hash=generate_password_hash("ngo123"),
                ),
                NGOProfile(
                    name="Book Bridge NGO",
                    registration_no="NGO-KA-2018-004",
                    address="Whitefield, Bengaluru, Karnataka",
                    latitude=12.9698, longitude=77.7499,
                    category_tags=["Books", "Electronics", "General"],
                    contact_phone="9741234567",
                    contact_email="bookbridge@eco.in",
                    verified=True,
                    password_hash=generate_password_hash("ngo123"),
                ),
                NGOProfile(
                    name="Shelter India",
                    registration_no="NGO-KA-2021-010",
                    address="Malleshwaram, Bengaluru, Karnataka",
                    latitude=13.0027, longitude=77.5714,
                    category_tags=["Furniture", "Clothes", "General"],
                    contact_phone="9988776655",
                    contact_email="shelterindia@eco.in",
                    verified=True,
                    password_hash=generate_password_hash("ngo123"),
                ),
                NGOProfile(
                    name="Smiles Foundation",
                    registration_no="NGO-KA-2022-011",
                    address="Basavanagudi, Bengaluru, Karnataka",
                    latitude=12.9416, longitude=77.5729,
                    category_tags=["Toys", "Clothes", "Books"],
                    contact_phone="9845671230",
                    contact_email="smiles@eco.in",
                    verified=True,
                    password_hash=generate_password_hash("ngo123"),
                ),
            ]
            db.session.add_all(seed_ngos)
            print(f"[Seed] Added {len(seed_ngos)} NGO profiles.")

        db.session.commit()
        seed_pilot_data_if_empty()
        print("[OK] Database ready.")

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok", "message": "EcoCircle API running 🌿"})

    # ── Serve Uploaded Product Images ──────────────────────────
    UPLOADS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads", "products")

    @app.route("/uploads/products/<path:filename>")
    def serve_product_image(filename):
        return send_from_directory(UPLOADS_DIR, filename)

    # ── Serve Frontend Static Files ────────────────────────────
    @app.route("/")
    def index():
        # The landing page is the 3D globe app (frontend/assets bundle); its "Get Started" button opens login.html
        return send_from_directory(os.path.join(FRONTEND_DIR, "pages"), "index.html")

    @app.route("/index.html")
    def index_html_redirect():
        # The globe app's router only knows "/", so send /index.html there instead of showing its 404 page
        from flask import redirect
        return redirect("/", code=302)

    @app.route("/<path:filename>")
    def frontend_pages(filename):
        # Try pages/ first, then root of frontend
        pages_dir = os.path.join(FRONTEND_DIR, "pages")
        if os.path.exists(os.path.join(pages_dir, filename)):
            return send_from_directory(pages_dir, filename)
        return send_from_directory(FRONTEND_DIR, filename)

    @app.after_request
    def _revalidate_frontend_files(resp):
        """
        Pages/JS/CSS: always revalidate with the server (ETag -> instant 304). Without this the
        browser may keep serving an OLD copy of a page or script for hours after an update.
        """
        from flask import request
        if request.method == "GET" and not request.path.startswith(("/api/", "/socket.io")):
            resp.headers.setdefault("Cache-Control", "no-cache")
        return resp

    # ── Global Error Handlers ──────────────────────────────
    from sqlalchemy.exc import IntegrityError

    @app.errorhandler(IntegrityError)
    def handle_integrity_error(e):
        """Catch unhandled DB constraint violations and return a clean 400."""
        db.session.rollback()
        return jsonify({"error": "Data integrity error. Check required fields."}), 400

    @app.errorhandler(500)
    def handle_server_error(e):
        """Return a clean JSON 500 instead of an HTML traceback page."""
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred."}), 500

    return app


def _local_network_ip():
    """Best-effort LAN address so the app can also be opened from a phone on the same Wi-Fi."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:
            sk.connect(("10.255.255.255", 1))   # no packet is actually sent
            return sk.getsockname()[0]
    except Exception:
        return None


def _announce(port):
    """Print a clickable link to the web app and (optionally) open it in the browser."""
    url = f"http://localhost:{port}/"
    lan = _local_network_ip()
    line = "=" * 62
    print("")
    print(line)
    print("  EcoCircle is running")
    print(line)
    print("")
    print("  Open the app (Ctrl+Click / Cmd+Click the link):")
    print("")
    print(f"      {url}")
    if lan and lan != "127.0.0.1":
        print(f"      http://{lan}:{port}/   (other devices on your Wi-Fi)")
    print("")
    print("  The globe landing page opens first. Click \"Get Started\" to reach the login screen.")
    print(f"  API health check: {url}api/health")
    print("  Press Ctrl+C to stop the server.")
    print(line)
    print("", flush=True)

    # Auto-open the browser once, a moment after the server starts. Disable with AUTO_OPEN_BROWSER=false
    if os.getenv("AUTO_OPEN_BROWSER", "true").strip().lower() not in ("0", "false", "no", "off"):
        import threading
        import webbrowser
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()


if __name__ == "__main__":
    app = create_app()
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "True").strip().lower() in ("1", "true", "yes", "on")

    # Flask's auto-reloader is OFF by default: it builds the whole app twice at start-up and then
    # keeps polling every imported file (thousands once torch/transformers load), which makes the
    # server sluggish. Turn it on only while editing Python code:  FLASK_RELOAD=true
    use_reloader = debug and os.getenv("FLASK_RELOAD", "False").strip().lower() in ("1", "true", "yes", "on")

    # With the reloader on, this file runs twice (watcher + server); only the server process announces.
    is_reloader_child = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    if (not use_reloader) or is_reloader_child:
        _report_env_status()
        _check_ssl_patching()
        _announce(port)
        try:
            from ml import warmup
            warmup.start_light()      # background: pre-load the scoring models so first use is fast
            try:                      # background: find which Gemini models this key can use (cached)
                from gemini_check import discover_models
                warmup._spawn(lambda: discover_models(os.getenv("GEMINI_API_KEY")))
            except Exception:
                pass
            if os.getenv("GEMINI_STARTUP_CHECK", "true").strip().lower() not in ("0", "false", "no", "off"):
                from gemini_check import startup_selfcheck
                warmup._spawn(lambda: startup_selfcheck(lambda m: print(m, flush=True)))
        except Exception as e:
            print(f"[Warmup] skipped: {e}")

    # Use socketio.run() instead of app.run() to enable WebSocket support
    socketio.run(app, debug=debug, use_reloader=use_reloader, port=port, host="0.0.0.0", allow_unsafe_werkzeug=True)
