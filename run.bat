@echo off
REM Quick start script for Windows

echo Starting EA Global Meeting Matcher...
echo.

REM Check if secrets.toml exists
if not exist ".streamlit\secrets.toml" (
    echo [ERROR] .streamlit\secrets.toml not found
    echo.
    echo Please copy the template and configure:
    echo   copy .streamlit\secrets.toml.example .streamlit\secrets.toml
    echo.
    echo Then edit .streamlit\secrets.toml and add:
    echo   - GEMINI_API_KEY
    echo   - CSV_URL (Google Sheets URL^)
    echo   - APP_PASSWORD
    echo.
    pause
    exit /b 1
)

echo [OK] Configuration found
echo.
echo Starting Streamlit...
echo App will download data from Google Sheets on first load
echo.
streamlit run app.py
