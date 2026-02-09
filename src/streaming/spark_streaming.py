from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    from_json, col, window, count, avg, sum as spark_sum,
    when, expr, current_timestamp, udf, lit, length, 
    regexp_extract, split, explode, lower, trim,
    abs as spark_abs, concat, substring, md5,
    stddev, variance, min as spark_min, max as spark_max,
    collect_list, size, array_distinct, countDistinct
)
from pyspark.sql.types import (
    StructType, StructField, StringType, 
    IntegerType, FloatType, ArrayType, DoubleType
)
import os
import hashlib
import re
import math

# Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka-1:29092,kafka-2:29093,kafka-3:29094')
KAFKA_TOPIC = os.getenv('KAFKA_TOPIC', 'application-logs')
CHECKPOINT_LOCATION = os.getenv('CHECKPOINT_LOCATION', '/tmp/spark-checkpoints/log-analytics')
PUSHGATEWAY_URL = os.getenv('PUSHGATEWAY_URL', 'http://pushgateway:9091')

# PROCESSING: Near-continuous (every 1 second)
TRIGGER_INTERVAL = os.getenv('TRIGGER_INTERVAL', '3 seconds')

# CPU Intensity Level (1-5, higher = more CPU usage)
CPU_INTENSITY = int(os.getenv('CPU_INTENSITY', '5'))

# Log schema
LOG_SCHEMA = StructType([
    StructField("timestamp", StringType(), True),
    StructField("level", StringType(), True),
    StructField("service", StringType(), True),
    StructField("host", StringType(), True),
    StructField("request_id", StringType(), True),
    StructField("trace_id", StringType(), True),
    StructField("http_method", StringType(), True),
    StructField("http_path", StringType(), True),
    StructField("http_status", IntegerType(), True),
    StructField("response_time_ms", IntegerType(), True),
    StructField("client_ip", StringType(), True),
    StructField("message", StringType(), True),
    StructField("stack_trace", StringType(), True)
])


# ============================================================
# CPU-INTENSIVE UDFs (User Defined Functions)
# These simulate real-world heavy processing tasks
# ============================================================

def compute_anomaly_score(response_time, http_status, level):
    """
    Simulate ML-based anomaly detection computation
    Uses multiple mathematical operations to increase CPU load
    """
    if response_time is None or http_status is None:
        return 0.0
    
    score = 0.0
    
    # Base score from response time (simulating feature extraction)
    if response_time > 0:
        # Multiple expensive math operations
        log_rt = math.log(response_time + 1)
        sqrt_rt = math.sqrt(response_time)
        score += (log_rt * sqrt_rt) / 100
    
    # Status code scoring (simulating one-hot encoding + weighting)
    status_weights = {
        200: 0.0, 201: 0.0, 204: 0.1,
        400: 0.5, 401: 0.6, 403: 0.7, 404: 0.4,
        500: 1.0, 502: 0.9, 503: 0.95
    }
    score += status_weights.get(http_status, 0.3)
    
    # Level scoring
    level_weights = {'DEBUG': 0.0, 'INFO': 0.1, 'WARN': 0.5, 'ERROR': 1.0}
    score += level_weights.get(level, 0.2)
    
    # Normalize with sigmoid (expensive computation)
    try:
        normalized = 1 / (1 + math.exp(-score))
    except:
        normalized = 0.5
    
    # Additional CPU burn: hash iterations (tuned for 5 workers @ 20k logs/s)
    data = f"{response_time}-{http_status}-{level}"
    for _ in range(3):  # 3 iterations (reduced from 10)
        data = hashlib.sha256(data.encode()).hexdigest()
    
    return round(normalized * 100, 2)


def extract_patterns(message, http_path, stack_trace):
    """
    Complex pattern extraction using regex
    Simulates log parsing and pattern recognition
    """
    if not message:
        message = ""
    if not http_path:
        http_path = ""
    if not stack_trace:
        stack_trace = ""
    
    patterns_found = []
    combined_text = f"{message} {http_path} {stack_trace}"
    
    
    # Multiple regex patterns (CPU-intensive)
    # Simple pattern matching (reduced set)
    if "error" in combined_text.lower() or "exception" in combined_text.lower():
        patterns_found.append("error_keyword")
    
    # Simple word count metric instead of entropy
    words = combined_text.split()
    return len(patterns_found) + len(words) // 10
    


def compute_request_fingerprint(http_method, http_path, service, client_ip):
    """
    Generate unique fingerprint for request deduplication
    Uses multiple hashing algorithms
    """
    if not all([http_method, http_path, service]):
        return ""
    
    data = f"{http_method}:{http_path}:{service}:{client_ip or 'unknown'}"
    
    # Hash computations (Simplified)
    md5_hash = hashlib.md5(data.encode()).hexdigest()
    
    # Just return MD5, no heavy rehashing loop
    return md5_hash[:32]


def simulate_ml_classification(level, http_status, response_time, service):
    """
    Simulate a machine learning classification model
    for log severity prediction
    """
    if not all([level, http_status]):
        return 0
    
    # Feature vector computation (simulating feature engineering)
    features = []
    
    # One-hot encode level
    levels = ['DEBUG', 'INFO', 'WARN', 'ERROR']
    for l in levels:
        features.append(1.0 if level == l else 0.0)
    
    # Normalize http_status
    features.append((http_status - 200) / 500)
    
    # Normalize response_time
    rt = response_time or 0
    features.append(math.log(rt + 1) / 10)
    
    # Service encoding (simulating embedding lookup)
    services = ['api-gateway', 'auth-service', 'user-service', 
                'payment-service', 'order-service', 'notification-service']
    for s in services:
        features.append(1.0 if service == s else 0.0)
    
    # Simplified simulation (random based on input hash)
    # deterministic randomness based on features
    input_hash = hash(str(features))
    
    # Simple linear combination instead of neural net simulation
    score = (input_hash % 100)
    
    return score


# Register UDFs with Spark
anomaly_score_udf = udf(compute_anomaly_score, FloatType())
pattern_count_udf = udf(extract_patterns, IntegerType())
fingerprint_udf = udf(compute_request_fingerprint, StringType())
ml_classification_udf = udf(simulate_ml_classification, IntegerType())


def create_spark_session():
    """Create Spark session with settings for distributed processing"""
    return SparkSession.builder \
        .appName("LogAnalyticsStreaming-HeavyProcessing") \
        .config("spark.sql.streaming.checkpointLocation", CHECKPOINT_LOCATION) \
        .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0") \
        .config("spark.sql.adaptive.enabled", "true") \
        .config("spark.streaming.backpressure.enabled", "true") \
        .config("spark.sql.shuffle.partitions", "20") \
        .config("spark.default.parallelism", "20") \
        .config("spark.executor.cores", "2") \
        .config("spark.task.cpus", "1") \
        .getOrCreate()


def read_from_kafka(spark):
    """Read streaming data from Kafka"""
    return spark.readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS) \
        .option("subscribe", KAFKA_TOPIC) \
        .option("startingOffsets", "latest") \
        .option("failOnDataLoss", "false") \
        .option("kafka.request.timeout.ms", "120000") \
        .option("kafka.session.timeout.ms", "120000") \
        .option("maxOffsetsPerTrigger", "25000") \
        .load()


def parse_logs(kafka_df):
    """Parse JSON logs from Kafka messages"""
    return kafka_df \
        .selectExpr("CAST(value AS STRING) as json_str", "timestamp as kafka_timestamp") \
        .select(
            from_json(col("json_str"), LOG_SCHEMA).alias("log"),
            col("kafka_timestamp")
        ) \
        .select("log.*", "kafka_timestamp")


def enrich_with_heavy_processing(parsed_df):
    """
    Apply CPU-intensive transformations to the data
    This is where the heavy processing happens
    """
    enriched = parsed_df \
        .withColumn(
            "anomaly_score",
            anomaly_score_udf(col("response_time_ms"), col("http_status"), col("level"))
        ) \
        .withColumn(
            "pattern_count",
            pattern_count_udf(col("message"), col("http_path"), col("stack_trace"))
        ) \
        .withColumn(
            "request_fingerprint",
            fingerprint_udf(col("http_method"), col("http_path"), col("service"), col("client_ip"))
        ) \
        .withColumn(
            "ml_severity",
            ml_classification_udf(col("level"), col("http_status"), col("response_time_ms"), col("service"))
        ) \
        .withColumn(
            "is_anomaly",
            when(col("anomaly_score") > 60, 1).otherwise(0)
        ) \
        .withColumn(
            "is_critical",
            when(
                (col("level") == "ERROR") | 
                (col("http_status") >= 500) | 
                (col("anomaly_score") > 80),
                1
            ).otherwise(0)
        ) \
        .withColumn(
            "latency_bucket",
            when(col("response_time_ms") < 50, "fast")
            .when(col("response_time_ms") < 200, "normal")
            .when(col("response_time_ms") < 500, "slow")
            .otherwise("very_slow")
        ) \
        .withColumn(
            "path_hash",
            md5(col("http_path"))
        ) \
        .withColumn(
            "combined_hash",
            md5(concat(col("service"), lit(":"), col("http_method"), lit(":"), col("http_path")))
        )
    
    return enriched


def push_all_metrics(batch_df, batch_id):
    """
    Push ONLY original metrics (logs, error rate, latency)
    Heavy CPU processing already done in enrichment step
    When batch is empty, push 0 values so Grafana shows proper idle state
    """
    from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
    
    registry = CollectorRegistry()
    
    # Original metric definitions only
    log_gauge = Gauge('spark_logs_per_batch', 
                      'Logs processed per batch by service and level', 
                      ['service', 'level'], registry=registry)
    error_gauge = Gauge('spark_error_rate', 
                       'Error rate by service', 
                       ['service'], registry=registry)
    latency_gauge = Gauge('spark_latency_ms', 
                         'Response latency', 
                         ['service', 'percentile'], registry=registry)
    
    # Use count() instead of isEmpty() - triggers computation on Workers
    total_count = batch_df.count()
    
    if total_count == 0:
        # Push zeros for common services
        for service in ['api-gateway', 'user-service', 'order-service', 'payment-service', 'auth-service', 'notification-service']:
            for level in ['INFO', 'ERROR', 'DEBUG', 'WARN']:
                log_gauge.labels(service=service, level=level).set(0)
            error_gauge.labels(service=service).set(0)
            for percentile in ['p50', 'p95', 'p99']:
                latency_gauge.labels(service=service, percentile=percentile).set(0)
        try:
            push_to_gateway(PUSHGATEWAY_URL, job='spark_streaming', registry=registry)
            print(f"[Batch {batch_id}] No logs - pushed zeros (idle)")
        except Exception as e:
            print(f"[Batch {batch_id}] Failed to push: {e}")
        return
    
    # Aggregate on Workers, collect only small summary
    metrics = batch_df.groupBy("service", "level").agg(
        count("*").alias("log_count"),
        avg("response_time_ms").alias("avg_latency"),
        expr("percentile_approx(response_time_ms, 0.5)").alias("p50"),
        expr("percentile_approx(response_time_ms, 0.95)").alias("p95"),
        expr("percentile_approx(response_time_ms, 0.99)").alias("p99"),
        count(when(col("level") == "ERROR", 1)).alias("error_count"),
        count("*").alias("total_count")
    ).coalesce(1).collect()  # Coalesce to 1 partition for small result
    
    # Push metrics (small data, fast)
    service_totals = {}
    service_errors = {}
    
    for row in metrics:
        service = row.service
        level = row.level
        
        log_gauge.labels(service=service, level=level).set(row.log_count)
        
        service_totals[service] = service_totals.get(service, 0) + row.total_count
        service_errors[service] = service_errors.get(service, 0) + row.error_count
        
        if row.p50 is not None:
            latency_gauge.labels(service=service, percentile='p50').set(row.p50)
            latency_gauge.labels(service=service, percentile='p95').set(row.p95 or 0)
            latency_gauge.labels(service=service, percentile='p99').set(row.p99 or 0)
    
    # Error rates
    for service, total in service_totals.items():
        if total > 0:
            error_rate = (service_errors.get(service, 0) / total) * 100
            error_gauge.labels(service=service).set(error_rate)
    
    # Push to gateway
    try:
        push_to_gateway(PUSHGATEWAY_URL, job='spark_streaming', registry=registry)
        print(f"[Batch {batch_id}] Processed {total_count} logs (Workers did heavy CPU work)")
    except Exception as e:
        print(f"[Batch {batch_id}] Failed to push: {e}")


def main():
    print("=" * 60)
    print("Starting CPU-Intensive Spark Streaming Log Analytics")
    print("=" * 60)
    print(f"Trigger Interval: {TRIGGER_INTERVAL}")
    print("Features: Anomaly Detection, ML Classification, Pattern Extraction")
    print("Note: Heavy processing for CPU scaling demo, original metrics only")
    print("=" * 60)
    
    spark = create_spark_session()
    spark.sparkContext.setLogLevel("WARN")
    
    try:
        # Read from Kafka
        kafka_df = read_from_kafka(spark)
        
        # Parse JSON
        parsed_df = parse_logs(kafka_df)
        
        # Apply heavy CPU-intensive processing (this is the key part)
        enriched_df = enrich_with_heavy_processing(parsed_df)
        
        # Stream processing with original metrics push
        query = enriched_df.writeStream \
            .outputMode("append") \
            .trigger(processingTime=TRIGGER_INTERVAL) \
            .foreachBatch(push_all_metrics) \
            .queryName("cpu_intensive_analytics") \
            .start()
        
        print("Streaming query started. Processing logs with heavy computation...")
        query.awaitTermination()
        
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    main()

