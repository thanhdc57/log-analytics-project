#!/usr/bin/env bash
# Startup script for MIG instances (log producer only)

set -euo pipefail

META="http://metadata.google.internal/computeMetadata/v1/instance/attributes"
REPO_URL="$(curl -fsS -H "Metadata-Flavor: Google" "$META/REPO_URL" || true)"
GIT_BRANCH="$(curl -fsS -H "Metadata-Flavor: Google" "$META/GIT_BRANCH" || echo "main")"
KAFKA_BOOTSTRAP_SERVERS="$(curl -fsS -H "Metadata-Flavor: Google" "$META/KAFKA_BOOTSTRAP_SERVERS" || true)"
LOG_RATE="$(curl -fsS -H "Metadata-Flavor: Google" "$META/LOG_RATE" || echo "200")"

if [[ -z "$REPO_URL" ]]; then
  echo "ERROR: REPO_URL is required"
  exit 1
fi

if [[ -z "$KAFKA_BOOTSTRAP_SERVERS" ]]; then
  echo "ERROR: KAFKA_BOOTSTRAP_SERVERS is required"
  exit 1
fi

apt-get update -y
apt-get install -y ca-certificates curl gnupg lsb-release git

if ! command -v docker >/dev/null 2>&1; then
  apt-get install -y docker.io
  systemctl enable --now docker
fi

mkdir -p /opt
if [[ ! -d /opt/log-analytics-project/.git ]]; then
  git clone -b "$GIT_BRANCH" "$REPO_URL" /opt/log-analytics-project
else
  cd /opt/log-analytics-project
  git fetch --all
  git checkout "$GIT_BRANCH"
  git pull
fi

cd /opt/log-analytics-project
docker build -t log-producer:latest src/producer

docker rm -f log-producer >/dev/null 2>&1 || true
docker run -d --name log-producer --restart unless-stopped \
  -e KAFKA_BOOTSTRAP_SERVERS="$KAFKA_BOOTSTRAP_SERVERS" \
  -e KAFKA_TOPIC="application-logs" \
  -e LOG_RATE="$LOG_RATE" \
  -e METRICS_PORT="8000" \
  -p 8000:8000 \
  log-producer:latest