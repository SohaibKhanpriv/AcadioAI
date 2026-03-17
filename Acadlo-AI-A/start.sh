#!/bin/bash
# Quick start script for Acadlo AI Core

echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║              Acadlo AI Core - Quick Start                         ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.11 or higher."
    exit 1
fi

# Check if requirements are installed
if ! python3 -c "import fastapi" &> /dev/null; then
    echo "📦 Installing dependencies..."
    pip install -r requirements.txt
fi

# Check if .env exists
if [ ! -f .env ]; then
    echo "📝 Creating .env file from .env.example..."
    cp .env.example .env
fi

echo ""
echo "🚀 Starting Acadlo AI Core..."
echo "📝 API docs will be available at: http://localhost:8000/docs"
echo "🏥 Health check at: http://localhost:8000/health"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Start the server
python3 -m app.main

