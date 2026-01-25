#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-}"
ZONE="${GCP_ZONE:-}"

if [[ -z "$PROJECT_ID" ]]; then
  echo "ERROR: GCP_PROJECT_ID is required"
  exit 1
fi

if [[ -z "$ZONE" ]]; then
  echo "ERROR: GCP_ZONE is required"
  exit 1
fi

SRC="config/prometheus/prometheus-gce.yml"
DST="config/prometheus/prometheus-gce.generated.yml"

sed -e "s|__GCP_PROJECT_ID__|$PROJECT_ID|g" -e "s|__GCP_ZONE__|$ZONE|g" "$SRC" > "$DST"
echo "Generated $DST"