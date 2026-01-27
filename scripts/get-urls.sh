#!/bin/bash
# Script to fetch Access URLs for Log Analytics System
# Usage: ./scripts/get-urls.sh

echo "=========================================="
echo "🔍 Fetching Access URLs..."
echo "=========================================="

# Helper to wait for IP
wait_for_ip() {
    local service=$1
    local ip=""
    # Check immediately first
    ip=$(kubectl get svc $service -n log-analytics -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null)
    
    if [ -n "$ip" ]; then
        echo "$ip"
        return
    fi

    echo -n "   Waiting for IP ($service)..." >&2
    # Loop 12 times * 5s = 60s max wait
    for i in {1..12}; do
        ip=$(kubectl get svc $service -n log-analytics -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null)
        if [ -n "$ip" ]; then
            echo " Done!" >&2
            echo "$ip"
            return
        fi
        echo -n "." >&2
        sleep 5
    done
    echo " Pending (Check GKE Console)"
}

GRAFANA_IP=$(wait_for_ip grafana)
WEB_IP=$(wait_for_ip log-web-manager)
PROMETHEUS_IP=$(wait_for_ip prometheus)
SPARK_UI_IP=$(wait_for_ip spark-master)

# Create Output File
OUTPUT_FILE="access-urls.txt"
cat <<EOF > $OUTPUT_FILE
==============================================
� Access URLs (Updated: $(date))
==============================================

1. 📊 Grafana Dashboard:
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

==============================================
EOF

# Display output
cat $OUTPUT_FILE
echo ""
echo "✅ Links saved to $OUTPUT_FILE"
