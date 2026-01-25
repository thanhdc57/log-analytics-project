#!/usr/bin/env bash
# Deploy Log Analytics on GCE using MIG (no Kubernetes)
# Required env:
#   GCP_PROJECT_ID
#   REPO_URL
# Optional env:
#   GIT_BRANCH, REGION, ZONE, LOG_RATE

set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-}"
REPO_URL="${REPO_URL:-}"
GIT_BRANCH="${GIT_BRANCH:-main}"
REGION="${REGION:-asia-southeast1}"
ZONE="${ZONE:-${REGION}-a}"
LOG_RATE="${LOG_RATE:-200}"

CORE_VM="log-analytics-core"
MIG_NAME="log-producer-mig"
TEMPLATE_NAME="log-producer-template"

if [[ -z "$PROJECT_ID" ]]; then
  echo "ERROR: GCP_PROJECT_ID is required"
  exit 1
fi

if [[ -z "$REPO_URL" ]]; then
  echo "ERROR: REPO_URL is required"
  exit 1
fi

gcloud config set project "$PROJECT_ID"
gcloud services enable compute.googleapis.com >/dev/null

create_firewall_rule() {
  local name="$1"
  local ports="$2"
  local tags="$3"

  if gcloud compute firewall-rules describe "$name" >/dev/null 2>&1; then
    echo "Firewall rule $name already exists"
  else
    gcloud compute firewall-rules create "$name" \
      --allow "$ports" \
      --target-tags "$tags" \
      --source-ranges 0.0.0.0/0
  fi
}

echo "🔐 Creating firewall rules..."
create_firewall_rule "log-analytics-core-allow" "tcp:9092,tcp:3000,tcp:9090,tcp:8080,tcp:8081,tcp:9091" "log-analytics-core"

echo "🖥️ Creating core VM (Kafka + Spark + Monitoring)..."
if gcloud compute instances describe "$CORE_VM" --zone "$ZONE" >/dev/null 2>&1; then
  echo "Core VM already exists"
else
  gcloud compute instances create "$CORE_VM" \
    --zone "$ZONE" \
    --machine-type "e2-standard-4" \
    --tags "log-analytics-core" \
    --metadata "REPO_URL=$REPO_URL,GIT_BRANCH=$GIT_BRANCH" \
    --metadata-from-file startup-script="scripts/startup-core.sh"
fi

echo "⏳ Waiting for core VM to start..."
gcloud compute instances describe "$CORE_VM" --zone "$ZONE" >/dev/null

KAFKA_IP=$(gcloud compute instances describe "$CORE_VM" --zone "$ZONE" --format='get(networkInterfaces[0].networkIP)')
KAFKA_BOOTSTRAP="$KAFKA_IP:9092"

echo "⚙️ Creating/Updating instance template for MIG..."
if gcloud compute instance-templates describe "$TEMPLATE_NAME" >/dev/null 2>&1; then
  gcloud compute instance-templates delete "$TEMPLATE_NAME" -q
fi

gcloud compute instance-templates create "$TEMPLATE_NAME" \
  --machine-type "e2-standard-2" \
  --tags "log-producer" \
  --metadata "REPO_URL=$REPO_URL,GIT_BRANCH=$GIT_BRANCH,KAFKA_BOOTSTRAP_SERVERS=$KAFKA_BOOTSTRAP,LOG_RATE=$LOG_RATE" \
  --metadata-from-file startup-script="scripts/startup-producer.sh"

echo "📦 Creating/Updating MIG..."
if gcloud compute instance-groups managed describe "$MIG_NAME" --zone "$ZONE" >/dev/null 2>&1; then
  gcloud compute instance-groups managed set-instance-template "$MIG_NAME" \
    --zone "$ZONE" \
    --template "$TEMPLATE_NAME"
else
  gcloud compute instance-groups managed create "$MIG_NAME" \
    --zone "$ZONE" \
    --template "$TEMPLATE_NAME" \
    --size 1
fi

gcloud compute instance-groups managed set-autoscaling "$MIG_NAME" \
  --zone "$ZONE" \
  --min-num-replicas 1 \
  --max-num-replicas 5 \
  --target-cpu-utilization 0.6 \
  --cool-down-period 90

CORE_EXT_IP=$(gcloud compute instances describe "$CORE_VM" --zone "$ZONE" --format='get(networkInterfaces[0].accessConfigs[0].natIP)')

echo ""
echo "=========================================="
echo "✅ Deployment Complete!"
echo "=========================================="
echo "Core VM External IP: $CORE_EXT_IP"
echo "Grafana:    http://$CORE_EXT_IP:3000 (admin/admin123)"
echo "Prometheus: http://$CORE_EXT_IP:9090"
echo "Kafka UI:   http://$CORE_EXT_IP:8080"
echo "Spark UI:   http://$CORE_EXT_IP:8081"
echo ""
echo "MIG Name: $MIG_NAME"
echo "Kafka Bootstrap: $KAFKA_BOOTSTRAP"
echo ""