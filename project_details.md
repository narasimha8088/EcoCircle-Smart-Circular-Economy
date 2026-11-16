# Smart Circular Economy Platform (EcoCircle)

## 1. Project Overview
**EcoCircle** is a full-stack, AI-driven Smart Circular Economy platform designed to promote sustainability, resource efficiency, and environmentally conscious consumption. The platform empowers users to buy, sell, repair, reuse, and recycle products intelligently. By leveraging an embedded AI Engine, the system provides actionable sustainability intelligence, such as material scoring, hydrological impact, and carbon footprint analysis for various products.

The primary goal of the project is to shift consumer behavior from a linear "take-make-dispose" model to a circular model by making sustainable actions (repairing, recycling, donating) highly accessible, rewarding, and data-driven.

---

## 2. Technical Stack
The platform is built using a modern, scalable, and lightweight tech stack:

### Frontend
* **Core:** HTML5, Vanilla JavaScript, CSS3
* **Styling & UI:** Tailwind CSS (via CDN) for responsive, atomic design
* **Icons & Typography:** Google Material Symbols, Manrope font family
* **Architecture:** Component-based UI logic utilizing modular JS (`config.js`, `api.js`, `socket.js`)
* **Real-Time Client:** Socket.IO client-side library (`socket.io.min.js`)

### Backend
* **Framework:** Python + Flask (RESTful API architecture)
* **Real-time Engine:** Flask-SocketIO (WebSocket integration for live events, notifications, and active user tracking)
* **Database:** SQLite with SQLAlchemy ORM (lightweight, portable relational database)
* **Authentication:** Flask-JWT-Extended for secure, token-based user sessions
* **Concurrency:** `eventlet` for asynchronous WebSocket support

### AI Engine & External Integrations
* **AI Vision Core:** Google Gemini 3.8 Flash API (for Multi-Modal image, video, and text analysis)
* **ML Intelligence Core:** 4-Phase pipeline (CLIP, YOLOv8, EasyOCR, XGBoost resale pricing, LCA carbon estimation, Sentence-BERT NGO matching)
* **Geospatial Data:** Leaflet.js + OpenStreetMap (Frontend) & LocationIQ API (Backend nearby facility search)
* **Environmental Data:** Carbon Interface API (used for fetching real-time carbon footprint data)

---

## 3. Architecture and Application Flow

The application follows a decoupled client-server architecture:

1. **Client Layer (Frontend):** 
   Static HTML/JS files served via a lightweight HTTP server or directly from Flask. The frontend makes asynchronous `fetch` requests to the Flask REST API and maintains a persistent WebSocket connection for real-time data.
2. **API Layer (Flask Backend):**
   Handles routing, business logic, user authentication (JWT generation/validation), and interfaces with external APIs.
3. **Data Layer (SQLite):**
   Stores user profiles, product inventories, transaction histories, NGO data, and cached AI analysis results across several relational tables.
4. **AI/Processing Layer:**
   When media is uploaded, the Flask backend routes the data to the `ai_routes` module, which processes the inputs via Google Gemini API (or the fallback recommender script), generates sustainability scores, and returns a JSON payload to the frontend for visualization.
5. **Real-Time Layer:**
   The `socket_events.py` module manages WebSocket rooms and broadcasts events (like new donations, active user counts) using `eventlet`.

---

## 4. Core Features & How They Work (Deep Dive)

### 4.1. Smart Product Analyzer (AI Engine)
**What it does:** Acts as the "brain" of the platform, assessing the environmental impact of physical goods using advanced AI Vision.
**How it works:**
* **Multi-Modal Input Options:** Users upload product media (images/videos) and enter text descriptions about an item they own or plan to buy.
* **Processing:** The Python backend securely processes the media through the Phase 1 & 2 ML models and Google Gemini 3.8 Flash (`/vision-analyze` endpoint) along with a strict system prompt.
* **Output & Insights:**
  * **Condition Assessment:** The AI visually inspects the item for wear and tear.
  * **Material Scoring:** Evaluates the composition (e.g., recycled plastic vs. virgin materials).
  * **Carbon & Hydrological Impact:** Estimates the water footprint and logistics emissions.
  * **Estimated Value:** AI calculates market resale value in INR based on condition.
  * **Overall Sustainability Score:** An aggregate score out of 100.
* **Actionable Recommendations:** Based on the score and condition, the AI suggests the most sustainable next step: **Repair**, **Resell**, **Recycle**, **Donate**, or **Keep Using**. It also provides specific repair tips and facility recommendations.

### 4.2. Eco-Manager Dashboard & Gamification
**What it does:** A central hub giving users a personalized overview of their environmental impact and platform activity.
**How it works:**
* **Impact Metrics:** Aggregates data from user actions to display lifetime environmental savings, such as "Total Items Saved from Landfill", "Carbon Offset (kg CO2)", and "Water Conserved (Liters)".
* **Gamification & Badges:** Based on their `eco_score` points, users achieve ranks such as "Newcomer 🌰", "Eco Starter 🌱", "Earth Saver 🌍", "Green Hero 🌿", or "Eco Champion 🏆".
* **Leaderboards:** The backend dynamically calculates the top 10 most sustainable users on the platform to encourage friendly competition.
* **Live Activity Feed:** Uses WebSockets to stream real-time community actions to the dashboard.

### 4.3. Inventory Management (My Items)
**What it does:** Allows users to digitize their physical belongings to keep track of their lifecycle.
**How it works:**
* Users can add items to their digital inventory by inputting details (category, brand, age, condition, weight).
* Items are stored in the SQLite `Product` table linked to their User ID.
* Items from the inventory can be easily pushed to the AI Engine for analysis, or listed directly on the Marketplace or Donation page. The system tracks the lifecycle stage (In Use, Repaired, Sold, Donated).

### 4.4. Interactive Eco-Map
**What it does:** Bridges the digital platform with the physical world by showing nearby sustainability resources.
**How it works:**
* Integrates seamlessly with the **Google Maps JavaScript API**.
* When the AI Engine recommends a specific action (like "Recycle" or "Repair"), the map dynamically filters and plots relevant local facilities.
* Backend models (`RepairCenter`, `RecyclingCenter`) store coordinates (latitude, longitude) of verified local centers, which the frontend fetches and plots as interactive markers.

### 4.5. Smart Donation & NGO Integrations
**What it does:** Encourages community-driven sustainability by connecting users with NGOs.
**How it works:**
* **Rule-Based Classification:** When users describe an item to donate, the `/classify` API categorizes the item (e.g., Clothes, Electronics, Books) and returns a matching score and suggested NGOs.
* **Real-Time Socket Events:** When a donation is submitted, the user earns Eco Points, and a WebSocket event is fired. All users currently on the "Donate" page instantly see a live notification (e.g., "🎉 Alex just donated Clothes items to Goonj Donation Hub!").
* **NGO Urgency Index:** NGOs can broadcast real-time urgency updates if they are critically low on specific supplies, shifting donor priorities dynamically.

### 4.6. Peer-to-Peer Marketplace
**What it does:** A dedicated storefront for extending product lifecycles through secondhand commerce.
**How it works:**
* Users can buy and sell used, refurbished, or upcycled goods by creating a `Listing` linked to their `Product`.
* Promotes circular commerce rather than buying new, directly reducing manufacturing demand and waste.
* The system estimates depreciation and suggests fair pricing using the `recommender.py` logic.

---

## 5. Database Schema & Models

The SQLite database employs several core SQLAlchemy models:
* **User (`user_model.py`):** Stores credentials, location, `eco_score`, gamification badges, and relationships to products/listings.
* **Product (`product_model.py`):** Represents physical items owned by users. Tracks age, condition, purchase price, category, and current `lifecycle_stage`.
* **Listing (`listing_model.py`):** Represents active items for sale or trade on the marketplace, linked to a Product.
* **EcoScore (`eco_model.py`):** An audit log of all sustainable actions taken by a user (e.g., donated, recycled, repaired), tracking date and points awarded.
* **RepairCenter / RecyclingCenter (`repair_model.py` / `recycling_model.py`):** Geolocation data for physical facilities plotted on the Eco-Map.

---

## 6. API Route Structure

* `/api/auth` - User registration, login, JWT generation, and profile management.
* `/api/ai` - AI Vision analysis (`/vision-analyze`), carbon footprint calculations, and automated pricing predictions.
* `/api/dashboard` - Aggregated user statistics, carbon saved, leaderboard data, and recent actions.
* `/api/donate` - NGO listings, item classification, donation processing, and live stats.
* `/api/products` - CRUD operations for user inventories.
* `/api/marketplace` - Buying and selling logic.
* `/api/repair` & `/api/recycling` - Fetching local facilities and booking services.

---

## 7. Potential Use Cases & Value Proposition
* **Consumer Empowerment:** Provides everyday users with enterprise-grade sustainability data about the objects they own.
* **Corporate ESG:** Can be white-labeled for corporations to track the lifecycle and end-of-life management of office assets.
* **Community Building:** Connects local users, repair shops, and recycling facilities into a cohesive, localized circular economy loop.

This architecture ensures the platform is highly interactive, easily extensible, and heavily relies on real-time feedback loops to modify user behavior towards a greener, circular economy.
