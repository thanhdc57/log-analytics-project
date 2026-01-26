# Spark Scaling Simulation

To ensure the system auto-scales during your demo, I have added a "Simulation Mode" to the processing logic.

## Changes

1.  **Spark Streaming (`spark_streaming.py`)**:
    -   Added a `heavy_processing_simulation` function.
    -   This function introduces a small delay (0.01 seconds) for **every log message**.
    -   **Why?**: With 100 logs/sec, this creates 1 second of processing work per second. If you scale to 500 logs/sec, a single CPU cannot keep up -> Spark **MUST** scale up to handle the backlog.

## Testing the Demo

1.  **Deploy**:
    ```bash
    ./scripts/deploy-gke.sh
    ```

2.  **Start Low Load**:
    -   Go to Web UI -> Start "Baseline" (1 worker).
    -   Watch Grafana. Everything should be stable.

3.  **Trigger Scaling**:
    -   Go to Web UI -> Scale to **10 Workers** (High Load).
    -   This pumps ~1000+ logs/sec.
    -   Spark processing will slow down (Artificial Delay).
    -   **Result**: Watch the **Kubernetes Pods**. You will see new Spark Executors (`log-analytics-streaming-exec-...`) appearing automatically to help out.
