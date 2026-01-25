# Load Test Scenarios

## 1. Baseline Test (Normal Load)
```bash
# 10 users, spawn rate 1 user/sec, run for 5 minutes
locust -f locustfile.py --users 10 --spawn-rate 1 --run-time 5m --headless
```

## 2. Stress Test (High Load)
```bash
# 100 users, spawn rate 10 users/sec, run for 10 minutes
locust -f locustfile.py --users 100 --spawn-rate 10 --run-time 10m --headless
```

## 3. Spike Test (Sudden Traffic Surge)
```bash
# 500 users, spawn rate 100 users/sec, run for 3 minutes
locust -f locustfile.py --users 500 --spawn-rate 100 --run-time 3m --headless
```

## 4. Endurance Test (Sustained Load)
```bash
# 50 users, run for 30 minutes to test stability
locust -f locustfile.py --users 50 --spawn-rate 5 --run-time 30m --headless
```

## 5. Interactive Mode (With Web UI)
```bash
# Start Locust with web UI at http://localhost:8089
locust -f locustfile.py --host ""
```

## Expected Metrics to Monitor

| Scenario | Expected Logs/sec | CPU Usage | Memory | Kafka Lag |
|----------|------------------|-----------|--------|-----------|
| Baseline | 100-200 | < 30% | < 2GB | < 100 |
| Stress | 1000-2000 | 50-80% | 2-4GB | < 1000 |
| Spike | 3000-5000 | > 80% | 4-6GB | May spike |
| Endurance | 500-800 | 40-60% | Stable | Stable |
