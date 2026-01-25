"""
Spark Batch Analytics - Daily Log Aggregation and Analysis
Reads logs from storage (HDFS/GCS) and generates analytical reports
"""
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, date_format, hour, count, avg, max, min,
    when, sum as spark_sum, expr, lit, 
    to_timestamp, date_trunc
)
from pyspark.sql.types import (
    StructType, StructField, StringType, 
    IntegerType, TimestampType
)
import os
from datetime import datetime, timedelta

# Configuration
INPUT_PATH = os.getenv('INPUT_PATH', '/data/logs')
OUTPUT_PATH = os.getenv('OUTPUT_PATH', '/data/reports')
REPORT_DATE = os.getenv('REPORT_DATE', (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'))

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
    """Create Spark session for batch processing"""
    return SparkSession.builder \
        .appName("LogAnalyticsBatch") \
        .config("spark.sql.adaptive.enabled", "true") \
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true") \
        .getOrCreate()


def read_logs(spark, input_path, date_filter=None):
    """Read logs from storage"""
    df = spark.read \
        .schema(LOG_SCHEMA) \
        .json(f"{input_path}/*.json")
    
    # Parse timestamp
    df = df.withColumn("ts", to_timestamp(col("timestamp")))
    
    # Filter by date if specified
    if date_filter:
        df = df.filter(date_format(col("ts"), "yyyy-MM-dd") == date_filter)
    
    return df


def hourly_aggregation(df):
    """Aggregate logs by hour and service"""
    return df \
        .withColumn("hour", hour(col("ts"))) \
        .groupBy("hour", "service") \
        .agg(
            count("*").alias("total_logs"),
            count(when(col("level") == "ERROR", 1)).alias("error_count"),
            count(when(col("level") == "WARN", 1)).alias("warn_count"),
            count(when(col("level") == "INFO", 1)).alias("info_count"),
            avg("response_time_ms").alias("avg_response_time"),
            expr("percentile_approx(response_time_ms, 0.5)").alias("p50_response_time"),
            expr("percentile_approx(response_time_ms, 0.95)").alias("p95_response_time"),
            expr("percentile_approx(response_time_ms, 0.99)").alias("p99_response_time"),
            max("response_time_ms").alias("max_response_time"),
            min("response_time_ms").alias("min_response_time")
        ) \
        .withColumn("error_rate", (col("error_count") / col("total_logs") * 100)) \
        .orderBy("hour", "service")


def service_summary(df):
    """Generate service-level summary"""
    return df \
        .groupBy("service") \
        .agg(
            count("*").alias("total_requests"),
            count(when(col("http_status") >= 500, 1)).alias("server_errors"),
            count(when((col("http_status") >= 400) & (col("http_status") < 500), 1)).alias("client_errors"),
            count(when(col("http_status") < 400, 1)).alias("successful_requests"),
            avg("response_time_ms").alias("avg_response_time_ms"),
            expr("percentile_approx(response_time_ms, 0.95)").alias("p95_response_time_ms"),
            expr("percentile_approx(response_time_ms, 0.99)").alias("p99_response_time_ms")
        ) \
        .withColumn("success_rate", 
                    (col("successful_requests") / col("total_requests") * 100)) \
        .withColumn("error_rate", 
                    (col("server_errors") / col("total_requests") * 100)) \
        .orderBy(col("total_requests").desc())


def endpoint_analytics(df):
    """Analyze performance by HTTP endpoint"""
    return df \
        .filter(col("http_path").isNotNull()) \
        .groupBy("http_path", "http_method") \
        .agg(
            count("*").alias("request_count"),
            avg("response_time_ms").alias("avg_response_time"),
            expr("percentile_approx(response_time_ms, 0.95)").alias("p95_response_time"),
            count(when(col("http_status") >= 500, 1)).alias("error_count")
        ) \
        .withColumn("error_rate", (col("error_count") / col("request_count") * 100)) \
        .orderBy(col("request_count").desc())


def error_analysis(df):
    """Detailed error analysis"""
    return df \
        .filter(col("level") == "ERROR") \
        .groupBy("service", "message") \
        .agg(
            count("*").alias("occurrence_count"),
            min("ts").alias("first_occurrence"),
            max("ts").alias("last_occurrence")
        ) \
        .orderBy(col("occurrence_count").desc())


def traffic_pattern(df):
    """Analyze traffic patterns by hour"""
    return df \
        .withColumn("hour", hour(col("ts"))) \
        .groupBy("hour") \
        .agg(
            count("*").alias("request_count"),
            count(when(col("level") == "ERROR", 1)).alias("error_count"),
            avg("response_time_ms").alias("avg_response_time")
        ) \
        .orderBy("hour")


def save_report(df, output_path, report_name, report_date):
    """Save report to storage"""
    full_path = f"{output_path}/{report_date}/{report_name}"
    df.coalesce(1) \
        .write \
        .mode("overwrite") \
        .json(full_path)
    print(f"Report saved to: {full_path}")


def generate_summary_stats(df):
    """Generate overall summary statistics"""
    stats = df.agg(
        count("*").alias("total_logs"),
        count(when(col("level") == "ERROR", 1)).alias("total_errors"),
        count(when(col("level") == "WARN", 1)).alias("total_warnings"),
        avg("response_time_ms").alias("avg_response_time"),
        expr("percentile_approx(response_time_ms, 0.99)").alias("p99_response_time")
    ).collect()[0]
    
    return {
        "total_logs": stats["total_logs"],
        "total_errors": stats["total_errors"],
        "total_warnings": stats["total_warnings"],
        "error_rate": round((stats["total_errors"] / stats["total_logs"]) * 100, 2) if stats["total_logs"] > 0 else 0,
        "avg_response_time_ms": round(stats["avg_response_time"], 2) if stats["avg_response_time"] else 0,
        "p99_response_time_ms": stats["p99_response_time"]
    }


def main():
    print(f"Starting Batch Analytics for date: {REPORT_DATE}")
    
    # Create Spark session
    spark = create_spark_session()
    spark.sparkContext.setLogLevel("WARN")
    
    # Read logs
    print(f"Reading logs from: {INPUT_PATH}")
    logs_df = read_logs(spark, INPUT_PATH, REPORT_DATE)
    
    # Cache for multiple operations
    logs_df.cache()
    
    log_count = logs_df.count()
    print(f"Total logs to process: {log_count}")
    
    if log_count == 0:
        print("No logs found for the specified date. Exiting.")
        return
    
    # Generate summary stats
    print("\n=== Summary Statistics ===")
    summary = generate_summary_stats(logs_df)
    for key, value in summary.items():
        print(f"  {key}: {value}")
    
    # Generate reports
    print("\n=== Generating Reports ===")
    
    # 1. Hourly aggregation
    print("1. Hourly Aggregation...")
    hourly_df = hourly_aggregation(logs_df)
    save_report(hourly_df, OUTPUT_PATH, "hourly_aggregation", REPORT_DATE)
    
    # 2. Service summary
    print("2. Service Summary...")
    service_df = service_summary(logs_df)
    save_report(service_df, OUTPUT_PATH, "service_summary", REPORT_DATE)
    service_df.show(truncate=False)
    
    # 3. Endpoint analytics
    print("3. Endpoint Analytics...")
    endpoint_df = endpoint_analytics(logs_df)
    save_report(endpoint_df, OUTPUT_PATH, "endpoint_analytics", REPORT_DATE)
    
    # 4. Error analysis
    print("4. Error Analysis...")
    error_df = error_analysis(logs_df)
    save_report(error_df, OUTPUT_PATH, "error_analysis", REPORT_DATE)
    
    # 5. Traffic pattern
    print("5. Traffic Pattern...")
    traffic_df = traffic_pattern(logs_df)
    save_report(traffic_df, OUTPUT_PATH, "traffic_pattern", REPORT_DATE)
    traffic_df.show()
    
    # Unpersist
    logs_df.unpersist()
    
    print(f"\n=== Batch Analytics Complete ===")
    print(f"Reports saved to: {OUTPUT_PATH}/{REPORT_DATE}/")
    
    spark.stop()


if __name__ == "__main__":
    main()
