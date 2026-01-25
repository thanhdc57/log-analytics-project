FROM apache/spark:3.5.0

USER root

# Install Python dependencies
RUN pip install prometheus_client

# Copy application code
WORKDIR /opt/spark-apps
COPY spark_streaming.py streaming/spark_streaming.py

USER 185
