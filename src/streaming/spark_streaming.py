from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    from_json, col, window, count, avg, 
    when, expr, current_timestamp
)
from pyspark.sql.types import (
    StructType, StructField, StringType, 
    IntegerType
)
import os

# Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka-1:29092,kafka-2:29093,kafka-3:29094')
KAFKA_TOPIC = os.getenv('KAFKA_TOPIC', 'application-logs')
CHECKPOINT_LOCATION = os.getenv('CHECKPOINT_LOCATION', '/tmp/spark-checkpoints/log-analytics')
PUSHGATEWAY_URL = os.getenv('PUSHGATEWAY_URL', 'http://pushgateway:9091')

# PROCESSING: Near-continuous (every 1 second)
TRIGGER_INTERVAL = os.getenv('TRIGGER_INTERVAL', '1 second')

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


def create_spark_session():
    """Create Spark session with optimized settings"""
    return SparkSession.builder \
        .appName("LogAnalyticsStreaming") \
        .config("spark.sql.streaming.checkpointLocation", CHECKPOINT_LOCATION) \
        .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0") \
        .config("spark.sql.adaptive.enabled", "true") \
        .config("spark.streaming.backpressure.enabled", "true") \
        .config("spark.sql.shuffle.partitions", "10") \
        .getOrCreate()


def read_from_kafka(spark):
    """Read streaming data from Kafka"""
    return spark.readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS) \
        .option("subscribe", KAFKA_TOPIC) \
        .option("startingOffsets", "latest") \
        .option("failOnDataLoss", "false") \
        .option("maxOffsetsPerTrigger", "10000") \
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


def push_all_metrics(batch_df, batch_id):
    """
    OPTIMIZED: Push ALL metrics in ONE function call
    Combines: log counts, error rates, and latency percentiles
    """
    from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
    
    if batch_df.isEmpty():
        return
    
    registry = CollectorRegistry()
    
    # Metric definitions - Using Gauge since we push fresh values each batch
    log_gauge = Gauge('spark_logs_per_batch', 
                      'Logs processed per batch by service and level', 
                      ['service', 'level'], registry=registry)
    error_gauge = Gauge('spark_error_rate', 
                       'Error rate by service', 
                       ['service'], registry=registry)
    latency_gauge = Gauge('spark_latency_ms', 
                         'Response latency', 
                         ['service', 'percentile'], registry=registry)
    
    # Calculate all metrics in one pass using Spark SQL
    # This avoids multiple collect() calls
    metrics = batch_df.groupBy("service", "level").agg(
        count("*").alias("log_count"),
        avg("response_time_ms").alias("avg_latency"),
        expr("percentile_approx(response_time_ms, 0.5)").alias("p50"),
        expr("percentile_approx(response_time_ms, 0.95)").alias("p95"),
        expr("percentile_approx(response_time_ms, 0.99)").alias("p99"),
        count(when(col("level") == "ERROR", 1)).alias("error_count"),
        count("*").alias("total_count")
    ).collect()
    
    # Service-level aggregates for error rate
    service_totals = {}
    service_errors = {}
    
    for row in metrics:
        service = row.service
        level = row.level
        
        # Log counts per batch (Gauge - shows current batch count)
        log_gauge.labels(service=service, level=level).set(row.log_count)
        
        # Accumulate for error rate calculation
        service_totals[service] = service_totals.get(service, 0) + row.total_count
        service_errors[service] = service_errors.get(service, 0) + row.error_count
        
        # Latency (first row per service wins)
        if row.p50 is not None:
            latency_gauge.labels(service=service, percentile='p50').set(row.p50)
            latency_gauge.labels(service=service, percentile='p95').set(row.p95 or 0)
            latency_gauge.labels(service=service, percentile='p99').set(row.p99 or 0)
    
    # Error rates
    for service, total in service_totals.items():
        if total > 0:
            error_rate = (service_errors.get(service, 0) / total) * 100
            error_gauge.labels(service=service).set(error_rate)
    
    # Single push with all metrics
    try:
        push_to_gateway(PUSHGATEWAY_URL, job='spark_streaming', registry=registry)
        print(f"[Batch {batch_id}] Pushed metrics for {len(metrics)} service-level combinations")
    except Exception as e:
        print(f"[Batch {batch_id}] Failed to push: {e}")


def main():
    print("Starting Optimized Spark Streaming Log Analytics...")
    print(f"Trigger Interval: {TRIGGER_INTERVAL}")
    
    spark = create_spark_session()
    spark.sparkContext.setLogLevel("WARN")
    
    try:
        # Read and parse
        kafka_df = read_from_kafka(spark)
        parsed_df = parse_logs(kafka_df)
        
        # OPTIMIZED: Single query with trigger interval
        query = parsed_df.writeStream \
            .outputMode("append") \
            .trigger(processingTime=TRIGGER_INTERVAL) \
            .foreachBatch(push_all_metrics) \
            .queryName("unified_metrics") \
            .start()
        
        print("Streaming query started. Processing logs...")
        query.awaitTermination()
        
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    main()
