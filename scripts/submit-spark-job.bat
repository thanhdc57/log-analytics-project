@echo off
REM Submit Spark jobs
REM Windows batch script

echo ==========================================
echo ⚡ Spark Job Submission
echo ==========================================
echo.

set SPARK_MASTER=local[*]

echo Select job to run:
echo   1. Streaming Job (Real-time log processing)
echo   2. Batch Job (Daily analytics)
echo.

set /p choice="Enter choice (1-2): "

if "%choice%"=="1" goto streaming
if "%choice%"=="2" goto batch
goto invalid

:streaming
echo 🚀 Submitting Spark Streaming Job...
echo 📦 Installing Python dependencies...
docker exec -u 0 spark-master pip install prometheus_client
echo 🧹 Clearing previous checkpoints...
docker exec -u 0 spark-master rm -rf /tmp/spark-checkpoints/log-analytics
docker exec -u 0 spark-master /opt/spark/bin/spark-submit --master "local[2]" --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.apache.commons:commons-pool2:2.11.1 --conf spark.streaming.backpressure.enabled=true /opt/spark-apps/streaming/spark_streaming.py
goto end

:batch
echo 🚀 Submitting Spark Batch Job...
docker exec -u 0 spark-master /opt/spark/bin/spark-submit --master "local[*]" --conf spark.executor.memory=2g --conf spark.executor.cores=2 /opt/spark-apps/batch/spark_batch_analytics.py
goto end

:invalid
echo ❌ Invalid choice
goto end

:end
