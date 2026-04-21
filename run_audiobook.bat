@echo off
title Arabic Audiobook Converter - PDF to Voice
echo ====================================================
echo    Arabic Audiobook Converter is Starting...
echo ====================================================
echo.
echo [1/2] Checking and Installing requirements...
echo This may take a moment on the first run...
uv pip install -r requirements.txt --python 3.11

echo.
echo [2/2] Starting server...
echo.
uv run --python 3.11 python app.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to start the server. 
    echo Please check the error_log.txt for details.
    pause
)
pause
