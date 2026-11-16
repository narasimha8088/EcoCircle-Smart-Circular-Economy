#!/bin/bash
# ─────────────────────────────────────────────────
# EcoCircle — Quick Start Script
# Run this from the project root directory
# ─────────────────────────────────────────────────

echo ""
echo "🌿 Smart Circular Economy Platform — Setup"
echo "==========================================="

# ── Backend ──────────────────────────────────────
echo ""
echo "📦 Setting up Backend..."
cd backend

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
  echo "   Creating virtual environment..."
  python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Install dependencies
echo "   Installing Python dependencies..."
pip install -r requirements.txt -q

# Create .env from example if missing
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo ""
  echo "⚠️  IMPORTANT: Edit backend/.env and add your API keys!"
  echo "   Then run this script again."
  echo ""
  echo "   Required keys:"
  echo "   - SECRET_KEY   (any random string)"
  echo "   - GEMINI_API_KEY (from https://aistudio.google.com/app/apikey) for the AI Analyzer"
  echo ""
fi

echo ""
echo "🚀 Starting EcoCircle Platform ..."
echo "   (The backend serves both the API and the web pages)"
echo "   A clickable link will appear below — Ctrl/Cmd+Click it to open the app."
echo "   Press Ctrl+C to stop."
echo ""
# Run in the foreground so the link banner is visible and Ctrl+C stops the server cleanly
exec python app.py
