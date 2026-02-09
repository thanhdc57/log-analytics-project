# Log Analytics Project - Cloud Computing BTL

Hệ thống phân tích log real-time mô phỏng kiến trúc E-commerce (Shopee) với khả năng tự động co dãn (auto-scaling) trên Google Kubernetes Engine (GKE).

📄 **[Xem Tài liệu Kiến trúc Hệ thống Chi tiết (SYSTEM_ARCHITECTURE.md)](SYSTEM_ARCHITECTURE.md)**

## 🎯 Tính Năng Chính

- **High Throughput**: Xử lý tới **20,000 logs/s** (tương đương Flash Sale).
- **Real-time Processing**: Spark Streaming xử lý dữ liệu với độ trễ thấp (< 1s).
- **Auto-scaling đa tầng**:
    - **Log Workers**: Tự động scale từ 1 -> 5 workers theo kịch bản tải (Cluster Manager).
    - **Spark Workers**: Tự động scale từ 1 -> 5 workers theo CPU (K8s HPA).
- **Full Observability**: Dashboard Grafana giám sát toàn diện (Business Metrics, System Health, Kafka Lag).

## 🛠 Tech Stack

| Component | Technology | Deploy Mode |
|-----------|------------|-------------|
| **Log Generator** | Python (FastAPI + Kafka Producer) | **Client Controller** (Manager/Worker) |
| **Message Queue** | Apache Kafka | StatefulSet (3 Brokers) |
| **Stream Processing** | Apache Spark 3.5 | **Standalone Cluster** (Master/Worker) |
| **Monitoring** | Prometheus + Pushgateway | K8s Deployment |
| **Visualization** | Grafana | K8s Deployment |
| **Infrastructure** | Google Kubernetes Engine (GKE) | Regional Cluster |

## 📂 Cấu Trúc Dự Án

```
log-analytics-project/
├── docker-compose.gce-core.yml # Local/VM deployment reference
├── src/
│   ├── webload/            # Log Generator (Manager + Worker logic)
│   └── streaming/          # Spark Streaming Application
├── k8s/                    # Kubernetes Manifests
│   ├── kafka/              # Manual Kafka Cluster
│   ├── producer/           # Log Web Manager & Workers
│   ├── spark-manual/       # Spark Master, Worker (HPA), Submit Job
│   └── monitoring/         # Prometheus, Grafana, Pushgateway
├── scripts/                # Automation scripts
│   └── deploy-gke.sh       # Script deploy toàn bộ lên GKE
└── SYSTEM_ARCHITECTURE.md  # Tài liệu kiến trúc chi tiết
```

## 🚀 Hướng Dẫn Deploy (GKE)

### Yêu cầu
- Google Cloud Project (có Billing).
- `gcloud` CLI & `kubectl` đã cài đặt.

### Các Bước Triển Khai
1. **Cấu hình Project ID:**
   Thiết lập biến môi trường `GCP_PROJECT_ID` (được sử dụng bởi script deploy) và cấu hình gcloud.
   ```bash
   export GCP_PROJECT_ID=your-project-id
   gcloud config set project $GCP_PROJECT_ID
   ```

2. **Chạy Script Deploy:**
   (Script này sẽ tự động tạo Cluster, cài đặt Kafka, Spark, Monitoring và Deploy App)
   ```bash
   chmod +x scripts/deploy-gke.sh
   ./scripts/deploy-gke.sh
   ```
   > **Lưu ý:** Nếu bạn muốn thay đổi Project ID mặc định vĩnh viễn, bạn có thể chỉnh sửa trực tiếp dòng `PROJECT_ID` trong file `scripts/deploy-gke.sh`.

3. **Truy Cập Hệ Thống:**
   Sau khi deploy xong, script sẽ xuất ra các đường dẫn truy cập:
   - **Log Web UI**: Để điều khiển kịch bản tải.
   - **Grafana**: `admin` / `admin123` (Xem Dashboard).
   - **Spark Master UI**: Xem trạng thái Cluster và Jobs.

## 📊 Kịch Bản Test Tải (Shopee Style)

Hệ thống hỗ trợ 4 kịch bản mô phỏng thực tế:

| Kịch Bản | Mục Tiêu (Logs/s) | Số Worker (Scale) | Mô Tả |
|----------|-------------------|-------------------|-------|
| **Baseline** | 1,000 | 1 | Ngày thường, traffic ổn định. |
| **Endurance** | 3,000 | 2 | Giờ cao điểm tối (Evening Peak). |
| **Stress** | 10,000 | 3 | **9.9 Sale Campaign**. |
| **Spike** | 20,000 | 5 | **Flash Sale 0h**. Traffic nổ tung. |

## 📈 Cơ Chế Auto-Scaling

### 1. Log Generator Scaling (Custom Controller)
- **Cơ chế**: `Log Web Manager` nhận lệnh từ UI -> Gọi K8s API để patch số lượng replica của `log-web-worker`.
- **Logic**: 
    - Baseline -> 1 Replica.
    - Spike -> 5 Replicas.
    - Stop/Timeout -> 0 Replicas (Tiết kiệm tài nguyên).

### 2. Spark Worker Scaling (K8s HPA)
- **Cơ chế**: Kubernetes Horizontal Pod Autoscaler.
- **Trigger**: CPU Utilization > 50%.
- **Range**: Min 1 - Max 5 Workers.

