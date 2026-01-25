@echo off
REM Run load tests with Locust
REM Windows batch script

echo ==========================================
echo 🔥 Log Analytics Load Testing
echo ==========================================
echo.

REM Check if Locust is installed
pip show locust >nul 2>&1
if errorlevel 1 (
    echo 📦 Installing Locust and dependencies...
    pip install -r load-tests\requirements.txt
)

echo.
echo Select test scenario:
echo   1. Baseline (10 users, 100 logs/s, 5 min)
echo   2. Stress (100 users, 1000 logs/s, 10 min)  
echo   3. Spike (500 users, 5000 logs/s, 3 min)
echo   4. Endurance (50 users, 500 logs/s, 30 min)
echo   5. Interactive (Web UI)
echo.

set /p choice="Enter choice (1-5): "

cd load-tests

if "%choice%"=="1" (
    echo 🚀 Running Baseline Test...
    locust -f locustfile.py --users 10 --spawn-rate 1 --run-time 5m --headless --html=reports/baseline.html
) else if "%choice%"=="2" (
    echo 🚀 Running Stress Test...
    locust -f locustfile.py --users 100 --spawn-rate 10 --run-time 10m --headless --html=reports/stress.html
) else if "%choice%"=="3" (
    echo 🚀 Running Spike Test...
    locust -f locustfile.py --users 500 --spawn-rate 100 --run-time 3m --headless --html=reports/spike.html
) else if "%choice%"=="4" (
    echo 🚀 Running Endurance Test...
    locust -f locustfile.py --users 50 --spawn-rate 5 --run-time 30m --headless --html=reports/endurance.html
) else if "%choice%"=="5" (
    echo 🌐 Starting Locust Web UI at http://localhost:8089
    locust -f locustfile.py
) else (
    echo ❌ Invalid choice
)

cd ..
