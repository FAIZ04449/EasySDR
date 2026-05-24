@echo off
echo ===================================================
echo   EasySDR Autonomous Prospecting System
echo ===================================================
echo.
echo Starting services...
echo.

:: Start FastAPI Backend
echo [1/2] Starting FastAPI Backend on http://localhost:8000...
start "FastAPI Backend" cmd /k "cd backend && .\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"

:: Start Vite Frontend
echo [2/2] Starting Vite React Frontend...
start "Vite React Dashboard" cmd /k "cd frontend && npm run dev"

echo.
echo ===================================================
echo Services successfully started in separate windows!
echo - FastAPI API Documentation: http://localhost:8000/docs
echo - Vite React Dashboard is loading (default: http://localhost:5173)
echo ===================================================
echo.
pause
