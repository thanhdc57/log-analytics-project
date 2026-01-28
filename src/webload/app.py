import os
from kubernetes import client, config
import json
import time
import random
import threading
import logging
from datetime import datetime
from fastapi import FastAPI, Request

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from kafka import KafkaProducer
from prometheus_client import make_asgi_app, Counter, Gauge, Histogram

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "application-logs")

# Prometheus metrics
logs_produced_total = Counter('logs_produced_total', 'Total number of logs produced', ['level', 'service'])
logs_per_second = Gauge('logs_per_second', 'Current log production rate')
log_size_bytes = Histogram('log_size_bytes', 'Size of produced logs in bytes', 
                           buckets=[100, 200, 500, 1000, 2000, 5000])
kafka_send_latency = Histogram('kafka_send_latency_seconds', 'Latency of Kafka send operations',
                               buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0])

app = FastAPI()
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

templates = Jinja2Templates(directory="templates")

SERVICES = [
    "api-gateway",
    "auth-service",
    "user-service",
    "payment-service",
    "order-service",
    "notification-service",
]
LOG_LEVELS = ["DEBUG", "INFO", "WARN", "ERROR"]
LOG_LEVEL_WEIGHTS = [5, 70, 20, 5]
HTTP_STATUS_CODES = [200, 201, 204, 400, 401, 403, 404, 500, 502, 503]
HTTP_STATUS_WEIGHTS = [50, 10, 5, 10, 5, 3, 7, 5, 3, 2]
HTTP_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH"]
HTTP_ENDPOINTS = [
    "/api/v1/users",
    "/api/v1/orders",
    "/api/v1/payments",
    "/api/v1/products",
    "/api/v1/auth/login",
    "/api/v1/auth/logout",
    "/api/v1/notifications",
    "/api/v1/health",
    "/api/v1/metrics",
]

SCENARIOS = {
    "baseline": {"rate": int(os.getenv("BASELINE_RATE", 200)), "duration": 86400},
    "stress": {"rate": 1200, "duration": 600},         # Target: ~10 workers
    "spike": {"rate": 2000, "duration": 180},          # Target: Max/Overload
    "endurance": {"rate": 800, "duration": 1800},      # Target: ~7-8 workers
}

_lock = threading.Lock()
_running = False
_stop_event = threading.Event()
_thread = None
_current = {"scenario": None, "rate": 0, "started_at": None}


def _make_log(req_id: int):
    level = random.choices(LOG_LEVELS, weights=LOG_LEVEL_WEIGHTS, k=1)[0]
    status_code = random.choices(HTTP_STATUS_CODES, weights=HTTP_STATUS_WEIGHTS, k=1)[0]
    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "level": level,
        "service": random.choice(SERVICES),
        "host": f"host-{random.randint(1, 10)}",
        "request_id": f"req-{req_id:08d}",
        "trace_id": f"trace-{random.randint(100000, 999999)}",
        "http_method": random.choice(HTTP_METHODS),
        "http_path": random.choice(HTTP_ENDPOINTS),
        "http_status": status_code,
        "response_time_ms": random.randint(5, 500),
        "client_ip": f"10.0.{random.randint(1, 255)}.{random.randint(1, 255)}",
        "message": "Load test log",
    }


def _run_scenario(rate: int, duration: int):
    global _running
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(","),
        acks=1,
        linger_ms=5,
        batch_size=16384,
    )
    start = time.time()
    req_id = 0
    interval = 1.0

    logs_per_second.set(rate)

    try:
        while not _stop_event.is_set() and (time.time() - start) < duration:
            batch_start = time.time()
            for _ in range(rate):
                req_id += 1
                log_entry = _make_log(req_id)
                
                # OPTIMIZATION: Serialize once
                payload_bytes = json.dumps(log_entry).encode("utf-8")
                
                # Metrics: Size
                log_size_bytes.observe(len(payload_bytes))

                # Send raw bytes
                send_start = time.time()
                producer.send(KAFKA_TOPIC, value=payload_bytes)
                kafka_send_latency.observe(time.time() - send_start)

                # Metrics: Count
                logs_produced_total.labels(
                    level=log_entry['level'],
                    service=log_entry['service']
                ).inc()

            producer.flush()
            elapsed = time.time() - batch_start
            sleep_time = max(0.0, interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)
    finally:
        producer.flush()
        producer.close()
        logs_per_second.set(0)
        with _lock:
            _running = False
            _current["scenario"] = None
            _current["rate"] = 0
            _current["started_at"] = None
        _stop_event.clear()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "scenarios": SCENARIOS,
        },
    )


@app.get("/status")
def status():
    with _lock:
        return JSONResponse({
            "running": _running,
            "scenario": _current["scenario"],
            "rate": _current["rate"],
            "started_at": _current["started_at"],
        })


CLUSTER_MODE = os.getenv("CLUSTER_MODE", "false").lower() == "true"
WORKER_DEPLOYMENT = "log-web-worker"
NAMESPACE = "log-analytics"

class ClusterManager:
    def __init__(self):
        self.enabled = False
        try:
            config.load_incluster_config()
            self.apps_v1 = client.AppsV1Api()
            self.enabled = True
            logger.info("ClusterManager: Kubernetes config loaded successfully.")
        except Exception as e:
            logger.warning(f"ClusterManager: Failed to load K8s config. Scaling disabled. Error: {e}")

    def scale_workers(self, replicas: int):
        if not self.enabled:
            return False
        try:
            logger.info(f"ClusterManager: Scaling {WORKER_DEPLOYMENT} to {replicas} replicas.")
            # Patch the deployment
            body = {"spec": {"replicas": replicas}}
            self.apps_v1.patch_namespaced_deployment_scale(
                name=WORKER_DEPLOYMENT,
                namespace=NAMESPACE,
                body=body
            )
            return True
        except Exception as e:
            logger.error(f"ClusterManager: Scaling failed: {e}")
            return False

cluster_manager = ClusterManager() if CLUSTER_MODE else None

@app.post("/start/{name}")
def start(name: str):
    global _running, _thread
    if name not in SCENARIOS:
        return JSONResponse({"error": "Unknown scenario"}, status_code=400)

    # CLUSTER MODE LOGIC
    if CLUSTER_MODE and cluster_manager:
        target_replicas = 1  # Default
        if name == "stress": target_replicas = 10
        if name == "spike": target_replicas = 20
        if name == "endurance": target_replicas = 5
        
        success = cluster_manager.scale_workers(target_replicas)
        if success:
             with _lock:
                _running = True
                _current["scenario"] = name
                _current["rate"] = f"Cluster Scale: {target_replicas} workers"
                _current["started_at"] = datetime.utcnow().isoformat() + "Z"
             
             # Monitor Thread for Cluster Mode Duration
             def _monitor_cluster_scenario(duration):
                global _running
                logger.info(f"Monitor: Waiting for {duration}s or stop event...")
                if not _stop_event.wait(duration):
                    # Timeout reached -> Scale Down
                    logger.info("Monitor: Duration expired. Auto-scaling to 0.")
                    cluster_manager.scale_workers(0)
                    with _lock:
                        _running = False
                        _current["scenario"] = None
                else:
                    logger.info("Monitor: Stopped manually.")

             _stop_event.clear()
             threading.Thread(target=_monitor_cluster_scenario, args=(SCENARIOS[name]["duration"],), daemon=True).start()

             return JSONResponse({"ok": True, "scenario": name, "mode": "cluster", "replicas": target_replicas})
        else:
             return JSONResponse({"error": "Failed to scale cluster"}, status_code=500)

    # LOCAL MODE LOGIC (Legacy)
    with _lock:
        if _running:
            return JSONResponse({"error": "Scenario already running"}, status_code=400)
        _running = True
        _current["scenario"] = name
        _current["rate"] = SCENARIOS[name]["rate"]
        _current["started_at"] = datetime.utcnow().isoformat() + "Z"

    _stop_event.clear()
    _thread = threading.Thread(
        target=_run_scenario,
        args=(SCENARIOS[name]["rate"], SCENARIOS[name]["duration"]),
        daemon=True,
    )
    _thread.start()
    return JSONResponse({"ok": True, "scenario": name})


@app.on_event("startup")
def startup_event():
    # Helper to start scenario in a separate thread
    def auto_start():
        logger.info("Checking AUTO_START configuration...")
        auto_start_env = os.getenv("AUTO_START", "false").lower()
        if auto_start_env == "true":
            logger.info("AUTO_START is enabled. Starting baseline scenario...")
            # Give Kafka a moment to be ready
            time.sleep(10)
            
            # Simulate a start request
            global _running, _thread
            name = "baseline"
            
            with _lock:
                if not _running:
                    _running = True
                    _current["scenario"] = name
                    _current["rate"] = SCENARIOS[name]["rate"]
                    _current["started_at"] = datetime.utcnow().isoformat() + "Z"
                    
                    _stop_event.clear()
                    _thread = threading.Thread(
                        target=_run_scenario,
                        args=(SCENARIOS[name]["rate"], SCENARIOS[name]["duration"]),
                        daemon=True,
                    )
                    _thread.start()
                    logger.info(f"Auto-started scenario: {name}")

    threading.Thread(target=auto_start, daemon=True).start()


@app.post("/stop")
def stop():
    if CLUSTER_MODE and cluster_manager:
        logger.info("Stop requested. Scaling workers to 0...")
        cluster_manager.scale_workers(0)

    if not _running:
        return JSONResponse({"ok": True, "message": "No scenario running (Workers scaled down)"})
    
    _stop_event.set()
    return JSONResponse({"ok": True})
