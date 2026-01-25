# Báo cáo Bài Tập Lớn: Hệ Thống Phân Tích Log Real-time với Auto-Scaling

**Môn học**: Cloud Computing  
**Nhóm**: [Tên nhóm]  
**Thành viên**:
1. [Tên - MSSV]
2. [Tên - MSSV]
3. [Tên - MSSV]
4. [Tên - MSSV]
5. [Tên - MSSV]

---

## Mục Lục
1. [Đặt Vấn Đề](#1-đặt-vấn-đề)
2. [Xác Định Yêu Cầu](#2-xác-định-yêu-cầu)
3. [Thiết Kế](#3-thiết-kế)
4. [Xây Dựng và Triển Khai](#4-xây-dựng-và-triển-khai)
5. [Thử Nghiệm](#5-thử-nghiệm)
6. [Kết Luận và Đánh Giá](#6-kết-luận-và-đánh-giá)

---

## 1. Đặt Vấn Đề

### 1.1 Bối Cảnh
Trong môi trường microservices hiện đại, các ứng dụng tạo ra lượng log khổng lồ từ hàng trăm đến hàng nghìn instances. Việc thu thập, xử lý và phân tích log theo thời gian thực là thách thức lớn đòi hỏi một hệ thống có khả năng:
- **Co dãn linh hoạt** theo lưu lượng log
- **Xử lý real-time** để phát hiện sự cố nhanh chóng
- **Lưu trữ hiệu quả** cho phân tích batch

### 1.2 Vấn Đề Cần Giải Quyết
- Xử lý **peak traffic** (10,000+ logs/giây) mà không mất dữ liệu
- Tự động **scale-up** khi tải cao và **scale-down** khi tải thấp
- Cung cấp **metrics real-time** cho việc giám sát hệ thống
- **Tối ưu chi phí** bằng cách chỉ sử dụng tài nguyên khi cần thiết

---

## 2. Xác Định Yêu Cầu

### 2.1 Yêu Cầu Chức Năng

| Chức năng | Mô tả |
|-----------|-------|
| F1 | Thu thập log từ nhiều nguồn đồng thời |
| F2 | Xử lý log theo thời gian thực (latency < 5s) |
| F3 | Aggregate metrics theo window (1 phút, 5 phút) |
| F4 | Phát hiện anomaly (error rate > threshold) |
| F5 | Lưu trữ log để phân tích batch |
| F6 | Dashboard hiển thị metrics real-time |

### 2.2 Yêu Cầu Phi Chức Năng

| Yêu cầu | Mục tiêu |
|---------|----------|
| Throughput | 100 - 10,000 logs/giây |
| Latency | P95 < 5 giây |
| Availability | 99.9% |
| Scalability | Auto-scale 2x - 10x |
| Storage | 30 ngày hot, archive sau đó |

---

## 3. Thiết Kế

### 3.1 Kiến Trúc Tổng Quan

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Log Producers  │────▶│  Apache Kafka    │────▶│ Spark Streaming │
│  (Simulator)    │     │  (3 Brokers)     │     │  (Real-time)    │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
                        ┌──────────────────┐              │
                        │     Grafana      │◀─────────────┤
                        │    Dashboard     │              │
                        └──────────────────┘              ▼
                                ▲               ┌─────────────────┐
                                │               │   HDFS / GCS    │
                        ┌───────┴──────┐        └────────┬────────┘
                        │  Prometheus  │                 │
                        └──────────────┘                 ▼
                                               ┌─────────────────┐
                                               │  Spark Batch    │
                                               │  Analytics      │
                                               └─────────────────┘
```

### 3.2 Thành Phần

| Component | Công nghệ | Vai trò |
|-----------|-----------|---------|
| Message Queue | Apache Kafka | Buffer logs, đảm bảo không mất dữ liệu |
| Stream Processing | Spark Structured Streaming | Xử lý real-time, calculate metrics |
| Batch Processing | Spark SQL | Phân tích daily, generate reports |
| Storage | HDFS / Google Cloud Storage | Lưu trữ logs và reports |
| Monitoring | Prometheus + Grafana | Thu thập và hiển thị metrics |
| Load Testing | Locust | Simulate các kịch bản tải |

### 3.3 Chiến Lược Auto-Scaling

| Layer | Metric | Threshold | Action |
|-------|--------|-----------|--------|
| Kafka | Consumer lag | > 1000 | Add partition |
| Spark | Processing time | > batch interval | Add executor |
| K8s | CPU usage | > 70% | Add pod |

---

## 4. Xây Dựng và Triển Khai

### 4.1 Môi Trường Development

**Yêu cầu hệ thống**:
- Docker Desktop với 8GB RAM trở lên
- Docker Compose v2.x
- Python 3.9+

**Khởi chạy hệ thống**:
```bash
cd log-analytics-project
docker compose up -d
```

### 4.2 Các Service Chính

| Service | Port | URL |
|---------|------|-----|
| Kafka UI | 8080 | http://localhost:8080 |
| Spark Master | 8081 | http://localhost:8081 |
| Prometheus | 9090 | http://localhost:9090 |
| Grafana | 3000 | http://localhost:3000 |

### 4.3 Triển Khai Cloud (GCP)
[Chi tiết các bước deploy lên GKE...]

---

## 5. Thử Nghiệm

### 5.1 Kịch Bản Test

| Scenario | Users | Rate | Duration | Mục tiêu |
|----------|-------|------|----------|----------|
| Baseline | 10 | 100 logs/s | 5 min | Xác định baseline |
| Stress | 100 | 1000 logs/s | 10 min | Test scaling up |
| Spike | 500 | 5000 logs/s | 3 min | Test đột biến |
| Endurance | 50 | 500 logs/s | 30 min | Test ổn định |

### 5.2 Kết Quả

[Bảng kết quả và biểu đồ...]

### 5.3 Phân Tích

[Phân tích chi tiết về hiệu năng, scaling behavior...]

---

## 6. Kết Luận và Đánh Giá

### 6.1 Kết Quả Đạt Được
- ✅ Xây dựng thành công hệ thống log analytics real-time
- ✅ Thực hiện auto-scaling theo các kịch bản khác nhau
- ✅ Thu thập metrics và hiển thị trên dashboard

### 6.2 Hạn Chế
- [Liệt kê các hạn chế...]

### 6.3 Hướng Phát Triển
- Machine Learning để phát hiện anomaly
- Integration với alerting system (PagerDuty, Slack)
- Support multi-tenant

---

## Tài Liệu Tham Khảo
1. Apache Kafka Documentation
2. Apache Spark Structured Streaming Guide
3. Prometheus & Grafana Documentation
4. Google Cloud Platform Documentation
