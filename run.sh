#!/bin/bash
# Quick start script for Unix/Mac/Linux

echo "Starting EA Global Meeting Matcher..."
echo ""

# Check if secrets.toml exists
if [ ! -f ".streamlit/secrets.toml" ]; then
    echo "[ERROR] .streamlit/secrets.toml not found"
    echo ""
    echo "Please copy the template and configure:"
    echo "  cp .streamlit/secrets.toml.example .streamlit/secrets.toml"
    echo ""
    echo "Then edit .streamlit/secrets.toml and add:"
    echo "  - GEMINI_API_KEY"
    echo "  - CSV_URL (Google Sheets URL)"
    echo "  - APP_PASSWORD"
    echo ""
    exit 1
fi

echo "✓ Configuration found"
echo ""
echo "Starting Streamlit..."
echo "App will download data from Google Sheets on first load"
echo ""
streamlit run app.py
