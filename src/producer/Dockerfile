FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY log_generator.py .

# Expose metrics port
EXPOSE 8000

# Run the producer
CMD ["python", "log_generator.py"]
