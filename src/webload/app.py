import os
import json
import time
import random
import threading
from datetime import datetime
from fastapi import FastAPI, Request
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
    "baseline": {"rate": 100, "duration": 300},
    "stress": {"rate": 1000, "duration": 600},
    "spike": {"rate": 5000, "duration": 180},
    "endurance": {"rate": 300, "duration": 1800},
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
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
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
                
                # Metrics: Size
                log_json = json.dumps(log_entry)
                log_size_bytes.observe(len(log_json.encode('utf-8')))

                # Send
                send_start = time.time()
                producer.send(KAFKA_TOPIC, value=log_entry)
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


@app.post("/start/{name}")
def start(name: str):
    global _running, _thread
    if name not in SCENARIOS:
        return JSONResponse({"error": "Unknown scenario"}, status_code=400)

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


@app.post("/stop")
def stop():
    if not _running:
        return JSONResponse({"ok": True, "message": "No scenario running"})
    _stop_event.set()
    return JSONResponse({"ok": True})