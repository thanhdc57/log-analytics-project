"""
Log Producer - Generates simulated application logs and sends to Kafka
"""
import os
import json
import time
import random
import logging
from datetime import datetime
from typing import Dict, Any
from kafka import KafkaProducer
from prometheus_client import start_http_server, Counter, Gauge, Histogram

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
KAFKA_TOPIC = os.getenv('KAFKA_TOPIC', 'application-logs')
LOG_RATE = int(os.getenv('LOG_RATE', '100'))  # logs per second
METRICS_PORT = int(os.getenv('METRICS_PORT', '8000'))

# Prometheus metrics
logs_produced_total = Counter('logs_produced_total', 'Total number of logs produced', ['level', 'service'])
logs_per_second = Gauge('logs_per_second', 'Current log production rate')
log_size_bytes = Histogram('log_size_bytes', 'Size of produced logs in bytes', 
                           buckets=[100, 200, 500, 1000, 2000, 5000])
kafka_send_latency = Histogram('kafka_send_latency_seconds', 'Latency of Kafka send operations',
                               buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0])

# Sample data for log generation
SERVICES = ['api-gateway', 'auth-service', 'user-service', 'payment-service', 'order-service', 'notification-service']
LOG_LEVELS = ['DEBUG', 'INFO', 'WARN', 'ERROR']
LOG_LEVEL_WEIGHTS = [5, 70, 20, 5]  # Weighted distribution

HTTP_METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']
HTTP_ENDPOINTS = [
    '/api/v1/users', '/api/v1/orders', '/api/v1/payments',
    '/api/v1/products', '/api/v1/auth/login', '/api/v1/auth/logout',
    '/api/v1/notifications', '/api/v1/health', '/api/v1/metrics'
]
HTTP_STATUS_CODES = [200, 201, 204, 400, 401, 403, 404, 500, 502, 503]
HTTP_STATUS_WEIGHTS = [50, 10, 5, 10, 5, 3, 7, 5, 3, 2]

ERROR_MESSAGES = [
    "Database connection timeout",
    "Redis cache miss",
    "External API call failed",
    "Invalid request payload",
    "Authentication token expired",
    "Rate limit exceeded",
    "Service unavailable",
    "Memory allocation failed"
]

INFO_MESSAGES = [
    "Request processed successfully",
    "User authenticated",
    "Order created",
    "Payment processed",
    "Notification sent",
    "Cache updated",
    "Health check passed"
]


class LogGenerator:
    """Generates realistic application logs"""
    
    def __init__(self):
        self.request_id_counter = 0
    
    def generate_request_id(self) -> str:
        self.request_id_counter += 1
        return f"req-{self.request_id_counter:08d}"
    
    def generate_log(self) -> Dict[str, Any]:
        """Generate a single log entry"""
        level = random.choices(LOG_LEVELS, weights=LOG_LEVEL_WEIGHTS, k=1)[0]
        service = random.choice(SERVICES)
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "service": service,
            "host": f"{service}-{random.randint(1, 5)}",
            "request_id": self.generate_request_id(),
            "trace_id": f"trace-{random.randint(100000, 999999)}",
        }
        
        # Add HTTP request info
        if random.random() < 0.8:  # 80% of logs have HTTP info
            status_code = random.choices(HTTP_STATUS_CODES, weights=HTTP_STATUS_WEIGHTS, k=1)[0]
            log_entry.update({
                "http_method": random.choice(HTTP_METHODS),
                "http_path": random.choice(HTTP_ENDPOINTS),
                "http_status": status_code,
                "response_time_ms": self._generate_response_time(status_code),
                "client_ip": f"192.168.{random.randint(1, 255)}.{random.randint(1, 255)}"
            })
        
        # Add message based on level
        if level == "ERROR":
            log_entry["message"] = random.choice(ERROR_MESSAGES)
            log_entry["stack_trace"] = self._generate_stack_trace()
        elif level == "WARN":
            log_entry["message"] = f"Warning: {random.choice(ERROR_MESSAGES)}"
        else:
            log_entry["message"] = random.choice(INFO_MESSAGES)
        
        return log_entry
    
    def _generate_response_time(self, status_code: int) -> int:
        """Generate response time based on status code"""
        if status_code >= 500:
            return random.randint(1000, 5000)  # Slow for server errors
        elif status_code >= 400:
            return random.randint(10, 100)  # Fast for client errors
        else:
            return random.randint(5, 500)  # Normal distribution
    
    def _generate_stack_trace(self) -> str:
        """Generate a fake stack trace"""
        return f"""java.lang.RuntimeException: {random.choice(ERROR_MESSAGES)}
    at com.example.{random.choice(SERVICES)}.handler.RequestHandler.process(RequestHandler.java:{random.randint(50, 200)})
    at com.example.{random.choice(SERVICES)}.service.MainService.execute(MainService.java:{random.randint(100, 300)})
    at java.base/java.util.concurrent.ThreadPoolExecutor.runWorker(ThreadPoolExecutor.java:1136)"""


class LogProducer:
    """Produces logs to Kafka"""
    
    def __init__(self, bootstrap_servers: str, topic: str):
        self.topic = topic
        self.generator = LogGenerator()
        
        logger.info(f"Connecting to Kafka at {bootstrap_servers}")
        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers.split(','),
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            acks='all',
            retries=3,
            retry_backoff_ms=100
        )
        logger.info("Kafka producer initialized successfully")
    
    def send_log(self, log_entry: Dict[str, Any]):
        """Send a single log to Kafka"""
        start_time = time.time()
        
        # Serialize and measure size
        log_json = json.dumps(log_entry)
        log_size_bytes.observe(len(log_json.encode('utf-8')))
        
        # Send to Kafka
        future = self.producer.send(self.topic, value=log_entry)
        
        # Record latency
        latency = time.time() - start_time
        kafka_send_latency.observe(latency)
        
        # Update counters
        logs_produced_total.labels(
            level=log_entry['level'],
            service=log_entry['service']
        ).inc()
        
        return future
    
    def run(self, rate_per_second: int):
        """Run the producer at specified rate"""
        logger.info(f"Starting log production at {rate_per_second} logs/second")
        logs_per_second.set(rate_per_second)
        
        interval = 1.0 / rate_per_second if rate_per_second > 0 else 1.0
        
        while True:
            batch_start = time.time()
            
            for _ in range(rate_per_second):
                log_entry = self.generator.generate_log()
                self.send_log(log_entry)
            
            # Flush the batch
            self.producer.flush()
            
            # Calculate sleep time to maintain rate
            elapsed = time.time() - batch_start
            sleep_time = max(0, 1.0 - elapsed)
            
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                logger.warning(f"Falling behind: batch took {elapsed:.2f}s")
    
    def close(self):
        self.producer.close()


def main():
    # Start Prometheus metrics server
    logger.info(f"Starting metrics server on port {METRICS_PORT}")
    start_http_server(METRICS_PORT)
    
    # Wait for Kafka to be ready
    logger.info("Waiting for Kafka to be ready...")
    time.sleep(10)
    
    # Create and run producer
    producer = LogProducer(KAFKA_BOOTSTRAP_SERVERS, KAFKA_TOPIC)
    
    try:
        producer.run(LOG_RATE)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        producer.close()


if __name__ == "__main__":
    main()
