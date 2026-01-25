# Log Analytics Project - Cloud Computing BTL

Hệ thống phân tích log real-time với khả năng tự động co dãn (auto-scaling) trên Google Cloud Platform.

## 🎯 Tính Năng

- **Real-time Processing**: Xử lý log theo thời gian thực với Spark Streaming
- **Auto-scaling**: Tự động scale theo tải (Kafka partitions, Spark executors, K8s pods)
- **Monitoring**: Dashboard Grafana hiển thị metrics real-time
- **Load Testing**: Locust với 4 kịch bản test khác nhau

## 🛠 Tech Stack

| Component | Technology |
|-----------|------------|
| Message Queue | Apache Kafka (3 brokers) |
| Stream Processing | Spark Structured Streaming |
| Batch Processing | Spark SQL |
| Monitoring | Prometheus + Grafana |
| Container | Docker / Kubernetes |
| Cloud | Google Cloud (GKE) |

## 📂 Project Structure

```
log-analytics-project/
├── docker-compose.yml      # Local development
├── src/
│   ├── producer/           # Log generator (Python)
│   ├── streaming/          # Spark Streaming job
│   └── batch/              # Spark Batch analytics
├── k8s/                    # Kubernetes manifests
│   ├── kafka/              # Strimzi Kafka cluster
│   ├── spark/              # Spark Operator jobs
│   ├── hpa/                # Horizontal Pod Autoscalers
│   └── monitoring/         # Prometheus + Grafana
├── config/                 # Configuration files
├── dashboards/             # Grafana dashboards
├── load-tests/             # Locust load testing
├── scripts/                # Automation scripts
└── docs/                   # Documentation
```

## 🚀 Quick Start (Local)

### Prerequisites
- Docker Desktop (8GB+ RAM)
- Python 3.9+

### Start System
```bash
# Windows
scripts\start-local.bat

# Or manually
docker compose up -d
```

### Access UIs
| Service | URL | Credentials |
|---------|-----|-------------|
| Kafka UI | http://localhost:8080 | - |
| Spark Master | http://localhost:8081 | - |
| Prometheus | http://localhost:9090 | - |
| Grafana | http://localhost:3000 | admin / admin123 |

### Run Load Tests
```bash
# Windows - Interactive menu
scripts\run-load-test.bat

# Manual
cd load-tests
pip install -r requirements.txt
locust -f locustfile.py --users 10 --spawn-rate 1 --run-time 5m
```

## ☁️ Deploy to GKE

### Prerequisites
- Google Cloud account with billing
- gcloud CLI installed
- kubectl configured

### Deploy
```bash
# Set project ID
export GCP_PROJECT_ID=your-project-id

# Run deployment script
chmod +x scripts/deploy-gke.sh
./scripts/deploy-gke.sh
```

## 📊 Load Test Scenarios

| Scenario | Users | Rate | Duration | Purpose |
|----------|-------|------|----------|---------|
| Baseline | 10 | 100/s | 5 min | Establish baseline |
| Stress | 100 | 1000/s | 10 min | Test scale-up |
| Spike | 500 | 5000/s | 3 min | Test sudden surge |
| Endurance | 50 | 500/s | 30 min | Test stability |

## 📈 Auto-Scaling Configuration

### Kafka
- 3 brokers, 12 partitions
- Replication factor: 3

### Spark (Dynamic Allocation)
- Min executors: 1
- Max executors: 10
- Scale trigger: Processing time > batch interval

### Kubernetes (HPA)
- Min pods: 1
- Max pods: 10
- Scale trigger: CPU > 70% or Memory > 80%

## 👥 Team Members

1. [Tên - MSSV]
2. [Tên - MSSV]
3. [Tên - MSSV]
4. [Tên - MSSV]
5. [Tên - MSSV]

## 📝 License

This project is for educational purposes - Cloud Computing course.
