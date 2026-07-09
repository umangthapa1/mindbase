#!/bin/bash

# Mindbase Startup Script
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "🚀 Mindbase - AI Workspace"
echo "=========================="
echo ""

# Check Ollama
echo "📡 Checking Ollama..."
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "✓ Ollama is running"
else
    echo "✗ Ollama is not running"
    echo "   Start Ollama with: ollama serve"
    echo "   Pull a model with: ollama pull mistral"
    exit 1
fi

# Activate virtual environment
if [ ! -d "venv" ]; then
    echo ""
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

# Install/update dependencies
if [ ! -f "venv/bin/uvicorn" ]; then
    echo "📥 Installing dependencies..."
    pip install -q -r backend/requirements.txt
fi

echo ""
echo "🎯 Starting Mindbase..."
echo "   Open browser: http://localhost:8000"
echo "   Press Ctrl+C to stop"
echo ""

cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
