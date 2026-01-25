@echo off
REM Start Log Analytics System locally with Docker Compose
REM Windows batch script

echo ==========================================
echo 🚀 Starting Log Analytics System
echo ==========================================

REM Check Docker is running
docker info >nul 2>&1
if errorlevel 1 (
    echo ❌ Docker is not running. Please start Docker Desktop first.
    exit /b 1
)

REM Create network if not exists
docker network create log-analytics-net 2>nul

REM Copy env file
if not exist .env (
    copy .env.example .env
    echo 📝 Created .env from .env.example
)

REM Build log producer image
echo 📦 Building log-producer image...
docker build -t log-producer:latest src\producer\

REM Start services
echo 🚀 Starting all services...
docker compose up -d

REM Wait for services
echo ⏳ Waiting for services to be ready...
timeout /t 30 /nobreak >nul

REM Check services
echo.
echo ==========================================
echo ✅ Services Started!
echo ==========================================
echo.
echo 📊 Access URLs:
echo    Kafka UI:     http://localhost:8080
echo    Spark Master: http://localhost:8081
echo    Prometheus:   http://localhost:9090
echo    Grafana:      http://localhost:3000 (admin/admin123)
echo.
echo 📌 Useful Commands:
echo    docker compose logs -f log-producer
echo    docker compose ps
echo    docker compose down
echo.
