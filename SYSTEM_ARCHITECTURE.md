# Tài Liệu Kiến Trúc Hệ Thống Log Analytics (Mô Hình Scalable)

Tài liệu này tổng hợp kiến thức về hệ thống phân tích Log thời gian thực (Real-time Log Analytics) được xây dựng trên Google Kubernetes Engine (GKE), mô phỏng theo kiến trúc xử lý dữ liệu lớn của các nền tảng E-commerce (như Shopee).

## 1. Tổng Quan Hệ Thống

Hệ thống được thiết kế để chịu tải lớn, có khả năng tự động mở rộng (Auto Scale) khi lưu lượng truy cập tăng vọt (Flash Sale).

**Luồng Dữ Liệu:**
`Log Web Workers` -> `Kafka Brokers` -> `Spark Streaming` -> `Prometheus/Pushgateway` -> `Grafana`

---

## 2. Google Kubernetes Engine (GKE) - "Vị Thuyền Trưởng"

**Vai trò:** Hệ điều hành, Tổng chỉ huy của toàn bộ cơ sở hạ tầng.

GKE quản lý và điều phối các Container (các ứng dụng đóng gói). Nó giống như Chính Quyền Thành Phố quản lý các tòa nhà và cư dân.

*   **Declarative (Khai báo):** Chúng ta không ra lệnh "Làm thế nào", mà chỉ khai báo "Muốn cái gì" (thông qua file YAML). Ví dụ: "Tôi muốn 5 worker", GKE sẽ tự tìm cách làm điều đó.
*   **Scheduling (Sắp xếp):** Tự động tìm máy chủ (Node) còn trống tài nguyên để đặt ứng dụng vào chạy.
*   **Self-Healing (Tự phục hồi):** Nếu một Worker bị lỗi (crash), GKE tự động phát hiện và tạo cái mới thay thế ngay lập tức.
*   **Auto Scaling (Mở rộng):**
    *   *Horizontal Pod Autoscaler (HPA):* Tự động tăng số lượng Pod khi CPU cao.
    *   *Cluster Autoscaler:* Tự động mua thêm máy chủ (Node) Google Cloud khi cụm bị chật cứng.

---

## 3. Kafka Brokers - "Kho Tiếp Nhận & Băng Chuyền"

**Vai trò:** Hàng đợi thông điệp (Message Queue), bộ đệm trung gian.

*   **Tại sao cần Kafka?**
    *   Tốc độ sinh Log (Producer) thường không ổn định (lúc nhanh lúc chậm, có lúc Spike lên 20k log/s).
    *   Tốc độ xử lý (Consumer/Spark) thường ổn định và có giới hạn.
    *   Nếu nối trực tiếp, hệ thống xử lý sẽ bị "sặc" (overload) khi traffic tăng đột ngột. Kafka đứng giữa gánh toàn bộ traffic đó, lưu tạm vào ổ cứng để Spark lấy dần ra xử lý.
*   **Topic:** Giống như các "kệ hàng" phân loại trong kho (ví dụ: topic `application-logs`).

---

## 4. Apache Spark - "Nhà Máy Xử Lý Dữ Liệu"

Đây là bộ não tính toán, chia làm 3 thành phần chính:

### A. Spark Master (Quản Đốc)
*   Không trực tiếp xử lý dữ liệu.
*   Quản lý tài nguyên: Biết có bao nhiêu lính (Workers), ai rảnh ai bận.
*   Điều phối công việc (Task) cho các Workers.

### B. Spark Workers (Công Nhân)
*   Đây là lực lượng lao động chính, trực tiếp tiêu tốn CPU/RAM để xử lý dữ liệu.
*   Nhiệm vụ: Lấy dữ liệu từ Kafka, đếm log, tính toán Error Rate, lọc thông tin.
*   **Scaling:** Số lượng Worker có thể tăng giảm tùy theo khối lượng công việc (nhờ HPA). Nhiều Worker = Xử lý càng nhanh.

### C. Spark Submit / Driver (Giám Sát Viên & Lệnh Sản Xuất)
*   **Spark Submit Job:** Là một Pod chạy ứng dụng `spark_streaming.py`.
*   **Vai trò:**
    *   Chứa Code Logic (Ví dụ: "Hãy đếm số log lỗi trong 5 giây qua").
    *   Kết nối với Master để nộp "Phương án sản xuất".
    *   Duy trì kết nối mạng để giám sát quá trình chạy liên tục (Streaming).

---

## 5. Hệ Thống Giám Sát (Monitoring Stack)

Để biết hệ thống đang khỏe hay yếu, chúng ta cần bộ bác sĩ theo dõi 24/7.

### A. Prometheus (Thư Ký Ghi Chép)
*   Là cơ sở dữ liệu chuỗi thời gian (Time Series Database).
*   **Cơ chế Pull:** Định kỳ (ví dụ 15s), Prometheus chủ động đi "gõ cửa" các dịch vụ (Kafka, Log Web) để hỏi: "Nãy giờ chạy được bao nhiêu rồi?".
*   Nó lưu lại lịch sử các con số này.

### B. Pushgateway (Hòm Thư Ký Gửi)
*   **Vấn đề:** Spark là hệ thống phân tán, các Worker sinh ra chết đi liên tục, địa chỉ IP thay đổi, Prometheus không thể biết đường nào mà đến "gõ cửa".
*   **Giải pháp:** Spark chủ động GỬI (Push) báo cáo vào Pushgateway. Prometheus chỉ cần đến Pushgateway để lấy về.
*   Đóng vai trò trung gian/bộ đệm cho metric.

### C. Grafana (Màn Hình Hiển Thị)
*   Grafana **không chứa dữ liệu**.
*   Nó kết nối tới Prometheus để lấy số liệu và vẽ lên các biểu đồ đẹp mắt (Dashboard).
*   Giúp đội vận hành (DevOps) nhìn vào là biết ngay tình trạng sức khỏe hệ thống (Error Rate bao nhiêu, Traffic đang là bao nhiêu).

---

## 6. Các Kịch Bản Quy Hoạch Tải (Capacity Planning)

Hệ thống Log Web Generator được cấu hình các kịch bản mô phỏng thực tế:

| Kịch Bản | Mục Tiêu (Logs/s) | Số Lượng Worker | Mô Tả Thực Tế |
| :--- | :--- | :--- | :--- |
| **Baseline** | 1,000 | 1 | Ngày thường, traffic ổn định. |
| **Endurance** | 3,000 | 3 | Giờ cao điểm buổi tối (20h - 22h). |
| **Stress** | 10,000 | 10 | Các ngày Sale định kỳ (9.9, 10.10). |
| **Spike** | 20,000 | 20 | **Flash Sale 0h**. Traffic nổ tung trong thời gian ngắn. |
