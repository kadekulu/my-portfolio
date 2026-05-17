@echo off
cd /d "%~dp0"
echo ========================================
echo   Starting Tag Editor Server...
echo   Browser will open automatically.
echo   * DO NOT close this window while editing *
echo ========================================
timeout /t 2 /nobreak >nul
start "" "http://localhost:5000"
python tag_editor.py
