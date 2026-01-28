#!/bin/bash
# Deploy Log Analytics System to GKE
# Prerequisites:
#   - gcloud CLI installed and authenticated
#   - kubectl configured
#   - Docker images pushed to GCR

set -e

PROJECT_ID="${GCP_PROJECT_ID:-electric-tesla-482312-f2}"
CLUSTER_NAME="log-analytics-cluster"
REGION="asia-southeast1"
ZONE="${REGION}-a"

echo "=========================================="
echo "🚀 Deploying Log Analytics to GKE"
echo "=========================================="

# Step 1: Create GKE Cluster (if not exists)
echo "📦 Step 1: Creating GKE Cluster..."
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --project $PROJECT_ID &>/dev/null || \
gcloud container clusters create $CLUSTER_NAME \
    --zone $ZONE \
    --project $PROJECT_ID \
    --num-nodes 3 \
    --machine-type e2-standard-4 \
    --enable-autoscaling \
    --min-nodes 2 \
    --max-nodes 10 \
    --enable-autorepair \
    --enable-autoupgrade \
    --scopes "https://www.googleapis.com/auth/cloud-platform"

# Get credentials
gcloud container clusters get-credentials $CLUSTER_NAME --zone $ZONE --project $PROJECT_ID

# Step 2: Create namespace
echo "📁 Step 2: Creating namespace..."
kubectl apply -f k8s/namespace.yaml

# Step 3: Install Strimzi Kafka Operator
# Step 3: Deploy Kafka Cluster (Manual Mode - No Operator)
# Using standard StatefulSet to verify GKE environment and bypass RBAC issues
echo "� Step 3: Deploying Kafka (Manual Mode)..."
echo "   🧹 Removing any old Operator leftovers..."
# Cleanup old operator stuff just in case
helm uninstall strimzi-operator-fresh -n log-analytics --ignore-not-found --wait || true
helm uninstall strimzi-kafka-operator -n log-analytics --ignore-not-found --wait || true
kubectl delete deployment strimzi-cluster-operator -n log-analytics --ignore-not-found
kubectl delete crd kafkas.kafka.strimzi.io --ignore-not-found # Cleanup key CRD

echo "   🚀 Applying Kafka Manifests..."
# Restart Kafka to ensure clean state
kubectl delete -f k8s/kafka/kafka-manual.yaml --ignore-not-found
kubectl apply -f k8s/kafka/kafka-manual.yaml

# Wait for Zookeeper
echo "   ⏳ Waiting for Zookeeper..."
kubectl wait deployment/zookeeper --for=condition=Available --timeout=300s -n log-analytics

# Wait for Kafka
echo "   ⏳ Waiting for Kafka..."
# Wait for at least one pod ready
kubectl wait pod/kafka-0 --for=condition=Ready --timeout=300s -n log-analytics

# Operator wait skipped (Manual Mode)

# Step 4: Skip (Kafka deployed in Step 3)
# echo "📨 Step 4: Deploying Kafka Cluster..."
# kubectl apply -f k8s/kafka/kafka-metrics-config.yaml
# Wait for Kafka
echo "   ⏳ Waiting for Kafka cluster..."
kubectl wait pod/kafka-0 --for=condition=Ready --timeout=300s -n log-analytics
kubectl wait pod/kafka-1 --for=condition=Ready --timeout=300s -n log-analytics
kubectl wait pod/kafka-2 --for=condition=Ready --timeout=300s -n log-analytics

# Give DNS time to propagate (Critical for Headless Services)
echo "   ⏳ Waiting 30s for DNS propagation..."
sleep 30

# Explicitly create topic to prevent Spark UnknownTopicOrPartitionException
# Explicitly create topic with retries to handle DNS propagation delay
echo "   ✨ Ensuring 'application-logs' topic exists (with retries for DNS)..."
for i in {1..5}; do
    echo "   🔄 Attempt $i/5 to create topic..."
    kubectl delete pod kafka-init-topic -n log-analytics --ignore-not-found >/dev/null 2>&1
    if kubectl run -n log-analytics kafka-init-topic --image=confluentinc/cp-kafka:7.5.0 --restart=Never --rm --attach -- \
        kafka-topics --create --topic application-logs --bootstrap-server log-analytics-kafka-kafka-bootstrap.log-analytics.svc.cluster.local:9092 --partitions 3 --replication-factor 1 --if-not-exists; then
        echo "   ✅ Topic created/verified successfully."
        break
    else
        echo "   ⚠️ Failed to create topic. Retrying in 10s..."
        sleep 10
    fi
done
kubectl delete pod kafka-init-topic -n log-analytics --ignore-not-found
# Wait for Kafka
# echo "⏳ Waiting for Kafka cluster (this may take 5-10 minutes)..."
# kubectl wait kafka/log-analytics-kafka --for=condition=Ready --timeout=600s -n log-analytics

# Step 5: Deploy Spark Cluster (Manual Mode)
echo "🔥 Step 5: Deploying Spark Cluster (Manual Mode)..."
# Cleanup old operator stuff just in case
helm uninstall spark-operator -n log-analytics --ignore-not-found --wait || true
kubectl delete sparkapp --all -n log-analytics --ignore-not-found || true
kubectl delete deployment spark-operator-webhook -n log-analytics --ignore-not-found || true

# Update Image in Manual Manifests
echo "   🔧 Configuring Spark Manifests..."
# Reset placeholders first
sed -i "s|image: .*/spark-streaming:latest|image: spark-streaming:latest|g" k8s/spark-manual/*.yaml
# Apply Project ID
sed -i "s|image: spark-streaming:latest|image: gcr.io/$PROJECT_ID/spark-streaming:latest|g" k8s/spark-manual/*.yaml

echo "   🚀 Applying Spark Master & Worker..."
# Restart Spark Cluster
kubectl delete -f k8s/spark-manual/spark-master.yaml --ignore-not-found
kubectl delete -f k8s/spark-manual/spark-worker.yaml --ignore-not-found
kubectl delete -f k8s/spark-manual/spark-worker-hpa.yaml --ignore-not-found
# Clean up NFS as well to ensure fresh start
kubectl delete -f k8s/spark-manual/nfs-server.yaml --ignore-not-found

# Deploy NFS First
echo "   📦 Deploying NFS Server..."
kubectl apply -f k8s/spark-manual/nfs-server.yaml
echo "   ⏳ Waiting for NFS Server..."
kubectl wait deployment/nfs-server --for=condition=Available --timeout=300s -n log-analytics

kubectl apply -f k8s/spark-manual/spark-master.yaml
kubectl apply -f k8s/spark-manual/spark-worker.yaml
kubectl apply -f k8s/spark-manual/spark-worker-hpa.yaml

echo "   ⏳ Waiting for Spark Master..."
kubectl wait deployment/spark-master --for=condition=Available --timeout=300s -n log-analytics


# Step 6: Deploy Monitoring
echo "📊 Step 6: Deploying Monitoring Stack..."
# Restart Monitoring
kubectl delete -f k8s/monitoring/prometheus.yaml --ignore-not-found
kubectl delete -f k8s/monitoring/pushgateway.yaml --ignore-not-found
kubectl delete -f k8s/monitoring/grafana.yaml --ignore-not-found

kubectl apply -f k8s/monitoring/prometheus.yaml
kubectl apply -f k8s/monitoring/pushgateway.yaml
kubectl apply -f k8s/monitoring/grafana.yaml

# Step 7: Build and Push Docker Images
echo "🐳 Step 7: Building and pushing Docker images..."
# Log Producer (Now using log-web source)
# Using Cloud Build to bypass Cloud Shell network restrictions
yes | gcloud auth configure-docker || true
gcloud builds submit --tag gcr.io/$PROJECT_ID/log-web:latest src/webload/

# Spark Streaming
gcloud builds submit --tag gcr.io/$PROJECT_ID/spark-streaming:latest src/streaming/

# Update image in deployment
sed -i "s|log-web:latest|gcr.io/$PROJECT_ID/log-web:latest|g" k8s/producer/deployment.yaml

# Step 8: Deploy Applications
echo "🚀 Step 8: Deploying Applications..."
kubectl apply -f k8s/producer/rbac.yaml
# Restart Log Manager
kubectl delete hpa log-producer-hpa -n log-analytics --ignore-not-found
kubectl delete hpa log-web-worker -n log-analytics --ignore-not-found
kubectl delete -f k8s/producer/deployment.yaml --ignore-not-found
kubectl apply -f k8s/producer/deployment.yaml
# kubectl apply -f k8s/hpa/log-producer-hpa.yaml (Disabled: Managed by Web UI)

# Step 9: Deploy Spark Submit (Driver as Deployment Service)
echo "   🚀 Deploying Spark Submit Driver (Continuous Service)..."
# Delete old resources (both Job and Deployment) to ensure clean restart and image pull
kubectl delete job spark-submit -n log-analytics --ignore-not-found
kubectl delete deployment spark-submit -n log-analytics --ignore-not-found
kubectl apply -f k8s/spark-manual/spark-submit-job.yaml


# Step 9: Get URLs
echo ""
echo "=========================================="
echo "✅ Deployment Complete!"
echo "=========================================="
echo ""
echo "📊 Access URLs:"
GRAFANA_IP=""
WEB_IP=$(kubectl get svc log-web-manager -n log-analytics -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
PROMETHEUS_IP=$(kubectl get svc prometheus -n log-analytics -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
SPARK_UI_IP=$(kubectl get svc spark-master -n log-analytics -o jsonpath='{.status.loadBalancer.ingress[0].ip}')



echo "   ⏳ Waiting for LoadBalancers to assign IPs (this may take a minute)..."

# Helper to wait for IP
wait_for_ip() {
    local service=$1
    local ip=""
    # Loop 24 times * 5s = 120s max wait
    for i in {1..24}; do
        ip=$(kubectl get svc $service -n log-analytics -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null)
        if [ -n "$ip" ]; then
            echo "$ip"
            return
        fi
        echo -n "." >&2
        sleep 5
    done
    echo "Pending"
}

GRAFANA_IP=$(wait_for_ip grafana)
echo "" >&2
WEB_IP=$(wait_for_ip log-web-manager)
echo "" >&2
PROMETHEUS_IP=$(wait_for_ip prometheus)
echo "" >&2
# Spark Master UI
SPARK_UI_IP=$(wait_for_ip spark-master)
echo "" >&2

# Create Output File
OUTPUT_FILE="access-urls.txt"
cat <<EOF > $OUTPUT_FILE
==============================================
✅ Deployment Complete!
==============================================

📊 Access URLs:
1. � Grafana Dashboard:
   URL: http://$GRAFANA_IP:3000
   User: admin / Pass: admin123

2. 🕸️ Log Web Manager:
   URL: http://$WEB_IP:8088
   Endpoints: /status, /start, /stop

3. 🔍 Prometheus UI:
   URL: http://$PROMETHEUS_IP:9090

4. ⚡ SPARK MASTER UI:
   URL: http://$SPARK_UI_IP:8080
   Note: View running applications here.


5. 📨 KAFKA BROKERS (Internal Cluster DNS)
   - kafka-0.log-analytics-kafka-kafka-bootstrap.log-analytics.svc:9092
   - kafka-1.log-analytics-kafka-kafka-bootstrap.log-analytics.svc:9092
   - kafka-2.log-analytics-kafka-kafka-bootstrap.log-analytics.svc:9092

==================================================
Generated at: $(date)
EOF

cat $OUTPUT_FILE
echo ""
echo "✅ Links saved to $OUTPUT_FILE"
echo "📌 Useful Commands:"
echo "   kubectl get pods -n log-analytics"
echo "   kubectl logs -f deployment/log-web-manager -n log-analytics"
echo ""
