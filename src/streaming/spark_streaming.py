"""
Spark Structured Streaming - Real-time Log Analytics
Consumes logs from Kafka, processes them, and pushes metrics to Prometheus
"""
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    from_json, col, window, count, avg, 
    when, lit, current_timestamp, expr
)
from pyspark.sql.types import (
    StructType, StructField, StringType, 
    IntegerType, TimestampType
)
import os

# Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka-1:29092,kafka-2:29093,kafka-3:29094')
KAFKA_TOPIC = os.getenv('KAFKA_TOPIC', 'application-logs')
CHECKPOINT_LOCATION = os.getenv('CHECKPOINT_LOCATION', '/tmp/spark-checkpoints/log-analytics')
PUSHGATEWAY_URL = os.getenv('PUSHGATEWAY_URL', 'http://pushgateway:9091')

# Log schema matching the producer output
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
    """Create Spark session with Kafka support"""
    return SparkSession.builder \
        .appName("LogAnalyticsStreaming") \
        .config("spark.sql.streaming.checkpointLocation", CHECKPOINT_LOCATION) \
        .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0") \
        .config("spark.sql.adaptive.enabled", "true") \
        .config("spark.streaming.backpressure.enabled", "true") \
        .getOrCreate()


def read_from_kafka(spark):
    """Read streaming data from Kafka"""
    return spark.readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS) \
        .option("subscribe", KAFKA_TOPIC) \
        .option("startingOffsets", "latest") \
        .option("failOnDataLoss", "false") \
        .load()


import time
from pyspark.sql.functions import udf

@udf(StringType())
def heavy_processing_simulation(val):
    """Simulate CPU intensive task to force scaling (Busy Wait)"""
    # Busy loop to burn CPU cycles (trigger HPA) without sleeping
    # 5000 iterations of math is negligible latency but measurable CPU
    _ = [x**2 for x in range(5000)]
    return val

def parse_logs(kafka_df):
    """Parse JSON logs from Kafka messages and simulate load"""
    parsed = kafka_df \
        .selectExpr("CAST(value AS STRING) as json_str", "timestamp as kafka_timestamp") \
        .select(
            from_json(col("json_str"), LOG_SCHEMA).alias("log"),
            col("kafka_timestamp")
        ) \
        .select("log.*", "kafka_timestamp")
    
    # Apply simulation (Busy Wait for CPU Scaling)
    return parsed.withColumn("message", heavy_processing_simulation(col("message")))


def calculate_metrics(parsed_df):
    """Calculate real-time metrics with windowing"""
    
    # 1-minute window aggregations
    metrics_1m = parsed_df \
        .withWatermark("kafka_timestamp", "1 minute") \
        .groupBy(
            window(col("kafka_timestamp"), "1 minute"),
            col("service"),
            col("level")
        ) \
        .agg(
            count("*").alias("log_count"),
            avg("response_time_ms").alias("avg_response_time"),
            count(when(col("http_status") >= 500, 1)).alias("error_count"),
            count(when(col("http_status") >= 400, 1)).alias("client_error_count")
        )
    
    return metrics_1m


def calculate_error_rate(parsed_df):
    """Calculate error rate per service in 5-minute windows"""
    return parsed_df \
        .withWatermark("kafka_timestamp", "5 minutes") \
        .groupBy(
            window(col("kafka_timestamp"), "5 minutes"),
            col("service")
        ) \
        .agg(
            count("*").alias("total_logs"),
            count(when(col("level") == "ERROR", 1)).alias("error_logs")
        ) \
        .withColumn("error_rate", 
                    (col("error_logs") / col("total_logs") * 100).cast("double"))


def calculate_latency_percentiles(parsed_df):
    """Calculate response time percentiles per service"""
    return parsed_df \
        .withWatermark("kafka_timestamp", "5 minutes") \
        .groupBy(
            window(col("kafka_timestamp"), "5 minutes"),
            col("service")
        ) \
        .agg(
            expr("percentile_approx(response_time_ms, 0.5)").alias("p50_latency"),
            expr("percentile_approx(response_time_ms, 0.95)").alias("p95_latency"),
            expr("percentile_approx(response_time_ms, 0.99)").alias("p99_latency"),
            avg("response_time_ms").alias("avg_latency")
        )


def write_to_console(df, query_name):
    """Write stream to console for debugging"""
    return df.writeStream \
        .outputMode("update") \
        .format("console") \
        .option("truncate", "false") \
        .queryName(query_name) \
        .start()


def push_log_counts(batch_df, batch_id):
    """Push log counts to Prometheus"""
    from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
    registry = CollectorRegistry()
    g = Gauge('spark_log_count', 'Log count by service and level', 
              ['service', 'level'], registry=registry)
    
    rows = batch_df.collect()
    for row in rows:
        g.labels(service=row.service, level=row.level).set(row.log_count)
    
    try:
        push_to_gateway(PUSHGATEWAY_URL, job='spark_counts', registry=registry)
    except Exception as e:
        print(f"Failed to push counts: {e}")

def push_error_rates(batch_df, batch_id):
    """Push error rates to Prometheus"""
    from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
    registry = CollectorRegistry()
    g = Gauge('spark_error_rate', 'Error rate by service', ['service'], registry=registry)
    
    rows = batch_df.collect()
    for row in rows:
        g.labels(service=row.service).set(row.error_rate)
        
    try:
        push_to_gateway(PUSHGATEWAY_URL, job='spark_errors', registry=registry)
    except Exception as e:
        print(f"Failed to push errors: {e}")

def push_latency(batch_df, batch_id):
    """Push latency metrics to Prometheus"""
    from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
    registry = CollectorRegistry()
    g = Gauge('spark_latency_ms', 'Response latency', ['service', 'percentile'], registry=registry)
    
    rows = batch_df.collect()
    for row in rows:
        g.labels(service=row.service, percentile='p50').set(row.p50_latency or 0)
        g.labels(service=row.service, percentile='p95').set(row.p95_latency or 0)
        g.labels(service=row.service, percentile='p99').set(row.p99_latency or 0)
        
    try:
        push_to_gateway(PUSHGATEWAY_URL, job='spark_latency', registry=registry)
    except Exception as e:
        print(f"Failed to push latency: {e}")

def main():
    print("Starting Spark Streaming Log Analytics...")
    
    # Create Spark session
    spark = create_spark_session()
    spark.sparkContext.setLogLevel("WARN")
    
    # Read from Kafka
    kafka_df = read_from_kafka(spark)
    
    # Parse logs
    parsed_df = parse_logs(kafka_df)
    
    # Calculate different metrics
    metrics_1m = calculate_metrics(parsed_df)
    error_rates = calculate_error_rate(parsed_df)
    latency_percentiles = calculate_latency_percentiles(parsed_df)
    
    # Start queries
    
    # Query 1: Log Counts to Prometheus
    q1 = metrics_1m.writeStream \
        .outputMode("update") \
        .foreachBatch(push_log_counts) \
        .queryName("push_counts") \
        .start()

    # Query 2: Error Rates to Prometheus
    q2 = error_rates.writeStream \
        .outputMode("update") \
        .foreachBatch(push_error_rates) \
        .queryName("push_errors") \
        .start()

    # Query 3: Latency to Prometheus
    q3 = latency_percentiles.writeStream \
        .outputMode("update") \
        .foreachBatch(push_latency) \
        .queryName("push_latency") \
        .start()
    
    # Debug Console
    q_console = write_to_console(metrics_1m, "debug_console")
    
    print("Streaming queries started. Waiting for data...")
    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
