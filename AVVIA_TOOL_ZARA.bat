@echo off
title Zara Logistics Tool - Monterotondo
cd /d "%~dp0"
echo ========================================================
echo   Avvio Zara Logistics Automation Platform (Background)
echo ========================================================
echo.
echo Riavvio del server in background (la finestra DOS si chiudera' da sola)...
taskkill /F /IM streamlit.exe >nul 2>&1
powershell -NoProfile -Command "Start-Process python -ArgumentList '-m streamlit run app.py --server.headless true --server.port 8501' -WorkingDirectory '%~dp0' -WindowStyle Hidden"
timeout /t 2 /nobreak >nul
start http://localhost:8501
exit
