"""
Load Testing with Locust - Simulates various load scenarios
"""
from locust import User, task, between, events
from kafka import KafkaProducer
import json
import random
from datetime import datetime
import time

# Kafka configuration
KAFKA_SERVERS = "localhost:9092,localhost:9093,localhost:9094"
KAFKA_TOPIC = "application-logs"

# Sample data
SERVICES = ['api-gateway', 'auth-service', 'user-service', 'payment-service', 'order-service']
LOG_LEVELS = ['DEBUG', 'INFO', 'WARN', 'ERROR']
LOG_LEVEL_WEIGHTS = [5, 70, 20, 5]


class LogProducerUser(User):
    """Simulates a log producer sending logs to Kafka"""
    
    wait_time = between(0.01, 0.1)  # Wait between 10-100ms between tasks
    
    def on_start(self):
        """Initialize Kafka producer"""
        self.producer = KafkaProducer(
            bootstrap_servers=KAFKA_SERVERS.split(','),
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            acks=1,
            linger_ms=5,
            batch_size=16384
        )
        self.request_counter = 0
    
    def on_stop(self):
        """Cleanup Kafka producer"""
        if self.producer:
            self.producer.flush()
            self.producer.close()
    
    @task(10)
    def send_info_log(self):
        """Send INFO level log (most common)"""
        self._send_log("INFO")
    
    @task(3)
    def send_warn_log(self):
        """Send WARN level log"""
        self._send_log("WARN")
    
    @task(1)
    def send_error_log(self):
        """Send ERROR level log (rare)"""
        self._send_log("ERROR")
    
    def _send_log(self, level):
        """Send a log message to Kafka"""
        self.request_counter += 1
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "service": random.choice(SERVICES),
            "host": f"host-{random.randint(1, 10)}",
            "request_id": f"req-{self.request_counter:08d}",
            "trace_id": f"trace-{random.randint(100000, 999999)}",
            "http_method": random.choice(["GET", "POST", "PUT", "DELETE"]),
            "http_path": f"/api/v1/{random.choice(['users', 'orders', 'products'])}",
            "http_status": self._get_status_code(level),
            "response_time_ms": random.randint(5, 500),
            "message": f"Test log message - {level}"
        }
        
        start_time = time.time()
        try:
            future = self.producer.send(KAFKA_TOPIC, value=log_entry)
            # Don't wait for ack to maximize throughput
            events.request.fire(
                request_type="KAFKA",
                name=f"send_{level.lower()}_log",
                response_time=(time.time() - start_time) * 1000,
                response_length=len(json.dumps(log_entry)),
                exception=None,
                context={}
            )
        except Exception as e:
            events.request.fire(
                request_type="KAFKA",
                name=f"send_{level.lower()}_log",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                exception=e,
                context={}
            )
    
    def _get_status_code(self, level):
        """Get HTTP status code based on log level"""
        if level == "ERROR":
            return random.choice([500, 502, 503])
        elif level == "WARN":
            return random.choice([400, 401, 404])
        else:
            return random.choice([200, 201, 204])


# Custom event handlers for reporting
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print("=" * 60)
    print("🚀 Load Test Starting...")
    print(f"   Target: {KAFKA_SERVERS}")
    print(f"   Topic: {KAFKA_TOPIC}")
    print("=" * 60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    print("=" * 60)
    print("✅ Load Test Complete!")
    print("=" * 60)
