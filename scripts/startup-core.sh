#!/usr/bin/env bash
# Startup script for the core VM (Kafka + Spark + Monitoring)

set -euo pipefail

META="http://metadata.google.internal/computeMetadata/v1/instance/attributes"
REPO_URL="$(curl -fsS -H "Metadata-Flavor: Google" "$META/REPO_URL" || true)"
GIT_BRANCH="$(curl -fsS -H "Metadata-Flavor: Google" "$META/GIT_BRANCH" || echo "main")"

if [[ -z "$REPO_URL" ]]; then
  echo "ERROR: REPO_URL is required"
  exit 1
fi

apt-get update -y
apt-get install -y ca-certificates curl gnupg lsb-release git

if ! command -v docker >/dev/null 2>&1; then
  apt-get install -y docker.io
  systemctl enable --now docker
fi

if ! command -v docker-compose >/dev/null 2>&1; then
  apt-get install -y docker-compose
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

KAFKA_HOST=$(curl -s -H "Metadata-Flavor: Google" \
  http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/ip)

cat >/opt/log-analytics-project/.env <<EOF
KAFKA_HOST=$KAFKA_HOST
EOF

cd /opt/log-analytics-project
docker-compose -f docker-compose.gce-core.yml up -d --build