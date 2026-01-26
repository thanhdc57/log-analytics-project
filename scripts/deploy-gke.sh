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
# Step 3: Install Strimzi Kafka Operator
echo "🔧 Step 3: Installing Strimzi Kafka Operator (YAML Method)..."

# 0. Ensure YOU have admin rights (Required on GKE to grant rights to others)
echo "   🔑 Granting admin rights to current user..."
USER_ACCOUNT=$(gcloud config get-value core/account)
kubectl create clusterrolebinding cluster-admin-binding --clusterrole=cluster-admin --user=$USER_ACCOUNT --dry-run=client -o yaml | kubectl apply -f -

# 1. Cleanup Old Installations (Helm & YAML)
echo "   🧹 Cleaning up old installations..."
helm uninstall strimzi-operator-fresh -n log-analytics --ignore-not-found --wait || true
helm uninstall strimzi-kafka-operator -n log-analytics --ignore-not-found --wait || true
# Delete old CRDs to ensure clean slate
kubectl get crd | grep strimzi | awk '{print $1}' | xargs -r kubectl delete crd --ignore-not-found

# 2. Cleanup leftovers
kubectl delete rolebinding strimzi-cluster-operator -n log-analytics --ignore-not-found
kubectl delete clusterrolebinding strimzi-cluster-operator-namespaced --ignore-not-found
kubectl delete clusterrolebinding strimzi-cluster-operator-leader-election --ignore-not-found
kubectl delete clusterrolebinding strimzi-cluster-operator-global --ignore-not-found

echo "   ⏳ Waiting for cleanup..."
sleep 15

# 3. Install via YAML (Stable Method)
echo "   🚀 Installing Strimzi 0.44.0..."
curl -L https://github.com/strimzi/strimzi-kafka-operator/releases/download/0.44.0/strimzi-cluster-operator-0.44.0.yaml \
  | sed 's/namespace: .*/namespace: log-analytics/' \
  | kubectl apply -f - -n log-analytics

# Wait for operator
echo "⏳ Waiting for Strimzi Operator..."
kubectl wait --for=condition=available --timeout=300s deployment/strimzi-cluster-operator -n log-analytics

# Step 4: Deploy Kafka
echo "📨 Step 4: Deploying Kafka Cluster..."
kubectl apply -f k8s/kafka/kafka-metrics-config.yaml
kubectl apply -f k8s/kafka/kafka-cluster.yaml

# Wait for Kafka
echo "⏳ Waiting for Kafka cluster (this may take 5-10 minutes)..."
kubectl wait kafka/log-analytics-kafka --for=condition=Ready --timeout=600s -n log-analytics

# Step 5: Install Spark Operator
echo "🔧 Step 5: Installing Spark Operator..."
helm repo add spark-operator https://kubeflow.github.io/spark-operator
helm repo update
helm upgrade --install spark-operator spark-operator/spark-operator \
    --namespace log-analytics \
    --set webhook.enable=true \
    --set image.tag=v1beta2-1.4.0-3.5.0

# Step 6: Deploy Monitoring
echo "📊 Step 6: Deploying Monitoring Stack..."
kubectl apply -f k8s/monitoring/prometheus.yaml
kubectl apply -f k8s/monitoring/grafana.yaml

# Step 7: Build and Push Docker Images
echo "🐳 Step 7: Building and pushing Docker images..."
# Log Producer (Now using log-web source)
docker build -t gcr.io/$PROJECT_ID/log-web:latest src/webload/
docker push gcr.io/$PROJECT_ID/log-web:latest

# Spark Streaming
docker build -t gcr.io/$PROJECT_ID/spark-streaming:latest src/streaming/
docker push gcr.io/$PROJECT_ID/spark-streaming:latest

# Update image in deployment
sed -i "s|log-producer:latest|gcr.io/$PROJECT_ID/log-web:latest|g" k8s/producer/deployment.yaml

# Step 8: Deploy Applications
echo "🚀 Step 8: Deploying Applications..."
kubectl apply -f k8s/producer/rbac.yaml
kubectl apply -f k8s/producer/deployment.yaml
# kubectl apply -f k8s/hpa/log-producer-hpa.yaml (Disabled: Managed by Web UI)

# Update and deploy Spark
sed -i "s|spark-streaming:latest|gcr.io/$PROJECT_ID/spark-streaming:latest|g" k8s/spark/spark-streaming.yaml
kubectl apply -f k8s/spark/spark-streaming.yaml

# Step 9: Get URLs
echo ""
echo "=========================================="
echo "✅ Deployment Complete!"
echo "=========================================="
echo ""
echo "📊 Access URLs:"
GRAFANA_IP=$(kubectl get svc grafana -n log-analytics -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo "   Grafana: http://$GRAFANA_IP:3000 (admin/admin123)"
echo ""
echo "📌 Useful Commands:"
echo "   kubectl get pods -n log-analytics"
echo "   kubectl get hpa -n log-analytics"
echo "   kubectl logs -f deployment/log-producer -n log-analytics"
echo ""
